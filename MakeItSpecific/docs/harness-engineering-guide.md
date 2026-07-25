# Harness Engineering 学习指南 — 从 Prompt 到全链路驾驭

> 驾驭工程 (Harness Engineering)：不只是写好 prompt，而是设计一套**系统性的约束和控制机制**，让 AI Agent 在复杂多轮对话中不跑偏、不编造、不遗忘、不失控。
>
> 阅读对象：想理解 AI Agent 可控性设计的人。本文从概念到实践，用 MakeItSpecific 项目的真实设计决策作为案例。

---

## 〇、先定位：三层工程的关系

在深入之前，先搞清楚三个容易混淆的概念：

```
Prompt Engineering    怎么写好单次 prompt           单次交互       "这句 prompt 怎么改能让模型输出更好？"
Context Engineering   怎么管理多轮对话的信息流        多交互         "第 5 轮对话时，模型还能看到第 1 轮的细节吗？"
Harness Engineering   怎么约束模型不跑偏              全链路控制      "模型开始胡说时，谁能拦住它？"
```

**Harness Engineering 是 Prompt Engineering + Context Engineering + 质量控制 + 工具约束 + 记忆系统 + 成本管理的总和。** 它不是某一个技术，而是一套设计哲学。

打个比方：
- Prompt Engineering = 教一个人怎么做好一件事（单次指导）
- Context Engineering = 确保这个人不会忘记前面说过的话（信息管理）
- Harness Engineering = 给这个人配一个监工 + 一本操作手册 + 一个预算上限 + 一个质检流程（全链路控制）

本文按「概念 → 原理 → 实践 → 进阶」的结构展开，每一节都可以独立阅读。

---

## 一、Prompt Engineering — 驾驭的第一层

### 1.1 模型不是"理解"你，是在"补全"你

LLM 的本质是 next-token prediction。它看到你的 prompt，然后预测最可能的下一个 token。这意味着：

- **你没说的，它会猜** — 而且猜得很有信心
- **你说了但不强调的，它可能忽略** — 因为从概率上不那么重要
- **你说的顺序影响它的注意力** — 开头和结尾权重最高

所以 Prompt Engineering 的核心不是"写得好"，而是**用结构弥补概率模型的弱点**。

### 1.2 四个核心技巧

#### 技巧一：指令在前，参考在后

```
❌ 差:
"这是一段对话历史...（500字）...根据以上内容，请帮用户优化提示词。注意：不要改变用户的原始意图。"

✅ 好:
"## 🔴 核心任务：优化提示词，不改变用户原始意图
## 🟡 对话背景：（对话历史摘要，200字）
## 🟢 参考资料：（完整对话，500字）"
```

**原理**：Transformer 的注意力机制对序列位置敏感。开头（position 0）的 token 会被所有后续 token attend 到，所以指令放最前面。

#### 技巧二：用视觉标记创造注意力锚点

模型训练数据中，emoji 和 Markdown 标题天然携带"重要"的语义偏差：

```
🔴 = 必须遵守（最高优先级）
🟡 = 重要参考（中等优先级）
🟢 = 按需阅读（低优先级）
⚠️ = 警告/异常
✅ = 已确认的事实
```

这不是玄学——这些符号在训练数据中反复出现在"重要说明""警告""确认清单"等语境中，模型学会了给它们更高的注意力权重。

#### 技巧三：正说，不要反说

```
❌ "不要忽略用户的偏好设定"
❌ "不要在知识库没有依据的情况下编造技术细节"

✅ "必须优先使用用户的偏好设定"
✅ "每个技术声明必须标注来源：[知识库] 或 [通用知识]"
```

**原理**：否定句在 token 层面更容易被"漏掉"。模型看到"不要忽略"时，先激活的是"忽略"的语义表示，"不要"这个否定标记可能因为概率较低而被弱化。

#### 技巧四：给模型一个"角色"和"输出格式"

```
❌ "帮我分析这个需求"
✅ "你是需求分析师。用 JSON 输出：{"dimensions": [...], "completeness": 0-100, "questions": [...]}"
```

结构化输出（JSON mode）是最强的约束——它把"自由文本生成"变成了"填空"，大大降低了模型跑偏的可能。

