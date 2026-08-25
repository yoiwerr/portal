# 课程 10：Checkpoint 与 Reflect — 语义中枢 + 质量检查双保险

> **难度**: 高级 | **预计阅读**: 20 分钟 | **前置**: [09-执行节点](09-执行节点.md)

---

## 一、为什么需要两道检查

Executor 完成了输出，但我们怎么知道输出是**对的**？

两道独立的检查：
- **Checkpoint**: "方向对不对？" → 语义对齐（快速，单次 LLM）
- **Reflect**: "质量好不好？" → 完整性+准确性（深度，包含评分）

```
execute → checkpoint → {reflect | execute(重试)}
                            ↓
                       reflect → {execute(重试) | END}
```

---

## 二、Checkpoint — 语义中枢

### 2.1 职责

在 Reflector 之前先拦截明显的语义偏移。避免质量检查浪费在方向性错误上。

### 2.2 System Prompt

```python
PLANNER_CHECKPOINT_PROMPT = """你是语义对齐审核员。检查执行结果是否与用户原始意图一致。

## 审核标准
- **语义对齐**: 输出的内容是否回答了用户真正在问的问题？有没有答非所问？
- **意图偏移**: 执行过程中是否偏离了 Planner 最初设定的目标？
- **知识库忠实度**: 输出中的技术声明是否能在提供的知识库参考中找到依据？
- **遗漏**: 用户的多个子问题是否都覆盖了？

## 输出格式
{
  "aligned": true/false,
  "score": 0-10,
  "drift_description": "如果有偏移，描述偏移了什么",
  "correction": "如果未对齐，给出明确的修正方向",
  "hallucination_detected": false,
  "hallucination_details": []
}
- score >= 7: 对齐
- score < 7: 需要修正
"""
```

### 2.3 核心逻辑

```python
async def checkpoint_node(state, model):
    output = state.get("output", "")
    plan = state.get("plan", {})
    contract = plan.get("contract", {})
    message = _get_last_user_message(state)
    checkpoint_retry_count = state.get("checkpoint_retry_count", 0)

    # 超过最大重试 → 跳过
    if checkpoint_retry_count >= MAX_CHECKPOINT_RETRIES:
        return {"checkpoint_feedback": ""}

    # 输出过短 → 自动标记为不对齐
    if not output or len(output.strip()) < 30:
        return {
            "checkpoint_feedback": "输出过短或不完整，请根据用户需求重新生成完整回答。",
            "checkpoint_retry_count": checkpoint_retry_count + 1,
        }

    # LLM 语义对齐检查
    checkpoint_prompt = f"""{PLANNER_CHECKPOINT_PROMPT}

## Planner 设定的原始目标
{plan.get('goal')}

## 任务契约
{format_contract_for_checkpoint(contract)}

## 执行进度
已完成步骤: {completed_steps}
执行轮次: 第 {execute_round} 轮

## 用户的原始消息
{message}

## 知识库参考
{rag_brief[:800]}

## Executor 的实际输出（前 1500 字符）
{output[:1500]}

请评估语义对齐程度，输出 JSON。"""

    structured_model = model.bind(response_format={"type": "json_object"})
    response = await structured_model.ainvoke([...])
    checkpoint = _parse_checkpoint_json(response.content)

    if checkpoint.get("aligned", True):
        return {"checkpoint_feedback": ""}   # 对齐 → 进 reflect
    else:
        return {
            "checkpoint_feedback": checkpoint.get("correction", ""),
            "checkpoint_retry_count": checkpoint_retry_count + 1,
            "plan": {**plan, "retry_reason": f"[语义偏移] {checkpoint.get('drift_description')}"},
        }
```

### 2.4 条件路由

```python
def route_after_checkpoint(state):
    feedback = state.get("checkpoint_feedback", "")
    checkpoint_retry_count = state.get("checkpoint_retry_count", 0)
    if feedback and checkpoint_retry_count <= MAX_CHECKPOINT_RETRIES:
        return "execute"   # 有反馈 + 未超限 → 回到 execute 重试
    return "reflect"       # 无反馈或超限 → 进入 reflect
```

---

## 三、Reflect — 质量检查

### 3.1 职责

深度的质量审查：完整性、准确性、忠实度、边界守护。

### 3.2 System Prompt

