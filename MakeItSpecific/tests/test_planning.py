"""Core readiness, provenance and text-only delivery regression cases."""

from core.planning import normalize_plan, validate_output
from models.task_contract import TaskContract


VALID_PLAN = """# 个人读书记录项目方案

## 1. 目标与使用场景
只有用户自己使用，记录读过的书和感想，方便以后回看。

## 2. 第一版范围
添加书名和感想、保存、列表回看。推荐以后再做评分统计，不删减明确要求。

## 3. 页面与操作流程
打开书单，添加书名和感想，保存后回到列表。无内容显示引导，失败保留输入。

## 4. 技术方案与理由
推荐简单网页和单体后端，少组件容易维护。相比纯本地页面可跨设备访问，但需要服务器费用。

## 5. 数据与权限
书名、感想和记录时间持久化保存，归属个人账号。只有本人能读取和修改。

## 6. 分阶段实施
先实现保存和列表并验证重新打开仍有内容，再补权限检查，最后验证完整访问流程。

## 7. 部署、安全与备份
先在本地验证，再部署长期运行服务。正式访问使用 HTTPS，规划备份及临时恢复演练。

## 8. 成本与假设
小规模服务器和备份存储可能收费，费用以所选平台实际报价为准，不承诺免费。

## 9. 验收与报错处理
保存一本书后重新打开能看到感想。其他人无法读取。出错交给编程 Agent 收集脱敏信息、定位、修复并回归验证。

## 10. 已确认、默认与待定
### 已确认要求
个人使用，保存书名和感想，能回看。
### 默认假设
按小规模和少组件规划，数据持久化；这些是推荐，用户未逐项指定技术。
### 待定事项
第一版无阻塞事项，统计功能待后续讨论。
"""


def ready_plan():
    return {
        "response_mode": "plan", "is_complete": False,
        "contract": {
            "goal": "个人读书记录", "target_users": "只有我自己",
            "scope": {"in": ["记录书名和感想", "回看"], "out": []},
            "main_flow": ["打开", "添加书名和感想", "保存", "回看"],
            "acceptance": ["重新打开记录仍在"],
            "constraints": ["数据不能丢失"],
            "confirmed_requirements": ["只有我自己使用"],
        },
        "missing_fields": ["tech_stack", "time_constraint", "deliverables"],
        "clarify_questions": [{"dimension": "tech_stack", "text": "想用什么框架？"}],
    }


def test_ready_core_uses_defaults_instead_of_technical_questionnaire():
    raw = ready_plan()
    plan = normalize_plan(raw)
    assert plan["is_complete"] is True
    assert plan["response_mode"] == "plan"
    assert plan["clarify_questions"] == []
    assert plan["contract"]["target_users"] == "只有我自己"
    assert plan["contract"]["constraints"] == ["数据不能丢失"]
    assert plan["contract"]["scope"]["in"] == raw["contract"]["scope"]["in"]
    assert plan["contract"]["scope"]["out"] == []
    assert plan["contract"]["confirmed_requirements"] == ["只有我自己使用"]
    assert plan["contract"]["assumptions"]
    assert raw["contract"].get("assumptions") is None


def test_missing_workflow_still_requires_clarification_even_with_high_score():
    raw = ready_plan()
    raw["contract"]["main_flow"] = []
    raw["contract"]["confidence"] = 1
    raw["is_complete"] = True
    plan = normalize_plan(raw)
    assert not plan["is_complete"]
    assert plan["clarify_questions"][0]["dimension"] == "main_flow"


def test_blocking_permissions_conflict_is_not_hidden_by_defaults():
    raw = ready_plan()
    raw["blocking_questions"] = ["公开展示与只有本人能看矛盾，第一版是哪一种？"]
    plan = normalize_plan(raw)
    assert not plan["is_complete"]
    assert plan["clarify_questions"][0]["dimension"] == "blocking"


def test_advice_can_answer_stack_question_without_starting_an_interview():
    plan = normalize_plan({"response_mode": "advice", "contract": {}})
    assert plan["is_complete"]
    assert plan["response_mode"] == "advice"
    assert plan["clarify_questions"] == []


