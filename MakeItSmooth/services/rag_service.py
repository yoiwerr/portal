"""
RAG 领域知识库服务 — 对齐 ChatLab src/rag_function.py。
基于 ChromaDB 存储 + DashScope Embedding (text-embedding-v3)。

知识来源: knowledge_base/ 目录下的 .md 文件（用户手动维护）
"""

import hashlib
import re
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
from chromadb.config import Settings as ChromaSettings
from langchain_community.embeddings import DashScopeEmbeddings


class DashScopeEmbeddingFunction(EmbeddingFunction):
    """ChromaDB EmbeddingFunction 适配器 — 委托给 DashScopeEmbeddings。
    对齐 ChatLab 的 text-embedding-v3（1024 维）。"""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("DASHSCOPE_API_KEY is required for DashScope embeddings")
        self._embeddings = DashScopeEmbeddings(
            model="text-embedding-v3",
            dashscope_api_key=api_key,
        )

    def __call__(self, input: Documents) -> Embeddings:
        return self._embeddings.embed_documents(input)


class RAGService:
    """领域知识检索服务。"""

    COLLECTION_NAME = "domain_knowledge"

    def __init__(self, chroma_path: Path, knowledge_base_dir: Path, api_key: str = ""):
        self.chroma_path = str(chroma_path)
        self.kb_dir = knowledge_base_dir
        self._api_key = api_key
        self._client: Optional[chromadb.PersistentClient] = None
        self._collection: Optional[chromadb.Collection] = None

    # ============================================================
    # 初始化
    # ============================================================

    @property
    def client(self) -> chromadb.PersistentClient:
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=self.chroma_path,
                settings=ChromaSettings(anonymized_telemetry=False)
            )
        return self._client

    @property
    def ef(self) -> EmbeddingFunction:
        """懒加载 embedding function（首次调用时可能发起网络请求验证 API key）。"""
        return DashScopeEmbeddingFunction(api_key=self._api_key)

    @property
    def collection(self) -> chromadb.Collection:
        if self._collection is None:
            try:
                self._collection = self.client.get_collection(
                    self.COLLECTION_NAME,
                    embedding_function=self.ef,
                )
            except Exception:
                # collection 不存在或 embedding function 不匹配 → 新建
                try:
                    self.client.delete_collection(self.COLLECTION_NAME)
                except Exception:
                    pass
                self._collection = self.client.create_collection(
                    name=self.COLLECTION_NAME,
                    metadata={"description": "MakeItSmooth 领域知识库"},
                    embedding_function=self.ef,
                )
        return self._collection

    # ============================================================
    # 知识库索引
    # ============================================================

    def ingest_knowledge_base(self) -> int:
        """
        扫描 knowledge_base_dir 目录，将 .md 文件分块后索引到 ChromaDB。

        分块策略: 按 ## 标题分段，每段不超过 500 字符。
        使用 DashScope text-embedding-v3 生成 1024 维向量。

        Returns:
            本次索引入的 chunk 数量
        """
        md_files = list(self.kb_dir.glob("*.md"))
        if not md_files:
            return 0

        total_chunks = 0
        existing_ids = set()

        try:
            existing = self.collection.get()
            if existing and existing["ids"]:
                existing_ids = set(existing["ids"])
        except Exception:
            pass

        new_ids = []
        new_documents = []
        new_metadatas = []

        for md_file in md_files:
            content = md_file.read_text(encoding="utf-8")
            chunks = self._chunk_text(content)

            for i, chunk in enumerate(chunks):
                chunk_id = self._make_chunk_id(str(md_file), i)

                if chunk_id in existing_ids:
                    continue

                keywords = self._extract_keywords(chunk)

                new_ids.append(chunk_id)
                new_documents.append(chunk)
                new_metadatas.append({
                    "source_file": md_file.name,
                    "source_path": str(md_file),
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "keywords": keywords,
                })

        if new_ids:
            self.collection.add(
                ids=new_ids,
                documents=new_documents,
                metadatas=new_metadatas,
            )
            total_chunks = len(new_ids)

        return total_chunks

    def reindex_all(self) -> int:
        """清除并重建整个索引。"""
        try:
            self.client.delete_collection(self.COLLECTION_NAME)
        except Exception:
            pass
        self._collection = None
        return self.ingest_knowledge_base()

    def get_kb_stats(self) -> dict:
        """获取知识库统计信息。"""
        try:
            count = self.collection.count()
        except Exception:
            count = 0

        md_files = list(self.kb_dir.glob("*.md"))
        return {
            "chunk_count": count,
            "source_files": len(md_files),
            "file_names": [f.name for f in md_files],
        }

    # ============================================================
    # 检索
    # ============================================================

    def query(self, query_text: str, top_k: int = 3) -> list[str]:
        """
        向量相似度检索 — 使用 ChromaDB 原生 query（DashScope embedding）。

        Args:
            query_text: 查询文本
            top_k: 返回的 top-K 片段数

        Returns:
            相关知识片段文本列表
        """
        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=top_k,
            )
        except Exception:
            return []

        if not results or not results.get("ids") or not results["ids"][0]:
            return []

        documents = results.get("documents", [[]])[0]
        return [doc for doc in documents if doc]

    def query_formatted(self, query_text: str, top_k: int = 3) -> str:
        """
        检索并格式化为上下文文本。
        可直接注入到 LLM prompt 中。
        """
        chunks = self.query(query_text, top_k)
        if not chunks:
            return "（未找到相关知识）"

        lines = ["以下是从知识库中检索到的相关信息：", ""]
        for i, chunk in enumerate(chunks, 1):
            lines.append(f"### 📚 知识点 {i}")
            lines.append(chunk)
            lines.append("")

        return "\n".join(lines)

    # ============================================================
    # 内部工具方法
    # ============================================================

    def _chunk_text(self, text: str, max_chars: int = 500, overlap: int = 50) -> list[str]:
        """将文本按段落+句子分块。"""
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
                        overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                        current_chunk = overlap_text + sent
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())

        return chunks

    def _extract_keywords(self, text: str) -> str:
        """提取中文+英文关键词（简单规则版，用于 metadata 辅助检索）。"""
        tech_patterns = [
            r'\b(?:LLM|RAG|QLoRA|API|GPU|CPU|SQL|NoSQL|HTTP|REST|SSE|JSON|XML|'
            r'CSS|HTML|JS|TS|React|Vue|Python|Rust|Go|Java|Docker|K8s|CI|CD|'
            r'GPT|Claude|Ollama|ChromaDB|SQLite|FastAPI|Gradio|'
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
        stopwords = {'可以', '这个', '那个', '什么', '怎么', '为什么', '一个', '不是',
                     '我们', '他们', '就是', '还是', '或者', '但是', '因为', '所以',
                     '如果', '虽然', '而且', '然后', '之后', '之前', '已经', '没有'}
        for w in chinese_words:
            if w not in stopwords and len(w) >= 3:
                keywords.add(w)

        return ", ".join(sorted(keywords)[:20])

    def _make_chunk_id(self, file_path: str, chunk_index: int) -> str:
        """生成唯一的 chunk ID。"""
        raw = f"{file_path}:{chunk_index}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]
