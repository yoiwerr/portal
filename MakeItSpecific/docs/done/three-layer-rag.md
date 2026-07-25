# Three-Layer RAG -- 稠密+稀疏+知识图谱混合检索

> 从「单靠向量检索」到「三路互补全覆盖」，逐步理解为什么一层不够、每层解决了什么问题、以及如何在 MakeItSpecific 中落地第三层。
>
> 核心原则：**稠密捕获语义，稀疏捕获术语，知识图谱提供全局视图 -- 三层互补才能覆盖全部检索需求。**

---

## 一、为什么需要三层？

### 1.1 中心论点

单靠稠密向量检索，以下类型的查询会系统性失败：

- **专有名词** -- "Suspense"、"use() hook"、"ErrorBoundary" 在 prompt engineering 知识库的 embedding 空间中找不到相近向量
- **数字和代码片段** -- "React 18"、"MAX_TOOL_ROUNDS = 10" 这种精确标识符在语义空间中不具备独特签名
- **缩写** -- "RRF"、"SSE"、"CoT" 这类缩写 embedding 模型训练数据中频率低，向量表示不充分
- **反向查询** -- "知识库里有什么关于 React 的内容？" 这不是在找一个 chunk，而是在问全局覆盖情况

**稠密擅长语义，稀疏擅长术语，知识图谱提供全局视图。三者各司其职。**

### 1.2 一个真实场景：MakeItSpecific 的三层分别能找到什么

用户输入：「React 18 Suspense 怎么处理数据加载？」

```
Layer 1 稠密 (Dense) 找到什么:
  ✅ "React 18 引入了并发特性，包括 Suspense 和 startTransition..."
     ↑ 语义相关 -- chunk 讨论了 React 并发模式
  ✅ "数据获取的最佳实践 -- 使用异步加载可以提升用户体验..."
     ↑ 语义相关 -- "数据获取" 和 "数据加载" 在向量空间中距离近
  ❌ "Vue 3 也有 Suspense 组件..." -- 语义相近但用户说的是 React

Layer 2 稀疏 (BM25) 找到什么:
  ✅ "React Suspense 数据加载实现指南" -- 精确标题匹配
  ✅ "Suspense API 参考 -- React 18 新特性" -- 关键词 "Suspense" + "React" + "数据"
  ❌ 无法匹配同义表达 "数据加载" vs "data fetching" vs "加载数据"

Layer 3 知识图谱 (KG) 能提供什么:
  如果知识库中有 react_guide.md:
    ## 并发特性
      ### Suspense
        - 基本用法
        - 数据加载模式 (Render-as-You-Fetch)
        - 与 ErrorBoundary 配合
      ### startTransition
        ...
    ## Hooks
      ### use()
        ...

  → LLM 看到这个结构化大纲后知道: 知识库里有 Suspense 相关的内容，
    集中在 react_guide.md 的「并发特性 > Suspense」节点下，
    而不是从 3 个孤立 chunk 中盲目拼凑答案。
```

---

## 二、Layer 1: 稠密检索 (Dense) -- 已实现

### 2.1 是什么

```
用户 query: "怎么优化运行速度"
  → DashScope text-embedding-v4 → [0.023, -0.015, 0.087, ...]  (1024 维向量)
  → PGVector cosine distance → top-20 候选
```

把文本映射到高维语义空间，语义相似的文本向量距离近。

### 2.2 当前实现

```python
# config.py -- 稠密检索相关配置
rag_top_k: int = 3                # 最终返回数
rag_chunk_min: int = 200          # 语义分块最小字符数
rag_chunk_max: int = 800          # 语义分块最大字符数
similarity_threshold: float = 0.6  # 相似度过滤阈值

# services/rag_service.py -- embedding 模型
self._embedding_model = DashScopeEmbeddings(
    model="text-embedding-v4",       # DashScope 最新 embedding 模型
    dashscope_api_key=self._api_key,
)

# services/vector_store.py -- 存储层
CREATE TABLE domain_knowledge (
    id          TEXT PRIMARY KEY,           -- MD5(filepath:idx)[:16]
    document    TEXT NOT NULL,              -- 语义分块后的文本
    embedding   vector(1024) NOT NULL,      -- DashScope text-embedding-v4
    metadata    JSONB DEFAULT '{}',         -- {source_file, keywords, content_hash, ...}
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_domain_knowledge_embedding
    ON domain_knowledge USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);                    -- IVFFlat 索引，lists = sqrt(N)
```

