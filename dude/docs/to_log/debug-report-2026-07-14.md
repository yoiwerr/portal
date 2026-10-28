# 调试报告 — 2026-07-14

> V2 流式输出全链路排查，定位并修复 4 个 bug

## 问题时间线

| 顺序 | 用户反馈 | 日志信号 | 根因 |
|------|---------|---------|------|
| 1 | "输出是 JSON 格式" | token 流包含 Planner JSON | `astream_events` 无过滤 → Planner/Checkpoint/Reflector 的 JSON mode 输出混入 |
| 2 | "加过滤后没有输出" | `tokens=0` | 白名单 `!= "execute"` 误杀（子图 LLM 节点名是 `"agent"`） |
| 3 | 同上 | `get_state: No checkpointer set` | `get_state(initial_state)` — 传了 dict 而不是 RunnableConfig；图编译时无 checkpointer |
| 4 | 同上 | 子图 `agent` 节点 token 不在外层 stream 中 | `create_react_agent` 的 token 不冒泡到外层 `astream_events` — 架构问题 |
| 5 | "tool 参数格式问题" | `Object of type coroutine is not JSON serializable` | `search_knowledge_base` 是 sync `@tool`，但内部调用了 `async` 函数没 `await` |
| 6 | "看看哪里话有问题" | L3 0 条事实 / 话题误判 | L3 `json.loads` 不处理 markdown 包裹 / 早期对话被误判为话题切换 |

---

## Bug 1: 流式输出包含内部 JSON

### 现象
用户看到对话框里输出 Planner/Checkpoint/Reflector 的 JSON 原文。

### 根因
`core/agent.py:221` 的 `process_message_stream()` 通过 `astream_events` 监听**所有节点**的 `on_chat_model_stream` 事件。Planner、Checkpoint、Reflector 都使用 `response_format={"type": "json_object"}` 输出结构化 JSON，这些 token 被无条件推给了前端。

### 后果
用户看到类似这样的内容混在正常对话里：
```json
{"is_complete": true, "completeness": 0.85, "goal": "...", "extracted_dimensions": {...}}
```

### 修复尝试与失败

**尝试 1** — 白名单过滤（`agent.py:229`）：
```python
node_name = event.get("metadata", {}).get("langgraph_node", "")
if node_name != "execute":
    continue
```
**失败原因**：`execute_node` 内部调用 `create_react_agent` 构建了一个独立的子图。该子图的 LLM 节点运行时 `langgraph_node` 值是 `"agent"`（由 `create_react_agent` 内部命名），不是 `"execute"`。白名单把 ReAct Agent 的 token 也拒绝了。→ **tokens=0**

**尝试 2** — 黑名单过滤：
```python
if node_name in ("planner", "router", "checkpoint", "reflect"):
    continue
```
**失败原因**：黑名单逻辑本身正确，但由于 Bug 2，ReAct Agent 子图的 token 根本不经过外层的 `astream_events`，所有 token 事件都来自外层节点（planner）。黑名单把 planner 拦了 → 仍然 **tokens=0**。

### 最终修复
放弃 `astream_events`，改用 `graph.ainvoke()` 直接拿最终结果：

```python
# core/agent.py — 最终方案
result = await self.graph.ainvoke(initial_state)
output = result.get("output", "")        # Executor 的完成文本
intent = result.get("intent", {})        # Router 的判断结果
plan = result.get("plan", {})            # Planner 的计划
```

SSE 事件流仍然是 `session → execute/clarify → done`，前端无需改动。代价是失去了"逐字打印"效果。

### 为什么逐字打印做不到了
`create_react_agent` 是 LangGraph 的预编译子图，在 `execute_node` 内部通过 `.ainvoke()` 调用。外层 `astream_events` 只能看到外层编译图节点的 LLM 事件：

```
外层 astream_events 能看到:
  ✅ planner (LLM JSON mode)
  ❌ execute 内部的 create_react_agent 子图 (LLM token 不冒泡！)
  ✅ checkpoint (LLM JSON mode)
  ✅ reflect (LLM JSON mode)
```

这是 LangGraph 的架构限制：子图的 streaming 事件不会冒泡到父图的 `astream_events`。要恢复 token 级流式，需要把 ReAct Agent 从 `execute_node` 内部提到外层图作为独立节点。

---

## Bug 2: `get_state` 失败 — No checkpointer set

### 现象
```
[WARNING] [Agent] get_state 失败: No checkpointer set
```

### 根因
`agent.py:270` 的旧代码：
```python
raw_state = self.graph.get_state(initial_state)  # ❌
```
`initial_state` 是纯 `dict`，而 `get_state()` 需要 `RunnableConfig`（含 `thread_id`）。图编译时也没带 checkpointer。

### 连锁反应
`except: pass` 静默吞了异常 → output 保持 `full_output`（空字符串）→ `if output:` 为 False → 整个 SSE 流只有 `session` 事件，没有 `clarify`/`execute` 事件 → 前端显示空白。