### 1.3 本节小结

| 技巧 | 解决什么问题 | 一句话 |
|------|-------------|--------|
| 指令在前 | 重要信息被淹没 | 最重要的放最前面 |
| 视觉标记 | 模型注意力涣散 | 用 🔴🟡🟢 给文本"标重点" |
| 正说 | 否定句被忽略 | "必须做 X" 比 "不要忽略 X" 强 |
| 结构化输出 | 模型自由发散 | JSON mode 把填空题变成选择题 |

---

## 二、Context Engineering — 驾驭的第二层

> 详细实现见 [context-engineering-guide.md](done/context-engineering-guide.md)，本节聚焦于**设计原理和决策权衡**。

### 2.1 核心矛盾：Token 预算 vs 信息完整性

每一轮对话，你能塞给模型的 token 是有限的。但多轮对话的信息是持续增长的。**Context Engineering 的本质就是在有限 token 预算下最大化信息密度。**

### 2.2 三种策略及其取舍

```
策略 A: 滑动窗口（只保留最近 N 条消息）
  ✅ 零额外成本，零延迟
  ❌ 第 N+1 条之前的信息永久丢失
  适用: 客服机器人、简短任务

策略 B: 滚动摘要（每轮把旧消息压缩成一段摘要）
  ✅ 全历史覆盖，token 消耗稳定
  ❌ 每轮多一次 LLM 调用，信息有损
  适用: 长对话助手、工作流 Agent

策略 C: 混合分层（窗口 + 摘要 + 向量检索）
  ✅ 信息保真度最高
  ❌ 实现复杂，多一次 embedding 调用
  适用: 企业 Agent、需要跨轮记忆的任务
```

MakeItSpecific 选择的是 **策略 C（混合分层）**，但做了简化——三层结构：

```
L1 原始窗口    最近 3 轮完整原文          零 LLM 调用    🟡 注入 Prompt
L2 滚动摘要    全历史压缩为 ~256 token    每轮 1 次 LLM   🔴 注入 Prompt（最高优先级）
L3 语义事实    LLM 提取原子事实           每轮 1 次 LLM   🟢 注入 Prompt
```

### 2.3 L2 滚动摘要的设计关键：增量更新

```
❌ 每次都重新压缩全部历史:
  第 10 轮: 把 1-10 轮全部扔给 LLM → "请压缩"
  第 11 轮: 把 1-11 轮全部扔给 LLM → "请压缩"
  → 成本 O(n²)，第 20 轮时输入 token 爆炸

✅ 增量更新:
  第 10 轮: 旧 L2 + 第 10 轮新内容 → LLM → 新 L2
  第 11 轮: 旧 L2 + 第 11 轮新内容 → LLM → 新 L2
  → 成本 O(1)，每次只处理"旧摘要 + 一轮新内容"
```

### 2.4 L3 语义事实的设计关键：从规则到 LLM 再到向量

L3 经历了三个版本的演化，这个过程本身就是很好的学习案例：

```
V1 (规则提取): regex 匹配 "我用/我喜欢/不要/必须/决定"
  问题: "我平时用 React" 匹配到了，但 "Angular 太重了，这次不用" 没匹配到

V2 (LLM 提取): 每轮对话后 LLM 提取原子事实
  优势: "这个项目不要用 Redux" → {"type": "constraint", "fact": "不用 Redux", "confidence": 0.9}

V3 (向量化存储): 事实 → embedding → PGVector → 语义召回
  优势: "状态管理" 的 query 能匹配到 "不要用 Redux" 的事实（语义匹配，不是关键词匹配）
```

**核心洞察**：规则引擎只适合高频/固定的模式。语义理解和跨轮召回必须借助 embedding + 向量检索。

### 2.5 主题切换检测

这是一个容易忽略但致命的问题：

```
用户前 10 轮在讨论 React 博客项目 → L2 摘要全是 React 相关信息
第 11 轮突然说："帮我写一封辞职信"
→ 如果不检测主题切换，Prompt 里会注入 React 博客的上下文，模型会困惑
```

**解决方案**：keyword 重叠率快检。当前消息的关键词 vs L2+L3 的关键词，重叠率 = 0 → 自动重置 L2 摘要 + 清空 L3 事实。