### 2.3 什么时候有效

| 场景 | 效果 | 原因 |
|------|------|------|
| "怎么优化速度" 匹配 "性能提升策略" | 好 | 语义空间相近 |
| "写一封邮件" 匹配 "邮件模板编写指南" | 好 | 语义空间相近 |
| 不同措辞的同一问题 | 好 | 这是 embedding 的核心能力 |

### 2.4 什么时候失效

| 场景 | 效果 | 原因 |
|------|------|------|
| 精确查找 "Suspense" | 差 | 专有名词在 embedding 空间中没有独特签名 |
| 查找 "React 18" | 差 | 数字/版本号 embedding 模型难以区分 |
| 查找代码片段 "useTransition()" | 差 | 符号在文本 embedding 空间中不被特殊对待 |
| "知识库里有什么关于 React 的" | 差 | 这不是查 chunk，是查全局覆盖情况 |

### 2.5 分块策略：语义分块 (SemanticChunker)

项目中已实现的 `SemanticChunker` 在 `services/rag_service.py`:

```python
class SemanticChunker:
    """
    用相邻句子 embedding 相似度找自然断点。

    当话题切换时，相邻句子的 embedding 相似度会骤降（语义断崖），
    那里就是自然的分块边界。

    句子1: "React 18 引入了 Suspense"             │
    句子2: "Suspense 是一种新的并发特性"           │ 相似度 0.85 -- 同一主题，不切
    句子3: "使用前需要先安装 react-dom"            │ 相似度 0.78 -- 同一主题，不切
    ──────────── 语义断崖 (相似度 0.45) ──────────
    句子4: "Vue 3 也有类似的 Suspense 组件"        │
    句子5: "需要在 vue.config.js 中配置"           │ 相似度 0.72 -- 新主题开始
    """

    def __init__(
        self,
        embedding_fn,        # DashScope text-embedding-v4
        threshold: float = 0.5,    # 相似度低于此视为语义断崖
        min_chars: int = 200,      # 最小块大小，防止碎片化
        max_chars: int = 800,      # 最大块大小，超此强制切分
    ):
        ...
```

语义分块解决了三个问题：
1. 不在段落中间切断 -- 话题切换时才切
2. 保留 `##` 标题的文档结构 -- 先按标题粗分，再在每段内找语义断崖
3. 大小控制 -- `min_chars` 防碎片，`max_chars` 防过大的单个 chunk

---

## 三、Layer 2: 稀疏检索 (BM25) -- 已实现

### 3.1 是什么

```
用户 query: "React Suspense"
  → PG plainto_tsquery('simple', query) → 'react' & 'suspense'
  → GIN index on to_tsvector('simple', document) → 快速匹配
  → ts_rank() 排序 → top-20 候选
```

BM25 是经典的 TF-IDF 统计算法，不依赖 embedding，纯基于词频统计。

### 3.2 BM25 五句话原理

```
1. 把 query 和每个文档都切成词（中文依赖 'simple' 分词器 + 单字切分兜底）
2. TF (词频):       这个词在文档中出现的次数 / 文档总词数
                     → "Suspense" 在一篇 React 文档中出现 15 次 = 高 TF
3. IDF (逆文档频率): log((总文档数 - 含该词的文档数 + 0.5) / (含该词的文档数 + 0.5))
                     ↑ 稀有词（如 "Suspense"）权重高，常见词（如 "方法"）权重低
4. 文档长度归一化:   防止长文档天然占优势
5. 得分 = Σ(TF x IDF) 对所有 query 词求和

BM25 不需要 embedding，纯统计，PG 内置 tsvector 即可实现，零额外依赖。
```

### 3.3 当前实现

```python
# services/vector_store.py -- bm25_search() 方法

async def bm25_search(
    self,
    collection: str,
    query: str,
    top_k: int = 10,
) -> list[dict]:
    """
    PostgreSQL 全文检索 (BM25 等效) -- PG tsvector/tsquery。

    使用 'simple' 分词器 -- 避免 PG 默认的英文词干化对
    中文的影响（中文分词依赖 zhparser 扩展，这里用单字切分兜底）。
    """
    cur = self.conn.cursor()
    cur.execute(
        sql.SQL("""
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
    ...
```

