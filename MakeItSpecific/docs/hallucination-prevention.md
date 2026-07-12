# Hallucination Prevention Guide -- 幻觉从哪来、怎么层层拦截

> 从「模型为什么胡说」到「每一层怎么拦住」，系统性地理解和防御 AI 幻觉。
>
> 核心原则：**幻觉不是 LLM 的 bug，而是 LLM 的默认行为。防御不是一次性的事，是架构层面的持续对抗。**

---

## 一、先理解幻觉：四种类型

AI 幻觉不是单一的「胡说八道」。在 MakeItSmooth 这个 AI 工作流增强 Agent 的场景下，幻觉可以按来源和表现分为四种类型。

### 1.1 RAG 幻觉 -- 无视知识库，自由发挥

**定义**：知识库已经检索到了相关内容，但模型在生成回复时完全无视检索结果，凭自己的预训练记忆或「语感」自由输出。

**真实场景**：

```
用户选「工作安排规划师」，说："我想做一个知识管理工具，帮我设计架构"

RAG 检索结果 (score 0.82):
  "### 知识点 1 (来源: workflow_best_practices.md)
   任务分解最佳实践: 1. 先定义 MVP 范围 2. 列出核心功能 3. 估算时间..."

模型输出:
  "推荐使用 Next.js 14 + tRPC + Prisma + PlanetScale + Upstash Redis..."
  ↑ 这一整套技术栈推荐在知识库中完全没有依据！
  ↑ 而且用户根本没说是 Web 应用还是 CLI 工具
  ↑ 这就是典型的「RAG 幻觉」-- 模型记住了检索结果存在，但选择了忽略它
```

**根本原因**：LLM 的预训练分布和当前 RAG 上下文之间存在竞争。当检索结果和模型「习惯性回答」差距较大时，模型倾向于选择后者。

### 1.2 推断幻觉 -- 从知识库中过度推断不存在的信息

**定义**：模型确实引用了知识库内容，但在此基础上做了「创造性延伸」，推断出了知识库中不存在的信息。这种幻觉比 1.1 更隐蔽，因为它看起来有根有据。

**真实场景**：

```
知识库内容:
  "CoT (Chain-of-Thought) 思维链技术: 要求模型在最终回答前展示推理步骤，
   适用于数学推理、逻辑推理、多步决策等场景。"

模型输出（引用了知识库）:
  "根据知识库，CoT 思维链技术由 Google Brain 团队于 2022 年 1 月在论文
   'Chain-of-Thought Prompting Elicits Reasoning in Large Language Models'
   中首次提出，实验表明在 GSM8K 基准上准确率从 17.7% 提升到 58.1%..."
  ↑ 论文信息、时间、具体数字 -- 知识库里一个都没有！
  ↑ 模型从「CoT 是思维链技术」这个基本事实推断出了一整套论文引述
  ↑ 虽然推理方向是对的，但具体信息是编造的
```

**根本原因**：模型有强烈的「补全」倾向 -- 当知识库给了它一个方向的线索，它就想把剩下的细节也补上。这和人类的「脑补」行为非常相似。

### 1.3 时效幻觉 -- 知识库过时但未经校验就输出

**定义**：知识库中的信息已经过时，但模型没有能力判断时效性，当作当前事实输出。

**真实场景**：

```
知识库 (tech_news.md，3 个月前写入):
  "OpenAI 最近发布了 GPT-4o 模型，支持多模态输入..."

模型输出（3 个月后，GPT-5 已发布）:
  "目前最先进的 OpenAI 模型是 GPT-4o..."
  ↑ 知识库没有更新，模型也「诚实」地引用了过时信息
  ↑ 模型不会说「我引用的信息是 3 个月前的，以当前时间为准可能已过时」
```

**根本原因**：LLM 的预训练有截止日期，而 RAG 知识库的更新时间通常滞后。当用户问「最新」或「现在」时，两个时间源都不足以回答。模型缺乏「信息时效性意识」。

### 1.4 格式幻觉 -- 编造不存在的 API/函数名/版本号

**定义**：模型在生成结构化输出（代码、API 调用、配置）时，编造了看起来合理但实际不存在的函数名、参数或版本号。

**真实场景**：

```
用户: "帮我写一个 LangChain 的 RAG pipeline 代码"

模型输出:
  ```python
  from langchain.retrievers import HybridRetriever  # ← 不存在！
  from langchain.rerankers import CohereReranker    # ← 不存在！

  retriever = HybridRetriever(
      dense_retriever=PineconeRetriever(...),
      sparse_retriever=BM25Retriever(...),
      fusion_method="reciprocal_rank_fusion",       # ← 参数名是编的
  )
  ```
  ↑ 这些 API 名「听起来像真的」但实际 LangChain 里没有
  ↑ 一个有经验的开发者一眼能看出，但 AI 助手面向的用户不一定
```

**根本原因**：代码相关的问题在 LLM 训练数据中占比很高，模型对「代码应该长什么样」的分布很强。但当它尝试组合多个库的 API 时，很容易张冠李戴 -- 从库 A 借一个函数名，从库 B 借一个参数风格，拼出一个不存在的 API。

