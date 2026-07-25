# Context Engineering 实战指南

> 从问题诊断到代码落地，一步步理解 AI Agent 的上下文管理。

---

## 一、先理解问题：你的 Agent 为什么"健忘"？

### 1.1 一个典型的多轮对话

```
第 1 轮:  用户: "我想用 React 写个博客"
          AI:   "好的，请问你的博客需要哪些功能？"
          追问:   技术栈偏好？时间约束？交付物？

第 2 轮:  用户: "TypeScript, 一个月, 只要写文章功能就行"
          AI:   "明白了。请稍等，我来规划..."  ← 这里开始执行任务
```

**问题在哪？** 当第 2 轮 AI 开始执行任务时，它看到的 prompt 是这样的：

```
[Skill System Prompt]       ← 200 行角色定义
[Executor System Prompt]    ← 告诉它怎么用工具
目标: 完成用户请求           ← 模糊！
步骤: ["规划项目"]           ← 只有一条
用户背景: （未填写）
知识库: （无）
上下文: （无）
用户原始需求: "TypeScript, 一个月, 只要写文章功能就行"  ← 只有这一轮！
```

模型看到"TypeScript, 一个月, 只要写文章功能就行"这一句话，但它**不知道**用户上一轮说过"用 React 写博客"——因为上一轮的内容根本没被注入。

### 1.2 这就是 Context Engineering 要解决的问题

```
Prompt Engineering:    "怎么写好 prompt"（单次交互）
Context Engineering:   "怎么管理多轮对话的信息流"（多交互）
Harness Engineering:   "怎么约束模型不跑偏"（全链路控制）
```

Context Engineering 的核心问题是：**在每一轮对话中，模型能看到多少上文？看到的上文有没有被合理压缩和组织？**

---

## 二、设计思路：企业级方案全景

### 2.1 三种主流范式

当前（2025-2026）企业级 AI Agent 的上下文管理有三类主流方案：

```
┌──────────────────────────────────────────────────────────────────┐
│                        方案对比                                   │
├────────────┬─────────────────┬────────────────┬──────────────────┤
│            │  滑动窗口        │  摘要压缩       │  混合分层          │
│            │  Sliding Window │  Summarization │  Hybrid Layered   │
├────────────┼─────────────────┼────────────────┼──────────────────┤
│  核心思想   │ 只保留最近 N 条   │ 把旧消息压缩成  │ 滑动窗口 (原始)    │
│            │ 消息，丢弃旧的    │ 一段摘要文本     │ ＋摘要 (压缩)      │
│            │                 │                │ ＋向量检索 (召回)   │
├────────────┼─────────────────┼────────────────┼──────────────────┤
│  LLM 调用   │ 零额外调用        │ 每次压缩一次     │ 按需 (摘要 + 检索) │
│  成本       │                 │                │                  │
├────────────┼─────────────────┼────────────────┼──────────────────┤
│  信息保真   │ 低 — 旧信息永久   │ 中 — 有损但保留  │ 高 — 原始 + 摘要   │
│            │ 丢失             │ 关键信息        │ + 语义检索互补     │
├────────────┼─────────────────┼────────────────┼──────────────────┤
│  适用场景   │ 短对话 / 客服机器人│ 长对话 / 工作助手│ 企业 Agent /      │
│            │                 │                │ 多会话 / 自主任务  │
├────────────┼─────────────────┼────────────────┼──────────────────┤
│  代表实践   │ AWS Strands,    │ GoDaddy,       │ Oracle, LangMem,  │
│            │ OpenSearch      │ JumpCloud      │ Cursor           │
└────────────┴─────────────────┴────────────────┴──────────────────┘
```

你项目目前的方案（按轮数切换 + 长对话 LLM 压缩）属于**混合分层**的初级阶段。

---

### 2.2 滑动窗口：最简单也最容易被误解

#### 怎么工作

维护一个固定大小的窗口（比如最近 40 条消息或最近 6 轮对话），窗口之外的全部丢弃。

