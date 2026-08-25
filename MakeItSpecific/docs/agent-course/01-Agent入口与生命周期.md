# 课程 01：Agent 入口与生命周期

> **难度**: 中级 | **预计阅读**: 20 分钟 | **前置**: [00-架构全景图](00-概述-架构全景图.md)

---

## 一、Agent 类全景

`core/agent.py` 是 FastAPI 与 LangGraph 之间的**桥梁**。它的核心职责：

```
┌─────────────────────────────────────────────────────┐
│                    Agent 类                          │
│                                                     │
│  __init__()  初始化所有子系统                        │
│    ├─ ContextEngine    三层上下文引擎                │
│    ├─ SessionMemory    L2 跨会话记忆                 │
│    ├─ UserProfile      L3 用户画像                   │
│    ├─ inject_services  工具服务注入                  │
│    ├─ Skills 注册      4 个 Skill                    │
│    └─ create_graph()   LangGraph 图                  │
│                                                     │
│  process_message()          旧版: 一次性返回         │
│  process_message_stream()   V2: 节点级流式           │
│                                                     │
│  _retrieve_memory()        记忆检索                  │
│  _summarize_on_complete()  会话结束自动摘要          │
│  _build_initial_state()    构建图的初始状态          │
└─────────────────────────────────────────────────────┘
```

---

## 二、完整请求链路

### 2.1 从 HTTP 到 Agent

```
POST /api/chat/message  (SSE)
  │
  ├─ routers/chat.py: chat_message()
  │   ├─ 解析 ChatRequest (Pydantic)
  │   ├─ JWT 鉴权 → UserClaims
  │   └─ EventSourceResponse(_stream_progress())
  │
  └─ _stream_progress() 异步生成器
      └─ agent.process_message_stream(
            message, module, background, session_id,
            clarify_round, dimensions, extra_context, user_id
         )
         ↓ 逐个 yield SSE 事件
         ↓ {event: "session", data: {session_id, module, model}}
         ↓ {event: "progress", data: {node: "router", label: "正在理解您的意图…"}}
         ↓ {event: "progress", data: {node: "rag", label: "正在检索知识库…"}}
         ↓ ...
         ↓ {event: "contract", data: {action: "draft", contract: {...}}}
         ↓ {event: "clarify", data: {...}} 或 {event: "execute", data: {...}}
         ↓ {event: "done", data: {session_id, tokens_used}}
```

### 2.2 process_message_stream() 详细步骤

```python
async def process_message_stream(self, message, module, background,
                                  session_id, clarify_round, dimensions,
                                  extra_context, user_id):
    # Step 1: 创建或复用会话
    if not session_id:
        session_id = self.sessions.create_session(module, background)
    self.sessions.save_message(session_id, "user", message, "input")

    # Step 2: 发送 session 事件 (含 session_id 和模型名)
    yield {"event": "session", "data": {...}}

    # Step 3: 检索跨会话记忆 (L2/L3)
    memory_context = await self._retrieve_memory(message, session_id)

    # Step 4: 构建初始状态 (L1/L2/L3 + enriched_query + 契约)
    initial_state = await self._build_initial_state(...)

    # Step 5: astream 执行 LangGraph 图
    async for chunk in self.graph.astream(initial_state, stream_mode="updates"):
        for node_name, node_state in chunk.items():
            # 推送进度事件
            yield {"event": "progress", "data": {"node": node_name, "label": ...}}
            # 收集状态变量
            output = node_state.get("output", "") or output
            intent = node_state.get("intent", intent)
            plan = node_state.get("plan", plan)
            ...

    # Step 6: 推送任务契约事件
    if contract and contract.get("goal"):
        yield {"event": "contract", "data": {"action": "draft", "contract": contract}}

    # Step 7: 推送多Agent事件 (如果触发)
    if multi_perspectives:
        for evt in format_panel_for_sse(multi_perspectives):
            yield evt

    # Step 8: 推送工具调用事件
    for tr in tool_results:
        yield {"event": "tool_start", "data": {...}}
        yield {"event": "tool_end", "data": {...}}

    # Step 9: 保存消息 + 触发记忆摘要
    self.sessions.save_message(...)
    await self._summarize_on_complete(session_id, output, intent)

    # Step 10: 更新三层上下文
    await self.context_engine.update_after_turn(messages, session_id, output)

    # Step 11: 发送 done 事件
    yield {"event": "done", "data": {...}}
```

