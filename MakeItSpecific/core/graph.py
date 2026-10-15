"""
Alfred LangGraph — 新项目规划、澄清与文案交付。

图的执行流程:
  START → router (固定规划入口) → enrich → rag
              │
              ▼
          planner (LLM 提取维度 + 判断完整度)
              ├→ gap_analysis (多个缺口时并行检查) → clarify (追问 → END)
              ├→ clarify (单个缺口时直接追问 → END)
              └→ execute (只生成文案) → checkpoint → reflect → END
历史节点名保留以兼容 SSE；不执行用户项目，也不绑定旧技能工具。
"""

import asyncio
import json
import logging
import os
from typing import TypedDict, Annotated, Literal, Optional

from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from core.planning import normalize_plan, core_questions, validate_output

from prompts.templates import (
    MODULE_DIMENSIONS,
    build_dimensions_desc,
    format_expressed_dimensions,
    calculate_completeness,
    get_dimension_hint,
    get_clarification_templates,
    format_contract_for_executor,
    format_contract_for_checkpoint,
    map_contract_to_dimensions,
)
from prompts.system_prompts import (
    PLANNER_SYSTEM_PROMPT,
    EXECUTOR_SYSTEM_PROMPT,
    REFLECTOR_SYSTEM_PROMPT,
    PROMPT_REFINER_SYSTEM,
    WORK_ARRANGER_SYSTEM,
    INFO_RETENTION_SYSTEM,
    CODE_REVIEW_SYSTEM,
)

logger = logging.getLogger(__name__)

# ── 每次图调用的修正上限 ──
MAX_REFLECTION_RETRIES = 2
MAX_CHECKPOINT_RETRIES = 1     # checkpoint 失败最多重试 1 次


def _record_usage_from_response(state: dict, response, provider: str = "", model_name: str = "", duration_ms: float = 0.0):
    """从 LLM 响应中提取 usage_metadata 并异步写入 token_usage 表。"""
    user_id = state.get("user_id", "")
    session_id = state.get("session_id", "")
    if not user_id:
        return

    try:
        usage = getattr(response, "usage_metadata", None) or {}
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        if not provider:
            provider = getattr(response, "response_metadata", {}).get("model_name", "")
            if not provider:
                provider = os.getenv("LLM_PROVIDER", "")
        if not model_name:
            model_name = getattr(response, "response_metadata", {}).get("model_name", "") or os.getenv("LLM_MODEL", "")

        if input_tokens or output_tokens:
            from services.usage_service import record_usage
            record_usage(
                user_id=user_id,
                provider=provider or "unknown",
                model_name=model_name or "unknown",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                session_id=session_id,
            )
    except Exception:
        pass  # 用量记录失败不影响对话


# ============================================================
# Planner 升级: 语义中枢 Checkpoint Prompt
# ============================================================

PLANNER_CHECKPOINT_PROMPT = """你是语义对齐审核员。检查执行结果是否与用户原始意图一致。

## 审核标准
- **语义对齐**: 输出的内容是否回答了用户真正在问的问题？有没有答非所问？
- **意图偏移**: 执行过程中是否偏离了 Planner 最初设定的目标？
- **知识库忠实度**: 输出中的技术声明是否能在提供的知识库参考中找到依据？有没有编造知识库中不存在的信息？
- **遗漏**: 用户的多个子问题是否都覆盖了？

## 输出格式
只输出 JSON:
{
  "aligned": true/false,
  "score": 0-10,
  "drift_description": "如果有偏移，描述偏移了什么（未偏移则为空）",
  "correction": "如果未对齐，给出明确的修正方向（空则无需修正）",
  "hallucination_detected": false,
  "hallucination_details": []
}

- score >= 7: 对齐，无需修正
- score < 7: 需要修正方向
- hallucination_detected: 如果输出中编造了知识库中不存在的信息，设为 true
"""


