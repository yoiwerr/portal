# 工具防循环指南 — Agent 为什么打转、怎么拦住它

> 从「为什么 Agent 会跑偏」到「每一步怎么拦」，逐步理解工具调用的循环检测与预防。

---

## 一、先看问题：Agent 在什么情况下会打转？

### 1.1 三类典型死循环

```
类型 A: 重复调用 (Repeat Loop)
  search_web("React Suspense") → 结果不够具体
  search_web("React Suspense 用法") → 还是不够
  search_web("React Suspense how to use") → 还不够...
  ↑ 同一个工具，换汤不换药的参数，期待不同结果
  ↑ 这是 Agent 最常见的问题 — 它以为"再搜一次就能找到"

类型 B: 摇摆循环 (Ping-Pong Loop)
  search_web("React Suspense") → 结果偏向 React 官方
  search_web("React Suspense 社区方案") → 结果偏向社区
  search_web("React Suspense 官方") → 又回到官方...
  ↑ Agent 在两个方案之间来回摇摆，无法做出选择
  ↑ 根本原因: 它在"收集信息"和"做决策"之间没有清晰的切换点

类型 C: 工具链陷阱 (Tool Chain Trap)
  search_web("A") → 返回提到了 B
  search_web("B") → 返回提到了 C
  search_web("C") → 返回提到了 A...
  ↑ 每次搜索都打开一个新方向，永远在探索，永远不输出
  ↑ 根本原因: 没有"够了就停下来"的判断标准
```

### 1.2 不是循环，但也是问题

```
类型 D: 过早放弃 (Early Termination)
  用户: "帮我对比 React 和 Vue 的性能"
  Agent: search_web("React performance") → 拿到结果 1
  Agent: 直接输出对比报告（只搜了一次！）
  ↑ 对比任务需要搜至少两次，但 Agent 偷懒了

类型 E: 重复 delegate (Delegate Duplication)
  主 Agent: delegate_task("调研 React 服务端渲染方案")
  子 Agent 返回了报告
  主 Agent: delegate_task("调研 React SSR 方案")  ← 几乎一样！
  ↑ 浪费了 60s 和一次完整的子 Agent 调用
```

---

## 二、设计思路：三层防线

```
┌──────────────────────────────────────────────────────────────────┐
│                        三层防线                                   │
├────────────┬─────────────────┬────────────────┬──────────────────┤
│            │  第 1 层: Prompt  │  第 2 层: 计数  │  第 3 层: 模式    │
│            │  告诉模型别循环   │  硬限制打断     │  检测（智能）     │
├────────────┼─────────────────┼────────────────┼──────────────────┤
│  手段       │ System Prompt    │ 计数器 + 阈值   │ 去重指纹 + 相似度  │
│            │ 中明确约束        │ + 强制终止      │ + 摇摆检测        │
├────────────┼─────────────────┼────────────────┼──────────────────┤
│  成本       │ 零（已内置于      │ 低（几个变量）   │ 中（需维护追踪状态）│
│            │ Prompt 中）       │                │                  │
├────────────┼─────────────────┼────────────────┼──────────────────┤
│  能拦住     │ 守规矩的模型      │ 超出上限的循环   │ 换参数重试 /       │
│            │                 │                │ 来回摇摆 / 重复    │
│            │                 │                │ delegate          │
├────────────┼─────────────────┼────────────────┼──────────────────┤
│  拦不住     │ 不听话的模型      │ 上限内的循环    │ —                 │
│            │ (会无视 prompt)   │ (3 次重复)     │                  │
└────────────┴─────────────────┴────────────────┴──────────────────┘
```

三层从软到硬、从便宜到贵逐层递进。第 1 层拦住大部分，第 2 层兜底，第 3 层做精细拦截。

---

## 三、第 1 层：Prompt 约束 — 告诉模型什么时候该停

### 3.1 原则

Prompt 中对循环的约束必须是**正向指令**（告诉它该做什么），而非否定指令（告诉它别做什么）。模型对否定指令天然不敏感。

```
❌ 差: "不要重复调用同一个工具"           ← 否定指令
❌ 差: "禁止搜索超过 3 次"                ← 否定指令
✅ 好: "搜索 3 次后，即使结果不完美也直接输出"  ← 正向指令 + 明确退出条件
✅ 好: "如果连续 2 次搜索结果相似，停止搜索"    ← 正向指令 + 触发条件
```

### 3.2 当前 Executor Prompt 中已有的约束

