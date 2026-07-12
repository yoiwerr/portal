"""
Skill 3: 信息留存（Info Retention）

流程: 用户加载 MD 文件 → 注入上下文 → Agent 整理为结构化文档。

参照 ChatLab skill03_atmosphere.py 的 LangChain Agent 模式。
"""

from langchain.agents import create_agent
from langchain_core.messages import SystemMessage, HumanMessage

from skills.base import BaseSkill, SkillContext
from prompts.templates import format_expressed_dimensions
from prompts.system_prompts import INFO_RETENTION_SYSTEM
from tools.search import ALL_TOOLS


class InfoRetention(BaseSkill):
    """信息留存。"""

    name = "info_retention"
    label = "信息留存"
    description = (
        "将对话和知识整理为可复用的文档。"
        "支持加载 .md 文件作为上下文，输出结构化的整理文档，"
        "下次使用时可以直接加载继续工作。"
    )
    icon = "📁"

    async def execute(self, context: SkillContext, model) -> str:
        """
        使用 LangChain Agent 整理并生成留存文档。

        Agent 可以调用 search_chat_history 获取完整对话上下文，
        调用 search_knowledge_base 获取相关知识。
        """
        dims_text = format_expressed_dimensions(context.expressed_dimensions)

        user_prompt = f"""## 用户背景
{context.background or "（未填写背景信息）"}

## 留存需求
{context.original_message}

## 已确认的需求信息
{dims_text}

## 知识库参考
{context.rag_context or "（知识库中暂无相关知识）"}

## 额外上下文（从加载的文件中读取）
{context.extra_context or "（未加载额外上下文文件）"}

## 任务
请按照系统提示词中的格式要求，将以上信息整理为结构化文档。
包含核心信息摘要、详细内容、关键决策点、下次使用提示和时效性标注。"""

        agent = create_agent(
            model=model,
            tools=ALL_TOOLS,
            system_prompt=INFO_RETENTION_SYSTEM,
        )
        result = await agent.ainvoke({
            "messages": [SystemMessage(content=INFO_RETENTION_SYSTEM), HumanMessage(content=user_prompt)]
        })
        return result["messages"][-1].content

    def get_input_placeholder(self) -> str:
        return (
            "描述你想留存什么信息...\n"
            "例如：帮我把刚才关于 React 项目的讨论整理成文档，"
            "下次可以快速回顾关键决策"
        )