### 1.5 四种幻觉的严重程度和频率

| 类型 | 频率 | 危害 | 可检测性 | 典型触发条件 |
|------|------|------|---------|------------|
| **RAG 幻觉** | 中 | 高 -- 直接输出错误信息 | 中 -- 对比 rag_context 可发现 | 检索结果和预训练知识冲突 |
| **推断幻觉** | 高 | 中 -- 部分正确部分错误 | 低 -- 需要逐声明核查 | 知识库只给了方向性线索 |
| **时效幻觉** | 低 | 中 -- 信息过时但不一定错 | 中 -- 检查知识库写入时间 | 用户问「最新」「现在」 |
| **格式幻觉** | 高 | 高 -- 代码直接报错 | 高 -- 代码执行可验证 | 跨库 API 组合、新版本 API |

---

## 二、当前项目已有的防御（现状分析）

在写新的防御之前，先盘点 MakeItSmooth 已经做了哪些事。以下全部来自代码实际实现。

### 2.1 检索层: 相似度阈值过滤 + Rerank + 关键词加权

**位置**: `services/rag_service.py`

```python
# config.py -- 可配置阈值
similarity_threshold: float = 0.6

# rag_service.py -- 实际过滤逻辑
class RAGService:
    COLLECTION = "domain_knowledge"
    SIMILARITY_THRESHOLD = 0.6

    async def query(self, query_text: str, top_k: int = 3,
                    min_score: float = None) -> list[dict]:
        if min_score is None:
            min_score = self.similarity_threshold
        # ...
        # 最终过滤:
        results = [
            r for r in merged
            if (r.get("score", 0) >= min_score or r.get("rerank_score", 0) >= 0.3)
        ]
        # 关键词重叠加权
        return self._apply_keyword_boost(query_text, results)
```

**混合检索 pipeline（已实现）**:
```
Dense 检索 (PGVector cosine distance) → coarse_k 候选
BM25 检索 (PG tsvector)               → coarse_k 候选
    ↓
RRF 合并 → top-(coarse_k)
    ↓
Rerank (qwen3-rerank) → top-k
    ↓
相似度阈值过滤 (min_score ≥ 0.6)
    ↓
关键词重叠加权 → 最终排序
```

**效果**: 不相关内容在注入 prompt 之前就被拦截。低于阈值（0.6）的 chunk 直接被丢弃，即使检索引擎返回了它。

**覆盖**: 防御类型 1（RAG 幻觉）的源头 -- 不让不相关内容进入模型视野。

### 2.2 Prompt 层: 来源引用要求 + 知识边界声明

**位置**: `prompts/system_prompts.py` -- `EXECUTOR_SYSTEM_PROMPT`

```python
## 知识库使用规则（必须遵守）
- 你的回答必须基于提供的知识库内容
- 如果知识库未覆盖某个话题，请明确说明「知识库中暂无相关信息」
- 每条关键技术建议必须注明来源（参考知识块中标注的「来源」文件名）
- 不要编造知识库中不存在的数据、API 名称、版本号
- 如果对某个细节不确定，使用 ⚠️ 标记并建议用户查阅官方文档
```

**位置**: `services/rag_service.py` -- `query_formatted()` 方法

```python
async def query_formatted(self, query_text: str, top_k: int = 3) -> str:
    # ...
    if not results:
        return "（未找到相关知识。以下回答基于通用知识，可能不准确。）"

    lines = [
        "## 🔴 知识库参考", "",
        "以下信息必须作为回答的基础:", "",
    ]
    for i, r in enumerate(results, 1):
        source = r.get("metadata", {}).get("source_file", "未知来源")
        lines.append(f"### 知识点 {i} (来源: {source})")
        lines.append(r["document"])
        lines.append("")

    lines.append("**规则: 基于以上内容回答。如知识库未覆盖请明确说明。不要编造知识库中不存在的信息。**")
    return "\n".join(lines)
```

**效果**: 三管齐下 -- 知识库未命中时主动声明边界、命中时要求逐条标注来源、不确定时标记 ⚠️。

**覆盖**: 防御类型 1（RAG 幻觉）+ 类型 2（推断幻觉）的 Prompt 层约束。

### 2.3 Checkpoint 层: 语义对齐 + 幻觉检测

**位置**: `core/graph.py` -- `checkpoint_node()` 和 `PLANNER_CHECKPOINT_PROMPT`

这是 V3 架构中 Planner 升级的核心机制。每次 Executor 完成输出后，Checkpoint 节点介入：

```python
PLANNER_CHECKPOINT_PROMPT = """你是语义对齐审核员。检查执行结果是否与用户原始意图一致。

## 审核标准
- **语义对齐**: 输出的内容是否回答了用户真正在问的问题？有没有答非所问？
- **意图偏移**: 执行过程中是否偏离了 Planner 最初设定的目标？
- **知识库忠实度**: 输出中的技术声明是否能在提供的知识库参考中找到依据？
  有没有编造知识库中不存在的信息？
- **遗漏**: 用户的多个子问题是否都覆盖了？

## 输出格式
只输出 JSON:
{
  "aligned": true/false,
  "score": 0-10,
  "drift_description": "如果有偏移，描述偏移了什么（未偏移则为空）",
  "correction": "如果未对齐，给出明确的修正方向（空则无需修正）",
  "hallucination_detected": false,
  "hallucination_details": []
}
"""
```

