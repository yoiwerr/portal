"""
Skill 2: 工作安排交流（Work Arranger）

流程: 用户输入工作需求 → 追问补全 → Agent 输出结构化工作计划。

参照 ChatLab skill02_emotion.py 的 LangChain Agent 模式。
"""

from langchain.agents import create_agent
from langchain_core.messages import SystemMessage, HumanMessage

from skills.base import BaseSkill, SkillContext
from prompts.templates import format_expressed_dimensions
from prompts.system_prompts import WORK_ARRANGER_SYSTEM
from tools import get_tools_for_skill


class WorkArranger(BaseSkill):
    """工作安排规划。"""

    name = "work_arranger"
    label = "工作安排交流"
    description = (
        "把你的想法变成可执行的工作计划。"
        "通过追问了解项目全貌，输出包含阶段划分、任务清单、时间线、"
        "工具推荐的完整方案。"
    )
    icon = "📋"

    async def execute(self, context: SkillContext, model) -> str:
        """
        使用 LangChain Agent 生成结构化工作计划。

        Agent 可以调用 search_knowledge_base 获取项目管理最佳实践。
        """
        dims_text = format_expressed_dimensions(context.expressed_dimensions)

        user_prompt = f"""## 项目背景
{context.background or "（未填写背景信息）"}

## 工作需求
{context.original_message}

## 已确认的需求信息
{dims_text}

## 知识库参考
{context.rag_context or "（知识库中暂无相关知识）"}

## 任务
请按照系统提示词中的格式要求，生成完整的项目工作计划。
包含项目概述、阶段划分、任务清单、时间线、工具推荐、风险提示和下一步行动。"""

        agent = create_agent(
            model=model,
            tools=get_tools_for_skill(self.name),
            system_prompt=WORK_ARRANGER_SYSTEM,
        )
        result = await agent.ainvoke({
            "messages": [SystemMessage(content=WORK_ARRANGER_SYSTEM), HumanMessage(content=user_prompt)]
        })
        return result["messages"][-1].content

    def get_input_placeholder(self) -> str:
        return (
            "描述你想做的项目或任务...\n"
            "例如：我想搭建一个个人博客，技术栈偏好 React + Node.js，"
            "大概一个月内完成，主要用来写技术文章"
        )
