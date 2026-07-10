"""
RAG 领域知识库服务 — 基于 PostgreSQL + PGVector。

知识来源: knowledge_base/ 目录下的 .md 文件（用户手动维护）
向量引擎: DashScope text-embedding-v3 (1024维)，与 ChatLab 一致

ChromaDB → PGVector 迁移:
  旧: chromadb.PersistentClient + DashScopeEmbeddingFunction
  新: services.vector_store.PGVectStore + 手动 embedding 调用
"""

import hashlib
import logging
import re
from pathlib import Path
from typing import Optional

from langchain_community.embeddings import DashScopeEmbeddings

from services.vector_store import PGVectorStore

logger = logging.getLogger(__name__)


class RAGService:
    """领域知识检索服务 — PGVector 后端。

    Collection: domain_knowledge
    分块策略: 按 ## 标题分段，每段 ≤500 字符，overlap=50
    Embedding: DashScope text-embedding-v3 (1024 维)
    """

    COLLECTION = "domain_knowledge"

    def __init__(
        self,
        vector_store: PGVectorStore,
        knowledge_base_dir: Path,
        api_key: str = "",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ):
        self.store = vector_store
        self.kb_dir = knowledge_base_dir
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Embedding 模型（与 ChatLab 一致: text-embedding-v3, 1024维）
        self._embedding_model: Optional[DashScopeEmbeddings] = None
        self._api_key = api_key

    @property
    def embedding_model(self) -> DashScopeEmbeddings:
        if self._embedding_model is None:
            if not self._api_key:
                raise ValueError("DASHSCOPE_API_KEY 未设置，无法生成 embedding")
            self._embedding_model = DashScopeEmbeddings(
                model="text-embedding-v3",
                dashscope_api_key=self._api_key,
            )
        return self._embedding_model

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
        扫描 knowledge_base_dir 目录，将 .md 文件分块后索引到 PGVector。

        分块策略: 按 ## 标题分段，每段不超过 chunk_size 字符。
        去重: 按 MD5(chunk) 检查是否已存在。

        Returns:
            本次新索引的 chunk 数量
        """
        md_files = list(self.kb_dir.glob("*.md"))
        if not md_files:
            logger.info("[RAG] knowledge_base/ 目录为空，跳过索引")
            return 0

        total_chunks = 0
        new_documents = []
        new_metadatas = []
        new_ids = []

        # 获取已存在的 ID（用于去重）
        existing_ids = set()
        try:
            count = await self.store.count(self.COLLECTION)
            logger.info(f"[RAG] 当前 domain_knowledge 表中有 {count} 条记录")
        except Exception:
            pass

        for md_file in md_files:
            content = md_file.read_text(encoding="utf-8")
            chunks = self._chunk_text(content)

            for i, chunk in enumerate(chunks):
                chunk_id = self._make_chunk_id(str(md_file), i)
                content_hash = hashlib.md5(chunk.encode()).hexdigest()

                # 检查是否已存在（用 content_hash 在 metadata 中）
                results = await self.store.search(
                    self.COLLECTION,
                    self._dummy_embedding(),  # 不用于搜索，只是占位
                    top_k=1,
                    filter_meta={"content_hash": content_hash},
                )
                if results:
                    existing_ids.add(chunk_id)
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
            # 批量生成 embedding
            logger.info(f"[RAG] 生成 {len(new_documents)} 个 embedding...")
            embeddings = self.embedding_model.embed_documents(new_documents)

            # 批量写入 PGVector
            await self.store.add(
                collection=self.COLLECTION,
                documents=new_documents,
                embeddings=embeddings,
                metadatas=new_metadatas,
                ids=new_ids,
            )
            total_chunks = len(new_ids)
            logger.info(f"[RAG] 已索引 {total_chunks} 个新片段")

        # 清理已删除文件的旧 chunk（可选）
        current_files = {f.name for f in md_files}
        if current_files:
            # PGVector 不支持 "NOT IN" 批量删除，此处用简单策略：
            # 保留所有数据，手动清理时调用 reindex_all()
            pass

        return total_chunks

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

    async def query(self, query_text: str, top_k: int = 3) -> list[str]:
        """向量相似度检索 — PGVector cosine distance。

        Args:
            query_text: 查询文本
            top_k: 返回的 top-K 片段数

        Returns:
            相关知识片段文本列表
        """
        try:
            # 生成查询 embedding
            query_emb = self.embedding_model.embed_query(query_text)

            # PGVector 搜索
            results = await self.store.search(
                collection=self.COLLECTION,
                query_embedding=query_emb,
                top_k=top_k,
            )
        except Exception as e:
            logger.error(f"[RAG] 检索失败: {e}")
            return []

        return [r["document"] for r in results if r.get("document")]

    async def query_formatted(self, query_text: str, top_k: int = 3) -> str:
        """检索并格式化为上下文文本，可直接注入 LLM prompt。"""
        chunks = await self.query(query_text, top_k)
        if not chunks:
            return "（未找到相关知识）"

        lines = ["以下是从知识库中检索到的相关信息：", ""]
        for i, chunk in enumerate(chunks, 1):
            lines.append(f"### 📚 知识点 {i}")
            lines.append(chunk)
            lines.append("")

        return "\n".join(lines)

    # ============================================================
    # 内部工具方法（保留原有逻辑）
    # ============================================================

    def _chunk_text(self, text: str, max_chars: int = None, overlap: int = None) -> list[str]:
        """将文本按段落+句子分块。"""
        if max_chars is None:
            max_chars = self.chunk_size
        if overlap is None:
            overlap = self.chunk_overlap

        sections = re.split(r"\n(?=## )", text)
        chunks = []

        for section in sections:
            section = section.strip()
            if not section:
                continue

            if len(section) <= max_chars:
                chunks.append(section)
            else:
                sentences = re.split(r"(?<=[。！？.!?\n])\s*", section)
                current_chunk = ""
                for sent in sentences:
                    if len(current_chunk) + len(sent) <= max_chars:
                        current_chunk += sent
                    else:
                        if current_chunk.strip():
                            chunks.append(current_chunk.strip())
                        overlap_text = (
                            current_chunk[-overlap:]
                            if len(current_chunk) > overlap
                            else current_chunk
                        )
                        current_chunk = overlap_text + sent
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())

        return chunks

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

    def _make_chunk_id(self, file_path: str, chunk_index: int) -> str:
        raw = f"{file_path}:{chunk_index}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def _dummy_embedding(self) -> list[float]:
        """返回一个占位 embedding（仅用于 metadata 查询，不用于向量检索）。"""
        return [0.0] * 1024
