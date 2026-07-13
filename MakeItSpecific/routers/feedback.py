"""
反馈收集接口。

POST /api/feedback      — 用户对 AI 输出的评价
GET  /api/feedback/stats — 反馈统计

存储: PostgreSQL (通过 SessionStore)
"""

from fastapi import APIRouter, HTTPException

from models.schemas import FeedbackRequest

router = APIRouter(prefix="/api/feedback", tags=["Feedback"])

_agent = None


def set_agent(agent):
    global _agent
    _agent = agent


@router.post("")
async def submit_feedback(request: FeedbackRequest):
    """提交用户反馈。"""
    if _agent is None or _agent.sessions is None:
        raise HTTPException(status_code=503, detail="服务未初始化")

    _agent.sessions.save_feedback(
        session_id=request.session_id,
        message_id=request.message_id,
        rating=request.rating,
        comment=request.comment or "",
        skill=request.skill or "",
    )
    return {"ok": True, "rating": request.rating}


@router.get("/stats")
async def get_feedback_stats(skill: str = None):
    """获取反馈统计。可选按 skill 过滤。"""
    if _agent is None or _agent.sessions is None:
        raise HTTPException(status_code=503, detail="服务未初始化")

    return _agent.sessions.get_feedback_stats(skill=skill)