```
对话进行中:
  消息:  [1][2][3][4][5][6][7][8][9][10][11][12]
                                              ↑ 当前
  窗口=6:
         ───────────丢弃───────────  ──保留──
         [1][2][3][4][5][6]         [7][8][9][10][11][12]

  下一轮:
         ──────────────丢弃───────────  ──保留──
         [1][2][3][4][5][6][7]         [8][9][10][11][12][13]
```

**关键参数：**
- `window_size`: 保留多少条消息（通常是消息数而非轮数，因为每轮 token 数不同）
- `strategy`: `"last"`（保留末尾）/ `"first"`（保留开头）/ 自定义
- `start_on`: `"human"`（从用户消息开始计数，保证窗口开头是完整的问答对）

#### 代码长什么样

```python
from langchain_core.messages import trim_messages

def call_model(state):
    # 每次调模型前，只保留最近 6 条消息（约 3 轮对话）
    selected = trim_messages(
        state["messages"],
        token_counter=len,          # 简单计条数；生产环境用 token counter
        max_tokens=6,               # 窗口大小
        strategy="last",            # 保留末尾
        start_on="human",           # 从用户消息开始，避免切碎问答对
        include_system=True,        # 系统 prompt 不参与计数
    )
    response = model.invoke(selected)
    return {"messages": [response]}
```

AWS Strands 框架的默认配置是 **window_size=40 条消息**，在窗口占用达到 70% 时触发预压缩。OpenSearch 用的是 **6 条最近消息**，在累计超过 20 条后激活。

#### 优劣

| ✅ 优点 | ❌ 缺点 |
|---------|---------|
| 零额外 LLM 调用，零延迟 | 旧信息永久丢失 |
| 实现极简单 | 第 1 轮说的需求到第 7 轮已经不在了 |
| Token 消耗完全可控 | 不适合需要跨轮次记忆的任务 |

**一句话：滑动窗口保证当前对话流畅，但不保证记住。**

---

### 2.3 你的想法：始终摘要 + 压缩率控制

> "除了第一次，每次都把上文整理摘要，摘要程度设为一个百分数，每次新对话都对上文处理。"

这个想法在企业实践中叫做 **Running Summary（滚动摘要）**，LangMem 和 GoDaddy 都在用。核心区别在于：**不按轮数阈值触发，而是按 token 预算触发——每次对话都更新摘要。**

#### 怎么工作

```
第 1 轮:
  用户: "我想用 React 写博客"
  AI: "好的，请问技术栈偏好？"
  → 只有 1 轮，不需要摘要（或摘要为空）

第 2 轮:
  用户: "TypeScript，一个月"
  输入给模型:
    [摘要: （空）]                   ← 第一次有上文，生成摘要
    [最近消息: "TypeScript，一个月"]   ← 当前轮原始内容
  AI 回复后:
    自动更新摘要 → "用户想用 React + TypeScript 写博客，时间一个月"

第 3 轮:
  用户: "只要写文章功能"
  输入给模型:
    [摘要: "用户想用 React + TypeScript 写博客，时间一个月"]  ← 上轮生成的摘要
    [最近消息: "只要写文章功能"]                              ← 当前轮
  AI 回复后:
    更新摘要 → "用户想用 React + TypeScript 写博客，时间一个月，只需要写文章功能"

第 N 轮: 一样的模式 — 每次对话后更新摘要，下次对话前注入摘要
```

**关键的"压缩率"参数（你的百分数想法）：**

```
compression_ratio = 0.3  意思是：原文 1000 字符 → 摘要 300 字符

实际使用时通常是 token 预算制:
  max_summary_tokens = 256    摘要最多 256 token
  max_context_tokens = 4096   总上下文预算（摘要 + 最近消息 + 系统 prompt）
```

#### 代码实现