存储层自动创建 GIN 索引 (`services/vector_store.py:ensure_tables()`):

```sql
-- 全文检索索引 (domain_knowledge 专用)
CREATE INDEX idx_domain_knowledge_fts
    ON domain_knowledge
    USING gin (to_tsvector('simple', document));
```

### 3.4 什么时候有效

| 场景 | 效果 | 原因 |
|------|------|------|
| "Suspense 用法" | 好 | 精确关键词匹配 |
| "React 18" | 好 | 数字在 tsvector 中可被索引 |
| "MAX_TOOL_ROUNDS" | 好 | 全大写标识符，BM25 IDF 天然给予高权重 |
| 代码符号 `useTransition()` | 好 | 符号在 'simple' 分词器中被保留 |

### 3.5 什么时候失效

| 场景 | 效果 | 原因 |
|------|------|------|
| "数据加载" vs "data fetching" | 差 | 同义词不匹配（需要翻译/同义词扩展） |
| "怎么加速" vs "性能优化" | 差 | 不同措辞无词汇重叠 |
| 中文 "怎么优化" vs 英文 "optimization" | 差 | 跨语言不匹配 |

---

## 四、Layer 3: 知识图谱摘要 (KG) -- 计划中

### 4.1 是什么

不检索单个 chunk，而是返回知识库中每篇 `.md` 文件的**结构化目录大纲**。

这是三层中唯一回答「知识库整体有什么」而非「某个 chunk 里有什么」的层。

### 4.2 为什么需要：真实失败案例

```
用户问: "知识库里有什么关于 React 的内容？"

当前行为 (Dense + BM25):
  → 检索到 prompt_engineering.md 中的一个 chunk:
    "在写 React 提示词时，建议指定组件名称和 props 结构..."
  → LLM 看到这个 chunk，以为知识库只有这一条 React 相关内容
  → LLM 回复: "知识库中有一条关于 React 提示词的内容..."

但假设知识库中有一整篇 react_guide.md:
  ## React 并发特性
  ## Hooks 使用指南
  ## 性能优化
  ## Suspense 与数据加载

  → 如果有了 KG 层，LLM 会看到:
    "知识库在 react_guide.md 中涵盖了 React 的并发特性、Hooks、性能优化、
     和 Suspense 数据加载 4 个主题。请告诉我你想深入了解哪个方向？"
  → 而不是只看到一个碎片
```

### 4.3 工作原理

```
Step 1: 知识库索引时预计算每篇 .md 的 ## 标题树

  react_guide.md 的内容:
    # React 开发指南
    ## 并发特性
      ### Suspense
      ### startTransition
    ## Hooks 使用
      ### useState / useEffect
      ### use() hook (React 19)
    ## 性能优化
      ### memo / useMemo
      ### 代码分割

  提取的 header_tree:
    {
      "source_file": "react_guide.md",
      "headers": [
        {"level": 2, "text": "并发特性", "path": "react_guide.md#并发特性"},
        {"level": 3, "text": "Suspense", "path": "react_guide.md#并发特性#Suspense"},
        {"level": 3, "text": "startTransition", "path": "react_guide.md#并发特性#startTransition"},
        {"level": 2, "text": "Hooks 使用", "path": "react_guide.md#Hooks 使用"},
        ...
      ],
      "total_chunks": 12,
      "keyword_summary": "React, Suspense, Hooks, 性能优化, 代码分割"
    }

Step 2: 存储到 PGVector metadata (JSONB 字段，不占向量索引)

  -- 每个 chunk 携带所属文件的 header_tree（仅在其 chunk_index=0 的 chunks 中存储全局元数据）
  -- 或者直接存在 domain_knowledge 中第一条 chunk 的 metadata 里

Step 3: 查询时按 source_file 聚合

  def kg_search(query: str, source_files: list[str]) -> list[dict]:
      """返回与 query 相关的 .md 文件的结构化目录大纲。"""
      # 1. 从 metadata 中提取所有 source_file 的 header_tree
      # 2. 按 query 关键词匹配标题 -- 找到相关的 ## 节点
      # 3. 构建结构化的 TOC 返回
      ...

Step 4: 格式化注入 Prompt

  ## 知识库目录概览
  | 文件 | 相关主题 | 覆盖范围 |
  |------|---------|---------|
  | react_guide.md | 并发特性, Suspense, Hooks | React 18-19 开发指南 |
  | prompt_engineering.md | （与当前问题无关，已省略） | -- |

  → LLM 看到这个就知道哪些文件有相关内容的全局视图
```