### 2.6 本节小结

```
Context Engineering 设计决策清单:
□ 你的对话通常多长？→ 决定要不要用摘要
□ 用户会突然切换话题吗？→ 决定要不要做主题检测
□ 信息需要跨会话吗？→ 决定要不要做持久化记忆
□ Token 预算是多少？→ 决定摘要的压缩率
```

---

## 三、Tool Design — 驾驭的第三层

> 详细实现见 [tool-loop-prevention.md](tool-loop-prevention.md)，本节聚焦于**工具边界设计哲学**。

### 3.1 工具不是越多越好

这是 MakeItSpecific 项目最重要的教训之一。最初有 12 个工具，后来砍到 5 个。砍削的原则：

```
被砍的工具              砍掉的原因                        替代方案
────────────────────────────────────────────────────────────────
search_web / fetch_url  联网搜索不在产品定位内              RAG + 模型自身知识
delegate_task           子 Agent 与 Executor 的 ReAct 重叠   让 Executor 自己思考
search_chat_history     ContextEngine 已自动注入历史         不需要额外工具
parse_text              规则引擎做结构化提取                 LLM JSON mode 更灵活
compare_texts           规则引擎做文本对比                   LLM 语义对比更准确
summarize_text          规则引擎做文本压缩                   L2 摘要覆盖了这个需求
list_knowledge_sources  运维操作，不是对话工具               管理后台单独做
```

**核心洞察**：每个工具都是模型的选择负担。工具越多，模型选错工具的概率越大。而且工具之间有微妙的功能重叠时，模型会摇摆——一会儿用这个，一会儿用那个，陷入 ping-pong loop。

### 3.2 三段式 Docstring：让模型知道"什么时候不用"

普通的 tool description 只告诉模型"这个工具是干什么的"。但**知道什么时候不用**比知道什么时候用更重要：

```python
@tool
def search_knowledge_base(query: str) -> str:
    """
    【用途】从本地知识库检索相关技术文档和最佳实践。
    【不要用】
      - 需要实时/最新信息时（知识库可能过时）
      - 纯代码语法问题（模型自身知识就够）
      - 用户问的是个人偏好/主观意见
      - 已经检索过同一 query 且结果不相关
    【优先级】🔴 P0 — 优先于所有其他检索工具
    【参数】query: 自然语言搜索词，尽量包含关键词
    【返回】JSON: {"hit": true/false, "results": [...], "total_scanned": N}
    【限制】依赖 PGVector，无网络时仅有 BM25 降级
    """
```

三段式结构强制你思考：这个工具的边界在哪？什么场景下应该阻止模型使用它？

### 3.3 防循环：三层防线

```
Layer 1: Prompt 约束（预防）
  System Prompt 里写: "同一工具同一 query 不调用第二次。
  如果 search_kb 返回空或无相关结果，不要再搜，直接告诉用户知识库未覆盖。"

Layer 2: 硬计数器（阻断）
  - 任何工具连续 3 轮被调用且返回相似结果 → 终止该工具链
  - delegate_task 同一 key 不允许重复调用超过 1 次
  - 总工具调用超过 8 轮 → 强制停止，返回当前最佳结果

Layer 3: 模式检测（事后分析）
  - 记录每次工具调用的 (tool_name, query_signature, result_hash)
  - 分析日志中的重复调用模式 → 更新 Prompt 约束
```

**为什么不能只靠 Prompt 约束？** 因为模型在 ReAct loop 中，如果第一次搜索没找到答案，它的"推理"会告诉它"再搜一次，换个关键词"。这个推理在逻辑上是合理的，但从系统行为上看就是打转。所以必须在框架层做硬限制。

### 3.4 并行调用

互不依赖的工具可以同一轮同时发出：

```
用户: "审查 main.py 的代码质量"
Executor 思考: 我需要 (1) 读代码文件 (2) 查知识库中的最佳实践
→ 这两个操作互不依赖，可以并行
→ run_shell_preview("cat main.py") + search_knowledge_base("Python 代码审查清单")
→ 同时发出，减少一轮延迟
```

