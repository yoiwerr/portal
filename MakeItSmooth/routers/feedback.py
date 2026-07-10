"""
反馈收集接口。

POST /api/feedback — 用户对 AI 输出的评价
GET  /api/feedback/stats — 反馈统计
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from models.schemas import FeedbackRequest

router = APIRouter(prefix="/api/feedback", tags=["Feedback"])

_agent = None
_db_path = None


def set_agent(agent):
    global _agent, _db_path
    _agent = agent
    if agent and agent.config:
        _db_path = agent.config.db_path


def _init_feedback_table():
    """初始化反馈表（如果不存在）。"""
    if not _db_path:
        return None
    conn = sqlite3.connect(str(_db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            message_id INTEGER DEFAULT 0,
            rating TEXT NOT NULL,
            comment TEXT DEFAULT '',
            skill TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def _ensure_db():
    if not _db_path:
        raise HTTPException(status_code=503, detail="Agent 未初始化")
    _init_feedback_table()
    return _db_path


@router.post("")
async def submit_feedback(request: FeedbackRequest):
    """提交用户反馈。"""
    db_path = _ensure_db()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO feedback (session_id, message_id, rating, comment, skill) VALUES (?, ?, ?, ?, ?)",
        (request.session_id, request.message_id, request.rating, request.comment or "", request.skill)
    )
    conn.commit()
    conn.close()
    return {"ok": True, "rating": request.rating}


@router.get("/stats")
async def get_feedback_stats(skill: str = None):
    """获取反馈统计。可选按 skill 过滤。"""
    db_path = _ensure_db()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    if skill:
        rows = conn.execute(
            "SELECT rating, COUNT(*) as count FROM feedback WHERE skill = ? GROUP BY rating",
            (skill,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT rating, COUNT(*) as count FROM feedback GROUP BY rating"
        ).fetchall()

    # 按 skill 统计
    skill_rows = conn.execute(
        "SELECT skill, rating, COUNT(*) as count FROM feedback GROUP BY skill, rating ORDER BY skill"
    ).fetchall()

    conn.close()

    stats = {"positive": 0, "negative": 0, "neutral": 0}
    for r in rows:
        stats[r["rating"]] = r["count"]

    by_skill = {}
    for r in skill_rows:
        s = r["skill"]
        if s not in by_skill:
            by_skill[s] = {"positive": 0, "negative": 0, "neutral": 0}
        by_skill[s][r["rating"]] = r["count"]

    return {
        "total": sum(stats.values()),
        "by_rating": stats,
        "by_skill": by_skill,
    }