### 4.4 KG 层不是替代，是补充

```
KG 层的核心价值: 帮助 LLM 理解知识库的「全局视图」

Dense + BM25 回答:  "这个 chunk 里有什么？"      → 碎片视角
KG 层回答:          "这些文件里覆盖了哪些话题？"  → 全景视角

两者结合:
  LLM 先看 KG 的 TOC → 知道知识库有 React/TypeScript/部署三个方向
  再看 Dense+BM25 的 chunks → 拿到具体的内容细节
  → 最后生成: "根据知识库，React 方面推荐 react_guide.md，
    它覆盖了并发特性和 Hooks。以下是 Suspense 的具体内容: ..."
```

---

## 五、三路融合: RRF + Rerank

### 5.1 当前已实现的两路融合 (Dense + BM25)

```python
# services/rag_service.py -- query() 方法的检索管线

async def query(self, query_text: str, top_k: int = 3,
                min_score: float = None) -> list[dict]:
    """
    混合检索 + Rerank + 相似度过滤。

    Pipeline:
      1. Dense 检索 (PGVector)  → coarse_k 候选 (默认 20)
      2. BM25 检索 (PG tsvector) → coarse_k 候选 (默认 20)
      3. RRF 合并 → top-(coarse_k)                  ← ★ 关键融合点
      4. Rerank (qwen3-rerank)  → top-(rerank_top_k) (默认 5)
      5. 相似度阈值过滤          → top-k             (默认 3)
      6. 关键词重叠加权
    """

    # 1. Dense 检索
    query_emb = self.embedding_model.embed_query(query_text)
    dense_results = await self.store.search(
        collection=self.COLLECTION,
        query_embedding=query_emb,
        top_k=self.rerank_coarse_k,   # 默认 20
    )

    # 2. BM25 检索
    bm25_results = await self.store.bm25_search(
        collection=self.COLLECTION,
        query=query_text,
        top_k=self.rerank_coarse_k,   # 默认 20
    )

    # 3. RRF 合并 -- 两路结果融合为统一排名
    merged = self._rrf_fusion([dense_results, bm25_results], k=60)
    merged = merged[:self.rerank_coarse_k]

    # 4. Rerank -- 精排
    if self.rerank_enabled and len(merged) > top_k:
        documents = [r["document"] for r in merged]
        reranked = await self._rerank(query_text, documents,
                                      top_n=self.rerank_top_k)
        ...

    # 5. 相似度 + 关键词过滤
    results = [r for r in merged
               if (r.get("score", 0) >= min_score
                   or r.get("rerank_score", 0) >= 0.3)]
    results = results[:top_k]

    # 6. 关键词重叠加权
    return self._apply_keyword_boost(query_text, results)
```

### 5.2 RRF (Reciprocal Rank Fusion)

```python
# services/rag_service.py -- _rrf_fusion()

@staticmethod
def _rrf_fusion(results_lists: list[list[dict]], k: int = 60) -> list[dict]:
    """
    RRF 公式: score(d) = SUM_i ( 1 / (k + rank_i(d)) )

    其中 rank_i(d) 是文档 d 在第 i 路结果中的排名。
    k=60 是论文中验证的稳定常数 -- 确保排名的微小差异
    不会导致分数剧烈波动。

    为什么不用分数直接融合？
      稠密的 cosine distance 和 BM25 的 ts_rank 在不同尺度上，
      直接加权求和需要归一化，而 RRF 只需要排名信息即可。
      零调参，零训练数据。
    """
    fused = {}
    doc_map = {}

    for results in results_lists:
        for rank, doc in enumerate(results, start=1):
            doc_id = doc.get("id", "")
            if not doc_id:
                continue
            # RRF 核心公式: 1 / (k + rank)
            fused[doc_id] = fused.get(doc_id, 0) + 1.0 / (k + rank)
            if doc_id not in doc_map:
                doc_map[doc_id] = dict(doc)
            doc_map[doc_id]["rrf_score"] = fused[doc_id]

    sorted_ids = sorted(fused.keys(),
                        key=lambda x: fused[x], reverse=True)
    return [doc_map[i] for i in sorted_ids]
```

