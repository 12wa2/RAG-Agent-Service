from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def normalize_text(text: str) -> str:
    return text.lower().strip()


def contains_keyword(text: str, keyword: str) -> bool:
    return bool(keyword) and normalize_text(keyword) in normalize_text(text)


def count_matches(text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if contains_keyword(text, keyword))


def score_rule(text: str, rule: Any) -> float:
    if isinstance(rule, str):
        return 1.0 if contains_keyword(text, rule) else 0.0

    if not isinstance(rule, dict):
        return 0.0

    all_of = [item for item in rule.get("all_of", []) if item]
    any_of = [item for item in rule.get("any_of", []) if item]
    none_of = [item for item in rule.get("none_of", []) if item]

    if none_of and any(contains_keyword(text, item) for item in none_of):
        return 0.0

    components: list[float] = []
    if all_of:
        components.append(count_matches(text, all_of) / len(all_of))

    if any_of:
        min_any = max(int(rule.get("min_any", 1)), 1)
        matched_any = count_matches(text, any_of)
        components.append(min(matched_any / min_any, 1.0))

    if not components:
        return 0.0

    return sum(components) / len(components)


def hit_rate(text: str, items: list[Any]) -> float:
    if not items:
        return 1.0
    return sum(score_rule(text, item) for item in items) / len(items)


def apply_answer_penalties(answer_score: float, answer: str, case: dict[str, Any]) -> float:
    capped_score = answer_score

    incomplete_markers = case.get("answer_incomplete_markers", [])
    if incomplete_markers and any(contains_keyword(answer, marker) for marker in incomplete_markers):
        penalty_factor = float(case.get("incomplete_penalty_factor", 0.5))
        capped_score *= penalty_factor

    return max(0.0, min(capped_score, 1.0))


def score_answers(cases_path: Path, answers_path: Path) -> dict[str, Any]:
    cases = {case["id"]: case for case in load_jsonl(cases_path)}
    answers = load_jsonl(answers_path)

    details: list[dict[str, Any]] = []
    for row in answers:
        case = cases[row["case_id"]]
        answer = row.get("answer", "")
        context = row.get("retrieved_context", "")

        answer_rules = case.get("required_answer_point_rules", case.get("required_answer_points", []))
        answer_score = hit_rate(answer, answer_rules)
        answer_score = apply_answer_penalties(answer_score, answer, case)
        knowledge_score = hit_rate(context, case.get("expected_keywords", [])) if context else None

        details.append(
            {
                "scheme": row.get("scheme", ""),
                "case_id": row["case_id"],
                "category": case.get("category", ""),
                "answer_score": round(answer_score, 4),
                "knowledge_score": None if knowledge_score is None else round(knowledge_score, 4),
            }
        )

    scheme = answers[0].get("scheme", answers_path.stem) if answers else answers_path.stem
    answer_accuracy = sum(item["answer_score"] for item in details) / len(details) if details else 0
    knowledge_items = [item["knowledge_score"] for item in details if item["knowledge_score"] is not None]
    knowledge_hit_rate = sum(knowledge_items) / len(knowledge_items) if knowledge_items else None

    return {
        "scheme": scheme,
        "summary": {
            "case_count": len(details),
            "answer_accuracy": round(answer_accuracy, 4),
            "knowledge_hit_rate": None if knowledge_hit_rate is None else round(knowledge_hit_rate, 4),
        },
        "details": details,
    }


def print_summary_table(report_paths: list[Path]) -> None:
    print("| 方案 | 回答准确率 | 知识命中率 |")
    print("| --- | ---: | ---: |")
    for path in report_paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        summary = report["summary"]
        knowledge = summary["knowledge_hit_rate"]
        knowledge_text = "-" if knowledge is None else f"{knowledge * 100:.0f}%"
        print(
            f"| {report['scheme']} | "
            f"{summary['answer_accuracy'] * 100:.0f}% | "
            f"{knowledge_text} |"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Score benchmark outputs.")
    parser.add_argument("--cases", default="eval/benchmark_cases.jsonl")
    parser.add_argument("--answers")
    parser.add_argument("--output")
    parser.add_argument("--summary", nargs="*")
    args = parser.parse_args()

    if args.summary:
        print_summary_table([Path(path) for path in args.summary])
        return 0

    if not args.answers or not args.output:
        parser.error("--answers and --output are required unless --summary is used")

    report = score_answers(Path(args.cases), Path(args.answers))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Report written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
