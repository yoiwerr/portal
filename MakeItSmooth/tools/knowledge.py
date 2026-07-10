"""
MakeItSmooth Agent Tool — 知识管理。

add_to_knowledge_base : 将对话中提炼的知识点写入 PGVector 向量库
"""

import hashlib
import logging
from datetime import datetime

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_rag_service = None
_config = None


def set_knowledge_tool_services(rag_service=None, config=None):
    global _rag_service, _config
    _rag_service = rag_service
    _config = config


@tool
def add_to_knowledge_base(content: str, title: str = "", source: str = "conversation") -> str:
    """
    将一段有价值的知识/信息持久化存入本地知识库（PGVector）。
    后续对话中可通过 search_knowledge_base 检索到。

    使用时机:
    - 用户在对话中透露了重要决策、偏好、技术选型理由
    - Agent 发现了一个值得记住的最佳实践
    - 对话中产生了可复用的代码片段/配置模板

    参数:
    - content: 要存入的知识内容（Markdown 格式最佳）
    - title: 知识标题（可选）
    - source: 来源标识（默认 "conversation"）
    """
    if _rag_service is None:
        return "（知识库服务未初始化，无法写入）"

    if not content or len(content.strip()) < 20:
        return "内容过短（< 20 字符），拒绝写入。"

    try:
        title = title or content.strip().split("\n")[0][:50]
        content_hash = hashlib.md5(content.encode()).hexdigest()
        chunk_id = hashlib.md5(
            f"{source}:{title}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

        # 生成 embedding
        emb = _rag_service.embedding_model.embed_query(content.strip())

        # 写入 PGVector domain_knowledge 表
        from services.vector_store import PGVectorStore
        store = _rag_service.store
        collection = PGVectorStore.COLLECTIONS["domain_knowledge"] and "domain_knowledge"

        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            future = asyncio.run_coroutine_threadsafe(
                store.add(
                    collection="domain_knowledge",
                    documents=[content.strip()],
                    embeddings=[emb],
                    metadatas=[{
                        "source": source,
                        "title": title,
                        "added_at": datetime.now().isoformat(),
                        "content_hash": content_hash,
                        "content_length": len(content),
                    }],
                    ids=[chunk_id],
                ),
                loop,
            )
            future.result(timeout=10)
        else:
            asyncio.run(store.add(
                collection="domain_knowledge",
                documents=[content.strip()],
                embeddings=[emb],
                metadatas=[{
                    "source": source,
                    "title": title,
                    "added_at": datetime.now().isoformat(),
                    "content_hash": content_hash,
                    "content_length": len(content),
                }],
                ids=[chunk_id],
            ))

        return (
            f"✅ 已存入知识库。\n"
            f"- 标题: {title}\n"
            f"- 内容长度: {len(content)} 字符\n"
            f"下次对话中可通过 search_knowledge_base 检索到此信息。"
        )
    except Exception as e:
        logger.error(f"[Tool] add_to_knowledge_base 失败: {e}")
        return f"知识库写入失败: {str(e)}"


@tool
def list_knowledge_sources() -> str:
    """列出知识库中已有的知识来源和统计信息。"""
    if _rag_service is None:
        return "（知识库服务未初始化）"

    try:
        import asyncio
        stats = asyncio.run(_rag_service.get_kb_stats())

        lines = [
            "### 知识库状态",
            f"- 总片段数: {stats.get('chunk_count', 0)}",
            f"- 源文件数: {stats.get('source_files', 0)}",
            f"- 文件名: {', '.join(stats.get('file_names', []))}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"获取知识库状态失败: {str(e)}"