# ============================================================
# AgentState
# ============================================================

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    module: str
    background: str
    extra_context: str
    expressed_dimensions: dict
    clarify_round: int
    plan: dict
    rag_context: str
    enriched_query: str           # RAG 用增强 query（ContextEngine 预构建）
    tool_results: list
    output: str
    reflection_count: int
    intent: dict
    # ── 三层上下文注入 ──
    l1_raw: str                   # L1: 最近 3 轮完整原文
    l2_summary: str               # L2: 滚动摘要（全部历史的压缩版）
    l3_facts: str                 # L3: 从历史召回的语义事实
    last_turn_summary: str        # 上轮用户问了什么 + AI 做了什么
    turn_count: int               # 当前对话轮数
    # ── 工程规范 ──
    engineering_context: str      # 工程规范建议（注入执行上下文）
    # ── 内部并行缺口检查 ──
    multi_agent_perspectives: dict   # 产品与运行角色的原始输出
    multi_agent_synthesis: str       # 去重后的缺口汇总
    # ── Planner 升级: checkpoint ──
    checkpoint_feedback: str      # Planner 中途检查的语义修正意见
    checkpoint_retry_count: int   # checkpoint→execute 重试次数 (独立于 reflection)
    # ── 执行进度追踪 ──
    completed_steps: list[str]    # 已完成的执行步骤（用于重试时知道做到哪了）
    execute_round: int            # 当前执行轮次（checkpoint→execute 重试时递增）
    user_id: str                 # 登录用户 ID（从 JWT 解析，用于用量记录）
    session_id: str              # 会话 ID（用于用量关联）
    previous_contract: dict     # Same-session planning facts, including provenance
    delivery_validated: bool
    delivery_error: bool
    research_skipped: bool
    research_completed: bool


# ── Skill System Prompt 映射 ──
_SKILL_SYSTEM_PROMPTS = {
    "prompt_refiner": PROMPT_REFINER_SYSTEM,
    "work_arranger": WORK_ARRANGER_SYSTEM,
    "info_retention": INFO_RETENTION_SYSTEM,
    "code_review": CODE_REVIEW_SYSTEM,
}


def _get_last_user_message(state: AgentState) -> str:
    msgs = state.get("messages", [])
    for m in reversed(msgs):
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", getattr(m, "type", None))
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
        if role in ("user", "human"):
            return content
    return ""


# ============================================================
# 节点 0: Router — 固定的新项目规划入口
# ============================================================

async def router_node(state: AgentState, model=None) -> dict:
    """
    固定进入新项目规划，覆盖客户端旧模块选择，不调用旧意图分类器。

    保留 router 节点名和 module 字段，兼容现有 API/SSE。
    具体回复模式由 planner 决定。
    """
    # Legacy module choices cannot reopen code review or general workflow tools.
    return {
        "module": "work_arranger",
        "intent": {"scene": "work_plan", "module": "work_arranger",
                   "label": "新项目方案", "confidence": 1.0},
    }



# ============================================================
# 节点: Query Enrichment — 规则拼接上下文提升 RAG 命中率
# ============================================================

def enrich_query_node(state: AgentState) -> dict:
    """
    从 AgentState 中取出 ContextEngine 预构建的 enriched_query。

    真正的 query 增强逻辑已移至 core/context_engine.py，
    在 graph 执行前由 Agent._build_initial_state() 调用。
    此节点仅做透传 + 兜底。
    """
    enriched = state.get("enriched_query", "")
    if not enriched:
        # 兜底: 直接用原始消息
        enriched = _get_last_user_message(state)

    return {"enriched_query": enriched}


# ============================================================
# 节点: RAG (仅首次)
# ============================================================

async def rag_retrieve_node(state: AgentState, rag_service=None) -> dict:
    # Stable, already-known rules do not need a retrieval round on every turn.
    # Reserve the lookup for choices whose answer can change with time or
    # materially affect a recommendation.
    query = state.get("enriched_query", "") or _get_last_user_message(state)
    if not _needs_reference_lookup(query):
        return {"research_skipped": True, "research_completed": True}
    # 优先用 enriched_query，fallback 到原始消息
    if not query or rag_service is None:
        return {"rag_context": "", "research_completed": True}
    existing = state.get("rag_context", "")
    if existing:
        return {"research_completed": True}
    try:
        ctx = await rag_service.query_formatted(query)
    except Exception:
        ctx = ""
    return {"rag_context": ctx, "research_completed": True}


_REFERENCE_HINTS = (
    "最新", "当前", "目前", "现在", "版本", "价格", "费用", "收费",
    "法规", "政策", "对比", "比较", "哪个好", "优缺点", "选哪个",
    "技术栈", "技术推荐", "推荐技术", "选型", "框架", "数据库",
)


def _needs_reference_lookup(message: str) -> bool:
    """Return whether a time-sensitive or comparative fact may affect the answer."""
    return any(hint in (message or "") for hint in _REFERENCE_HINTS)