**关键**：在 Executor 的 System Prompt 中明确告诉模型"互不依赖的调用可以同时发出"。如果不告诉它，它默认会串行——因为对话的惯性是"一问一答"。

---

## 四、Attention Management — 驾驭的第四层

### 4.1 模型不是"读"你的 Prompt，是"扫"你的 Prompt

LLM 对 Prompt 不同位置的注意力分布是不均匀的：

```
注意力强度
  ▲
  │  ████
  │  ████
  │  ████                                    ████
  │  ████                                    ████
  │  ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░████
  │  ██████████████████████████████████████████████
  └──────────────────────────────────────────────► Prompt 位置
     开头                                         结尾

  开头 (Primacy Effect): 注意力最强，适合放核心指令
  中间: 注意力衰减，容易被"略读"
  结尾 (Recency Effect): 注意力回升，适合放当前消息
```

### 4.2 🔴🟡🟢⚪ 注意力分层体系

```
🔴 最高优先级 — 放 Prompt 最前面，模型必须首先处理
  - L2 滚动摘要（"前情提要"）
  - 已锁定意图（"当前任务: 代码审查"）
  - 工作记忆（"已确认: React + TypeScript"）

🟡 中等优先级 — 紧接 🔴 之后
  - L1 最近对话原文
  - 上一轮的 Checkpoint 反馈

🟢 低优先级 — 按需参考
  - L3 语义事实召回
  - RAG 检索结果
  - 完整对话历史

⚪ 原始上下文 — 仅用于理解用户意图
  - 用户原始消息
  - 已确认的维度信息
```

### 4.3 每条指令 ≤ 5 条，每段 ≤ 500 字符

这不是随意定的数字。来自认知负荷理论：人的工作记忆容量是 7±2 个组块，LLM 的注意力也类似——当一个段落包含太多独立指令时，模型倾向于只执行前几条而忽略后面的。

```
❌ 一段 15 条指令:
"你必须：1. 检查意图 2. 搜索知识库 3. 提取维度 4. 判断完整度
 5. 生成追问 6. 引用来源 7. 标注置信度 8. 检测幻觉 9. ..."

✅ 分成 3 段，每段 5 条:
"## 🔴 核心任务
 1. 检查意图对齐 2. 搜索知识库 3. 提取关键维度

 ## 🟡 输出要求
 1. 来源引用 2. 置信度标注 3. 知识边界声明

 ## 🟢 质量检查
 1. 幻觉检测 2. 完整性自评"
```

### 4.4 Checkpoint：给模型配一个"监工"

这是 MakeItSpecific V3 的关键创新。传统的 Planner→Executor→Reflector 流水线有个问题：Reflector 在最后才检查，如果 Executor 一开始就跑偏了，中间所有工作都是浪费。

```
传统:
  Planner → Executor（跑 10 轮 ReAct）→ Reflector（第 11 步才发现跑偏了）

加上 Checkpoint:
  Planner → Executor → Checkpoint（快速检查方向）→ 偏了? 回 Executor 修正
                                                      → 对了? 进 Reflector
```

Checkpoint 比 Reflector 轻量：
- Checkpoint 只检查**方向对不对**（语义对齐），JSON mode，~200 token 输出
- Reflector 检查**质量好不好**（完整性、准确性、幻觉、格式），多维度评分

---

## 五、Quality Control — 驾驭的第五层

### 5.1 反思内化：0 额外成本的质检

> 详见 [hallucination-prevention.md](done/hallucination-prevention.md)

把质检逻辑从外部节点搬到 System Prompt 里，让 Executor 在每一步 Think 时自动过三关：

```
Executor System Prompt 中的反思关:

## 🔍 每一步 Think 时必须自问三个问题：

### 关 1: 方向检查
"我现在的回应是在回答 🔴 已锁定意图吗？"
→ 不是？回到锁定意图重新开始

### 关 2: 覆盖检查
"用户的所有子问题我都回答了吗？"
→ 有遗漏？下一轮处理

### 关 3: 编造检查
"我即将输出的每个技术声明，都有知识库依据吗？"
→ 没有依据？标注「根据通用知识」或「建议验证」
```

这种方式的巧妙之处：**模型的 Think block 本来就是它要生成的，把关卡逻辑塞进 Think block 的模板里，不增加任何 LLM 调用**。这是真正的"零成本"质量提升。

