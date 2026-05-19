# Benchmark Output Files

Put generated answers here when running the four-scheme benchmark:

- `prompt_only_answers.jsonl`
- `rag_answers.jsonl`
- `rag_reranker_answers.jsonl`
- `lora_rag_answers.jsonl`

Each line should use this shape:

```json
{
  "scheme": "rag_reranker",
  "case_id": "fault_e104_001",
  "answer": "model answer",
  "retrieved_context": "retrieved knowledge chunks",
  "tool_success": false
}
```