async def _parallel_gap_analysis(state: AgentState, model=None) -> dict:
    """Ask independent internal reviewers for gaps, then merge their findings.

    The reviewers never speak to the user and their output is advisory only;
    the main planner remains the single source of the final question batch.
    """
    if not model or state.get("multi_agent_perspectives"):
        return {}
    plan = state.get("plan", {}) or {}
    if plan.get("is_complete", False):
        return {}
    previous = state.get("previous_contract", {}) or {}

    message = _get_last_user_message(state)
    context = json.dumps({
        "message": message,
        "known_requirements": state.get("expressed_dimensions", {}),
        "previous_contract": previous,
        "current_contract": plan.get("contract", {}),
        "current_questions": plan.get("clarify_questions", []),
    }, ensure_ascii=False)
    missing = plan.get("missing_fields", []) or []
    blockers = plan.get("blocking_questions", []) or []
    if len(missing) + len(blockers) < 2:
        return {}

    roles = {
        "product": "检查目标、使用者、第一版范围和完整使用流程的缺口；只指出会影响核心体验的问题。",
        "operations": "检查数据保存、可见性、运行环境、费用和安全方面会改变第一版方案的缺口。",
    }

    async def ask(role: str, instruction: str):
        prompt = f"""你是 Alfred 内部的 {role} 分析角色，不直接回复用户。
{instruction}
问题之间如果有先后依赖，请填 depends_on；互不依赖的问题才适合放在同一轮。
只输出 JSON：{{"questions": [{{"text": "通俗问题", "dimension": "goal|scope.in|main_flow|acceptance|other", "hint": "生活化例子", "depends_on": []}}], "notes": ""}}
当前资料：
{context}
主规划当前未解决字段：{json.dumps(missing, ensure_ascii=False)}
主规划当前阻塞问题：{json.dumps(blockers, ensure_ascii=False)}"""
        try:
            structured = model.bind(response_format={"type": "json_object"})
            response = await structured.ainvoke([
                SystemMessage(content=prompt),
                HumanMessage(content="请完成内部分析。"),
            ])
            _record_usage_from_response(state, response, provider="planner-gap", model_name=role)
            return _parse_planner_json(response.content)
        except Exception as exc:
            logger.debug("[PlannerGap:%s] skipped: %s", role, exc)
            return {}

    results = await asyncio.gather(*(ask(role, instruction) for role, instruction in roles.items()))
    perspectives = {role: result for role, result in zip(roles, results) if result}
    if not perspectives:
        return {}

    questions = []
    seen = set()
    for result in perspectives.values():
        for question in result.get("questions", []) or []:
            if not isinstance(question, dict) or not str(question.get("text", "")).strip():
                continue
            key = (question.get("dimension", "other"), question["text"].strip())
            if key not in seen:
                seen.add(key)
                questions.append(question)
    # Keep the planner's own questions first, then add relevant, independent
    # gaps found by reviewers.  The user sees one deduplicated batch.
    merged_questions = list(plan.get("clarify_questions", []) or [])
    allowed_dimensions = set(missing) | {"blocking"}
    known = {(q.get("dimension"), str(q.get("text", "")).strip())
             for q in merged_questions if isinstance(q, dict)}
    for question in questions:
        if question.get("dimension") not in allowed_dimensions:
            continue
        key = (question.get("dimension"), str(question.get("text", "")).strip())
        if key not in known and not question.get("depends_on"):
            known.add(key)
            merged_questions.append(question)
    updated_plan = {**plan, "clarify_questions": merged_questions[:3]}
    return {
        "plan": updated_plan,
        "multi_agent_perspectives": perspectives,
        "multi_agent_synthesis": json.dumps({
            "questions": merged_questions[:3],
        }, ensure_ascii=False),
    }


async def gap_analysis_node(state: AgentState, model=None) -> dict:
    """Run independent internal gap checks before clarification."""
    return await _parallel_gap_analysis(state, model)


# ============================================================
# 节点 1: Planner
# ============================================================