### 5.3 Rerank -- 百炼 qwen3-rerank

```python
# services/rag_service.py -- _rerank()

async def _rerank(self, query: str, documents: list[str],
                  top_n: int = 5) -> list[dict]:
    """
    使用百炼 qwen3-rerank 精排检索结果。

    为什么需要 Rerank？
      Bi-Encoder (Embedding):   分别编码 query 和文档，算距离 -- 快速但粗糙
      Cross-Encoder (Rerank):   拼接后一起编码，深度交互 -- 慢但精确

      策略: 粗筛 top-20 (Dense+BM25) → Rerank 精排 → top-5

    qwen3-rerank:
      - 最大 500 文档, 单条 4K token, 请求上限 120K token
      - 100+ 语言覆盖
      - API: /compatible-api/v1/reranks (兼容 OpenAI 格式)
      - 成本: ~0.02元/千次, 单次 RAG 查询 <0.001元
    """
    url = "https://dashscope.aliyuncs.com/compatible-api/v1/reranks"
    payload = {
        "model": "qwen3-rerank",
        "query": query,
        "documents": documents,
        "top_n": top_n,
        "return_documents": True,
    }
    ...
```

### 5.4 三路融合后的完整数据流

```
                             用户 query: "React 18 Suspense 数据加载"
                                  │
                                  ▼
                        ContextEngine._build_enriched_query()
                                   │
                    enriched_query: "React 18 Suspense 数据加载"
                    (长 query ≥ 80 字符，不增强)
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
    Layer 1: Dense              Layer 2: BM25          Layer 3: KG (计划中)
    PGVector cosine             PG tsvector             header_tree 元数据
    top-20                      top-20                 按 source_file 聚合
              │                    │                    │
              ▼                    ▼                    ▼
         [15 条 chunks]       [12 条 chunks]       [react_guide.md TOC]
              │                    │                    │
              └────────────────────┼────────────────────┘
                                   │
                                   ▼
                          RRF 融合 (k=60)
                    合并去重 → 统一排名 top-20
                                   │
                                   ▼
                        qwen3-rerank 精排
                     top-20 → top-5 (Cross-Encoder)
                                   │
                                   ▼
                        相似度阈值过滤 (≥ 0.6)
                          top-5 → top-3
                                   │
                                   ▼
                         关键词重叠加权
                         最终 top-3 chunks
                                   │
                                   ▼
                         注入 Prompt:
                   ## 🔴 知识库参考
                   ### 知识点 1 (来源: react_guide.md)
                     ...
                   ### 知识点 2 (来源: react_guide.md)
                     ...
                   ### 知识点 3 (来源: frontend_best_practices.md)
                     ...
                   ## 知识库目录概览 (KG)
                   | react_guide.md | 并发特性, Suspense, Hooks | ...
                                   │
                                   ▼
                          Planner / Executor
                           使用 RAG 上下文生成回答
```

### 5.5 关键词重叠加权 -- 稠密 + 稀疏之外的第三个信号

```python
# services/rag_service.py -- _apply_keyword_boost()

@staticmethod
def _apply_keyword_boost(query: str, results: list[dict],
                         boost_factor: float = 0.05) -> list[dict]:
    """
    对最终检索结果做关键词覆盖微调。

    稠密捕获语义，BM25 捕获词频，但两个都是"独立打分"。
    关键词重叠加权是"交叉验证": 一个 chunk 如果同时被
    稠密和关键词两方面命中，说明它真的相关，加分。

    对于含专有名词/代码符号的 query，这项能显著提升精度。
    """
    tech_terms = RAGService._extract_tech_terms(query)
    # 提取: ['React', 'Suspense', ...]
    # 模式: PascalCase, kebab-case, 全大写, dot.notation

    if not tech_terms:
        return results

    for r in results:
        doc_lower = r.get("document", "").lower()
        overlap_count = sum(1 for t in tech_terms
                           if t.lower() in doc_lower)
        overlap_ratio = overlap_count / len(tech_terms)

        if overlap_ratio >= 0.3:  # 至少 30% 的技术术语被覆盖
            # 微调分数: boost_factor = 0.05，影响很小
            # 但在分数接近的候选中足以做出正确排序
            if "rerank_score" in r:
                r["rerank_score"] += overlap_ratio * boost_factor
            elif "score" in r:
                r["score"] = min(1.0, r["score"] + overlap_ratio * boost_factor)
    ...
```

