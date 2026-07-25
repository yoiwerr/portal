"""
聊天对话接口。

POST /api/chat/message — SSE 进度流式（节点级，非 token 级）
  事件: session → progress* → contract → clarify/execute → done
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from models.schemas import ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["Chat"])

# Agent 实例由 app.py 在启动时注入
_agent = None


def set_agent(agent):
    """由 app.py 在启动时调用，注入 Agent 实例。"""
    global _agent
    _agent = agent


# ============================================================
# 核心对话 — SSE 进度流式
# ============================================================

async def _stream_progress(request: ChatRequest):
    """
    SSE 生成器 — 节点级进度。
    在每个 graph 节点完成后推送 progress 事件，不做 token 流式。
    """
    if _agent is None:
        yield {"event": "error", "data": json.dumps({"detail": "Agent 未初始化"})}
        return

    try:
        async for sse_event in _agent.process_message_stream(
            message=request.message,
            module=request.module,
            background=request.background or "",
            session_id=request.session_id,
            clarify_round=request.clarify_round,
            dimensions=request.dimensions or {},
            extra_context=request.extra_context or "",
        ):
            event_type = sse_event.get("event", "unknown")
            data = sse_event.get("data", {})

            yield {
                "event": event_type,
                "data": json.dumps(data, ensure_ascii=False, default=str),
            }

    except Exception as e:
        logger.error(f"[Chat] 处理失败: {e}", exc_info=True)
        yield {
            "event": "error",
            "data": json.dumps({"detail": f"处理消息失败: {str(e)}"}),
        }


@router.post("/message")
async def chat_message(request: ChatRequest):
    """
    发送消息 → SSE 进度流式返回。

    事件序列:
      session   — 会话 ID + 模块
      progress  — 每完成一个 graph 节点推送一次 {node, label}
      contract  — 任务契约（如有）
      clarify   — 需追问时的消息
      execute   — 完成执行时的消息
      done      — 结束标记
    """
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent 未初始化，请等待服务启动完成")

    return EventSourceResponse(_stream_progress(request))


# ============================================================
# 任务契约操作
# ============================================================

@router.post("/{session_id}/contract/confirm")
async def confirm_contract(session_id: str):
    """用户确认任务契约。更新 contract_store 状态为 confirmed。"""
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent 未初始化")
    if not _agent.contract_store:
        raise HTTPException(status_code=501, detail="ContractStore 未启用")
    row = _agent.contract_store.get_latest(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="当前会话没有契约")
    contract_id = row["contract_id"]
    confirmed = _agent.contract_store.confirm(contract_id, row["contract"])
    return JSONResponse(content={"ok": True, "contract": confirmed})


@router.post("/{session_id}/contract/update")
async def update_contract(session_id: str, request: Request):
    """用户修改契约字段（增量更新）。"""
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent 未初始化")
    if not _agent.contract_store:
        raise HTTPException(status_code=501, detail="ContractStore 未启用")
    body = await request.json()
    row = _agent.contract_store.get_latest(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="当前会话没有契约")
    contract, contract_id = row["contract"], row["contract_id"]
    for f in ["goal", "confidence", "status"]:
        if f in body:
            contract[f] = body[f]
    if "scope" in body and isinstance(body["scope"], dict):
        contract.setdefault("scope", {})
        if "in" in body["scope"]:
            contract["scope"]["in"] = body["scope"]["in"]
        if "out" in body["scope"]:
            contract["scope"]["out"] = body["scope"]["out"]
    for lf in ["constraints", "acceptance", "risks"]:
        if lf in body:
            contract[lf] = body[lf]
    if "deliverables" in body:
        contract["deliverables"] = body["deliverables"]
    if "permissions" in body:
        contract["permissions"] = body["permissions"]
    contract["status"] = "draft"
    _agent.contract_store.update(contract_id, contract, increment_version=True)
    return JSONResponse(content={"ok": True, "contract": contract})


@router.get("/{session_id}/contract")
async def get_contract(session_id: str):
    """获取当前会话契约（用于页面恢复）。"""
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent 未初始化")
    if not _agent.contract_store:
        raise HTTPException(status_code=501, detail="ContractStore 未启用")
    row = _agent.contract_store.get_latest(session_id)
    return JSONResponse(content={"ok": True, "contract": row["contract"] if row else None})
