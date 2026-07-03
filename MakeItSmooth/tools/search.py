"""
MakeItSmooth Agent Tools。

参照 ChatLab src/tools.py 的 LangChain @tool 模式。
三个 Tool：
  - search_knowledge_base: ChromaDB 领域知识检索
  - search_chat_history: SQLite 历史对话检索
  - search_web: 联网搜索（Phase 2 占位）

与 ChatLab 的差异：
  - ChromaDB 替代 PGVector 做向量检索
  - 本地知识库替代 Tavily 做联网搜索（Phase 2）
"""

from langchain_core.tools import tool

# 工具实例在模块加载时通过 _set_services() 注入
# 避免循环导入（tools 不能被 services 反向依赖）
_rag_service = None
_session_store = None
_session_id = None  # 当前会话 ID，用于历史检索


def set_tool_services(rag_service=None, session_store=None, session_id=None):
    """在 Agent 初始化时注入服务实例。"""
    global _rag_service, _session_store, _session_id
    _rag_service = rag_service
    _session_store = session_store
    _session_id = session_id


# ============================================================
# Tool 1: 知识库检索
# ============================================================

@tool
def search_knowledge_base(query: str) -> str:
    """
    从 MakeItSmooth 本地知识库中检索与工作流增强相关的领域知识。
    当需要推荐工具、提供最佳实践、查询技术选型建议时，调用此工具。
    输入参数 query 是你想查询的关键词或问题。
    """
    print(f"[Tool] 知识库检索: {query}")
    if _rag_service is None:
        return "（知识库服务未初始化）"

    try:
        result = _rag_service.query_formatted(query, top_k=3)
        return result
    except Exception as e:
        return f"知识库检索失败: {str(e)}"


# ============================================================
# Tool 2: 历史对话检索
# ============================================================

@tool
def search_chat_history(query: str) -> str:
    """
    检索当前会话中与查询相关的历史对话记录。
    当用户提到之前说过的话、想参考之前的决策时，调用此工具。
    输入参数 query 是你想查找的历史对话关键词。
    """
    print(f"[Tool] 历史对话检索: {query}")
    if _session_store is None or _session_id is None:
        return "（当前没有可检索的历史对话）"

    try:
        conversation = _session_store.get_conversation_text(_session_id)
        if not conversation:
            return "（当前会话暂无历史消息）"

        # 简单关键词过滤（Phase 2 可升级为向量检索）
        lines = conversation.split("\n")
        matched = []
        for line in lines:
            if query.lower() in line.lower():
                matched.append(line)

        if matched:
            return "\n".join(matched[:10])
        return "（未找到相关历史对话）"
    except Exception as e:
        return f"历史对话检索失败: {str(e)}"


# ============================================================
# Tool 3: 联网搜索（Phase 2 占位）
# ============================================================

@tool
def search_web(query: str) -> str:
    """
    当本地知识库无法回答问题时，使用此工具进行联网搜索。
    Phase 2 接入真实搜索 API，当前返回占位提示。
    输入参数 query 是你要搜索的关键词。
    """
    print(f"[Tool] 联网搜索: {query}")
    # Phase 2: 接入 Tavily / 其他搜索 API
    return (
        f"联网搜索功能将在 Phase 2 上线。当前查询: {query}。\n"
        "建议参考本地知识库或手动搜索获取最新信息。"
    )


# ============================================================
# 统一导出
# ============================================================

ALL_TOOLS = [search_knowledge_base, search_chat_history, search_web]
