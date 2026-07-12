"""
MakeItSpecific Agent Tools — 信息检索。

search_knowledge_base : ChromaDB 向量检索本地知识库
search_web           : Tavily API 联网搜索
fetch_url            : 抓取指定 URL 转为 Markdown
search_chat_history  : 当前会话历史检索
"""

import json
import logging
from typing import Optional

import httpx
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ── 服务注入（避免循环导入）──────────────────────────────────
_rag_service = None
_session_store = None
_session_id = None
_config = None


def set_tool_services(rag_service=None, session_store=None, session_id=None, config=None):
    global _rag_service, _session_store, _session_id, _config
    _rag_service = rag_service
    _session_store = session_store
    _session_id = session_id
    _config = config


# ============================================================
# Tool 1: 知识库检索（保留）
# ============================================================

@tool
def search_knowledge_base(query: str) -> str:
    """
    【用途】从本地知识库 (PGVector) 中检索领域知识。适用于推荐工具、最佳实践、技术选型建议等已有文档覆盖的内容。

    【不要用】
    - 需要实时/最新信息时（用 search_web）
    - 纯代码语法问题（知识库不存代码文档）
    - 常识性问题（直接回答，不需要检索）

    【优先级】🔴 最高 — 每次执行任务前必须先搜本地知识库。

    【参数】query: 搜索查询，尽量用关键词而非完整句子，英文术语效果更好。
    """
    logger.info(f"[Tool] search_knowledge_base: {query}")
    if _rag_service is None:
        return "（知识库服务未初始化）"
    try:
        return _rag_service.query_formatted(query, top_k=3)
    except Exception as e:
        return f"知识库检索失败: {str(e)}"


# ============================================================
# Tool 2: 联网搜索 — Tavily API
# ============================================================

@tool
def search_web(query: str) -> str:
    """
    【用途】联网搜索互联网获取最新信息（Tavily API）。适用于本地知识库无覆盖、需要最新新闻/技术动态/实时数据时。

    【不要用】
    - 本地知识库已有答案时（先用 search_knowledge_base）
    - 纯代码/语法/调试问题（不需要联网）
    - 常识性问题（直接回答）
    - 需要深度分析时（用 delegate_task 代替，它能搜索+阅读+分析）

    【优先级】🟡 中等 — 仅在 search_knowledge_base 返回 "未找到" 后使用。

    【参数】query: 搜索词，英文效果更好。不超过 50 字符，用关键词而非完整句子。
    【前置条件】需设置 TAVILY_API_KEY 或 SEARCH_API_KEY 环境变量。
    """
    logger.info(f"[Tool] search_web: {query}")

    api_key = _get_search_api_key()
    if not api_key:
        return (
            "联网搜索未配置。请设置 TAVILY_API_KEY 环境变量。\n"
            "获取免费 API Key: https://tavily.com (1000次/月)\n"
            f"当前查询: {query}"
        )

    try:
        result = _tavily_search(query, api_key)
        return _format_search_results(result)
    except Exception as e:
        logger.error(f"[Tool] search_web 失败: {e}")
        return f"联网搜索失败: {str(e)}"


def _get_search_api_key() -> str:
    import os
    return (
        getattr(_config, "search_api_key", "") if _config else ""
    ) or os.getenv("TAVILY_API_KEY", "") or os.getenv("SEARCH_API_KEY", "")


def _tavily_search(query: str, api_key: str, max_results: int = 5) -> dict:
    """调用 Tavily Search API。"""
    import httpx
    resp = httpx.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": True,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


def _format_search_results(result: dict) -> str:
    """将 Tavily 搜索结果格式化为 LLM 可读的文本。"""
    lines = []

    # Tavily 的 AI 摘要
    answer = result.get("answer", "")
    if answer:
        lines.append(f"### 📝 搜索摘要\n{answer}\n")

    # 搜索结果
    results = result.get("results", [])
    if results:
        lines.append(f"### 🔗 搜索结果 ({len(results)} 条)\n")
        for i, r in enumerate(results, 1):
            title = r.get("title", "无标题")
            url = r.get("url", "")
            content = r.get("content", "")[:300]
            score = r.get("score", 0)
            lines.append(f"**{i}. [{title}]({url})** (相关度: {score:.0%})")
            lines.append(f"   {content}")
            lines.append("")

    if not answer and not results:
        return f"未找到与「{result.get('query', '')}」相关的搜索结果。"

    return "\n".join(lines)


