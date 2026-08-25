# 课程 08：多 Agent Panel — 三立场并行分析

> **难度**: 高级 | **预计阅读**: 20 分钟 | **前置**: [07-工程规范检查](07-工程规范检查.md)

---

## 一、是什么

三个不同决策立场的 AI Agent **并行**分析同一问题，然后由阿福整合为结构化对比报告。

```
用户问题: "我应该用 JWT 还是 Session？"
        │
        ├── ⚡ 实用派 (并行)
        │   原则: 最快落地、最小成本、最简实现
        │
        ├── 🛡️ 稳健派 (并行)
        │   原则: 安全第一、可维护、可扩展
        │
        └── 🚀 创新派 (并行)
            原则: 差异化、突破常规、前瞻性
        │
        └── 阿福整合 → 结构化对比
```

---

## 二、触发规则

### 2.1 明确触发

```python
EXPLICIT_TRIGGERS = [
    "从不同角度", "多角度", "对比方案", "多个方案",
    "优缺点", "利弊", "优劣", "权衡",
    "不同立场", "多视角", "帮我对比", "分析对比",
    "有什么选择", "有哪些方案", "各有什么",
    "哪种更好", "选哪个", "怎么选",
    "帮我分析一下", "帮我评估",
    "对比一下", "对比优劣", "方案对比", "方案比较",
]
```

### 2.2 禁止触发

```python
SUPPRESS_TRIGGERS = [
    "什么是", "怎么用", "介绍一下", "解释",
    "帮我查", "搜索", "翻译",
]
```

### 2.3 低置信度强制输出

```python
# 需求不明确 + 用户拒绝追问 + 坚持要输出
if confidence < 0.5 and has_reject and len(message) > 5:
    return {"trigger": True, "reason": "需求不明确但用户拒绝追问", "method": "unclear_demand"}
```

### 2.4 完整检测逻辑

```python
def should_trigger_multi_agent(message, contract):
    text = message.lower().strip()
    confidence = (contract or {}).get("confidence", 1.0)

    # Rule 1: 明确触发词 + 非禁止词
    explicit_hits = [t for t in EXPLICIT_TRIGGERS if t in text]
    suppress_hits = [t for t in SUPPRESS_TRIGGERS if t in text]
    if explicit_hits and not suppress_hits:
        return {"trigger": True, "method": "explicit"}

    # Rule 2: 低置信度 + 拒绝追问
    reject_phrases = ["直接给我", "不用问了", "先输出", "随便", "你看着办"]
    has_reject = any(p in text for p in reject_phrases)
    if confidence < 0.5 and has_reject:
        return {"trigger": True, "method": "unclear_demand"}

    return {"trigger": False}
```

---

## 三、三立场 Prompt 设计

### 3.1 实用派 (Pragmatist)

```python
PRAGMATIST_PROMPT = """你是一个**实用派**工程师。核心原则：最快落地、最小成本、最简实现。

## 思考方式
- 什么方案能最快跑起来？
- 有没有现成的库/工具可以直接用？
- 先做 MVP，能用再迭代
- 技术选型优先选你熟的、社区大的、坑少的

## 你的限制
- 不推荐需要学一周才能上手的新技术
- 不引入超过 3 个新依赖
- 不设计"万一将来要扩展"的预留接口
"""
```

### 3.2 稳健派 (Conservative)

```python
CONSERVATIVE_PROMPT = """你是一个**稳健派**架构师。核心原则：安全第一、可维护、可扩展。

## 思考方式
- 这个方案 6 个月后还有人能维护吗？
- 边界条件都处理了吗？
- 有没有安全隐患？数据会不会丢？
- 测试怎么保证？部署出问题怎么回滚？

## 你的限制
- 数据相关操作必须有备份和回滚方案
- 标注每个决策的可逆性
"""
```

### 3.3 创新派 (Innovator)

```python
INNOVATOR_PROMPT = """你是一个**创新派**技术探索者。核心原则：差异化、突破常规、前瞻性。

## 思考方式
- 有没有更聪明的方法？
- 新技术有没有可能大幅简化这个问题？
- 用户的隐性需求可能是什么？

## 你的限制
- 不推荐你了解不深的技术
- 创新方案必须说明风险
- 不能为了炫技而推荐复杂度高的方案
"""
```

