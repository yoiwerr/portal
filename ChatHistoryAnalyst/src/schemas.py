# src/schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional


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

class EmotionResponse(BaseModel):
    """
    Skill 2: 情感分析的强制结构化输出规范
    大模型将严格按照此结构返回数据
    """
    emotion_score: int = Field(
        ...,
        description="情感得分，范围 0-100。0代表极其消极/愤怒，50代表中立，100代表极其积极/开心"
    )
    dominant_emotion: str = Field(
        ...,
        description="主导情感标签，例如：'焦虑'、'开心'、'冷漠'、'试探' 等，精简为几个字"
    )
    analysis_reasoning: str = Field(
        ...,
        description="基于聊天记录的详细分析推导过程，解释为什么给出上述得分和标签"
    )
class AtmosphereResponse(BaseModel):
    """
    Skill 3: 聊天气氛与沟通姿态分析的结构化输出
    """
    atmosphere_summary: str = Field(
        ...,
        description="对当前聊天气氛的整体简短总结，例如：'紧张僵持'、'单方面迎合'、'轻松暧昧'等"
    )
    power_dynamic: str = Field(
        ...,
        description="双方权力动态（Power Dynamic）深度分析。明确指出是否有哪一方过于迎合、软弱或处于劣势，并给出判断依据。"
    )
    actionable_suggestions: List[str] = Field(
        ...,
        description="给出的具体聊天建议列表，至少包含两点。例如如何改善卑微姿态、如何不卑不亢地夺回话语权等。"
    )


class FileUploadResponse(BaseModel):
    status: str
    message: str
    parsed_chats: List[ChatMessage] = []