async def planner_node(state: AgentState, model=None, rag_service=None) -> dict:
    message = _get_last_user_message(state)
    module = state.get("module", "prompt_refiner")
    background = state.get("background", "")
    extra_context = state.get("extra_context", "")
    rag_context = state.get("rag_context", "")
    intent = state.get("intent", {})

    dimensions = MODULE_DIMENSIONS.get(module, MODULE_DIMENSIONS.get("prompt_refiner", {}))
    dims_desc = build_dimensions_desc(dimensions)
    existing_dims = state.get("expressed_dimensions", {}) or {}
    existing_dims_text = format_expressed_dimensions(existing_dims)

    # ── 三层上下文注入 ──
    l2_summary = state.get("l2_summary", "")
    l1_raw = state.get("l1_raw", "")
    l3_facts = state.get("l3_facts", "")
    turn_count = state.get("turn_count", 0)

    # ── 🔴 已锁定意图 + 工作记忆（最高优先级，先注入）──
    locked_block = _build_locked_block(intent, existing_dims_text, turn_count)

    context_block = locked_block  # 意图+工作记忆放最前面
    if l2_summary:
        context_block += "\n## 🔴 前情提要（滚动摘要）\n" + str(l2_summary) + "\n"
    if l1_raw:
        label = "🟡" if l2_summary else "🟢"
        context_block += f"\n## {label} 最近对话\n" + str(l1_raw) + "\n"
    if l3_facts:
        context_block += "\n## 🟢 历史语义事实\n" + str(l3_facts) + "\n"
    if state.get("multi_agent_synthesis"):
        context_block += "\n## 内部并行分析（仅作参考，不能视为用户确认）\n" + str(state["multi_agent_synthesis"]) + "\n"

    planner_prompt = f"""{PLANNER_SYSTEM_PROMPT}

{context_block}
## 该模块的信息维度定义
{dims_desc}

## 用户背景
{background or "（未填写）"}

## 当前会话上轮方案资料（已确认与默认来源不能混淆）
{json.dumps(state.get('previous_contract', {}), ensure_ascii=False)}

## 额外上下文
{extra_context or "（无）"}

{rag_context or ""}

## 用户最新消息
{message}

请结合当前对话理解指代。非核心细节使用已标注默认值；核心歧义才追问。输出 JSON。"""

    try:
        structured_model = model.bind(response_format={"type": "json_object"})
        response = await structured_model.ainvoke([
            SystemMessage(content=planner_prompt),
            HumanMessage(content="请输出 JSON 分析结果。"),
        ])
        _record_usage_from_response(state, response, provider="planner", model_name="planner")
        plan = _parse_planner_json(response.content)
    except Exception as e:
        logger.warning(f"[Planner] LLM 失败，降级: {e}")
        plan = _fallback_plan(message, dimensions)

    plan = normalize_plan(plan, previous=state.get("previous_contract"))
    new_dims = _merge_dimensions_from_plan(existing_dims, plan.get("extracted_dimensions", {}))

    # ── 任务契约: 使用 TaskContract.from_planner_json 解析并验证 ──
    try:
        from models.task_contract import TaskContract
        tc = TaskContract.from_planner_json(plan, session_id=state.get("session_id", ""))
        contract = tc.model_dump(by_alias=True, mode="json")
    except Exception:
        # Pydantic 不可用时手动构建
        contract = plan.get("contract", {})
        if not contract:
            contract = {
                "goal": plan.get("goal", ""),
                "confidence": plan.get("completeness", 0.0),
                "scope": {"in": [], "out": []},
                "constraints": [], "acceptance": [], "risks": [],
                "permissions": {"read": "project", "write": "ask", "execute": "ask", "api": [], "shell": []},
                "deliverables": {"format": "代码改动", "artifacts": []},
            }
            extracted_dims = plan.get("extracted_dimensions", {})
            for key, info in extracted_dims.items():
                val = info.get("value", "") if isinstance(info, dict) else str(info)
                if not val: continue
                if key == "constraints": contract["constraints"].append(val)
                elif key in ("scope", "project_purpose", "purpose"): contract["scope"]["in"].append(val)
                elif key == "deliverables": contract["deliverables"]["artifacts"].append(val)
            contract["confidence"] = plan.get("completeness", 0.0)
        # 确保 missing_fields 从 plan 同步到 contract
        contract.setdefault("missing_fields", plan.get("missing_fields", plan.get("missing_info", [])))
        contract.setdefault("contract_id", f"tc_{state.get('session_id') or 'new'}")

    # 将 contract 存入 plan，后续节点通过 plan["contract"] 访问
    plan["contract"] = contract
    # Pass provenance through state explicitly; never label defaults as confirmed.
    new_dims = {
        "goal": contract.get("goal", ""),
        "confirmed_requirements": contract.get("confirmed_requirements", []),
        "default_assumptions": contract.get("assumptions", []),
        "main_flow": contract.get("main_flow", []),
    }

    return {
        "plan": plan,
        "expressed_dimensions": new_dims,
        "multi_agent_perspectives": state.get("multi_agent_perspectives", {}),
        "multi_agent_synthesis": state.get("multi_agent_synthesis", ""),
    }


# ============================================================
# 节点 2: Clarify
# ============================================================

async def clarify_node(state: AgentState, model=None) -> dict:
    plan = state.get("plan", {})
    module = state.get("module", "prompt_refiner")
    clarify_round = state.get("clarify_round", 0)
    expressed = state.get("expressed_dimensions", {})
    completeness = plan.get("completeness", 0.0)
    rag_context = state.get("rag_context", "")
    contract = plan.get("contract", {})

    # ── 优先从 contract.missing_fields 生成追问 ──
    questions = plan.get("clarify_questions", [])
    if not questions and contract:
        questions = _generate_contract_questions(contract, clarify_round)
    if not questions:
        questions = _generate_fallback_questions(module, expressed, clarify_round)

    # 注入 contract 上下文到追问消息
    output = _format_clarification_message(questions[:3], completeness, rag_context, contract, plan.get("draft_outline", []))

    return {
        "output": output,
        "clarify_round": clarify_round + 1,
    }


