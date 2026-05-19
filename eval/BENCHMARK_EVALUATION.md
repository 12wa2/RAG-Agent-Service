# 四方案对比评测方案

你截图里的表格是更适合论文、答辩、项目汇报的最终评测口径。建议按下面 4 个方案、2 个核心指标进行测试。

## 评测方案

| 方案 | 含义 | 评测目的 |
| --- | --- | --- |
| Prompt-only | 只把用户问题发给模型，不接知识库、不用工具 | 作为基础模型能力基线 |
| RAG | 使用知识库检索，把 Top-K 知识片段拼进提示词 | 验证知识库是否提升准确率 |
| RAG + Reranker | 在 RAG 基础上增加重排模型 | 验证 rerank 是否提升知识命中和答案准确率 |
| LoRA + RAG | 使用微调后的 Agent 模型 + RAG + 工具 | 验证微调模型在领域任务中的回答效果 |

## 评测指标

| 指标 | 定义 | 计算方式 |
| --- | --- | --- |
| 回答准确率 | 答案是否覆盖标准答案要点 | 命中标准答案要点数 / 标准答案要点总数 |
| 知识命中率 | 检索上下文是否命中答案所需知识 | 检索上下文命中关键词数 / 关键词总数 |

## 推荐测试集结构

测试集文件：

```text
eval/benchmark_cases.jsonl
```

每条用例包含：

```json
{
  "id": "fault_e104_001",
  "query": "PM01 出现 E-104 报错怎么办？",
  "category": "fault",
  "requires_tool": false,
  "expected_keywords": ["PM01", "E-104"],
  "required_answer_points": ["说明 E-104 的含义或可能原因", "给出排查步骤", "建议无法恢复时联系售后"],
  "required_answer_point_rules": [
    {"all_of": ["E-104"], "any_of": ["含义", "原因", "表示"]},
    {"any_of": ["检查", "排查", "清理", "重启"], "min_any": 2},
    {"any_of": ["联系售后", "联系客服", "授权维修"]}
  ],
  "forbidden_claims": ["更换主板即可解决", "E-104 一定是电池损坏"]
}
```

说明：

- `required_answer_points` 用于人工阅读和标注
- `required_answer_point_rules` 用于脚本打分，支持 `all_of`、`any_of`、`none_of`、`min_any`
- 如果是需要工具或实时信息的题目，还可以增加：
  - `max_answer_score_without_tool`
  - `answer_incomplete_markers`
  - `incomplete_penalty_factor`

## 执行步骤

### Step 1: 准备四组输出

你需要分别运行 4 个方案，并把每条用例的回答保存成 JSONL。

项目现在提供了一个可直接执行的脚本：

```powershell
python eval\run_benchmark.py --scheme prompt_only
python eval\run_benchmark.py --scheme rag
python eval\run_benchmark.py --scheme rag_reranker
python eval\run_benchmark.py --scheme lora_rag
```

这个脚本默认会：

- 按方案写入对应的 `eval/outputs/*.jsonl`
- 已有结果时自动跳过已经完成的 `case_id`
- 支持你一次只跑一个方案，或者中断后继续跑

如果你想逐条测评某个用例，可以使用：

```powershell
python eval\run_benchmark.py --scheme rag --case-id fault_e104_001
python eval\run_benchmark.py --scheme lora_rag --case-id weather_tool_007
```

如果你想从头重跑某个方案，可以加：

```powershell
python eval\run_benchmark.py --scheme rag --overwrite
```

建议输出文件：

```text
eval/outputs/prompt_only_answers.jsonl
eval/outputs/rag_answers.jsonl
eval/outputs/rag_reranker_answers.jsonl
eval/outputs/lora_rag_answers.jsonl
```

每行格式：

```json
{
  "scheme": "rag_reranker",
  "case_id": "fault_e104_001",
  "answer": "模型最终回答文本",
  "retrieved_context": "检索到的知识片段，可为空",
  "tool_expected": false,
  "tool_success": false
}
```

### Step 2: 对每组输出打分

```powershell
python eval\score_benchmark.py --cases eval\benchmark_cases.jsonl --answers eval\outputs\prompt_only_answers.jsonl --output eval\reports\prompt_only_score.json
python eval\score_benchmark.py --cases eval\benchmark_cases.jsonl --answers eval\outputs\rag_answers.jsonl --output eval\reports\rag_score.json
python eval\score_benchmark.py --cases eval\benchmark_cases.jsonl --answers eval\outputs\rag_reranker_answers.jsonl --output eval\reports\rag_reranker_score.json
python eval\score_benchmark.py --cases eval\benchmark_cases.jsonl --answers eval\outputs\lora_rag_answers.jsonl --output eval\reports\lora_rag_score.json
```

### Step 3: 汇总成你截图里的表

```powershell
python eval\score_benchmark.py --summary eval\reports\prompt_only_score.json eval\reports\rag_score.json eval\reports\rag_reranker_score.json eval\reports\lora_rag_score.json
```

输出表格字段就是：

```text
方案 | 回答准确率 | 知识命中率
```

## 每个方案怎么跑

### Prompt-only

只把 `query` 发给模型，不拼接知识库上下文，不调用工具。

适合测试：

- 模型本身是否知道业务知识

### RAG

使用向量检索或 BM25 + 向量混合检索，把 Top-K 文档拼进 prompt。

适合测试：

- 知识库是否覆盖问题
- 检索内容是否能支撑回答

### RAG + Reranker

先召回 Top-K，再用 reranker 选 Top-N。

适合测试：

- 重排是否提升相关知识排序
- 是否减少无关上下文导致的错误回答

### LoRA + RAG

使用微调后的 Agent 模型，结合 RAG 和工具。

适合测试：

- 业务表达是否更稳定
- 多轮问答和任务执行是否更顺

## 你截图里的示例结果口径

最终可以整理成：

| 方案 | 回答准确率 | 知识命中率 |
| --- | ---: | ---: |
| Prompt-only | 62% | - |
| RAG | 78% | 81% |
| RAG + Reranker | 84% | 89% |
| LoRA + RAG | 88% | 89% |

注意：上表里的数字应该来自真实跑分，不建议直接写死。当前仓库提供的是测试集、结果模板和打分脚本。
