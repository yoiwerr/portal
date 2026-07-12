# MakeItSpecific 目录职能

> AI 工作流增强 Agent — 直接对话，自动路由意图，RAG 知识检索 + 三层记忆 + 追问补全。
> 最后更新：2026-07-12

---

## 目录一览

```
MakeItSpecific/
│
├── static/          ← 前端（浏览器直接加载）
├── routers/         ← API 路由（HTTP 请求入口）
├── core/            ← Agent 引擎（意图路由、LangGraph 图、上下文管理、LLM 工厂）
├── services/        ← 数据服务（PGVector 向量库、RAG 检索、SQLite 会话、MD 导出）
├── tools/           ← Agent 可调用的工具集（10 个 LangChain @tool）
├── skills/          ← 三个 Skill（提示词工程 / 工作安排 / 信息留存）
├── prompts/         ← 所有 System Prompt 文本 + 维度定义 + 追问模板
├── models/          ← Pydantic 数据模型（请求/响应/SSE 事件/Agent 内部）
├── memory/          ← L2 跨会话记忆 + L3 用户画像
│
├── knowledge_base/  ← RAG 知识源（手写 .md 文件，向量化后注入 Agent）
├── data/            ← 运行时数据（SQLite DB + 导出文件 + 运行日志）
│
├── docs/            ← 学习文档（RAG 深挖、幻觉防御、Context Engineering 等）
├── tests/           ← 单元测试
│
├── app.py           ← 启动入口
├── config.py        ← 全局配置
├── Dockerfile / docker-compose.yml / pyproject.toml / requirements.txt
└── *.md             ← 项目治理文档（CLAUDE.md / boundary.md / GOVERNANCE.md / PROGRESS.md / CAPABILITIES.md）
```

---

## `static/` — 前端

浏览器加载的纯静态文件，零框架依赖。

| 文件 | 作用 |
|------|------|
| `index.html` | 纯对话 UI：初始显示三个功能提示框 + 提示词范例，发消息后切为对话流 |
| `css/style.css` | 全站样式（黑色 + 灰色，零色彩零特效） |
| `js/chat.js` | SSE 流式对话客户端：逐 token 渲染、Markdown 解析、👍👎 反馈收集 |
| `js/particles.js` | 可选背景（当前未使用） |

---

## `routers/` — API 路由

HTTP 请求的入口层，每个文件对应一组 REST 端点。

| 文件 | 端点 | 作用 |
|------|------|------|
| `chat.py` | `POST /api/chat/stream` | 核心对话：V1 一次性返回 + V2 SSE token 流式（`?v=2`） |
| `sessions.py` | `GET/DELETE /api/sessions` | 历史会话列表、详情、删除 |
| `knowledge.py` | `GET/POST /api/knowledge` | 知识库搜索 + 重建索引 |
| `feedback.py` | `POST /api/feedback` | 用户反馈收集（存 SQLite feedback 表，含 rating + comment） |

---

## `core/` — Agent 引擎

整个系统的大脑。五个文件协作构建 Agent 的完整决策循环。

| 文件 | 作用 |
|------|------|
| `graph.py` | **最核心文件** — LangGraph 状态图定义。8 节点流程：`router → enrich → rag → planner → {clarify | execute → checkpoint → reflect → {execute | END}}`。checkpoint 是 Planner 语义中枢，在每次 execute 后检查输出是否偏离用户意图 |
| `agent.py` | Agent 编排器 — 封装 LangGraph 图的调用。`process_message()` (V1) 和 `process_message_stream()` (V2 token 流式)，初始化时注入 ContextEngine + 记忆系统 + 三个 Skill + 工具 |
| `router.py` | 意图识别 — LLM + 规则双通道，判断用户想做什么（6 类意图 → 3 个模块），替代手动选模块 |
| `context_engine.py` | 三层上下文引擎 — L1 最近 3 轮原文零成本保留 / L2 LLM 滚动摘要增量更新 / L3 LLM 提取语义事实 → PGVector 跨会话召回。含主题切换检测 + RAG query 增强 |
| `llm_client.py` | LLM 工厂 — 一个 `create_model(config)` 函数，支持 DashScope / DeepSeek / OpenAI / Local 四 provider，新加 provider 只需一个 `@_reg("name")` 装饰函数 |

