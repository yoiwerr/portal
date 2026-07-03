"""
Skill 1: 提示词工程（Prompt Refiner）

流程: 用户输入白话 → 追问补全 → Agent 生成 2-3 个优化版本。

参照 ChatLab skill01_imitate.py 的 LangChain Agent 模式。
使用 create_agent + ALL_TOOLS 实现。
"""

from langchain.agents import create_agent
from langchain_core.messages import SystemMessage, HumanMessage

from skills.base import BaseSkill, SkillContext
from prompts.templates import format_expressed_dimensions
from prompts.system_prompts import PROMPT_REFINER_SYSTEM
from tools.search import ALL_TOOLS


class PromptRefiner(BaseSkill):
    """提示词精炼师。"""

    name = "prompt_refiner"
    label = "提示词工程"
    description = (
        "把你的大白话变成高质量 AI 提示词。"
        "通过引导式对话了解你的真实需求，生成 2-3 个不同策略的优化版本。"
    )
    icon = "✨"

    async def execute(self, context: SkillContext, model) -> str:
        """
        使用 LangChain Agent 生成优化后的提示词。

        Agent 可以调用 search_knowledge_base 获取提示词最佳实践，
        也可以调用 search_chat_history 参考历史偏好。
        """
        dims_text = format_expressed_dimensions(context.expressed_dimensions)

        user_prompt = f"""## 用户背景
{context.background or "（未填写背景信息）"}

## 原始提示词/需求
{context.original_message}

## 已确认的需求信息
{dims_text}

## 知识库参考
{context.rag_context or "（知识库中暂无相关知识）"}

## 任务
请按照系统提示词中的格式要求，生成 2-3 个优化后的提示词版本。
每个版本标注策略、推荐模型、风格和推荐理由。"""

        agent = create_agent(
            model=model,
            tools=ALL_TOOLS,
            system_prompt=PROMPT_REFINER_SYSTEM,
        )
        result = await agent.ainvoke({
            "messages": [SystemMessage(content=PROMPT_REFINER_SYSTEM), HumanMessage(content=user_prompt)]
        })
        return result["messages"][-1].content

    def get_input_placeholder(self) -> str:
        return (
            "用大白话描述你想用 AI 做什么...\n"
            "例如：我想写一个提示词，让 AI 帮我生成产品文案，"
            "受众是年轻消费者，风格要活泼有趣"
        )
