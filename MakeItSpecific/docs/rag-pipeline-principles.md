# RAG 检索·编排·过滤原理详解

> 对应实现：`services/rag_service.py`（RAGService V5）、`services/vector_store.py`（PGVectorStore）、`services/document_processor.py`（来源感知分块）。
> 本文按「索引侧（写入时）」和「检索侧（查询时）」两阶段，逐环节拆解每个算法、每个阈值、每条过滤规则的原理。

---

## 一、一句话概述

Alfred 的 RAG 是一条**「双通道召回 → RRF 融合 → 精排 → 多层过滤 → 上下文补全」**的流水线：

```
索引侧（离线）：.md 文件 → 来源元数据 → 语义分块 → 双通道文本 → PGVector + KG
检索侧（在线）：query → Dense(向量) + Sparse(全文) → RRF 融合 → qwen3-rerank 精排
               → 相似度阈值过滤 → 关键词加权 → 邻接 Chunk 召回 → 来源恢复
```

核心设计思想是**「来源感知」**：每个 Chunk 不只是"一段文字"，而是"一段文字 + 它来自哪里 + 它在原文中的位置 + 它的前后文"，让检索结果能自证来源、能还原上下文。

---

## 二、索引侧原理（写入时）

索引入口是 `RAGService.ingest_knowledge_base()`（`rag_service.py:98`），对 `knowledge_base/` 下每个 `.md` 走 6 步。

### 2.1 SourceParser — 来源元数据提取

`SourceParser.parse()`（`document_processor.py:186`）从每个文件的 **YAML frontmatter**（`--- ... ---`）或正文开头的 `> 来源: ...` 描述行提取文档级元数据：

```
source_title / source_url / source_type / repository / author / accessed_at / version_or_commit
```

**关键原则**：来源元数据是**不可分割**的，不参与语义分块，而是在后面（ChunkBuilder）**原样复制到每个子 Chunk**。这样无论 Chunk 被切多碎，都能追溯来源。

`SourceMetadata.from_frontmatter()` 支持字段别名映射（`source_title` 也认 `title`/`name`；`source_url` 也认 `url`/`link`），无 frontmatter 时用文件名兜底。

### 2.2 SourceSplitter — 多来源/工具卡拆分

`SourceSplitter.split()`（`document_processor.py:359`）把一个文件拆成**一个或多个独立 Document**：

- **单来源**：一个文件 → 一个 Document。
- **多来源**（正文含 `## 来源1` / `## Source 1` 等标记）：按 `## 来源` 正则切分，每个来源 → 一个独立 Document，各自携带 `source_refs`。
- **工具卡片集合**（含 `<!-- TOOL CARD N START/END -->` 标记）：`_extract_tool_cards()` 把 20 张卡片拆成 20 个独立 Document，卡片级 frontmatter（`name/category/source_url/risk_level`）提取为独立元数据，`source_type` 标记为 `tool_card`。

**意义**：一个文件里混了 10 个来源，如果整篇一起分块，来源就混了。先拆 Document 再各自分块，保证"来源精确到 Document 级"。

### 2.3 SemanticChunker — 语义分块（核心算法）

`SemanticChunker.chunk()`（`document_processor.py:552`），参数 `threshold=0.5, min_chars=200, max_chars=800`。

算法分 4 层，**从粗到细**：

1. **按标题切**：`_split_by_headers` 用 `\n(?=## )` 把正文切成 section（只认二级标题 `## `）。
2. **句子切分**：`_split_sentences` 用 `(?<=[。！？.!?\n])\s*` 按标点+换行切句，丢弃长度 < 5 的碎片。
3. **语义断崖检测**：对相邻句子两两算 **cosine 相似度**（`_cosine_similarity`，numpy 实现），相似度 `< threshold(0.5)` 的相邻位置记为**断点**（breakpoint）——语义在这里发生了跳变。
4. **按断点成块**：`_split_at_breakpoints` 沿断点切分；切出的段如果 `< min_chars(200)` 且不是最后一段就丢弃（并入前段），如果 `> max_chars(800)` 就 `_force_split` 硬切。