---

## 三、_build_initial_state() 详解

这是 graph 执行的**起始状态**，所有字段都会被注入到 `AgentState`：

```python
async def _build_initial_state(self, message, module, background,
                                session_id, extra_context, dimensions,
                                clarify_round, memory_context, user_id):
    # ── Step A: 调用 ContextEngine.build() 构建三层上下文 ──
    ctx = await self.context_engine.build(
        session_store=self.sessions,
        session_id=session_id,
        current_message=message,
        intent=None,           # 此时尚未识别
        expressed_dimensions=dimensions,
    )
    # ctx.l1_raw, ctx.l2_summary, ctx.l3_facts, ctx.enriched_query, ...

    # ── Step B: 合并记忆上下文到 extra_context ──
    full_extra = extra_context or ""
    if memory_context:
        full_extra = memory_context + "\n\n" + full_extra

    # ── Step C: 组装 AgentState ──
    return {
        "messages": [{"role": "user", "content": message}],
        "module": module,
        "background": background,
        "extra_context": full_extra,
        "expressed_dimensions": dimensions,
        "clarify_round": clarify_round,
        "rag_context": "",
        "enriched_query": ctx.enriched_query,
        "plan": {},
        "tool_results": [],
        "reflection_count": 0,
        "output": "",
        "intent": {},
        # 三层上下文
        "l1_raw": ctx.l1_raw,
        "l2_summary": ctx.l2_summary,
        "l3_facts": ctx.l3_facts,
        "last_turn_summary": ctx.last_turn_summary,
        "turn_count": ctx.turn_count,
        # Planner checkpoint
        "checkpoint_feedback": "",
        "checkpoint_retry_count": 0,
        # 执行进度追踪
        "completed_steps": [],
        "execute_round": 0,
        # 用户上下文
        "user_id": user_id,
        "session_id": session_id,
    }
```

> **关键设计**: `enriched_query` 在 graph 执行前就预构建好了（由 ContextEngine 完成），graph 中的 `enrich` 节点只做透传+兜底。这样上下文注入和 RAG 查询增强是解耦的。

---

## 四、记忆检索策略

```python
async def _retrieve_memory(self, message, session_id):
    # 条件1: session_memory 或 user_profile 已初始化
    if not self.session_memory and not self.user_profile:
        return ""

    # 条件2: 新会话首条消息 → 只有"继续"信号才检索
    if session_id and self.sessions:
        msgs = self.sessions.get_conversation(session_id)
        turn_count = sum(1 for m in msgs if m.get("role") == "user")
        if turn_count <= 1:
            resume_signals = ["继续","上次","之前","恢复","接着","接上","回到","前面","刚才"]
            if not any(sig in message for sig in resume_signals):
                return ""  # 新会话默认不注入旧记忆，避免污染

    # L2: 检索相关历史会话摘要 (向量相似度, top_k=3)
    hist = await self.session_memory.retrieve(message, top_k=3)

    # L3: 获取用户画像
    profile = await self.user_profile.format_for_context()

    return "\n".join([hist, profile])
```

> **设计要点**: 新会话不会被旧记忆污染。只有用户明确表达"继续上次"时，才会检索跨会话记忆。

---

## 五、会话结束自动摘要

```python
async def _summarize_on_complete(self, session_id, output, intent):
    # 前置条件: session_memory 和 user_profile 已初始化
    # 对话至少 3 轮
    messages = self.sessions.get_conversation(session_id)
    if len(messages) < 3:
        return

    # L2: 生成会话摘要 (LLM → JSON → PGVector)
    summary = await self.session_memory.summarize_and_store(
        session_id=session_id, messages=messages, module=intent.get("module",""))

    # L3: 更新用户画像 (规则合并 + LLM 更新)
    if summary:
        summary_data = json.loads(summary)
        await self.user_profile.update_from_summary(summary_data)
```