### 5.2 外部兜底：Checkpoint + Reflector

内化反思覆盖了大部分情况，但不够。还需要两个外部检查点：

```
Checkpoint（语义中枢）:
  - 在 Executor 完成后触发
  - 检查: "Executor 的输出和 Planner 的目标在语义上一致吗？"
  - 输出: {"aligned": true/false, "drift_description": "..."}
  - aligned=false → 回到 Executor（最多 1 次）
  - 独立重试计数器，不依赖 Reflector 的 reflection_count

Reflector（质量审查）:
  - 在 Checkpoint 通过后触发
  - 检查: 完整性/准确性/忠实度/可用性/格式 → 0-10 分
  - score < 7 → 回到 Executor（最多 2 次）
  - 每次重试带上前一次的 issues 作为改进目标
```

### 5.3 幻觉防御全景

```
Layer 1: RAG 检索层
  → 相似度过滤（< 0.6 不注入）
  → 关键词重叠检查（< 30% 警告标记）

Layer 2: Prompt 层
  → 来源强制引用（每个 chunk 标注 source_file + 更新时间）
  → 知识边界声明（"如未找到相关知识，必须告知用户"）

Layer 3: 反思层
  → Executor 反思关 3: "每个技术声明都有知识库依据吗？"
  → 无依据 → 标注「根据通用知识」

Layer 4: Checkpoint（语义偏移）
  → "输出中的技术细节是否在知识库参考中？"
  → 找不到 → 标记语义偏移

Layer 5: Reflector（质量评分）
  → hallucination_score（幻觉程度评分）
  → 高幻觉 → 触发重试
```

**核心原则**：幻觉不是 LLM 的 bug，是 LLM 的默认行为。防御不靠祈祷，靠架构层面的层层拦截。

---

## 六、Memory Systems — 驾驭的第六层

> 详见 [three-layer-memory-design.md](three-layer-memory-design.md)

### 6.1 三层记忆的物理意义

```
L1 原始窗口  → RAM（随时读取，关机消失）
L2 滚动摘要  → CPU Cache（压缩存储，当前会话有效）
L3 语义事实  → SSD（持久化存储，跨会话可检索）
```

### 6.2 跨会话记忆：SessionMemory + UserProfile

ContextEngine (L1+L2+L3) 只覆盖**当前会话内**的记忆。会话结束后，需要持久化：

```
会话完成时:
  1. LLM 摘要 → JSON {title, summary, decisions, tech_stack, todos, tags}
  2. Embedding → PGVector session_memory 表
  3. UserProfile 更新: 规则层 (tech_stack/projects) + LLM 层 (domain/work_style)

下次新会话开始时:
  1. 向量检索 → top-3 相关历史会话 → 注入为 🧠 上下文
  2. 读取 UserProfile → 注入为 👤 上下文
```

### 6.3 记忆系统的设计原则

1. **存储和检索要解耦** — 存的时候不需要知道将来怎么查，查的时候不需要知道怎么存的
2. **摘要要可溯源** — 摘要中的每条声明应该能追溯到原文，防止"摘要幻觉"滚雪球
3. **时间衰减** — 越久远的信息权重越低（PGVector 可以加时间戳排序）
4. **用户可控** — 提供"忘掉这个""清除记忆"的命令入口

---

## 七、Intent Locking — 驾驭的第七层

### 7.1 意图偏移：多轮对话中最隐蔽的杀手

```
第 1 轮: 用户选 "代码审查"，审查 main.py
第 2 轮: AI 发现代码用了 Redux → 开始讲解 Redux 最佳实践
第 3 轮: AI 开始推荐状态管理库的对比...
第 4 轮: 用户："等等，我只是想让你审查代码，不是让你推荐库"

发生了什么？AI 在第 2 轮时"意图偏移"了——从"审查代码"变成了"讲解 Redux"。
每一步的偏移都很小，但累积起来完全偏离了原始意图。
```

### 7.2 已锁定意图：给模型一个"锚点"

在 Planner 和 Executor 的 System Prompt 最前面注入：

