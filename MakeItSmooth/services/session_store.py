"""
SQLite 会话和消息持久化。
存储每轮对话，支持历史会话加载和导出。
"""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional


class SessionStore:
    """会话和消息的 SQLite 存储。"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    # ============================================================
    # 数据库初始化
    # ============================================================

    def _get_conn(self) -> sqlite3.Connection:
        """每个线程获取独立连接。"""
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        # 使用 DELETE 模式而非 WAL（WSL 网络文件系统兼容性更好）
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id              TEXT PRIMARY KEY,
                module          TEXT NOT NULL,
                title           TEXT DEFAULT '',
                background      TEXT DEFAULT '',
                status          TEXT DEFAULT 'active',
                clarify_rounds  INTEGER DEFAULT 0,
                completeness    REAL DEFAULT 0.0,
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                msg_type    TEXT NOT NULL,
                meta        TEXT DEFAULT '{}',
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id, created_at);
        """)
        conn.commit()
        conn.close()

    # ============================================================
    # 会话操作
    # ============================================================

    def create_session(
        self,
        module: str,
        title: str = "",
        background: str = ""
    ) -> str:
        """创建新会话，返回 session_id。"""
        session_id = f"sess_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO sessions (id, module, title, background) VALUES (?, ?, ?, ?)",
            (session_id, module, title or "新对话", background)
        )
        conn.commit()
        conn.close()
        return session_id

    def get_session(self, session_id: str) -> Optional[dict]:
        """获取会话元数据。"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_session(
        self,
        session_id: str,
        **kwargs
    ):
        """更新会话字段。"""
        if not kwargs:
            return
        kwargs["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [session_id]
        conn = self._get_conn()
        conn.execute(
            f"UPDATE sessions SET {set_clause} WHERE id = ?", values
        )
        conn.commit()
        conn.close()

    def list_sessions(
        self, module: str = None, limit: int = 20
    ) -> list[dict]:
        """列出最近的会话。"""
        conn = self._get_conn()
        if module:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE module = ? ORDER BY updated_at DESC LIMIT ?",
                (module, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def delete_session(self, session_id: str):
        """删除会话及关联消息。"""
        conn = self._get_conn()
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()

    # ============================================================
    # 消息操作
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
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO messages (session_id, role, content, msg_type, meta) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, msg_type, json.dumps(meta or {}, ensure_ascii=False))
        )
        # 同步更新会话时间
        conn.execute(
            "UPDATE sessions SET updated_at = datetime('now') WHERE id = ?",
            (session_id,)
        )
        conn.commit()
        msg_id = cursor.lastrowid
        conn.close()
        return msg_id

    def get_conversation(self, session_id: str) -> list[dict]:
        """获取会话的完整对话历史。"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,)
        ).fetchall()
        conn.close()
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