Checkpoint 的实际执行逻辑（`graph.py` `checkpoint_node`）：

```python
async def checkpoint_node(state: AgentState, model=None) -> dict:
    """
    Planner 语义中枢 -- 每次 Executor 完成后介入，检查语义对齐。

    与 Reflector 的分工:
    - Checkpoint: 检查「方向对不对」（语义对齐）-- 快速，单次 LLM
    - Reflector:  检查「质量好不好」（完整性、准确性）-- 更深，包含评分
    """
    # ...
    # 将知识库参考 + 原始目标 + Executor 输出一并提交给 LLM 审核
    checkpoint_prompt = f"""{PLANNER_CHECKPOINT_PROMPT}

## Planner 设定的原始目标
{plan.get('goal', '完成用户请求')}

## 用户的原始消息
{message}

## 知识库参考（判断技术声明是否有依据）
{rag_brief}

## Executor 的实际输出（前 1500 字符）
{output[:1500]}"""

    structured_model = model.bind(response_format={"type": "json_object"})
    response = await structured_model.ainvoke([...])
    checkpoint = _parse_checkpoint_json(response.content)

    if checkpoint.get("aligned", True):
        return {"checkpoint_feedback": ""}
    else:
        # 未对齐 → 返回修正意见 → graph 路由回 execute 重试
        return {
            "checkpoint_feedback": correction,
            "checkpoint_retry_count": checkpoint_retry_count + 1,
        }
```

**效果**: 每次 Executor 完成后，用一个独立的 LLM 调用来做「事后诸葛亮」式的审核。具体检查 `hallucination_detected` 字段 -- 如果发现编造的知识库外信息，标记并报告。

**覆盖**: 防御类型 1（RAG 幻觉）+ 类型 2（推断幻觉）的生成后核查。

### 2.4 Reflector 层: 质量审查 + 幻觉字段

**位置**: `core/graph.py` -- `reflect_node()` 和 `prompts/system_prompts.py` -- `REFLECTOR_SYSTEM_PROMPT`

```python
REFLECTOR_SYSTEM_PROMPT = """你是一个质量审核助手。

## 审核标准
- **完整性**: 是否回答了用户的所有问题？是否有遗漏？
- **准确性**: 信息是否正确？有无明显错误或过时信息？
- **忠实度**: 有没有编造知识库中不存在的信息？技术声明是否有依据？
- **可用性**: 用户能直接使用这个输出吗？还是需要再加工？
- **格式**: 是否使用了合适的 Markdown 格式？结构是否清晰？

## 输出格式
你必须以 JSON 格式输出：
{
  "pass": true/false,
  "score": 0-10,
  "issues": ["发现的问题"],
  "suggestions": ["改进建议"],
  "verdict": "通过 / 需要重试 / 需要补充信息",
  "hallucination_detected": false,
  "hallucination_details": []
}
"""
```

Reflector 的实际执行逻辑（`graph.py` `reflect_node`）：

```python
async def reflect_node(state: AgentState, model=None) -> dict:
    # ...
    reflect_prompt = f"""{REFLECTOR_SYSTEM_PROMPT}

## 用户原始需求
{message}

## 期望完成的目标
{plan.get('goal', '完成用户请求')}

## 知识库参考（判断技术声明是否有依据）
{rag_brief}

## 实际输出（前 2000 字符）
{output[:2000]}"""

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

**效果**: Reflector 在 Checkpoint 之后做「二次检查」，更关注质量和完整性。同样包含 `hallucination_detected` 字段，形成了一个 double-check 机制。

**覆盖**: 防御类型 1-3 的综合质量把关。如果 Checkpoint 漏过了某个幻觉，Reflector 还能再查一次。

### 2.5 反馈收集层: Badcase 源头

**位置**: `routers/feedback.py`

```python
# feedback 表结构
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    message_id INTEGER DEFAULT 0,
    rating TEXT NOT NULL,          -- positive | negative | neutral
    comment TEXT DEFAULT '',
    skill TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
)
```

**目前的局限**: 反馈表只存了 rating + comment + skill，没有存当时的 RAG chunks 和完整输出。用户点 👎 之后无法回溯「到底是什么让用户不满意」-- 缺少 badcase 自动保存机制。

### 2.6 已有防御汇总

```
┌─────────────────────────────────────────────────────────────────────┐
│                        幻觉防御现状总览                               │
├──────────┬────────────────────────┬──────────────┬──────────────────┤
│   层级    │       机制              │    文件       │      状态         │
├──────────┼────────────────────────┼──────────────┼──────────────────┤
│  检索前   │ enriched_query 上下文   │ context_      │ ✅ 已实现         │
│          │ 驱动短 query 组合       │ engine.py     │   不扩写，只组合   │
├──────────┼────────────────────────┼──────────────┼──────────────────┤
│  检索中   │ Dense + BM25 混合检索   │ rag_service.py│ ✅ 已实现         │
│          │ + RRF 合并              │              │   多路互补         │
├──────────┼────────────────────────┼──────────────┼──────────────────┤
│  检索后   │ Rerank (qwen3-rerank)   │ rag_service.py│ ✅ 已实现         │
│          │ 相似度阈值 (≥0.6)       │              │   ✅ 已实现       │
│          │ 关键词重叠加权           │              │   ✅ 已实现       │
├──────────┼────────────────────────┼──────────────┼──────────────────┤
│  Prompt  │ 来源引用要求              │ system_       │ ✅ 已实现         │
│          │ 知识边界声明              │ prompts.py    │   ✅ 已实现       │
│          │ ⚠️ 不确定性标记          │              │   ✅ 已实现       │
├──────────┼────────────────────────┼──────────────┼──────────────────┤
│  生成后   │ Checkpoint 语义对齐      │ graph.py      │ ✅ 已实现         │
│          │   (含 hallucination      │              │   每次 execute    │
│          │    _detected 字段)       │              │   后介入          │
│          │ Reflector 质量审查        │ graph.py      │ ✅ 已实现         │
│          │   (含 hallucination      │              │   double-check   │
│          │    _detected 字段)       │              │                   │
├──────────┼────────────────────────┼──────────────┼──────────────────┤
│  反馈    │ 👍👎 用户反馈             │ feedback.py   │ ⚠️ 基础版         │
│          │ Badcase 自动收集          │ -            │ ❌ 缺失           │
│          │ 知识库覆盖分析            │ -            │ ❌ 缺失           │
└──────────┴────────────────────────┴──────────────┴──────────────────┘
```

---

## 三、设计思路：四层防线

幻觉防御不是加一个检查点，而是沿着数据的流动路径在每一层设卡。

```
用户消息
    │
    ▼
