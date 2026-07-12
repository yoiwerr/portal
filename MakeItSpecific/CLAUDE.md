# MakeItSmooth — 个人工作流增强 Agent

> AI 助手，通过引导式对话 + 工具调用，把模糊想法变成可执行方案。
> GitHub: [yoiwerr/portal](https://github.com/yoiwerr/portal) 子项目

## 架构概览

```
Browser (SSE Token Streaming)
    │
    ▼ POST /api/chat/stream?v=2
routers/chat.py  ← token 级流式 (V2) 或兼容模式 (V1)
    │
    ▼
core/agent.py  (Agent 编排器)
    │
    ├─ process_message()        ← 兼容旧版，等图跑完一次性返回
    └─ process_message_stream() ← V2，astream_events token 级流式
         │
         ▼
core/graph.py  (LangGraph ReAct Agentic Loop)
    │
    ├─ rag_retrieve → LangGraph 图:
    │     START → planner → {clarify | execute → reflect → {retry | END}}
    │
    ├─ planner:   LLM JSON mode 提取维度 + 判断完整度
    ├─ clarify:   动态生成追问 (模板兜底)
    ├─ execute:   ReAct Agent (create_react_agent) tool calling loop
    └─ reflect:   LLM 质量检查，不达标自动重试 (最多2次)
         │
         ▼
    ┌─────────────┐  ┌────────────────┐  ┌──────────────┐
    │ tools/       │  │ services/      │  │ skills/      │
    │ search_kb    │  │ rag_service    │  │ YAML 注册    │
    │ search_web   │  │ session_store  │  │ base.py      │
    │ search_hist  │  │ md_export      │  │ registry.py  │
    │ python_exec  │  └────────────────┘  └──────────────┘
    │ file_r/w     │
    └─────────────┘
```

## V2 vs V1 关键差异

| 维度 | V1 (旧) | V2 (新) |
|------|---------|---------|
| 维度提取 | 正则匹配 (`_rule_based_extract_dimensions`) | LLM JSON mode structured output |
| Agent 模式 | 单向流水线 (rag→extract→clarify/execute) | ReAct Agentic Loop (planner→executor→reflector) |
| 执行 | 单次 `create_agent().ainvoke()` | `create_react_agent()` tool calling loop |
| Streaming | 假流式，等 Agent 跑完一次性吐 | 真 token 级流式 (`astream_events`) |
| LLM Provider | 仅 DashScope | DashScope / DeepSeek / OpenAI / Local |
| 反馈 | 无 | 👍👎 按钮 + SQLite 存储 |

## 本地开发

```bash
cd ~/portal
make dev    # 拉起 ChatLab + Streamlit + MakeItSmooth 三服务

# 或单独启动 MakeItSmooth
cd MakeItSmooth
python app.py
# → 首页: http://localhost:8000
# → API 文档: http://localhost:8000/docs
```

### 环境变量

```bash
# 必填（至少一个）
LLM_PROVIDER=auto          # dashscope | deepseek | openai | local | auto
DASHSCOPE_API_KEY=sk-xxx   # 或 DEEPSEEK_API_KEY / OPENAI_API_KEY

# 可选
LLM_MODEL=qwen-plus
MAX_TOOL_ROUNDS=10
SEARCH_API_KEY=tvly-xxx    # Tavily 联网搜索
MEMORY_ENABLED=true
SANDBOX_ENABLED=false      # Python 沙箱（安全风险，默认关闭）
```

## 运行测试

```bash
cd MakeItSmooth
python -m pytest tests/ -v
```

## 服务器部署

```bash
docker compose up -d
# MakeItSmooth API 通过 nginx /smooth/ 路由对外暴露
```

## 加新 Skill

1. 创建 `skills/my_skill.yaml`:
```yaml
name: my_skill
label: 我的技能
icon: 🔧
description: 一句话描述
system_prompt: |
  你是...（System Prompt）
tools: [search_knowledge_base, search_web]
```

2. 在 `skills/registry.py` 注册（或在 `core/agent.py` 中手动添加）

## 项目依赖

- **框架**: FastAPI + LangGraph + LangChain
- **LLM**: 多 Provider (DashScope / DeepSeek / OpenAI / Local)
- **向量存储**: ChromaDB + DashScope text-embedding-v4
- **会话**: SQLite (WSL 兼容)
- **流式**: SSE (sse-starlette)

## 目录结构

```
MakeItSmooth/
├── app.py              ← FastAPI 入口
├── config.py           ← 全局配置 (dataclass, 多 provider)
├── Dockerfile
├── docker-compose.yml
│
├── core/
│   ├── agent.py        ← Agent 编排器 (async, astream_events)
│   ├── graph.py        ← LangGraph V2 ReAct Agentic Loop
│   └── llm_client.py   ← 多 Provider LLM 工厂
│
├── routers/            ← FastAPI 路由
│   ├── chat.py         ← 核心对话 (V1+V2 双模式 SSE)
│   ├── sessions.py     ← 会话管理
│   ├── knowledge.py    ← 知识库管理
│   └── feedback.py     ← 用户反馈
│
├── tools/
│   └── search.py       ← @tool: search_kb / search_web / search_history
│
├── skills/
│   ├── base.py         ← 抽象基类 BaseSkill
│   ├── prompt_refiner.py
│   ├── work_arranger.py
│   └── info_retention.py
│
├── prompts/
│   ├── system_prompts.py  ← Planner/Executor/Reflector + Skill Prompts
│   └── templates.py       ← 维度定义 + 追问模板 + 工具函数
│
├── services/
│   ├── rag_service.py     ← ChromaDB 向量检索
│   ├── session_store.py   ← SQLite 会话持久化
│   └── md_export.py       ← Markdown 导入导出
│
├── models/
│   └── schemas.py         ← Pydantic 模型 (含 V2 streaming 事件)
│
├── static/                ← 前端 (Vanilla JS + CSS)
│   ├── index.html
│   ├── css/style.css
│   └── js/chat.js         ← V2 token 流式渲染 + 反馈
│
├── knowledge_base/        ← 手写领域知识 (.md)
├── tests/
└── data/                  ← 运行时数据 (SQLite + ChromaDB)
```

## Session 记录

### 2026-07-11（上午 — 架构升级）

1. **三层上下文架构 (V3)** — `core/context_engine.py` (300+ 行)，L1 滑动窗口 + L2 滚动摘要 + L3 语义事实，替代旧版按轮数阈值切换
2. **Planner 升级为语义中枢** — `core/graph.py` 新增 `checkpoint_node`，Executor 后持续介入检查语义对齐
3. **工具 docstring 三段式** — 12 个工具补齐【用途】【不要用】【优先级】【参数/返回】【限制】标注
4. **约束规范文档** — `boundary.md`，7 个维度的 Harness Engineering 规范 + 附录优先级汇总 + 检查清单
5. **Context Engineering 实战指南** — `docs/context-engineering-guide.md`，从问题诊断到代码落地的完整指南
6. **RAG 深挖指南** — `docs/rag-deep-dive.md`，从单层检索到企业级多路召回（v2: 6 点反馈修订，含语义分块/qwen3-rerank/上下文驱动Query/幻觉ReAct本质）

### 2026-07-11（下午 — RAG + 深挖）

7. **Embedding 升级** — `text-embedding-v3` → `text-embedding-v4`，6 个文件同步
8. **语义分块 (SemanticChunker)** — 相邻句子 embedding 相似度断崖切分
9. **混合检索管道** — Dense + BM25(PG tsvector GIN) → RRF → qwen3-rerank → 相似度过滤 ≥0.6 → 关键词加权
10. **Rerank** — 百炼 qwen3-rerank (120K token/500 docs/100+语言)
11. **上下文驱动 Query 增强** — 去硬编码 scene_keywords，多源信号动态加权 + 话题切换检测
12. **Prompt 层 RAG 指令** — Executor 来源引用 + Reflector/Checkpoint 幻觉检测
13. **Code Review 8 项修复** — router crash / literal `\n` / 无限循环 / 死守卫 / inject_to_prompt 死代码 / RRF 污染 / 重复代码 / 零向量低效
14. **L3 语义事实升级** — regex → LLM 结构化提取 (偏好/决策/约束/技术栈 + 置信度)，内存字典 → PGVector session_memory (embedding → 向量语义召回)，跨会话可用，LLM 不可用时自动降级
15. **Checkpoint 完成** — 独立 retry 计数器 + L1/L2/RAG 上下文注入 + 幻觉检测维度
16. **学习文档** — `docs/tool-loop-prevention.md` (工具防循环), `docs/hallucination-prevention.md` (幻觉防御), `docs/three-layer-rag.md` (三层 RAG)
17. **boundary/TODO 分离** — boundary 放约束规范, TODO 放进度追踪
18. **主题切换检测** — keyword 重叠率快检 → L2 摘要重置 + L3 内存清空, P1 全部完成

### 2026-07-10

1. **V2 架构重写** — 从「正则+模板」升级为「ReAct Agentic Loop」
   - `core/graph.py`: 单向流水线 → Planner→Executor(ReAct)→Reflector
   - `core/llm_client.py`: 仅 DashScope → 多 Provider (DashScope/DeepSeek/OpenAI/Local)
   - `routers/chat.py`: 假流式 → astream_events token 级流式 (V2)+兼容模式 (V1)
   - `models/schemas.py`: 新增 TokenEvent、ToolCallEvent 等 streaming 事件
2. **Prompt 重构** — 删除 200 行正则 (`DIALOGUE_DIMENSION_DEFS`)，维度提取改 LLM structured output
3. **前端升级** — 实时 token 渲染 + 光标动画 + 工具调用指示器 + 👍👎 反馈按钮
4. **反馈系统** — `routers/feedback.py` + SQLite feedback 表 + 统计 API
5. **测试覆盖** — 25 tests，测试维度合并、JSON 解析、追问生成、完整度计算