# ============================================================
# Tool 3: 抓取 URL 内容
# ============================================================

@tool
def fetch_url(url: str) -> str:
    """
    【用途】抓取指定网页 URL 并提取为纯文本（前 8000 字符）。适用于用户提供链接、需要阅读在线文档/文章/代码时。

    【不要用】
    - 需要登录/认证的页面（会抓到登录页）
    - 大文件下载或 API 接口调用
    - 已知内容的页面（重复抓取）
    - 非 HTML/纯文本页面（PDF、视频等）

    【优先级】🟢 低 — 仅在 search_web 搜索结果需要深入阅读时使用。

    【参数】url: 完整的 HTTP/HTTPS URL。
    【限制】超时 15 秒，前 8000 字符，仅支持 HTML 和纯文本。
    """
    logger.info(f"[Tool] fetch_url: {url}")

    if not url.startswith(("http://", "https://")):
        return f"无效 URL: {url}（必须以 http:// 或 https:// 开头）"

    try:
        resp = httpx.get(
            url,
            headers={
                "User-Agent": "MakeItSpecific/2.0 (AI Agent; +https://github.com/yoiwerr/portal)"
            },
            timeout=15.0,
            follow_redirects=True,
        )
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            return f"不支持的内容类型: {content_type}。仅支持 HTML 和纯文本。"

        # 简单 HTML → 文本（不依赖 BeautifulSoup）
        text = _html_to_text(resp.text)
        if len(text) > 8000:
            text = text[:8000] + "\n\n... (内容过长，已截断)"

        return f"### 🌐 {url}\n\n{text}"

    except httpx.TimeoutException:
        return f"请求超时: {url}（15 秒）"
    except httpx.HTTPStatusError as e:
        return f"HTTP {e.response.status_code}: {url}"
    except Exception as e:
        return f"抓取失败: {str(e)}"


def _html_to_text(html: str) -> str:
    """简易 HTML → 纯文本（移除标签和脚本）。"""
    import re
    # 移除 script/style
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # 移除 HTML 标签
    text = re.sub(r'<[^>]+>', ' ', text)
    # 清理空白
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()[:8000]


# ============================================================
# Tool 4: 历史对话检索（保留 + 优化）
# ============================================================

@tool
def search_chat_history(query: str) -> str:
    """
    【用途】检索当前会话中与查询相关的历史对话记录。适用于用户提到之前说过的话、想参考之前的决策时。

    【不要用】
    - 用户第一次发言时（无历史可搜）
    - 查询与当前话题无关的历史时
    - 需要精确事实时（应优先用 search_knowledge_base）

    【优先级】🟢 低 — 仅在用户明确引用过去内容、或当前问题需要历史上下文时使用。

    【参数】query: 搜索关键词（当前为关键词匹配，后续升级为向量检索）。
    【注意】此工具依赖 Agent 主动调用。多轮对话时 execute_node 已自动注入上轮摘要，大部分情况不需要手动调用此工具。
    """
    logger.info(f"[Tool] search_chat_history: {query}")
    if _session_store is None or _session_id is None:
        return "（当前没有可检索的历史对话）"

    try:
        conversation = _session_store.get_conversation_text(_session_id)
        if not conversation:
            return "（当前会话暂无历史消息）"

        # 关键词过滤（Phase 2 可升级为向量检索）
        lines = conversation.split("\n")
        matched = []
        query_lower = query.lower()
        for line in lines:
            if query_lower in line.lower():
                matched.append(line)

        if matched:
            return "\n".join(matched[:15])
        return "（未找到相关历史对话）"
    except Exception as e:
        return f"历史对话检索失败: {str(e)}"


# ============================================================
# 统一导出
# ============================================================

ALL_TOOLS = [search_knowledge_base, search_web, search_chat_history, fetch_url]