┌─────────────────────────────────────────┐
│ 第 1 层: 检索时过滤                       │
│ 不注入不相关内容                          │
│ ├─ 相似度阈值 (≥0.6)                     │
│ ├─ Rerank 精排                           │
│ ├─ 关键词重叠检查                         │
│ └─ 低相似度降级 (全部 <0.5 → 拒绝注入)     │
│                                          │
│ 捕获: RAG 幻觉的源头                      │
│ 漏过: 知识库本身有错 / 过度推断            │
└────────────────────┬────────────────────┘
                     │ rag_context
                     ▼
┌─────────────────────────────────────────┐
│ 第 2 层: Prompt 中约束                    │
│ 告诉模型怎么用检索结果                     │
│ ├─ 来源强制引用                           │
│ ├─ 知识边界声明                           │
│ ├─ ⚠️ 不确定性标记                        │
│ └─ 禁止编造 API/版本号                    │
│                                          │
│ 捕获: 守规矩的模型会遵守                   │
│ 漏过: 不守规矩的模型 / 复杂上下文          │
└────────────────────┬────────────────────┘
                     │ system prompt + output
                     ▼
┌─────────────────────────────────────────┐
│ 第 3 层: 生成后核查                       │
│ Checkpoint + Reflector 双重审查           │
│ ├─ 语义对齐检查（方向对不对）              │
│ ├─ 知识库忠实度检查（技术声明有依据吗）      │
│ ├─ 幻觉检测字段 (hallucination_detected)   │
│ └─ 不通过 → correction → execute 重试     │
│                                          │
│ 捕获: 已生成但不符合约束的输出              │
│ 漏过: LLM 审查也看不出的精细幻觉           │
└────────────────────┬────────────────────┘
                     │ final output
                     ▼
┌─────────────────────────────────────────┐
│ 第 4 层: Badcase 自动收集                 │
│ 反馈闭环驱动迭代                          │
│ ├─ 👎 → 自动保存 input+output+RAG chunks  │
│ ├─ Reflector score < 5 → 自动保存         │
│ ├─ 知识库未覆盖类错误 → 提醒补充知识库      │
│ └─ Badcase 分析 → 改进 Prompt/阈值/知识库  │
│                                          │
│ 捕获: 前 3 层都漏过的 badcase             │
│ 漏过: 用户不点反馈的 case                  │
└─────────────────────────────────────────┘
```

### 3.1 第 1 层: 检索时过滤 -- 不注入不相关内容

**做什么**: 在检索结果注入 prompt 之前，尽可能过滤掉不相关的内容。核心逻辑是「宁可少给，不可给错」。

**怎么做的** (已实现):
1. 相似度阈值过滤 -- cosine similarity < 0.6 的 chunk 直接丢弃
2. Rerank 精排 -- 粗筛 20 个候选，Rerank 后只取 top-5，再过滤 top-3
3. 关键词重叠加权 -- 对含 query 核心术语的 chunk 微调加分

**捕获什么**: RAG 幻觉的源头 -- 不相关内容不进入模型视野，模型就没有机会「无视正确知识」。

**漏过什么**:
- 知识库本身有错误 -- 内容相关但信息是错的
- 模型过度推断 -- 内容相关但模型在此基础上发挥
- 高相似度但不精准的匹配 -- 语义接近但回答不了具体问题

### 3.2 第 2 层: Prompt 中约束 -- 告诉模型怎么用检索结果

**做什么**: 在 System Prompt 中明确指令模型如何使用知识库、何时承认不知道、如何标注不确定性。

**怎么做的** (已实现):
1. 「必须基于提供的知识库内容回答」
2. 「如知识库未覆盖请明确说明」
3. 「每条关键技术建议注明来源」
4. 「不确定时用 ⚠️ 标记并建议查官方文档」

**捕获什么**: 对遵守 System Prompt 的模型（大部分主流模型），这些约束直接抑制了幻觉倾向。

**漏过什么**:
- 上下文过长时，模型对 System Prompt 的注意力衰减
- 复杂任务中，模型可能「忘记」来源引用规则
- 模型存在系统性的「自信偏差」-- 即使提示了要用 ⚠️，模型仍然倾向于给出确信的答案

### 3.3 第 3 层: 生成后核查 -- Checkpoint + Reflector

**做什么**: 生成完成后，用独立的 LLM 调用来检查输出是否存在幻觉。这是 Prompt 约束的补充 -- Prompt 告诉模型怎么做，Checkpoint 检查模型做得怎么样。

**怎么做的** (已实现):
```
Checkpoint（快，单次 LLM):
  检查: 语义对齐 + 知识库忠实度 + hallucination_detected
  路由: aligned=false → execute 重试 (最多 1 次)
        aligned=true  → Reflector

