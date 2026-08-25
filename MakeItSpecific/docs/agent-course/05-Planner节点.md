# 课程 05：Planner 节点 — 维度提取 + 任务契约

> **难度**: 高级 | **预计阅读**: 25 分钟 | **前置**: [04-上下文引擎](04-上下文引擎.md)

---

## 一、Planner 的职责

Planner 是图的**核心决策节点**，它决定：

1. **这个任务需要什么信息？** → 从用户消息中提取维度
2. **信息够不够？** → 计算完整度 (completeness)
3. **要做哪些、不做哪些？** → 生成任务契约 (TaskContract)
4. **下一步是追问还是执行？** → 决定 clarify 还是 engineering_check

---

## 二、Planner 的完整 Prompt

Planner 的 System Prompt 包含三个层次：

```
┌──────────────────────────────────┐
│ 1. 阿福身份定义 (共享)            │
│    - 擅长什么、不做什么            │
│    - 工具使用铁律                  │
│    - 输出克制原则                  │
├──────────────────────────────────┤
│ 2. Planner 专属职责               │
│    - 理解意图 + 评估完整度         │
│    - 制定计划 + 生成追问           │
│    - 边界识别                     │
├──────────────────────────────────┤
│ 3. 任务契约 JSON 输出格式          │
│    - 7 个契约字段                  │
│    - confidence 加权规则           │
└──────────────────────────────────┘
```

---

## 三、维度系统

### 3.1 维度定义 (以 prompt_refiner 为例)

```python
PROMPT_REFINER_DIMENSIONS = {
    "purpose": {
        "label": "核心目的", "weight": 0.25, "required": True,
        "hint": "这个提示词要完成什么任务？"
    },
    "target_model": {
        "label": "目标模型", "weight": 0.15, "required": False,
    },
    "output_style": {
        "label": "输出风格", "weight": 0.20, "required": True,
        "hint": "简洁实用 / 详细教程 / 创意发散 / 结构化报告？"
    },
    "constraints": {
        "label": "约束条件", "weight": 0.15, "required": False,
    },
    "target_audience": {
        "label": "目标受众", "weight": 0.15, "required": False,
    },
    "examples": {
        "label": "参考示例", "weight": 0.10, "required": False,
    },
}
```

### 3.2 完整度计算

```python
def calculate_completeness(expressed, dimensions):
    total_weight = sum(d["weight"] for d in dimensions.values())
    covered_weight = 0.0
    gaps = []

    for key, dim in dimensions.items():
        if key in expressed and expressed[key]:
            confidence = expressed.get(f"{key}_confidence", 0.5)
            covered_weight += dim["weight"] * confidence
        else:
            gaps.append({"key": key, "label": dim["label"], ...})

    completeness = covered_weight / total_weight
    return completeness, gaps
```

> **关键**: 每个维度不仅看是否填写，还看置信度（0.5 默认 → 最高 1.0）。

---

## 四、Planner LLM 调用

```python
async def planner_node(state, model, rag_service):
    # ── 组装 Prompt ──
    dims_desc = build_dimensions_desc(dimensions)
    existing_dims_text = format_expressed_dimensions(existing_dims)

    # 三层上下文注入
    locked_block = _build_locked_block(intent, existing_dims_text, turn_count)
    context_block = locked_block
    if l2_summary:  context_block += "\n## 🔴 前情提要\n" + l2_summary
    if l1_raw:      context_block += "\n## 🟡 最近对话\n" + l1_raw
    if l3_facts:    context_block += "\n## 🟢 语义事实\n" + l3_facts

    planner_prompt = f"""{PLANNER_SYSTEM_PROMPT}
{context_block}
## 该模块的信息维度定义
{dims_desc}
## 用户背景
{background}
## 额外上下文
{extra_context}
{rag_context}
## 用户最新消息
{message}
请分析这条消息，输出 JSON。"""

    # ── LLM 调用 (JSON mode) ──
    structured_model = model.bind(response_format={"type": "json_object"})
    response = await structured_model.ainvoke([
        SystemMessage(content=planner_prompt),
        HumanMessage(content="请输出 JSON 分析结果。"),
    ])

    plan = _parse_planner_json(response.content)
```

---

## 五、Planner JSON 输出格式

```json
{
  "contract": {
    "goal": "为博客项目添加用户名+密码登录",
    "confidence": 0.85,
    "scope": {
      "in": ["注册", "登录", "session 保持"],
      "out": ["OAuth", "密码找回", "权限管理"]
    },
    "constraints": ["React+TS", "下周五前", "不多于2个新依赖"],
    "acceptance": ["密码错误不区分原因提示"],
    "risks": ["涉及密码存储需确认方案"],
    "deliverables": {"format": "代码改动+PR", "artifacts": ["代码", "测试"]},
    "recommended_tools": ["Claude Code — 写代码"]
  },
  "is_complete": true,
  "missing_fields": [],
  "clarify_questions": [],
  "execution_plan": ["步骤1", "步骤2"],
  "goal": "为博客项目添加用户名+密码登录"
}
```

