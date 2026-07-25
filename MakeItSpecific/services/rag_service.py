"""
RAG 领域知识库服务 V5 — 来源感知的语义分块 + 多模态检索。

V5 新特性:
  1. 来源元数据提取 → 复制到每个子 Chunk（source_title/source_url/repository/author/accessed_at/version_or_commit）
  2. Chunk Identity Chain: document_id/chunk_id/parent_id/prev_id/next_id/chunk_index/source_refs
  3. 多来源文档自动拆分 → 各自独立语义分割
  4. 稠密检索: "source_title + entity_names + section_title + body" 组合文本
  5. 稀疏检索: 单独索引 repository/URL/author/专有名称
  6. 知识图谱: Source→Document→Chunk→Claim 证据链
"""

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional

from services.vector_store import PGVectorStore
from services.document_processor import (
    SourceParser,
    SourceSplitter,
    SemanticChunker,
    ChunkBuilder,
    KnowledgeGraphBuilder,
    SourceMetadata,
)

logger = logging.getLogger(__name__)

CHUNK_COLLECTION = "knowledge_chunks"  # 新 collection（来源感知）
LEGACY_COLLECTION = "domain_knowledge"  # 旧 collection（向后兼容）


class RAGService:
    """领域知识检索服务 V5 — PGVector + 来源感知 Chunking + 知识图谱。"""

    SIMILARITY_THRESHOLD = 0.6

    def __init__(
        self,
        vector_store: PGVectorStore,
        knowledge_base_dir: Path,
        api_key: str = "",
        chunk_min: int = 200,
        chunk_max: int = 800,
        similarity_threshold: float = 0.6,
        rerank_enabled: bool = True,
        rerank_model: str = "qwen3-rerank",
        rerank_top_k: int = 5,
        rerank_coarse_k: int = 20,
    ):
        self.store = vector_store
        self.kb_dir = knowledge_base_dir
        self.chunk_min = chunk_min
        self.chunk_max = chunk_max
        self.similarity_threshold = similarity_threshold
        self.rerank_enabled = rerank_enabled
        self.rerank_model = rerank_model
        self.rerank_top_k = rerank_top_k
        self.rerank_coarse_k = rerank_coarse_k
        self._api_key = api_key
        self._embedding_model = None
        self._chunker = None

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            if not self._api_key:
                raise ValueError("DASHSCOPE_API_KEY 未设置，无法生成 embedding")
            from langchain_community.embeddings import DashScopeEmbeddings
            self._embedding_model = DashScopeEmbeddings(
                model="text-embedding-v4", dashscope_api_key=self._api_key,
            )
        return self._embedding_model

    @property
    def chunker(self):
        if self._chunker is None:
            self._chunker = SemanticChunker(
                embedding_fn=self.embedding_model.embed_documents,
                threshold=0.5, min_chars=self.chunk_min, max_chars=self.chunk_max,
            )
        return self._chunker

    # ============================================================
    # 初始化
    # ============================================================

    async def ensure_ready(self):
        await self.store.ensure_tables()

    # ============================================================
    # 知识库索引 V5 — 来源感知
    # ============================================================

    async def ingest_knowledge_base(self) -> dict:
        """
        扫描 knowledge_base_dir，来源感知索引。

        流程:
          1. SourceParser 提取 frontmatter 元数据
          2. SourceSplitter 多来源文档拆分
          3. SemanticChunker 对正文语义分割
          4. ChunkBuilder 装配 Chunk（复制元数据 + identity chain）
          5. KnowledgeGraphBuilder 建立 KG 边
          6. 写入 knowledge_chunks (PGVector) + KG 表 (PostgreSQL)

        Returns:
            {new_chunks, new_sources, new_documents}
        """
        md_files = list(self.kb_dir.rglob("*.md"))
        if not md_files:
            logger.info("[RAG] knowledge_base/ 为空")
            return {"chunks": 0, "sources": 0, "documents": 0}

        stats = {"chunks": 0, "sources": 0, "documents": 0}

        for md_file in md_files:
            try:
                file_stats = await self._ingest_one_file(md_file)
                stats["chunks"] += file_stats["chunks"]
                stats["sources"] += file_stats["sources"]
                stats["documents"] += file_stats["documents"]
            except Exception as e:
                logger.error(f"[RAG] 索引失败 {md_file.name}: {e}")

        logger.info(
            f"[RAG] 索引完成: {stats['chunks']} chunks, "
            f"{stats['sources']} sources, {stats['documents']} documents"
        )
        return stats

    async def _ingest_one_file(self, file_path: Path) -> dict:
        """索引单个文件。"""
        # Step 1: 解析来源元数据
        source_meta, source_refs, body = SourceParser.parse(file_path)

        # Step 2: 按来源拆分
        documents = SourceSplitter.split(file_path, source_meta, source_refs, body)

        stats = {"chunks": 0, "sources": 0, "documents": len(documents)}

        for doc in documents:
            doc_id = doc["document_id"]

            # Step 3: 对正文做语义分割
            raw_chunks = self.chunker.chunk(doc["body_text"])
            if not raw_chunks:
                continue

            # Step 4: ChunkBuilder 装配 Chunk
            built_chunks = ChunkBuilder.build(doc, raw_chunks)

            # Step 5: 知识图谱边
            kg = KnowledgeGraphBuilder.build_edges(doc, built_chunks)

            # Step 6: 写入
            # 6a - KG Source node
            source_id = kg["source_node"]["source_id"]
            await self._upsert_source(kg["source_node"])
            stats["sources"] += 1

            # 6b - KG Document node
            await self._upsert_document(kg["document_node"])

            # 6c - Chunks → PGVector
            new_chunk_ids = []
            new_docs_for_embedding = []
            new_metadatas = []
            new_ids = []

            for c in built_chunks:
                # 去重
                exists = await self.store.exists_by_metadata(
                    CHUNK_COLLECTION, {"content_hash": c["content_hash"]}
                )
                if exists:
                    continue

                new_ids.append(c["chunk_id"])
                # 稠密检索文本用于 embedding
                new_docs_for_embedding.append(c["search_text_dense"])
                new_metadatas.append({
                    "document_id": c["document_id"],
                    "parent_id": c["parent_id"],
                    "chunk_index": c["chunk_index"],
                    "previous_chunk_id": c["previous_chunk_id"],
                    "next_chunk_id": c["next_chunk_id"],
                    "source_refs": json.dumps(c["source_refs"], ensure_ascii=False),
                    "source_metadata": json.dumps(c["source_metadata"], ensure_ascii=False),
                    "source_id": source_id,
                    "section_title": c["section_title"],
                    "entity_names": json.dumps(c["entity_names"], ensure_ascii=False),
                    "search_text_sparse": c["search_text_sparse"],
                    "content_hash": c["content_hash"],
                    "chunk_type": c["source_metadata"].get("source_type", "document"),
                })
                new_chunk_ids.append(c["chunk_id"])

            if new_ids:
                embeddings = self.embedding_model.embed_documents(new_docs_for_embedding)
                # 存储 body_text 为 document 字段（PGVector 主字段），search_text_dense 用于生成 embedding
                # 实际正文内容存于 metadata.body_text
                await self.store.add(
                    collection=CHUNK_COLLECTION,
                    documents=new_docs_for_embedding,  # search_text_dense 作为主文本
                    embeddings=embeddings,
                    metadatas=new_metadatas,
                    ids=new_ids,
                )
                stats["chunks"] += len(new_ids)

                # 6d - KG Chunk edges
                for c in built_chunks:
                    if c["chunk_id"] in new_chunk_ids:
                        self._save_chunk_edge(c["chunk_id"], source_id, doc_id, c)

        return stats

    async def _upsert_source(self, node: dict):
        """INSERT OR UPDATE knowledge_sources。"""
        cur = self.store.conn.cursor()
        try:
            cur.execute("""
                INSERT INTO knowledge_sources (source_id, source_title, source_url, source_type,
                                               repository, author, accessed_at, version_or_commit)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (source_id) DO UPDATE SET
                    source_title=EXCLUDED.source_title, source_url=EXCLUDED.source_url,
                    accessed_at=EXCLUDED.accessed_at
            """, (
                node["source_id"], node["source_title"], node["source_url"], node["source_type"],
                node["repository"], node["author"], node["accessed_at"], node["version_or_commit"],
            ))
            self.store.conn.commit()
        except Exception:
            self.store.conn.rollback()
            raise
        finally:
            cur.close()

    async def _upsert_document(self, node: dict):
        cur = self.store.conn.cursor()
        try:
            cur.execute("""
                INSERT INTO knowledge_documents (document_id, source_id, source_title, chunk_count)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (document_id) DO UPDATE SET chunk_count=EXCLUDED.chunk_count
            """, (node["document_id"], node["source_id"], node["source_title"], node["chunk_count"]))
            self.store.conn.commit()
        except Exception:
            self.store.conn.rollback()
            raise
        finally:
            cur.close()

    def _save_chunk_edge(self, chunk_id: str, source_id: str, document_id: str, chunk: dict):
        """记录 Chunk → Source/Document KG 边（存于 metadata，无需单独表）。"""
        pass  # metadata 中已包含 source_id + document_id，KG 关系由 JOIN 查询恢复

    # ============================================================
    # 检索 V5 — 稠密 + 稀疏 + 知识图谱
    # ============================================================

    async def query(
        self, query_text: str, top_k: int = 3, min_score: float = None
    ) -> list[dict]:
        """
        多模态检索。

        Pipeline:
          1. Dense (PGVector): 对 search_text_dense embedding 做向量检索
          2. Sparse (BM25 tsvector): 对 search_text_sparse 字段独立做全文检索
          3. RRF 融合
          4. Rerank 精排 (qwen3-rerank)
          5. 相似度/关键词过滤
          6. 召回邻接 Chunk: 通过 previous_chunk_id/next_chunk_id 补全上下文
          7. 恢复来源元数据

        Returns:
            [{id, document, metadata, score, source_metadata, identity, ...}, ...]
        """
        if min_score is None:
            min_score = self.similarity_threshold

        query_emb = None

        try:
            query_emb = self.embedding_model.embed_query(query_text)

            # ── 1. Dense 检索 ──
            dense_results = await self.store.search(
                collection=CHUNK_COLLECTION,
                query_embedding=query_emb,
                top_k=self.rerank_coarse_k,
            )

            # ── 2. 稀疏检索 (BM25 on search_text_sparse) ──
            sparse_results = await self._sparse_search(query_text, top_k=self.rerank_coarse_k)

            # ── 3. RRF 融合 ──
            merged = self._rrf_fusion([dense_results, sparse_results], k=60)
            merged = merged[:self.rerank_coarse_k]

            # ── 4. Rerank ──
            if self.rerank_enabled and len(merged) > top_k:
                documents = [r["document"] for r in merged]
                reranked = await self._rerank(query_text, documents, top_n=self.rerank_top_k)
                if reranked:
                    final = []
                    for rr in reranked:
                        idx = rr.get("index", 0)
                        if idx < len(merged):
                            final.append({**merged[idx], "rerank_score": rr.get("relevance_score", 0)})
                    merged = final

            # ── 5. 相似度过滤 ──
            results = [
                r for r in merged
                if (r.get("score", 0) >= min_score or r.get("rerank_score", 0) >= 0.3)
            ]
            results = results[:top_k]

            # ── 6. 关键词加权 ──
            results = self._apply_keyword_boost(query_text, results)

            # ── 7. 召回邻接 Chunk ──
            results = await self._fetch_adjacent_chunks(results, top_k)

            # ── 8. 恢复来源引用（从 metadata 解包）──
            for r in results:
                meta = r.get("metadata", {})
                if isinstance(meta.get("source_metadata"), str):
                    try:
                        r["source_metadata"] = json.loads(meta["source_metadata"])
                    except (json.JSONDecodeError, TypeError):
                        r["source_metadata"] = {}
                if isinstance(meta.get("source_refs"), str):
                    try:
                        r["source_refs"] = json.loads(meta["source_refs"])
                    except (json.JSONDecodeError, TypeError):
                        r["source_refs"] = []
                r["identity"] = {
                    "chunk_id": r.get("id", ""),
                    "document_id": meta.get("document_id", ""),
                    "parent_id": meta.get("parent_id", ""),
                    "chunk_index": meta.get("chunk_index", 0),
                    "previous_chunk_id": meta.get("previous_chunk_id", ""),
                    "next_chunk_id": meta.get("next_chunk_id", ""),
                }

            return results

        except Exception as e:
            logger.error(f"[RAG] 检索失败: {e}", exc_info=True)
            if query_emb is not None:
                try:
                    return await self.store.search(
                        collection=CHUNK_COLLECTION, query_embedding=query_emb, top_k=top_k,
                    )
                except Exception:
                    pass
            return []

    async def _sparse_search(self, query: str, top_k: int = 10) -> list[dict]:
        """稀疏检索 — 对 search_text_sparse 字段做 BM25 全文检索。

        独立索引: repository + URL + author + 专有名称。
        不走 PG tsvector（索引的是 metadata 中的 search_text_sparse 字段）。
        """
        # 提取实体名做精确匹配
        entities = self._extract_tech_terms(query)

        # 先尝试 metadata->>search_text_sparse 的 GIN 索引（如果已建）
        cur = self.store.conn.cursor()
        try:
            # 构建 tsquery
            search_terms = query + " " + " ".join(entities)
            escaped = re.sub(r'[^\w\s]', ' ', search_terms.lower())
            terms = [t for t in escaped.split() if len(t) >= 2]
            if not terms:
                cur.close()
                return []

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

            rows = cur.fetchall()
            results = []
            for row in rows:
                meta = row[2] if isinstance(row[2], dict) else json.loads(row[2] or "{}")
                results.append({"id": row[0], "document": row[1], "metadata": meta, "score": float(row[3])})
            cur.close()
            return results
        except Exception as e:
            logger.warning(f"[RAG] 稀疏检索失败: {e}")
            if cur and not cur.closed:
                cur.close()
            return []

    async def _fetch_adjacent_chunks(self, results: list[dict], _top_k: int) -> list[dict]:
        """召回邻接 Chunk — 通过 previous_chunk_id / next_chunk_id 补充上下文。"""
        seen = set(r.get("id", "") for r in results)
        to_fetch = set()

        for r in results[:3]:
            meta = r.get("metadata", {})
            prev_id = meta.get("previous_chunk_id", "")
            next_id = meta.get("next_chunk_id", "")
            if prev_id and prev_id not in seen:
                to_fetch.add(prev_id)
            if next_id and next_id not in seen:
                to_fetch.add(next_id)

        if not to_fetch:
            return results

        for chunk_id in list(to_fetch)[:5]:
            try:
                fetched = await self.store.get_by_id(CHUNK_COLLECTION, chunk_id)
                if fetched:
                    results.append({
                        "id": fetched["id"],
                        "document": fetched["document"],
                        "metadata": fetched["metadata"],
                        "score": 0.3,  # 标记为邻接补充，非直接召回
                        "_adjacent": True,
                    })
            except Exception:
                pass

        return results

    # ============================================================
    # 格式化输出
    # ============================================================

    async def query_formatted(self, query_text: str, top_k: int = 3) -> str:
        results = await self.query(query_text, top_k)
        if not results:
            # 降级: 尝试旧 collection
            results = await self._legacy_query(query_text, top_k)
        if not results:
            return "（未找到相关知识。以下回答基于通用知识，可能不准确。）"

        lines = ["## 🔴 知识库参考", "", "以下信息必须作为回答的基础:", ""]
        for i, r in enumerate(results, 1):
            src = r.get("source_metadata", {}).get("source_title", r.get("metadata", {}).get("source_file", "未知"))
            url = r.get("source_metadata", {}).get("source_url", "")
            source_line = f"**来源**: {src}"
            if url:
                source_line += f" ({url})"
            if r.get("_adjacent"):
                source_line += " [邻接上下文]"

            lines.append(f"### 知识点 {i} — {source_line}")
            # 显示 search_text_dense 中实际的 body 部分（去掉前缀）
            doc = r.get("document", "")
            lines.append(doc)
            lines.append("")

        lines.append("**规则: 基于以上内容回答。如知识库未覆盖请明确说明。不要编造知识库中不存在的信息。**")
        return "\n".join(lines)

    async def query_structured(self, query_text: str, top_k: int = 3) -> dict:
        raw = await self.query(query_text, top_k)
        results = []
        for i, r in enumerate(raw, 1):
            src = r.get("source_metadata", {})
            results.append({
                "rank": i,
                "source_title": src.get("source_title", r.get("metadata", {}).get("source_file", "未知")),
                "source_url": src.get("source_url", ""),
                "repository": src.get("repository", ""),
                "author": src.get("author", ""),
                "content_snippet": r.get("document", "")[:400],
                "score": round(r.get("score", 0), 3),
                "rerank_score": round(r.get("rerank_score", 0), 3) if "rerank_score" in r else None,
                "chunk_id": r.get("identity", {}).get("chunk_id", ""),
                "adjacent": bool(r.get("_adjacent")),
            })
        return {
            "hit": len(results) > 0,
            "query": query_text,
            "results": results,
            "total_scanned": self.rerank_coarse_k,
        }

    # ============================================================
    # 降级: 旧 collection
    # ============================================================

    async def _legacy_query(self, query_text: str, top_k: int = 3) -> list[dict]:
        try:
            query_emb = self.embedding_model.embed_query(query_text)
            return await self.store.search(
                collection=LEGACY_COLLECTION, query_embedding=query_emb, top_k=top_k,
            )
        except Exception:
            return []

    # ============================================================
    # 知识图谱: Source → Document → Chunk → Claim
    # ============================================================

    async def kg_lookup(self, chunk_id: str) -> dict:
        """从 Chunk ID 沿知识图谱查找 Source → Document 链。"""
        cur = self.store.conn.cursor()
        cur.execute("""
            SELECT ks.source_id, ks.source_title, ks.source_url, ks.source_type,
                   ks.repository, ks.author, ks.accessed_at,
                   kd.document_id, kd.chunk_count
            FROM knowledge_sources ks
            JOIN knowledge_documents kd ON kd.source_id = ks.source_id
            WHERE kd.document_id = (
                SELECT metadata->>'document_id'
                FROM knowledge_chunks
                WHERE id = %s
            )
            LIMIT 1
        """, (chunk_id,))
        row = cur.fetchone()
        cur.close()
        if row:
            return {
                "source_id": row[0], "source_title": row[1], "source_url": row[2],
                "source_type": row[3], "repository": row[4], "author": row[5],
                "accessed_at": row[6], "document_id": row[7], "chunk_count": row[8],
            }
        return {}

    async def save_claim(self, chunk_id: str, document_id: str, source_id: str,
                         claim_text: str, confidence: float = 0.5):
        """保存 Claim 到知识图谱。"""
        claim_id = f"cl_{hashlib.md5(claim_text.encode()).hexdigest()[:12]}"
        cur = self.store.conn.cursor()
        cur.execute("""
            INSERT INTO knowledge_claims (claim_id, chunk_id, document_id, source_id, claim_text, confidence)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (claim_id) DO NOTHING
        """, (claim_id, chunk_id, document_id, source_id, claim_text, confidence))
        self.store.conn.commit()
        cur.close()

    async def get_claims_for_source(self, source_id: str) -> list[dict]:
        """获取某个来源下的所有 Claims。"""
        cur = self.store.conn.cursor()
        cur.execute(
            "SELECT claim_id, chunk_id, claim_text, confidence FROM knowledge_claims WHERE source_id=%s",
            (source_id,),
        )
        rows = cur.fetchall()
        cur.close()
        return [{"claim_id": r[0], "chunk_id": r[1], "claim_text": r[2], "confidence": r[3]} for r in rows]

    # ============================================================
    # Query 增强 (保持向后兼容)
    # ============================================================

    def build_context_query(self, message, l3_facts="", expressed_dimensions=None, l2_summary="") -> str:
        if len(message) >= 80:
            return message
        if len(message) >= 30:
            if l3_facts:
                from core.context_engine import _filter_facts_by_query
                relevant = _filter_facts_by_query(l3_facts, message)
                if relevant:
                    return f"{message} {relevant}"[:500]
            return message
        parts = [message]
        if l3_facts:
            parts.append(l3_facts[:200])
        if expressed_dimensions:
            dims = [str(v) for k, v in expressed_dimensions.items()
                    if not k.endswith("_confidence") and v and str(v) != "null"]
            if dims:
                parts.append(" ".join(dims)[:150])
        if l2_summary:
            parts.append(l2_summary[:150])
        return " ".join(parts)[:500]

    # ============================================================
    # Stats
    # ============================================================

    async def get_kb_stats(self) -> dict:
        chunk_count = await self.store.count(CHUNK_COLLECTION)
        legacy_count = await self.store.count(LEGACY_COLLECTION)
        md_files = list(self.kb_dir.glob("*.md")) + list(self.kb_dir.glob("**/*.md"))
        # Count KG nodes
        cur = self.store.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM knowledge_sources")
        sources = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM knowledge_documents")
        docs = cur.fetchone()[0]
        cur.close()
        return {
            "chunk_count": chunk_count,
            "legacy_count": legacy_count,
            "source_files": len(md_files),
            "file_names": [f.name for f in md_files],
            "sources": sources,
            "documents": docs,
        }

    # ============================================================
    # 复用: Rerank + RRF + KeywordBoost (从 V4 继承)
    # ============================================================

    async def _rerank(self, query: str, documents: list[str], top_n: int = 5) -> list[dict]:
        import aiohttp
        url = "https://dashscope.aliyuncs.com/compatible-api/v1/reranks"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        payload = {"model": self.rerank_model, "query": query, "documents": documents,
                   "top_n": top_n, "return_documents": True}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload,
                                        timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    return data.get("results", [])
        except Exception:
            return []

    @staticmethod
    def _rrf_fusion(results_lists: list[list[dict]], k: int = 60) -> list[dict]:
        fused = {}; doc_map = {}
        for results in results_lists:
            for rank, doc in enumerate(results, start=1):
                did = doc.get("id", "")
                if not did: continue
                fused[did] = fused.get(did, 0) + 1.0 / (k + rank)
                if did not in doc_map:
                    doc_map[did] = dict(doc)
                    doc_map[did]["rrf_score"] = 0.0
                doc_map[did]["rrf_score"] = fused[did]
        return [doc_map[i] for i in sorted(fused, key=lambda x: fused[x], reverse=True)]

    @staticmethod
    def _apply_keyword_boost(query: str, results: list[dict], boost_factor: float = 0.05) -> list[dict]:
        tech_terms = RAGService._extract_tech_terms(query)
        if not tech_terms:
            return results
        boosted = []
        for r in results:
            r = dict(r)
            doc_lower = r.get("document", "").lower()
            overlap = sum(1 for t in tech_terms if t.lower() in doc_lower) / max(len(tech_terms), 1)
            if overlap >= 0.3:
                for key in ("rerank_score", "score"):
                    if key in r:
                        r[key] = min(1.0, r[key] + overlap * boost_factor)
            boosted.append(r)
        def key(r): return max(r.get("rerank_score", 0), r.get("score", 0))
        boosted.sort(key=key, reverse=True)
        return boosted

    @staticmethod
    def _extract_tech_terms(query: str) -> list[str]:
        patterns = [
            r'\b[A-Z][a-z]+(?:\s?[A-Z][a-z]+)*\b',
            r'\b[a-z]+(?:-[a-z]+)+\b',
            r'\b[A-Z]{2,}\b',
            r'\b[a-z]+(?:\.[a-z]+)+\b',
        ]
        terms = set()
        for p in patterns:
            terms.update(f for f in re.findall(p, query) if len(f) >= 2)
        return list(terms)