Reflector（深，包含评分):
  检查: 完整性 + 准确性 + 忠实度 + hallucination_detected
  路由: pass=false → execute 重试 (最多 2 次)
        pass=true  → END
```

**捕获什么**:
- Checkpoint 捕获明显的方向性错误和知识库偏离
- Reflector 捕获更细微的质量问题和事实错误
- 两个节点各自独立调用一次 LLM，等于做了一次 double-check

**漏过什么**:
- LLM 检查 LLM 的局限性 -- 如果检查用的 LLM 也有知识盲区，可能漏判
- 精细的推断幻觉 -- 「部分是知识库的内容，部分是模型推断的」这种情况最难判断
- 时效性幻觉 -- 检查用的 LLM 也不知道「现在」是什么时候

### 3.4 第 4 层: Badcase 自动收集 -- 反馈闭环

**做什么**: 当前只有基础的 👍👎 收集（存 SQLite），缺失的是自动 badcase 保存和知识库覆盖分析。

**为什么重要**: 前 3 层是「预防性」的 -- 在你看到问题之前就尽力拦截。但总有些 case 会漏过。第 4 层是「响应性」的 -- 把漏过的 case 收集起来，分析根因，改进前 3 层。

**当前状态**:

| 能力 | 状态 | 说明 |
|------|------|------|
| 用户手动 👍👎 | ✅ | `routers/feedback.py` |
| 自动保存 badcase 上下文 | ❌ | 没有保存当时的 RAG chunks、完整输出 |
| Reflector score 自动触发 | ❌ | score < 5 的 case 应该自动保存 |
| 知识库覆盖分析 | ❌ | 不知道哪些 query 在知识库里没匹配到 |
| Badcase → 改进闭环 | ❌ | 收集了但不知道怎么用 |

---

## 四、Layer 3 深入：事实核查的 ReAct 本质

### 4.1 Checkpoint 和 Reflector 不只是「检查」，是一个外层 ReAct 循环

幻觉防御中最容易被误解的一点是：Checkpoint 和 Reflector 不是在「做质量检查」，它们在执行一个**外层 ReAct 循环**。

```
┌────────────────────────────────────────────────────────────────┐
│                    工具级 ReAct (Executor 内部)                  │
│                                                                │
│  Observe ─── tool 返回的结果                                    │
│    │                                                           │
│  Reason ─── "这个结果够吗？还需要什么信息？"                      │
│    │                                                           │
│  Act    ─── 调用下一个 tool / 生成最终输出                       │
│    │                                                           │
│    └── 循环，最多 10 轮                                         │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                质量级 ReAct (Checkpoint → Reflector)             │
│                                                                │
│  Observe ─── Executor 完整 output + rag_context + 原始 query    │
│    │                                                           │
│  Reason ─── Checkpoint Prompt:                                 │
│             "输出中的技术声明在知识库中有依据吗？                  │
│              语义方向和 Planner 原始目标一致吗？"                 │
│    │                                                           │
│  Act    ─── hallucination_detected=true → correction →          │
│             execute 重试 (带修正方向)                            │
│          ─── aligned=true → 进入 Reflector                      │
│    │                                                           │
│    └── Reflector 再次 Observe → Reason → Act:                   │
│              pass=false → execute 重试                          │
│              pass=true → END                                   │
└────────────────────────────────────────────────────────────────┘
```

### 4.2 两层 ReAct 的对应关系

这是一个分形结构 -- 内层和外层在做相同的事情，只是粒度不同：

| 维度 | 工具级 ReAct (Executor) | 质量级 ReAct (Checkpoint+Reflector) |
|------|------------------------|-------------------------------------|
| **Observe** | Tool 返回的即时结果 | Executor 的完整输出 + 知识库 + 原始意图 |
| **Reason** | "还需要什么信息？" | "输出合格吗？有没有幻觉？" |
| **Act** | 调用工具 / 输出 | 修正重试 / 通过 / 拒绝 |
| **粒度** | 单个 tool call | 完整 exec 输出 |
| **目标** | 完成当前子任务 | 保证最终输出质量 |
| **反馈回路** | tool result → next action | checkpoint_feedback → execute 重试 |

### 4.3 这意味着什么

**幻觉防御不是一个「功能」，而是 Agent 架构的固有属性。**

一个好的 Agent 循环天然具备抗幻觉能力，因为它的每一步都在做 Observe → Reason → Act。幻觉之所以会产生，是因为某一步的 Reason 不够好。防御幻觉的方法不是加一个「幻觉检测模块」，而是加强每一步的 Reason 能力。

在 MakeItSmooth 的 V3 架构中，这意味着：
- Planner 做第一层 Reason（需求理解）
- Executor 做第二层 Reason（工具调用决策）
- Checkpoint 做第三层 Reason（语义对齐审核）
- Reflector 做第四层 Reason（质量最终把关）

每一层都可能发现并纠正上一层的幻觉。

### 4.4 流程示意

```
START → router → enrich → rag → planner
                                    │
                    ┌───────────────┼───────────────┐
                    ▼                               ▼
                clarify → END              execute (ReAct loop)
                                               │
                                               ▼
                                          checkpoint
                                          "技术声明有依据吗？"
                                               │
                                    ┌──────────┼──────────┐
                                    │                      │
                               aligned=false          aligned=true
                                    │                      │
                                    ▼                      ▼
                              execute 重试             reflect
                              (带 correction)         "完整性够吗？"
                                                          │
                                               ┌──────────┼──────────┐
                                               │                      │
                                          pass=false            pass=true
                                               │                      │
                                               ▼                      ▼
                                         execute 重试                END