---

## 六、JSON 解析的三级降级

```python
def _parse_planner_json(content: str) -> dict:
    # Level 1: 直接 parse
    try: return json.loads(content)
    except: pass

    # Level 2: 提取 ```json ... ``` 代码块
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
    if match:
        try: return json.loads(match.group(1))
        except: pass

    # Level 3: 提取第一个 { ... } 块
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        try: return json.loads(match.group(0))
        except: pass

    # Level 4: 完全失败 → 降级 plan
    return {"is_complete": False, "completeness": 0.3, ...}
```

---

## 七、🔴 已锁定意图块 (Locked Block)

这是解决**意图偏移**和**信息遗忘**的核心机制：

```python
def _build_locked_block(intent, dims_text, turn_count):
    lines = []

    # 🔴 已锁定意图
    if intent_label:
        lines.append("## 🔴 已锁定意图（最高优先级，不可偏离）")
        lines.append(f"- **当前任务**: {intent_label}")
        lines.append("- **规则**: 以下所有回答必须围绕此意图。")
        lines.append("  如果用户后续消息看似偏离，优先确认是否切换话题。")

    # 🔴 工作记忆（已确认的需求，跨轮持久化）
    if dims_text:
        lines.append("## 🔴 工作记忆（已确认的需求信息，跨轮持久化）")
        lines.append(dims_text)

    return "\n".join(lines)
```

> 这个块在 Planner、Executor、Checkpoint 的所有 Prompt 中**最高优先级注入**。

---

## 八、降级 Plan

当 LLM 完全不可用时：

```python
def _fallback_plan(message, dimensions):
    msg_len = len(message)
    if msg_len < 20:
        return {"is_complete": False, "completeness": 0.2,
                "clarify_questions": [
                    {"text": "能再详细说说你想做什么吗？", "dimension": "purpose"}
                ]}
    elif msg_len < 100:
        return {"is_complete": False, "completeness": 0.4,
                "clarify_questions": [
                    {"text": "能说具体要求吗？比如风格、格式、时间？", "dimension": "details"}
                ]}
    else:
        return {"is_complete": True, "completeness": 0.8,
                "execution_plan": ["直接基于用户输入执行"]}
```

> 纯基于消息长度的启发式规则，不依赖 LLM。

---

## 九、维度合并

多轮对话中，新提取的维度需要与已有的合并：

```python
def _merge_dimensions_from_plan(existing, extracted):
    merged = dict(existing)
    for key, info in extracted.items():
        value = info.get("value", "") if isinstance(info, dict) else str(info)
        confidence = info.get("confidence", 0.5)
        if value and str(value) != "null":
            existing_conf = merged.get(f"{key}_confidence", 0)
            # 只在新置信度更高时才覆盖
            if confidence > existing_conf:
                merged[key] = value
                merged[f"{key}_confidence"] = confidence
    return merged
```

---

## 十、从 Plan 到 TaskContract

```python
# graph.py planner_node 中:
from models.task_contract import TaskContract
tc = TaskContract.from_planner_json(plan, session_id="")
contract = tc.model_dump(by_alias=True, mode="json")

# 将 contract 存入 plan，后续节点通过 plan["contract"] 访问
plan["contract"] = contract
```

> `TaskContract` 是 Pydantic 模型，提供验证和类型安全。详见 [14-任务契约](14-任务契约.md)。

---

## 十一、Planner 在图中的位置

```
router → enrich → rag → PLANNER → {clarify | engineering_check}
```

Planner 之后的决策：

```python
def route_after_planner(state):
    plan = state.get("plan", {})
    clarify_round = state.get("clarify_round", 0)
    if not plan.get("is_complete") and clarify_round < max_clarify_rounds:
        return "clarify"    # 信息不足 → 追问
    return "engineering_check"  # 信息够 → 工程检查
```

---

## 十二、关键要点

1. **Planner 是决策中枢** — 它决定任务是追问、执行还是阻断
2. **JSON mode 保证结构化输出** — `model.bind(response_format={"type": "json_object"})`
3. **三级 JSON 解析** — 直接 parse → 代码块提取 → 正则兜底
4. **维度权重驱动完整度** — 必填维度权重高，scope.out 为空减 0.2
5. **Locked Block 防止意图漂移** — 最高优先级注入所有后续 Prompt
6. **合并策略保守** — 只在置信度更高时才覆盖已有维度

---

## 十三、继续学习

→ [06-追问系统](06-追问系统.md) — 什么时候追问、问什么、怎么展示