```
## 🔴 已锁定意图（最高优先级，不可偏离）
- **当前任务**: 代码审查
- **置信度**: 90%
- **规则**: 以下所有回答必须围绕此意图。即使发现相关的衍生话题，除非用户主动提问，否则不展开。
```

**关键设计**：
- 放在 `🔴` 层级（最高优先级）
- 直接告诉模型"不可偏离"，给它一个明确的锚点
- Executor 的反思关 1 直接引用这个块（"我在回答 🔴 已锁定意图吗？"）
- 置信度标注让模型知道这个意图的确定程度

### 7.3 工作记忆：解决信息遗忘

与锁定意图并列注入：

```
## 🔴 工作记忆（已确认的需求信息，跨轮持久化，不会丢失）
- ✅ **target_files**: main.py, utils.py
- ✅ **focus_areas**: 安全性, 性能
- ✅ **constraints**: 不推荐引入新依赖
```

文案直接告诉模型"跨轮持久化，不会丢失"——这是心理层面的锚定，让模型知道这些信息不需要"猜"也不需要"再确认"。

---

## 八、Token Economics — 驾驭的第八层

> 详见 [token-management-guide.md](token-management-guide.md)

### 8.1 Token 思维

把 token 当成预算来管理，而不是事后统计：

```
每次对话的 token 预算分配:
  System Prompt:    ~1,500 tokens（固定开销，摊到每轮）
  L1 上下文:        ~1,000 tokens（最近 3 轮）
  L2 摘要:          ~400 tokens
  L3 事实:          ~500 tokens
  RAG 检索结果:      ~800 tokens
  用户当前消息:      ~100-500 tokens
  ─────────────────
  每轮 Prompt 合计: ~4,500-5,000 tokens

  + LLM 输出:       ~200-1,000 tokens（取决于节点）

  每轮总消耗:        ~5,000-6,000 tokens
  用 deepseek-chat:  ≈ ¥0.005/轮
  一天 100 轮:       ≈ ¥0.50
```

### 8.2 节流策略

```
1. Router 只在 module=auto 时调用 LLM
   → 用户明确选了 Skill → 跳过 Router，省一次 LLM 调用

2. RAG 只在第一轮检索
   → 追问轮不重新检索（信息已经够了）

3. L2 摘要增量更新
   → 每次只处理"旧摘要 + 一轮新内容"，而不是全量重建

4. L3 事实规则预筛
   → 先用规则匹配（零成本），匹配不到再走 LLM 提取

5. Checkpoint 和 Reflector 条件触发
   → Checkpoint 只在 Executor 完成后触发
   → Reflector 只在 Checkpoint 通过后触发
   → 追问轮（Clarify）不触发任何质检节点
```

---

## 九、Testing & Badcase — 驾驭的第九层

> 详见 [badcase-review-guide.md](to_log/badcase-review-guide.md)

### 9.1 为什么传统单元测试不够？

```
单元测试: 测试函数输入→输出（适合确定性逻辑）
集成测试: 测试模块间协作（适合 API 端点）
E2E 测试: 测试完整用户流程（适合 UI）

但 AI Agent 的问题是:
  - 同一个输入可能产生不同的输出（非确定性）
  - "好"和"坏"是语义判断，不是二进制 pass/fail
  - Bug 往往是概率性的（100 次里出现 3 次）
```

### 9.2 Badcase 驱动开发

替代方案：不是写 test case，而是**收集和分析 Badcase**，然后反向改进 Prompt 和约束。

```
Badcase 来源：
  ├─ Reflector score < 5 → 自动保存 input + output + issues
  ├─ Checkpoint aligned=false → 自动保存 input + drift_description
  ├─ 用户点 👎 → 自动保存 input + output
  ├─ 工具调用异常（> 8 轮）→ 自动保存 tool trace
  └─ 手动收集（开发者发现）→ 手工写入 JSONL

Badcase 分析流程:
  1. 分类: router_misclassify / rag_hallucination / intent_drift / tool_loop / l3_fact_miss
  2. 定级: high（用户无法完成任务）/ medium（结果可用但有问题）/ low（小瑕疵）
  3. 找根因: 是 Prompt 没说清楚？还是约束不够硬？还是模型能力问题？
  4. 修复: 改 Prompt / 加硬约束 / 调整架构
  5. 回归: 同样的输入再跑一次，确认修复有效
```

