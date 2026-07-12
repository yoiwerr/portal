# MakeItSmooth V2 开发进度总结

> 2026-07-10

---

## 一句话

从「正则+模板的单向流水线」升级为「ReAct Agentic Loop + 多 Agent 委托 + 跨会话记忆」的生产级 Agent 平台。

---

## 已完成工作

### 阶段 A: 核心 Agent 化

**LLM 层**
- `core/llm_client.py` — 多 Provider 工厂，支持 DashScope / DeepSeek / OpenAI / Local / Auto
- 装饰器 `@_provider()` 注册模式，加 provider 只需一个函数

**Agent 引擎**
- `core/graph.py` — ReAct Agentic Loop 替代单向流水线
  - 6 节点: Router → Enrich → RAG → Planner → Clarify/Execute → Reflect
  - Planner: LLM JSON mode 提取维度（替代 200 行正则）
  - Execute: `create_react_agent()` tool calling loop（替代单次 invoke）
  - Reflector: 质量审查 + 最多 2 次自动重试
  - Query Enrichment: 规则拼接上下文（零延迟）提升 RAG 命中率
- `core/router.py` — 意图识别 Router
  - 规则快速分类 + LLM 精判双通道
  - 6 类意图: prompt_optimize / work_plan / info_organize / research / code_help / general
- `core/agent.py` — Agent 编排器
  - `process_message()` — 兼容旧版 API
  - `process_message_stream()` — astream_events token 级流式
  - 自动记忆注入 + 会话结束自动摘要
  - module="auto" 默认触发 Router

**Prompt 层**
- `prompts/system_prompts.py` — Planner / Executor / Reflector / 3 Skills System Prompts
- `prompts/templates.py` — 删除正则维度提取，保留维度定义 + 追问模板 + 工具函数

### 数据库迁移: ChromaDB → PostgreSQL + PGVector

- `services/vector_store.py` — PGVectorStore 类
  - 3 张表: domain_knowledge / session_memory / user_profile
  - 自动建表 + IVFFlat 索引 + 完整 CRUD
- `services/rag_service.py` — 重写为 PGVector 后端
- `memory/session_memory.py` — L2 跨会话记忆
- `memory/user_profile.py` — L3 用户画像
- 与 ChatLab 共用 pgvector/pgvector:pg16 容器，独立 database `makeitsmooth`

### 工具生态: 7 Tools（含 1 Meta Tool）

```
信息检索:
  search_knowledge_base   — PGVector 向量检索
  search_web              — Tavily 联网搜索（非占位符）
  fetch_url               — 抓取网页内容 → Markdown

代码执行:
  python_exec             — 沙箱 Python（SANDBOX_ENABLED 控制）

知识管理:
  add_to_knowledge_base   — 对话知识写入向量库（信息闭环）

系统感知:
  run_shell_preview       — 只读 Shell 白名单（ls/cat/git status 等）

Multi-Agent:
  delegate_task           — ★ 委托子 Agent 独立执行子任务
                            子 Agent 自带搜索工具，不能再 spawn
                            8 轮上限 / 60s 超时
```

**Skill → Tool 映射**：每种 Skill 只拿到 2-5 个相关工具，避免选择困难。

### 记忆系统: L1/L2/L3

```
L1 ✅ 对话内记忆 — SQLite sessions/messages
L2 ✅ 跨会话记忆 — 会话结束 LLM 摘要 → PGVector session_memory
                   新会话开始自动检索相关历史
L3 ✅ 用户画像   — 技术栈/项目/偏好增量学习
                   规则层快速合并 + LLM 层智能更新
```

### 产品化基础

- `routers/feedback.py` — 👍👎 反馈收集 + 统计
- `models/schemas.py` — 完整 Pydantic 模型（含 streaming 事件 + Agent 内部模型）
- `GOVERNANCE.md` — 项目宪章（开发原则/代码审查 Checklist/安全规范/多 Agent 协议/质量指标）
- `CAPABILITIES.md` — 能力清单 + Tools/Skills/MCP/API Key 矩阵
- `CLAUDE.md` — 架构文档 + 开发指南
- `TODO.md` — 待做事项 + 实施路线图（含你主导部分）

### 前端

- `static/js/chat.js` — V2 Token 级流式渲染 + 👍👎 反馈按钮 + tool_start/tool_end 状态
- `static/css/style.css` — 流式光标动画 + 工具调用指示器 + 反馈 UI

### 基础设施

- `config.py` — 多 Provider + PG + Agent + Sandbox 配置
- `.env.example` — 更新
- `docker-compose.yml` — 共享 ChatLab PG 容器
- `Dockerfile` — 更新依赖
- `requirements.txt` — chromadb → psycopg2-binary

### 测试

- **25 tests pass** — 维度合并 / JSON 解析 / 追问生成 / 完整度计算 / 会话管理
- Shell 安全校验 8/8
- Router 规则分类 9/9

