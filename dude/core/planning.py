"""New-project planning policy and deterministic document checks.

These checks cover structure and obvious output violations, not factual or
semantic correctness. The model still reviews the full document afterwards.
"""

from copy import deepcopy
import re
from core.project_state import workflow_for


PLAN_SECTIONS = (
    "目标与使用场景", "第一版范围", "页面与操作流程", "技术方案与理由",
    "数据与权限", "分阶段实施", "部署、安全与备份", "成本与假设",
    "验收与报错处理", "已确认、默认与待定",
)

DEFAULT_ASSUMPTIONS = (
    "规模未明确时按个人或小规模使用设计；用户明确要求优先。",
    "没有指定技术时推荐成熟的少组件方案，不默认引入微服务、队列或集群。",
    "优先完成核心流程，额外功能提出分期建议，改变核心范围需用户确认。",
    "需要保留的数据持久化，并按场景规划权限、备份和恢复。",
)

CORE_QUESTIONS = {
    "goal": {"text": "你想做一个什么工具，最想解决哪件事？", "hint": "例如：记录自己读过的书，方便以后回看。"},
    "scope.in": {"text": "第一版最不能少的功能有哪些？", "hint": "例如：记下一本书、写读后感、回看以前的记录。"},
    "main_flow": {"text": "从打开到完成，你希望怎样用它？", "hint": "例如：打开书单 → 添加书名和感想 → 保存 → 下次还能看到。"},
    "acceptance": {"text": "出现哪些结果，你就觉得第一版可以用了？", "hint": "例如：保存后重新打开，书名和感想都还在。也可以让我根据已确定功能推荐。"},
}


def _strings(value):
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(item.strip() for item in value if isinstance(item, str) and item.strip()))


def core_questions(fields):
    return [{"dimension": field, **CORE_QUESTIONS[field]}
            for field in fields if field in CORE_QUESTIONS][:3]


