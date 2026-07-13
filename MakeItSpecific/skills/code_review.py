"""
Skill 4: 代码审查（Code Review）

流程: 用户指定文件/代码 → Agent 读取代码 (run_shell_preview) → 输出结构化审查报告。

轻量实现:
  - 不依赖 AST 解析或 linter
  - 用 run_shell_preview 读取目标文件
  - 用 search_knowledge_base 检索相关最佳实践
  - LLM 逐文件/逐区域分析，输出问题列表 + 改进建议
"""

from langchain.agents import create_agent
from langchain_core.messages import SystemMessage, HumanMessage

from skills.base import BaseSkill, SkillContext
from prompts.templates import format_expressed_dimensions
from prompts.system_prompts import CODE_REVIEW_SYSTEM
from tools import get_tools_for_skill


class CodeReview(BaseSkill):
    """代码审查。"""

    name = "code_review"
    label = "代码审查"
    description = (
        "审查代码质量，发现潜在问题。"
        "支持指定文件或目录，输出按严重程度排序的问题列表，"
        "附带改进建议和参考最佳实践。"
    )
    icon = "🔍"

    async def execute(self, context: SkillContext, model) -> str:
        """
        使用 LangChain Agent 审查代码。

        Agent 可以调用 run_shell_preview 读取代码文件，
        调用 search_knowledge_base 检索最佳实践。
        """
        dims_text = format_expressed_dimensions(context.expressed_dimensions)

        user_prompt = f"""## 用户背景
{context.background or "（未填写）"}

## 审查需求
{context.original_message}

## 已确认的需求信息
{dims_text}

## 知识库参考
{context.rag_context or "（知识库中暂无相关知识）"}

## 额外上下文
{context.extra_context or "（无）"}

## 任务
请按照系统提示词中的格式要求，完成代码审查。
如果用户指定了文件路径，先用 run_shell_preview 读取文件内容。
审查完成后输出结构化报告。"""

        agent = create_agent(
            model=model,
            tools=get_tools_for_skill(self.name),
            system_prompt=CODE_REVIEW_SYSTEM,
        )
        result = await agent.ainvoke({
            "messages": [SystemMessage(content=CODE_REVIEW_SYSTEM), HumanMessage(content=user_prompt)]
        })
        return result["messages"][-1].content

    def get_input_placeholder(self) -> str:
        return (
            "描述你想审查的代码...\n"
            "例如：帮我审查一下 main.py 的代码质量，重点关注错误处理和安全性"
        )
