# RAG + Agent 智能问答 Demo

这是一个面向扫地机器人知识库的 RAG + Agent 项目，包含 FastAPI 后端、Streamlit 前端、Chroma 向量库、BM25 + 向量混合检索、重排和流式回答。

本轮优先补强三件事：评测体系、Demo 部署、README。

## 功能概览

- FastAPI 提供会话管理和 SSE 流式问答接口。
- Streamlit 提供可交互 Demo 页面，支持知识文件上传和多轮会话。
- RAG 检索链路使用 Chroma 向量检索、BM25 混合检索和 rerank。
- Agent 支持工具调用、记忆摘要和上下文注入。
- `eval/` 提供可复用评测数据集与命令行评测脚本。

## 项目结构

```text
agent/                 ReAct Agent、记忆和工具
config/                RAG、Chroma、Agent 配置
data/                  示例知识库文件
eval/                  评测数据、评测脚本和报告输出目录
model/                 LLM、Embedding、Rerank 模型工厂
rag/                   向量库和 RAG 服务
utils/                 配置、文件、日志和路径工具
app.py                 Streamlit Demo
main.py                FastAPI 服务
start_demo.py          同时启动后端和前端的 Demo 入口
Dockerfile             Docker 部署入口
render.yaml            Render Blueprint 示例
```

## 本地运行

1. 创建并激活虚拟环境。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. 配置环境变量。

```powershell
$env:DASHSCOPE_API_KEY="你的 DashScope API Key"
```

3. 启动后端。

```powershell
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

4. 另开一个终端启动前端。

```powershell
streamlit run app.py
```

浏览器访问 Streamlit 输出的地址，默认通常是 `http://localhost:8501`。

## Demo 部署

### Docker

```powershell
docker build -t rag-agent-demo .
docker run --rm -p 8501:8501 -e DASHSCOPE_API_KEY="你的 DashScope API Key" rag-agent-demo
```

容器会通过 `start_demo.py` 同时启动：

- FastAPI: `0.0.0.0:8000`
- Streamlit: `0.0.0.0:8501`

### Render

仓库包含 `render.yaml`，可作为 Render Blueprint 使用。部署前在 Render 控制台配置 `DASHSCOPE_API_KEY`，然后使用 Docker 环境启动 Demo。

当前 Streamlit 代码默认访问 `http://127.0.0.1:8000/api/v1`，因此前后端放在同一个容器内运行。

## 评测体系

评测数据位于 `eval/eval_dataset.jsonl`，每行包含：

- `id`: 用例编号
- `query`: 用户问题
- `expected_keywords`: 期望命中的关键词
- `category`: 用例类别

### 检索评测

检索评测会调用本地向量库，检查 Top-K 检索内容是否覆盖期望关键词。

```powershell
python eval/run_eval.py --mode retrieval
```

### 端到端 API 评测

先启动 FastAPI 后端，再运行：

```powershell
python eval/run_eval.py --mode api --api-base-url http://127.0.0.1:8000/api/v1
```

评测报告默认输出到：

```text
eval/reports/latest.json
```

报告包含用例数、通过率、平均关键词得分、平均延迟和每条用例的回答预览。

## API 快速验证

创建会话：

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/sessions
```

查看会话：

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/api/v1/sessions
```

流式问答接口：

```text
POST /api/v1/chat/stream
Content-Type: application/json

{
  "session_id": "上一步返回的 session_id",
  "query": "PM01 出现 E-104 报错怎么办？"
}
```

## 后续建议

- 将 `expected_keywords` 扩展为人工标注参考答案和引用片段，提升评测可信度。
- 增加 CI 中的轻量检索评测，保证知识库或检索策略变化后不会静默退化。
- 将 Streamlit 的后端地址改为环境变量，方便前后端拆分部署。