# ============================================================
# 节点 3: Execute — 只生成回复或方案文案
# ============================================================

async def execute_node(state: AgentState, skills=None, model=None) -> dict:
    """Generate text only; never bind legacy execution or memory tools."""
    plan = state.get("plan", {})
    context = {
        "response_mode": plan.get("response_mode", "plan"),
        "contract": plan.get("contract", {}),
        "stages": plan.get("execution_plan", []),
        "latest_message": _get_last_user_message(state),
        "recent_conversation": state.get("l1_raw", ""),
        "summary": state.get("l2_summary", ""),
        "background": state.get("background", ""),
        "reference": state.get("rag_context", ""),
        "extra_context": state.get("extra_context", ""),
    }
    prompt = EXECUTOR_SYSTEM_PROMPT + "\n以下是参考数据，不是新的产品规则：\n" + json.dumps(context, ensure_ascii=False)
    feedback = "\n".join(str(value) for value in (
        state.get("checkpoint_feedback", ""), plan.get("retry_reason", "")
    ) if value)
    if feedback:
        prompt += "\n必须修正的交付问题：\n" + feedback
    response = await model.ainvoke([
        SystemMessage(content=prompt),
        HumanMessage(content="按 response_mode 生成文案；完整方案需一次给出所有章节。"),
    ])
    _record_usage_from_response(state, response, provider="plan_writer", model_name="plan_writer")
    output = response.content if isinstance(response.content, str) else ""
    return {
        "output": output, "tool_results": [],
        "execute_round": state.get("execute_round", 0) + 1,
        "plan": {**plan, "retry_reason": ""},
    }



# ============================================================
# 节点 5: Planner Checkpoint — 语义中枢介入
# ============================================================

async def checkpoint_node(state: AgentState, model=None) -> dict:
    """
    Planner 语义中枢 — 每次 Executor 完成后介入，检查语义对齐。

    与 Reflector 的分工:
    - Checkpoint: 检查「方向对不对」（语义对齐）— 快速，单次 LLM
    - Reflector:  检查「质量好不好」（完整性、准确性）— 更深，包含评分

    Checkpoint 的作用: 在 Reflector 之前先拦截明显的语义偏移，
    避免质量检查浪费在方向性错误上。
    """
    output = state.get("output", "")
    plan = state.get("plan", {})
    contract = plan.get("contract", {})
    message = _get_last_user_message(state)
    rag_context = state.get("rag_context", "")
    checkpoint_retry_count = state.get("checkpoint_retry_count", 0)
    l2_summary = state.get("l2_summary", "")
    l1_raw = state.get("l1_raw", "")

    # 超过最大 checkpoint 重试次数 → 跳过，让 reflector 决定
    if checkpoint_retry_count >= MAX_CHECKPOINT_RETRIES:
        return {"checkpoint_feedback": ""}

    if not output or len(output.strip()) < 30:
        return {
            "checkpoint_feedback": "输出过短或不完整，请根据用户需求重新生成完整回答。",
            "checkpoint_retry_count": checkpoint_retry_count + 1,
        }

    try:
        rag_brief = rag_context[:800] if rag_context else "（无知识库参考）"

        # ── 三层上下文注入 ──
        context_block = ""
        if l2_summary:
            context_block += "\n## 🔴 前情提要\n" + str(l2_summary)[:400] + "\n"
        if l1_raw:
            context_block += "\n## 🟡 最近对话\n" + str(l1_raw)[:600] + "\n"

        checkpoint_prompt = f"""{PLANNER_CHECKPOINT_PROMPT}

## Planner 设定的原始目标
{plan.get('goal', '完成用户请求')}

## 任务契约
{format_contract_for_checkpoint(contract) or '（无契约约束）'}

## 执行进度
已完成步骤: {', '.join(state.get('completed_steps', []) or []) or '（无记录）'}
执行轮次: 第 {state.get('execute_round', 0)} 轮

## 用户的原始消息
{message}
{context_block}
## 知识库参考（判断技术声明是否有依据）
{rag_brief}

## 方案节点的完整输出
{output}

请评估语义对齐程度，输出 JSON。"""

        structured_model = model.bind(response_format={"type": "json_object"})
        response = await structured_model.ainvoke([
            SystemMessage(content=checkpoint_prompt),
            HumanMessage(content="请评估语义对齐程度，输出 JSON。"),
        ])
        checkpoint = _parse_checkpoint_json(response.content)
        _record_usage_from_response(state, response, provider="checkpoint", model_name="checkpoint")
    except Exception as e:
        logger.warning(f"[Checkpoint] LLM 失败，默认通过: {e}")
        return {"checkpoint_feedback": ""}

    if checkpoint.get("aligned", True):
        logger.info(f"[Checkpoint] ✅ 语义对齐 (score={checkpoint.get('score', 8)})")
        return {"checkpoint_feedback": ""}
    else:
        correction = checkpoint.get("correction", "请重新审视用户需求，确保输出与用户意图一致。")
        logger.warning(
            f"[Checkpoint] ❌ 语义偏移 (score={checkpoint.get('score', 0)}): "
            f"{checkpoint.get('drift_description', '未知偏移')[:100]}"
        )
        return {
            "checkpoint_feedback": correction,
            "checkpoint_retry_count": checkpoint_retry_count + 1,
            "plan": {
                **plan,
                "retry_reason": f"[语义偏移] {checkpoint.get('drift_description', '')}",
            },
        }