def normalize_plan(raw: dict, previous: dict | None = None) -> dict:
    """Resolve non-blocking defaults, while never inventing a core workflow.

    A model's completion score, a long message, and a round limit cannot
    override missing core fields or explicit blocking questions.
    """
    plan = deepcopy(raw) if isinstance(raw, dict) else {}
    raw_contract = plan.get("contract")
    contract = deepcopy(previous) if isinstance(previous, dict) and plan.get("reset_project") is not True else {}
    if isinstance(raw_contract, dict):
        # Omitted fields survive a follow-up; explicit replacements win.
        contract.update(raw_contract)
        if isinstance(raw_contract.get("scope"), dict):
            contract["scope"] = {**(previous or {}).get("scope", {}), **raw_contract["scope"]} if plan.get("reset_project") is not True else raw_contract["scope"]
    mode = plan.get("response_mode", "plan")
    mode = mode if mode in {"plan", "clarify", "advice", "boundary"} else "clarify"
    if contract.get("project_type") == "existing":
        mode = "boundary"
    contract["project_type"] = "existing" if contract.get("project_type") == "existing" else "new"
    contract["confirmed_by_user"] = False  # A changed draft is not blanket user confirmation.
    contract["deliverables"] = {"format": "Markdown 方案文案", "artifacts": ["一份完整项目实施方案"]}
    contract["permissions"] = {"read": "none", "write": "none", "execute": "none", "api": [], "shell": []}
    for field in ("constraints", "acceptance", "risks", "main_flow", "confirmed_requirements", "assumptions", "pending_questions"):
        contract[field] = _strings(contract.get(field))
    scope = contract.get("scope")
    scope = scope if isinstance(scope, dict) else {}
    contract["scope"] = {"in": _strings(scope.get("in", scope.get("in_"))), "out": _strings(scope.get("out"))}
    contract["goal"] = contract.get("goal", "") if isinstance(contract.get("goal", ""), str) else ""
    contract["target_users"] = contract.get("target_users", "") if isinstance(contract.get("target_users", ""), str) else ""
    contract["assumptions"] = list(dict.fromkeys(contract["assumptions"] + list(DEFAULT_ASSUMPTIONS)))
    if not contract["target_users"].strip():
        contract["target_users"] = "个人或小规模使用（默认假设）"
        contract["assumptions"].append("未明确使用者时，暂按个人或小规模使用者规划。")

    missing = []
    for field, present in (
        ("goal", contract["goal"].strip()), ("scope.in", contract["scope"]["in"]),
        ("main_flow", contract["main_flow"]), ("acceptance", contract["acceptance"]),
    ):
        if not present:
            missing.append(field)
    blockers = _strings(plan.get("blocking_questions"))
    if not isinstance(raw_contract, dict) and mode not in {"advice", "boundary"}:
        blockers.append("这轮信息暂时没能可靠整理，请稍后重试或重发刚才的补充。")
    workflow = workflow_for(contract, blockers)
    ready_fields = set(workflow["ready"])
    if mode in {"advice", "boundary"}:
        questions = []
        complete = True  # Finish this reply, not the project plan.
    else:
        # The planner must express unresolved ambiguity as a blocking question.
        # Optional technical decisions are resolved using the labelled defaults.
        complete = not missing and not blockers
        mode = "plan" if complete else "clarify"
        offered = plan.get("clarify_questions", [])
        offered = offered if isinstance(offered, list) else []
        questions = [{"text": text, "dimension": "blocking", "hint": "这个选择会改变核心流程、权限或费用，需要先确定。"}
                     for text in blockers[:3]]
        questions.extend(q for q in offered if isinstance(q, dict)
                         and q.get("dimension") in ready_fields and isinstance(q.get("text"), str) and q["text"].strip())
        covered = {q.get("dimension") for q in questions}
        questions.extend(core_questions([field for field in workflow["ready"] if field not in covered]))
        # Independent questions can be answered in one batch.  A model may
        # mark a question as dependent on another; defer those to the next
        # turn so the user is not asked to resolve a chain at once.
        questions = [q for q in questions if not q.get("depends_on")][:3]
        if not questions and not complete:
            questions = core_questions(workflow["ready"])

    contract["missing_fields"] = missing + (["blocking"] if blockers else [])
    contract["confidence"] = (4 - len(missing)) / 4
    contract["workflow"] = workflow
    plan.update(contract=contract, response_mode=mode, is_complete=complete,
                completeness=contract["confidence"], goal=contract["goal"],
                missing_fields=contract["missing_fields"], clarify_questions=questions,
                blocking_questions=blockers)
    return plan


def validate_output(text: str, *, full_plan: bool) -> list[str]:
    """Return actionable defects; do not certify the plan's semantics."""
    issues = []
    if not text or not text.strip():
        return ["输出为空"]
    if re.search(r"(?m)^\s*(```|~~~)", text):
        issues.append("输出包含代码围栏；本产品只交付方案文案")
    if re.search(r"(?im)^\s*(?:\$\s*)?(?:sudo\s+|docker\s+compose\s+|pip\s+install\s+|npm\s+install\s+|CREATE\s+TABLE\s+|SELECT\s+.+\s+FROM\s+|def\s+\w+\s*\(|import\s+\w+)", text):
        issues.append("输出包含可执行命令、SQL 或代码，应改为用途和要求说明")
    if re.search(r"\[(?:TODO|待填写|待补充|placeholder)[^\]]*\]|<待填写>|\bTODO\s*:", text, re.I):
        issues.append("输出包含未填写的占位内容")
    if not full_plan:
        return issues
    headings = list(re.finditer(r"(?m)^##\s+(.+)$", text))
    for section in PLAN_SECTIONS:
        matching = [i for i, heading in enumerate(headings) if section in heading.group(1)]
        if not matching:
            issues.append(f"缺少章节：{section}")
            continue
        i = matching[0]
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[headings[i].end():end].strip()
        if len(re.sub(r"[#*\-\s]", "", body)) < 12:
            issues.append(f"章节未展开：{section}")
    # Require explicit provenance, not just a heading that mentions it.
    for label in ("已确认要求", "默认假设", "待定事项"):
        if not re.search(r"(?m)^(?:###\s+|\*\*)" + label, text):
            issues.append(f"决策来源未单列：{label}")
    return issues
