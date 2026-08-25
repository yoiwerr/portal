# 课程 11：RAG 系统 — 混合检索管道 V5

> **难度**: 高级 | **预计阅读**: 25 分钟 | **前置**: [04-上下文引擎](04-上下文引擎.md)

---

## 一、RAG V5 架构全景

```
用户 Query
    │
    ├── 1. Dense 检索 (PGVector)
    │      search_text_dense → embedding → 向量相似度 top_k
    │
    ├── 2. Sparse 检索 (BM25 tsvector)
    │      search_text_sparse → PostgreSQL GIN 全文索引
    │
    ├── 3. RRF 融合
    │      合并 Dense + Sparse 结果，加权排序
    │
    ├── 4. Rerank 精排
    │      百炼 qwen3-rerank (120K token, 500 docs)
    │
    ├── 5. 相似度过滤
    │      过滤 score < 0.6 的结果
    │
    ├── 6. 关键词加权
    │      技术术语匹配度高的结果提权
    │
    ├── 7. 邻接 Chunk 召回
    │      通过 previous/next_chunk_id 补充上下文
    │
    └── 8. 来源元数据恢复
          解包 source_metadata + identity chain
```

---

## 二、知识库索引流程

### 2.1 文档处理管道

```
.md 文件
  → SourceParser:    提取 frontmatter 元数据 (source_title, URL, repository, author…)
  → SourceSplitter:  多来源文档拆分 (含工具卡片拆分)
  → SemanticChunker: 按语义边界切分 (embedding 相似度断崖检测)
  → ChunkBuilder:    装配 Chunk (复制元数据 + identity chain)
  → KnowledgeGraph:  建立 Source→Document→Chunk→Claim 边
  → PGVector:        写入 knowledge_chunks 表 + KG 表
```

### 2.2 Chunk 结构

每个 Chunk 包含：
- `chunk_id` / `document_id` / `parent_id`
- `previous_chunk_id` / `next_chunk_id` (邻接链)
- `search_text_dense`: "source_title + entity_names + section_title + body" (用于向量检索)
- `search_text_sparse`: "repository + URL + author + 专有名称" (用于 BM25 全文检索)
- `source_metadata`: 完整的来源信息
- `content_hash`: MD5 去重

---

## 三、混合检索详解

### 3.1 Dense 检索 (向量)

```python
query_emb = self.embedding_model.embed_query(query_text)
dense_results = await self.store.search(
    collection=CHUNK_COLLECTION,
    query_embedding=query_emb,
    top_k=self.rerank_coarse_k,   # 默认 20
)
```

### 3.2 Sparse 检索 (BM25)

```python
async def _sparse_search(self, query, top_k=10):
    # 提取技术术语做精确匹配
    entities = self._extract_tech_terms(query)
    search_terms = query + " " + " ".join(entities)

    # PostgreSQL tsvector 全文检索
    tsquery = " & ".join(terms[:10])
    cur.execute(f"""
        SELECT id, document, metadata,
               ts_rank(
                   to_tsvector('simple', metadata->>'search_text_sparse'),
                   to_tsquery('simple', %s)
               ) AS score
        FROM {CHUNK_COLLECTION}
        WHERE to_tsvector('simple', coalesce(metadata->>'search_text_sparse', ''))
              @@ to_tsquery('simple', %s)
        ORDER BY score DESC
        LIMIT %s
    """, (tsquery, tsquery, top_k))
```

### 3.3 RRF 融合 (Reciprocal Rank Fusion)

```python
@staticmethod
def _rrf_fusion(results_lists, k=60):
    fused = {}
    doc_map = {}
    for results in results_lists:
        for rank, doc in enumerate(results, start=1):
            did = doc.get("id", "")
            # RRF score: 1 / (k + rank)
            fused[did] = fused.get(did, 0) + 1.0 / (k + rank)
            doc_map[did] = dict(doc)
            doc_map[did]["rrf_score"] = fused[did]
    return sorted by rrf_score desc
```

### 3.4 Rerank 精排