```python
# prompts/system_prompts.py — EXECUTOR_SYSTEM_PROMPT

## 工具使用原则
- 工具调用最多 10 轮，超过后必须给出当前最佳结果   ← ✅ 有明确退出条件
```

### 3.3 需要补的约束

```python
# 应添加:
## 停止搜索的条件
- 如果连续 2 次搜索返回相似结果，停止搜索，基于已有信息输出
- 如果需要的信息已经在之前的搜索结果中，不要重复搜索
- 禁止对同一查询换语言/换措辞重复搜索（如 "React Suspense" → "React Suspense 用法" → "React Suspense how to use"）

## 决策与行动
- 收集够 3 条来源后，开始综合分析而非继续搜索
- 在工具调用前先问自己: "这次搜索能带来之前没有的新信息吗？"
```

这些改动量很小（~10 行加到现有 Prompt），但能显著减少重复搜索。

---

## 四、第 2 层：硬计数器 — 绝对上限

### 4.1 当前已有的计数器

```python
# core/graph.py
DEFAULT_MAX_TOOL_ROUNDS = 10      # ReAct 总轮数上限
MAX_REFLECTION_RETRIES = 2        # Reflector 拒绝重试上限
MAX_CLARIFY_ROUNDS = 5            # 追问轮数上限
MAX_CHECKPOINT_RETRIES = 1        # Checkpoint 修正重试上限

# tools/delegate.py
DELEGATE_SYSTEM_PROMPT             # 子 Agent 最多 8 轮
asyncio.wait_for(..., timeout=60)  # 子 Agent 60s 超时
```

这些是**全局上限**。它们的优点是零实现成本，缺点是粒度太粗——Agent 在第 10 轮被强制打断，但前 9 轮可能全是重复调用。

### 4.2 缺失的计数器：工具级上限

```
全局上限 (已有):
  ReAct 总轮数 ≤ 10           ← 兜底

工具级上限 (缺失):
  search_web 调用 ≤ 5          ← 搜索不是越多越好
  fetch_url 调用 ≤ 3           ← 读网页很慢，限制更严
  delegate_task 调用 ≤ 1       ← 同一任务不能重复委托
  python_exec 调用 ≤ 3         ← 代码执行消耗 token 多
```

**实现方案：**

```python
# 在 AgentState 中追踪工具调用
class AgentState(TypedDict):
    ...
    tool_call_counts: dict   # {"search_web": 3, "fetch_url": 1, ...}

# 在 execute_node 中每次 tool call 后检查
TOOL_CALL_LIMITS = {
    "search_web": 5,
    "fetch_url": 3,
    "python_exec": 3,
    "delegate_task": 1,
}
```

---

## 五、第 3 层：模式检测 — 识别循环，不止计数

这一层是智能的核心。不是「到了上限就停」，而是「识别出你在重复就停」。

### 5.1 去重指纹 (Deduplication Fingerprint)

**思想**：即使两次工具调用的参数不完全相同，如果它们的「意图」相同，就应该视为重复。

```python
def make_tool_fingerprint(tool_name: str, tool_args: dict) -> str:
    """
    生成工具调用的去重指纹。

    例:
      search_web("React Suspense")        → "search_web:react_suspense"
      search_web("React Suspense 怎么用")  → "search_web:react_suspense"  ← 相同！
      fetch_url("https://react.dev")      → "fetch_url:react_dev"
    """
    import re

    # 1. 提取核心信息
    if tool_name in ("search_knowledge_base", "search_web"):
        query = tool_args.get("query", "")
        # 2. 归一化: 去停用词 + 去标点 + 小写 + 排序
        words = re.findall(r'\w+', query.lower())
        stopwords = {"how", "to", "what", "is", "the", "a", "an", "in", "of", "for",
                     "and", "or", "怎么", "如何", "是什么", "为什么", "的", "了", "吗"}
        key_words = sorted(set(w for w in words if w not in stopwords and len(w) >= 2))
        core = "_".join(key_words[:5])  # 最多取 5 个核心词
        return f"{tool_name}:{core}"

    elif tool_name == "fetch_url":
        url = tool_args.get("url", "")
        domain = re.search(r'https?://([^/]+)', url)
        return f"fetch_url:{domain.group(1) if domain else url[:30]}"

    elif tool_name == "delegate_task":
        task = tool_args.get("task_description", "")
        # 和 search 用同一套归一化
        words = re.findall(r'\w+', task.lower())
        stopwords = {"how", "to", "what", "is", "the", "a", "an", "in", "of", "for",
                     "and", "or", "怎么", "如何", "是什么", "为什么", "的", "了", "吗"}
        key_words = sorted(set(w for w in words if w not in stopwords and len(w) >= 2))
        core = "_".join(key_words[:8])
        return f"delegate_task:{core}"

    else:
        # 默认: tool名 + 核心参数
        arg_str = str(sorted(tool_args.values())[:3])
        return f"{tool_name}:{arg_str[:60]}"


def detect_repeat_calls(tool_history: list[dict], threshold: int = 2) -> bool:
    """
    检测同一个指纹是否重复调用超过阈值。

    例:
      tool_history = [
        {"name": "search_web", "args": {"query": "React Suspense"}},
        {"name": "search_web", "args": {"query": "React Suspense 怎么用"}},
        {"name": "search_web", "args": {"query": "React Suspense 用法详解"}},
      ]
      → 三者的指纹都是 "search_web:react_suspense" → 触发重复检测！
    """
    fingerprints = [make_tool_fingerprint(h["name"], h["args"]) for h in tool_history]
    from collections import Counter
    counts = Counter(fingerprints)
    return any(c > threshold for c in counts.values())
```

