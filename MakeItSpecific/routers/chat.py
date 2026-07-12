"""
聊天对话接口。

POST /api/chat/stream       — V1 兼容模式 (SSE: session → thinking → clarify/execute → done)
POST /api/chat/stream/v2    — V2 Token 级流式 (SSE: session → token* → tool_start/tool_end* → clarify/execute → done)

V2 模式使用 astream_events() 实现真正的 token 级流式输出，
用户可以看到 AI 逐字生成文本，以及实时的工具调用状态。
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Query
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
# V1: 兼容模式（保持向后兼容）
# ============================================================

async def _stream_chat_v1(request: ChatRequest):
    """
    SSE 生成器 — V1 兼容模式。
    事件流: session → thinking → clarify/execute → done
    """
    if _agent is None:
        yield {"event": "error", "data": json.dumps({"detail": "Agent 未初始化"})}
        return

    session_id = request.session_id or "new"
    yield {
        "event": "session",
        "data": json.dumps({"session_id": session_id, "scenario": request.module})
    }

    yield {
        "event": "thinking",
        "data": json.dumps({"content": "正在分析你的需求..."})
    }

    try:
        result = await _agent.process_message(
            message=request.message,
            module=request.module,
            background=request.background or "",
            session_id=request.session_id,
            clarify_round=request.clarify_round,
            dimensions=request.dimensions or {},
            extra_context=request.extra_context or "",
        )
    except Exception as e:
        logger.error(f"[Chat V1] 处理失败: {e}", exc_info=True)
        yield {
            "event": "error",
            "data": json.dumps({"detail": f"处理消息失败: {str(e)}"})
        }
        return

    if result["type"] == "clarify":
        yield {
            "event": "clarify",
            "data": json.dumps({
                "type": "clarify",
                "progress": result["state_update"]["dimensions"].get("_completeness", 0),
                "scenario": request.module,
                "message": result["message"],
            })
        }
    else:
        yield {
            "event": "execute",
            "data": json.dumps({
                "type": "execute",
                "skill": request.module,
                "scenario": request.module,
                "message": result["message"],
            })
        }

    yield {
        "event": "done",
        "data": json.dumps({
            "session_id": result["session_id"],
            "message_id": 0,
        })
    }


# ============================================================
# V2: Token 级流式（新）
# ============================================================

async def _stream_chat_v2(request: ChatRequest):
    """
    SSE 生成器 — V2 Token 级流式。
    使用 astream_events() 实现：
      - 每个 LLM token 即时推送到前端
      - 工具调用开始/结束时发送 tool_start/tool_end
      - Agent 完成时发送 clarify/execute + done
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
                "data": json.dumps(data, ensure_ascii=False),
            }

    except Exception as e:
        logger.error(f"[Chat V2] 流式处理失败: {e}", exc_info=True)
        yield {
            "event": "error",
            "data": json.dumps({"detail": f"处理消息失败: {str(e)}"})
        }


# ============================================================
# 路由
# ============================================================

@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    v: Optional[str] = Query(default=None, alias="v", description="API 版本: 不传=V1, v=2=V2 token流式"),
):
    """
    核心对话入口 — 双模式支持。

    V1 (默认): POST /api/chat/stream
      - 兼容旧版前端，等 Agent 跑完一次性吐出

    V2 (新): POST /api/chat/stream?v=2
      - Token 级流式，每个 token 实时推送
      - 支持 tool_start / tool_end 事件

    用法:
      # V1 兼容模式
      curl -X POST http://localhost:8000/api/chat/stream \\
        -H "Content-Type: application/json" \\
        -d '{"message":"我想用React写个博客", "module":"work_arranger"}'

      # V2 Token 流式
      curl -X POST "http://localhost:8000/api/chat/stream?v=2" \\
        -H "Content-Type: application/json" \\
        -d '{"message":"帮我写一个提示词，生成产品文案", "module":"prompt_refiner"}'
    """
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent 未初始化，请等待服务启动完成")

    if v == "2":
        return EventSourceResponse(_stream_chat_v2(request))
    else:
        return EventSourceResponse(_stream_chat_v1(request))