```python
class RunningSummaryEngine:
    """每次对话后更新摘要，每次对话前注入摘要。"""

    def __init__(self, model, max_summary_tokens=256, keep_recent_messages=4):
        self.model = model
        self.max_summary_tokens = max_summary_tokens   # 摘要 token 上限
        self.keep_recent = keep_recent_messages         # 保留最近 N 条原始消息
        self._current_summary = ""                       # 滚动摘要

    async def build_context(self, messages: list) -> dict:
        """对话前：组装上下文。"""
        if len(messages) <= 2:  # 第一轮（只有 1 条 user 消息 + 可能 1 条 system）
            return {
                "summary": "",
                "recent_messages": messages,
            }

        # 最近 N 条保留原文
        recent = messages[-self.keep_recent:] if len(messages) > self.keep_recent else messages

        return {
            "summary": self._current_summary,       # 上轮生成的摘要
            "recent_messages": recent,              # 最近原始消息
        }

    async def update_summary(self, messages: list):
        """对话后：更新摘要。把最新一轮的信息合并进去。"""
        if len(messages) < 4:  # 至少一轮完整对话（user + assistant）
            return

        # 构建"旧摘要 + 新消息"的合并 prompt
        new_turns = self._format_recent_turns(messages, last_n=1)

        prompt = f"""将以下对话历史合并到已有摘要中，生成新的滚动摘要。

## 已有摘要
{self._current_summary or "（这是对话的开始）"}

## 最新一轮对话
{new_turns}

## 要求
- 严格控制在 {self.max_summary_tokens} token 以内
- 保留：用户的核心需求、已做出的决策、关键约束条件
- 丢弃：追问的来回细节、问候语、过渡语句
- 使用第三人称：'用户想要...'、'已确定...'

## 新的滚动摘要（直接输出，不要前缀）"""

        response = await self.model.ainvoke([HumanMessage(content=prompt)])
        self._current_summary = response.content.strip()

    def _format_recent_turns(self, messages, last_n=1):
        # 取最近 N 轮的内容
        ...
```

#### 和当前方案的关键区别

| | 当前方案 (按轮数阈值切换) | 始终摘要 + 压缩率 |
|---|---|---|
| **触发条件** | ≥ 8 轮才触发 LLM 压缩 | 每次对话都更新摘要 |
| **第 2-7 轮** | 注入完整历史原文 | 注入摘要（短但覆盖全） |
| **Token 消耗** | 前 7 轮越来越高，第 8 轮骤降 | 每轮稳定（摘要固定大小） |
| **信息保真** | 前 7 轮完美，第 8 轮后降级 | 从第 2 轮起就是有损的 |
| **延迟** | 前 7 轮无额外延迟 | 每轮都有一次摘要 LLM 调用 |
| **适合** | 短任务为主，偶尔长对话 | 长对话为主，需要跨轮记忆 |

---

### 2.4 企业级最优解：混合分层

Oracle、GoDaddy、AWS 的共识是**单一策略不够用**。生产系统用分层架构：

```
┌─────────────────────────────────────────────────────────┐
│              Memory Manager（策略层）                     │
│       决定: 存什么、取什么、压什么、丢什么                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  L1 原始窗口（滑动窗口）                                   │
│    最近 3-5 轮完整原文，保证当前对话流畅                      │
│                                                         │
│  L2 滚动摘要（你的想法）                                   │
│    所有旧消息的压缩版，每次对话后增量更新                      │
│                                                         │
│  L3 向量检索（语义召回）                                   │
│    从历史会话中检索相关的旧信息，补充 L2 遗漏的细节             │
│                                                         │
│  L4 结构化记忆（事实/决策/偏好）                             │
│    从对话中提取的持久化事实，跨会话可用                       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**优先级（Oracle 的推荐）：**
1. 当前用户消息 🔴
2. 最近对话原文 (L1) 🟡
3. 滚动摘要 (L2) 🟡
4. 结构化的决策/偏好 (L4) 🟢
5. 向量召回的旧信息 (L3) 🟢
6. 已归档的历史摘要 ⚪

GoDaddy 的关键创新是**增量合并 + 引用溯源**：

```
轮次:  1-5        6-10        11-15       16-20
        ↓           ↓           ↓           ↓
    [摘要₁] ──→ [合并] ──→ [摘要₂] ──→ [合并] ──→ [摘要₃] ──→ ...