### 5.2 结果相似度检测 (Output Similarity)

**思想**：即使参数不同，如果工具返回的结果高度相似，也应该停止。

```python
def detect_similar_outputs(outputs: list[str], threshold: float = 0.8) -> bool:
    """
    检测最近 N 次工具调用返回的结果是否高度相似。

    用简单的 Jaccard 相似度（单词重叠率），不需要 embedding。
    """
    import re

    if len(outputs) < 2:
        return False

    # 取最近两次
    a, b = outputs[-2], outputs[-1]

    # 分词
    words_a = set(re.findall(r'\w+', a.lower()))
    words_b = set(re.findall(r'\w+', b.lower()))

    if not words_a or not words_b:
        return False

    intersection = words_a & words_b
    union = words_a | words_b
    jaccard = len(intersection) / len(union)

    return jaccard > threshold
```

### 5.3 摇摆检测 (Ping-Pong Detection)

**思想**：Agent 在两个工具/查询之间来回切换。

```python
def detect_ping_pong(tool_history: list[dict], window: int = 4) -> bool:
    """
    检测最近 window 次调用中是否存在 "A → B → A → B" 的摇摆模式。

    例:
      search_web("React 官方") → search_web("React 社区") →
      search_web("React 官方") → search_web("React 社区")
      ↑ 在两个查询之间来回摇摆
    """
    if len(tool_history) < window:
        return False

    recent = tool_history[-window:]
    fingerprints = [make_tool_fingerprint(h["name"], h["args"]) for h in recent]

    # 检查是否呈现 ABAB 模式
    return (
        len(set(fingerprints)) == 2 and          # 只有两种指纹
        fingerprints[0] == fingerprints[2] and   # A 出现了两次
        fingerprints[1] == fingerprints[3]        # B 出现了两次
    )
```

### 5.4 信息增益检查 (Information Gain)

**思想**：每次搜索应该带来新信息。如果没有，就该停了。

不依赖 LLM（太贵、太慢）——用一个简单规则：新搜索的结果关键词和之前所有搜索结果的关键词重叠了多少？

```python
def compute_information_gain(
    new_output: str,
    previous_outputs: list[str],
    min_gain: float = 0.15
) -> float:
    """
    计算新搜索带来了多少新信息。

    返回值: 0.0 ~ 1.0。0.0 = 完全重复，1.0 = 全新信息。
    低于 min_gain → 建议停止搜索。
    """
    import re

    def extract_keywords(text):
        words = re.findall(r'[A-Za-z一-鿿]{2,}', text.lower())
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "in", "of", "for",
                     "to", "and", "or", "的", "了", "是", "在", "有", "和", "与", "或",
                     "不", "也", "都", "就", "还", "要", "会", "能", "可以"}
        return set(w for w in words if w not in stopwords)

    new_kw = extract_keywords(new_output)
    if not new_kw:
        return 0.0

    # 合并之前所有结果的关键词
    prev_kw = set()
    for output in previous_outputs:
        prev_kw |= extract_keywords(output)

    if not prev_kw:
        return 1.0  # 第一次搜索，全是新信息

    # 新关键词中有多少是之前没见过的
    new_info = new_kw - prev_kw
    gain = len(new_info) / len(new_kw)
    return gain
```

