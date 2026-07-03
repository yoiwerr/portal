"""
POST /api/chat/stream — 核心对话入口（SSE 流式）。

参照 ChatLab 的端点模式，但增加了 LangGraph 追问/执行决策流。
内部流程：
  1. 接收 ChatRequest
  2. 构建 AgentState
  3. 运行 LangGraph 图
  4. 通过 SSE 流式返回: session → thinking → clarify/execute → done
"""

import json
import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from models.schemas import ChatRequest

router = APIRouter(prefix="/api/chat", tags=["Chat"])

# Agent 实例由 app.py 在启动时注入
_agent = None


def set_agent(agent):
    """由 app.py 在启动时调用，注入 Agent 实例。"""
    global _agent
    _agent = agent


async def _stream_chat(request: ChatRequest):
    """
    SSE 生成器。按顺序发送事件：
      session → thinking → clarify/execute → done
    """
    if _agent is None:
        yield {"event": "error", "data": json.dumps({"detail": "Agent 未初始化"})}
        return

    # Event 1: session
    session_id = request.session_id or "new"
    yield {
        "event": "session",
        "data": json.dumps({"session_id": session_id, "scenario": request.module})
    }

    # Event 2: thinking
    yield {
        "event": "thinking",
        "data": json.dumps({"content": "正在分析你的需求..."})
    }
    await asyncio.sleep(0.3)

    # Event 3: 运行 Agent（内部调用 LangGraph 图）
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
        yield {
            "event": "error",
            "data": json.dumps({"detail": f"处理消息失败: {str(e)}"})
        }
        return

    # Event 4: clarify 或 execute
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

    # Event 5: done
    yield {
        "event": "done",
        "data": json.dumps({
            "session_id": result["session_id"],
            "message_id": 0,
        })
    }


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """
    核心对话入口。

    客户端发送 { message, session_id?, module? }
    服务端返回 SSE 流: session → thinking → clarify/execute → done

    用法:
      curl -X POST http://localhost:8000/api/chat/stream \
        -H "Content-Type: application/json" \
        -d '{"message":"我想用React写个博客"}'
    """
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    return EventSourceResponse(_stream_chat(request))
