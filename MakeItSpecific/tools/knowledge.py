"""
MakeItSpecific Agent Tool — 知识持久化。

add_to_knowledge_base : 将对话中提炼的有价值知识写入 PGVector 向量库。
                       写入后立即可通过 search_knowledge_base 检索到。
                       同一张 domain_knowledge 表，读写分离。
"""

import hashlib
import logging
from datetime import datetime

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_rag_service = None


def set_knowledge_tool_services(rag_service=None, **kwargs):
    global _rag_service
    _rag_service = rag_service


@tool
async def add_to_knowledge_base(content: str, title: str = "", source: str = "conversation") -> str:
    """
    【用途】将对话中提炼的有价值知识持久化写入 PGVector 向量库。写入后立即可通过 search_knowledge_base 检索到（无需 reindex）。

    【什么时候用】
    - 用户明确要求保存（"帮我把这个记下来""存一下"）
    - Executor 从对话中提取出了可复用的知识（技术决策、项目约定、经验总结）
    - 用户分享了值得跨会话复用的领域知识或工作方法

    【坚决不用】
    - 临时/一次性的闲聊 — 知识库是长期资产，不是垃圾桶
    - 用户隐私信息 — 密码、联系方式、身份证号等
    - 少于 30 字符的碎片 — 检索时也匹配不到，写了白写
    - 用户没有主动要求、且无法判断是否值得留存 — 默认不写
    - 与已有内容高度重复 — 浪费 embedding 调用（虽然 content_hash 会标记但不会去重）

    【与其他 tool 的关系】
    - 与 search_knowledge_base: 读写分离。add_to_kb 只写不读，search_kb 只读不写。
      同一张表双向操作 — 写入的知识下次 search_kb 可命中。职责明确，无重叠。
    - 与 python_exec: 无关。
    - 与 run_shell_preview: 无关。shell 不能写 PGVector。

    【参数】
    - content: 知识内容 (Markdown 最佳，纯文本也可)。≥30 字符。
    - title:   标题 (可选，默认取 content 首行前 50 字符)
    - source:  来源 (默认 "conversation"，可设 "user_shared" / "code_review" 等)

    【返回】写入结果摘要。失败时返回错误原因（不会丢数据 — 对话本身已存在 messages 表）。
    """
    if _rag_service is None:
        return "（知识库服务未初始化，无法写入。内容已保留在当前对话中。）"

    if not content or len(content.strip()) < 30:
        return "内容过短（< 30 字符），拒绝写入。知识库只接受有实质信息的内容（≥30 字符）。"

    try:
        title = title or content.strip().split("\n")[0][:50]
        content_hash = hashlib.md5(content.encode()).hexdigest()
        chunk_id = hashlib.md5(
            f"{source}:{title}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

        emb = _rag_service.embedding_model.embed_query(content.strip())

        await _rag_service.store.add(
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
        )

        return (
            f"✅ 已存入知识库。\n"
            f"- 标题: {title}\n"
            f"- 内容长度: {len(content)} 字符\n"
            f"下次对话中可通过 search_knowledge_base 检索到。"
        )
    except Exception as e:
        logger.error(f"[Tool] add_to_knowledge_base 失败: {e}")
        return f"知识库写入失败: {str(e)}。内容已保留在当前对话中（messages 表），重启后可能丢失。"
