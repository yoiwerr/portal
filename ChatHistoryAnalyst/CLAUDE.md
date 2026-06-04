# ChatHistoryAnalyst (ChatLab)

> **Deployment**: This project is a sub-project of [Portal](../). See `../docker-compose.yml` for the top-level orchestration that includes nginx, homepage, and all sub-projects on a shared Docker network.

AI-powered chat history analysis engine. Three core skills:
1. **Tone Imitation** — mimic a person's speaking style and predict their next reply
2. **Emotion Analysis** — score (0-100), dominant emotion label, reasoning
3. **Atmosphere Analysis** — power dynamics, communication posture, suggestions

All skills use LangChain agents backed by a RAG system (PGVector with two stores: psychology knowledge + chat history).

## Tech Stack

| Layer | Tech |
|-------|------|
| Language | Python 3.12, managed with `uv` |
| Backend | FastAPI + Uvicorn |
| Frontend | Streamlit (pink/ivory theme) |
| LLM | Qwen via DashScope (`qwen3-max` for analysis, `qwen3-omni-flash` for OCR) |
| Agent FW | LangChain (`create_agent`) |
| Vector DB | PostgreSQL + pgvector (two collections) |
| Embeddings | DashScope `text-embedding-v3` |
| Web Search | Tavily Search |
| Observability | LangSmith |

## Quick Start

```bash
# Prerequisites: PostgreSQL with pgvector extension, Python 3.12, uv

# Install deps
uv sync

# Import psychology reference data (one-time)
python import_knowledge.py

# Terminal 1: Backend API (port 8000)
uvicorn src.main:app --reload

# Terminal 2: Frontend (port 8501)
streamlit run front/frontend.py
```

## Architecture

```
Browser (Streamlit :8501)
        │
        ▼
FastAPI (:8000) ── src/main.py
        │
        ├── src/schemas.py         Pydantic request/response models
        ├── src/core_llm.py        LLM instances (base_llm, vision_llm)
        │
        ▼
    Skill Agents (src/skills/)
        │
        ├── skill01_imitate.py     Agent: search history + psych → mimic reply
        ├── skill02_emotion.py     Agent: search history + psych → JSON emotion report
        └── skill03_atmosphere.py  Agent: search history + psych → JSON atmosphere report
        │
        ▼
    Tools (src/tools.py)
        ├── search_psychology_knowledge(query)       → knowledge_store (permanent)
        ├── search_chat_history(query, target_person) → chat_history_store (persistent)
        └── web_search(query)                        → Tavily
        │
        ▼
    PGVector (src/rag_function.py)
        ├── knowledge_store   collection="psychology_knowledge"  (from data/*.txt)
        └── chat_history_store collection="chat_history"         (from imported chats)
```

## File Map

| File | Role |
|------|------|
| `src/main.py` | FastAPI app — 8 endpoints for import, analysis, memory, knowledge mgmt |
| `src/core_llm.py` | Creates `base_llm` (qwen3-max) and `vision_llm` (qwen3-omni-flash) |
| `src/schemas.py` | Pydantic models: ChatMessage, AnalysisRequest, EmotionResponse, AtmosphereResponse |
| `src/tools.py` | Three LangChain `@tool`s available to all agents + RELEVANCE_THRESHOLD |
| `src/rag_function.py` | PGVector store management, dedup, chunking, dimension checking, import |
| `src/skills/skill01_imitate.py` | Agent: imitates tone, returns `{"reply": "..."}` |
| `src/skills/skill02_emotion.py` | Agent: structured JSON output, regex-extracted from LLM response |
| `src/skills/skill03_atmosphere.py` | Agent: same pattern, atmosphere/power-dynamics JSON |
| `front/frontend.py` | Streamlit UI: file upload, chat preview, analysis cards, emotion gauge |
| `import_knowledge.py` | One-shot script to chunk and import `data/*.txt` into knowledge_store |
| `data/*.txt` | Chinese psychology reference: attachment, communication, personality, relationships |
| `docs/rag-roadmap.md` | RAG evolution plan (HyDE, rerank, GraphRAG, etc.) |
| `pyproject.toml` | Dependencies and project metadata |
| `.env` | API keys + DB creds (gitignored, see `.env.example` for template) |
| `Dockerfile` | Single Python 3.12 image for both API and Streamlit |
| `docker-compose.yml` | Orchestrates nginx + api + streamlit + postgres (pgvector) |
| `nginx/nginx.conf` | Reverse proxy: `/` → Streamlit, `/api` → FastAPI |
| `scripts/deploy.sh` | One-click server deployment script |
| `TODO.md` | Server setup steps for the user to complete |