**为什么用 embedding 相似度断崖而不是固定字数切块**：固定字数会在语义不连贯处硬切（一句话被劈两半）；语义断崖则让"话题切换点"自然成为块边界，每个 Chunk 内部语义更自洽。

**降级**：embedding 调用抛异常时，`_fallback_chunk` 退回纯按 `max_chars` 硬切。

### 2.4 ChunkBuilder — 双通道检索文本构建

这是**理解检索为什么是"双通道"的关键**。`ChunkBuilder.build()`（`document_processor.py:702`）为每个 Chunk 装配两段**不同的**文本：

| 通道 | 文本构成 | 用途 |
|---|---|---|
| **稠密 `search_text_dense`** | `source_title \| category \| entity_names \| section_title \| body` | 生成 embedding，做**语义**检索 |
| **稀疏 `search_text_sparse`** | `repository url author category entity_names` | 做**精确**全文匹配 |

同时建立 **Identity Chain**（`ChunkIdentity.build_chain`）：`chunk_id / document_id / parent_id / previous_chunk_id / next_chunk_id / chunk_index`，其中 chunk_id = `md5(f"{document_id}:chunk:{i}")[:16]`，prev/next 由相邻 index 推导。这条链是后面"邻接 Chunk 召回"的基础。

**设计意图**：
- 稠密通道把"来源标题 + 实体 + 小节标题 + 正文"一起喂给 embedding，让**来源信息和正文共同参与语义匹配**——查"React 状态管理"时，一个标题写着 React、正文谈状态管理的 Chunk 能被语义命中。
- 稀疏通道单独把 repository/URL/author/专有名词摘出来，让"精确词面匹配"（比如某个仓库名、某个人名、某个技术名词）不受正文稀释。

**实体抽取**：`SemanticChunker._extract_entities`（`document_processor.py:661`）用 5 组正则抽实体——PascalCase（`React`）、连字符（`post-commit`）、全大写缩写（`URL`）、点分（`a.b.c`）、CJK 双字词（`[一-鿿]{2,8}`），再过滤英文停用词和中文虚词，取前 15 个。

### 2.5 KnowledgeGraph — 证据链

`KnowledgeGraphBuilder.build_edges()`（`document_processor.py:831`）建立四层关系，落在 4 张普通 PG 表（非向量表）：

```
knowledge_sources   (来源)     source_id, source_title, source_url, ...
knowledge_documents (文档)     document_id FK→sources
knowledge_chunks    (Chunk)    ← 即 PGVector collection，metadata 带 source_id/document_id
knowledge_claims    (Claim)    claim_id FK→chunks，由 save_claim() 运行时写入
```

来源 ID `source_id = "src_" + md5(source_title + source_url)[:12]`。Chunk→Source/Document 的边不单独建表，而是**存回 Chunk 的 metadata**（`document_id`/`source_id`），`kg_lookup(chunk_id)` 用 JOIN 反查整条链（`rag_service.py:520`）。

### 2.6 写入与去重

写入 `knowledge_chunks` collection（`_ingest_one_file`，`rag_service.py:135`）：

- **去重**：`store.exists_by_metadata(CHUNK_COLLECTION, {"content_hash": c["content_hash"]})`，`content_hash = md5(body)`，相同正文跳过。
- **embedding**：对 `search_text_dense` 批量 `embed_documents`（一次调用），向量维度 1024。
- **存储**：PGVector 的 `document` 主字段存的是 `search_text_dense`（不是纯 body），metadata 存 identity chain + `search_text_sparse` + `source_metadata` + `entity_names` 等。

> ⚠️ 见 §七"已知问题"第 1 条——代码注释声称"正文存于 metadata.body_text"，但 metadata 里**没有** body_text 字段，纯正文只在 `search_text_dense` 的末段里。

---

## 三、检索侧原理（查询时）

检索入口 `RAGService.query()`（`rag_service.py:267`），默认 `top_k=3, min_score=0.6`。完整 pipeline：

