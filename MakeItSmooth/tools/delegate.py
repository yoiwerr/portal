"""
Multi-Agent Phase 1 — Task Delegate Tool。

delegate_task: 主 Agent 调此 tool spawn 一个独立的 ReAct 子 Agent，
              子 Agent 拿着搜索工具专注完成一个子任务，返回完整结果。

与 search_web 的区别:
  search_web → 返回搜索结果列表（原始数据, 主 Agent 自己分析）
  delegate_task → 返回一份经过思考和分析的完整报告

子 Agent 的工具集: search_kb + search_web + fetch_url (只搜不写)
子 Agent 不包含 delegate_task 自身 (防止递归 spawn)
子 Agent 上限 8 轮 tool call，60s 超时
"""

import asyncio
import logging
from datetime import datetime

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

# ── 模型引用（由 Agent 在初始化时注入）──
_model = None
_config = None


def set_delegate_model(model, config=None):
    global _model, _config
    _model = model
    _config = config


# ── 子 Agent 的 System Prompt ──

DELEGATE_SYSTEM_PROMPT = """你是 MakeItSmooth 的子 Agent。你被委托完成一个独立子任务。

## 你的工作方式
1. 你只负责当前分配给你的子任务，不要超范围
2. 先用 search_knowledge_base 搜本地知识库
3. 如果本地知识不够，用 search_web 联网搜索
4. 需要深入阅读某个网页时用 fetch_url
5. 综合所有信息后输出完整报告

## 输出要求
- 结构化 Markdown 格式
- 引用来源（URL 或知识库文件名）
- 如果信息有不确定性，标注 "（待验证）"
- 不要省略细节——你的输出是给主 Agent 进一步使用的原材料

## 约束
- 最多 8 轮工具调用
- 只输出最终结果，不要中间过程
- 不要猜测——不确定的就说不知道"""


@tool
async def delegate_task(task_description: str) -> str:
    """
    将一个子任务委托给独立的子 Agent 执行。

    适用场景:
    - 主 Agent 发现任务太复杂，当前上下文难以一次性完成
    - 需要深入调研某个主题（搜索 → 阅读 → 分析 → 总结）
    - 需要并行处理多个独立子任务（多次调用此工具，每次一个子任务）

    子 Agent 拥有搜索工具（search_knowledge_base / search_web / fetch_url），
    会自行搜索、阅读、分析后返回完整报告。

    参数:
    - task_description: 详细的子任务描述（越具体越好，子 Agent 只有这一个任务）

    返回:
    - 子 Agent 的完整分析报告（Markdown 格式）

    注意:
    - 子 Agent 没有 python_exec、没有文件写权限、不能再 spawn 子 Agent
    - 子 Agent 超时 60 秒，最多 8 轮工具调用
    """
    if _model is None:
        return "❌ delegate_task 不可用: LLM 模型未注入。请联系管理员。"

    task = task_description.strip()
    if len(task) < 20:
        return "❌ 任务描述太短（< 20 字符），请提供更详细的子任务描述。"

    started_at = datetime.now()
    logger.info(f"[Delegate] 开始子任务: {task[:100]}...")

    try:
        # ── 创建子 Agent ──
        from tools.search import search_knowledge_base, search_web, fetch_url
        from langgraph.prebuilt import create_react_agent

        sub_tools = [search_knowledge_base, search_web, fetch_url]

        sub_agent = create_react_agent(
            model=_model,
            tools=sub_tools,
            prompt=DELEGATE_SYSTEM_PROMPT,
        )

        # ── 执行 ──
        result = await asyncio.wait_for(
            sub_agent.ainvoke({
                "messages": [
                    SystemMessage(content=DELEGATE_SYSTEM_PROMPT),
                    HumanMessage(content=f"## 你的任务\n\n{task}"),
                ],
            }),
            timeout=60.0,
        )

        # ── 提取输出 ──
        output = ""
        for m in reversed(result.get("messages", [])):
            if hasattr(m, "content") and m.content and not hasattr(m, "tool_calls"):
                output = m.content
                break

        if not output:
            return "（子 Agent 完成但未产生文本输出）"

        elapsed = (datetime.now() - started_at).total_seconds()
        logger.info(
            f"[Delegate] 完成: {len(output)} 字符, 耗时 {elapsed:.1f}s"
        )

        return (
            f"### 📋 子任务执行报告\n"
            f"**任务**: {task[:200]}\n"
            f"**耗时**: {elapsed:.1f}s\n"
            f"**输出长度**: {len(output)} 字符\n\n"
            f"---\n\n"
            f"{output}"
        )

    except asyncio.TimeoutError:
        elapsed = (datetime.now() - started_at).total_seconds()
        logger.warning(f"[Delegate] 超时: {elapsed:.1f}s")
        return (
            f"### ⚠️ 子任务超时\n"
            f"**任务**: {task[:200]}\n"
            f"**超时**: 60 秒\n\n"
            f"子 Agent 未能在规定时间内完成。建议：\n"
            f"1. 缩小任务范围，拆分为更小的子任务\n"
            f"2. 手动搜索关键信息后重新提问"
        )

    except Exception as e:
        elapsed = (datetime.now() - started_at).total_seconds()
        logger.error(f"[Delegate] 失败 ({elapsed:.1f}s): {e}")
        return f"❌ 子任务执行失败 ({elapsed:.1f}s): {str(e)}"
