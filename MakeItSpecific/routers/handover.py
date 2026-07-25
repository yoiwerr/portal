"""
项目记忆导入 API。

POST /api/sessions/import — 上传项目记忆文件 (.md/.json)，解析后注入 L2 上下文
"""

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["Handover"])

# Agent 实例由 app.py 注入
_agent = None


def set_agent(agent):
    global _agent
    _agent = agent


# ============================================================
# 导入项目记忆
# ============================================================

@router.post("/import")
async def import_handover(
    file: UploadFile = File(...),
):
    """
    上传项目记忆文件（.md 或 .json），解析后注入为 L2 上下文。

    前端收到后将 context_text 作为 extra_context 传入下一次对话。
    """
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    # 读取文件
    try:
        raw = await file.read()
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gbk")
        except Exception:
            raise HTTPException(status_code=400, detail="无法解码文件，请使用 UTF-8 编码")

    if not text or len(text) < 20:
        raise HTTPException(status_code=400, detail="文件内容过短")

    # 解析
    from services.handover_service import HandoverService
    handover = HandoverService.parse_from_text(text)

    if not handover:
        raise HTTPException(status_code=400, detail="无法从文件中解析交接卡格式")

    # 转为上下文文本 → 注入 L2
    context_text = HandoverService.to_context_string(handover)

    # ── 将导入的项目记忆存入 context_engine 的 L2 运行状态 ──
    if _agent.context_engine:
        import_session_id = f"imported_{file.filename or 'unknown'}"
        existing = _agent.context_engine._running_summaries.get(import_session_id, "")
        imported_block = f"\n\n## 📥 导入的项目记忆\n{context_text}"
        _agent.context_engine._running_summaries[import_session_id] = (existing + imported_block)[:4000]

    logger.info(f"[Handover] 导入成功 → L2 上下文已注入")

    return JSONResponse(content={
        "ok": True,
        "handover": handover,
        "context_text": context_text,
        "format": "json" if file.filename and file.filename.endswith(".json") else "markdown",
        "filename": file.filename,
    })