每次合并:
  旧摘要 + 新窗口的对话 → LLM → 新摘要（覆盖旧摘要）
  新摘要中的每条声明必须能追溯到原文（防止幻觉滚雪球）
```

---

### 2.5 🔴🟡🟢⚪ — Prompt 内的注意力分层

无论选哪种方案，最终注入给模型的上下文都需要分层标记。模型对**位置靠前**和**有视觉标记**的内容天然分配更多注意力：

```
🔴 当前任务 / 前情提要          ← 最高优先级，放 prompt 最前面
   "用户想要 React + TypeScript 博客，已确定: 技术栈、时间、功能范围"

🟡 上一轮 / 滚动摘要             ← 中等优先级
   "上轮确定了只做文章功能，不需要评论系统"

🟢 参考资料 / 对话历史            ← 按需参考，不用全读
   最近 3 轮完整记录 或 RAG 检索结果

⚪ 原始上下文                    ← 最低优先级，仅用于理解意图
   用户原始消息 + 已确认的维度信息
```

这个分层和前面的存储分层（L1-L4）是**垂直和水平**的关系：
- 存储分层（L1-L4）= **存什么**、什么粒度
- 注意力分层（🔴🟡🟢⚪）= **怎么呈现**给模型

---

### 2.6 方案选择决策树

```
你的对话通常是多长？
  │
  ├─ 5 轮以内 → 滑动窗口就行
  │
  ├─ 5-15 轮 → 始终摘要（你的想法）+ 保留最近 3 轮原文
  │             推荐: compression_ratio = 0.3 (即 max_summary_tokens=256)
  │
  ├─ 15-30 轮 → 混合分层
  │             L1 最近 3 轮原文 + L2 滚动摘要 + L3 向量检索
  │
  └─ 30 轮以上 / 多会话 → 完整五层
                          L1-L4 + Memory Manager + GoDaddy 式引用溯源
```

你当前的项目版本（按轮数切换），往前一步最适合进化到**二级混合**：

```
改造方向:
  现在:   ≤2轮无历史 / 3-7轮完整 / ≥8轮压缩
  目标:   从第 2 轮起始终注入摘要 + 保留最近 3 轮原文
         摘要大小 = 对话总 token × compression_ratio (默认 0.3)
         
改动:
  ContextEngine 加 max_summary_tokens 参数
  _compress() 改为 update_running_summary() — 增量而非每次重建
  去掉 turn_count >= 8 的硬阈值
