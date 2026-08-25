# Alfred — AI 工作流增强 Agent

> 守在用户与智能体之间的 AI 协作管家。帮助你想清楚目标、适配合适能力、规范工作过程、记住项目结果。

[![Python](https://img.shields.io/badge/python-3.12+-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-orange)](https://langchain-ai.github.io/langgraph/)
[![License](https://img.shields.io/badge/license-MIT-brightgreen)](./LICENSE)

---

## 快速开始

### 前置依赖

- **Python 3.12+**
- **PostgreSQL 16** + [pgvector](https://github.com/pgvector/pgvector) 扩展
- **LLM API Key**（至少一个：DashScope / DeepSeek / OpenAI）

### 1. 克隆 & 安装

```bash
git clone https://github.com/yoiwerr/Alfred.git
cd Alfred

# pip
pip install -r requirements.txt

# 或 uv（推荐）
uv sync
```

### 2. 配置环境变量

```bash
cp .env.example .env
vim .env
```

**必填项：**

```bash
# LLM Provider — 至少填一个
LLM_PROVIDER=auto              # dashscope | deepseek | openai | auto
DASHSCOPE_API_KEY=sk-xxx       # 百炼 API Key（Embedding + Rerank 必须）
DEEPSEEK_API_KEY=sk-xxx        # DeepSeek API Key

# PostgreSQL
PGSQLPASSWORD=your-pg-password
```

> 完整环境变量见 [.env.example](./.env.example)

### 3. 启动 PostgreSQL

```bash
docker run -d --name alfred-pg \
  -e POSTGRES_PASSWORD=yourpassword \
  -e POSTGRES_DB=alfred \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

如果使用已有 PostgreSQL 实例，确保启用 pgvector 扩展：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 4. 启动

```bash
python app.py
```

启动成功：

```
============================================================
  Alfred — Provider: deepseek | Model: deepseek-chat
============================================================
  KB: 8 files, 156 chunks
  [OK] ready
```

### 5. 访问

| 地址 | 说明 |
|------|------|
| http://localhost:8001 | 前端界面（三栏工作台） |
| http://localhost:8001/docs | Swagger API 文档 |
| http://localhost:8001/api/health | 健康检查 |

---

## Docker 部署

```bash
# 1. 配置
cp .env.example .env && vim .env

# 2. 启动（含 PostgreSQL + Alfred）
docker compose up -d

# 3. 首次运行后索引知识库
docker exec alfred-api python -c "
from services.rag_service import RAGService
# 或等待自动索引
"
```

---

## 对话流程

在浏览器打开 http://localhost:8001，输入需求。Alfred 会：

1. **Router** → 意图识别 + 模块自动路由
2. **Enrich** → Query 增强（上下文驱动，提升检索命中率）
3. **RAG** → 混合检索（Dense + BM25 → RRF → Rerank）
4. **Planner** → 提取维度 + 判断信息完整度
5. **Clarify** → 信息不足时动态追问（任务契约引导）
6. **Engineering Check** → 工程规范检测（建议/确认/阻断三级）
7. **Execute** → ReAct Agent tool calling loop
8. **Checkpoint** → Planner 语义中枢介入，检查对齐
9. **Reflect** → 质量评分 + 不达标自动重试（最多 2 次）

---

## 四项核心能力

| 能力 | 一句话 |
|------|--------|
| 💡 **想清楚** | 目标不清晰时追问关键信息，形成任务契约 |
| 🤝 **选对人** | 根据任务特点推荐合适的模型、工具或 Agent |
| 🛡️ **看住过程** | 控制范围、规范节奏，高风险操作先确认 |
| 🧠 **记住结果** | 任务收尾生成交接卡，下次直接恢复上下文 |

---

## 架构

```
Browser (SSE Token Streaming)
    │  POST /api/chat/stream?v=2
    ▼
FastAPI → LangGraph ReAct Agentic Loop
    │
    ├── Router           意图识别 + 模块自动路由
    ├── Enrich           Query 增强（上下文驱动）
    ├── RAG              混合检索（Dense + BM25 → RRF → Rerank）
    ├── Planner          LLM JSON mode 提取维度 + 判断完整度
    ├── Clarify          动态生成追问（任务契约引导）
    ├── Engineering      工程规范检测（建议/确认/阻断三级）
    ├── Multi-Agent      三立场 Agent Panel（实用/稳健/创新并行）
    ├── Execute          ReAct tool calling loop
    ├── Checkpoint       Planner 语义中枢，检查语义对齐
    └── Reflect          LLM 质量检查，不达标自动重试（最多 2 次）

存储层: PostgreSQL + PGVector（向量 + 会话 + 记忆 + 反馈 + 契约）
```

### 三层上下文

| 层 | 内容 | 生命周期 |
|----|------|----------|
| L1 滑动窗口 | 最近 3 轮完整对话 | 当前会话 |
| L2 滚动摘要 | 全部历史的压缩总结 | 当前会话 |
| L3 语义事实 | LLM 提取的结构化事实（PGVector 持久化） | 跨会话 |

### 多 Agent Panel

当需求不明确但用户拒绝追问时，自动触发三立场并行分析：

| 立场 | 关注点 |
|------|--------|
| 💼 实用派 | 最快能用的方案 |
| 🛡️ 稳健派 | 最稳妥可维护的方案 |
| 💡 创新派 | 最优雅前瞻的方案 |

---

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 首页 |
| `GET` | `/api/health` | 健康检查（PG + Agent 状态） |
| `POST` | `/api/chat/stream?v=2` | SSE 流式对话 |
| `GET` | `/api/sessions` | 会话列表 |
| `GET` | `/api/sessions/{id}` | 会话详情 |
| `DELETE` | `/api/sessions/{id}` | 删除会话 |
| `GET` | `/api/sessions/{id}/export` | 导出 Markdown |
| `POST` | `/api/sessions/{id}/handover` | 生成交接卡 |
| `POST` | `/api/feedback` | 提交反馈（👍👎） |
| `GET` | `/api/feedback/stats` | 反馈统计 |
| `POST` | `/api/knowledge/upload` | 上传知识文件 |
| `POST` | `/api/files/upload` | 上传附件 |

---

## 项目结构

```
Alfred/
├── app.py                  ← FastAPI 入口
├── config.py               ← 全局配置（多 Provider）
├── pyproject.toml          ← 项目元数据 + 依赖
├── requirements.txt        ← pip 依赖
├── .env.example            ← 环境变量模板
├── Dockerfile
├── docker-compose.yml
│
├── core/                   ← Agent 引擎
│   ├── agent.py            ← Agent 编排器（astream 流式）
│   ├── graph.py            ← LangGraph ReAct Agentic Loop
│   ├── llm_client.py       ← 多 Provider LLM 工厂
│   ├── context_engine.py   ← 三层上下文（L1/L2/L3）
│   └── router.py           ← 意图路由（规则 + LLM）
│
├── routers/                ← FastAPI 路由
│   ├── chat.py             ← SSE 流式对话
│   ├── sessions.py         ← 会话管理 + 导出
│   ├── knowledge.py        ← 知识库管理
│   ├── feedback.py         ← 用户反馈
│   ├── files.py            ← 文件上传
│   └── handover.py         ← 交接卡
│
├── services/               ← 数据服务
│   ├── rag_service.py      ← RAG（来源感知 + 混合检索 + 知识图谱）
│   ├── vector_store.py     ← PGVector 向量存储
│   ├── session_store.py    ← PostgreSQL 会话持久化
│   ├── contract_store.py   ← 任务契约持久化
│   ├── document_processor.py ← 文档解析 + 语义分块
│   ├── engineering_advisor.py ← 工程规范顾问
│   ├── multi_agent.py      ← 三立场 Agent Panel
│   ├── handover_service.py ← 交接卡服务
│   └── md_export.py        ← Markdown 导入导出
│
├── tools/search.py         ← Agent 工具（search_kb / search_web / search_history）
├── skills/                 ← 技能（提示词工程 / 工作安排 / 信息留存 / 代码审查）
├── prompts/                ← System Prompts（Planner / Executor / Reflector）
├── models/                 ← Pydantic 数据模型
├── memory/                 ← L2/L3 记忆系统
│
├── static/                 ← 前端（Vanilla JS + CSS，零框架依赖）
├── knowledge_base/         ← RAG 知识源（.md 文件）
├── tests/                  ← 测试
└── data/                   ← 运行时数据（日志 + 导出，自动创建）
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| 框架 | FastAPI + LangGraph + LangChain |
| LLM | DashScope (Qwen) / DeepSeek / OpenAI / Local |
| 嵌入 | DashScope text-embedding-v4（1024 维） |
| 向量存储 | PostgreSQL + PGVector |
| 检索 | Dense + BM25 Sparse → RRF → Rerank (qwen3-rerank) → 关键词加权 |
| 分块 | SemanticChunker（embedding 相似度断崖切分） |
| 流式 | SSE（sse-starlette），节点级进度 + token 级渲染 |
| 前端 | Vanilla JS + CSS（零框架依赖，三栏工作台） |

---

## 开发

### 运行测试

```bash
python -m pytest tests/ -v
```

### 添加知识库文件

在 `knowledge_base/` 下放置 `.md` 文件，支持 YAML frontmatter：

```markdown
---
source_title: 参考文档
source_url: https://example.com/doc
source_type: documentation
---
正文内容...
```

重启后自动索引。

### 添加 Skill

1. `skills/` 下创建类，继承 `skills/base.py` 的 `BaseSkill`
2. `core/agent.py` 的 `__init__` 中注册
3. `prompts/system_prompts.py` 添加对应 System Prompt

---

## License

MIT