## Key Conventions

- **Agent pattern**: `create_agent(model, tools, system_prompt=...)` — all three skills follow this
- **JSON extraction**: LLM responses use `re.search(r'\{.*\}', raw, re.DOTALL)` to safely extract JSON
- **PGVector stores**: Two separate collections, dimension checked at startup (`check_dimension_mismatch()`)
- **Dedup**: Chat messages deduplicated by (content, sender, timestamp) before insert
- **Chunking**: Knowledge files chunked at 500 chars with 50-char overlap
- **Relevance threshold**: 0.3 for all tool searches

## Progress

**Phase**: [阶段一: 需求对齐] ✅ → [阶段二: 架构设计] ✅ → [阶段三: 精确执行] ← we are here → [阶段四: 脱水沉淀]

**Done (核心功能):**
- 三个 Skill Agent：语气模仿、情感分析、气氛分析，均接入 RAG 工具
- FastAPI 后端：8 个 API 端点（导入、分析、记忆管理、知识库管理）
- Streamlit 前端：文件上传、截图 OCR、聊天预览、分析结果可视化
- PGVector 双库 RAG：心理学知识库（`data/*.txt`）+ 聊天历史库
- 知识导入流水线 (`import_knowledge.py`)

**Done (部署修复，本次 session):**
- Dockerfile（Python 3.12 镜像）+ 国内源镜像加速（apt/pip 阿里云镜像）
- docker-compose.yml（nginx + api + streamlit + postgres/pgvector）
- nginx 反向代理（`/` → Streamlit，`/api` → FastAPI，运行时 DNS 解析）
- 一键部署脚本 `scripts/deploy.sh`
- `src/rag_function.py` 支持 `DB_HOST`/`DB_PORT` 环境变量
- `front/frontend.py` BASE_URL 支持 `API_BASE_URL` 环境变量
- `.env.example` / `TODO.md` 重写为公网 IP 部署（去掉域名和 HTTPS）
- 服务器已部署成功

**下一步:**
- 浏览器访问 `http://<公网IP>` 验证
- 前端优化 → 功能扩展 → 阶段四沉淀

---

## Session Update

### 2026-05-22
- **What I did**: Dockerized the project for deployment. Created Docker Compose stack (nginx + Streamlit + FastAPI + PostgreSQL/pgvector), deploy script.

### 2026-05-23
- **What I did**: Removed portfolio homepage — Streamlit is now the main page at `/`. Bought domain, updated TODO.md with DNS setup instructions. Fixed `BASE_URL` in frontend.py to support Docker cross-container communication via `API_BASE_URL` env var.
- **What changed** (files): Modified nginx/nginx.conf, docker-compose.yml, front/frontend.py, scripts/deploy.sh, TODO.md, CLAUDE.md. Deleted portfolio/index.html.

### 2026-05-26
- **What I did**: 国内服务器部署成功。重写 TODO.md 为公网 IP 部署（去掉域名/HTTPS）。Dockerfile 添加 apt/pip 阿里云镜像源。修复 nginx 运行时 DNS 解析（`host not found in upstream`）和 proxy_pass 变量模式 URI 被覆盖问题。服务器 80 端口被宿主机 nginx 占用，停掉后切换为 Docker nginx。
- **What changed** (files): Modified TODO.md, Dockerfile, nginx/nginx.conf, CLAUDE.md.
- **What's next**: 浏览器 `http://<公网IP>` 验证。后续安装 sing-box 代理和 Claude Code。
- **Blockers / notes**: 服务器已有宿主机 nginx，已 `systemctl stop/disable`。Docker 镜像加速已配。API 返回正常（`/api/v1/imported_files` 返回 200）。