---

## 六、集成到 Agent 循环中

### 6.1 在 LangGraph 中的放置位置

```
execute_node (ReAct Agent)
    │
    ├─ tool call 发生
    │     │
    │     ├─ 1. 生成指纹 → 去重检测
    │     │   如果重复 > 2 次 → 注入 "你已经搜索过这个话题，请基于已有信息直接输出"
    │     │
    │     ├─ 2. 工具级计数器 + 1
    │     │   如果超过工具上限 → 从工具列表中暂时移除该工具
    │     │
    │     └─ 3. 结果相似度检测
    │     │   如果和上次结果高度重叠 → 注入 "搜索结果和上次相似，建议停止搜索"
    │     │
    │     └─ 继续 ReAct 循环
    │
    └─ 超过全局 10 轮 → 强制进入输出阶段
```

### 6.2 实现结构

```python
# tools/loop_guard.py — 新建文件

from dataclasses import dataclass, field
from typing import Optional

@dataclass
class LoopGuard:
    """工具调用循环检测器。

    在每次 tool call 之前调用 check()，返回:
      - None: 继续执行
      - str:  拦截原因，应注入到 prompt 作为警告
    """

    # ── 配置 ──
    max_repeat_fingerprint: int = 2       # 同一指纹重复几次触发
    max_output_similarity: float = 0.8    # Jaccard 相似度阈值
    ping_pong_window: int = 4             # 摇摆检测窗口
    min_info_gain: float = 0.15           # 最小信息增益

    # 工具级上限
    tool_limits: dict = field(default_factory=lambda: {
        "search_web": 5,
        "fetch_url": 3,
        "python_exec": 3,
        "delegate_task": 1,
    })

    # ── 状态 ──
    tool_history: list = field(default_factory=list)       # [{name, args, output_preview}]
    fingerprint_counts: dict = field(default_factory=dict) # {fp: count}
    tool_counts: dict = field(default_factory=dict)        # {tool_name: count}

    def check(self, tool_name: str, tool_args: dict) -> Optional[str]:
        """
        在工具调用前检查。

        Returns:
            None → 可以调用
            str  → 拦截，返回警告信息（应注入到系统 prompt）
        """
        # 1. 工具级上限
        if tool_name in self.tool_limits:
            count = self.tool_counts.get(tool_name, 0)
            if count >= self.tool_limits[tool_name]:
                return (
                    f"你已经调用了 {tool_name} {count} 次，已达到上限。"
                    f"请基于已有信息直接输出，不要再调用此工具。"
                )

        # 2. 去重指纹
        fp = make_tool_fingerprint(tool_name, tool_args)
        fp_count = self.fingerprint_counts.get(fp, 0)
        if fp_count >= self.max_repeat_fingerprint:
            return (
                f"你已经就 「{fp}」这个主题搜索了 {fp_count} 次。"
                f"请停止重复搜索，基于已有信息直接输出。"
            )

        # 3. 摇摆检测
        if len(self.tool_history) >= self.ping_pong_window - 1:
            # 构造临时历史（包括本次即将进行的调用）
            temp_history = self.tool_history + [{"name": tool_name, "args": tool_args}]
            if detect_ping_pong(temp_history, self.ping_pong_window):
                return (
                    "检测到你在两个查询之间来回切换。"
                    "请做出决定，选择一个方向并基于该方向的信息输出。"
                )

        return None  # 通过所有检查

    def record(self, tool_name: str, tool_args: dict, output: str = ""):
        """记录一次成功的工具调用（在调用完成后调用）。"""
        fp = make_tool_fingerprint(tool_name, tool_args)

        self.tool_history.append({
            "name": tool_name,
            "args": tool_args,
            "output_preview": output[:200],
        })
        self.fingerprint_counts[fp] = self.fingerprint_counts.get(fp, 0) + 1
        self.tool_counts[tool_name] = self.tool_counts.get(tool_name, 0) + 1

    def should_force_stop(self, total_rounds: int, max_rounds: int) -> bool:
        """是否应该强制停止工具调用？"""
        if total_rounds >= max_rounds:
            return True

        # 额外检查: 最近 2 次调用信息增益都低于阈值
        if len(self.tool_history) >= 3:
            recent = [h.get("output_preview", "") for h in self.tool_history[-3:]]
            gains = [
                compute_information_gain(recent[i], recent[:i])
                for i in range(1, len(recent))
            ]
            if all(g < self.min_info_gain for g in gains):
                return True

        return False
```