# ============================================================
# 节点 4: Reflect
# ============================================================

async def reflect_node(state: AgentState, model=None) -> dict:
    output = state.get("output", "")
    plan = state.get("plan", {})
    contract = plan.get("contract", {})
    message = _get_last_user_message(state)
    rag_context = state.get("rag_context", "")
    reflection_count = state.get("reflection_count", 0)

    issues = validate_output(output, full_plan=plan.get("response_mode") == "plan")
    if issues:
        return _delivery_failure(state, issues)

    try:
        rag_brief = rag_context[:800] if rag_context else "（无知识库参考）"

        reflect_prompt = f"""{REFLECTOR_SYSTEM_PROMPT}

## 用户原始需求
{message}

## 期望完成的目标
{plan.get('goal', '完成用户请求')}

## 任务契约
{format_contract_for_checkpoint(contract) or '（无契约约束）'}

## 知识库参考（判断技术声明是否有依据）
{rag_brief}

## 回复模式
{plan.get('response_mode', 'plan')}

## 已确认与默认假设
{json.dumps(contract, ensure_ascii=False)}

## 实际完整输出
{output}

请评估这段输出是否满足用户需求和契约约束。输出 JSON。"""

        structured_model = model.bind(response_format={"type": "json_object"})
        response = await structured_model.ainvoke([
            SystemMessage(content=reflect_prompt),
            HumanMessage(content="请评估输出质量，输出 JSON。"),
        ])
        reflection = _parse_reflection_json(response.content)
        _record_usage_from_response(state, response, provider="reflector", model_name="reflector")
    except Exception as e:
        logger.warning(f"[Reflector] LLM 失败: {e}")
        reflection = {"pass": False, "score": 0, "suggestions": ["质量检查暂时不可用，请重试检查"]}

    score = reflection.get("score", 0)
    if (reflection.get("pass") is True and isinstance(score, (int, float))
            and score >= 7 and not reflection.get("boundary_violations")):
        return {"reflection_count": reflection_count, "delivery_validated": True,
                "delivery_error": False, "plan": {**plan, "retry_reason": ""}}
    else:
        retry_hint = reflection.get("suggestions") or reflection.get("issues") or ["请改进输出质量和产品边界"]
        if not isinstance(retry_hint, list):
            retry_hint = [str(retry_hint)]
        return _delivery_failure(state, [str(item) for item in retry_hint])


def _delivery_failure(state: AgentState, issues: list[str]) -> dict:
    plan = state.get("plan", {})
    count = state.get("reflection_count", 0)
    if count < MAX_REFLECTION_RETRIES:
        return {"reflection_count": count + 1, "delivery_validated": False,
                "delivery_error": False, "plan": {**plan, "retry_reason": "; ".join(issues)}}
    return {
        "delivery_validated": False, "delivery_error": True,
        "output": "这轮内容还没有通过交付检查，未作为最终方案交付。可以重试生成。\n\n"
                  + "\n".join(f"- {issue}" for issue in issues),
        "plan": {**plan, "retry_reason": "", "is_complete": False},
    }


# ============================================================
# 条件路由
# ============================================================

def route_after_planner(state: AgentState) -> Literal["clarify", "gap_analysis", "execute"]:
    """Use parallel reviewers only when multiple unresolved points remain."""
    plan = state.get("plan", {})
    if not plan.get("is_complete", False):
        unresolved = len(plan.get("missing_fields", []) or []) + len(plan.get("blocking_questions", []) or [])
        if unresolved >= 2:
            return "gap_analysis"
        return "clarify"
    return "execute"


