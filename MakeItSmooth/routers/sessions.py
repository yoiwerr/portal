"""
会话管理接口。

GET  /api/sessions        — 历史会话列表
GET  /api/sessions/{id}   — 会话详情
DELETE /api/sessions/{id} — 删除会话
"""

from fastapi import APIRouter, HTTPException

from models.schemas import SessionSummary, SessionDetail, ChatMessage

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])

_agent = None


def set_agent(agent):
    global _agent
    _agent = agent


@router.get("")
async def list_sessions(module: str = None):
    """获取历史会话列表。可选按 module 过滤。"""
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    sessions = _agent.list_sessions(module=module)
    result = []
    for s in sessions:
        msg_count = len(_agent.sessions.get_conversation(s["id"]))
        result.append(SessionSummary(
            id=s["id"],
            module=s.get("module", ""),
            title=s.get("title", ""),
            status=s.get("status", ""),
            clarify_rounds=s.get("clarify_rounds", 0),
            completeness=s.get("completeness", 0.0),
            message_count=msg_count,
            created_at=s.get("created_at", ""),
            updated_at=s.get("updated_at", ""),
        ))
    return {"sessions": result}


@router.get("/{session_id}")
async def get_session(session_id: str):
    """获取会话详情（完整消息历史）。"""
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    session = _agent.sessions.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    msgs = _agent.sessions.get_conversation(session_id)
    messages = [
        ChatMessage(role=m["role"], content=m["content"])
        for m in msgs
    ]

    summary = SessionSummary(
        id=session["id"],
        module=session.get("module", ""),
        title=session.get("title", ""),
        status=session.get("status", ""),
        clarify_rounds=session.get("clarify_rounds", 0),
        completeness=session.get("completeness", 0.0),
        message_count=len(messages),
        created_at=session.get("created_at", ""),
        updated_at=session.get("updated_at", ""),
    )

    return SessionDetail(session=summary, messages=messages)


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """删除会话及关联消息。"""
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    session = _agent.sessions.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    _agent.sessions.delete_session(session_id)
    return {"ok": True, "deleted": session_id}
