# src/schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict


class ChatMessage(BaseModel):
    sender: str = Field(..., description="发送者名称")
    content: str = Field(..., description="文本内容")
    timestamp: str = Field(..., description="时间戳")


class AnalysisRequest(BaseModel):
    target_person: str = Field(..., description="目标分析对象名称")
    recent_chat: List[ChatMessage] = Field(..., description="近期的聊天记录列表")
    background_info: Optional[str] = Field(default=None, description="可选的补充背景信息")


class ImportRequest(BaseModel):
    format_type: str = Field(description="数据格式，必须是 'text' 或 'json'")
    text_data: Optional[str] = None
    json_data: Optional[List[dict]] = None
    target_person: str = Field(default="Unknown", description="分析目标对象名称")
    save_to_rag: bool = Field(default=False, description="是否存入长期记忆向量库")


# ══════════════════════════════════════════════════════════════
# Skill 2: 情感心理指数
# ══════════════════════════════════════════════════════════════

class EmotionIndices(BaseModel):
    """情感心理量化指数 — 替代旧的 EmotionResponse"""
    sincerity_index: int = Field(
        ..., ge=0, le=100,
        description="真诚指数 0-100。0=高度虚伪/套路化，100=高度真诚坦露"
    )
    sincerity_reasoning: str = Field(
        ...,
        description="真诚指数判断依据：语言一致性、自我暴露程度、承诺兑现线索等"
    )
    avoidance_index: int = Field(
        ..., ge=0, le=100,
        description="回避指数 0-100。0=正面回应，100=极度回避/已读不回"
    )
    avoidance_reasoning: str = Field(
        ...,
        description="回避指数判断依据：话题转移频率、敷衍回应占比、关键问题回答率"
    )
    cold_violence_index: int = Field(
        ..., ge=0, le=100,
        description="冷暴力指数 0-100。0=无冷暴力，100=重度冷暴力/完全情感冻结"
    )
    cold_violence_reasoning: str = Field(
        ...,
        description="冷暴力指数判断依据：沉默间隔、情感回应缺失度、刻意无视行为"
    )
    emotional_stability: int = Field(
        ..., ge=0, le=100,
        description="情绪稳定性 0-100。0=极度波动/反复无常，100=极其稳定/始终如一"
    )
    dominant_emotion: str = Field(
        ...,
        description="当前最突出的主导情绪标签，如'焦虑'、'开心'、'冷漠'、'试探'、'愤怒'等"
    )
    emotion_trajectory: str = Field(
        ...,
        description="近 N 条消息的情感变化趋势描述，如'持续升温'、'逐渐冷却'、'波动剧烈'等"
    )


# ══════════════════════════════════════════════════════════════
# Skill 3: 关系动力学
# ══════════════════════════════════════════════════════════════

class RelationProgress(BaseModel):
    """关系进度条 — 四个维度"""
    certainty: int = Field(
        ..., ge=0, le=100,
        description="确定性 0-100。关系定义是否清晰：0=完全不确定，100=明确定义"
    )
    ambiguity: int = Field(
        ..., ge=0, le=100,
        description="暧昧度 0-100。言行中暧昧信号强度：0=完全友谊，100=强烈暧昧"
    )
    closeness: int = Field(
        ..., ge=0, le=100,
        description="亲近度 0-100。情感距离：0=疏远/陌生，100=亲密无间"
    )
    possibility: int = Field(
        ..., ge=0, le=100,
        description="发展可能性 0-100。关系往前发展的概率：0=毫无可能，100=必然发展"
    )
    progress_summary: str = Field(
        ...,
        description="对当前关系进度的整体评述，1-2句话总结四个维度的综合判断"
    )


class ActionSuggestion(BaseModel):
    """行动建议卡片"""
    category: str = Field(
        ...,
        description="建议分类：'立即行动' / '长期策略' / '风险预警'"
    )
    priority: int = Field(
        ..., ge=1, le=5,
        description="优先级 1-5，1=最低，5=最高/最紧急"
    )
    suggestion: str = Field(
        ...,
        description="具体可执行的建议内容"
    )
    expected_effect: str = Field(
        ...,
        description="采取该建议后预期的效果或改善方向"
    )


class RelationDynamics(BaseModel):
    """关系动力学分析 — 替代旧的 AtmosphereResponse"""
    control_strength: Dict[str, int] = Field(
        ...,
        description="掌控力分配，如 {'target_person': 65, 'me': 35}，合为 100"
    )
    control_analysis: str = Field(
        ...,
        description="掌控力分析：谁主导话题、谁决定节奏、权力不对等的具体表现"
    )
    communication_posture: str = Field(
        ...,
        description="沟通姿态诊断：讨好型/指责型/超理性/打岔型/一致型（萨提亚模式）"
    )
    relation_progress: RelationProgress = Field(
        ...,
        description="关系进度条四个维度"
    )
    atmosphere_summary: str = Field(
        ...,
        description="当前聊天气氛的整体简短总结，如'紧张僵持'、'轻松暧昧'、'单方面迎合'等"
    )
    power_dynamic: str = Field(
        ...,
        description="双方权力动态深度分析，明确指出哪一方处于高位/低位及判断依据"
    )
    actionable_suggestions: List[ActionSuggestion] = Field(
        ...,
        description="按优先级排序的行动建议列表，至少 3 条，覆盖立即行动+长期策略+风险预警"
    )


# ══════════════════════════════════════════════════════════════
# 兼容 API
# ══════════════════════════════════════════════════════════════

class FileUploadResponse(BaseModel):
    status: str
    message: str
    parsed_chats: List[ChatMessage] = []