```python
async def _rerank(self, query, documents, top_n=5):
    url = "https://dashscope.aliyuncs.com/compatible-api/v1/reranks"
    payload = {
        "model": "qwen3-rerank",
        "query": query,
        "documents": documents,
        "top_n": top_n,
        "return_documents": True,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            data = await resp.json()
            return data.get("results", [])
```

### 3.5 关键词加权

```python
@staticmethod
def _apply_keyword_boost(query, results, boost_factor=0.05):
    tech_terms = RAGService._extract_tech_terms(query)
    for r in results:
        doc_lower = r.get("document", "").lower()
        overlap = sum(1 for t in tech_terms if t.lower() in doc_lower) / len(tech_terms)
        if overlap >= 0.3:
            r["score"] = min(1.0, r["score"] + overlap * boost_factor)
    return sorted by score desc
```

---

## 四、知识图谱

```
knowledge_sources (来源)
    │ 1:N
    ▼
knowledge_documents (文档)
    │ 1:N
    ▼
knowledge_chunks (分块, PGVector)
    │ 1:N
    ▼
knowledge_claims (声明, 可验证的事实片段)
```

### 关键查询

```python
async def kg_lookup(self, chunk_id):
    """从 Chunk ID 沿知识图谱查找 Source → Document 链。"""
    cur.execute("""
        SELECT ks.*, kd.*
        FROM knowledge_sources ks
        JOIN knowledge_documents kd ON kd.source_id = ks.source_id
        WHERE kd.document_id = (
            SELECT metadata->>'document_id' FROM knowledge_chunks WHERE id = %s
        )
    """, (chunk_id,))
```

---

## 五、邻接 Chunk 召回

防止检索到的片段丢失上下文：

```python
async def _fetch_adjacent_chunks(self, results, _top_k):
    for r in results[:3]:
        meta = r.get("metadata", {})
        prev_id = meta.get("previous_chunk_id", "")
        next_id = meta.get("next_chunk_id", "")
        if prev_id and prev_id not in seen:
            to_fetch.add(prev_id)
        if next_id and next_id not in seen:
            to_fetch.add(next_id)

    # 标记为邻接补充，非直接召回
    for chunk_id in to_fetch:
        results.append({..., "score": 0.3, "_adjacent": True})
```

---

## 六、两种输出格式

### 6.1 Markdown (注入 Prompt)

```python
async def query_formatted(self, query_text, top_k=3):
    results = await self.query(query_text, top_k)
    # 格式化为:
    # ## 🔴 知识库参考
    # ### 知识点 1 — 来源: xxx (url)
    # content...
    # **规则: 基于以上内容回答。不要编造知识库中不存在的信息。**
```

### 6.2 结构化 JSON (工具返回)

```python
async def query_structured(self, query_text, top_k=3):
    # 返回:
    {
      "hit": true,
      "query": "...",
      "results": [
        {
          "rank": 1,
          "source_title": "...",
          "source_url": "...",
          "content_snippet": "...",
          "score": 0.85,
          "rerank_score": 0.92,
          "chunk_id": "...",
        }
      ],
      "total_scanned": 20
    }
```

---

## 七、在 Agent 中的两种使用方式

| 方式 | 调用位置 | 格式 | 用途 |
|------|---------|------|------|
| **被动注入** | planner_node / execute_node 的 System Prompt | Markdown | 提供知识背景 |
| **主动检索** | ReAct Agent 的 search_knowledge_base tool | 结构化 JSON | 精确引用 + 幻觉检测 |

> 被动注入保证 Agent 始终有知识背景；主动检索让 Agent 在需要时查证细节。

---

## 八、关键要点

1. **Dense + Sparse 互补**: 语义相似 + 关键词精确匹配
2. **RRF 融合**: 不偏袒任何一种检索方式
3. **Rerank 精排**: qwen3-rerank 显著提升 top_k 精度
4. **邻接 Chunk**: 防止上下文割裂
5. **来源可追溯**: 每个 Chunk 都能追溯到 Source → Document
6. **两种输出格式**: Markdown 注入 vs JSON 工具返回，各司其职

---

## 九、继续学习

→ [12-记忆系统](12-记忆系统.md) — L2 会话摘要 + L3 用户画像
