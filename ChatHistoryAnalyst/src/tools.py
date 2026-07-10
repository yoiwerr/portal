# src/tools.py
from langchain_core.tools import tool
from langchain_tavily import TavilySearch
from src.rag_function import (
    get_knowledge_store,
    get_chat_history_store,
    get_context_analysis_store,
)


RELEVANCE_THRESHOLD = 0.3


# ══════════════════════════════════════════════════════════════
# Tool 1: 心理学知识库检索（保持不变）
# ══════════════════════════════════════════════════════════════

@tool
def search_psychology_knowledge(query: str) -> str:
    """
    检索心理学专业知识库。当需要分析聊天记录背后的心理学动机、依恋模式、
    沟通姿态理论、关系动力学模型，或需要专业的心理学框架来支撑指数评分时，
    必须调用此工具。
    输入参数 query 应该是你想查询的心理学关键词或现象描述。
    """
    print(f"🛠️ [Tool] 知识库检索: {query}")
    try:
        results_with_score = get_knowledge_store().similarity_search_with_score(query, k=5)
    except Exception as e:
        err = str(e)
        if "different vector dimensions" in err:
            return "向量库维度不匹配，请先调用 POST /api/v1/import_knowledge 重新导入知识文件。"
        return f"知识库检索失败: {err}"

    filtered = [(doc, score) for doc, score in results_with_score if score >= RELEVANCE_THRESHOLD]
    if not filtered:
        return "本地心理学知识库中未找到相关内容。"

    lines = []
    for i, (doc, score) in enumerate(filtered):
        source = doc.metadata.get("source", "未知来源")
        lines.append(f"[{source}] (相关度: {score:.2f})\n{doc.page_content}")
    return "\n\n---\n\n".join(lines)


# ══════════════════════════════════════════════════════════════
# Tool 2: 结构化对话上下文检索（替代旧 search_chat_history）
# ══════════════════════════════════════════════════════════════

@tool
def search_chat_context(query: str, target_person: str = "") -> str:
    """
    检索对话的**纯结构化统计指标**。返回内容是原始数据，没有任何预判解读：
    - 消息量统计（总数、各自条数、比例）
    - 主动性数据（谁发起/终结对话的次数）
    - 消息长度统计（各自平均字数）
    - 响应时间数据（双方互相响应的平均间隔）
    - 逐轮对话时序（每条消息的发送者、字数、是否发起/终结）

    注意：返回的是原始统计数据，你需要根据 System Prompt 中的标准自行解读。
    如需查看具体的某条原始消息文本，请额外调用 deep_read_message 工具。

    当需要了解对话整体态势、量化指标、互动节奏时，优先调用此工具。

    输入参数:
    - query: 要搜索的数据维度关键词，如"消息量"、"响应时间"、"主动性"、"互动模式"
    - target_person: 目标分析对象名称，用于过滤只属于该人物的分析结果
    """
    print(f"🛠️ [Tool] 结构化上下文检索: {query} (target_person={target_person})")

    search_filter: dict = {"type": "context_analysis"}
    if target_person:
        search_filter["target_person"] = target_person

    try:
        store = get_context_analysis_store()
        results_with_score = store.similarity_search_with_score(
            query, k=5, filter=search_filter
        )
    except Exception as e:
        err = str(e)
        if "different vector dimensions" in err:
            return "向量库维度不匹配，请重新导入聊天记录。"
        # context_analysis store 可能为空或不存在，fallback 到原始消息
        print(f"  ⚠️ 结构化上下文检索失败，fallback 到原始消息: {err}")
        return _search_chat_history_fallback(query, target_person)

    filtered = [(doc, score) for doc, score in results_with_score if score >= RELEVANCE_THRESHOLD]
    if not filtered:
        print("  → 结构化指标无结果，fallback 到原始消息")
        fallback = _search_chat_history_fallback(query, target_person)
        return f"[结构化指标无直接命中，以下为原始消息检索结果]\n\n{fallback}"

    lines = []
    for doc, score in filtered:
        subtype = doc.metadata.get("subtype", "分析")
        lines.append(f"[{subtype}] (相关度: {score:.2f})\n{doc.page_content}")
    return "\n\n---\n\n".join(lines)


