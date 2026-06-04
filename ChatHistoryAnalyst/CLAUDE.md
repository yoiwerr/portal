# ChatLab (ChatHistoryAnalyst)

> Portal 子项目。外层运维见 [../CLAUDE.md](../CLAUDE.md)。

AI 聊天记录分析引擎，三个核心 Agent：
1. **语气模仿** — 模仿对方说话风格，预测下一条回复
2. **情感分析** — 评分 (0-100)、主导情感、推理
3. **气氛分析** — 权力动态、沟通姿态、改进建议

全部基于 LangChain Agent + PGVector RAG（心理学知识库 + 聊天历史库）。

## 本地开发

```bash
cd ~/portal
make dev                           # 一键: FastAPI (:8000) + Streamlit (:8501)
# 或手动:
cd ~/portal/ChatHistoryAnalyst
uv run uvicorn src.main:app --reload        # 终端 1
uv run streamlit run front/frontend.py       # 终端 2
```

打开 `http://localhost:8000`。

## 首次准备

```bash
uv sync                              # 装依赖
cp .env.example .env && vim .env     # 填 API 密钥
uv run python import_knowledge.py    # 导入知识库（需 PostgreSQL + pgvector）
```

## 技术栈

| Layer | Tech |
|-------|------|
| Language | Python 3.12, managed with `uv` |
| Backend | FastAPI + Uvicorn |
| Frontend | Streamlit (pink/ivory theme) |
| LLM | Qwen via DashScope (`qwen3-max` analysis, `qwen3-omni-flash` OCR) |
| Agent FW | LangChain `create_agent` |
| Vector DB | PostgreSQL + pgvector |
| Embeddings | DashScope `text-embedding-v3` |
| Web Search | Tavily |
| Observability | LangSmith |

## 架构

```
Browser (Streamlit :8501)
        │
        ▼
FastAPI (:8000) ── src/main.py
        │
        ├── /          → portal/static/index.html  (首页)
        ├── /chatlab   → 302 → localhost:8501      (线上 nginx 拦截)
        ├── /css/*     → portal/static/css/
        └── /api/v1/*  → 8 个业务端点
        │
        ├── src/schemas.py             Pydantic models
        ├── src/core_llm.py            LLM 实例
        │
        ▼
    Skill Agents (src/skills/)
        ├── skill01_imitate.py         → {"reply": "..."}
        ├── skill02_emotion.py         → EmotionResponse (JSON)
        └── skill03_atmosphere.py      → AtmosphereResponse (JSON)
        │
        ▼
    Tools (src/tools.py)
        ├── search_psychology_knowledge()  → knowledge_store
        ├── search_chat_history()          → chat_history_store
        └── web_search()                   → Tavily
        │
        ▼
    PGVector (src/rag_function.py)
        ├── knowledge_store   collection="psychology_knowledge"
        └── chat_history_store collection="chat_history"
```

## File Map

| File | Role |
|------|------|
| `src/main.py` | FastAPI app — 8 endpoints + 首页挂载 + /chatlab 重定向 |
| `src/core_llm.py` | `base_llm` (qwen3-max) + `vision_llm` (qwen3-omni-flash) |
| `src/schemas.py` | Pydantic: ChatMessage, AnalysisRequest, EmotionResponse, AtmosphereResponse |
| `src/tools.py` | 3 个 LangChain `@tool` + RELEVANCE_THRESHOLD |
| `src/rag_function.py` | PGVector 双库管理、去重、分块、维度检查 |
| `src/skills/skill01_imitate.py` | 语气模仿 Agent |
| `src/skills/skill02_emotion.py` | 情感分析 Agent，LLM 输出用 regex 提取 JSON |
| `src/skills/skill03_atmosphere.py` | 气氛分析 Agent |
| `front/frontend.py` | Streamlit UI: 文件上传、OCR、分析卡片、情感仪表盘 |
| `import_knowledge.py` | 一次性脚本: data/*.txt → knowledge_store |
| `data/*.txt` | 心理学参考: 依恋、沟通、性格、关系 |
| `docs/rag-roadmap.md` | RAG 演进路线 (HyDE, rerank, GraphRAG, …) |
| `pyproject.toml` | Python 依赖 |
| `docker-compose.yml` | postgres + api + streamlit |
| `Dockerfile` | Python 3.12 镜像 |
| `.env.example` | 密钥模板 (DB_HOST=localhost 本地, =postgres Docker) |

## 关键约定

- **Agent pattern**: `create_agent(model, tools, system_prompt=...)`
- **JSON extraction**: `re.search(r'\{.*\}', raw, re.DOTALL)` 安全提取
- **PGVector**: 两个独立 collection，启动时 `check_dimension_mismatch()`
- **Dedup**: 按 (content, sender, timestamp) 去重
- **Chunking**: 500 字符 + 50 重叠
- **Relevance threshold**: 0.3

## 本次 Session (2026-06-04)

1. 删除冗余文件：`nginx/` `static/` `scripts/` `TODO.md` `course/` `portfolio/`（提升至 portal/）
2. 删除 ChatHistoryAnalyst/.git，统一为 portal/ 大仓 → GitHub [yoiwerr/portal](https://github.com/yoiwerr/portal)
3. `src/main.py` 新增 `/` 首页 + `/css` 静态挂载 + `/chatlab` → localhost:8501 重定向
4. `make dev` 本地一键启动
5. `.env.example` DB_HOST 默认 localhost
