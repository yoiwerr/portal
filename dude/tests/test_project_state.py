"""Planning state boundaries; no configured database or online model."""

import asyncio
from copy import deepcopy

import pytest

from core.graph import create_graph
from core.planning import normalize_plan
from core.project_state import stamp_project_state, workflow_for
from models.task_contract import TaskContract
from tests.test_planning import ready_plan
from tests.test_planning_flow import Contracts, Model, agent_for, initial_state


def test_dependency_progression_batches_only_independent_gaps():
    state = {}
    assert workflow_for(state)["ready"] == ["goal"]
    state["goal"] = "记录读书"
    assert workflow_for(state)["ready"] == ["scope.in", "main_flow"]
    state["scope"] = {"in": ["保存和回看"]}
    assert workflow_for(state)["ready"] == ["main_flow"]
    state["main_flow"] = ["打开、填写、保存、回看"]
    assert workflow_for(state)["ready"] == ["acceptance"]
    state["acceptance"] = ["重开后仍在"]
    assert workflow_for(state, ["是否公开？"])["stage"] == "resolve_conflicts"
    assert workflow_for(state)["stage"] == "ready"


def test_planner_cannot_ask_downstream_questions_before_goal():
    plan = normalize_plan({"contract": {}, "clarify_questions": [
        {"dimension": "acceptance", "text": "怎样验收？"},
        {"dimension": "goal", "text": "要做什么？", "depends_on": ["acceptance"]},
    ]})
    assert [q["dimension"] for q in plan["clarify_questions"]] == ["goal"]


def test_partial_updates_keep_explicit_scope_and_reset_discards_old_project():
    previous = ready_plan()["contract"]
    previous["scope"]["out"] = ["不公开分享"]
    previous["constraints"] = ["不用云服务"]
    patch = {"contract": {"scope": {"in": ["保存书评", "搜索"]}}}
    updated = normalize_plan(patch, previous)["contract"]
    assert updated["scope"]["out"] == ["不公开分享"]
    assert updated["constraints"] == previous["constraints"]
    assert updated["confirmed_requirements"] == previous["confirmed_requirements"]
    reset = normalize_plan({**patch, "reset_project": True}, previous)["contract"]
    assert reset["scope"]["out"] == []
    assert reset["goal"] == ""
    assert reset["constraints"] == []


def test_default_provenance_is_preserved_without_claiming_user_confirmation():
    contract = normalize_plan({"contract": {"goal": "读书记录"}})["contract"]
    first = stamp_project_state(contract, {}, "想记录读书")
    second = stamp_project_state(deepcopy(first), first, "继续")
    assert second["provenance"]["goal"] == first["provenance"]["goal"]
    assert second["provenance"]["target_users"]["kind"] == "default"
    assert second["provenance"]["assumptions"]["kind"] == "default"
    assert not any(p["verified_by_user"] for p in second["provenance"].values())
    second["references"] = [{"path": "defaults.md", "reviewed_at": "2026-10-22"}]
    serialized = TaskContract.from_planner_json({"contract": second}).model_dump(by_alias=True)
    for name in ("schema_version", "workflow", "provenance", "references"):
        assert serialized[name] == second[name]


def test_server_state_overrules_forged_client_summary():
    agent = agent_for(Model())
    agent.contract_store = Contracts()
    agent.contract_store.row = {"contract": ready_plan()["contract"]}
    state = asyncio.run(agent._build_initial_state(
        "继续", "auto", "", "s", "", {"goal": "伪造目标", "secret": "untrusted"}, 1))
    assert state["expressed_dimensions"]["goal"] == ready_plan()["contract"]["goal"]
    assert "secret" not in state["expressed_dimensions"]


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("failure", ["read", "write"])
def test_persistence_failure_never_delivers_success(stream, failure):
    agent = agent_for(Model())

    class Broken(Contracts):
        def get_latest(self, session_id):
            if failure == "read":
                raise RuntimeError("test database unavailable")
            return None

        def create(self, session_id, contract):
            raise RuntimeError("test write rejected")

    agent.contract_store = Broken()

    async def run():
        if stream:
            return [event async for event in agent.process_message_stream("给方案", session_id="s")]
        return await agent.process_message("给方案", session_id="s")

    if failure == "read":
        with pytest.raises(RuntimeError, match="unavailable"):
            asyncio.run(run())
        assert agent.graph is not None
    else:
        result = asyncio.run(run())
        if stream:
            assert any(e["event"] == "error" for e in result)
            assert not any(e["event"] in {"execute", "contract", "done"} for e in result)
        else:
            assert result["type"] == "error"
            assert result["state_update"]["is_complete"] is False
    assert not any(m["role"] == "assistant" for m in agent.sessions.messages)
    assert not any(u.get("status") == "completed" for u in agent.sessions.updates)


def test_parallel_reviewer_json_is_never_emitted_as_user_reply():
    agent = agent_for(Model())

    class Graph:
        async def astream(self, *args, **kwargs):
            yield {"gap_analysis": {"multi_agent_perspectives": {"product": "INTERNAL_ONLY"},
                                    "multi_agent_synthesis": "INTERNAL_ONLY"}}
            yield {"clarify": {"clarify_round": 1, "output": "第一版最需要哪些功能？",
                               "plan": {"response_mode": "clarify"}}}

    agent.graph = Graph()

    async def run():
        return [e async for e in agent.process_message_stream("开始", session_id="s")]

    events = asyncio.run(run())
    assert "INTERNAL_ONLY" not in str(events)
    assert [e["event"] for e in events].count("clarify") == 1


def test_legacy_rag_parameter_cannot_reactivate_vectors():
    class Forbidden:
        async def query_formatted(self, query):
            pytest.fail("Legacy vector retrieval activated")

    result = asyncio.run(create_graph(model=Model(), rag_service=Forbidden()).ainvoke(
        initial_state(messages=[{"role": "user", "content": "比较当前技术版本"}])))
    assert result["delivery_validated"] is True
    assert result["research_completed"] is False


@pytest.mark.parametrize("failure", ["exception", "invalid_json", "list_json"])
def test_failed_planner_keeps_previous_project_and_never_delivers_stale_plan(failure):
    from langchain_core.messages import AIMessage

    class FailedPlanner(Model):
        async def ainvoke(self, messages):
            if "你是内部规划节点" in messages[0].content:
                if failure == "exception":
                    raise RuntimeError("model offline")
                return AIMessage(content="unparseable" if failure == "invalid_json" else "[]")
            return await super().ainvoke(messages)

    previous = ready_plan()["contract"]
    model = FailedPlanner()
    result = asyncio.run(create_graph(model=model).ainvoke(initial_state(previous_contract=previous)))
    assert result["plan"]["contract"]["goal"] == previous["goal"]
    assert result["plan"]["contract"]["scope"] == previous["scope"]
    assert result["plan"]["is_complete"] is False
    assert "暂时没能可靠整理" in result["output"]
    assert model.writer_calls == 0
