"""
Skill 2: 工作安排交流（Work Arranger）

流程: 用户输入工作需求 → 追问补全 → Agent 输出结构化工作计划。

使用 LangGraph prebuilt create_react_agent + 工具调用。
"""

from langgraph.prebuilt import create_react_agent
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
        使用 LangGraph ReAct Agent 生成结构化工作计划。

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

        tools = get_tools_for_skill(self.name)
        agent = create_react_agent(
            model=model.bind_tools(tools, parallel_tool_calls=True),
            tools=tools,
            prompt=WORK_ARRANGER_SYSTEM,
        )
        result = await agent.ainvoke({
            "messages": [SystemMessage(content=WORK_ARRANGER_SYSTEM), HumanMessage(content=user_prompt)]
        })
        output_messages = result.get("messages", [])
        for m in reversed(output_messages):
            if hasattr(m, "content") and m.content:
                return m.content
        return ""

    def get_input_placeholder(self) -> str:
        return (
            "描述你想做的项目或任务...\n"
            "例如：我想搭建一个个人博客，技术栈偏好 React + Node.js，"
            "大概一个月内完成，主要用来写技术文章"
        )