```

---

## 五、Code Landing: 可以立刻加的三道防线

### 5.1 防线 1: Output fact-check prompt 升级 (~15 行)

**当前 Prompt 的问题**：Checkpoint 的 hallucination 检测是二元的（`hallucination_detected: true/false`），但缺少对「具体哪个声明可能是假的」的指引。

**升级方案** -- 在 `PLANNER_CHECKPOINT_PROMPT` 中添加逐声明核查指令：

```python
# 在 graph.py 的 PLANNER_CHECKPOINT_PROMPT 中追加:

## 逐声明事实核查
对 AI 输出中的每个关键技术声明，逐一判断:
- 声明是否在知识库中有明确依据？ → 标注 "✅"
- 声明超出知识库范围但属于常识？ → 标注 "⚠️ 常识推断"
- 声明明显超出知识库范围且无法验证？ → 标注 "❌ 可能幻觉"

## hallucination_details 格式
每个怀疑的幻觉声明必须包含:
{
  "claim": "被怀疑的具体声明文本",
  "evidence_in_kb": "在知识库中查找了但没有找到对应内容",
  "severity": "high / medium / low",    ← 影响程度
  "suggestion": "建议删除 / 替换为 / 标注不确定"
}

## Hallucination severity 定义
- high: 如果用户按这个信息操作，会导致错误结果 (如编造不存在 API)
- medium: 信息可能不对，但不影响核心结论
- low: 装饰性信息，是否准确影响不大
```

**改动位置**: `core/graph.py` 的 `PLANNER_CHECKPOINT_PROMPT`。
**预计行数**: ~15 行。
**效果**: 从「有没有幻觉」的二元判断升级为「哪个具体声明可能有问题」的逐条分析。

### 5.2 防线 2: Low-confidence marker system -- 不确定性分层标记

**当前状态**：Prompt 里有「不确定时用 ⚠️」的指令，但没有明确的不确定性分级。

**升级方案** -- 在 Executor Prompt 中添加三级不确定性标记：

```python
# 在 EXECUTOR_SYSTEM_PROMPT 中追加:

## 不确定性标记规则（必须遵守）
对每个技术声明，按确定程度标记:
- 🟢 确定: 知识库中明确有依据 → 正常输出
- 🟡 推断: 知识库给了方向但没直接说，基于常识推断 → 用 *斜体* 包裹 + 标注「（基于常识推断）」
- 🔴 不确定: 知识库完全未涉及 → 用 ⚠️ 开头 + 标注「（知识库未覆盖，建议查阅官方文档）」

## 示例
- 🟢 "CoT 思维链适用于数学推理和多步决策" ← 知识库中有
- 🟡 "*建议将角色扮演与 CoT 结合使用*（基于常识推断）" ← 知识库没直接说
- 🔴 "⚠️ React 19 引入了新的 use() hook（知识库未覆盖，建议查阅 React 官方文档）"
  ← 知识库没有 React 相关内容
```

**覆盖**: 让用户能看到模型的「确定程度」，即使模型出错，用户也知道哪些该信、哪些需要验证。

### 5.3 防线 3: Knowledge boundary declaration -- 知识库覆盖情况声明

**当前状态**：`query_formatted()` 在知识库未命中时返回 `"（未找到相关知识）"`，但没有告知用户知识库覆盖了什么、没覆盖什么。

**升级方案** -- 在 RAG 结果中附加覆盖声明：

```python
# 在 rag_service.py 的 query_formatted() 中添加:

async def query_formatted(self, query_text: str, top_k: int = 3) -> str:
    results = await self.query(query_text, top_k)
    if not results:
        # ── 升级: 不仅说「没找到」，还说「我只有这些知识」 ──
        kb_files = await self.get_kb_stats()
        file_list = ", ".join(kb_files.get("file_names", ["无"]))
        return (
            f"## 🔴 知识库参考\n\n"
            f"（知识库中未找到与「{query_text[:50]}」直接相关的内容。）\n\n"
            f"### 当前知识库覆盖范围\n"
            f"共 {kb_files['source_files']} 篇文档: {file_list}\n\n"
            f"**规则: 以下回答将基于通用知识，可能不准确。**\n"
            f"**建议: 在 /api/knowledge 中补充相关领域的 .md 文件以提高准确性。**"
        )

    # ... 正常流程
```

**覆盖**: 防御类型 1（RAG 幻觉）+ 类型 3（时效幻觉）。告诉用户知识库的覆盖边界，让用户自行判断模型输出的可信度。

---

## 六、常见问题

### Q: Rerank 能防幻觉吗？

不能直接防。Rerank 的作用是**提升检索精度**，让更多相关内容、更少不相关内容进入 prompt。这降低了「模型被迫胡说」的概率，但它不检查模型是否胡说。Rerank 解决的是「输入质量问题」，不是「输出质量问题」。

类比：Rerank 是帮你在图书馆找到正确的书，但不保证你读懂之后写的读书报告是准确的。

### Q: 相似度阈值设多少合适？

当前项目使用 0.6，这是一个经过 trade-off 的值。

```
阈值 = 0.8: 精度极高，但可能漏掉相关内容（召回率骤降）
            → 用户问 "React Suspense" 可能找不到，因为知识库里没有专门讲 React 的文档

阈值 = 0.6: 精度和召回率的平衡点 (当前值)
            → 能过滤掉明显不相关的 chunk，同时保留语义接近但用词不同的内容

阈值 = 0.4: 召回率高，但大量不相关内容注入
            → 模型看到太多噪音，反而更容易产生幻觉
```

调参建议：如果知识库只有 3 篇（当前状态），0.6 偏低 -- 因为检索空间小，相关性容易漂移。建议在知识库补齐到 10 篇后再根据 badcase 数据调整。

### Q: 怎么知道知识库覆盖了多少？

目前没有覆盖分析工具。一个简单的评估方法：

```python
# 手动评估: 收集 20 个典型用户 query，逐个检索，看命中率
test_queries = [
    "帮我优化这个提示词: 写一篇关于 AI 的文章",
    "设计一个教育类 App 开发计划",
    "React Suspense 怎么用？",
    "LangChain 的 RAG pipeline 怎么搭？",
    # ... 加到 20 个
]

for q in test_queries:
    results = await rag.query(q)
    has_content = any(r["score"] >= 0.5 for r in results)
    print(f"[{'✅' if has_content else '❌'}] {q}")