```

## 三、代码实现：三个文件怎么协作

### 3.1 整体数据流

```
┌─────────────────────────────────────────────────────────┐
│                      agent.py                           │
│                                                         │
│  用户消息到达                                             │
│    │                                                    │
│    ▼                                                    │
│  _build_initial_state()                                 │
│    │                                                    │
│    ├─→ ContextEngine.build(session_store, session_id)   │
│    │     │                                              │
│    │     ├─ 读 SQLite 对话历史                            │
│    │     ├─ _count_turns()        → 统计轮数              │
│    │     ├─ _extract_last_turn()  → 上轮规则摘要           │
│    │     ├─ 轮数 ≥ 8? _compress() → LLM 压缩前情提要       │
│    │     ├─ _format_recent_history() → 格式化历史文本       │
│    │     └─ _build_enriched_query()  → RAG 增强 query     │
│    │     │                                              │
│    │     └→ 返回 ConversationContext:                    │
│    │          .turn_count = 5                           │
│    │          .last_turn_summary = "👤 用户: ...\n🤖 AI: ..." │
│    │          .history_text = "### 第3轮\n..."           │
│    │          .conversation_summary = "" (未达 8 轮)      │
│    │          .enriched_query = "关键词 关键词 原始消息"    │
│    │                                                    │
│    ▼                                                    │
│  initial_state = {                                      │
│    "messages": [...],                                   │
│    "conversation_summary": "",                          │
│    "last_turn_summary": "👤 用户: React 博客\n🤖 AI: 追问了技术栈", │
│    "turn_count": 5,                                     │
│    "history_text": "### 第3轮\n...\n### 第4轮\n...\n### 第5轮\n...", │
│    "enriched_query": "工作安排 React 博客 TypeScript...",│
│    ...                                                  │
│  }                                                      │
│    │                                                    │
│    ▼                                                    │
│  graph.ainvoke(initial_state)                           │
│    │                                                    │
└────┼────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│                      graph.py                           │
│                                                         │
│  START → router → enrich → rag → planner → executor ... │
│                      │         │          │             │
│                      │         │          │             │
│    enrich_query_node:│         │          │             │
│      从 state 取出 enriched_query（已在 agent.py 预构建）  │
│      透传给 rag_retrieve_node                            │
│                                                         │
│    planner_node:                                        │
│      ┌──────────────────────────────────────┐           │
│      │ 从 state 取 context 字段:             │           │
│      │                                       │           │
│      │ conversation_summary = ""             │           │
│      │ last_turn_summary = "👤 ... 🤖 ..."   │           │
│      │ history_text = "### 第3轮\n..."       │           │
│      │ turn_count = 5                        │           │
│      │                                       │           │
│      │ ▼ 组装 prompt:                        │           │
│      │                                       │           │
│      │ [PLANNER SYSTEM PROMPT]               │           │
│      │ ## 当前模块: prompt_refiner            │           │
│      │ ## 对话轮数: 第 5 轮                   │           │
│      │                                       │           │
│      │ ## 🟡 上一轮对话                       │  ← 注入！  │
│      │ 👤 用户: React 博客                    │           │
│      │ 🤖 AI: 追问了技术栈...                 │           │
│      │                                       │           │
│      │ ## 🟢 对话历史                         │  ← 注入！  │
│      │ ### 第 3 轮                            │           │
│      │ 用户: xxx | AI: xxx                    │           │
│      │ ### 第 4 轮 ...                       │           │
│      │ ### 第 5 轮 ...                       │           │
│      │                                       │           │
│      │ ## 用户最新消息                         │           │
│      │ "TypeScript, 一个月, 只要写文章功能就行"  │           │
│      └──────────────────────────────────────┘           │
│                                                         │
│    execute_node: 同 planner，注入 exec_context_block      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 3.2 context_engine.py 核心逻辑

```python
class ContextEngine:
    MAX_HISTORY_TURNS_RAW = 3       # 短对话保留 3 轮完整历史
    COMPRESSION_THRESHOLD = 8       # 超过 8 轮触发 LLM 压缩
    SUMMARY_MAX_CHARS = 500         # 压缩摘要最大长度

    async def build(self, session_store, session_id, current_message, ...):
        ctx = ConversationContext()              # 空数据包

        messages = session_store.get_conversation(session_id)  # 从 SQLite 读
        
        ctx.turn_count = _count_turns(messages)  # 统计 user 消息数
        ctx.last_turn_summary = _extract_last_turn(messages)   # 规则提取

        if ctx.turn_count >= 8:
            ctx.conversation_summary = await self._compress(messages)  # LLM 压缩
            ctx.history_text = _format_recent_history(messages, max_turns=1)
        elif ctx.turn_count >= 2:
            ctx.history_text = _format_recent_history(messages, max_turns=3)
        
        ctx.enriched_query = _build_enriched_query(...)  # RAG 增强 query
        return ctx
```

### 3.3 AgentState 新增的 4 个字段

```python
class AgentState(TypedDict):
    # ... 原有字段
    conversation_summary: str     # LLM 压缩的「前情提要」(≥8轮时有值)
    last_turn_summary: str        # 规则提取的上轮摘要 (格式: "👤 用户: xxx\n🤖 AI: xxx")
    turn_count: int               # 当前对话轮数
    history_text: str             # 最近 N 轮完整对话历史 (Markdown 格式)
```