---

## 六、与现有实现的对比

### 6.1 已完成 (Dense + BM25 + RRF + Rerank)

| 组件 | 状态 | 位置 | 说明 |
|------|------|------|------|
| Dense 检索 | 已实现 | `rag_service.py` L371-375 | PGVector + cosine distance |
| BM25 检索 | 已实现 | `vector_store.py` L303-363 | PG tsvector + GIN index, 'simple' 分词器 |
| RRF 融合 | 已实现 | `rag_service.py` L582-614 | k=60, 双路排名融合 |
| Rerank | 已实现 | `rag_service.py` L525-576 | qwen3-rerank, top-20 -> top-5 |
| 相似度过滤 | 已实现 | `rag_service.py` L402-406 | threshold=0.6 |
| 关键词加权 | 已实现 | `rag_service.py` L616-651 | tech_terms 交叉验证 |
| 语义分块 | 已实现 | `rag_service.py` L34-173 | SemanticChunker, 相邻句子相似度断崖 |
| 上下文 Query 增强 | 已实现 | `rag_service.py` L451-517 | 多源信号组合，不扩写只组合 |
| 幻觉防御 | 已实现 | `graph.py` L56-78+L428-509 | Checkpoint + Reflector 双层 |

### 6.2 缺失: KG 层

| 缺失 | 影响 | 优先级 |
|------|------|--------|
| source_file 聚合查询 | 无法回答 "知识库有什么" 类问题 | P2 |
| header_tree 预计算 | 无法提供结构化目录大纲 | P2 |
| KG 结果格式化注入 | LLM 看不到知识库全局视图 | P2 |

### 6.3 KG 层会带来什么

```
Before (只有 Dense + BM25):
  用户: "知识库里有什么关于 React 的内容？"
  LLM 看到: 3 个孤立的 chunk，其中 1 个包含 "React" 但上下文不完整
  LLM 回答: "知识库中有一条关于 React 提示词的建议..."

After (Dense + BM25 + KG):
  用户: "知识库里有什么关于 React 的内容？"
  LLM 看到: 3 个 chunk + 结构化 TOC:
    react_guide.md
      ## 并发特性 → Suspense, startTransition
      ## Hooks 使用 → useState, useEffect, use()
      ## 性能优化 → memo, useMemo, 代码分割
  LLM 回答: "知识库在 react_guide.md 中覆盖了 React 的并发特性、
    Hooks 使用、和性能优化三个主题。你想深入了解哪个方向？"
```

---

## 七、实施路线

### Step 1: 预计算文档目录大纲

```
改动文件: services/rag_service.py -- ingest_knowledge_base() 扩展

在索引每个 .md 文件时，同时解析 ## 标题树，
存入第一条 chunk 的 metadata 中:

metadata = {
    "source_file": "react_guide.md",
    "chunk_index": 0,
    "header_tree": [
        {"level": 2, "text": "并发特性", "path": "react_guide.md#并发特性"},
        {"level": 3, "text": "Suspense", "path": "react_guide.md#并发特性#Suspense"},
        ...
    ],
    "total_chunks": 12,
    "keyword_summary": "React, Suspense, Hooks, 性能优化",
    ...
}
```

提取 header_tree 的函数（~30 行）:

```python
@staticmethod
def _extract_header_tree(md_content: str, source_file: str,
                         max_depth: int = 3) -> list[dict]:
    """从 Markdown 内容中提取 ## / ### 标题树。"""
    import re
    headers = []
    for match in re.finditer(r'^(#{2,3})\s+(.+)$', md_content, re.MULTILINE):
        level = len(match.group(1))
        if level > max_depth:
            continue
        text = match.group(2).strip()
        # 去掉链接和格式标记
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        headers.append({
            "level": level,
            "text": text,
            "path": f"{source_file}#{text.replace(' ', '-')}",
        })
    return headers
```

