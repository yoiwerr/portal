"""SessionStore 单元测试。"""

import tempfile
from pathlib import Path

from services.session_store import SessionStore


def test_create_and_get_session():
    """测试创建和获取会话。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)

        # 创建会话
        sid = store.create_session(
            module="prompt_refiner",
            title="测试会话",
            background="测试背景"
        )
        assert sid.startswith("sess_")

        # 获取会话
        session = store.get_session(sid)
        assert session is not None
        assert session["module"] == "prompt_refiner"
        assert session["title"] == "测试会话"


def test_save_and_get_messages():
    """测试消息存储和获取。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)

        sid = store.create_session(module="work_arranger")

        # 保存多条消息
        store.save_message(sid, "user", "你好", "input")
        store.save_message(sid, "assistant", "你好！有什么可以帮你的？", "clarify")
        store.save_message(sid, "user", "我需要做一个项目", "input")
        store.save_message(sid, "assistant", "好的，让我们来规划一下", "result")

        # 获取对话
        msgs = store.get_conversation(sid)
        assert len(msgs) == 4
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
        assert msgs[2]["content"] == "我需要做一个项目"


def test_list_sessions():
    """测试列出会话。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)

        store.create_session(module="prompt_refiner", title="S1")
        store.create_session(module="work_arranger", title="S2")

        sessions = store.list_sessions()
        assert len(sessions) == 2

        sessions = store.list_sessions(module="prompt_refiner")
        assert len(sessions) == 1
        assert sessions[0]["title"] == "S1"


def test_delete_session():
    """测试删除会话级联删除消息。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)

        sid = store.create_session(module="info_retention")
        store.save_message(sid, "user", "test", "input")
        assert len(store.get_conversation(sid)) == 1

        store.delete_session(sid)
        assert store.get_session(sid) is None
        assert len(store.get_conversation(sid)) == 0