---

## `services/` — 数据服务

对接 PostgreSQL / SQLite / 文件系统的数据层。

| 文件 | 作用 |
|------|------|
| `vector_store.py` | PGVector 向量存储封装 — 三张表（domain_knowledge / session_memory / user_profile），IVFFlat 余弦索引 + GIN 全文索引，完整 CRUD + BM25 全文检索 |
| `rag_service.py` | RAG 检索管道 — 混合检索 Dense+BM25 → RRF 融合 → qwen3-rerank 精排 → 相似度过滤（≥0.6）→ 关键词加权。含 SemanticChunker 语义分块器 |
| `session_store.py` | SQLite 会话存储 — sessions + messages 两张表，WSL 兼容（journal_mode=DELETE + busy_timeout） |
| `md_export.py` | Markdown 导入导出 — 将对话记录导出为 .md 文件，或从多个 .md 文件加载上下文 |

---

## `tools/` — Agent 工具集

LangChain `@tool` 装饰的函数，Agent 在执行阶段按需调用。由 `__init__.py` 统一注册并分配到各 Skill。

| 文件 | 工具 | 类型 |
|------|------|------|
| `search.py` | `search_knowledge_base` / `search_web` / `fetch_url` / `search_chat_history` | 信息检索 |
| `code.py` | `python_exec` | 代码沙箱 |
| `delegate.py` | `delegate_task` | 多 Agent 委托 |
| `shell.py` | `run_shell_preview` | 只读 Shell |
| `text.py` | `parse_text` / `compare_texts` / `summarize_text` | 文本规则引擎 |
| `knowledge.py` | `add_to_knowledge_base` / `list_knowledge_sources` | 知识管理 |
| `__init__.py` | `ALL_TOOLS` + `SKILL_TOOL_MAP` + `get_tools_for_skill()` | 工具注册表 |

---

## `skills/` — 任务执行模块

三个 Skill 都继承 `base.py` 的 `BaseSkill`，输入 `SkillContext`，输出 Markdown。

| 文件 | 功能 | 典型输出 |
|------|------|----------|
| `prompt_refiner.py` | 提示词工程 | 大白话 → 追问 → 2-3 个优化版提示词（版号 A/B/C + 推荐模型 + 理由） |
| `work_arranger.py` | 工作安排 | 模糊想法 → 追问 → 结构化计划（阶段划分 + 任务表 + MVP + 下一步） |
| `info_retention.py` | 信息留存 | 对话/文件 → 追问 → 结构化 Markdown 文档 |
| `base.py` | 抽象基类 | `BaseSkill(ABC)` + `SkillContext` dataclass |

---

## `prompts/` — Prompt 文本

所有 System Prompt 文本集中管理，与 Python 逻辑分离。

| 文件 | 内容 |
|------|------|
| `system_prompts.py` | 8 段 Prompt：Planner / Executor / Reflector / 三个 Skill / 维度提取 / 场景分类 |
| `templates.py` | 维度定义（权重/必填/可选）+ 追问模板 + 工具函数（完整度计算/维度格式化） |

---

## `models/` — 数据模型

| 文件 | 内容 |
|------|------|
| `schemas.py` | Pydantic 模型全集：`ChatRequest`、SSE 事件（Token/ToolCall/Clarify/Execute/Error/Done）、Agent 内部（AgentPlan/DimensionInfo/SkillResult/PromptVersion）、管理（SessionSummary/FeedbackRequest/HealthResponse） |

---

## `memory/` — 记忆系统