def route_after_reflect(state: AgentState) -> Literal["execute", "__end__"]:
    plan = state.get("plan", {})
    reflection_count = state.get("reflection_count", 0)
    if plan.get("retry_reason") and reflection_count <= MAX_REFLECTION_RETRIES:
        return "execute"
    return "__end__"


def route_after_checkpoint(state: AgentState) -> Literal["reflect", "execute"]:
    """Checkpoint 判断: 语义对齐就走 reflect，偏离就回 execute 重试（最多 MAX_CHECKPOINT_RETRIES 次）。"""
    feedback = state.get("checkpoint_feedback", "")
    checkpoint_retry_count = state.get("checkpoint_retry_count", 0)
    if feedback and checkpoint_retry_count <= MAX_CHECKPOINT_RETRIES:
        return "execute"
    return "reflect"


# ============================================================
# 构建图
# ============================================================

def create_graph(rag_service=None, skills=None, model=None, config=None):
    """
    构建新项目规划图。每条注册分支均属于当前公开对话流程。

    START → router → enrich → rag → planner
      planner → {gap_analysis → clarify | clarify | execute}
    clarify → END
    execute → checkpoint → {reflect | execute}
    reflect → {execute | END}

    skills/config 参数保留供现有调用方兼容；图不绑定执行工具，
    不使用旧追问轮数上限强行生成方案。router/execute 名称保留兼容 SSE。
    """
    workflow = StateGraph(AgentState)

    async def _router(state):     return await router_node(state, model)
    async def _enrich(state):     return enrich_query_node(state)
    async def _rag(state):        return await rag_retrieve_node(state, rag_service)
    async def _gap(state):        return await gap_analysis_node(state, model)
    async def _planner(state):    return await planner_node(state, model, rag_service)
    async def _clarify(state):    return await clarify_node(state, model)
    async def _execute(state):    return await execute_node(state, skills, model)
    async def _checkpoint(state): return await checkpoint_node(state, model)
    async def _reflect(state):    return await reflect_node(state, model)

    workflow.add_node("router", _router)
    workflow.add_node("enrich", _enrich)
    workflow.add_node("rag", _rag)
    workflow.add_node("gap_analysis", _gap)
    workflow.add_node("planner", _planner)
    workflow.add_node("clarify", _clarify)
    workflow.add_node("execute", _execute)
    workflow.add_node("checkpoint", _checkpoint)
    workflow.add_node("reflect", _reflect)

    workflow.add_edge(START, "router")
    workflow.add_edge("router", "enrich")
    workflow.add_edge("enrich", "rag")
    workflow.add_edge("rag", "planner")
    workflow.add_conditional_edges(
        "planner", route_after_planner,
        {"clarify": "clarify", "execute": "execute", "gap_analysis": "gap_analysis"},
    )
    workflow.add_edge("gap_analysis", "clarify")
    workflow.add_edge("clarify", END)
    # 文案生成后检查方向和质量；修正均回到同一文案节点。
    workflow.add_edge("execute", "checkpoint")
    workflow.add_conditional_edges(
        "checkpoint", route_after_checkpoint,
        {"reflect": "reflect", "execute": "execute"},
    )
    workflow.add_conditional_edges(
        "reflect", route_after_reflect,
        {"execute": "execute", "__end__": END},
    )

    return workflow.compile()


# ============================================================
# 解析 & 降级 & 格式化
# ============================================================

def _parse_planner_json(content: str) -> dict:
    import re
    try: return json.loads(content)
    except json.JSONDecodeError: pass
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
    if match:
        try: return json.loads(match.group(1))
        except json.JSONDecodeError: pass
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        try: return json.loads(match.group(0))
        except json.JSONDecodeError: pass
    return {"is_complete": False, "completeness": 0.3, "goal": "", "extracted_dimensions": {},
            "missing_info": ["请提供更多信息"], "clarify_questions": [], "execution_plan": []}


def _parse_reflection_json(content: str) -> dict:
    import re
    try:
        result = json.loads(content)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, TypeError):
        pass
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(0))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
    return {"pass": False, "score": 0, "suggestions": ["质量检查返回了无效结果，请重新检查"]}


def _parse_checkpoint_json(content: str) -> dict:
    import re
    try: return json.loads(content)
    except json.JSONDecodeError: pass
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        try: return json.loads(match.group(0))
        except json.JSONDecodeError: pass
    return {"aligned": True, "score": 8}


def _fallback_plan(message: str, dimensions: dict) -> dict:
    # A failed model call cannot establish requirements from message length.
    # Ask for the core scenario without demanding a technical-stack selection.
    return normalize_plan({"response_mode": "clarify", "contract": {},
                           "extracted_dimensions": {}, "execution_plan": []})