# 如果命中率 < 50%，知识库覆盖不够
```

### Q: 如果知识库本身有错误怎么办？

这是四层防线中最难处理的问题。当前项目没有任何机制检测知识库内容本身的正确性。可行的方案：

1. **知识库文件增加元数据**: 在 .md 文件头部加 YAML frontmatter，标注来源和时间
2. **知识库审计 (P3)**: 定期用 LLM 检查知识库内部的一致性（如不同文档对同一概念的定义是否矛盾）
3. **用户纠错机制**: 允许用户对「来源引用」点踩，AI 输出的每条引用如果被多个用户标记为不准确，自动降低该 chunk 的权重

### Q: Checkpoint 和 Reflector 都在做幻觉检测，为什么需要两个？

分工不同：

| | Checkpoint | Reflector |
|---|---|---|
| **检查什么** | 方向对不对（语义对齐） | 质量好不好（完整性、准确性） |
| **重点** | 有没有编造、有没有偏题 | 有没有遗漏、格式好不好 |
| **速度** | 快（只看前 1500 字符） | 慢（看前 2000 字符 + 详细评分） |
| **失败后** | 回 execute 重试 (1 次) | 回 execute 重试 (2 次) |
| **为什么不是同一个** | 语义偏题和质量差是两类问题，混在一起判断准确率低 | |

如果一个节点需要同时检查「方向对不对」和「质量好不好」，Prompt 会变得冗长，LLM 的注意力会分散。拆成两个节点各司其职，准确率更高。

### Q: LLM 检查 LLM 的输出，有什么局限性？

最大的局限性是**检查者的知识边界**。如果检查用的 LLM（Checkpoint/Reflector）本身的预训练和生成用的 LLM（Executor）相同或类似，它们可能共享同样的知识盲区。

例如：
- Executor 编造了 `HybridRetriever` 这个不存在的 API
- Checkpoint 用的也是同一个 LLM，它也不知道 `HybridRetriever` 是否存在
- 结果：Checkpoint 可能漏判

对策：
1. 用不同的 LLM 做检查和生成（如 Executor 用 DeepSeek，Checker 用 Qwen）
2. 不依赖 LLM 的知识来判断，而是对比知识库内容来判断（当前做法）
3. 对代码类输出，优先通过实际执行来验证（而非 LLM 检查）

---

## 七、实施路线图

### P0（已完成）-- 基础防御就位

| 机制 | 文件 | 效果 |
|------|------|------|
| 相似度阈值 ≥0.6 | `rag_service.py` | 不相关内容不注入 |
| Rerank 精排 | `rag_service.py` | 检索精度提升 |
| 来源引用要求 | `system_prompts.py` | Prompt 层约束 |
| 知识边界声明 | `system_prompts.py` + `rag_service.py` | 未命中时明确说 |
| Checkpoint hallucination 检测 | `graph.py` | 每次 execute 后核查 |
| Reflector hallucination 检测 | `graph.py` + `system_prompts.py` | double-check |

### P1（预计 2h）-- 三道升级防线

| 任务 | 文件 | 预计行数 | 效果 |
|------|------|---------|------|
| 逐声明事实核查 Prompt 升级 | `graph.py` | ~15 行 | 从二元判断到逐条分析 |
| 三级不确定性标记 | `system_prompts.py` | ~20 行 | 🟢🟡🔴 让用户看到确定程度 |
| 知识库覆盖声明增强 | `rag_service.py` | ~15 行 | 告知用户知识库有什么 |
| Badcase 自动保存（Reflector score < 5） | `graph.py` + `feedback.py` | ~30 行 | 低分输出自动存档 |

### P2（预计 4h）-- 跨源验证 + 闭环

| 任务 | 文件 | 预计行数 | 效果 |
|------|------|---------|------|
| 跨源交叉验证 (search_web vs rag) | `tools/search.py` | ~40 行 | 联网搜索结果和知识库对比，不一致时标注 |
| Badcase 自动保存（用户 👎 触发） | `feedback.py` | ~30 行 | 完整上下文存档（含 RAG chunks） |
| Badcase 分析 dashboard | `routers/feedback.py` | ~50 行 | 统计未覆盖 query top-10 |
| 知识库覆盖评估脚本 | `tests/` 新增 | ~60 行 | 自动跑 20 个典型 query 统计命中率 |
| 反馈表扩展字段 | `feedback.py` | ~15 行 | 新增 rag_chunks, output, query 字段 |

### P3（预计 6h）-- 知识库质量审计

| 任务 | 文件 | 预计行数 | 效果 |
|------|------|---------|------|
| 知识库内部一致性检查 | 新建脚本 | ~80 行 | 检测不同文档对同一概念的定义矛盾 |
| 时效性标注自动提醒 | 新建脚本 | ~60 行 | 知识库文件超过 N 天未更新自动提醒 |
| 不同 LLM 做 Checker 配置 | `config.py` + `graph.py` | ~20 行 | 检查和生成用不同模型 |
| 知识库文件 YAML frontmatter | `knowledge_base/*.md` | ~5 篇 | 加入来源、时间、作者元数据 |

---

## 八、相关文件索引

| 文件 | 角色 | 幻觉防御相关 |
|------|------|------------|
| `core/graph.py` | **核心** -- LangGraph 图 + Checkpoint + Reflector | `PLANNER_CHECKPOINT_PROMPT` (L56-78), `checkpoint_node()` (L428-509), `reflect_node()` (L516-570) |
| `prompts/system_prompts.py` | **Prompt** -- Executor/Reflector 约束 | `EXECUTOR_SYSTEM_PROMPT` 知识库使用规则 (L73-78), `REFLECTOR_SYSTEM_PROMPT` 忠实度审核 (L102-121) |
| `services/rag_service.py` | **检索** -- 混合检索 + Rerank + 来源引用 | `query_formatted()` 来源标注 + 边界声明 (L426-445), `query()` 阈值过滤 (L338-424) |
| `services/vector_store.py` | **存储** -- PGVector + BM25 | 稠密 + 稀疏双路检索 |
| `core/context_engine.py` | **Query 增强** -- 上下文驱动 query 构建 | 短 query 不扩写、零幻觉的上下文组合 |
| `routers/feedback.py` | **反馈** -- 用户 👍👎 收集 | Badcase 自动保存 (待实现) |
| `routers/knowledge.py` | **API** -- 知识库搜索/统计/重建 | `/api/knowledge/search` |
| `config.py` | **参数** -- 阈值/开关/模型配置 | `similarity_threshold`, `rerank_enabled`, `rerank_model` |
| `models/schemas.py` | **数据模型** -- FeedbackRequest | `rating`, `comment`, `skill` |
| `knowledge_base/*.md` | **数据** -- 手写领域知识 | 3 篇 .md: prompt_engineering, workflow_best_practices, tech_news |
| `docs/rag-deep-dive.md` | **参考** -- RAG 深挖指南 | 第六节: 幻觉防御 -- 四层防线 + ReAct 本质 |
| `docs/tool-loop-prevention.md` | **参考** -- 工具防循环指南 | 三层防线设计模式的参考 |
| `boundary.md` | **规范** -- RAG 优化要求 | 包含幻觉防御相关的待办事项 |