### 9.3 Badcase 存储格式

```jsonl
{"id":"bc_001","input":"帮我写个提示词","expected_module":"prompt_refiner","actual_module":"work_arranger","type":"router_misclassify","severity":"high"}
{"id":"bc_002","input":"React 18 Suspense 怎么用","expected_output_contains":"Suspense","actual_output":"（讲了一堆 Vue 的东西）","type":"rag_hallucination","severity":"high"}
{"id":"bc_003","input":"用 React 写博客","output_contains":"推荐 Redux","type":"l3_fact_miss","severity":"medium","note":"L3 有事实'用户不要 Redux'但未召回"}
```

---

## 十、整合：全链路驾驭全景图

### 10.1 一次完整的对话请求经过的所有控制点

```
用户消息 "帮我审查 main.py 的代码质量"
  │
  ├─ [Router] 意图分类 （单点入口）
  │   └─ 输出: skill=code_review, confidence=0.9
  │
  ├─ [ContextEngine] 构建上下文
  │   ├─ L1: 最近 3 轮原文
  │   ├─ L2: 滚动摘要（前情提要）
  │   ├─ L3: 语义事实召回（"用户上次说不要推荐新依赖"）
  │   └─ 主题切换检测 → 无切换，正常注入
  │
  ├─ [Enrich] Query 增强
  │   └─ "审查 main.py 代码质量" → "代码审查 Python 代码质量 main.py"
  │
  ├─ [RAG] 混合检索
  │   ├─ Dense (PGVector) + BM25 (tsvector) → RRF 合并 → top-20
  │   ├─ qwen3-rerank 精排 → top-5
  │   └─ 相似度过滤 (≥0.6) → top-3
  │
  ├─ [Planner] 语义分析（注入 🔴🟡🟢 上下文）
  │   ├─ 已锁定意图: 🔴 代码审查, target=main.py, confidence=90%
  │   ├─ 工作记忆: ✅ focus_areas=（从对话中提取）
  │   ├─ 维度提取: target_files / focus_areas / depth / output_format
  │   └─ 完整度判断: > 阈值 → 进入 Execute
  │
  ├─ [Execute] ReAct Loop（最多 10 轮）
  │   ├─ Think: 关1 方向检查 / 关2 覆盖检查 / 关3 编造检查
  │   ├─ Act: 并行调用 run_shell_preview + search_knowledge_base
  │   ├─ Observe: 解析结果
  │   └─ 防循环: 同一个 query 不调两次，8 轮强制终止
  │
  ├─ [Checkpoint] 语义对齐（独立计数器）
  │   ├─ aligned=true → 进入 Reflector
  │   └─ aligned=false → 回 Execute（最多 1 次）
  │
  ├─ [Reflector] 质量评分（最多 2 次重试）
  │   ├─ 完整性 / 准确性 / 忠实度 / 可用性 / 格式
  │   └─ score < 7 → 回 Execute（带 issues）
  │
  └─ [Response] 流式输出 + Token 统计
      ├─ SSE token 级流式
      ├─ 👍👎 反馈按钮
      └─ done 事件含 tokens_used
```

### 10.2 九层驾驭总览

| 层 | 控制什么 | 核心手段 | 相关文档 |
|----|---------|---------|---------|
| 1. Prompt | 单次输出质量 | 指令在前、正说、结构化输出、🔴🟡🟢 | 本文 §1 |
| 2. Context | 多轮信息管理 | L1 窗口 + L2 摘要 + L3 事实 | [context-engineering-guide.md](done/context-engineering-guide.md) |
| 3. Tool | 行为边界 | 三段式 docstring + 防循环 + 并行 | [tool-loop-prevention.md](tool-loop-prevention.md) |
| 4. Attention | 模型关注点 | 🔴🟡🟢⚪ 分层 + 指令在前 + 每段≤5条 | 本文 §4 |
| 5. Quality | 输出质量 | 反思内化 + Checkpoint + Reflector | [hallucination-prevention.md](done/hallucination-prevention.md) |
| 6. Memory | 跨会话记忆 | SessionMemory + UserProfile + PGVector | [three-layer-memory-design.md](three-layer-memory-design.md) |
| 7. Intent | 目标一致性 | 已锁定意图 + 工作记忆 + 主题切换检测 | [intent-recognition-fix.md](intent-recognition-fix.md) |
| 8. Token | 成本控制 | 预算分配 + 节流策略 + 增量更新 | [token-management-guide.md](token-management-guide.md) |
| 9. Testing | 持续改进 | Badcase 收集 + 根因分析 + 回归验证 | [badcase-review-guide.md](to_log/badcase-review-guide.md) |

