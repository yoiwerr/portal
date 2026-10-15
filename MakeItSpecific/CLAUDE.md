# Alfred — 开发说明

Alfred 当前位于 Portal 的 `MakeItSpecific/`，定位为面向新手的 Vibe Coding 方案助手。

## 当前开发依据

- 产品范围与交付标准以 [PRODUCT.md](PRODUCT.md) 为准，开发安装见 [README.md](README.md)。
- 后续按 [板块划分](docs/product-modules.md) 的九块（00–08）一次改一块，[逐步优化路线](docs/product-roadmap.md) 用于对照产品目标。先限定函数与接口，只做必要联动，不一次性改写整个工程。
- 首版只支持新项目，最终提供一份可交给编程 Agent 的方案文案；Alfred 产品本身不写代码、不执行用户项目、不接手实际排错。
- 技术选择使用普通语言、场景和优缺点说明；信息不全时采用标注清楚的简单默认方案，不覆盖用户明确要求。
- 跨会话项目记忆与后续修改方案的交互待调研，不依据旧实现直接认定需求已确认。
- 当前仍存在旧的通用工作流、工具、技能和记忆实现，需逐步审查；下方架构与历史记录不是新能力承诺。
- 第一轮已对齐规划提示词、核心信息与默认来源处理、只返回文案的方案节点及交付检查；API/SSE 的旧节点名称保留兼容。界面、方案直接导出和真实模型效果验证尚待后续。产品输出边界不限制开发者正常维护本仓库的代码与命令。

## 历史实现参考：架构概览

