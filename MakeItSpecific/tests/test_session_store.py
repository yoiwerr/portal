"""SessionStore 单元测试 — PostgreSQL 版。

需要 PostgreSQL 运行中。未配置则跳过。
"""

import os
import pytest
psycopg = pytest.importorskip("psycopg", reason="psycopg 未安装")
from services.session_store import SessionStore


def _get_test_conn_string():
    return (
        f"host={os.getenv('DB_HOST', 'localhost')} "
        f"port={os.getenv('DB_PORT', '5432')} "
        f"dbname={os.getenv('DB_NAME', 'makeitspecific')} "
        f"user={os.getenv('DB_USER', 'postgres')} "
        f"password={os.getenv('PGSQLPASSWORD', '')}"
    )


def _pg_available():
    try:
        conn = psycopg.connect(_get_test_conn_string())
        conn.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _pg_available(), reason="PostgreSQL 不可用，跳过")
class TestSessionStorePG:

    def test_create_and_get_session(self):
        store = SessionStore(_get_test_conn_string())
        sid = store.create_session(module="prompt_refiner", title="测试")
        assert sid.startswith("sess_")
        session = store.get_session(sid)
        assert session is not None
        assert session["module"] == "prompt_refiner"
        store.delete_session(sid)
        store.close()

    def test_save_and_get_messages(self):
        store = SessionStore(_get_test_conn_string())
        sid = store.create_session(module="work_arranger")
        store.save_message(sid, "user", "你好", "input")
        store.save_message(sid, "assistant", "你好！", "clarify")
        msgs = store.get_conversation(sid)
        assert len(msgs) == 2
        store.delete_session(sid)
        store.close()

    def test_list_sessions(self):
        store = SessionStore(_get_test_conn_string())
        s1 = store.create_session(module="prompt_refiner", title="S1")
        s2 = store.create_session(module="work_arranger", title="S2")
        sessions = store.list_sessions()
        assert len(sessions) >= 2
        store.delete_session(s1)
        store.delete_session(s2)
        store.close()

    def test_delete_session_cascade(self):
        store = SessionStore(_get_test_conn_string())
        sid = store.create_session(module="info_retention")
        store.save_message(sid, "user", "test", "input")
        assert len(store.get_conversation(sid)) == 1
        store.delete_session(sid)
        assert store.get_session(sid) is None
        assert len(store.get_conversation(sid)) == 0
        store.close()

    def test_feedback(self):
        store = SessionStore(_get_test_conn_string())
        sid = store.create_session(module="code_review")
        store.save_feedback(session_id=sid, rating="negative", comment="no")
        stats = store.get_feedback_stats()
        assert stats["total"] >= 1
        store.delete_session(sid)
        store.close()