### 修复
随 Bug 1 一起，改为 `ainvoke` 直接拿结果，不再需要 `get_state`。

---

## Bug 3: `search_knowledge_base` — coroutine 未 awaited

### 现象
```
[ERROR] search_knowledge_base 失败: Object of type coroutine is not JSON serializable
RuntimeWarning: coroutine 'RAGService.query_structured' was never awaited
```

### 根因
`tools/search.py:31` — `search_knowledge_base` 是**同步** `@tool`：
```python
@tool
def search_knowledge_base(query: str) -> str:  # ← sync
    ...
    data = _rag_service.query_structured(query, top_k=3)  # ← async，但没 await
    return json.dumps(data, ...)  # ← data 是 coroutine 对象，不是 dict！
```

`add_to_knowledge_base` 已经正确声明为 `async def`，但 `search_knowledge_base` 漏掉了。

### 为什么之前没发现
之前的"流式"实际上是你说的 Bug 1（Planner JSON 被当输出）。在 Bug 1 修复之前，Executor 根本没走到 tool calling 这一步 — Planner 可能判定信息足够直接进入 execute，execute 不调 search tool 就直接回答了，所以这个 coroutine 错误从来没暴露过。

### 修复
```python
# tools/search.py
@tool
async def search_knowledge_base(query: str) -> str:  # ← async
    ...
    data = await _rag_service.query_structured(query, top_k=3)  # ← await
```

---

## Bug 4: L3 事实提取静默失败

### 现象
```
[WARNING] L3 LLM 提取失败，降级规则提取: '\n  "facts"'
[INFO] L3 累计事实: 会话 ... → 0 条 (内存后备)
```

### 根因
`context_engine.py:380` — `_extract_facts_llm` 中：
```python
data = json.loads(response.content)
```
LLM（DeepSeek/Qwen）有时在 JSON 外加 markdown 代码块包围（```` ```json ... ``` ````），`json.loads` 直接失败。降级到 `_extract_atomic_facts()`（规则提取，正则匹配），但规则提取只能匹配非常明确的句式，这轮对话中没匹配到任何模式 → 0 条事实。

### 连锁反应
- **L3 完全没数据**：Planner/Executor 拿不到历史事实上下文
- **话题切换检测退化**：`_detect_topic_switch` 从 L3 事实中提取关键词进行对比，L3 为空时只能用 L2 摘要的关键词，匹配率下降 → 误判概率上升

### 修复
1. 新增 `_safe_parse_json()` — 健壮 JSON 解析，依次尝试：裸 JSON → markdown 代码块 → 正则提取 `{...}`
2. `_extract_facts_llm` 改用 `_safe_parse_json()`

### 同时修复：话题切换误判

`_detect_topic_switch` 在早期对话（≤4 轮）中过于激进。用户一轮说"我想做卡牌游戏"，下一轮补充"类似杀戮尖塔"、"用 Unity" — 这些细节展开被判定为"话题切换"，L2 摘要被重置导致上下文丢失。

修复：
```python
# 早期对话（≤4 轮）仍在澄清需求，不检测话题切换
if turn_count <= 4:
    return False
```

---

## 修改文件清单

| 文件 | 改动行 | 改动内容 |
|------|--------|---------|
| `core/agent.py` | 181-303 | `process_message_stream` 重写：`astream_events` → `ainvoke` |
| `core/context_engine.py` | 25 | 新增 `import json` |
| `core/context_engine.py` | 200 | L3 提取补 `await` |
| `core/context_engine.py` | 275-278 | 话题切换检测加 `turn_count <= 4` 早退 |
| `core/context_engine.py` | 370-390 | `_extract_facts_llm` JSON 解析改用 `_safe_parse_json()` |
| `core/context_engine.py` | 738-755 | 新增 `_safe_parse_json()` 函数 |
| `tools/search.py` | 31 | `def` → `async def` |
| `tools/search.py` | 71 | 补 `await` |

---

## 架构启示

1. **`astream_events` 只捕获本层图的 LLM 事件** — 子图（`create_react_agent`）的 token 不冒泡。这是 LangGraph 的设计，不是 bug。如果用 `astream_events` 实现流式，需要把 ReAct Agent 直接编译到主图里而不是嵌套在节点内。

2. **`@tool` 的 async/sync 必须与内部调用一致** — LangChain 对 sync tool 做了线程池包装，但如果 sync tool 内部调了 async 函数且没 await，coroutine 对象会静默通过返回值传递，直到 `json.dumps` 之类的地方才炸。这个 bug 之前被其他问题掩盖，直到核心流程疏通后才暴露。

3. **LLM JSON 输出不可靠** — 即使用了 `response_format={"type": "json_object"}`，某些模型（DeepSeek）仍可能在 JSON 外围包裹 markdown 代码块。所有 `json.loads(response.content)` 都应该走健壮解析。

4. **`except: pass` 是调试黑洞** — `get_state` 异常被静默吞掉，导致输出为空时完全没有线索。关键路径的 `except` 至少应该打一条 warning。
