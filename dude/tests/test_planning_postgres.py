"""Opt-in integration test. Only a dedicated disposable database is allowed."""

import asyncio
import os
import uuid

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from core.planning import normalize_plan
from services.contract_store import ContractStore
from services.session_store import SessionStore
from tests.test_planning import ready_plan
from tests.test_planning_flow import Model, agent_for


def test_versioned_project_roundtrip_and_legacy_row_compatibility():
    connection = (os.getenv("DUDE_PLANNING_TEST_DATABASE_URL") or os.getenv("ALFRED_PLANNING_TEST_DATABASE_URL"))
    if not connection:
        pytest.skip("dedicated disposable PostgreSQL not supplied")
    if not conninfo_to_dict(connection).get("dbname", "").startswith("alfred_planning_test"):
        pytest.fail("refusing to write outside alfred_planning_test database")
    sessions, contracts = SessionStore(connection), ContractStore(connection)
    try:
        session_id = sessions.create_session(module="work_arranger")
        raw = ready_plan()
        raw["contract"]["main_flow"] = []
        model = Model(plan=raw)
        agent = agent_for(model)
        agent.sessions, agent.contract_store = sessions, contracts
        first = asyncio.run(agent.process_message("记录读书", session_id=session_id))
        assert first["type"] == "clarify"
        saved = contracts.get_latest(session_id)
        assert saved["contract"]["schema_version"] == 1
        assert saved["contract"]["provenance"]
        assert saved["contract"]["workflow"]["ready"] == ["main_flow"]
        model.plan = ready_plan()
        result = asyncio.run(agent.process_message("填写、保存、回看", session_id=session_id, clarify_round=1))
        assert result["state_update"]["is_complete"] is True
        history = contracts.get_history(session_id)
        assert [row["version"] for row in history] == [2, 1]
        assert {row["contract_id"] for row in history} == {saved["contract_id"]}
        assert history[0]["contract"]["workflow"]["stage"] == "delivered"
        assert history[1]["contract"]["workflow"]["stage"] != "delivered"
        assert sessions.get_conversation(session_id)[-1]["role"] == "assistant"

        # Existing rows need no column migration; missing JSON fields normalize.
        old_session = "legacy-" + uuid.uuid4().hex
        contracts.create(old_session, {"goal": "已有会话目标", "scope": {"in": ["保存"]}})
        legacy = contracts.get_latest(old_session)["contract"]
        normalized = normalize_plan({"contract": {"main_flow": ["打开、保存"]}}, legacy)
        assert normalized["contract"]["goal"] == "已有会话目标"
        assert normalized["contract"]["scope"]["in"] == ["保存"]
        contracts.close()
        reopened = ContractStore(connection)
        try:
            assert reopened.get_latest(session_id)["version"] == 2
        finally:
            reopened.close()
        with psycopg.connect(connection) as conn:
            assert conn.execute("SELECT count(*) FROM pg_extension WHERE extname='vector'").fetchone()[0] == 0
    finally:
        sessions.close()
        contracts.close()
