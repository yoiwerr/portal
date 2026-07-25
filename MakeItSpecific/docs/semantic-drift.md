# 语义偏移：多节点 Agent 冲突与重试机制

## 一、问题概述

Alfred 的 LangGraph 图有 10 个节点，其中 7 个节点各自绑定了独立的 LLM 调用，每个节点有自己的 System Prompt 和行为倾向。当这些节点的 Prompt 方向不一致时，会产生**语义偏移**（semantic drift）——后续节点产出的内容偏离了前面节点设定的目标和契约。

## 二、图的执行流程与各节点角色

```
START
  → router (LLM)     — 意图识别：用户想做什么类型的任务
  → enrich           — 纯数据：丰富查询词，不做 LLM
  → rag              — 检索知识库
  → planner (LLM)    — 语义中枢：提取维度 → 生成任务契约 → 判断完整度
      ├→ clarify (LLM)           — 信息不足时追问，然后 END
      └→ engineering_check (LLM) — 工程规范扫描：建议 / 确认 / 阻断
            ├→ multi_agent (多 LLM 并行) — 多视角分析
            ├→ execute (ReAct, 最多 10 轮 LLM) — 工具调用循环
            │     └→ checkpoint (LLM) → 检查语义对齐
            │           ├→ 对齐 → reflect
            │           └→ 偏离 → 回 execute 重试（最多 2 次）
            └→ reflect (LLM) → 质量检查 → 不合格回 execute
                                      → 合格 → END
```

## 三、语义偏移的典型场景

### 场景 1：Planner vs Executor 方向不一致

**触发条件**：用户说"帮我做一个论坛"，Planner 正确提取目标为"搭建一个论坛项目"，但 Executor 的 ReAct Agent（work_arranger skill）的 System Prompt 倾向于"先规划再行动"，于是它写出了一份"如何开发论坛的策略提示词"而不是实际的代码/项目文件。

**日志表现**：
```
[Checkpoint] ❌ 语义偏移 (score=2): 输出内容完全偏离了用户意图
——用户要求实际开发一个论坛，但 Executor 却设计了三个不同策略的开发提示词，
没有执行任何编码或实现步骤。
```

**根因**：
- Planner 使用 JSON mode，输出结构化的 `goal` + `execution_plan`
- Executor（ReAct Agent）有自己的 System Prompt（WORK_ARRANGER_SYSTEM），它对"安排工作"的理解可能偏向"写规划文档"而非"动手执行"
- 两个 Prompt 之间没有硬约束，完全靠语义传递

### 场景 2：Executor 输出风格与 Checkpoint 预期不符

**触发条件**：Executor 用工具完成了实际工作（写入文件、运行命令），但最终的文字输出是简短的总结而非详细的交付清单。Checkpoint 读取 output 文本判断"没有完整输出"，标记为不完整。

**根因**：
- Checkpoint 的 PLANNER_CHECKPOINT_PROMPT 检查"输出是否满足用户需求"
- 当实际工作落在文件系统而非对话文本中时，Checkpoint 无法感知工具调用的产出

### 场景 3：重试循环 — 同样的输入，同样的错误

**触发条件**：Checkpoint 检测到偏移 → 返回 `checkpoint_feedback` → Executor 被重新调用，但反馈只是被拼接到 extra_context 中，System Prompt 不变 → Executor 再次输出类似的错误内容 → Checkpoint 再次检测到偏移 → 进入死循环。

**现在的处理**：`MAX_CHECKPOINT_RETRIES = 1`，最多回 Executor 重试 1 次。如果 1 次后仍未对齐，强制进入 reflector，reflector 再做最后一次重试决策（`MAX_REFLECTION_RETRIES = 2`）。

## 四、当前的重试与兜底机制

### 4.1 Checkpoint → Execute 重试

```python
# core/graph.py:550-556
if checkpoint_retry_count >= MAX_CHECKPOINT_RETRIES:
    return {"checkpoint_feedback": ""}  # 放弃纠正，放行

# 偏离时注入反馈，回 execute
return {
    "checkpoint_feedback": correction,
    "checkpoint_retry_count": checkpoint_retry_count + 1,
}
```

路由逻辑（`route_after_checkpoint`）：
- 有 feedback 且 retry_count ≤ 1：回 `execute`
- 否则：进 `reflect`

### 4.2 Reflector → Execute 重试

```python
# core/graph.py:846-851
def route_after_reflect(state):
    if plan.get("retry_reason") and reflection_count < 2:
        return "execute"
    return "__end__"
```

### 4.3 各层兜底

| 层级 | 兜底策略 | 代码位置 |
|---|---|---|
| Planner | LLM JSON 解析失败 → `_fallback_plan()` 规则降级 | graph.py:287-289 |
| Checkpoint | LLM 调用失败 → 默认通过（不阻断） | graph.py:598-600 |
| Reflector | LLM 调用失败 → 默认通过（score=7） | graph.py:673-674 |
| Contract | Pydantic 解析失败 → 手动构建 dict | graph.py:298-320 |

## 五、当前机制的已知缺陷

### 5.1 重试不改变策略

Checkpoint 反馈只是一段文字，被拼接到 Executor 的 extra_context 中。Executor 的 System Prompt 不变，工具集不变，温度不变。所以**同样的模型 + 同样的 Prompt 骨架 + 微调的文字反馈 → 大概率输出类似的结果**。

### 5.2 重试成本线性累积

1 次 Checkpoint 重试 = 1 次额外的完整 ReAct 循环（最多 10 轮 LLM）。在语义偏移场景下，第二次 ReAct 通常仍然错误，白白消耗 ~60s。

### 5.3 工具产出不可见

Executor 通过 `write_file` / `run_shell_preview` 完成的实际工作，Checkpoint 只能通过 `tool_results` 列表感知工具名称，无法读取写入的文件内容或命令输出。

### 5.4 Planner 意图传递衰减

Planner → contract dict → format_contract_for_executor() → Executor System Prompt。经过多次序列化/反序列化/格式化，Planner 的精确语义可能在传递中丢失。

## 六、改进方向（记录，尚未实施）

1. **Checkpoint 检测到偏移时，切换 Executor 的 System Prompt 变体** — 从"先规划"切换为"直接执行"，而非只加一行文字反馈
2. **工具产出感知** — Checkpoint 应能读取 tool_results 中的实际文件内容（或至少文件路径列表），判断"是否真的有产出"
3. **重试上限与降级** — 如果同一 Checkpoint 原因触发 2 次重试，第三次直接 END 返回"当前能力不足以完成此任务，建议缩小范围或换一种表述"
4. **Planner → Executor 的硬编码契约** — 在 execute_node 中解析 `execution_plan` 的 `steps`，按步骤逐一执行而非让 ReAct 自由发挥
5. **缩短单次 ReAct 轮数** — 从 `MAX_TOOL_ROUNDS=10` 降到 5-6，减少无意义探索的耗时
