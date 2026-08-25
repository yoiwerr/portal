# 面试题讲解 — 你标了"？？？"的两道

> 对应面试文件里你卡住的两题：2.2（AgentState 字段）和 3.1.2（L3 事实粒度）。逐题讲透：原理 + 代码位置 + 面试怎么答。

---

## 题 2.2：`AgentState` 挂了哪些字段？哪些跨节点共享、哪些是单节点临时值？

### 一句话答案

`AgentState` 是 LangGraph 的**共享状态字典**（`TypedDict`，`core/graph.py:127`）。所有节点读它、写它，写进去的字段会在节点间**自动传递**——这是 LangGraph 和"手写 while 循环"最本质的区别：**状态是显式的、集中管理的**，不是靠局部变量传来传去。

### 完整字段清单（`graph.py:127-159`）

| 字段 | 类型 | 作用 | 生命周期 |
|---|---|---|---|
| `messages` | `Annotated[list, add_messages]` | 对话消息，**唯一用 reducer 累加**的字段 | 全程累加 |
| `module` | str | 当前 skill（router 判定后写入） | 跨节点 |
| `background` / `extra_context` | str | 用户背景 / 附加上下文 | 全程只读 |
| `expressed_dimensions` | dict | 已确认的需求维度（工作记忆） | 跨轮持久 |
| `clarify_round` | int | 追问轮数 | 跨节点递增 |
| `plan` | dict | Planner 产出（含 contract） | 全程 |
| `rag_context` | str | 被动 RAG 注入结果 | 全程 |
| `enriched_query` | str | ContextEngine 预构建的增强 query | 全程 |
| `tool_results` | list | 工具调用结果 | 执行期 |
| `output` | str | 最终输出 | 末尾 |
| `reflection_count` | int | reflect 重试次数 | 质检期 |
| `intent` | dict | router 判定的意图 | 全程 |
| `l1_raw` / `l2_summary` / `l3_facts` / `last_turn_summary` / `turn_count` | str/str/str/str/int | 三层上下文注入 | 全程 |
| `engineering_context` | str | 工程规范建议（注入执行） | 执行期 |
| `multi_agent_perspectives` / `multi_agent_synthesis` | dict/str | 三立场原始输出 / 整合结果 | multi_agent 期 |
| `checkpoint_feedback` / `checkpoint_retry_count` | str/int | checkpoint 语义修正 / 重试次数 | 质检期 |
| `completed_steps` / `execute_round` | list/str | 执行进度追踪（重试时知道做到哪） | 执行期 |
| `user_id` / `session_id` | str/str | 登录用户 / 会话，用于用量记录 | 全程 |

### 面试怎么答（关键区分）

**"跨节点共享" vs "单节点临时值"** 这个问题的陷阱是：**在 LangGraph 里几乎所有的 state 字段都是跨节点共享的**——因为 state 就是这个机制。真正有区别的是两点：

1. **`messages` 是唯一带 reducer 的字段**（`add_messages`）：写它时是**追加**，不是覆盖；其他字段写就**整体覆盖**。
2. **"临时"体现在"什么时候写入、什么时候读完就用完"**：比如 `rag_context` 在 `rag` 节点写入、planner/execute 读；`checkpoint_feedback` 只在 checkpoint→execute 重试时短暂存在。它们不是"只属于某个节点"，而是"生命周期短"。

所以标准答法：**"LangGraph 的 state 是全局共享的字典，没有严格意义的'节点私有变量'；区别在于字段的写入时机和生命周期——`messages` 用 reducer 追加，其余字段是覆盖式写入，部分字段（如 checkpoint_feedback）只在质检回环里短暂存活。"**

---

## 题 3.1.2：L3 事实在 PGVector 里以什么粒度存储？为什么"一条事实 = 一行"是后来改的？

### 一句话答案

现在（改后）是**「一条事实 = 一行」**：每条原子事实单独一个 document + 单独一个 embedding + 单独一个 id。改之前是**「一轮 = 一行」**：整轮对话提取出的所有事实用 `\n` 拼成一个 document、打成一个 embedding。

### 改之前：一轮 = 一行（粗粒度）

```python
doc_text = "\n".join(facts)                    # N 条事实拼成一段
embedding = self.embedding_fn([doc_text])[0]    # 整段只打一个向量
fact_id = md5(f"{session_id}:{turn_count}")      # 每轮一个 id
```

**问题**：
1. **检索粗**：一个向量代表"这一轮所有事实的混合语义"，召回时整轮事实一起被召回，没法精确定位到"就是这句话"。
2. **语义被稀释**：一轮里如果既有"用 React"又有"喜欢简洁"，两条事实揉进一个向量，向量语义是二者的平均，单条事实的特征被冲淡。
3. **一条事实无法独立更新/删除**：id 是"轮次"粒度，想删掉其中一条事实无从下手。

### 改之后：一条事实 = 一行（细粒度）

```python
embeddings = self.embedding_fn(facts)           # 批量，一条事实一个向量
for i, (fact, emb) in enumerate(zip(facts, embeddings)):
    fact_id = md5(f"{session_id}:{turn_count}:{i}")   # id 精确到「轮+条」
    # 每条事实独立 document + metadata(fact_index) + id
```

**好处**：
1. **检索精准**：每条事实独立向量，语义召回直接命中那条事实，而不是"这一轮"。
2. **语义纯净**：一条事实一个向量，不会被同轮其他事实稀释。
3. **可独立寻址**：id 精确到 `{session_id}:{turn}:{index}`，可单条增删。

### 面试怎么答

> "一开始是『一轮一行』——把每轮提取的所有事实拼成一个文档、打一个 embedding，id 用 `md5(session_id + turn)`。问题在于检索粒度太粗：一个向量是整轮事实的混合语义，召回时整轮一起出来，单条事实的特征被稀释、也没法独立删改。后来改成『一条事实一行』——每条事实独立 embedding、独立 id（`session_id:turn:index`），检索直接命中单条事实，语义更纯净，也支持单条增删。代价是同一轮从 1 次 embedding 变成 N 次，但 `embed_documents` 支持批量，一次调用就全算完，成本可控。"

---

## 附：这道题的"面试官追一句"预案

- **追"改完后检索 top_k 要不要调？"** → 要。原来一行 = 一轮（可能含 10 条事实），现在一行 = 1 条，同样的 top_k 召回的绝对事实数变少，所以我把 top_k 从 5 提到了 10。
- **追"老数据怎么办？"** → 表结构没变，老的一轮一行数据还能被 `split("\n")` 逻辑读回，向后兼容，无需迁移。