### Step 2: 添加 KG 检索方法

```
改动文件: services/rag_service.py -- 新增 kg_search() 方法

async def kg_search(self, query: str) -> str:
    """
    知识图谱检索 -- 返回与 query 相关的 .md 文件的结构化目录大纲。

    不检索单个 chunk，而是按 source_file 聚合 header_tree。
    """
    ...

预计行数: ~60 行
```

### Step 3: 接入 RRF 融合作为第三路输入

```
改动文件: services/rag_service.py -- query() 方法

当前:
    merged = self._rrf_fusion([dense_results, bm25_results], k=60)

改造后:
    kg_results = await self.kg_search(query_text)
    # kg_results 不是按 chunk 排名的列表，而是按 source_file 的相关度排序
    # 需要对 kg_results 做一个排名映射（按关键词匹配度）
    merged = self._rrf_fusion(
        [dense_results, bm25_results, kg_chunks_ranked], k=60
    )

但注意: KG 的结果是 "源文件级别的目录大纲"，和 chunk 级别的结果混合
       需要特殊处理 -- 不是在 RRF 中融合，而是作为独立的 context block 注入。

更好的方案: KG 不走 RRF 融合，而是作为独立的 Prompt 注入段落:

def query_formatted(self, query_text: str, top_k: int = 3) -> str:
    chunks = await self.query(query_text, top_k)
    kg_overview = await self.kg_search(query_text)  # 独立调用

    # 格式化: chunks 作为主要参考，kg 作为全局视图
    parts = [kg_overview, "", chunks_formatted]
    return "\n".join(parts)
```

### Step 4: 格式化 KG 结果为结构化 TOC

```
改动文件: services/rag_service.py -- query_formatted() 扩展

在现有 ## 🔴 知识库参考 之前插入 ## 知识库目录概览:

async def query_formatted(self, query_text: str, top_k: int = 3) -> str:
    results = await self.query(query_text, top_k)
    kg_overview = await self.kg_search(query_text)

    lines = []

    # ── KG 层: 全局视图 ──
    if kg_overview:
        lines.append("## 知识库目录概览")
        lines.append(kg_overview)
        lines.append("")

    # ── Dense + BM25: 具体 chunk ──
    if results:
        lines.append("## 🔴 知识库参考")
        lines.append("以下信息必须作为回答的基础:")
        lines.append("")
        for i, r in enumerate(results, 1):
            source = r.get("metadata", {}).get("source_file", "未知来源")
            lines.append(f"### 知识点 {i} (来源: {source})")
            lines.append(r["document"])
            lines.append("")
    else:
        lines.append("（未找到相关知识。以下回答基于通用知识，可能不准确。）")

    return "\n".join(lines)
```

### 总览

| 步骤 | 改动文件 | 预计行数 | 影响范围 |
|------|---------|---------|---------|
| Step 1: header_tree 提取 | `rag_service.py` | ~30 行 | 索引时 |
| Step 2: kg_search 方法 | `rag_service.py` | ~60 行 | 查询时 |
| Step 3: 接入 query 管线 | `rag_service.py` | ~15 行 | 查询时 |
| Step 4: 格式化注入 | `rag_service.py` | ~20 行 | Prompt 构造 |
| **合计** | | **~125 行** | 零新依赖，纯增量改动 |

---

## 八、配置总览

所有三层 RAG 相关配置集中在 `config.py`:

```python
# config.py -- RAG 配置

# === Layer 1: Dense ===
rag_top_k: int = 3                # 最终返回 chunk 数
rag_chunk_min: int = 200          # 语义分块最小字符
rag_chunk_max: int = 800          # 语义分块最大字符
similarity_threshold: float = 0.6  # 相似度过滤阈值

# === Layer 2: BM25 ===
# 无需额外配置 -- PG tsvector + GIN index 自动生效
# 'simple' 分词器写在 vector_store.py:bm25_search() 中

# === Layer 2.5: Rerank ===
rerank_enabled: bool = True       # 是否启用 Rerank
rerank_model: str = "qwen3-rerank" # 百炼 Rerank 模型
rerank_top_k: int = 5             # Rerank 后保留数
rerank_coarse_k: int = 20          # 粗筛候选数 (Dense + BM25 各取此数)

# === Layer 3: KG (计划中) ===
# kg_enabled: bool = True          # 是否启用 KG 层
# kg_max_files: int = 5            # 最多返回几个文件的 TOC
```

