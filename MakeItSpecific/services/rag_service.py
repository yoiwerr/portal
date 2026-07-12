"""
RAG 领域知识库服务 — 基于 PostgreSQL + PGVector。

知识来源: knowledge_base/ 目录下的 .md 文件（用户手动维护）
向量引擎: DashScope text-embedding-v4 (1024维)，与 ChatLab 一致
Rerank:    百炼 qwen3-rerank (复用 DASHSCOPE_API_KEY)
分块策略:  语义分块 (SemanticChunker) — 相邻句子 embedding 相似度断崖切分

ChromaDB → PGVector 迁移:
  旧: chromadb.PersistentClient + DashScopeEmbeddingFunction
  新: services.vector_store.PGVectStore + 手动 embedding 调用
"""

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional

import numpy as np
from langchain_community.embeddings import DashScopeEmbeddings

from services.vector_store import PGVectorStore

logger = logging.getLogger(__name__)


# ============================================================
# 语义分块器
# ============================================================

class SemanticChunker:
    """语义分块器 — 用相邻句子 embedding 相似度找自然断点。

    设计思路:
      当话题切换时，相邻句子的 embedding 相似度会骤降（语义断崖），
      那里就是自然的分块边界。避免了固定大小分块在段落中间切断的问题。

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

    def chunk(self, text: str) -> list[str]:
        """
        1. 按 ## 标题粗分（保留文档结构）
        2. 每段拆句子，算相邻句子 embedding 相似度
        3. 在「语义断崖」处切分
        4. 控制 min/max 字符边界
        """
        sections = self._split_by_headers(text)

        all_chunks = []
        for section in sections:
            if len(section) <= self.min_chars:
                if section.strip():
                    all_chunks.append(section.strip())
                continue

            sentences = self._split_sentences(section)
            if len(sentences) <= 1:
                all_chunks.append(section.strip())
                continue

            # 批量生成 sentence embeddings
            try:
                embeddings = self.embed(sentences)
            except Exception as e:
                logger.warning(f"[SemanticChunker] embedding 失败，降级为固定大小分块: {e}")
                all_chunks.extend(self._fallback_chunk(section))
                continue

            # 找断点
            breakpoints = self._find_breakpoints(sentences, embeddings)

            # 在断点处切分
            chunks = self._split_at_breakpoints(sentences, breakpoints)
            all_chunks.extend(chunks)

        return all_chunks

    def _split_by_headers(self, text: str) -> list[str]:
        """按 ## 标题粗分 — 保留文档的逻辑结构。"""
        parts = re.split(r"\n(?=## )", text)
        return [p.strip() for p in parts if p.strip()]

    def _split_sentences(self, text: str) -> list[str]:
        """中英文句子切分。"""
        raw = re.split(r"(?<=[。！？.!?\n])\s*", text)
        return [s.strip() for s in raw if s.strip() and len(s.strip()) >= 5]

    def _find_breakpoints(
        self, sentences: list[str], embeddings: list[list[float]]
    ) -> list[int]:
        """找到语义断崖位置 — 相邻句子相似度低于阈值的点。"""
        breakpoints = []
        for i in range(len(sentences) - 1):
            sim = self._cosine_similarity(embeddings[i], embeddings[i + 1])
            if sim < self.threshold:
                breakpoints.append(i + 1)
        return breakpoints

    def _split_at_breakpoints(
        self, sentences: list[str], breakpoints: list[int]
    ) -> list[str]:
        """在断点处切分，同时遵守 min/max 字符约束。"""
        chunks = []
        start = 0

        for bp in breakpoints + [len(sentences)]:
            segment = sentences[start:bp]
            segment_text = " ".join(segment)

            # 太小 → 不在这里切，留到下一个断点合并
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

    def _force_split(self, sentences: list[str], max_chars: int) -> list[str]:
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

    def _fallback_chunk(self, text: str) -> list[str]:
        """降级方案: 固定大小分块。"""
        sentences = self._split_sentences(text)
        return self._force_split(sentences, self.max_chars)

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Cosine similarity between two vectors."""
        a_arr, b_arr = np.array(a), np.array(b)
        denom = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
        if denom == 0:
            return 0.0
        return float(np.dot(a_arr, b_arr) / denom)


# ============================================================
# RAG 服务
# ============================================================

class RAGService:
    """领域知识检索服务 — PGVector 后端。

    Collection: domain_knowledge
    分块策略: 语义分块 (SemanticChunker)
    Embedding: DashScope text-embedding-v4 (1024 维)
    Rerank:    百炼 qwen3-rerank
    """

    COLLECTION = "domain_knowledge"
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

        # Rerank 配置
        self.rerank_enabled = rerank_enabled
        self.rerank_model = rerank_model
        self.rerank_top_k = rerank_top_k
        self.rerank_coarse_k = rerank_coarse_k

        self._api_key = api_key
        self._embedding_model: Optional[DashScopeEmbeddings] = None
        self._chunker: Optional[SemanticChunker] = None

    @property
    def embedding_model(self) -> DashScopeEmbeddings:
        if self._embedding_model is None:
            if not self._api_key:
                raise ValueError("DASHSCOPE_API_KEY 未设置，无法生成 embedding")
            self._embedding_model = DashScopeEmbeddings(
                model="text-embedding-v4",
                dashscope_api_key=self._api_key,
            )
        return self._embedding_model

    @property
    def chunker(self) -> SemanticChunker:
        if self._chunker is None:
            self._chunker = SemanticChunker(
                embedding_fn=self.embedding_model.embed_documents,
                threshold=0.5,
                min_chars=self.chunk_min,
                max_chars=self.chunk_max,
            )
        return self._chunker

    # ============================================================
    # 初始化
    # ============================================================

    async def ensure_ready(self):
        """确保 PGVector 表已创建。"""
        await self.store.ensure_tables()

    # ============================================================
    # 知识库索引
    # ============================================================

    async def ingest_knowledge_base(self) -> int:
        """
        扫描 knowledge_base_dir 目录，语义分块后索引到 PGVector。

        分块策略: SemanticChunker — 在相邻句子 embedding 相似度断崖处切分。
        去重: 按 MD5(chunk) 检查是否已存在。

        Returns:
            本次新索引的 chunk 数量
        """
        md_files = list(self.kb_dir.glob("*.md"))
        if not md_files:
            logger.info("[RAG] knowledge_base/ 目录为空，跳过索引")
            return 0

        new_documents = []
        new_metadatas = []
        new_ids = []

        for md_file in md_files:
            content = md_file.read_text(encoding="utf-8")
            chunks = self.chunker.chunk(content)

            for i, chunk in enumerate(chunks):
                chunk_id = self._make_chunk_id(str(md_file), i)
                content_hash = hashlib.md5(chunk.encode()).hexdigest()

                # 检查是否已存在（直接查 JSONB，不跑向量检索）
                exists = await self.store.exists_by_metadata(
                    self.COLLECTION,
                    {"content_hash": content_hash},
                )
                if exists:
                    continue

                keywords = self._extract_keywords(chunk)

                new_ids.append(chunk_id)
                new_documents.append(chunk)
                new_metadatas.append({
                    "source_file": md_file.name,
                    "source_path": str(md_file),
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "content_hash": content_hash,
                    "keywords": keywords,
                })

        if new_documents:
            logger.info(f"[RAG] 生成 {len(new_documents)} 个 embedding...")
            embeddings = self.embedding_model.embed_documents(new_documents)

            await self.store.add(
                collection=self.COLLECTION,
                documents=new_documents,
                embeddings=embeddings,
                metadatas=new_metadatas,
                ids=new_ids,
            )
            logger.info(f"[RAG] 已索引 {len(new_ids)} 个新片段")

        return len(new_ids)

    async def reindex_all(self) -> int:
        """清除并重建整个 domain_knowledge 索引。"""
        await self.store.clear(self.COLLECTION)
        logger.info("[RAG] domain_knowledge 已清空，重新索引...")
        return await self.ingest_knowledge_base()

    async def get_kb_stats(self) -> dict:
        """获取知识库统计信息。"""
        count = await self.store.count(self.COLLECTION)
        md_files = list(self.kb_dir.glob("*.md"))
        return {
            "chunk_count": count,
            "source_files": len(md_files),
            "file_names": [f.name for f in md_files],
        }

    # ============================================================
    # 检索
    # ============================================================

    async def query(
        self,
        query_text: str,
        top_k: int = 3,
        min_score: float = None,
    ) -> list[dict]:
        """
        混合检索 + Rerank + 相似度过滤。

        Pipeline:
          1. Dense 检索 (PGVector)  → coarse_k 候选
          2. BM25 检索 (PG tsvector) → coarse_k 候选
          3. RRF 合并 → top-(coarse_k)
          4. Rerank (qwen3-rerank)  → top-k
          5. 相似度阈值过滤

        Args:
            query_text: 查询文本
            top_k: 最终返回数
            min_score: 相似度阈值（默认 0.6）

        Returns:
            [{id, document, metadata, score}, ...]
        """
        if min_score is None:
            min_score = self.similarity_threshold

        query_emb = None  # 提前声明，防止 except 中 UnboundLocalError

        try:
            query_emb = self.embedding_model.embed_query(query_text)

            # ── 1. Dense 检索 ──
            dense_results = await self.store.search(
                collection=self.COLLECTION,
                query_embedding=query_emb,
                top_k=self.rerank_coarse_k,
            )

            # ── 2. BM25 检索 ──
            bm25_results = await self.store.bm25_search(
                collection=self.COLLECTION,
                query=query_text,
                top_k=self.rerank_coarse_k,
            )

            # ── 3. RRF 合并 ──
            merged = self._rrf_fusion([dense_results, bm25_results], k=60)
            merged = merged[:self.rerank_coarse_k]

            # ── 4. Rerank ──
            if self.rerank_enabled and len(merged) > top_k:
                documents = [r["document"] for r in merged]
                reranked = await self._rerank(query_text, documents, top_n=self.rerank_top_k)
                if reranked:
                    # 将 rerank 结果映射回原始 metadata
                    final = []
                    for rr in reranked:
                        idx = rr.get("index", 0)
                        if idx < len(merged):
                            final.append({**merged[idx], "rerank_score": rr.get("relevance_score", 0)})
                    merged = final

            # ── 5. 相似度 + 关键词过滤 ──
            results = [
                r for r in merged
                if (r.get("score", 0) >= min_score or r.get("rerank_score", 0) >= 0.3)
            ]
            results = results[:top_k]

            # ── 6. 关键词重叠加权 — 对最终结果做微调 ──
            return self._apply_keyword_boost(query_text, results)

        except Exception as e:
            logger.error(f"[RAG] 检索失败: {e}", exc_info=True)
            # 降级: 只用 Dense 检索（前提是 embedding 已生成）
            if query_emb is not None:
                try:
                    results = await self.store.search(
                        collection=self.COLLECTION,
                        query_embedding=query_emb,
                        top_k=top_k,
                    )
                    return results
                except Exception:
                    pass
            return []

    async def query_formatted(self, query_text: str, top_k: int = 3) -> str:
        """检索并格式化为上下文文本，可直接注入 LLM prompt。"""
        results = await self.query(query_text, top_k)
        if not results:
            return "（未找到相关知识。以下回答基于通用知识，可能不准确。）"

        lines = [
            "## 🔴 知识库参考",
            "",
            "以下信息必须作为回答的基础:",
            "",
        ]
        for i, r in enumerate(results, 1):
            source = r.get("metadata", {}).get("source_file", "未知来源")
            lines.append(f"### 知识点 {i} (来源: {source})")
            lines.append(r["document"])
            lines.append("")

        lines.append("**规则: 基于以上内容回答。如知识库未覆盖请明确说明。不要编造知识库中不存在的信息。**")
        return "\n".join(lines)

    # ============================================================
    # Query 增强 — 上下文驱动（不扩写，只组合真实信息）
    # ============================================================

    def build_context_query(
        self,
        message: str,
        l3_facts: str = "",
        expressed_dimensions: dict = None,
        l2_summary: str = "",
    ) -> str:
        """
        上下文驱动的 Query 构建。

        原则:
          1. 只组合用户真实提供的信息，不生成虚假信息
          2. 长 query (>80 字符) 不增强 — 保护原始语义
          3. 信号按相关性加权，不相关的上下文不添加噪音
          4. 上下文不够 → 返回原始 query，让上游 clarify

        Args:
            message: 用户原始消息
            l3_facts: L3 语义事实（从历史提取的偏好/决策/约束）
            expressed_dimensions: 已确认的需求维度
            l2_summary: L2 滚动摘要（长对话脉络）

        Returns:
            增强后的 query 文本 (≤500 字符)
        """
        # ── 长 query: 不加任何上下文 ──
        if len(message) >= 80:
            return message

        # ── 中 query (30-80): 只加 L3 相关事实 ──
        if len(message) >= 30:
            if l3_facts:
                from core.context_engine import _filter_facts_by_query
                relevant = _filter_facts_by_query(l3_facts, message)
                if relevant:
                    return f"{message} {relevant}"[:500]
            return message

        # ── 短 query (<30): 多源信号组合 ──
        parts = [message]
        signals_added = 0

        # L3 语义事实 — 用户明确说过的偏好/决策 (权重最高)
        if l3_facts:
            l3_text = l3_facts.replace(
                "以下是从此前对话中召回的语义事实：\n", ""
            ).replace("- ", "")
            if l3_text.strip():
                parts.append(l3_text[:200])
                signals_added += 1

        # expressed_dimensions — 已确认的需求维度
        if expressed_dimensions:
            dim_parts = []
            for key, val in expressed_dimensions.items():
                if key.endswith("_confidence"):
                    continue
                if val and str(val) != "null" and len(str(val)) > 1:
                    dim_parts.append(str(val))
            if dim_parts:
                parts.append(" ".join(dim_parts)[:150])
                signals_added += 1

        # L2 滚动摘要 — 长对话的核心脉络
        if l2_summary and signals_added < 2:
            parts.append(l2_summary[:150])

        return " ".join(parts)[:500]

    # _filter_facts_by_query 已移至 core/context_engine.py（避免重复）

    # ============================================================
    # Rerank — 百炼 qwen3-rerank
    # ============================================================

    async def _rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int = 5,
    ) -> list[dict]:
        """
        使用百炼 qwen3-rerank 精排检索结果。

        qwen3-rerank:
          - 最大 500 文档, 单条 4K token, 请求上限 120K token
          - 100+ 语言覆盖
          - API: /compatible-api/v1/reranks (兼容 OpenAI 格式)

        Returns:
            [{index: int, document: str, relevance_score: float}, ...]
            按 relevance_score 降序排列
        """
        import aiohttp

        url = "https://dashscope.aliyuncs.com/compatible-api/v1/reranks"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.rerank_model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
            "return_documents": True,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.warning(f"[RAG] Rerank API 返回 {resp.status}: {text[:200]}")
                        return []

                    data = await resp.json()
                    return data.get("results", [])

        except Exception as e:
            logger.warning(f"[RAG] Rerank 失败 (非关键), 跳过精排: {e}")
            return []

    # ============================================================
    # 检索融合
    # ============================================================

    @staticmethod
    def _rrf_fusion(
        results_lists: list[list[dict]],
        k: int = 60,
    ) -> list[dict]:
        """
        Reciprocal Rank Fusion — 将多路检索结果合并为统一排序。

        RRF 公式: score(d) = Σ 1 / (k + rank_i(d))
        其中 rank_i(d) 是文档 d 在第 i 路结果中的排名，
        k=60 是论文中验证的稳定常数。

        无需调参，无需训练数据，基于排名信息合并。
        """
        fused = {}
        doc_map = {}

        for results in results_lists:
            for rank, doc in enumerate(results, start=1):
                doc_id = doc.get("id", "")
                if not doc_id:
                    continue

                fused[doc_id] = fused.get(doc_id, 0) + 1.0 / (k + rank)
                if doc_id not in doc_map:
                    # 复制 dict 避免修改调用方的原始数据
                    doc_map[doc_id] = dict(doc)
                    doc_map[doc_id]["rrf_score"] = 0.0

                doc_map[doc_id]["rrf_score"] = fused[doc_id]

        sorted_ids = sorted(fused.keys(), key=lambda x: fused[x], reverse=True)
        return [doc_map[i] for i in sorted_ids]

    @staticmethod
    def _apply_keyword_boost(
        query: str,
        results: list[dict],
        boost_factor: float = 0.05,
    ) -> list[dict]:
        """
        关键词重叠加权 — 对最终检索结果做微调。

        稠密向量捕获语义，关键词补捕获术语。
        对于含专有名词/代码符号的 query，这项能显著提升精度。
        """
        tech_terms = RAGService._extract_tech_terms(query)
        if not tech_terms:
            return results

        boosted = []
        for r in results:
            r = dict(r)  # 浅拷贝，不修改调用方
            doc_lower = r.get("document", "").lower()
            overlap_count = sum(1 for t in tech_terms if t.lower() in doc_lower)
            overlap_ratio = overlap_count / len(tech_terms)

            if overlap_ratio >= 0.3:
                if "rerank_score" in r:
                    r["rerank_score"] += overlap_ratio * boost_factor
                elif "score" in r:
                    r["score"] = min(1.0, r["score"] + overlap_ratio * boost_factor)
            boosted.append(r)

        # 按 score 重新排序
        def _sort_key(r):
            return max(r.get("rerank_score", 0), r.get("score", 0))

        boosted.sort(key=_sort_key, reverse=True)
        return boosted

    # ============================================================
    # 内部工具方法
    # ============================================================

    def _extract_keywords(self, text: str) -> str:
        """提取中文+英文关键词（用于 metadata 辅助检索）。"""
        tech_patterns = [
            r'\b(?:LLM|RAG|QLoRA|API|GPU|CPU|SQL|NoSQL|HTTP|REST|SSE|JSON|XML|'
            r'CSS|HTML|JS|TS|React|Vue|Python|Rust|Go|Java|Docker|K8s|CI|CD|'
            r'GPT|Claude|Ollama|PGVector|ChromaDB|SQLite|FastAPI|Gradio|'
            r'Prompt|Agent|Tool|Skill|Workflow|Chain|Embedding|Fine[\s-]?tuning|'
            r'Transformer|Attention|RLHF|DPO)\b',
            r'(?:提示词|工作流|微调|向量|嵌入|检索|增强|生成|推理|'
            r'深度学习|机器学习|自然语言|大模型|知识库|上下文|对话|追问|'
            r'分类|提取|总结|翻译|优化|部署|测试|调试|'
            r'软件工程|架构设计|技术选型|代码审查|项目管理|敏捷开发)',
        ]

        keywords = set()
        for pattern in tech_patterns:
            found = re.findall(pattern, text, re.IGNORECASE)
            keywords.update(f.lower() for f in found)

        chinese_words = re.findall(r'[一-鿿]{2,6}', text)
        stopwords = {
            '可以', '这个', '那个', '什么', '怎么', '为什么', '一个', '不是',
            '我们', '他们', '就是', '还是', '或者', '但是', '因为', '所以',
            '如果', '虽然', '而且', '然后', '之后', '之前', '已经', '没有',
        }
        for w in chinese_words:
            if w not in stopwords and len(w) >= 3:
                keywords.add(w)

        return ", ".join(sorted(keywords)[:20])

    @staticmethod
    def _extract_tech_terms(query: str) -> list[str]:
        """从 query 中提取技术专有名词（用于关键词重叠加权 + 短 query 相关性判断）。"""
        patterns = [
            r'\b[A-Z][a-z]+(?:\s?[A-Z][a-z]+)*\b',   # PascalCase / camelCase
            r'\b[a-z]+(?:-[a-z]+)+\b',                # kebab-case
            r'\b[A-Z]{2,}\b',                          # 全大写缩写
            r'\b[a-z]+(?:\.[a-z]+)+\b',                # dot.notation
        ]

        terms = set()
        for pattern in patterns:
            found = re.findall(pattern, query)
            terms.update(f for f in found if len(f) >= 2)
        return list(terms)

    # _extract_query_keywords 已移至 core/context_engine.py（避免重复）

    def _make_chunk_id(self, file_path: str, chunk_index: int) -> str:
        raw = f"{file_path}:{chunk_index}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    # _dummy_embedding 已移除 — 改用 PGVectorStore.exists_by_metadata() 直接查 JSONB
