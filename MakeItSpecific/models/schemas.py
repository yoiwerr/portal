"""
MakeItSpecific Pydantic 请求/响应模型。

参照 ChatLab src/schemas.py 的结构，适配工作流增强领域。
V2: 新增 token 级 streaming 事件模型 + 工具调用事件。
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from enum import Enum


# ============================================================
# 对话请求
# ============================================================

class ChatRequest(BaseModel):
    """POST /api/chat/stream 请求体"""
    message: str = Field(..., description="用户输入的大白话")
    session_id: Optional[str] = Field(default=None, description="已有会话 ID，不传则新建")
    module: str = Field(
        default="auto",
        description="指定模块: auto(自动识别) | prompt_refiner | work_arranger | info_retention"
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
# Streaming 事件 (V2 — 真正的 token 级流式)
# ============================================================

class SSEEventType(str, Enum):
    """SSE 事件类型"""
    SESSION = "session"
    THINKING = "thinking"
    TOKEN = "token"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    CLARIFY = "clarify"
    EXECUTE = "execute"
    ERROR = "error"
    DONE = "done"


class SessionEvent(BaseModel):
    """SSE session 事件 — 首次连接时发送"""
    session_id: str
    module: str = ""
    model: str = ""


class ThinkingEvent(BaseModel):
    """SSE thinking 事件 — Agent 开始处理时发送"""
    content: str = "正在分析你的需求..."


class TokenEvent(BaseModel):
    """SSE token 事件 — 每个 LLM token 实时推送"""
    content: str
    token_index: int = 0


class ToolCallEvent(BaseModel):
    """SSE tool_start / tool_end 事件"""
    tool_name: str
    tool_input: Optional[dict] = None     # tool_start 时携带
    tool_output: Optional[str] = None     # tool_end 时携带
    duration_ms: Optional[float] = None   # 工具执行耗时


class ClarifyEvent(BaseModel):
    """SSE clarify 事件 — 需要追问时发送"""
    type: str = "clarify"
    progress: float = Field(..., description="信息完整度 0-1")
    module: str = ""
    message: str = ""
    questions: List[dict] = Field(default_factory=list)


class ExecuteEvent(BaseModel):
    """SSE execute 事件 — Skill 执行完成"""
    type: str = "execute"
    skill: str = ""
    module: str = ""
    message: str = ""
    tool_calls_made: int = 0


class ErrorEvent(BaseModel):
    """SSE error 事件"""
    detail: str
    code: str = "unknown"


class DoneEvent(BaseModel):
    """SSE done 事件 — 流结束"""
    session_id: str
    message_id: int = 0
    tokens_used: int = 0


# ============================================================
# 追问相关
# ============================================================

class Question(BaseModel):
    """单个追问"""
    id: str = Field(..., description="问题 ID，如 q_purpose")
    text: str = Field(..., description="追问文本")
    dimension: str = Field(..., description="对应的信息维度")
    hint: str = Field(default="", description="输入提示")


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


# ============================================================
# Agent State (LangGraph 用)
# ============================================================

class AgentPlan(BaseModel):
    """Planner 节点输出的执行计划"""
    goal: str = ""
    steps: List[str] = Field(default_factory=list)
    missing_info: List[str] = Field(default_factory=list)  # 需要追问的信息
    is_complete: bool = False                               # 信息是否足够执行
    completeness: float = 0.0                               # 完整度 0-1


class DimensionInfo(BaseModel):
    """LLM 提取的单个维度信息"""
    key: str
    value: Optional[str] = None
    confidence: float = 0.0


class ExtractionResult(BaseModel):
    """LLM 维度提取结果（替代正则）"""
    dimensions: List[DimensionInfo] = Field(default_factory=list)
    completeness: float = 0.0
    missing_required: List[str] = Field(default_factory=list)


# ============================================================
# 会话管理
# ============================================================

class SessionSummary(BaseModel):
    """会话摘要（列表用）"""
    id: str
    module: str = ""
    title: str = ""
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
    session_id: str
    message_id: int = 0
    rating: str = Field(..., description="positive | negative | neutral")
    comment: Optional[str] = Field(default=None)
    skill: str = ""


# ============================================================
# 健康检查
# ============================================================

class HealthResponse(BaseModel):
    """GET /api/health 响应"""
    status: str
    llm_available: bool
    provider: str = ""
    model: str = ""
    kb_stats: dict = Field(default_factory=dict)
