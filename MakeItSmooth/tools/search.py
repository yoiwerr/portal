"""
MakeItSmooth Agent Tools — 信息检索。

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
    从本地知识库中检索与查询相关的领域知识。
    当需要推荐工具、提供最佳实践、查询技术选型建议时，调用此工具。
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
    联网搜索互联网获取最新信息。当本地知识库无法回答、或需要查询
    最新新闻/技术动态/实时数据时调用此工具。

    需要环境变量 TAVILY_API_KEY 或 SEARCH_API_KEY。
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
    抓取指定网页 URL 的内容并提取为纯文本。
    当用户提供链接、想阅读在线文档/文章/代码时调用此工具。

    限制: 仅抓取前 8000 字符，超时 15 秒。
    """
    logger.info(f"[Tool] fetch_url: {url}")

    if not url.startswith(("http://", "https://")):
        return f"无效 URL: {url}（必须以 http:// 或 https:// 开头）"

    try:
        resp = httpx.get(
            url,
            headers={
                "User-Agent": "MakeItSmooth/2.0 (AI Agent; +https://github.com/yoiwerr/portal)"
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
    检索当前会话中与查询相关的历史对话记录。
    当用户提到之前说过的话、想参考之前的决策时，调用此工具。
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