---

## 四、并行执行机制

```python
class MultiAgentPanel:
    PERSPECTIVES = {
        "pragmatist":    {"label": "实用派", "icon": "⚡", "color": "#4CAF50"},
        "conservative":  {"label": "稳健派", "icon": "🛡️", "color": "#2196F3"},
        "innovator":     {"label": "创新派", "icon": "🚀", "color": "#FF9800"},
    }

    async def run_panel(self, message, background, rag_context):
        # 并行执行三个 Agent
        async def run_one(key):
            config = self.PERSPECTIVES[key]
            response = await self.model.ainvoke([
                SystemMessage(content=config['system_prompt'] + context),
                HumanMessage(content="请给出你的分析和建议。"),
            ])
            elapsed = ...
            return key, response.content, elapsed

        tasks = [run_one(k) for k in self.PERSPECTIVES]
        results = await asyncio.gather(*tasks)  # ← 真正的并行

        # 阿福整合
        synthesis = await self._synthesize(message, *outputs)
        return {"perspectives": perspectives, "synthesis": synthesis}
```

---

## 五、阿福整合

### 5.1 整合 Prompt

```python
SYNTHESIZER_PROMPT = """你是阿福。你收到了三个不同立场的 AI 对同一问题的分析：
- 实用派：优先速度和最小实现
- 稳健派：优先安全和维护成本
- 创新派：优先差异化与创意

你的任务是把三份分析整合为一份结构化对比。

## 输出格式（Markdown）
### 🤝 共识
（三个立场都认同的核心观点）

### ⚡ 分歧
（关键分歧点，每个分歧说明三方的不同立场）

### 💰 每个方案的代价
| 方案 | 时间成本 | 风险等级 | 技术债务 | 适合场景 |
|------|---------|---------|---------|---------|

### 🎯 你需要决定的
（列出用户真正需要在意的 2-3 个关键决策点）

### 💡 阿福的建议
（如果有明确倾向，说明原因；如果取决于场景，说明什么情况选哪个）

## 规则
- 不要说"三方都很好"——必须有明确立场
- 不要重复三方原始输出，提炼要点
- 分歧点是价值所在，不要掩盖分歧
- 总长度控制在 500 字以内
"""
```

---

## 六、SSE 事件流

多 Agent 结果通过专门的 SSE 事件推送：

```python
def format_panel_for_sse(perspectives):
    events = []
    for key, p in perspectives.items():
        events.append({
            "event": "multi_agent_perspective",
            "data": {
                "key": key,
                "label": p["label"],
                "icon": p["icon"],
                "color": p["color"],
                "output": p["output"],
                "elapsed_ms": p["elapsed_ms"],
            },
        })
    return events
```

前端可以为每个立场渲染不同颜色的卡片。

---

## 七、降级方案

当 LLM 整合失败时：

```python
def _fallback_synthesis(self, pragmatist, conservative, innovator):
    return f"""### 🤝 共识
（三个立场自动生成，请手动对比）

### 💰 每个方案的代价
| 方案 | 适合场景 |
|------|---------|
| ⚡ 实用派 | 快速上线、验证想法 |
| 🛡️ 稳健派 | 长期维护、团队协作 |
| 🚀 创新派 | 差异化竞争、技术探索 |

<details>
<summary>⚡ 实用派原始分析</summary>
{pragmatist[:800]}
</details>
...
"""
```

---

## 八、在图中的位置

```
engineering_check → {execute | multi_agent | END}
                           │
multi_agent → checkpoint → {reflect | execute}
```

> 多 Agent 结果**也会经过 checkpoint + reflect**，不是直接输出。

---

## 九、关键要点

1. **真并行** — `asyncio.gather` 三个 Agent 同时运行，非串行
2. **触发是硬约束** — 用户必须明确要求，不会主动触发
3. **三立场互补** — 快/稳/新三个维度覆盖决策空间
4. **整合比分析更重要** — 500 字结构化对比 > 三篇长文
5. **整合结果同样走质量检查** — checkpoint + reflect 不跳过

---

## 十、继续学习

→ [09-执行节点](09-执行节点.md) — ReAct Agent 工具调用循环