```
query
 ├─ 1. Dense  向量检索          top_k = rerank_coarse_k(20)
 ├─ 2. Sparse 全文检索          top_k = 20
 ├─ 3. RRF 融合                 k=60，合并两路结果按 rrf_score 排序 → 取前 20
 ├─ 4. Rerank 精排              qwen3-rerank，top_n = rerank_top_k(5)
 ├─ 5. 相似度阈值过滤            score≥0.6 OR rerank_score≥0.3
 ├─ 6. 关键词加权               _apply_keyword_boost
 ├─ 7. 邻接 Chunk 召回          前 3 条的 prev/next，最多 5 个
 ├─ 8. 来源元数据恢复           source_metadata/source_refs/identity 反序列化
 └─ 返回 top_k(3)
```

### 3.1 Dense — 稠密向量检索

`store.search()`（`vector_store.py:308`）对 `query` 生成 embedding，用 **cosine 相似度**检索：

```sql
SELECT ..., 1 - (embedding <=> %s::vector) AS score
FROM knowledge_chunks ORDER BY embedding <=> %s::vector LIMIT %s
```

`<=>` 是 pgvector 的 cosine 距离（越小越相似），`1 - 距离` 转成相似度（越大越相似），所以 `score` 是 **0~1 的 cosine 相似度**。走 IVFFlat 索引（`vector_cosine_ops`，lists=100）。召回 `rerank_coarse_k=20` 条作为粗排候选。

### 3.2 Sparse — 稀疏全文检索

`_sparse_search()`（`rag_service.py:367`），**不是真 BM25**（见 §七第 2 条），而是 PostgreSQL `tsvector/tsquery` + `ts_rank`：

```sql
SELECT ..., ts_rank(to_tsvector('simple', metadata->>'search_text_sparse'),
                    to_tsquery('simple', %s)) AS score
FROM knowledge_chunks
WHERE to_tsvector('simple', metadata->>'search_text_sparse') @@ to_tsquery('simple', %s)
ORDER BY score DESC LIMIT %s
```

细节：
- **检索对象**是 `metadata->>'search_text_sparse'`（repository+url+author+category+实体名），**不含正文**——所以稀疏通道专抓"专有名词的精确命中"。
- **分词器**用 `'simple'`（`rag_service.py:392`），避免 PG 默认英文词干化对中文的干扰；中文靠单字/词组切分兜底。
- **tsquery 构造**：`query + 提取出的实体` 拼起来，非字母数字转空格，取 `len≥2` 的词，用 `&` AND 连接（`rag_service.py:387`）——即要求**所有词都命中**（严格 AND 语义，和稠密检索的模糊匹配互补）。
- `ts_rank` 是**词频+归一化**的打分，和 cosine 尺度不同（值通常偏小，见 §三.5 的尺度陷阱）。

### 3.3 RRF 融合（Reciprocal Rank Fusion）

`_rrf_fusion()`（`rag_service.py:642`）把 Dense、Sparse 两路结果融合成一路。公式：

```
RRF(doc) = Σ_{每路结果} 1 / (k + rank_doc)
```

其中 `k=60`，`rank` 是该文档在某一路结果里的排名（从 1 开始）。**直觉**：一个文档在两路里都排得靠前，RRF 分就高；只在一路靠前，RRF 分就低。RRF 不需要对两路分数做归一化（因为只关心**排名**，不关心绝对分数），这是它比"加权求和"更稳的地方——cosine 和 ts_rank 尺度不同也能公平融合。

**实现细节**：`doc_map[did]` 保留**第一次出现**的那路结果（dense 在前），所以融合后的 `score` 字段 = 该文档在 dense 路的 cosine 分（若只出现在 sparse 路，则 = ts_rank 分）。`rrf_score` 单独累积。融合后按 `rrf_score` 降序，截取前 `rerank_coarse_k(20)`。

### 3.4 Rerank — 交叉编码器精排

`_rerank()`（`rag_service.py:624`）调百炼 `qwen3-rerank`（DashScope compatible-api `/v1/reranks`），把粗排的 top-20 文档和 query 一起送给**交叉编码器**精排，返回 `top_n=5` 个结果及 `relevance_score`。

**为什么需要 Rerank**：向量检索（双塔模型）把 query 和 doc 各自编码再算余弦，速度快但精度有限；rerank（交叉编码器）把 query+doc **拼成一条输入一起编码**，能捕捉更细的语义交互，精度高但慢。所以典型做法是"向量粗召回 → rerank 精排"，本实现正是这个套路。