def _search_chat_history_fallback(query: str, target_person: str = "") -> str:
    """Fallback: 从原始聊天记录中检索。"""
    search_filter: dict = {"type": "chat_history"}
    if target_person:
        search_filter["target_person"] = target_person

    try:
        results_with_score = get_chat_history_store().similarity_search_with_score(
            query, k=5, filter=search_filter
        )
    except Exception as e:
        return f"历史记录检索失败: {str(e)}"

    filtered = [(doc, score) for doc, score in results_with_score if score >= RELEVANCE_THRESHOLD]
    if not filtered:
        hint = f"（已过滤 target_person={target_person}）" if target_person else ""
        return f"未找到相关的历史聊天记录。{hint}"

    lines = []
    for doc, score in filtered:
        sender = doc.metadata.get("sender", "?")
        ts = doc.metadata.get("timestamp", "")
        lines.append(f"[{sender} | {ts}] (相关度: {score:.2f})\n{doc.page_content}")
    return "\n\n---\n\n".join(lines)


# ══════════════════════════════════════════════════════════════
# Tool 3: 单条消息深读
# ══════════════════════════════════════════════════════════════

@tool
def deep_read_message(message_query: str, target_person: str = "") -> str:
    """
    根据关键词或内容片段精准检索**原始聊天消息全文**。
    当你已经通过 search_chat_context 了解了对话的整体态势，
    但需要核实某条具体消息的原文措辞、语气细节时，调用此工具。

    输入参数:
    - message_query: 要查找的消息关键词、话题或内容片段
    - target_person: 目标分析对象名称，用于过滤
    """
    print(f"🛠️ [Tool] 深读原文: {message_query} (target_person={target_person})")

    search_filter: dict = {"type": "chat_history"}
    if target_person:
        search_filter["target_person"] = target_person

    try:
        results_with_score = get_chat_history_store().similarity_search_with_score(
            message_query, k=3, filter=search_filter
        )
    except Exception as e:
        return f"原文检索失败: {str(e)}"

    filtered = [(doc, score) for doc, score in results_with_score if score >= RELEVANCE_THRESHOLD]
    if not filtered:
        return "未找到匹配的原始消息。"

    lines = []
    for doc, score in filtered:
        sender = doc.metadata.get("sender", "?")
        ts = doc.metadata.get("timestamp", "")
        msg_id = doc.metadata.get("message_id", "")
        lines.append(
            f"[{sender} | {ts}] (ID: {msg_id}, 相关度: {score:.2f})\n"
            f"{doc.page_content}"
        )
    return "\n\n---\n\n".join(lines)


# ══════════════════════════════════════════════════════════════
# Tool 4: 联网搜索（保持不变）
# ══════════════════════════════════════════════════════════════

_raw_tavily = TavilySearch(max_results=3)


@tool
def web_search(query: str) -> str:
    """
    当需要搜索最新的心理学论文、网络流行语含义、或本地知识库无法覆盖的外部实时信息时，
    调用此工具进行全网搜索。
    输入参数 query 是你要搜索的关键词。
    """
    print(f"🛠️ [Tool] 联网检索: {query}")
    try:
        results = _raw_tavily.invoke({"query": query})

        if isinstance(results, list):
            text_results = []
            for idx, r in enumerate(results):
                if isinstance(r, dict):
                    content = r.get("content", "")
                    text_results.append(f"结果{idx + 1}: {content}")
            return "\n\n".join(text_results) if text_results else "未找到相关网络信息。"

        return str(results)

    except Exception as e:
        return f"联网搜索失败: {str(e)}"


# ══════════════════════════════════════════════════════════════
# 统一导出
# ══════════════════════════════════════════════════════════════

ALL_TOOLS = [
    search_psychology_knowledge,
    search_chat_context,
    deep_read_message,
    web_search,
]
