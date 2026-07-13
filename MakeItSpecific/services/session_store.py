"""
PostgreSQL 会话 + 消息 + 反馈持久化。

替代旧的 SQLite 实现。与 PGVector 共用同一个 PostgreSQL 实例。
所有方法为同步（psycopg 3 sync 模式），在 async 上下文中由 Agent 直接调用。

表:
  sessions — 会话元数据
  messages — 对话消息 (FK → sessions)
  feedback — 用户反馈 (👍👎)
"""

import json
import uuid
from datetime import datetime
from typing import Optional

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

import logging
logger = logging.getLogger(__name__)


class SessionStore:
    """会话、消息、反馈的 PostgreSQL 存储。"""

    def __init__(self, conn_string: str):
        """
        Args:
            conn_string: PostgreSQL 连接串 (与 PGVectorStore 共用同一个 PG 实例)
              格式: host=localhost port=5432 dbname=makeitspecific user=postgres password=xxx
        """
        self.conn_string = conn_string
        self._conn: Optional[psycopg.Connection] = None
        self._init_db()

    # ============================================================
    # 连接
    # ============================================================

    @property
    def conn(self):
        """懒加载连接。"""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self.conn_string, row_factory=dict_row)
        return self._conn

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()

    # ============================================================
    # 建表
    # ============================================================

    def _init_db(self):
        """创建 sessions / messages / feedback 表（如不存在）。"""
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id              TEXT PRIMARY KEY,
                module          TEXT NOT NULL DEFAULT 'auto',
                title           TEXT DEFAULT '',
                background      TEXT DEFAULT '',
                status          TEXT DEFAULT 'active',
                clarify_rounds  INTEGER DEFAULT 0,
                completeness    REAL DEFAULT 0.0,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS messages (
                id          SERIAL PRIMARY KEY,
                session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                msg_type    TEXT NOT NULL DEFAULT 'input',
                meta        JSONB DEFAULT '{}',
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id, created_at);

            CREATE TABLE IF NOT EXISTS feedback (
                id          SERIAL PRIMARY KEY,
                session_id  TEXT NOT NULL,
                message_id  INTEGER DEFAULT 0,
                rating      TEXT NOT NULL,
                comment     TEXT DEFAULT '',
                skill       TEXT DEFAULT '',
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_feedback_session
                ON feedback(session_id);
            CREATE INDEX IF NOT EXISTS idx_feedback_rating
                ON feedback(rating);
        """)
        self.conn.commit()
        cur.close()

    # ============================================================
    # 会话
    # ============================================================

    def create_session(
        self,
        module: str,
        title: str = "",
        background: str = ""
    ) -> str:
        """创建新会话，返回 session_id。"""
        session_id = f"sess_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO sessions (id, module, title, background) VALUES (%s, %s, %s, %s)",
            (session_id, module, title or "新对话", background)
        )
        self.conn.commit()
        cur.close()
        return session_id

    def get_session(self, session_id: str) -> Optional[dict]:
        """获取会话元数据。"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None

    def update_session(self, session_id: str, **kwargs):
        """更新会话字段。"""
        if not kwargs:
            return
        kwargs["updated_at"] = "NOW()"
        set_parts = []
        values = []
        for k, v in kwargs.items():
            if v == "NOW()":
                set_parts.append(f"{k} = NOW()")
            else:
                set_parts.append(f"{k} = %s")
                values.append(v)
        values.append(session_id)
        cur = self.conn.cursor()
        cur.execute(
            f"UPDATE sessions SET {', '.join(set_parts)} WHERE id = %s",
            values
        )
        self.conn.commit()
        cur.close()

    def list_sessions(
        self, module: str = None, limit: int = 20
    ) -> list[dict]:
        """列出最近的会话。"""
        cur = self.conn.cursor()
        if module:
            cur.execute(
                "SELECT * FROM sessions WHERE module = %s ORDER BY updated_at DESC LIMIT %s",
                (module, limit)
            )
        else:
            cur.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT %s",
                (limit,)
            )
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]

    def delete_session(self, session_id: str):
        """删除会话及关联消息（CASCADE）。"""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
        self.conn.commit()
        cur.close()

    # ============================================================
    # 消息
    # ============================================================

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        msg_type: str,
        meta: dict = None
    ) -> int:
        """保存一条消息，返回消息 ID。"""
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO messages (session_id, role, content, msg_type, meta) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (session_id, role, content, msg_type,
             json.dumps(meta or {}, ensure_ascii=False))
        )
        msg_id = cur.fetchone()["id"]
        cur.execute(
            "UPDATE sessions SET updated_at = NOW() WHERE id = %s",
            (session_id,)
        )
        self.conn.commit()
        cur.close()
        return msg_id

    def get_conversation(self, session_id: str) -> list[dict]:
        """获取会话的完整对话历史。"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM messages WHERE session_id = %s ORDER BY created_at ASC",
            (session_id,)
        )
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]

    def get_conversation_text(self, session_id: str) -> str:
        """获取格式化对话文本，用于注入 LLM 上下文。"""
        messages = self.get_conversation(session_id)
        lines = []
        for msg in messages:
            role_label = {"user": "👤 用户", "assistant": "🤖 AI", "system": "⚙ 系统"}
            label = role_label.get(msg["role"], msg["role"])
            lines.append(f"### {label}\n{msg['content']}\n")
        return "\n".join(lines)

    # ============================================================
    # 反馈
    # ============================================================

    def save_feedback(
        self,
        session_id: str,
        rating: str,
        message_id: int = 0,
        comment: str = "",
        skill: str = "",
    ):
        """保存一条用户反馈。"""
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO feedback (session_id, message_id, rating, comment, skill) "
            "VALUES (%s, %s, %s, %s, %s)",
            (session_id, message_id, rating, comment or "", skill)
        )
        self.conn.commit()
        cur.close()

    def get_feedback_stats(self, skill: str = None) -> dict:
        """获取反馈统计。可选按 skill 过滤。"""
        cur = self.conn.cursor()

        if skill:
            cur.execute(
                "SELECT rating, COUNT(*) as count FROM feedback "
                "WHERE skill = %s GROUP BY rating",
                (skill,)
            )
        else:
            cur.execute(
                "SELECT rating, COUNT(*) as count FROM feedback GROUP BY rating"
            )
        rows = cur.fetchall()

        cur.execute(
            "SELECT skill, rating, COUNT(*) as count FROM feedback "
            "GROUP BY skill, rating ORDER BY skill"
        )
        skill_rows = cur.fetchall()
        cur.close()

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
