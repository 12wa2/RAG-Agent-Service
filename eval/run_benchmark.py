from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.messages import HumanMessage

from agent.react_agent import ReactAgent
from model.factory import chat_model
from rag.rag_service import RagSummarizeService


DEFAULT_OUTPUTS = {
    "prompt_only": "eval/outputs/prompt_only_answers.jsonl",
    "rag": "eval/outputs/rag_answers.jsonl",
    "rag_reranker": "eval/outputs/rag_reranker_answers.jsonl",
    "lora_rag": "eval/outputs/lora_rag_answers.jsonl",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def dump_jsonl_row(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
            elif isinstance(item, str):
                text_parts.append(item)
        return "".join(text_parts).strip()

    return str(content).strip() if content is not None else ""


def run_prompt_only(query: str) -> dict[str, Any]:
    response = chat_model.invoke([HumanMessage(content=query)])
    return {
        "answer": normalize_text(getattr(response, "content", "")),
        "retrieved_context": "",
        "tool_success": False,
    }


def run_rag(query: str, service: RagSummarizeService, use_rerank: bool) -> dict[str, Any]:
    answer, context = service.answer_with_context(query, use_rerank=use_rerank, top_n=5)
    return {
        "answer": normalize_text(answer),
        "retrieved_context": context,
        "tool_success": False,
    }


def run_lora_rag(query: str, agent: ReactAgent) -> dict[str, Any]:
    result = agent.execute([{"role": "user", "content": query}])
    return {
        "answer": normalize_text(result.get("answer", "")),
        "retrieved_context": "\n".join(result.get("tool_outputs", [])),
        "tool_success": bool(result.get("tool_used", False)),
    }


def select_cases(
    all_cases: list[dict[str, Any]],
    case_id: str | None,
    offset: int,
    limit: int | None,
) -> list[dict[str, Any]]:
    selected = all_cases
    if case_id:
        selected = [case for case in selected if case.get("id") == case_id]

    if offset:
        selected = selected[offset:]

    if limit is not None:
        selected = selected[:limit]

    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Run benchmark cases one by one and write answers to JSONL.")
    parser.add_argument(
        "--scheme",
        required=True,
        choices=["prompt_only", "rag", "rag_reranker", "lora_rag"],
        help="要执行的评测方案",
    )
    parser.add_argument("--cases", default="eval/benchmark_cases.jsonl", help="测试集 JSONL 路径")
    parser.add_argument("--output", help="输出 JSONL 路径，不传则按方案使用默认路径")
    parser.add_argument("--case-id", help="只运行指定用例 ID")
    parser.add_argument("--offset", type=int, default=0, help="从第几条用例开始")
    parser.add_argument("--limit", type=int, help="最多执行多少条用例")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="覆盖已有输出文件并从头执行；默认会保留已有结果并跳过已完成 case_id",
    )
    args = parser.parse_args()

    cases_path = Path(args.cases)
    output_path = Path(args.output or DEFAULT_OUTPUTS[args.scheme])
    cases = load_jsonl(cases_path)
    selected_cases = select_cases(cases, args.case_id, args.offset, args.limit)

    if not selected_cases:
        print("没有匹配到待执行的测试用例。")
        return 1

    existing_case_ids: set[str] = set()
    if args.overwrite and output_path.exists():
        output_path.unlink()
    elif output_path.exists():
        existing_case_ids = {
            row.get("case_id", "")
            for row in load_jsonl(output_path)
            if row.get("case_id")
        }

    rag_service: RagSummarizeService | None = None
    agent: ReactAgent | None = None

    if args.scheme in {"rag", "rag_reranker"}:
        rag_service = RagSummarizeService()
    elif args.scheme == "lora_rag":
        agent = ReactAgent()

    pending_cases = [case for case in selected_cases if case.get("id") not in existing_case_ids]
    if not pending_cases:
        print(f"{args.scheme} 的目标用例都已经完成，无需重复执行。")
        print(f"结果文件：{output_path}")
        return 0

    print(f"开始执行方案：{args.scheme}")
    print(f"待执行用例数：{len(pending_cases)}")
    print(f"结果文件：{output_path}")

    total = len(pending_cases)
    for index, case in enumerate(pending_cases, start=1):
        case_id = case["id"]
        query = case["query"]
        print(f"[{index}/{total}] {case_id} -> {query}")

        if args.scheme == "prompt_only":
            result = run_prompt_only(query)
        elif args.scheme == "rag":
            assert rag_service is not None
            result = run_rag(query, rag_service, use_rerank=False)
        elif args.scheme == "rag_reranker":
            assert rag_service is not None
            result = run_rag(query, rag_service, use_rerank=True)
        else:
            assert agent is not None
            result = run_lora_rag(query, agent)

        row = {
            "scheme": args.scheme,
            "case_id": case_id,
            "answer": result["answer"],
            "retrieved_context": result["retrieved_context"],
            "tool_expected": bool(case.get("requires_tool", False)),
            "tool_success": bool(result["tool_success"]),
        }
        dump_jsonl_row(output_path, row)
        print(f"已写入：{case_id}")

    print("执行完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