下图保留旧架构说明，不用于指导新增节点。00 首轮已移除图内空工程检查及不可达多 Agent 分支。当前公开对话统一走 `work_arranger`；Planner 直接进入追问或文案生成，之后方向与质量检查可有限重试，生成节点不绑定工具。当前流程图见 [板块 00](docs/product-modules.md#00对话流程与节点编排)，实际链路以 `core/graph.py` 为准；离线回归见 `tests/test_planning*.py`。

```
Browser (SSE Token Streaming)
    │
    ▼ POST /api/chat/message
routers/chat.py  ← 节点级进度流式，通过 SSE 推送
    │
    ▼
core/agent.py  (Agent 编排器)
    │
    ├─ process_message()        ← 兼容旧版，等图跑完一次性返回
    └─ process_message_stream() ← V2，astream 节点级流式
         │
         ▼
core/graph.py  (LangGraph V4 Agentic Loop)
    │
    ├─ router  → 意图识别 + 模块自动路由
    ├─ enrich  → Query 增强（上下文驱动）
    ├─ rag     → 混合检索（Dense + BM25 Sparse → RRF → Rerank）
    ├─ planner → LLM JSON mode 提取维度 + 判断完整度
    ├─ clarify → 动态生成追问（任务契约引导）
    ├─ engineering_check → 工程规范检测（建议/确认/阻断三级）
    ├─ multi_agent → 三立场 Agent Panel（实用/稳健/创新并行）
    ├─ execute → ReAct Agent tool calling loop
    ├─ checkpoint → Planner 语义中枢，检查语义对齐
    └─ reflect → LLM 质量检查，不达标自动重试 (最多2次)
         │
         ▼
    ┌─────────────┐  ┌────────────────┐  ┌──────────────┐
    │ tools/       │  │ services/      │  │ skills/      │
    │ search_kb    │  │ rag_service    │  │ base.py      │
    │              │  │ session_store  │  │ *.py 实现    │
    └─────────────┘  │ vector_store   │  └──────────────┘
                     │ contract_store │
                     │ md_export      │
                     │ multi_agent    │
                     │ document_proc  │
                     │ eng_advisor    │
                     │ handover_svc   │
                     └────────────────┘
```

## 本地开发

按 [README 的本地开发说明](README.md#当前工程与本地开发) 使用 `uv sync --frozen`，核对当前环境变量和数据库连接后运行。保留已有 `.env`，Python 与 AlfredAdmin 使用同一 `JWT_SECRET`。当前 Python 配置优先读取 Portal 根级 `.env`。

## 运行测试

```bash
cd /home/yoiwerr/portal/MakeItSpecific
uv run --frozen python -m pytest tests/ -v
```

## Docker 部署

使用 Portal 根级 Compose。`MakeItSpecific/docker-compose.yml` 定义 `specific-api`（容器 `alfred-api`，内部端口 8000），依赖根级 PostgreSQL；AlfredAdmin 也是根级编排的一部分。子项目 Compose 不自包含 PostgreSQL。运维参考 [Portal 运维说明](../CONTROLWEB.md)，变更时以当前配置为准。

## 加新 Skill

1. 创建 `skills/my_skill.py`，继承 `skills/base.py` 的 `BaseSkill`:
```python
from skills.base import BaseSkill, SkillContext

class MySkill(BaseSkill):
    name = "my_skill"
    label = "我的技能"
    icon = "🔧"
    description = "一句话描述"

    async def execute(self, context: SkillContext, model) -> str:
        # 实现技能逻辑
        return "输出内容"
```

2. 在 `prompts/system_prompts.py` 中添加对应的 System Prompt
3. 在 `core/agent.py` 的 `__init__` 中注册

## 项目依赖

- **框架**: FastAPI + LangGraph + LangChain
- **LLM**: 多 Provider (DashScope / DeepSeek / OpenAI / Local)
- **向量存储**: PostgreSQL + PGVector + DashScope text-embedding-v4
- **Rerank**: 百炼 qwen3-rerank
- **会话**: PostgreSQL (与向量存储共用实例)
- **流式**: SSE (sse-starlette)

## 目录结构

```
MakeItSpecific/
├── app.py              ← FastAPI 入口
├── config.py           ← 全局配置 (dataclass, 多 provider)
├── Dockerfile
├── docker-compose.yml  ← Python 服务定义，依赖 Portal 根级 PostgreSQL
├── .env.example        ← 环境变量模板
│
├── core/
│   ├── agent.py        ← Agent 编排器 (async, astream_events)
│   ├── graph.py        ← LangGraph V4 ReAct Agentic Loop
│   ├── llm_client.py   ← 多 Provider LLM 工厂
│   ├── context_engine.py ← 三层上下文架构 (L1/L2/L3)
│   └── router.py       ← 意图路由 (规则 + LLM 两阶段)
│
├── routers/            ← FastAPI 路由
│   ├── chat.py         ← 核心对话 (SSE 流式 + 契约确认)
│   ├── sessions.py     ← 会话管理 + Markdown 导出
│   ├── knowledge.py    ← 知识库管理
│   ├── feedback.py     ← 用户反馈 (👍👎)
│   ├── files.py        ← 文件上传
│   └── handover.py     ← 交接卡生成
│
├── tools/
│   └── search.py       ← @tool: search_knowledge_base
│
├── skills/
│   ├── base.py         ← 抽象基类 BaseSkill + SkillContext
│   ├── prompt_refiner.py
│   ├── work_arranger.py
│   ├── info_retention.py
│   └── code_review.py
│
├── prompts/
│   ├── system_prompts.py  ← Planner/Executor/Reflector + Skill Prompts
│   └── templates.py       ← 维度定义 + 追问模板 + 契约格式化工具
│
├── services/
│   ├── rag_service.py     ← RAG V5 (来源感知 + 混合检索 + 知识图谱)
│   ├── session_store.py   ← PostgreSQL 会话持久化
│   ├── vector_store.py    ← PGVector 向量存储
│   ├── contract_store.py  ← 任务契约持久化
│   ├── document_processor.py ← 文档解析 + SemanticChunker + SourceSplitter
│   ├── engineering_advisor.py ← 工程规范顾问 (三级输出)
│   ├── multi_agent.py     ← 三立场 Agent Panel
│   ├── handover_service.py   ← 交接卡服务
│   └── md_export.py       ← Markdown 导入导出
│
├── models/
│   ├── schemas.py         ← Pydantic 模型 (含 SSE 事件)
│   └── task_contract.py   ← 任务契约 Pydantic 模型
│
├── memory/
│   ├── session_memory.py  ← L2 跨会话记忆 (PGVector)
│   └── user_profile.py    ← L3 用户画像 (PGVector)
│
├── static/                ← 前端 (Vanilla JS + CSS)
│   ├── index.html
│   ├── css/style.css
│   └── js/chat.js         ← SSE 节点级渲染 + 反馈 + 交接卡
│
├── knowledge_base/        ← 手写领域知识 (.md)
│   ├── prompt_engineering.md
│   ├── workflow_best_practices.md
│   ├── tool_recommendations.md
│   ├── tech_news.md
│   ├── engineering/       ← 工程规范知识卡片
│   ├── coding_skills/
│   └── suggested_tools/   ← 工具推荐卡片集 (20张)
│
├── tests/
└── data/                  ← 运行时数据 (日志 + 导出，自动创建)
```

## Session 记录

以下为历史记录，描述当时的实现，不作为当前部署方式或产品方向的依据。特别是 2026-07-22 的独立仓库、自包含 Compose 和环境读取规则已不适用于当前 Portal checkout。

### 2026-07-27 — Docs 整理

- `docs/` 重组：新增 `done/` 归档目录，迁移已完成的架构设计文档（`agent-audit-2026-07-20.md`、`harness-engineering-guide.md`、`context-engineering-guide.md`、`hallucination-prevention.md`、`three-layer-rag.md`）
- `project-summary.md` 统计更新（文档数 10→18 篇 + 5 篇已归档，commit 数 40+→50+）
- 修复多处交叉引用（`product-vision.md`、`ops-guide.md`、`rag-deep-dive.md` 中指向已移动/不存在文件的链接）
- `阿福能力边界与工具使用规范-v1.0.txt` 添加 v2.0 取代声明
- `capability-and-tools.md`、`交互流程图.md` 日期刷新至 2026-07-27

### 2026-07-24 — RAG 来源感知 + 工具卡片

- `rag_service.py`: `ingest_knowledge_base()` glob 修复为 `rglob("*.md")`（子目录原来被忽略）
- `document_processor.py`: 新增 `SourceSplitter._extract_tool_cards()` — `suggested_tools/tools.md` 的 20 张工具卡片自动拆分为独立 Document，卡片级 frontmatter（name/category/source_url/risk_level）提取为独立 metadata
- `ChunkBuilder`: dense/sparse 检索文本加入 `category` 字段，提升分类检索命中率

### 2026-07-24 — 运维性修复

- `.env` 对齐 `.env.example`：补充 15+ 项缺失字段
- `requirements.txt` 同步 `pyproject.toml`：补充 pgvector/aiohttp/numpy/python-multipart
- 多文件修复陈旧引用（SQLite→PostgreSQL、ChromaDB→PGVector、tools 列表更新）

### 2026-07-22 — 独立为 Alfred 项目

从 Portal/MakeItSpecific 子项目独立为完整项目 Alfred:
- `config.py`: 移除 `../.env` (Portal 层) 依赖，仅读项目根 `.env`
- `docker-compose.yml`: 新增 `postgres` 服务 (pgvector/pgvector:pg16)，完全自包含
- `.env.example`: 独立环境变量模板
- 服务名: `specific-api` → `alfred-api`，DB 名: `chatdemopg` → `alfred`

### 2026-07-11（上午 — 架构升级）

1. **三层上下文架构 (V3)** — `core/context_engine.py` (300+ 行)，L1 滑动窗口 + L2 滚动摘要 + L3 语义事实，替代旧版按轮数阈值切换
2. **Planner 升级为语义中枢** — `core/graph.py` 新增 `checkpoint_node`，Executor 后持续介入检查语义对齐
3. **工具 docstring 三段式** — 12 个工具补齐【用途】【不要用】【优先级】【参数/返回】【限制】标注
4. **约束规范文档** — `boundary.md`，7 个维度的 Harness Engineering 规范 + 附录优先级汇总 + 检查清单

### 2026-07-11（下午 — RAG + 深挖）

5. **Embedding 升级** — `text-embedding-v3` → `text-embedding-v4`
6. **语义分块 (SemanticChunker)** — 相邻句子 embedding 相似度断崖切分
7. **混合检索管道** — Dense + BM25(PG tsvector GIN) → RRF → qwen3-rerank → 相似度过滤 ≥0.6 → 关键词加权
8. **Rerank** — 百炼 qwen3-rerank (120K token/500 docs/100+语言)
9. **上下文驱动 Query 增强** — 去硬编码 scene_keywords，多源信号动态加权 + 话题切换检测
10. **L3 语义事实升级** — regex → LLM 结构化提取，内存字典 → PGVector session_memory
11. **Checkpoint 完成** — 独立 retry 计数器 + L1/L2/RAG 上下文注入 + 幻觉检测维度

### 2026-07-10

1. **V2 架构重写** — 从「正则+模板」升级为「ReAct Agentic Loop」
2. **Prompt 重构** — 删除 200 行正则，维度提取改 LLM structured output
3. **前端升级** — 实时 token 渲染 + 光标动画 + 工具调用指示器 + 👍👎 反馈按钮
4. **反馈系统** — `routers/feedback.py` + PostgreSQL feedback 表 + 统计 API
5. **测试覆盖** — 25 tests