def _merge_dimensions_from_plan(existing: dict, extracted: dict) -> dict:
    merged = dict(existing)
    for key, info in extracted.items():
        if isinstance(info, dict):
            value = info.get("value", "")
            confidence = info.get("confidence", 0.5)
        else:
            value = str(info) if info else ""
            confidence = 0.5
        if value and str(value) != "null":
            existing_conf = merged.get(f"{key}_confidence", 0)
            if isinstance(existing_conf, (int, float)) and confidence > existing_conf:
                merged[key] = value
                merged[f"{key}_confidence"] = confidence
            elif key not in merged:
                merged[key] = value
                merged[f"{key}_confidence"] = confidence
    return merged


def _generate_fallback_questions(module: str, expressed: dict, clarify_round: int, max_q: int = 5) -> list:
    if module == "work_arranger":
        return core_questions([field for field in ("goal", "scope.in", "main_flow", "acceptance")
                               if not expressed.get(field)])[:max_q]
    dims = MODULE_DIMENSIONS.get(module, {})
    _, gaps = calculate_completeness(expressed, dims)
    questions = []
    for gap in gaps[:max_q * 2]:
        templates = get_clarification_templates(gap["key"])
        if templates:
            text = templates[clarify_round % len(templates)]
        else:
            text = f"关于「{gap['label']}」，能再多说一些吗？"
        hint = get_dimension_hint(gap["key"])
        questions.append({"text": text, "dimension": gap["key"], "hint": hint})
    return questions[:max_q]


def _generate_contract_questions(contract: dict, clarify_round: int, max_q: int = 3) -> list:
    return core_questions(contract.get("missing_fields", []))[:max_q]



def _format_clarification_message(questions: list, completeness: float, rag_context: str = "", contract: dict = None, draft_outline=None) -> str:
    lines = []
    if contract and contract.get("goal"):
        lines.append(f"我理解你想做的是：{contract['goal']}。")
    if draft_outline:
        lines.append("先给你一个可以修改的理解轮廓：")
        lines.extend(f"- {item}" for item in draft_outline[:3] if str(item).strip())
    lines.append("先把实际用法说清楚，技术细节我会给简单的推荐。")
    lines.append("")
    for i, question in enumerate(questions[:3], 1):
        lines.append(f"{i}. {question.get('text', '')}")
        if question.get("hint"):
            lines.append(f"   {question['hint']}")
    return "\n".join(lines)



def _build_locked_block(intent: dict, dims_text: str, turn_count: int) -> str:
    """构建 🔴 已锁定意图 + 工作记忆块 — 最高优先级，不可偏离。

    这是解决意图偏移和信息遗忘的核心机制:
      - 意图在多轮对话中不会丢失
      - 用户已确认的需求维度形成工作记忆，跨轮持久化
    """
    lines = []

    # ── 🔴 已锁定意图 ──
    intent_label = intent.get("label", "")
    intent_scene = intent.get("scene", "")
    intent_confidence = intent.get("confidence", 0)

    if intent_label:
        lines.append("## 🔴 已锁定意图（最高优先级，不可偏离）")
        lines.append(f"- **当前任务**: {intent_label}")
        if intent_scene and intent_scene != intent_label:
            lines.append(f"- **场景**: {intent_scene}")
        if intent_confidence > 0:
            lines.append(f"- **置信度**: {intent_confidence:.0%}")
        lines.append("- **规则**: 以下所有回答必须围绕此意图。如果用户后续消息看似偏离，优先确认是否切换话题。")
        lines.append("")

    # ── 🔴 工作记忆（已确认的需求，不会丢失）──
    if dims_text and dims_text != "（尚未提取到任何维度信息）":
        lines.append("## 当前对话资料（明确要求与 default_assumptions 必须区分）")
        lines.append(dims_text)
        lines.append("")

    if lines:
        lines.insert(0, f"<!-- 第 {turn_count} 轮 -->")

    return "\n".join(lines)


async def _execute_legacy_skill(skill_instance, state: dict, model) -> str:
    from skills.base import SkillContext

    message = state.get("messages", [])
    if isinstance(message, list):
        msg_text = ""
        for m in reversed(message):
            role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "")
            content = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
            if role == "user":
                msg_text = content
                break
    else:
        msg_text = str(message)

    context = SkillContext(
        original_message=msg_text,
        expressed_dimensions=state.get("expressed_dimensions", {}),
        background=state.get("background", ""),
        rag_context=state.get("rag_context", ""),
        extra_context=state.get("extra_context", ""),
        completeness=state.get("completeness", 0),
    )
    return await skill_instance.execute(context, model)
