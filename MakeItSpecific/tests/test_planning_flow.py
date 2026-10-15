"""Exercise real graph branches with a deterministic model, without DB/API keys."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from langchain_core.messages import AIMessage
from core.graph import _needs_reference_lookup, _parallel_gap_analysis, create_graph, route_after_planner
from core.agent import Agent
from tests.test_planning import VALID_PLAN, ready_plan


class Model:
    def __init__(self, plan=None, drafts=None, review=None, checkpoints=None):
        self.plan = plan or ready_plan()
        self.drafts = list(drafts or [VALID_PLAN])
        self.review = review or {"pass": True, "score": 8}
        self.writer_calls = 0
        self.checkpoints = list(checkpoints or [{"aligned": True, "score": 8}])
        self.checkpoint_calls = 0
        self.review_prompts = []
        self.writer_prompts = []

    def bind(self, **kwargs):
        return self

    def bind_tools(self, *args, **kwargs):
        raise AssertionError("Planning must not bind execution tools")

    async def ainvoke(self, messages):
        system = messages[0].content
        if "你是内部规划节点" in system:
            return AIMessage(content=json.dumps(self.plan, ensure_ascii=False))
        if "你是语义对齐审核员" in system:
            checkpoint = self.checkpoints[min(self.checkpoint_calls, len(self.checkpoints) - 1)]
            self.checkpoint_calls += 1
            return AIMessage(content=json.dumps(checkpoint))
        if "你审核整篇输出" in system:
            self.review_prompts.append(system)
            return AIMessage(content=json.dumps(self.review))
        if "你是方案撰写节点" in system:
            self.writer_prompts.append(system)
            draft = self.drafts[min(self.writer_calls, len(self.drafts) - 1)]
            self.writer_calls += 1
            return AIMessage(content=draft)
        raise AssertionError("Unexpected model invocation")


def initial_state(**changes):
    return {"messages": [{"role": "user", "content": "技术我不懂，按最简单的来"}],
            "module": "code_review", "clarify_round": 12, "plan": {}, "output": "",
            "reflection_count": 0, "checkpoint_retry_count": 0, "execute_round": 0,
            **changes}


def test_reference_lookup_only_for_time_sensitive_or_comparative_requests():
    assert not _needs_reference_lookup("我想记录自己读过的书")
    assert _needs_reference_lookup("现在选哪个版本，价格大概怎样？")
    assert _needs_reference_lookup("帮我比较这两个方案的优缺点")


def test_parallel_gap_analysis_merges_independent_roles_and_deduplicates_questions():
    class GapModel:
        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            return AIMessage(content=json.dumps({
                "questions": [{"dimension": "scope.in", "text": "第一版最不能少什么？", "depends_on": []}],
            }))

    state = initial_state(plan={
        "is_complete": False,
        "missing_fields": ["scope.in", "main_flow"],
        "blocking_questions": [],
        "clarify_questions": [],
        "contract": {},
    })
    result = asyncio.run(_parallel_gap_analysis(state, GapModel()))
    assert set(result["multi_agent_perspectives"]) == {"product", "operations"}
    assert len(result["plan"]["clarify_questions"]) == 1
    assert result["multi_agent_synthesis"]


def test_default_request_uses_single_plan_and_preserves_final_sections():
    model = Model(drafts=[VALID_PLAN + "\n" + "参考说明。" * 500 + "\n尾部验收标记"])
    result = asyncio.run(create_graph(model=model).ainvoke(initial_state()))
    assert result["module"] == "work_arranger"
    assert result["plan"]["response_mode"] == "plan"
    assert result["delivery_validated"] is True
    assert result["tool_results"] == []
    assert model.writer_calls == 1
    assert "尾部验收标记" in model.review_prompts[0]


def test_missing_core_still_clarifies_after_old_round_limit():
    raw = ready_plan()
    raw["contract"]["main_flow"] = []
    model = Model(plan=raw)
    result = asyncio.run(create_graph(model=model).ainvoke(initial_state()))
    assert result["clarify_round"] == 13
    assert "从打开到完成" in result["output"]
    assert model.writer_calls == 0
    assert route_after_planner(result) == "clarify"


def test_multiple_missing_fields_run_parallel_gap_review_before_one_question_batch():
    raw = ready_plan()
    raw["contract"]["scope"]["in"] = []
    raw["contract"]["main_flow"] = []
    raw["contract"]["acceptance"] = []
    raw["draft_outline"] = ["目标是个人读书记录", "先添加书名和感想", "保存后能够回看"]

    class GapFlowModel(Model):
        def __init__(self):
            super().__init__(plan=raw)
            self.gap_roles = []

        async def ainvoke(self, messages):
            system = messages[0].content
            if "你是内部规划节点" in system:
                return AIMessage(content=json.dumps(self.plan, ensure_ascii=False))
            if "你是 Alfred 内部的 product" in system:
                self.gap_roles.append("product")
            elif "你是 Alfred 内部的 operations" in system:
                self.gap_roles.append("operations")
            else:
                return await super().ainvoke(messages)
            return AIMessage(content=json.dumps({"questions": []}, ensure_ascii=False))

    model = GapFlowModel()
    graph = create_graph(model=model)

    async def trace():
        final = {}
        visited = []
        async for update in graph.astream(initial_state()):
            for name, state in update.items():
                visited.append(name)
                final.update(state)
        return visited, final

    visited, final = asyncio.run(trace())
    assert visited == ["router", "enrich", "rag", "planner", "gap_analysis", "clarify"]
    assert set(model.gap_roles) == {"product", "operations"}
    assert len(final["plan"]["clarify_questions"]) <= 3
    assert "先给你一个可以修改的理解轮廓" in final["output"]
    assert "个人读书记录" in final["output"]


def test_structural_failure_retries_complete_document_not_a_patch():
    model = Model(drafts=["只有概述，没有方案章节。", VALID_PLAN])
    result = asyncio.run(create_graph(model=model).ainvoke(initial_state()))
    assert result["delivery_validated"] is True
    assert model.writer_calls >= 2
    assert "必须修正的交付问题" in model.writer_prompts[-1]
    assert result["output"] == VALID_PLAN


def test_exhausted_quality_check_reports_failure_not_delivery():
    model = Model(review={"pass": False, "score": 3, "suggestions": ["验收遗漏核心流程"]})
    result = asyncio.run(create_graph(model=model).ainvoke(initial_state()))
    assert model.writer_calls == 3
    assert result["delivery_error"] is True
    assert result["delivery_validated"] is False
    assert result["plan"]["is_complete"] is False
    assert "未作为最终方案交付" in result["output"]


def test_single_technical_explanation_has_no_full_plan_requirement():
    model = Model(plan={"response_mode": "advice"}, drafts=["数据库就是保存记录的地方。个人小项目推荐少组件，后续需要多人访问再扩展。"])
    result = asyncio.run(create_graph(model=model).ainvoke(initial_state()))
    assert result["plan"]["response_mode"] == "advice"
    assert result["delivery_validated"] is True


class Sessions:
    def __init__(self):
        self.messages = []
        self.updates = []

    def save_message(self, **kwargs):
        self.messages.append(kwargs)

    def update_session(self, **kwargs):
        self.updates.append(kwargs)

    def get_conversation(self, session_id):
        return self.messages


class Context:
    async def build(self, **kwargs):
        return SimpleNamespace(enriched_query="", l1_raw="", l2_summary="", l3_facts="", last_turn_summary="", turn_count=1)

    async def update_after_turn(self, **kwargs):
        pass


def agent_for(model):
    agent = object.__new__(Agent)
    agent.sessions = Sessions()
    agent.contract_store = None
    agent.context_engine = Context()
    agent.session_memory = None
    agent.user_profile = None
    agent.config = SimpleNamespace(llm_model="offline-test")
    agent.graph = create_graph(model=model)
    return agent


def test_sse_failed_quality_never_sends_execute_or_completed_status():
    agent = agent_for(Model(review={"pass": False, "score": 2}))

    async def collect():
        return [event async for event in agent.process_message_stream("给最终方案", session_id="test-session")]

    events = asyncio.run(collect())
    assert any(event["event"] == "error" for event in events)
    assert not any(event["event"] == "execute" for event in events)
    assert all(update.get("status") != "completed" for update in agent.sessions.updates)


def test_nonstream_advice_does_not_complete_project_session():
    agent = agent_for(Model(plan={"response_mode": "advice"}, drafts=["推荐先做单体小项目，组件少，维护起来简单；以后规模增长时再考虑拆分。"] ))
    result = asyncio.run(agent.process_message("技术怎么选", session_id="test-session"))
    assert result["state_update"]["is_complete"] is False
    assert agent.sessions.updates[-1]["status"] == "active"


class Contracts:
    def __init__(self):
        self.row = None
        self.creates = 0
        self.updates = 0

    def get_latest(self, session_id):
        return self.row

    def create(self, session_id, contract):
        self.creates += 1
        self.row = {"contract_id": contract["contract_id"], "version": 1, "contract": dict(contract)}

    def update(self, contract_id, contract, increment_version=True):
        assert increment_version
        self.updates += 1
        contract["version"] = self.row["version"] + 1
        self.row = {"contract_id": contract_id, "version": contract["version"], "contract": dict(contract)}


def test_same_session_uses_versioned_drafts_and_passes_provenance_back_to_planner():
    raw = ready_plan()
    raw["contract"]["main_flow"] = []
    model = Model(plan=raw)
    agent = agent_for(model)
    agent.contract_store = Contracts()
    first = asyncio.run(agent.process_message("先记录书名和感想", session_id="test-session"))
    assert first["type"] == "clarify"
    first_id = agent.contract_store.row["contract_id"]
    state = asyncio.run(agent._build_initial_state(
        "按最简单的来", "auto", "", "test-session", "", {}, 1))
    assert state["previous_contract"]["assumptions"]
    assert state["previous_contract"]["confirmed_requirements"] == ["只有我自己使用"]
    model.plan = ready_plan()
    second = asyncio.run(agent.process_message("打开、保存、回看", session_id="test-session", clarify_round=1))
    assert second["state_update"]["is_complete"] is True
    assert agent.contract_store.creates == 1
    assert agent.contract_store.updates == 1
    assert agent.contract_store.row["contract_id"] == first_id
    assert agent.contract_store.row["version"] == 2
    assert agent.contract_store.row["contract"]["status"] == "completed"


def test_sse_success_sends_one_complete_plan_and_completed_status():
    agent = agent_for(Model())

    async def collect():
        return [event async for event in agent.process_message_stream("给方案", session_id="test-session")]

    events = asyncio.run(collect())
    deliveries = [event for event in events if event["event"] == "execute"]
    assert len(deliveries) == 1
    assert deliveries[0]["data"]["message"] == VALID_PLAN
    assert agent.sessions.updates[-1]["status"] == "completed"


@pytest.mark.parametrize("mode", ["plan", "clarify", "advice", "boundary"])
def test_actual_node_sequence_for_each_reply_mode(mode):
    raw = ready_plan()
    draft = VALID_PLAN
    if mode == "clarify":
        raw["contract"]["main_flow"] = []
    elif mode == "advice":
        raw = {"response_mode": "advice"}
        draft = "数据库就是保存记录的地方。个人小项目先选简单可靠的方案，能保存并回看记录，再考虑扩展。"
    elif mode == "boundary":
        raw = {"response_mode": "boundary", "contract": {"project_type": "existing"}}
        draft = "目前先支持从零规划新项目。已有项目改造需要另行整理现状、目标和验收，再交给编程助手实施。"
    model = Model(plan=raw, drafts=[draft])
    graph = create_graph(model=model)

    async def trace():
        return [name async for update in graph.astream(initial_state())
                for name in update]

    visited = asyncio.run(trace())
    common = ["router", "enrich", "rag", "planner"]
    expected = common + (["clarify"] if mode == "clarify" else ["execute", "checkpoint", "reflect"])
    assert visited == expected
    assert "engineering_check" not in graph.nodes
    assert "multi_agent" not in graph.nodes
    if mode == "clarify":
        assert model.writer_calls == model.checkpoint_calls == 0


def test_direction_retry_and_quality_retries_share_a_bounded_writer_path():
    model = Model(
        checkpoints=[{"aligned": False, "score": 2, "correction": "保持用户已确认的个人使用范围。"}],
        review={"pass": False, "score": 3, "suggestions": ["仍然缺少完整验收。"]},
    )
    graph = create_graph(model=model)

    async def trace():
        visited = []
        final = {}
        async for update in graph.astream(initial_state()):
            for name, state in update.items():
                visited.append(name)
                final.update(state)
        return visited, final

    visited, final = asyncio.run(trace())
    # Initial draft + one direction correction + two quality corrections.
    assert visited.count("execute") == model.writer_calls == 4
    assert model.checkpoint_calls == 1
    assert final["delivery_error"] is True
    assert final["delivery_validated"] is False
    assert final["plan"]["retry_reason"] == ""
    assert "保持用户已确认的个人使用范围" in model.writer_prompts[1]


def test_retrieved_reference_reaches_writer_without_legacy_execution_nodes():
    class Reference:
        def __init__(self):
            self.queries = []

        async def query_formatted(self, query):
            self.queries.append(query)
            return "来源：个人项目案例；优先少组件、持久化与备份。"

    reference = Reference()
    model = Model()
    result = asyncio.run(create_graph(model=model, rag_service=reference).ainvoke(
        initial_state(enriched_query="个人读书记录网站 技术推荐")
    ))
    assert reference.queries == ["个人读书记录网站 技术推荐"]
    assert "来源：个人项目案例" in model.writer_prompts[0]
    assert result["delivery_validated"] is True


def test_sse_progress_keeps_public_node_names_after_routing_cleanup():
    agent = agent_for(Model())

    async def collect():
        return [event async for event in agent.process_message_stream("给方案", session_id="test-session")]

    events = asyncio.run(collect())
    nodes = [event["data"]["node"] for event in events if event["event"] == "progress"]
    assert nodes == ["router", "rag", "planner", "execute", "checkpoint", "reflect"]
    assert len([event for event in events if event["event"] == "execute"]) == 1
    assert agent.sessions.updates[-1]["status"] == "completed"
