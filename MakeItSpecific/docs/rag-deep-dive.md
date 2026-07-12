# RAG 深挖指南 — 从单层检索到企业级多路召回

> 从当前实现出发，一步步理解 RAG 的每个环节，并规划从「能用」到「好用」的进化路径。
>
> 核心原则：**长缩短会丧失精度，短扩长很容易幻觉 — 只组合真实信息，不生成虚假信息。**

---

## 一、先理解问题：你的 RAG 现在卡在哪？

### 1.1 一次真实的检索失败

用户输入：「React 18 Suspense 怎么处理数据加载？」

当前 RAG 流程：

```
用户 query: "React 18 Suspense 怎么处理数据加载？"
    │
    ▼
ContextEngine._build_enriched_query()
    query = "提示词优化 prompt engineering React 18 Suspense 怎么处理数据加载？"
    │  ↑ 场景关键词拼接了"prompt engineering"，但用户问的是 React！
    │
    ▼
DashScope text-embedding-v4 → 1024 维向量
    │
    ▼
PGVector cosine distance → top-3 chunks
    │
    ▼ 返回结果:
    1. "提示词工程最佳实践 — Chain-of-Thought 思维链..." (score: 0.72)
    2. "工作流程最佳实践 — 任务分解方法..." (score: 0.68)
    3. "提示词优化 — 角色扮演技巧..." (score: 0.65)
    │
    ▼
模型看到的知识库内容: 全是提示词工程，没有 React 相关内容
模型的回复: 「推荐使用 Redux 管理状态...」← 幻觉，知识库里根本没这个
```

**问题出在哪？**

1. **enriched_query 被场景关键词污染** — 用户选的模块是 `prompt_refiner`，所以场景关键词被硬拼进去，而用户这次问的根本不是提示词问题
2. **没有相似度阈值** — score 0.65 的不相关内容也被注入
3. **知识库里没有 React 相关内容** — 3 篇 .md 文件全是提示词/工作流/技术新闻
4. **纯向量检索的盲区** — "Suspense" 是 React 专有名词，但在 prompt_engineering.md 的 embedding 空间中，它找不到任何相近的向量

### 1.2 RAG 质量 = 四个环节的乘积

```
最终答案质量 = 检索前（Query 质量）× 检索中（召回率）× 检索后（精排过滤）× 生成中（引用忠实度）

其中任何一环是 0，整体就是 0
```

| 环节 | 当前状态 | 问题 |
|------|---------|------|
| **检索前** Query 增强 | 场景关键词拼接（ContextEngine） | 关键词可能误导（1.1 的例子） |
| **检索中** 召回 | 纯稠密向量（cosine distance） | 术语精确匹配盲区，无语义之外的信号 |
| **检索后** 精排 | **无** | 不相关内容不过滤，无 rerank |
| **生成中** 引用 | **无** | 模型可以无视检索结果自由发挥 |

---

## 二、当前架构全景

### 2.1 数据流

