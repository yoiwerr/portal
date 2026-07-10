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
- **向量存储**: ChromaDB + DashScope text-embedding-v3
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
