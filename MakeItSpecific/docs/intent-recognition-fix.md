# 意图识别四连修复

> 2026-07-13 — 解决意图偏移、信息遗忘、追问拖沓、解释冗余

## 修复前的问题

测试和实际使用中暴露了四个问题：

| # | 问题 | 现象 |
|---|------|------|
| 1 | **意图偏移** | 多轮对话到后面，Executor 忘记了最初的任务是什么，回答偏离用户原始意图 |
| 2 | **信息遗忘** | Planner 追问获得的信息（如"目标文件是 main.py"）在后续轮次中丢失，Planner 重复追问同一问题 |
| 3 | **追问拖沓** | 每轮只问 2-3 个问题，最多 5 轮，导致一个简单需求补全要聊好几轮 |
| 4 | **解释冗余** | 每个追问附带"我问这个是因为…"的解释 + 提示词 + 进度段落 + RAG 备注，追问消息长到用户不想看 |

## 修复 1：🔴 已锁定意图

### 问题根因

旧代码中意图只在 Planner prompt 中以一行 `## 意图识别: 代码审查 (置信度: 90%)` 出现，被埋在 L2/L1/L3 上下文后面。Executor 的 System Prompt 里**根本没有 intent 字段**。对话越长，上下文越多，意图越容易被淹没。

### 修复

`core/graph.py` 新增 `_build_locked_block()` 函数，在 **Planner 和 Executor 的 System Prompt 最前面** 注入锁定块：

```
## 🔴 已锁定意图（最高优先级，不可偏离）
- **当前任务**: 代码审查
- **置信度**: 90%
- **规则**: 以下所有回答必须围绕此意图。如果用户后续消息看似偏离，优先确认是否切换话题。
```

`Executor 自审查 关1` 同步更新：引用此块而非模糊的"用户原始消息"。

### 改了什么

| 文件 | 改动 |
|------|------|
| `core/graph.py` | 新增 `_build_locked_block()` 函数 + Planner 和 Executor 的 context 构建中首部注入 |
| `prompts/system_prompts.py` | 关1 从"回到用户原始消息"→"先检查 prompt 最前面的 🔴 已锁定意图" |

## 修复 2：🔴 工作记忆

### 问题根因

`expressed_dimensions`（用户已确认的需求维度）在旧代码中放在 prompt 的 `## 已确认的信息` 段落，位置在 L2/L1/L3 上下文和 RAG 结果之后。LLM 读到那时注意力已经衰减，且没有任何"这是锁定的"语义标记。多轮后 Planner 看到 `existing_dims_text` 为空时，就会重复追问已经问过的问题。

### 修复

将 `expressed_dimensions` 提升到与锁定意图并列的位置，放在 context 最前面：

```
## 🔴 工作记忆（已确认的需求信息，跨轮持久化，不会丢失）
- ✅ **target_files**: main.py
- ✅ **focus_areas**: 安全性
- 🤔 **language**: Python
```

关键设计：文案明确写 "跨轮持久化，不会丢失" — 直接告诉 LLM 这不是可选上下文，是锁定的。

### 改了什么

| 文件 | 改动 |
|------|------|
| `core/graph.py` | `_build_locked_block()` 合并 intent + dims 双重锁定块 |
| `core/graph.py` | `execute_node` 不再单独注入 `## 已确认的需求信息`，工作记忆已通过锁定块注入 |
| `core/graph.py` | `planner_node` 同样改为锁定块注入，删除独立的 `## 已确认的信息` 段 |

## 修复 3：追问加速

### 问题根因

每轮 2-3 个问题，最多 5 轮。一个需求补全最多要 5 轮来回。用户不耐烦。

### 修复

| 参数 | 改前 | 改后 | 原因 |
|------|------|------|------|
| `max_questions_per_round` | 3 | **5** | 一轮问够 |
| `MAX_CLARIFY_ROUNDS` | 5 | **3** | 减少总轮数 |
| Planner prompt | "每轮最多 2-3 个问题，不要让用户感到被审问" | **"一次性问 4-5 个问题，减少追问轮数。不要一轮只问两三个拖好几轮"** | 明确指令 |
| `_generate_fallback_questions` max_q | 3 | **5** | 与配置对齐 |

效果：原来最多 5×3=15 个问题拖 5 轮，现在最多 3×5=15 个问题只需 2-3 轮。

### 改了什么

| 文件 | 改动 |
|------|------|
| `config.py` | `max_questions_per_round 3→5`、`max_clarify_rounds 5→3` |
| `core/graph.py` | `MAX_CLARIFY_ROUNDS 5→3`、`_generate_fallback_questions` max_q 3→5 |
| `prompts/system_prompts.py` | Planner 追问原则重写 |

## 修复 4：精简追问

### 问题根因

追问消息太啰嗦：

- 每轮有"先肯定用户"的寒暄段落
- 每个问题附带 hint 提示词
- "我问这个是因为…"的解释
- RAG 备注"已从知识库中找到相关资料"
- "信息完整度: 30% | 本轮追问: 3 个问题"

### 修复

`_format_clarification_message()` 重写：

改前（~15 行）：
```
我来帮你理清需求。先了解几个基本信息：

**1.** 你的目标是什么？
   *（比如：生成产品文案、写代码注释、翻译文档...）*

**2.** 什么时候完成？
   *（）*

---
（已从知识库中找到相关资料，会在生成时参考）
---
信息完整度: 30%  |  本轮追问: 2 个问题
```

改后（~6 行）：
```
还差一些信息，请帮忙补充：

**1.** 你的目标是什么？

**2.** 什么时候完成？

（进度 30%）
```

Planner prompt 同步删除 "我问这个是因为…" 指令。

### 改了什么

| 文件 | 改动 |
|------|------|
| `core/graph.py` | `_format_clarification_message` 重写：删除 hint、RAG 备注、冗余进度行 |
| `prompts/system_prompts.py` | 删除"给出追问的上下文"→ 改为"不要解释每个问题的缘由 — 直接问问题本身即可" |

## 效果对比

| 维度 | 改前 | 改后 |
|------|------|------|
| 意图在多轮后还准确吗 | ❌ 经常偏移 | ✅ 锁定块在最前面，不可绕过 |
| 已确认的信息会丢吗 | ❌ 第 3-4 轮后重复追问 | ✅ 工作记忆跨轮持久化 |
| 追问需要几轮 | 3-5 轮 | 1-2 轮 |
| 追问消息长度 | ~15 行 | ~6 行 |
| 追问有废话吗 | "我问这个是因为…" + hint + RAG 备注 | 直接问问题，干净 |
| 最多追问轮数 | 5 轮 | 3 轮（够用且不拖） |

## 涉及文件

```
config.py                   — max_questions_per_round 3→5, max_clarify_rounds 5→3
core/graph.py               — _build_locked_block() 新增
                               planner_node / execute_node 锁定块注入
                               _generate_fallback_questions max_q 3→5
                               _format_clarification_message 重写
                               MAX_CLARIFY_ROUNDS 5→3
prompts/system_prompts.py   — Planner 追问原则重写
                               Executor 关1 引用锁定意图
tests/test_graph.py          — 适配新 formatter 的断言
```
