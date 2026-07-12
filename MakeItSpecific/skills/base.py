"""
Skill 抽象基类。

参照 ChatLab 的 LangChain Agent 模式，同时保留原有的 ModuleContext。
所有 Skill 继承 BaseSkill，实现 execute() 方法。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SkillContext:
    """Skill 执行所需的完整上下文。由 Agent/Graph 组装后传入。"""

    original_message: str = ""              # 用户原始输入
    expressed_dimensions: dict = field(default_factory=dict)  # 已确认的维度信息
    background: str = ""                    # 用户背景
    rag_context: str = ""                   # RAG 检索结果
    extra_context: str = ""                 # 额外上下文（如加载的MD文件）
    completeness: float = 0.0               # 信息完整度


class BaseSkill(ABC):
    """
    Skill 基类。

    新 Skill 继承此基类，实现 execute() 方法即可。
    内部使用 LangChain Agent + Tools 模式调用 LLM。

    与 ChatLab skills/ 的对应关系：
      ChatLab: skill01_imitate.py → execute_imitate_skill(request)
      MakeItSpecific: prompt_refiner.py → PromptRefiner().execute(context, llm)
    """

    name: str = ""            # 唯一标识符
    label: str = ""           # 中文名称
    description: str = ""     # 一句话描述
    icon: str = "✨"          # 图标 emoji

    @abstractmethod
    async def execute(self, context: SkillContext, model) -> str:
        """
        执行 Skill 逻辑。

        Args:
            context: 完整上下文（原始消息、维度、RAG 结果等）
            model: LangChain 兼容的 ChatModel

        Returns:
            Markdown 格式的完整输出（直接展示给用户）
        """
        ...

    def get_input_placeholder(self) -> str:
        """获取输入框的占位文本。"""
        return "请描述你的需求..."

    def get_description_markdown(self) -> str:
        """获取模块说明（Markdown 格式）。"""
        return f"### {self.icon} {self.label}\n{self.description}"