这些字段在 `agent.py` 的 `_build_initial_state()` 中被填充，在 `graph.py` 的 `planner_node` 和 `execute_node` 中被消费。

### 3.4 三种摘要方式对比

| 方式 | 谁做 | 何时触发 | 特点 |
|------|------|---------|------|
| **上轮摘要** `_extract_last_turn()` | 规则引擎 | 每轮自动 | 零延迟，取最后一对 user→assistant，200 字符截断 |
| **对话压缩** `_compress()` | LLM | ≥8 轮 | 额外 API 调用，输出 ~500 字符，高质量 |
| **会话摘要** `_summarize_on_complete()` | LLM | 会话结束 | 写入 PGVector 供跨会话记忆检索，不阻塞主流程 |

三者的区别：
- 上轮摘要 = "这一轮之前发生了什么"（即时上下文）
- 对话压缩 = "整个对话的核心脉络"（长对话压缩）
- 会话摘要 = "这次对话值得记住什么"（持久化记忆，下次对话可用）

---

## 四、为什么这样设计？

### 4.1 "摘要"和"压缩"不是一回事

| | 摘要 (summary) | 压缩 (compression) |
|---|---|---|
| 目的 | 提取关键信息 | 保留尽可能多的细节 |
| 输出 | "用户想要 React 博客，已确定技术栈" | 同上但更详细，包括对话的转折点 |
| 触发 | 会话结束时 | 对话过长时（≥8 轮） |
| 持久化 | 存入 PGVector 供跨会话检索 | 仅当轮使用，不存储 |

ContextEngine 里的 `_compress()` 实际上是摘要——因为 LLM 不可能无损压缩，它做的就是提取关键信息。命名上叫 compress 是为了和 memory 模块的 summarize 区分开。

### 4.2 为什么压缩阈值是 8 轮？

8 轮对话 ≈ 3K-4K token 的纯历史文本。加上：
- 系统 prompt (~1K)
- RAG 检索结果 (~1K)
- 维度定义 + 追问模板 (~500)
- 用户的当前消息

总共约 6K token——这在大多数模型的注意力舒适区内。超过 8 轮后，历史本身可能达到 6K+，总 prompt 接近 10K，模型开始"略读"中间段落。所以 8 轮是一个合理的压缩触发点。

### 4.3 为什么不在 graph 里做而要在 agent.py 里做？

graph 节点是无状态的（只能读 AgentState），但上下文构建需要**异步读取数据库**（SQLite 历史）。把数据库访问放在 graph 节点里会让图变复杂，而且每个节点都可能需要访问数据库。

更好的做法是：**在 graph 执行前一次性构建上下文，作为 initial_state 传入**。这样图节点只需要从 state 取数据，不需要关心数据是怎么来的。

### 4.4 和 Memory 系统的关系

```
ContextEngine (L1 — 当前对话内)
    │
    ├─ 上轮摘要          ← 规则引擎，每轮自动
    ├─ 对话历史注入      ← 最近 N 轮完整文本
    └─ 长对话压缩        ← LLM 压缩前情提要
    │
    ▼ 会话结束时
Memory System (L2+L3 — 跨会话)
    │
    ├─ SessionMemory     ← LLM 摘要存入 PGVector
    └─ UserProfile       ← 用户画像更新
```

ContextEngine 管"这一轮模型能看到什么"，Memory 管"下次对话模型能回忆起什么"。两者互补。

---

## 五、如何自己加一个新的上下文能力？

假设你想加一个"自动检测用户情绪"并注入到上下文：

### 5.1 在 ConversationContext 加字段

```python
# context_engine.py
class ConversationContext:
    __slots__ = (
        ...existing fields...,
        "user_sentiment",  # 新增
    )
    
    def __init__(self):
        ...
        self.user_sentiment: str = ""
```

### 5.2 在 ContextEngine.build() 中计算