> **设计要点**: 摘要和画像更新是**异步非阻塞**的 — 失败了打 warning，不影响主对话流程。

---

## 六、与图的关系: 两种调用方式

| 方面 | process_message() | process_message_stream() |
|------|-------------------|--------------------------|
| 调用 | `graph.ainvoke()` | `graph.astream()` |
| 返回 | 一次性 dict | 逐个 yield 状态更新 |
| 前端 | 等全部完成 | 节点级进度推送 |
| 用途 | 向后兼容 | 当前主力 |

---

## 七、工具和服务注入

在 `Agent.__init__()` 中，`inject_services()` 只调用一次：

```python
# core/agent.py: __init__
inject_services(rag_service=rag_service, config=config, agent=self)
```

这会设置各工具模块的模块级变量：

```python
# tools/__init__.py
def inject_services(rag_service=None, config=None, agent=None):
    import tools.search as search_mod
    import tools.knowledge as knowledge_mod
    import tools.code as code_mod

    search_mod._rag_service = rag_service       # search_knowledge_base 用
    knowledge_mod._rag_service = rag_service    # add_to_knowledge_base 用
    code_mod._config = config                   # python_exec 用

    from tools.fs import set_fs_tool_config
    set_fs_tool_config(config=config)

    from tools.memory import set_memory_tool_services
    set_memory_tool_services(agent=agent, config=config)
```

> **为什么用模块级变量而不是依赖注入？** LangChain `@tool` 装饰器创建的是普通函数，不能通过构造函数注入。模块级变量是最轻量的方案。

---

## 八、生命周期时序图

```
时间 ──────────────────────────────────────────────────────>

App 启动
  ├─ config = Config.from_env()
  ├─ model = create_model(config)
  ├─ rag_service = RAGService(...)
  ├─ await rag_service.ensure_ready()
  ├─ await rag_service.ingest_knowledge_base()    ← 索引知识库
  ├─ session_store = SessionStore(...)
  ├─ contract_store = ContractStore(...)
  ├─ agent = Agent(model, rag_service, session_store, config, contract_store)
  │   ├─ ContextEngine.__init__()
  │   ├─ _init_memory()  → SessionMemory + UserProfile
  │   ├─ inject_services()
  │   ├─ Skills 注册 (4个)
  │   └─ create_graph()  → workflow.compile()
  └─ set_agent(agent)  ← 注入到 routers/chat.py

每次请求
  ├─ agent.process_message_stream(...)
  │   ├─ _retrieve_memory()        ← 检索跨会话记忆
  │   ├─ _build_initial_state()
  │   │   └─ context_engine.build() ← L1/L2/L3 + enriched_query
  │   ├─ graph.astream(initial_state)
  │   │   └─ [router → enrich → rag → planner → ...]
  │   ├─ _summarize_on_complete()  ← 异步，不阻塞
  │   └─ context_engine.update_after_turn()
  └─ yield SSE events → 前端渲染
```

---

## 九、关键要点

1. **Agent 是胶水层** — 它不干具体活，负责把 HTTP 请求、记忆系统、LangGraph 图、SSE 流式串起来
2. **初始状态构建是重头戏** — `_build_initial_state()` 决定了图一开始拿到什么上下文
3. **记忆默认不注入** — 新会话不会被旧记忆污染，只有"继续上次"时才检索
4. **总结是异步的** — 不阻塞主流程，失败了只打 warning
5. **工具注入是一次性的** — `inject_services()` 在 `__init__` 调用一次，后续所有工具调用共享

---

## 十、继续学习

→ [02-图与状态机](02-图与状态机.md) — 深入 LangGraph StateGraph 的定义、节点流转和条件路由
