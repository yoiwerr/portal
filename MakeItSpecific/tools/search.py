"""
MakeItSpecific Agent Tool — 知识库检索。

search_knowledge_base : PGVector 向量检索本地知识库。

这是唯一的检索入口。不再有联网搜索 — RAG + 模型自身知识覆盖所有场景。
"""

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ── 服务注入 ──
_rag_service = None


def set_tool_services(rag_service=None, **kwargs):
    """由 Agent 在每轮对话前调用，注入 RAG 服务引用。"""
    global _rag_service
    _rag_service = rag_service


# ============================================================
# search_knowledge_base — 唯一检索工具
# ============================================================

@tool
def search_knowledge_base(query: str) -> str:
    """
    【用途】从本地知识库 (PGVector) 向量检索领域知识。覆盖提示词工程、工作流、技术选型等已索引的 .md 文档。

    【什么时候用】
    - 用户的问题涉及最佳实践、工具推荐、方法论、技术对比
    - Planner 判断需要领域知识才能给出高质量回答
    - 用户明确问「知识库里有没有关于 X 的内容」
    - 你（Executor）对某个技术细节不确定，需要查证

    【坚决不用】
    - 常识性问题 — 模型自身知识已足够（如「什么是 Python」「for 循环怎么写」）
    - 纯代码语法/调试 — 知识库不存代码文档，直接回答
    - 纯创意/头脑风暴 — 不需要检索事实
    - 用户明确说「不要查资料，直接说」
    - 已经在本轮对话中检索过同一个 query — 用缓存的结果

    【优先级】🔴 最高 — Executor 在处理任务时，如果涉及技术选型、工具推荐、方法论，必须先调此工具。

    【参数】query: 搜索查询。用关键词而非完整句子。英文术语 + 中文描述混合效果最好。
           例: "RAG 混合检索 技术方案" / "prompt engineering Chain-of-Thought"
    【返回】格式化的知识库上下文文本（含来源文件标注）。未找到时返回明确提示。
    """
    logger.info(f"[Tool] search_knowledge_base: {query}")
    if _rag_service is None:
        return "（知识库服务未初始化，无法检索。请基于你的通用知识回答，并告知用户此限制。）"
    try:
        return _rag_service.query_formatted(query, top_k=3)
    except Exception as e:
        logger.error(f"[Tool] search_knowledge_base 失败: {e}")
        return f"知识库检索出错: {str(e)}。请基于你的通用知识继续回答，并告知用户检索失败。"