### 6.3 在 execute_node 中使用

```python
# core/graph.py — execute_node 改造

from tools.loop_guard import LoopGuard

async def execute_node(state: AgentState, skills=None, model=None) -> dict:
    ...
    # 从 state 中恢复或初始化 LoopGuard
    loop_guard = _restore_guard(state)

    # 在 ReAct Agent 的每次工具调用前后插入检查
    # (具体实现取决于 LangGraph 的 integration 方式)
    # 方案 A: 通过 callbacks 拦截
    # 方案 B: 在 agent 完成后分析 messages 中的 tool_calls

    result = await react_agent.ainvoke(...)

    # 分析本轮的工具调用模式
    tool_messages = [m for m in result["messages"] if hasattr(m, "tool_calls")]
    for msg in tool_messages:
        for tc in msg.tool_calls:
            warning = loop_guard.check(tc["name"], tc["args"])
            if warning:
                # 记录警告但不阻塞 — 下一轮 Prompt 中会注入
                state["loop_warnings"].append(warning)
            loop_guard.record(tc["name"], tc["args"], str(msg.content)[:200])

    # 如果需要强制停止
    tool_rounds = len(tool_messages)
    if loop_guard.should_force_stop(tool_rounds, DEFAULT_MAX_TOOL_ROUNDS):
        state["loop_force_stop"] = True

    # 保存 loop_guard 状态到 state
    return {..., "loop_guard": loop_guard}
```

---

## 七、当前状态与待做

### 7.1 已有防护

| 机制 | 位置 | 效果 |
|------|------|------|
| 全局 ReAct 轮数上限 10 | `graph.py` `DEFAULT_MAX_TOOL_ROUNDS` | 硬上限兜底 |
| 子 Agent 8 轮 + 60s 超时 | `delegate.py` | 子任务不跑飞 |
| "最多 10 轮" 写入 Prompt | `system_prompts.py` | 模型被提醒 |
| Reflector 最多拒 2 次 | `graph.py` `MAX_REFLECTION_RETRIES` | 不会无限重试 |
| Checkpoint 最多 1 次修正 | `graph.py` `MAX_CHECKPOINT_RETRIES` | 不会反复折腾 |

### 7.2 缺失

| 缺失 | 说明 |
|------|------|
| 工具指纹去重 | 无法检测 "用不同措辞搜同一个东西" |
| 工具级调用上限 | 所有工具共享 10 轮，search_web 可能吃掉 8 轮 |
| 结果相似度检测 | 搜索返回了几乎一样的内容，Agent 不知道 |
| 摇摆检测 | Agent 在两个方向之间反复横跳 |
| 信息增益检查 | 判断是否"该停了" |
| LoopGuard 状态持久化 | 跨 execute_node 重试时丢失计数 |
| delegate_task 去重 | 同一个子任务可能被 delegate 两次 |

---

## 八、实施路线

| 步骤 | 改动 | 行数 | 效果 |
|------|------|------|------|
| **Step 1**: Prompt 层约束 | `system_prompts.py` | ~10 行 | 减少 30% 的重复搜索 |
| **Step 2**: 新建 `tools/loop_guard.py` | 新增 | ~150 行 | 指纹去重 + 工具计数 + 摇摆检测 |
| **Step 3**: 集成到 execute_node | `graph.py` | ~30 行 | LoopGuard 在每次 tool call 前后介入 |
| **Step 4**: 工具级上限 | `graph.py` + `loop_guard.py` | ~20 行 | search_web ≤ 5, fetch_url ≤ 3, delegate ≤ 1 |
| **Step 5**: 信息增益检测 | `loop_guard.py` | ~30 行 | "搜了等于没搜" 自动停止 |
| **Step 6**: delegate 去重 | `delegate.py` | ~15 行 | delegate_task 带指纹，重复调用拒绝 |
| **Step 7**: AgentState 持久化 | `graph.py` + `agent.py` | ~20 行 | 跨 checkpoint/reflect 重试保持计数 |

---

## 九、相关文件

| 文件 | 角色 |
|------|------|
| `tools/loop_guard.py` | **新建** — LoopGuard 类，所有检测逻辑 |
| `core/graph.py` | 集成点 — execute_node 中调用 LoopGuard |
| `prompts/system_prompts.py` | Prompt 层 — 停止搜索的正向指令 |
| `tools/delegate.py` | delegate 去重 |
| `tools/__init__.py` | 工具列表, SKILL_TOOL_MAP |