```python
REFLECTOR_SYSTEM_PROMPT = """你是质量审核助手。审查阿福的输出质量。

## 审核标准
- **目标对齐**: 输出是否围绕用户的实际需求？有没有跑题？
- **边界守护**: 有没有假装能写代码、能执行命令？
- **完整性**: 用户的问题都覆盖了吗？
- **清晰度**: 用户读完知道下一步该做什么吗？
- **忠实度**: 有没有编造知识库中不存在的信息？

## 输出格式（JSON）
{
  "pass": true/false,
  "score": 0-10,
  "issues": ["发现的问题"],
  "suggestions": ["改进建议"],
  "hallucination_detected": false,
  "hallucination_details": [],
  "boundary_violations": ["越权行为"]
}
- score >= 7: 通过
- score 4-6: 需要修正
- score < 4: 需要重做
"""
```

### 3.3 核心逻辑

```python
async def reflect_node(state, model):
    output = state.get("output", "")
    plan = state.get("plan", {})
    reflection_count = state.get("reflection_count", 0)

    # 输出太短 + 未超限 → 重试
    if not output or len(output.strip()) < 50:
        if reflection_count < MAX_REFLECTION_RETRIES:
            return {"reflection_count": reflection_count + 1,
                    "plan": {**plan, "retry_reason": "输出过短或不完整"}}
        return {"reflection_count": reflection_count}

    # 已达最大重试 → 停止
    if reflection_count >= MAX_REFLECTION_RETRIES:
        return {"reflection_count": reflection_count}

    # LLM 质量检查
    reflect_prompt = f"""{REFLECTOR_SYSTEM_PROMPT}

## 用户原始需求
{message}

## 期望完成的目标
{plan.get('goal')}

## 任务契约
{format_contract_for_checkpoint(contract)}

## 知识库参考
{rag_brief[:800]}

## 实际输出（前 2000 字符）
{output[:2000]}

请评估这段输出是否满足用户需求和契约约束。输出 JSON。"""

    structured_model = model.bind(response_format={"type": "json_object"})
    response = await structured_model.ainvoke([...])
    reflection = _parse_reflection_json(response.content)

    if reflection.get("pass", True):
        return {"reflection_count": reflection_count}
    else:
        retry_hint = reflection.get("suggestions", ["请改进输出质量"])
        return {
            "reflection_count": reflection_count + 1,
            "plan": {**plan, "retry_reason": "; ".join(retry_hint)},
        }
```

### 3.4 条件路由

```python
def route_after_reflect(state):
    plan = state.get("plan", {})
    reflection_count = state.get("reflection_count", 0)
    if plan.get("retry_reason") and reflection_count < MAX_REFLECTION_RETRIES:
        return "execute"
    return "__end__"
```

---

## 四、Checkpoint vs Reflect 对比

| 维度 | Checkpoint | Reflect |
|------|-----------|---------|
| 检查什么 | 方向对不对（语义对齐） | 质量好不好（完整性+准确性） |
| 速度 | 快（≤1500字符输出） | 慢（≤2000字符输出，更多维度） |
| 最大重试 | 1 次 | 2 次 |
| 失败后 | 回 execute 重试 | 回 execute 重试 |
| 评分阈值 | score >= 7 通过 | score >= 7 通过 |
| 独有检查 | 语义偏移检测 | 边界越权检测 |
| 独有检查 | 幻觉检测 | 幻觉检测 |

---

## 五、两条独立重试路径

```
execute → checkpoint
            ├─ aligned → reflect → END
            └─ !aligned → execute (retry#1)
                            → checkpoint
                              ├─ aligned → reflect → END
                              └─ !aligned → reflect (超限，跳过)
                                              → END (即使不对齐)

execute → checkpoint → reflect
                        ├─ pass → END
                        └─ !pass → execute (retry#1)
                                    → checkpoint → reflect
                                      ├─ pass → END
                                      └─ !pass → execute (retry#2)
                                                  → END (超限，即使不通过)
```

> **最大总重试**: checkpoint 1次 + reflect 2次 = 可能 3 次 execute

---

## 六、JSON 解析降级

三个解析函数的降级策略相同：

```python
def _parse_checkpoint_json(content):
    try: return json.loads(content)
    except: pass
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        try: return json.loads(match.group(0))
        except: pass
    return {"aligned": True, "score": 8}  # 解析失败时默认通过
```

> **默认通过原则**: JSON 解析失败时不阻塞流程 — 宁放过不误杀。

---

## 七、关键要点

1. **双保险**: Checkpoint 看方向 + Reflect 看质量
2. **独立计数器**: checkpoint_retry_count 和 reflection_count 互不干扰
3. **降级安全**: LLM 失败/JSON 解析失败 → 默认通过
4. **输出长度检查**: 过短输出直接标记为不对齐/不通过
5. **渐进式**: 先快速检查方向（checkpoint），再深度检查质量（reflect）

---

## 八、继续学习

→ [11-RAG系统](11-RAG系统.md) — 混合检索管道详解