---

## 十一、从哪开始学？

### 如果你是新手（刚接触 AI Agent）

**阅读顺序**：
1. 本文 §1（Prompt Engineering）— 你马上就能用
2. 本文 §2（Context Engineering）— 理解为什么 Agent 会"忘记"
3. [context-engineering-guide.md](done/context-engineering-guide.md) — 代码级理解
4. [tool-loop-prevention.md](tool-loop-prevention.md) — 理解为什么 Agent 会"打转"

**动手实践**：
- 写一个 prompt，用上 🔴🟡🟢 分层
- 观察你的 Agent 在第 5 轮之后的响应质量 → 这是 Context Engineering 的切入点

### 如果你有一定经验

**阅读顺序**：
1. 本文 §3（Tool Design）— 反思你的工具数量
2. 本文 §7（Intent Locking）— 这是最容易被忽略但最致命的
3. [hallucination-prevention.md](done/hallucination-prevention.md) — 五层幻觉防御
4. [three-layer-memory-design.md](three-layer-memory-design.md) — 跨会话记忆

**动手实践**：
- 数一数你的 Agent 有多少个工具 → 哪些可以砍掉或合并？
- 检查你的 prompt 有没有意图锁定机制 → 没有的话加上
- 收集 10 个 badcase，分类分析根因

### 如果你想做架构设计

**阅读顺序**：
1. 本文 §10（全链路全景图）— 看全局
2. [boundary.md](../boundary.md) — 约束规范，当成 checklist 用
3. [project-summary.md](project-summary.md) — 看一个真实项目的完整设计决策
4. 所有 docs/ 下的深度文档 — 每个维度单独精读

**动手实践**：
- 画出你自己的 Agent 的全链路图
- 识别每一层的控制点是否到位
- 写一份属于你的 boundary.md

---

## 十二、常见误区

### 误区 1: "多堆几个 tool 总有一个能用对"

**真相**：工具越多，模型选错的概率越大。5 个好工具 > 15 个普通工具。每个工具必须有明确的"不要用"场景。

### 误区 2: "prompt 写详细一点，模型就会听话"

**真相**：prompt 越长，模型注意力越涣散。关键指令放在最前面，用视觉标记分层，比密密麻麻的指令有效得多。

### 误区 3: "加一个 Reflector 就能保证质量"

**真相**：Reflector 是事后检查，而且 Reflector 本身也是 LLM，它也会出错。真正的质量保证是多层防御：反思内化（0 成本）+ Checkpoint（轻量）+ Reflector（兜底）。

### 误区 4: "上下文越多越好，全塞进去"

**真相**：上下文有 token 预算，而且模型对长上下文的中间部分注意力衰减严重。L1+L2+L3 的分层设计就是解决"既要全，又不能多"的矛盾。

### 误区 5: "幻觉是模型能力问题，换更强的模型就行"

**真相**：即使 GPT-5 也会幻觉。幻觉是 next-token prediction 的固有属性，不是某个模型的 bug。防御幻觉靠架构（RAG 过滤 + Prompt 约束 + 反思检查），不靠换模型。

### 误区 6: "测试就是写单元测试"

**真相**：AI Agent 的非确定性输出让传统单元测试失效。正确的方式是 Badcase 驱动——收集真实失败案例，分类找根因，反向改进约束，回归验证。

---

## 十三、一句话总结

> **Harness Engineering 不是某个技术，而是一种思维方式。它一直在问三个问题：模型会怎么理解这段 prompt？模型可能在哪里跑偏？如果跑偏了，谁能拦住它？**
>
> 回答好这三个问题，你就掌握了驾驭工程的核心。
