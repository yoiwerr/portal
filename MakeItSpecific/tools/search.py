"""
MakeItSpecific Agent Tool — 知识库检索。

search_knowledge_base : PGVector 向量检索本地知识库。

这是唯一的检索入口。返回结构化 JSON，不是 Markdown 长文本 —
LLM 可以直接解析 source_file / score / content_snippet 做精准引用和幻觉检测。

与 passive RAG 注入的关系:
  - Planner/Executor System Prompt 中已有 query_formatted() 注入的 Markdown 上下文
  - search_knowledge_base tool 是主动检索 — 当被动注入不够或 Executor 需要查证细节时调用
  - 返回结构化 JSON，与注入的 Markdown 格式不同，用途不同
"""

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_rag_service = None


def set_tool_services(rag_service=None, **kwargs):
    global _rag_service
    _rag_service = rag_service


@tool
def search_knowledge_base(query: str) -> str:
    """
    【用途】从本地知识库 (PGVector) 向量检索领域知识，返回结构化 JSON。

    【什么时候用】
    - Executor 需要**精确引用**知识库内容时（需要 source_file 和 score）
    - 被动注入的 RAG 上下文不够具体，需要补充检索
    - 你需要验证一个技术细节在知识库中是否有记载
    - 用户要求 "查一下知识库里怎么说"

    【坚决不用】
    - 常识性问题 — 模型自身知识已足够（"Python 怎么读文件"）
    - 纯创意/头脑风暴 — 不需要检索事实
    - 用户明确说 "不要查资料"
    - 同一个 query 本轮已经检索过且结果还在上下文中 — 不要重复

    【什么时候用 vs 什么时候不用 — 决策树】
    - 问题涉及技术选型/最佳实践/方法论？→ 用
    - 问题很简单、你 100% 确定答案？→ 不用
    - 你不太确定、需要验证？→ 用
    - 上一轮已经搜过同一个 query 且拿到了结果？→ 不用

    【与其他 tool 的关系】
    - 与 add_to_knowledge_base: 读写分离。search_kb 只读不写，add_to_kb 只写不读。
      同一张 PGVector 表，操作方向相反 — 无重叠。
    - 与 python_exec: 无关。python_exec 不访问知识库。
    - 与 run_shell_preview: 无关。shell 操作文件系统，不访问知识库。

    【参数】query: 搜索查询。用关键词而非完整句子。中英混合最佳。
           例: "RAG 混合检索 rerank" / "prompt engineering CoT few-shot"
    【返回】JSON 字符串: {"hit": bool, "results": [{rank, source_file, content_snippet, score}, ...], "total_scanned": int}
           hit=false 时 results 为空数组 — 明确表示知识库无覆盖。
    """
    logger.info(f"[Tool] search_knowledge_base: {query}")
    if _rag_service is None:
        return json.dumps({
            "hit": False, "query": query, "results": [], "error": "知识库服务未初始化"
        }, ensure_ascii=False)

    try:
        data = _rag_service.query_structured(query, top_k=3)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[Tool] search_knowledge_base 失败: {e}")
        return json.dumps({
            "hit": False, "query": query, "results": [],
            "error": f"检索失败: {str(e)}"
        }, ensure_ascii=False)