---

## 九、相关文件索引

| 文件 | 角色 | 三层相关 |
|------|------|---------|
| `services/rag_service.py` | **核心** -- SemanticChunker、Dense 检索、BM25 检索、RRF 融合、Rerank、关键词加权、Query 增强、KG 检索 (待加) | L1+L2+L3 |
| `services/vector_store.py` | **存储** -- PGVector CRUD、bm25_search()、GIN 索引、IVFFlat 索引 | L1+L2 |
| `core/context_engine.py` | **Query 增强** -- `_build_enriched_query()`、L3 事实提供 | L1+L2 |
| `core/graph.py` | **消费端** -- `enrich_query_node` -> `rag_retrieve_node`、Checkpoint 幻觉防御、Reflector 质量检查 | 消费 |
| `core/agent.py` | **编排端** -- `_build_initial_state()` 调用 ContextEngine | 编排 |
| `config.py` | **参数** -- `rag_top_k`、`similarity_threshold`、`rerank_*`、分块参数 | 配置 |
| `prompts/system_prompts.py` | **Prompt** -- Planner/Executor/Reflector 的 RAG 使用指令 | 消费 |
| `routers/knowledge.py` | **API** -- `/api/knowledge/search` 接口 | 对外 |
| `knowledge_base/*.md` | **数据** -- 手写领域知识，KG 层的原材料 | L1+L3 |

---

## 十、常见问题

### Q: 为什么三层不能合并成一层大模型？

「一个模型解决所有问题」的幻觉。Cross-Encoder (Rerank) 虽然精确，但无法在全体文档上逐对比较（太慢）。Bi-Encoder (Embedding) 快但无法理解术语精确匹配。BM25 擅长术语但不懂语义。三层是精度、速度和覆盖面的工程权衡 -- 每一层做自己最擅长的事。

### Q: KG 层是不是过度设计？Dense + BM25 不就够了吗？

对于「找一个 chunk」的场景，Dense + BM25 确实够了。但 KG 解决的是另一个问题：「知识库里有哪些内容值得关注？」。这是一个全局查询，不是局部检索。没有 KG 层，LLM 只能从 3 个孤立的 chunk 中「盲人摸象」，不知道知识库里还有什么其他相关内容。KG 层的成本很低（预计算一次，查询零额外 LLM 调用），性价比极高。

### Q: KG 层的 header_tree 和 RAG 的 chunk 存储冲突吗？

不冲突。header_tree 存储在 chunk 的 metadata JSONB 字段中，不占向量索引。推荐方案：每个 source_file 的第一条 chunk (chunk_index=0) 的 metadata 中携带该文件的 `header_tree`。查询时按 `source_file` 聚合去重即可。

### Q: BM25 的 'simple' 分词器对中文效果好吗？

'plain' 比 'simple' 好（有英文词干化），但中文分词需要 `zhparser` 扩展。当前项目用 'simple' 作为兜底：中文按单字切分，英文保留原始词形。对于以英文术语为主的技术文档（React、Suspense、API），'simple' 分词器效果足够。如果需要更好的中文支持，可以安装 `zhparser` 扩展并将 `to_tsvector('simple', ...)` 替换为 `to_tsvector('zhparser', ...)`。

### Q: 三层的性能开销是多少？

```
Layer 1 Dense:   1 次 embedding API 调用 (~50ms) + PGVector 检索 (~5ms)   = ~55ms
Layer 2 BM25:    PG tsvector 全文检索 (~10ms)                             = ~10ms
Layer 3 KG:      JSONB metadata 查询 + 聚合 (~5ms, 无 API 调用)            = ~5ms
RRF 融合:        纯计算 (~1ms)                                             = ~1ms
Rerank:          1 次 API 调用 (~100ms, 重排 20 个文档)                    = ~100ms
关键词加权:      正则提取 + 分数微调 (~1ms)                                = ~1ms
────────────────────────────────────────────────────────────────────────
总计:            ~172ms (三层全开) vs ~155ms (只用 L1+L2) vs ~55ms (只用 L1)
```

KG 层的增量成本是 ~5ms（零 API 调用），完全值得。