- 仅当 `rerank_enabled=True` **且 `len(merged) > top_k(3)`** 时才 rerank（候选太少不值得）。
- rerank 只对**最终 `top_k` 之前的候选**重排，返回的 `index` 用于回查原 `merged`，拼上 `rerank_score`。
- rerank 失败（非 200 或超时）→ 返回空列表 → 跳过 rerank，直接用 RRF 排序结果。

### 3.5 相似度/阈值过滤

```python
results = [r for r in merged
           if (r.get("score", 0) >= min_score or r.get("rerank_score", 0) >= 0.3)]
results = results[:top_k]
```

双阈值 OR 关系：
- `score >= 0.6`：cosine 相似度达标（`SIMILARITY_THRESHOLD=0.6`）。
- `rerank_score >= 0.3`：rerank 相关性达标。

**尺度陷阱（重要）**：`score` 字段混合了两种尺度——dense 路的 cosine（0~1）和 sparse-only 文档的 ts_rank（通常远小于 0.6）。所以**只被稀疏路召回、没被稠密路召回的文档**，`score` 是 ts_rank 值，几乎过不了 `≥0.6` 的门，只能靠 `rerank_score≥0.3` 被捞回来。这意味着：**稀疏通道的贡献主要体现在"提升 RRF 排名"（把精确命中推到靠前），而不体现在"独立通过阈值"**——sparse-only 文档能否存活，取决于 rerank 是否给了 ≥0.3 分。

### 3.6 关键词加权

`_apply_keyword_boost()`（`rag_service.py:656`）：

- 用 `_extract_tech_terms` 从 query 抽技术术语（**只有英文 4 组正则，不含 CJK**，见 §七第 3 条）。
- 对每条结果，算 `overlap = 命中的术语数 / query 术语总数`。
- 若 `overlap >= 0.3`，对 `rerank_score` 和 `score` 各加 `overlap × 0.05`（封顶 1.0）。
- 最后按 `max(rerank_score, score)` 重新降序。

**意图**：把"词面命中了 query 术语"的文档略微上浮，弥补语义检索对专有名词不够敏感的问题。

### 3.7 邻接 Chunk 召回

`_fetch_adjacent_chunks()`（`rag_service.py:415`）：取**前 3 条**结果，读它们的 `previous_chunk_id` / `next_chunk_id`，把不在结果里的邻居 Chunk 用 `get_by_id` 补进来（最多 5 个），打上 `_adjacent=True`、`score=0.3` 标记。

**意图**：语义分块可能把"一个完整知识点"切在两块里，召回主 Chunk 后顺手把前后文补回来，避免回答断章取义。邻接 Chunk 不参与打分排序（score 固定 0.3），仅作上下文补充，前端标 `[邻接上下文]`。

### 3.8 来源元数据恢复

`query()` 末尾把 JSON 字符串字段反序列化：`source_metadata`、`source_refs`，并组装 `identity` 字典（chunk_id/document_id/parent_id/chunk_index/prev/next）。`query_formatted()`（`rag_service.py:452`）据此渲染成带来源链接的引用块，最后追加"规则：基于以上内容回答，不要编造知识库中不存在的信息"的防幻觉约束。

---

## 四、参数速查表

| 参数 | 默认值 | 位置 | 作用 |
|---|---|---|---|
| `SIMILARITY_THRESHOLD` | 0.6 | `rag_service.py:39` | cosine 达标线 |
| `rerank_coarse_k` | 20 | `__init__` | Dense/Sparse 粗召回条数 |
| `rerank_top_k` | 5 | `__init__` | rerank 精排条数 |
| `rerank_model` | qwen3-rerank | `__init__` | 交叉编码器 |
| RRF `k` | 60 | `_rrf_fusion` | 排名融合平滑系数 |
| 语义分块 `threshold` | 0.5 | `SemanticChunker` | 相邻句相似度断崖阈值 |
| `chunk_min` / `chunk_max` | 200 / 800 | `__init__` | 分块字数上下界 |
| keyword boost `factor` | 0.05 | `_apply_keyword_boost` | 关键词加权幅度 |
| keyword boost 触发 | overlap ≥ 0.3 | 同上 | 术语命中比例门槛 |
| rerank 存活线 | rerank_score ≥ 0.3 | `query` | rerank 达标线 |
| 邻接召回 | 前3条 / 最多5个 / score=0.3 | `_fetch_adjacent_chunks` | 上下文补全 |
| 最终返回 | top_k=3 | `query` | 用户可见结果数 |
| embedding | text-embedding-v4, 1024维 | `embedding_model` | 稠密向量 |