def test_existing_project_is_boundary_not_a_new_project_plan():
    raw = ready_plan()
    raw["contract"]["project_type"] = "existing"
    raw["contract"]["permissions"] = {"execute": "all", "write": "all"}
    raw["contract"]["deliverables"] = {"format": "代码改动"}
    plan = normalize_plan(raw)
    assert plan["response_mode"] == "boundary"
    assert plan["contract"]["permissions"]["execute"] == "none"
    assert plan["contract"]["deliverables"]["format"] == "Markdown 方案文案"


def test_provenance_survives_pydantic_json_roundtrip():
    plan = normalize_plan(ready_plan())
    saved = TaskContract.from_planner_json(plan).model_dump(by_alias=True, mode="json")
    assert saved["assumptions"] == plan["contract"]["assumptions"]
    assert saved["confirmed_requirements"] == ["只有我自己使用"]
    assert saved["main_flow"] == plan["contract"]["main_flow"]


def test_invalid_planner_shape_never_becomes_ready():
    plan = normalize_plan({"contract": ["not an object"], "is_complete": True})
    assert not plan["is_complete"]
    assert len(plan["clarify_questions"]) <= 3


def test_independent_questions_are_batched_but_dependent_questions_wait():
    raw = ready_plan()
    raw["contract"]["main_flow"] = []
    raw["contract"]["acceptance"] = []
    raw["clarify_questions"] = [
        {"dimension": "main_flow", "text": "从打开到保存怎么走？", "depends_on": []},
        {"dimension": "acceptance", "text": "怎样算完成？", "depends_on": ["main_flow"]},
    ]
    plan = normalize_plan(raw)
    assert [q["dimension"] for q in plan["clarify_questions"]] == ["main_flow"]
    # The dependent acceptance question is deferred until the user explains
    # the workflow in the next turn.
    assert not any(q.get("depends_on") for q in plan["clarify_questions"])


def test_followup_omitted_fields_preserve_sources_but_explicit_changes_win():
    previous = normalize_plan(ready_plan())["contract"]
    raw = {"response_mode": "plan", "contract": {"target_users": "我和三个朋友各有自己的记录"}}
    plan = normalize_plan(raw, previous=previous)
    assert plan["is_complete"]
    assert plan["contract"]["target_users"] == "我和三个朋友各有自己的记录"
    assert plan["contract"]["goal"] == previous["goal"]
    assert plan["contract"]["confirmed_requirements"] == previous["confirmed_requirements"]
    assert previous["target_users"] == "只有我自己"


def test_new_project_reset_does_not_inherit_old_requirements():
    previous = normalize_plan(ready_plan())["contract"]
    plan = normalize_plan({"reset_project": True, "contract": {"goal": "另一个预约项目"}}, previous=previous)
    assert not plan["is_complete"]
    assert plan["contract"]["scope"]["in"] == []
    assert not plan["contract"]["confirmed_requirements"]


def test_invalid_planner_without_contract_cannot_deliver_old_plan_as_new():
    previous = normalize_plan(ready_plan())["contract"]
    plan = normalize_plan({"is_complete": True}, previous=previous)
    assert not plan["is_complete"]


def test_complete_document_passes_structural_checks():
    assert validate_output(VALID_PLAN, full_plan=True) == []


def test_truncated_plan_empty_section_and_missing_provenance_fail():
    assert validate_output(VALID_PLAN.split("## 7.")[0], full_plan=True)
    empty_section = VALID_PLAN.replace("## 5. 数据与权限\n书名、感想和记录时间持久化保存，归属个人账号。只有本人能读取和修改。", "## 5. 数据与权限")
    assert "章节未展开：数据与权限" in validate_output(empty_section, full_plan=True)
    no_source = VALID_PLAN.replace("### 默认假设", "### 其他建议")
    assert "决策来源未单列：默认假设" in validate_output(no_source, full_plan=True)


def test_code_commands_and_placeholder_are_rejected_even_in_advice():
    for text in ("```python\nprint('hello')\n```", "docker compose up -d", "CREATE TABLE books(id int);", "[待填写技术方案]"):
        assert validate_output(text, full_plan=False)
    assert validate_output("数据库负责保存记录。可用 PostgreSQL；优点是可靠，代价是要维护服务。", full_plan=False) == []