```
┌─────────────────────────────────────────────────────────────────┐
│                         数据写入（离线）                          │
│                                                                 │
│  knowledge_base/*.md                                             │
│       │                                                         │
│       ▼                                                         │
│  RAGService.ingest_knowledge_base()                             │
│       │                                                         │
│       ├─ SemanticChunker        语义分块（相邻句子 embedding 相似度）│
│       ├─ _extract_keywords()   提取中英文技术关键词 → metadata     │
│       ├─ _make_chunk_id()      MD5(filepath:idx)                 │
│       ├─ embedding_model        DashScope text-embedding-v4      │
│       └─ PGVectorStore.add()   → domain_knowledge 表             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         数据读取（在线）                          │
│                                                                 │
│  用户消息 "React Suspense..."                                    │
│       │                                                         │
│       ▼                                                         │
│  agent.py : _build_initial_state()                              │
│       │                                                         │
│       ▼                                                         │
│  ContextEngine.build()                                          │
│       │                                                         │
│       ├─ L1 最近 3 轮原文                                        │
│       ├─ L2 滚动摘要                                             │
│       ├─ L3 语义事实召回                                         │
│       └─ _build_enriched_query()  ← RAG 增强 query (见 §7)       │
│             │                                                   │
│             ├─ L3 语义事实（用户明确表达的偏好/决策）               │
│             ├─ expressed_dimensions（已确认的需求维度）            │
│             ├─ L2 摘要关键词（长对话的滚动摘要）                   │
│             └─ 场景关键词（仅在 query 短且和场景明显相关时加入）     │
│             │                                                   │
│             ▼  组合 query，不是扩写 query                         │
│       │                                                         │
│       ▼                                                         │
│  graph.py : enrich_query_node → rag_retrieve_node                │
│       │                                                         │
│       ├─ 取 enriched_query（或 original message fallback）        │
│       └─ RAGService.query_formatted(query, top_k=3)             │
│             │                                                   │
│             ├─ embedding_model.embed_query(query)                │
│             ├─ PGVectorStore.search(cosine distance)             │
│             ├─ 相似度阈值过滤 (min_score ≥ 0.6)                   │
│             └─ 格式化为 "### 📚 知识点 N (来源: xxx.md)"          │
│       │                                                         │
│       ▼                                                         │
│  planner_node / execute_node                                    │
│       │                                                         │
│       └─ {rag_context} 注入 prompt，带来源引用要求                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 存储层

```sql
-- domain_knowledge 表结构
CREATE TABLE domain_knowledge (
    id          TEXT PRIMARY KEY,          -- MD5(filepath:idx)[:16]
    document    TEXT NOT NULL,             -- 分块文本 (语义分块，~200-800 字符)
    embedding   vector(1024) NOT NULL,     -- DashScope text-embedding-v4
    metadata    JSONB DEFAULT '{}',        -- {source_file, chunk_index, keywords, content_hash}
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_domain_knowledge_embedding
    ON domain_knowledge USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

### 2.3 关键参数（config.py）

```python
rag_top_k: int = 3           # 检索返回数
rag_chunk_min: int = 200     # 语义分块最小字符数
rag_chunk_max: int = 800     # 语义分块最大字符数
```

---

## 三、分块策略 — RAG 的第一道关卡

### 3.1 为什么分块方式决定了检索质量的上限

```
你不分块 → 一篇 5000 字的 prompt_engineering.md 作为一个 embedding
              → "React Suspense" 和这篇文章的 cosine similarity 可能只有 0.3
              → 检索不到

你分太细 → 每个句子一个 chunk
              → "Chain-of-Thought 思维链" 被切成 "Chain-of-Thought" + "思维链"
              → 语义碎片化，召回率高但精确率低

分得刚好 → 在语义自然边界处切分
              → "React 18 引入了 Suspense。Suspense 是一种并发特性..."
              → 同一主题的句子聚合，主题切换时切断
```

### 3.2 当前分块实现的问题

```python
def _chunk_text(self, text: str, max_chars=500, overlap=50) -> list[str]:
    # 1. 按 ## 标题分割
    sections = re.split(r"\n(?=## )", text)
    # 2. 每段如果超长，再按句子切分
```

- 固定 500 字符不考虑语义边界 — 可能在一个段落的中间切断
- 依赖 `## 标题` 作分割点 — 没有标题的文档就只能按句号硬切
- overlap 是字符级拼接，不保证语义完整

### 3.3 选择：语义分块 (Semantic Chunking)

**设计思路**: 用相邻句子的 embedding 相似度找「语义断崖」— 当话题切换时，相邻句子的 embedding 相似度会骤降，那里就是自然的分块边界。

```
句子1: "React 18 引入了 Suspense"             │
句子2: "Suspense 是一种新的并发特性"           │ 相似度 0.85 — 同一主题，不断
句子3: "使用前需要先安装 react-dom"            │ 相似度 0.78 — 同一主题，不断
──────────── 语义断崖 (相似度 0.45) ──────────
句子4: "Vue 3 也有类似的 Suspense 组件"        │
句子5: "需要在 vue.config.js 中配置"           │ 相似度 0.72 — 新主题开始了
```

**完整实现:**

```python
import numpy as np
from typing import List


class SemanticChunker:
    """语义分块器 — 用相邻句子 embedding 相似度找自然断点。

    参数:
        embedding_fn:   文本 → 向量的函数 (DashScope text-embedding-v4)
        threshold:      相似度低于此值视为「语义断崖」(默认 0.5)
        min_chars:      每块最小字符数（低于此不切，防止碎片化）
        max_chars:      每块最大字符数（超此强制在最近的句子边界切断）
    """

    def __init__(
        self,
        embedding_fn,
        threshold: float = 0.5,
        min_chars: int = 200,
        max_chars: int = 800,
    ):
        self.embed = embedding_fn
        self.threshold = threshold
        self.min_chars = min_chars
        self.max_chars = max_chars

    def chunk(self, text: str) -> List[str]:
        """
        1. 按 ## 标题粗分（保留文档结构）
        2. 每段拆句子，算相邻句子 embedding 相似度
        3. 在「语义断崖」处切分
        4. 控制 min/max 字符边界
        """
        # Step 1: 按 ## 标题粗分
        sections = self._split_by_headers(text)

        all_chunks = []
        for section in sections:
            if len(section) <= self.min_chars:
                if section.strip():
                    all_chunks.append(section.strip())
                continue

            # Step 2: 拆句子
            sentences = self._split_sentences(section)
            if len(sentences) <= 1:
                all_chunks.append(section.strip())
                continue

            # Step 3: 批量生成 sentence embeddings
            embeddings = self.embed(sentences)  # list[list[float]]

            # Step 4: 计算相邻相似度，找断点
            breakpoints = self._find_breakpoints(sentences, embeddings)

            # Step 5: 在断点处切分，控制大小
            chunks = self._split_at_breakpoints(sentences, breakpoints)
            all_chunks.extend(chunks)

        return all_chunks

    def _split_by_headers(self, text: str) -> List[str]:
        """按 ## 标题粗分 — 保留文档的逻辑结构。"""
        import re
        parts = re.split(r"\n(?=## )", text)
        return [p.strip() for p in parts if p.strip()]

    def _split_sentences(self, text: str) -> List[str]:
        """中英文句子切分。"""
        import re
        # 按句号、问号、感叹号、换行切分
        raw = re.split(r"(?<=[。！？.!?\n])\s*", text)
        return [s.strip() for s in raw if s.strip() and len(s.strip()) >= 5]

    def _find_breakpoints(
        self, sentences: List[str], embeddings: List[List[float]]
    ) -> List[int]:
        """找到语义断崖位置。"""
        breakpoints = []
        for i in range(len(sentences) - 1):
            sim = self._cosine_similarity(embeddings[i], embeddings[i + 1])
            if sim < self.threshold:
                breakpoints.append(i + 1)  # 在句子 i+1 前切断
        return breakpoints

    def _split_at_breakpoints(
        self, sentences: List[str], breakpoints: List[int]
    ) -> List[str]:
        """在断点处切分，同时遵守 min/max 约束。"""
        chunks = []
        start = 0

        for bp in breakpoints + [len(sentences)]:
            segment = sentences[start:bp]
            segment_text = " ".join(segment)

            # 太小 → 不合并不切，留到下一个断点
            if len(segment_text) < self.min_chars and bp < len(sentences):
                continue

            # 太大 → 在最近的句子边界强制切断
            if len(segment_text) > self.max_chars:
                sub_chunks = self._force_split(segment, self.max_chars)
                chunks.extend(sub_chunks)
            else:
                if segment_text.strip():
                    chunks.append(segment_text.strip())

            start = bp

        return chunks

    def _force_split(self, sentences: List[str], max_chars: int) -> List[str]:
        """强制在 max_chars 处切断（找最近的句子边界）。"""
        chunks = []
        current = ""
        for s in sentences:
            if len(current) + len(s) <= max_chars:
                current += " " + s if current else s
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = s
        if current.strip():
            chunks.append(current.strip())
        return chunks

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Cosine similarity between two vectors."""
        a_arr, b_arr = np.array(a), np.array(b)
        denom = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
        if denom == 0:
            return 0.0
        return float(np.dot(a_arr, b_arr) / denom)
```

**语义分块 vs 固定大小分块的差异:**

| | 固定大小 (旧) | 语义分块 (新) |
|---|---|---|
| 切断依据 | 字符数达上限 | 相邻句子相似度骤降 |
| 块内一致性 | 可能混合多个主题 | 同一主题的句子聚合 |
| 标题感知 | 仅 `##` 标题 | `##` 标题 + 语义断崖双层 |
| 额外成本 | 零 | 每句话一次 embedding（批量调用，可复用检索 embedding） |
| 碎片防护 | 无 | min_chars 阈值防止过碎 |

---

## 四、检索策略 — 从稠密向量到混合多路

### 4.1 稠密检索（Dense）— 已在用

```
query: "React Suspense 数据加载"
  → DashScope text-embedding-v4 → [0.023, -0.015, 0.087, ...]  (1024维)
  → PGVector cosine distance  → top-3
```

**工作原理**: 把文本映射到高维语义空间，语义相似的文本向量距离近。
**盲区**: 专有名词、缩写、代码片段、数字。这些在训练数据中出现频率低，embedding 模型「不认识」。

### 4.2 稀疏检索（Sparse / BM25）— 缺失

```
query: "React Suspense 数据加载"

稠密 (Dense) 找到:
  ✅ "React 18 并发模式指南 — Suspense 是一种..."  (语义相关)
  ✅ "数据获取最佳实践 — use() hook 的使用方法..."  (语义相关)

稀疏 (BM25) 找到:
  ✅ "React Suspense 数据加载"  ← 精确标题匹配
  ✅ "Suspense API 参考"        ← 关键词重叠
  ❌ "Vue Suspense 组件"        ← 虽然有 Suspense 但用户说的是 React
```

**稠密擅长语义，稀疏擅长术语。两者互补。**

### 4.3 BM25 五句话原理

```
1. 把 query 和每个文档都切成词
2. TF (词频):       这个词在文档中出现的次数 / 文档总词数
3. IDF (逆文档频率): log((总文档数 - 含该词的文档数 + 0.5) / (含该词的文档数 + 0.5))
                    ↑ 稀有词（如 "Suspense"）权重高，常见词（如 "方法"）权重低
4. 文档长度归一化:   防止长文档天然占优
5. 得分 = Σ(TF × IDF) 对所有 query 词求和

BM25 不需要 embedding，纯统计算法，PG 内置 tsvector 即可实现。
```

### 4.4 混合检索架构

```
                         用户 query
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
         Dense 检索      BM25 检索      Knowledge Graph
         (PGVector)     (PG tsvector)   (source_file 聚合)
              │             │             │
              ▼             ▼             ▼
           top-10        top-10        结构化目录大纲
              │             │             │
              └──────┬──────┘             │
                     ▼                    │
              合并去重 + RRF              │
              (Reciprocal Rank Fusion)    │
                     │                    │
                     ▼                    │
              混合排序 top-20              │
                     │                    │
                     ▼                    │
              Rerank → top-5              │
                     │                    │
                     ▼                    │
              相似度过滤 → top-3           │
                     │                    │
                     ▼                    │
              注入 Prompt                 │
```

### 4.5 RRF (Reciprocal Rank Fusion) — 合并多路排序

```python
def reciprocal_rank_fusion(results_lists: list[list[dict]], k=60) -> list[dict]:
    """
    将多路检索结果合并为统一排序。

    RRF 公式: score(d) = Σ 1 / (k + rank_i(d))
    其中 rank_i(d) 是文档 d 在第 i 路结果中的排名。

    为什么 k=60？来自论文实验 — 这个常数在大多数数据集上稳定，
    它确保排名的微小差异不会导致分数剧烈波动。
    """
    fused = {}
    for results in results_lists:
        for rank, doc in enumerate(results, start=1):
            doc_id = doc["id"]
            fused[doc_id] = fused.get(doc_id, 0) + 1 / (k + rank)

    sorted_ids = sorted(fused.keys(), key=lambda x: fused[x], reverse=True)
    return [{"id": i, "rrf_score": fused[i]} for i in sorted_ids]
```

### 4.6 短 Query 处理 — 上下文驱动，不猜不编

**核心原则: 长缩短会丧失精度，短扩长很容易幻觉。所以短 query 不从虚空中扩写，而是从对话上下文中组合真实信息。**

```
HyDE 的问题 (为什么不用):
  "怎么用 Suspense" → LLM 猜一篇文档 → "React Suspense 是一个..."
  ↑ 猜对了是运气，猜错了就是系统性误导。而且这个猜的过程本身就可能产生幻觉。

正确路径:
  "怎么用 Suspense" (7 个字 — 太短)
      │
      ▼
  Step 1: 从上下文中提取信号
      ├─ L3 语义事实: "用户偏好 React", "已确定用 TypeScript"
      ├─ L2 滚动摘要: "用户在搭建博客项目"
      ├─ L1 最近 3 轮: "刚才问的是数据加载方案"
      └─ expressed_dimensions: {target_model: "Claude", output_style: "简洁"}
      │
      ▼
  Step 2: 组合 query
      "React TypeScript 博客项目 Suspense 数据加载方案"
      ↑ 全是用户真实说过的话，没有一字是编的
      │
      ▼
  Step 3: 如果上下文信号也不够？
      → 不要硬检索，不要瞎猜
      → 注入 ContextEngine 的 clarify 追问: "你说的 Suspense 是指 React 的还是 Vue 的？"
      → 用户回答后再检索，此时有了精确的 query
```

**实现:**

```python
def build_context_driven_query(
    message: str,
    ctx: ConversationContext,
    expressed_dimensions: dict = None,
) -> str:
    """
    上下文驱动的 Query 构建。

    原则:
      1. 只组合用户真实提供的信息，不生成虚假信息
      2. 信号按相关性加权，不相关的上下文不添加噪音
      3. 长 query（> 80 字符）不加额外信号 — 用户已经说清楚了
      4. 短 query 且上下文也不够 → 返回短 query，让上游决定是否追问
    """
    parts = [message]

    # ── 长 query: 不加任何上下文，保护原始语义 ──
    if len(message) >= 80:
        return message

    # ── 中 query (30-80): 只加 L3 高置信度事实 ──
    if len(message) >= 30:
        if ctx.l3_facts:
            # 只取和 query 关键词相关的 L3 事实
            relevant = _filter_relevant_facts(ctx.l3_facts, message)
            if relevant:
                parts.append(relevant)
        return " ".join(parts)[:500]

    # ── 短 query (< 30): 多源信号组合 ──
    # 优先级: L3 事实 > expressed_dimensions > L2 摘要
    signals = []

    # 1. L3 语义事实 — 用户明确说过的偏好/决策 (权重最高)
    if ctx.l3_facts:
        l3_text = ctx.l3_facts.replace(
            "以下是从此前对话中召回的语义事实：\n", ""
        ).replace("- ", "")
        signals.append(l3_text[:200])

    # 2. expressed_dimensions — 已确认的需求维度
    if expressed_dimensions:
        dim_parts = []
        for key, val in expressed_dimensions.items():
            if key.endswith("_confidence"):
                continue
            if val and str(val) != "null" and len(str(val)) > 1:
                dim_parts.append(str(val))
        if dim_parts:
            signals.append(" ".join(dim_parts)[:150])

    # 3. L2 滚动摘要 — 长对话的核心脉络
    if ctx.l2_summary:
        signals.append(ctx.l2_summary[:150])

    # 组合
    if signals:
        parts.append(" ".join(signals))

    return " ".join(parts)[:500]


def _filter_relevant_facts(l3_facts: str, query: str) -> str:
    """只保留和 query 关键词相关的 L3 事实。"""
    keywords = _extract_query_keywords(query)
    if not keywords:
        return ""

    relevant = []
    for line in l3_facts.split("\n"):
        line = line.lstrip("- ").strip()
        if not line:
            continue
        score = sum(1 for kw in keywords if kw.lower() in line.lower())
        if score > 0:
            relevant.append(line)

    return " ".join(relevant[:3]) if relevant else ""
```

**和 HyDE 的对比:**

| | HyDE | 上下文驱动 |
|---|---|---|
| 信息来源 | LLM 生成的假设文档（可能虚假） | 用户的真实对话历史 |
| 幻觉风险 | 高 — 编出来的文档可能和知识库实际内容不符 | 零 — 每个词都是用户说过的 |
| 覆盖面 | 取决于 LLM 的知识边界 | 取决于对话历史的丰富度 |
| 上下文不够时 | 硬猜（危险） | 承认不够 → 触发 clarify 追问 |
| 额外 LLM 调用 | 每次 1 次 | **零**（只做字符串组合 + 关键词匹配） |
| 延迟 | ~200-500ms | ~1ms |

---

## 五、检索后处理 — 精排 + 过滤

### 5.1 Rerank — 从「大概相关」到「精确匹配」

```
传统流程:
  query → embedding → top-10 → 直接取 top-3 → 注入 prompt
                                ↑ 这里精度不够

Rerank 流程:
  query → embedding → top-20 → Rerank Model → top-5 → 注入 prompt
                                ↑ 逐对精排 (query, chunk_i)
```

**为什么 Rerank 有效？**

| | Bi-Encoder (Embedding) | Cross-Encoder (Rerank) |
|---|---|---|
| 工作方式 | query 和文档分别编码，然后算距离 | query 和文档拼接后一起编码 |
| 速度 | 快（文档向量可预计算） | 慢（每对都要重新算） |
| 精度 | 中（独立的向量空间距离） | 高（query-doc 交互建模） |
| 使用 | 粗筛 top-20 | 精排 top-20 → top-5 |

**Rerank 模型选型:**

| 模型 | 来源 | 部署 | 中文效果 | 单次成本 | 推荐场景 |
|------|------|------|---------|---------|---------|
| **gte-rerank** | 百炼 DashScope | API | ⭐⭐⭐ | ~¥0.02/千次 | **首选** — 已有 DashScope key |
| **bge-reranker-v2-m3** | BAAI 开源 | 本地 CPU/GPU (~2GB) | ⭐⭐⭐ | 零（自部署） | 离线/隐私敏感场景 |
| **bge-reranker-large** | BAAI 开源 | 本地 (~1.3GB) | ⭐⭐（英文为主） | 零 | 英文为主场景 |
| **Cohere rerank-multilingual-v3.0** | Cohere | API | ⭐⭐ | ~$2/千次 | 多语言混合场景 |

**推荐 `gte-rerank`**: 已通过 DashScope API key 接入，零额外配置。对个人项目的日调用量 (< 1000 次/天)，月成本 < ¥1。

```python
# DashScope Rerank API（阿里云百炼）
import aiohttp

async def dashscope_rerank(
    query: str,
    documents: list[str],
    api_key: str,
    top_n: int = 5,
    model: str = "gte-rerank",
) -> list[dict]:
    """使用 DashScope gte-rerank 精排检索结果。

    Returns:
        [{index: int, document: str, relevance_score: float}, ...]
        按 relevance_score 降序排列
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "input": {
                    "query": query,
                    "documents": documents,
                },
                "parameters": {
                    "top_n": top_n,
                    "return_documents": True,
                },
            },
        ) as resp:
            data = await resp.json()
            return data.get("output", {}).get("results", [])
```

### 5.2 相似度阈值过滤 — 最低成本的幻觉防御

```python
# 当前代码（无过滤）:
results = await self.store.search(collection, query_embedding, top_k=3)
return [r["document"] for r in results if r.get("document")]
# ↑ 只要返回了就照单全收

# 加阈值后:
SIMILARITY_THRESHOLD = 0.6  # cosine similarity < 0.6 → 不相关

results = await self.store.search(collection, query_embedding, top_k=3)
filtered = [
    r for r in results
    if r.get("score", 0) >= SIMILARITY_THRESHOLD
]
# ↑ 所有分数低于 0.6 的不注入，标记 "未找到相关知识"

if not filtered:
    return "（知识库中未找到与您的问题直接相关的内容，以下是基于通用知识的回答。）"
```

### 5.3 关键词重叠加权

```python
def keyword_overlap_boost(query: str, chunk: str, boost_factor=0.15) -> float:
    """
    计算 query 的核心技术名词在 chunk 中的覆盖率，
    返回加权分数（加到向量相似度上）。

    这是稠密向量的互补信号 — 向量捕获语义，关键词捕获术语。
    """
    tech_terms = extract_tech_terms(query)  # 提取 "React", "Suspense" 等
    if not tech_terms:
        return 0.0

    chunk_lower = chunk.lower()
    overlap_count = sum(1 for t in tech_terms if t.lower() in chunk_lower)
    overlap_ratio = overlap_count / len(tech_terms)

    if overlap_ratio < 0.3:
        return 0.0           # 重叠太少，不加分
    return overlap_ratio * boost_factor
```

---

## 六、幻觉防御 — 四层防线 + ReAct 本质

### 6.1 防线总览

```
┌──────────────────────────────────────────────────────────────┐
│ 第 1 层: 检索时过滤（不注入不相关内容）                        │
│   ├─ 相似度阈值 (min_score ≥ 0.6)                            │
│   ├─ 关键词重叠检查 (overlap_ratio ≥ 30%)                    │
│   └─ 低相似度降级 (所有 chunk < 0.5 → 拒绝注入)               │
├──────────────────────────────────────────────────────────────┤
│ 第 2 层: Prompt 中约束（告诉模型怎么用检索结果）               │
│   ├─ 来源强制引用: "每条关键信息必须注明来自知识库"            │
│   ├─ 知识边界声明: "如果知识库未覆盖，请明确说明"              │
│   └─ 不确定性标记: "不确定时用 ⚠️ 标记"                       │
├──────────────────────────────────────────────────────────────┤
│ 第 3 层: 生成后核查（Checkpoint / Reflector）                 │
│   ├─ Checkpoint: "输出中的技术细节是否在知识库参考中？"        │
│   └─ Reflector: "有没有编造知识库中不存在的信息？"            │
├──────────────────────────────────────────────────────────────┤
│ 第 4 层: Badcase 自动收集                                     │
│   ├─ 用户点 👎 → 自动保存 input + output + RAG chunks         │
│   ├─ Reflector score < 5 → 自动保存                          │
│   └─ 知识库未覆盖类错误 → 提醒用户补充知识库                   │
└──────────────────────────────────────────────────────────────┘
```

### 6.2 知识边界声明 — Prompt 层

```python
RAG_CONTEXT_PREFIX = """## 🔴 知识库参考（必须遵守以下规则）

### 可用知识
{rag_chunks}

### 规则
1. 你的回答必须基于以上知识库内容。如果知识库未覆盖某个话题，请明确说明"知识库中暂无相关信息"。
2. 每条关键技术建议必须注明来源（格式: 「参考: {source_file}」）
3. 不要编造知识库中不存在的数据、API 名称、版本号。
4. 如果对某个细节不确定，使用 ⚠️ 标记并建议用户查阅官方文档。

### 知识库覆盖情况
{coverage_note}
"""
```

### 6.3 Checkpoint 事实核查 — 生成后核查

```python
CHECKPOINT_FACT_CHECK_PROMPT = """你是事实核查员。检查 AI 输出中的关键技术声明是否能在知识库中找到依据。

## 知识库内容
{rag_chunks}

## AI 输出
{output}

## 核查要求
对于 AI 输出中的每个技术声明，判断:
- ✅ 有依据: 知识库中能找到对应的表述
- ⚠️ 不确定: 知识库未涉及但属于常识范围
- ❌ 无依据: 明显超出知识库范围，可能是编造的

只输出 JSON:
{
  "fact_check_pass": true/false,
  "hallucinations": [{"claim": "...", "evidence": "none"}],
  "verdict": "通过 / 存在幻觉 / 严重偏离"
}
"""
```

### 6.4 幻觉防御的 ReAct 本质

幻觉防御不是一次性的检查，而是一个**外层的 ReAct 循环**。这和 LangGraph 内部 Executor 的工具调用 ReAct 是同一模式，只是粒度不同：

```
┌─────────────────────────────────────────────────────────────┐
│                  工具级 ReAct (Executor 内部)                 │
│                                                             │
│  Observe ─── tool 返回的结果                                 │
│    │                                                        │
│  Reason ─── "这个结果够吗？还需要什么信息？"                   │
│    │                                                        │
│  Act    ─── 调用下一个 tool / 生成最终输出                    │
│    │                                                        │
│    └── 循环，最多 10 轮                                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│               质量级 ReAct (Checkpoint → Reflect)             │
│                                                             │
│  Observe ─── Executor 完整 output + rag_context + 原始 query │
│    │                                                        │
│  Reason ─── Checkpoint LLM:                                 │
│             "技术声明在知识库中有依据吗？                      │
│              语义方向和原始意图一致吗？"                       │
│    │                                                        │
│  Act    ─── aligned=false → correction → execute 重试        │
│          ─── aligned=true  → Reflector 质量检查               │
│    │                                                        │
│    └── Reflector 再决定: pass → END / fail → execute 重试    │
└─────────────────────────────────────────────────────────────┘
```

**两层 ReAct 的关系:**

```
Executor tool calling loop (内层)
    │  每轮: Observe tool output → Reason → Act (call next tool)
    │  粒度: 单个工具调用
    │  目标: 完成当前子任务
    ▼
Checkpoint 语义对齐 (外层 Observe)
    │  观察: 完整 output + 知识库 + 原始意图
    │  推理: 方向对了吗？有没有幻觉？
    │  行动: 修正 → 重试 / 通过 → 继续
    ▼
Reflector 质量审查 (外层 Reason)
    │  推理: 完整性够吗？准确性够吗？
    │  行动: 不够 → 重试 / 够了 → END
```

**这意味着幻觉防御不是一个「功能」，而是 Agent 架构的固有属性**。每层 ReAct 都在不同的抽象层级上做 Observe → Reason → Act，幻觉在任何一个层级都可能被发现和纠正。

---

## 七、智能 Query 构建 — 检索前的最重要一步

> **入口决定出口。RAG 管道再精良，query 构建错了，后面全是白费。**

### 7.1 当前 enriched_query 的问题

```python
# context_engine.py: _build_enriched_query()
scene_keywords = {
    "prompt_optimize": "提示词优化 提示词工程 prompt engineering",
    "work_plan": "工作安排 项目计划 任务分解 工作流",
    ...
}
if scene in scene_keywords:
    context_parts.append(scene_keywords[scene])
# ↑ 三个致命问题:
#   1. 强制注入: 用户选了 prompt_refiner 但问的是 React，"prompt engineering" 直接污染了 query
#   2. 无相关性判断: 场景关键词和用户消息之间没有任何语义匹配检查
#   3. 无信号权重: 所有上下文信号（场景/L2/维度）等权拼接，噪音和信号混在一起
```

### 7.2 设计原则

```
原则 1: 只组合真实信息，不生成虚假信息
  ✅ 从对话历史中提取用户明确说过的话
  ❌ 用 LLM 扩写 / 假设文档 / 编造上下文

原则 2: 相关性优先于完整性
  ✅ 只添加和当前 query 语义相关的上下文
  ❌ 把所有已知信息都拼进去 "以防万一"

原则 3: 信号有权重，不是等权拼接
  ✅ L3 事实 (用户明确说过的偏好) > expressed_dimensions (已确认需求) > L2 摘要 (长对话脉络)
  ❌ 所有信号无差别拼接

原则 4: 保护原始语义
  ✅ 长 query（用户已经说清楚了）不加任何额外信息
  ❌ 在清晰的 query 上叠加噪音

原则 5: 信息不够就承认，不要编造
  ✅ 上下文也不够 → 返回原始短 query → 让上游通过 clarify 反问用户
  ❌ HyDE 式 "假设知识库里有这么一篇文档"
```

### 7.3 多源上下文信号

Query 增强的信息来源（全部来自用户的真实对话历史）：

```
信号源                     权重      触发条件              信息类型
──────────────────────────────────────────────────────────────────
L3 语义事实                 0.4      有匹配关键词时         用户偏好/决策/约束
  "用户偏好 React, 不要 Redux, 决定用 Vercel"

expressed_dimensions        0.3      有已确认维度时         结构化需求信息
  {target_model: "Claude", output_style: "简洁"}

L2 滚动摘要                 0.2      query < 50 字符时      长对话脉络
  "用户在搭建 React + TypeScript 博客项目"

L1 最近原文                 0.1      query 含指代词时       指代消解的上下文
  "刚才说的是部署方案"

场景关键词                   0.1      query < 30 字符          领域知识定向
  "prompt engineering"        AND query 和场景明显相关时
```

**关键: 每个信号源有明确的触发条件，不是无差别注入。**

### 7.4 指代消解

用户说「上次那个方案怎么改」、「他说的方法行不行」时，需要把指代词替换为具体内容。

```python
# 指代词模式
REFERENCE_PATTERNS = [
    r'(?:上次|刚才|前面|之前)(?:那个|这个|说的|提到的)',
    r'(?:那个|这个)(?:方案|方法|想法|思路|问题)',
    r'(?:他|她)(?:说的|提到的|建议的)',
    r'(?:这样|那样)(?:做|搞|写|改)',
]

async def resolve_references(
    query: str,
    ctx: ConversationContext,
) -> str:
    """
    指代消解: "上次那个方案" → "React + TypeScript 博客 Vercel 部署方案"

    消解策略:
      1. 先查 L1 最近 3 轮原文 — "上次"通常是上一轮
      2. 再查 L2 滚动摘要 — 跨多轮的指代
      3. 最后查 L3 语义事实 — 用户明确说过的偏好
    """
    if not _has_reference_words(query):
        return query

    # 从上下文中提取可能的指代对象
    candidates = []

    # L1: 最近一轮的用户消息
    if ctx.l1_raw:
        import re
        user_msgs = re.findall(r'用户: (.+?)(?:\n|$)', ctx.l1_raw)
        if user_msgs:
            candidates.append(user_msgs[-1][:200])

    # L2: 滚动摘要的核心信息
    if ctx.l2_summary:
        candidates.append(ctx.l2_summary[:200])

    # 用简单的规则替换指代词
    for pattern in REFERENCE_PATTERNS:
        if re.search(pattern, query):
            # 用候选内容替换
            replacement = candidates[0] if candidates else ""
            if replacement:
                query = re.sub(pattern, replacement, query, count=1)
            break

    return query[:500]
```

### 7.5 什么时候不增强 — 保护原始语义

增强是有代价的 — 每次添加信息都是在稀释原始 query。以下情况**不做增强**：

```python
def should_enhance(query: str, ctx: ConversationContext) -> bool:
    """判断是否需要对 query 做上下文增强。"""

    # 1. 长 query — 用户已经说清楚了，增强只会加噪音
    if len(query) >= 80:
        return False

    # 2. 用户切换了话题 — 旧上下文和新 query 无关
    if _is_topic_switch(query, ctx):
        return False

    # 3. query 已包含足够的具体术语 — 不需要额外信号
    tech_terms = _extract_tech_terms(query)
    if len(tech_terms) >= 3:
        return False

    # 4. 上下文本身就很空 — 没什么可加的
    has_context = (
        bool(ctx.l3_facts) or
        bool(ctx.l2_summary) or
        bool(ctx.l1_raw)
    )
    if not has_context:
        return False

    return True


def _is_topic_switch(query: str, ctx: ConversationContext) -> bool:
    """检测话题切换 — 用户突然问了一个和之前对话完全无关的问题。"""
    if not ctx.l2_summary:
        return False

    # 简单策略: 如果 L2 摘要和 query 的关键词重叠为 0 ≠ 话题切换
    query_keywords = set(_extract_query_keywords(query))
    summary_keywords = set(_extract_query_keywords(ctx.l2_summary))
    overlap = query_keywords & summary_keywords

    return len(overlap) == 0 and len(query_keywords) > 0
```

### 7.6 动态权重 — 不是等权拼接

```python
def build_weighted_query(
    message: str,
    ctx: ConversationContext,
    expressed_dimensions: dict = None,
) -> str:
    """
    按信号相关性动态加权的 query 构建。
    核心: 不同场景下，不同信号源的权重不同。
    """
    if not should_enhance(message, ctx):
        return message[:500]

    # ── 计算每个信号源的权重 ──
    weights = {}

    # L3 事实: query 越短权重越高（需要更多上下文）
    if ctx.l3_facts:
        weights["l3"] = 0.4 if len(message) < 30 else 0.2

    # expressed_dimensions: 需求越明确权重越高
    if expressed_dimensions:
        dim_count = sum(
            1 for k, v in expressed_dimensions.items()
            if not k.endswith("_confidence") and v and str(v) != "null"
        )
        if dim_count > 0:
            weights["dims"] = min(0.3, dim_count * 0.1)

    # L2 摘要: 长对话时才有用
    if ctx.l2_summary and len(message) < 50:
        weights["l2"] = 0.2

    # 场景关键词: 仅在 query 极短且和场景相关时
    if len(message) < 30:
        weights["scene"] = 0.1

    # ── 归一化 ──
    total = sum(weights.values())
    if total == 0:
        return message[:500]

    weights = {k: v / total for k, v in weights.items()}

    # ── 按权重截取每个信号源的字符配额 ──
    MAX_TOTAL = 500 - len(message)
    parts = []

    signal_extractors = {
        "l3": lambda: _extract_l3_signal(ctx.l3_facts, message),
        "dims": lambda: _extract_dims_signal(expressed_dimensions),
        "l2": lambda: ctx.l2_summary[:200],
        "scene": lambda: _get_scene_keywords(ctx),
    }

    for key, weight in sorted(weights.items(), key=lambda x: x[1], reverse=True):
        char_budget = int(MAX_TOTAL * weight)
        if char_budget < 30:  # 太少了不值得加
            continue
        extractor = signal_extractors.get(key)
        if extractor:
            signal = extractor()
            if signal:
                parts.append(signal[:char_budget])

    # 权重最高的信号放最后（离 query 最近，embedding 时注意力最高）
    parts.append(message)
    return " ".join(parts)[:500]
```

### 7.7 Query Decomposition — 复杂查询拆解

```
用户: "React 和 Vue 的 Suspense 分别怎么用，各有什么优缺点？"

拆解:
  子问题 1: "React Suspense 怎么用？"
  子问题 2: "Vue Suspense 怎么用？"
  子问题 3: "React Suspense 的优缺点？"
  子问题 4: "Vue Suspense 的优缺点？"

每个子问题独立检索 → 合并去重 → 按子问题组织回答
```

```python
async def decompose_query(self, query: str) -> list[str]:
    """LLM 拆解复杂查询。

    注意: 这里只拆解结构（把一句话拆成多个子问题），
    不生成新信息。每个子问题仍然是用户的原始意图。
    """
    # 简单判断: 含 "和"、"分别"、"对比"、"区别" → 可能需要拆
    if not any(kw in query for kw in ["和", "分别", "对比", "区别", "比较", "以及"]):
        return [query]

    prompt = f"""将以下复杂查询拆解为独立可检索的子问题。
每个子问题应该是原子性的（只问一件事），便于知识库检索。
不要添加用户没说的信息。

查询: {query}

输出格式（每行一个子问题，不要编号）:"""

    try:
        response = await self.model.ainvoke([HumanMessage(content=prompt)])
        lines = response.content.strip().split("\n")
        sub_queries = [l.lstrip("0123456789. -)") for l in lines if l.strip()]
        return sub_queries if len(sub_queries) > 1 else [query]
    except Exception:
        return [query]
```

---

## 八、向量存储选型 — PGVector vs 其他

### 8.1 为什么选了 PGVector

```
选项对比:
┌─────────────┬──────────┬───────────┬──────────┬──────────┐
│             │ PGVector │ ChromaDB  │ Milvus   │ Qdrant   │
├─────────────┼──────────┼───────────┼──────────┼──────────┤
│ 部署         │ ✅ 已有PG │ 独立进程   │ 重量级    │ 独立进程  │
│ 运维         │ ✅ 零额外 │ 需维护     │ K8s 集群  │ 需维护    │
│ SQL 查询     │ ✅ 原生   │ ❌ 受限    │ ❌       │ ❌       │
│ 元数据过滤    │ ✅ JSONB  │ ✅        │ ✅       │ ✅       │
│ 混合检索      │ ✅ tsvector│ ❌       │ ✅       │ ✅       │
│ 扩展性        │ 千万级    │ 百万级     │ 十亿级    │ 十亿级    │
│ 你的使用      │ ✅ 已部署 │ 之前用的   │ 不需要     │ 不需要    │
└─────────────┴──────────┴───────────┴──────────┴──────────┘
```

PGVector 对当前规模（几千个 chunk，单个用户）完全够用。关键优势是 **PG 内置 tsvector 可以做 BM25 全文检索**，不需要引入新组件即可实现混合检索。

### 8.2 IVFFlat 索引调优

```sql
-- 当前索引:
CREATE INDEX ON domain_knowledge USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- lists 参数:
--   太小 (< sqrt(N)) → 搜索慢（探测太多 list）
--   太大 (> 10*sqrt(N)) → 构建慢，可能漏掉相近向量
--   推荐: N 是表行数，lists = sqrt(N) ~ N/1000

-- 定期维护（数据量变化后）:
-- VACUUM ANALYZE domain_knowledge;
```

---

## 九、代码落地 — 最小可行改造（P0）

### 9.1 三件立刻可以做的事

**不需要新依赖，纯增量改动。**

#### 改造 1: 相似度阈值过滤 (~10 行)

```python
# services/rag_service.py — query() 方法
SIMILARITY_THRESHOLD = 0.6

async def query(self, query_text: str, top_k: int = 3,
                min_score: float = None) -> list[dict]:
    if min_score is None:
        min_score = SIMILARITY_THRESHOLD

    results = await self.store.search(...)
    filtered = [r for r in results if r.get("score", 0) >= min_score]
    return filtered  # 原来是 return [r["document"] for r in results]
```

#### 改造 2: 上下文驱动短 Query 增强 (~40 行)

```python
# services/rag_service.py — 新增方法
async def build_context_query(
    self,
    message: str,
    l3_facts: str = "",
    expressed_dimensions: dict = None,
    l2_summary: str = "",
) -> str:
    """
    上下文驱动的 Query 构建 — 不扩写，只组合真实信息。

    原则:
      - 长 query (>80 字符): 不增强，保护原始语义
      - 中 query (30-80): 只加 L3 相关事实
      - 短 query (<30): 组合 L3 + dimensions + L2 摘要
      - 上下文不够: 返回原始 query，让上游 clarify
    """
    if len(message) >= 80:
        return message

    parts = [message]

    if len(message) >= 30:
        # 中 query: 只加 L3 高置信度事实
        if l3_facts:
            relevant = self._filter_facts_by_query(l3_facts, message)
            if relevant:
                parts.append(relevant)
    else:
        # 短 query: 多源组合
        if l3_facts:
            parts.append(l3_facts.replace(
                "以下是从此前对话中召回的语义事实：\n", ""
            ).replace("- ", "")[:200])

        if expressed_dimensions:
            dim_text = " ".join(
                str(v) for k, v in expressed_dimensions.items()
                if not k.endswith("_confidence") and v and str(v) != "null"
            )
            if dim_text:
                parts.append(dim_text[:150])

        if l2_summary:
            parts.append(l2_summary[:150])

    return " ".join(parts)[:500]
```

#### 改造 3: RAG prompt 加来源引用要求 (~15 行)

```python
# services/rag_service.py — query_formatted()
async def query_formatted(self, query_text: str, top_k: int = 3) -> str:
    results = await self.query(query_text, top_k)  # 现在返回带 metadata 的 dict
    if not results:
        return "（未找到相关知识。以下回答基于通用知识，可能不准确。）"

    lines = ["## 🔴 知识库参考", "", "以下信息必须作为回答的基础:", ""]
    for i, r in enumerate(results, 1):
        source = r.get("metadata", {}).get("source_file", "未知来源")
        lines.append(f"### 知识点 {i} (来源: {source})")
        lines.append(r["document"])
        lines.append("")

    lines.append("**规则: 基于以上内容回答。如知识库未覆盖请明确说明。**")
    return "\n".join(lines)
```

### 9.2 需要新依赖但性价比极高的（P1）

#### BM25 混合检索 — PG tsvector

```python
# services/vector_store.py — 新增 bm25_search 方法
async def bm25_search(self, collection: str, query: str, top_k: int = 10) -> list[dict]:
    """PostgreSQL 全文检索 (BM25 等效)。"""
    cur = self.conn.cursor()
    cur.execute(sql.SQL("""
        SELECT id, document, metadata,
               ts_rank(
                   to_tsvector('simple', document),
                   plainto_tsquery('simple', %s)
               ) AS score
        FROM {}
        WHERE to_tsvector('simple', document) @@ plainto_tsquery('simple', %s)
        ORDER BY score DESC
        LIMIT %s
    """).format(sql.Identifier(collection)),
        (query, query, top_k),
    )
    rows = cur.fetchall()
    cur.close()
    return [
        {"id": r[0], "document": r[1], "metadata": r[2], "score": float(r[3])}
        for r in rows
    ]
```

#### DashScope Rerank

已在上方 §5.1 给出完整实现，使用 `gte-rerank` 模型。

#### 语义分块

已在上方 §3.3 给出完整 `SemanticChunker` 实现。

---

## 十、知识库内容策略

### 10.1 当前知识库（3 篇）

| 文件 | 内容 | 覆盖范围 |
|------|------|---------|
| `prompt_engineering.md` | CoT、Few-Shot、角色扮演、结构化输出 | 提示词工程 |
| `workflow_best_practices.md` | 任务分解、流程设计、风险识别 | 工作流程 |
| `tech_news.md` | 技术新闻 | 时效性信息 |

**问题**: 三篇全是提示词/工作流相关，和 MakeItSpecific 的三个 Skill 强绑定。但用户的实际问题可能远超这三个领域。

### 10.2 知识库建设的优先级

```
第一优先级（补齐核心领域）:
  - React/Vue/TypeScript 常见问题
  - AI/LLM 技术术语解释
  - 软件工程最佳实践

第二优先级（与 Skill 互补）:
  - 各模型的提示策略差异
  - 项目管理方法论
  - 信息整理框架

第三优先级（用户高频问题驱动）:
  - 从 Badcase 中收集知识库未覆盖的 query
  - 针对 Top-10 未覆盖查询补写 .md
```

### 10.3 知识库文件规范

```markdown
# 标题: 一句话概括这篇文档覆盖什么

## 子主题 1 — 具体标题
（语义分块会在这段内保持连续，直到话题切换）

## 子主题 2 — 具体标题
（语义分块会在这段内保持连续，直到话题切换）

### 关键点（帮助 BM25 精确匹配）
- 专有名词: React Suspense, use() hook, ErrorBoundary
- 相关概念: 并发渲染, 数据获取, 加载状态
- 适用版本: React 18+

### 常见误区
- 误区 1: ...
- 误区 2: ...
```

---

## 十一、评估体系 — 你怎么知道 RAG 改好了？

### 11.1 离线评估（不依赖用户反馈）

```python
# tests/test_rag_quality.py
RAG_TEST_CASES = [
    {
        "query": "React Suspense 怎么用？",
        "expect_source": "react_guide.md",         # 期望命中哪个文件
        "expect_contains": ["Suspense", "fallback"],# 期望 chunk 包含的关键词
        "min_score": 0.7,                           # 期望最低相似度
    },
    {
        "query": "怎么写好的提示词？",
        "expect_source": "prompt_engineering.md",
        "expect_contains": ["Chain-of-Thought", "角色扮演"],
        "min_score": 0.7,
    },
    # ... 20 个典型 query
]

async def test_rag_recall():
    for case in RAG_TEST_CASES:
        results = await rag.query(case["query"], top_k=5)
        # 检查: 期望的源文件在 top-5 中
        sources = [r["metadata"]["source_file"] for r in results]
        assert case["expect_source"] in sources, \
            f"FAIL: '{case['query']}' → 未命中 {case['expect_source']}\n" \
            f"实际返回: {sources}"
```

### 11.2 在线评估（用户反馈驱动）

```
用户 👍 → 记录 positive
用户 👎 → 自动保存 badcase:
  {
    "query": "原始 query",
    "enriched_query": "增强后的 query",
    "retrieved_chunks": ["chunk1", "chunk2", "chunk3"],
    "scores": [0.72, 0.68, 0.65],
    "ai_output": "模型的最终回复",
    "module": "prompt_refiner",
    "time": "2026-07-11T..."
  }
```

---

## 十二、常见问题

### Q: 短 query 为什么不扩写而用上下文组合？

「长缩短会丧失精度，短扩长很容易幻觉」。用 LLM 扩写短 query（HyDE）的本质是生成假设文档 — 这是用模型的想象力代替检索，一旦猜错方向，检索结果全部跑偏。从对话上下文中组合真实信息有零幻觉风险，且信息本来就是用户说过的，和当前 query 天然相关。如果上下文也不够 → 反问用户，比瞎猜好。

### Q: BM25 和向量检索怎么选 top_k？

```
两路各取 top-20（宽松，宁可多不可少）
→ RRF 合并 → 去重 → top-10
→ Rerank → top-5
→ 相似度过滤 → top-3
→ 注入 Prompt

总原则: 粗筛时慷慨（多召回），精排时严苛（高精度）
```

### Q: Rerank 的 API 开销大吗？

DashScope gte-rerank 的定价约 ¥0.02/千次调用。每次 RAG 查询 rerank 20 个文档对消耗 ~20 次调用 = ¥0.0004。对于个人项目几乎免费。如果要完全离线，可以用 bge-reranker-v2-m3 本地部署（~2GB 显存/内存）。

### Q: 知识库文件应该放多少篇才合理？

```
< 3 篇: RAG 几乎没用，覆盖面窄
3-10 篇: 开始有效，但需要配合好的 query 增强
10-30 篇: 覆盖核心领域，RAG 明显改善体验
30+ 篇: 需要引入分层索引和查询路由

当前 3 篇 → 建议优先补到 10 篇
```

### Q: 为什么不在 graph 里做 RAG 优化而要在 rag_service 里做？

RAG 是一个独立的检索管道。它不依赖 LangGraph 的状态管理，也不需要知道 Agent 的对话流程。把 RAG 优化放在 `rag_service` 里：
- 所有 RAG 相关逻辑在一个文件中，方便调试和切换策略
- 可以被 `/api/knowledge/search` 接口直接复用
- 单元测试不依赖整个 graph

ContextEngine 的 `_build_enriched_query()` 是 RAG 和对话上下文的**唯一接口** — 它在 RAG 检索前组装好 query，后续流程保持解耦。

---

## 十三、相关文件索引

| 文件 | 角色 |
|------|------|
| `services/rag_service.py` | **核心** — 语义分块、索引、检索、Rerank、上下文 query 构建 |
| `services/vector_store.py` | **存储** — PGVector CRUD + tsvector 全文检索 |
| `core/context_engine.py` | **Query 增强** — `_build_enriched_query()` + L3 事实提供 |
| `core/graph.py` | **消费端** — `enrich_query_node` → `rag_retrieve_node` + Checkpoint/Reflect 幻觉防御 |
| `core/agent.py` | **编排端** — `_build_initial_state()` 调 ContextEngine |
| `config.py` | **参数** — `rag_top_k`, embedding model 配置 |
| `prompts/system_prompts.py` | **Prompt** — Planner/Executor/Reflector 的 RAG 使用指令 |
| `prompts/templates.py` | **维度** — 模块维度定义（影响 enriched_query） |
| `routers/knowledge.py` | **API** — `/api/knowledge/search` 接口 |
| `data/knowledge_base/*.md` | **数据** — 手写领域知识 |
| `boundary.md` | **规范** — RAG 优化的要求和待办 (§4, §7) |

---

## 十四、实施路线图

### 🔴 本周（P0，预计 2h）

| 任务 | 文件 | 预计行数 | 效果 |
|------|------|---------|------|
| 相似度阈值过滤 | `rag_service.py` | ~10 行 | 减少不相关内容注入 |
| 上下文驱动短 Query 增强 | `rag_service.py` | ~40 行 | 短 query 用上下文组合，零幻觉 |
| RAG prompt 来源引用 | `rag_service.py` | ~15 行 | 降低幻觉概率 |
| Embedding 模型 v3 → v4 | `rag_service.py` + `vector_store.py` | ~3 行 | 检索精度提升 |

### 🟡 下周（P1，预计 5h）

| 任务 | 文件 | 预计行数 | 效果 |
|------|------|---------|------|
| 语义分块 (SemanticChunker) | `rag_service.py` | ~120 行 | 块内语义一致性，检索精度提升 |
| BM25 全文检索 (PG tsvector) | `vector_store.py` | ~50 行 | 专有名词精确匹配 |
| RRF 混合合并 | `rag_service.py` | ~40 行 | 稠密+稀疏互补 |
| DashScope gte-rerank | `rag_service.py` | ~30 行 | top-20 → top-3 精度大幅提升 |
| 关键词重叠加权 | `rag_service.py` | ~20 行 | 补向量检索盲区 |
| 智能 Query 增强（多源+动态权重） | `context_engine.py` | ~80 行 | 解决场景关键词污染 |

### 🟢 下月（P2，预计 6h）

| 任务 | 文件 | 预计行数 | 效果 |
|------|------|---------|------|
| Query Decomposition | `rag_service.py` | ~50 行 | 复杂查询拆解 |
| Checkpoint 事实核查 | `graph.py` | ~40 行 | 拦截幻觉 |
| Badcase 自动收集 | `rag_service.py` + 新建 `tests/` | ~80 行 | 驱动迭代 |
| 知识库补齐 10 篇 | `data/knowledge_base/` | ~10 篇 .md | 提升覆盖面 |

### ⚪ 远期（P3，可选）

| 任务 | 预计行数 | 说明 |
|------|---------|------|
| Parent Document Retriever | ~80 行 | 小 chunk 检索 → 大段落返回 |
| Self-query 元数据过滤 | ~50 行 | LLM 自动生成 metadata filter |
| 知识图谱摘要 (L3) | ~80 行 | 按 source_file 聚合的结构化大纲 |
| Embedding 模型评估 | - | 对比 text-embedding-v4 vs bge-large vs stella-base |