---

## 五、降级链

从入口到最底层，共 4 级降级：

1. **整条 pipeline 异常**（`query` 的 `except`，`rag_service.py:356`）→ 只用 Dense 向量检索兜底返回 top_k。
2. **`query_formatted` 无结果** → `_legacy_query` 查旧 collection `domain_knowledge`（`rag_service.py:507`）。
3. **仍无结果** → 返回固定话术"（未找到相关知识。以下回答基于通用知识，可能不准确。）"。
4. **语义分块 embedding 异常**（索引侧）→ `_fallback_chunk` 纯字数硬切。

---

## 六、与 ContextEngine 的 Query 增强的衔接

检索 query 不是原始用户消息，而是经 `core/context_engine.py` 的 `_build_enriched_query` 增强过的（按消息长度分三档注入 L3 事实 / 已确认维度 / L2 摘要）。`RAGService.build_context_query()`（`rag_service.py:574`）是这套逻辑的向后兼容副本。**两者的共同原则**：长 query 不加上下文（保护原始语义），短 query 用多源信号补全，只组合用户真实说过的话、不凭空扩写。

---

## 七、已知问题 / 命名不准确（务必留意）

1. **`body_text` 未单独落库**：`_ingest_one_file` 的注释写"实际正文内容存于 metadata.body_text"（`rag_service.py:205`），但 metadata 字典里**没有 body_text 键**。纯正文只在 `search_text_dense` 的末段（前面是 title/category/entities/section_title）。所以 `query_formatted` 展示的"知识点内容"其实是**带前缀的稠密文本**，不是干净正文。

2. **"BM25" 名不副实**：`vector_store.bm25_search` 和 `_sparse_search` 的注释都写"BM25 等效"，但实际是 PostgreSQL `ts_rank`（词频+归一化），**不是 BM25**（BM25 有 IDF 饱和 + 文档长度归一化，公式不同）。而且 pipeline 实际走的是 `_sparse_search`，`bm25_search`（索引在 `document` 字段上）**没有被 V5 检索调用**。

3. **稀疏检索无索引**：`ensure_tables` 建的 GIN 全文索引是 `to_tsvector('simple', document)`（`vector_store.py:161`），但 `_sparse_search` 查的是 `to_tsvector('simple', metadata->>'search_text_sparse')`——**不同表达式，GIN 索引不生效**，等于每次全表扫描 + 现场算 tsvector。数据量大后会成为性能瓶颈；要么给 `search_text_sparse` 建 GIN，要么加一个物化的 tsvector 列。

4. **关键词加权对中文失效**：`_apply_keyword_boost` 用的 `_extract_tech_terms`（`rag_service.py:675`）**不含 CJK 正则**（而 `SemanticChunker._extract_entities` 有 `[一-鿿]{2,8}`）。所以中文技术术语不会被加权，中文 query 的 keyword boost 基本空转。

5. **RRF 后 `score` 尺度混合**：见 §三.5——融合后文档的 `score` 字段可能是 cosine（dense 路）或 ts_rank（sparse-only 路），阈值 `≥0.6` 对两类文档含义不一致，sparse-only 文档实际靠 rerank 救回。

---

## 八、速记心智模型

- **双通道 = 语义（dense）+ 词面（sparse）互补**，一个抓"意思像"，一个抓"字面准"。
- **RRF = 只看排名不看分数**，把两种尺度的结果公平合并。
- **Rerank = 交叉编码器精排**，牺牲速度换精度，只对粗排 top-20 做。
- **阈值过滤 = 双门 OR**：cosine≥0.6 或 rerank≥0.3。
- **邻接召回 = 补上下文**，把被切碎的知识点拼回来。
- **来源感知 = 元数据不可分割、复制到每个 Chunk**，让结果能自证出处。
