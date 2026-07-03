"""
MakeItSmooth Pydantic 请求/响应模型。

参照 ChatLab src/schemas.py 的结构，适配工作流增强领域。
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


# ============================================================
# 对话请求
# ============================================================

class ChatRequest(BaseModel):
    """POST /api/chat/stream 请求体"""
    message: str = Field(..., description="用户输入的大白话")
    session_id: Optional[str] = Field(default=None, description="已有会话 ID，不传则新建")
    module: str = Field(
        default="prompt_refiner",
        description="指定模块: prompt_refiner | work_arranger | info_retention"
    )
    background: Optional[str] = Field(default="", description="用户背景信息")
    extra_context: Optional[str] = Field(default="", description="额外上下文（如加载的MD文件）")
    clarify_round: int = Field(default=0, description="当前追问轮数")
    dimensions: Optional[dict] = Field(default_factory=dict, description="累积的维度信息")


class ChatMessage(BaseModel):
    """单条对话消息"""
    role: str = Field(..., description="user | assistant | system")
    content: str = Field(..., description="消息内容")


# ============================================================
# 追问相关
# ============================================================

class Question(BaseModel):
    """单个追问"""
    id: str = Field(..., description="问题 ID，如 q_purpose")
    text: str = Field(..., description="追问文本")
    dimension: str = Field(..., description="对应的信息维度")
    hint: str = Field(default="", description="输入提示")


class ClarifyEvent(BaseModel):
    """SSE clarify 事件数据"""
    type: str = Field(default="clarify")
    progress: float = Field(..., description="信息完整度 0-1")
    scenario: str = Field(..., description="场景分类: coding | learning | content")
    questions: List[Question] = Field(default_factory=list)
    missing_dimensions: List[str] = Field(default_factory=list)


# ============================================================
# 执行相关
# ============================================================

class PromptVersion(BaseModel):
    """优化后的提示词版本"""
    version: str = Field(..., description="A / B / C")
    title: str = Field(..., description="版本名称")
    prompt: str = Field(..., description="优化后提示词全文")
    target_model: str = Field(default="", description="推荐模型")
    style: str = Field(default="", description="风格标签")
    why: str = Field(default="", description="推荐理由")


class ToolRecommendation(BaseModel):
    """工具推荐"""
    name: str
    url: str = ""
    reason: str = ""


class SkillResult(BaseModel):
    """所有 Skill 输出的统一格式"""
    skill_name: str = Field(..., description="skill 标识")
    summary: str = Field(default="", description="一句话总结")
    refined_prompts: List[PromptVersion] = Field(default_factory=list)
    project_plan: Optional[dict] = Field(default=None, description="结构化工作计划")
    tool_recommendations: List[ToolRecommendation] = Field(default_factory=list)
    next_suggestions: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, description="置信度 0-1")
    raw_output: str = Field(default="", description="原始 Markdown 输出（前端直接渲染）")


class ExecuteEvent(BaseModel):
    """SSE execute 事件数据"""
    type: str = Field(default="execute")
    skill: str = Field(..., description="执行的 skill 名称")
    scenario: str = Field(default="")
    summary: str = Field(default="")
    result: SkillResult = Field(default_factory=SkillResult)


# ============================================================
# SSE 事件
# ============================================================

class SSEEvent(BaseModel):
    """通用 SSE 事件"""
    event: str = Field(..., description="session | thinking | clarify | execute | done")
    data: dict = Field(default_factory=dict)


class SessionEvent(BaseModel):
    """SSE session 事件数据"""
    session_id: str
    scenario: str = ""


class ThinkingEvent(BaseModel):
    """SSE thinking 事件数据"""
    content: str


class DoneEvent(BaseModel):
    """SSE done 事件数据"""
    session_id: str
    message_id: int = 0


# ============================================================
# 会话管理
# ============================================================

class SessionSummary(BaseModel):
    """会话摘要（列表用）"""
    id: str
    module: str = ""
    title: str = ""
    scenario: str = ""
    status: str = ""
    clarify_rounds: int = 0
    completeness: float = 0.0
    message_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class SessionDetail(BaseModel):
    """会话详情"""
    session: SessionSummary
    messages: List[ChatMessage] = Field(default_factory=list)


# ============================================================
# 知识库
# ============================================================

class KnowledgeResult(BaseModel):
    """知识库搜索结果"""
    name: str
    url: str = ""
    description: str = ""
    relevance: float = 0.0


# ============================================================
# 反馈
# ============================================================

class FeedbackRequest(BaseModel):
    """POST /api/feedback 请求体"""
    message_id: int
    rating: str = Field(..., description="positive | negative | neutral")
    comment: Optional[str] = Field(default=None)


# ============================================================
# 健康检查
# ============================================================

class HealthResponse(BaseModel):
    """GET /api/health 响应"""
    status: str
    llm_available: bool
    model: str = ""
    kb_stats: dict = Field(default_factory=dict)