```python
async def build(self, ...):
    ...
    # 新增: 检测用户情绪
    ctx.user_sentiment = await self._detect_sentiment(current_message)
    return ctx

async def _detect_sentiment(self, message: str) -> str:
    """用 LLM 一次性判断用户情绪（焦急/满意/困惑/中性）。"""
    if not self.model:
        return ""
    response = await self.model.ainvoke([
        SystemMessage(content="判断用户情绪，只输出一个词：焦急/满意/困惑/中性"),
        HumanMessage(content=message),
    ])
    return response.content.strip()
```

### 5.3 在 AgentState 加字段

```python
# graph.py
class AgentState(TypedDict):
    ...
    user_sentiment: str   # 新增
```

### 5.4 在 agent.py 传递

```python
# agent.py _build_initial_state()
return {
    ...
    "user_sentiment": ctx.user_sentiment,  # 新增
}
```

### 5.5 在 graph 节点中消费

```python
# graph.py planner_node
sentiment = state.get("user_sentiment", "")
if sentiment == "焦急":
    context_block += "⚠️ 用户当前显得焦急，请尽量简洁直接地回答。\n"
```

---

## 六、常见问题

### Q: 压缩摘要太长怎么办？

`_compress()` 的 prompt 里写了"严格控制在 500 字符以内"，但 LLM 不一定听话。所以代码里有一个安全截断：

```python
if len(summary) > self.SUMMARY_MAX_CHARS * 2:
    summary = summary[:self.SUMMARY_MAX_CHARS] + "..."
```

容忍到 2 倍（1000 字符），超出才硬截断——给 LLM 一些容错空间。

### Q: 如果压缩失败怎么办？

`_compress()` 返回空字符串 `""`。这意味着长对话时如果 LLM 挂了，模型会丢失历史——但不会报错，只是这轮没有前情提要。这是一个降级策略（graceful degradation）。

### Q: enriched_query 和原来的 enrich_query_node 有什么区别？

原来 `enrich_query_node` 在 graph 内部做拼接——它只能从 AgentState 取数据（intent + dimensions），不能访问数据库。现在 `ContextEngine._build_enriched_query()` 在 graph 执行前做，可以访问更多信息（包括对话历史摘要）。

`enrich_query_node` 现在只是一个透传兜底——如果 ContextEngine 没构建 enriched_query（比如 session_store 不可用），它就用原始消息兜底。

### Q: context_engine 和 memory 都在 agent.py 初始化，它们是同一个东西吗？

不是。它们共用同一个 model + vector_store，但职责完全不同：

```
ContextEngine → 管"这一轮"
  - 读 SQLite 历史
  - 不写任何数据
  - 每次对话都运行
  - 输出注入到 prompt

Memory System → 管"跨会话"
  - 读/写 PGVector
  - 持久化摘要 + 用户画像
  - 会话结束才运行
  - 输出注入到下次对话的 initial_state
```

---

## 七、相关文件索引

| 文件 | 角色 |
|------|------|
| `core/context_engine.py` | **核心** — 所有上下文构建逻辑 |
| `core/graph.py` | 消费端 — `AgentState` 定义 + `planner_node`/`execute_node` 注入 |
| `core/agent.py` | 编排端 — 创建 `ContextEngine` + `_build_initial_state()` 调用 |
| `services/session_store.py` | 数据源 — SQLite 对话历史 |
| `memory/session_memory.py` | L2 记忆 — 跨会话摘要（与 ContextEngine 互补） |
| `boundary.md` | 规范 — Context Engineering 的要求和待办 |

---

## 八、下一步可以做的

1. **压缩质量评估** — 对比 LLM 压缩 vs 规则摘要的效果差异
2. **阈值调优** — 统计实际对话的轮数分布，调整 3/8 这两个阈值
3. **主题切换检测** — 用户突然换话题时，自动重置上下文（不再注入旧历史）
4. **增量压缩** — 不每次都从第 1 轮开始压缩，而是"上次压缩结果 + 新增轮次"