---

## 文件变更全量

```
新建 (12):
  core/router.py
  tools/shell.py
  tools/delegate.py
  services/vector_store.py
  memory/__init__.py
  memory/session_memory.py
  memory/user_profile.py
  routers/feedback.py
  GOVERNANCE.md
  CAPABILITIES.md
  CLAUDE.md
  TODO.md

重写 (11):
  core/graph.py          (单向流水线 → 6 节点 ReAct + Router + Enrich)
  core/agent.py           (+ 记忆注入 + 自动摘要 + module="auto")
  core/llm_client.py      (DashScope only → 多 Provider 工厂)
  tools/__init__.py        (10→7 tools + Skill→Tool 映射)
  tools/search.py          (search_web 占位符 → Tavily 真实搜索 + fetch_url)
  tools/knowledge.py       (ChromaDB → PGVector)
  prompts/system_prompts.py (加入 Planner/Executor/Reflector)
  prompts/templates.py     (删除 200 行正则)
  models/schemas.py        (+ streaming 事件 + Agent 内部模型)
  services/rag_service.py  (ChromaDB → PGVector)
  config.py                (+ PG + 多 Provider + Agent + Sandbox)

更新 (11):
  app.py                   (同步 → async lifespan + PGVector)
  routers/chat.py          (V1 兼容 + V2 token 流式双模式)
  routers/knowledge.py     (ChromaDB → PGVector)
  routers/sessions.py      (无变动)
  static/js/chat.js        (V2 流式渲染 + 反馈)
  static/css/style.css     (流式动画 + 反馈 UI)
  memory/session_memory.py (ChromaDB → PGVector)
  memory/user_profile.py   (ChromaDB → PGVector)
  docker-compose.yml       (共享 PG + 网络)
  Dockerfile               (chromadb → psycopg2)
  requirements.txt         (chromadb → psycopg2-binary)
  .env.example             (+ DB 配置)
  tests/test_graph.py      (适配 V2 架构, 25 tests)

删除:
  chromadb 依赖 + 所有 ChromaDB 调用
  _rule_based_extract_dimensions() (~200 行正则)
  伪流式 SSE (保留 V1 兼容, 主推 V2 token 流)
```

---

## 当前完整图流程

```
START
  │
  ▼
┌──────────┐   module="auto" 时自动判断意图
│  Router  │   LLM + 规则双通道，6 类场景
└────┬─────┘
     │
     ▼
┌──────────┐   规则拼接上下文，提升 RAG 命中率
│  Enrich  │   零延迟，不调 LLM
└────┬─────┘
     │
     ▼
┌──────────┐   用 enriched_query 检索 PGVector
│   RAG    │   domain_knowledge 表
└────┬─────┘
     │
     ▼
┌──────────┐   LLM JSON mode 提取维度 + 判断完整度
│ Planner  │   完整度 < 75% → Clarify
└────┬─────┘   完整度 >= 75% → Execute
     │
  ┌──┴──┐
  │     │
  ▼     ▼
Clarify  Execute (ReAct Agent loop, 3-5 tools per Skill)
  │        │
  │        ▼
  │     Reflect (质量检查)
  │        │
  │     ┌──┴──┐
  │    OK  重试(≤2次)
  │     │     │
  ▼     ▼     └→ Execute
 END   END
```

---

## 已确认的架构决策

| 决策 | 结论 |
|------|------|
| Agent 范式 | **ReAct** — 所有决策点 LLM 推理 |
| 编排引擎 | **LangGraph StateGraph** — 为多 Agent Send() 做准备 |
| 向量库 | **PostgreSQL + PGVector** — 独立 database，与 ChatLab 隔离 |
| 工具数量 | **7 个** — 6 核心 + 1 Meta (delegate_task) |
| 缓存 | **Redis** — 暂不做，产品化阶段加 |
| 意图识别 | **独立 Router 节点** — LLM + 规则双通道 |
| 多 Agent | **Supervisor-Worker** — Phase 1: delegate_task tool (已实现) |
| 模型降级 | Auto 模式按 priority 选择第一个有 key 的 provider |
| 数据库 | 独立 database `makeitsmooth` |

---

## 待做

### 你主导实现（AI 引导）
- Token 用量实时监控 → `obs/token_tracker.py`
- 幻觉检测基础版 → 事实校验 + 置信度分层
- 循环检测 → ReAct 死循环打断
- RAG 语义化分块 → 分析现有问题 → 逐步升级

### 继续合作实现
- B4: 前端统一对话入口（替代三卡片）
- Graph 级多 Agent（Send API 并行）
- 产品化（认证/限流/LangFuse）

### 基础设施
- Tavily API 实测（需要 API Key）
- python_exec 沙箱安全审查
- PGVector 数据迁移脚本（从 ChromaDB 旧数据）
