"""
MakeItSpecific Agent Tool — 知识持久化。

add_to_knowledge_base : 将对话中提炼的有价值知识写入 PGVector 向量库。
                       下次对话可通过 search_knowledge_base 检索到。
"""

import hashlib
import logging
from datetime import datetime

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_rag_service = None


def set_knowledge_tool_services(rag_service=None, **kwargs):
    """由 Agent 在初始化时调用，注入 RAG 服务引用。"""
    global _rag_service
    _rag_service = rag_service


@tool
def add_to_knowledge_base(content: str, title: str = "", source: str = "conversation") -> str:
    """
    【用途】将对话中提炼的有价值知识持久化写入 PGVector 向量库。写入后，后续对话可通过 search_knowledge_base 检索到。

    【什么时候用】
    - 用户明确要求保存某段信息（「帮我把这个记下来」「保存一下」）
    - Executor 在对话中总结出了可复用的知识（技术决策、最佳实践、项目约定）
    - 用户分享了值得留存的领域经验或工作方法

    【坚决不用】
    - 临时/一次性的闲聊内容 — 不值得占用向量库空间
    - 用户隐私信息 — 密码、联系方式、身份证号等
    - 已有重复内容 — content_hash 去重会拦截，但浪费一次 embedding 调用
    - 少于 30 字符的碎片 — 信息量不足，检索时也匹配不到
    - 用户没有主动要求、且你自己也不确定是否值得留存时 — 默认不存

    【优先级】🟢 低 — 仅当信息明确有价值且用户同意时才写。知识库是长期资产，宁缺毋滥。

    【参数】
    - content: 知识内容 (Markdown 格式最佳，纯文本也可)
    - title:   知识标题 (可选，默认取 content 首行前 50 字符)
    - source:  来源标识 (默认 "conversation"，可改为 "user_shared" / "web_article" 等)

    【返回】写入结果摘要（标题、内容长度）。失败时返回错误原因。
    """
    if _rag_service is None:
        return "（知识库服务未初始化，无法写入。内容已保留在对话中，重启后可能丢失。）"

    if not content or len(content.strip()) < 30:
        return "内容过短（< 30 字符），拒绝写入。知识库只接受有实质信息的内容。"

    try:
        title = title or content.strip().split("\n")[0][:50]
        content_hash = hashlib.md5(content.encode()).hexdigest()
        chunk_id = hashlib.md5(
            f"{source}:{title}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

        # 生成 embedding
        emb = _rag_service.embedding_model.embed_query(content.strip())

        # 写入 PGVector domain_knowledge 表
        import asyncio
        store = _rag_service.store

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
        return f"知识库写入失败: {str(e)}。内容已保留在对话中，重启后可能丢失。"