| 文件 | 作用 |
|------|------|
| `session_memory.py` | L2 跨会话记忆 — 会话结束 LLM 摘要 → embedding → PGVector `session_memory` 表，新会话开始时向量检索注入上下文 |
| `user_profile.py` | L3 用户画像 — 从多次对话逐渐学习技术栈/偏好/项目，存 PGVector `user_profile` 表（单文档），规则层快速合并 + LLM 层智能更新 |

---

## `knowledge_base/` — RAG 知识源

手写 Markdown 文件，启动时自动向量化到 PGVector `domain_knowledge` 表。Agent 执行任务前先搜这里。

→ 加知识：新建 `.md` 文件放这里，调用 `/api/knowledge/reindex` 重建索引。

---

## `data/` — 运行时数据

程序运行中产生的文件，`.gitignore` 忽略全部（仅保留目录结构）。

| 子目录/文件 | 内容 |
|-------------|------|
| `makeitspecific.db` | SQLite 数据库（sessions + messages + feedback 三张表） |
| `exports/` | Markdown 导出文件 |
| `logs/app.log` | 运行日志（终端同步输出，RotatingFileHandler，5MB × 3 文件） |

---

## `docs/` — 学习文档

开发过程中产出的深度学习文档，非代码、非运行必需。

| 文件 | 内容 |
|------|------|
| `rag-deep-dive.md` | RAG 深挖：从单层检索到 Dense+BM25+RRF+Rerank 混合检索，六轮反馈修订 |
| `context-engineering-guide.md` | 三层上下文引擎：原理 → 代码落地 → 调试方法 |
| `three-layer-rag.md` | 三层 RAG 架构总览：Dense + BM25 + 知识图谱摘要互补覆盖 |
| `hallucination-prevention.md` | 幻觉防御：四种幻觉类型 + 四层防线 + ReAct 本质 |
| `tool-loop-prevention.md` | 工具防循环：Agent 为什么打转 + 三层防线设计 |

---

## `tests/` — 单元测试

| 文件 | 内容 |
|------|------|
| `test_graph.py` | 核心图纯函数测试：JSON 解析降级链、维度合并、追问生成、完整度计算、路由逻辑 |
| `test_session_store.py` | SQLite 会话测试：创建、消息读写、级联删除、过滤 |

---

## 项目治理文档（`*.md`）

| 文件 | 读者 | 内容 |
|------|------|------|
| `CLAUDE.md` | Claude Code | 架构概览 + 本地开发 + 部署 + Session 记录 |
| `boundary.md` | 开发者 | 工具边界、Context Engineering 规范、RAG 架构、检查清单 |
| `GOVERNANCE.md` | 开发者 | 项目宪章：开发原则、代码审查清单、安全规范、多 Agent 协议 |
| `CAPABILITIES.md` | 产品/开发者 | 能力清单、Tools/Skills/Memory/MCP/API Key 矩阵 |
| `PROGRESS.md` | 开发者 | V2/V3 开发进度记录、已完成的架构决策 |
| `README.md` | 所有人 | 本文件 |

---

## 数据流全链路

```
浏览器 POST /api/chat/stream?v=2
    │  SSE EventSourceResponse
    ▼
routers/chat.py
    │  agent.process_message_stream()
    ▼
core/agent.py ── _build_initial_state()
    │               ├─ ContextEngine.build()  → L1/L2/L3 上下文
    │               ├─ SessionMemory.retrieve() → 跨会话记忆
    │               └─ UserProfile.format()    → 用户画像
    ▼
core/graph.py ── LangGraph astream_events
    │
    ├─ router     → core/router.py (LLM+规则 意图识别)
    ├─ enrich     → context_engine (query 增强)
    ├─ rag        → services/rag_service.py (Dense+BM25→RRF→Rerank)
    ├─ planner    → prompts/system_prompts.py (LLM JSON mode)
    ├─ execute    → create_react_agent(tools) → tools/ (10 tools)
    ├─ checkpoint → Planner 语义对齐检查
    └─ reflect    → 质量审核 (最多 2 次重试)
    │
    ▼ SSE token stream
static/js/chat.js ── 逐 token 渲染 + Markdown + 反馈按钮
```
