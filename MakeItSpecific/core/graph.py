"""
MakeItSpecific LangGraph 图定义 — V2 ReAct Agentic Loop + Router。

图的执行流程:
  START → router (意图识别)
              │
              ▼
          rag → planner (LLM 提取维度 + 判断完整度)
              ├→ clarify (生成追问 → END)
              └→ execute (ReAct tool calling loop)
                      └→ reflect (质量检查)
                              ├→ 不够好 → 回 executor
                              └→ 通过 → END
"""

import json
import logging
from typing import TypedDict, Annotated, Literal, Optional

from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import create_react_agent
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from prompts.templates import (
    MODULE_DIMENSIONS,
    build_dimensions_desc,
    format_expressed_dimensions,
    calculate_completeness,
    get_dimension_hint,
    get_clarification_templates,
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

# ── 常量 ──
MAX_REFLECTION_RETRIES = 2
DEFAULT_MAX_TOOL_ROUNDS = 10
CLARIFY_THRESHOLD = 0.75
MAX_CLARIFY_ROUNDS = 3
MAX_CHECKPOINT_RETRIES = 1     # checkpoint 失败最多重试 1 次


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
    # ── Planner 升级: checkpoint ──
    checkpoint_feedback: str      # Planner 中途检查的语义修正意见
    checkpoint_retry_count: int   # checkpoint→execute 重试次数 (独立于 reflection)
    # ── 执行进度追踪 ──
    completed_steps: list[str]    # 已完成的执行步骤（用于重试时知道做到哪了）
    execute_round: int            # 当前执行轮次（checkpoint→execute 重试时递增）


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
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", None)
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
        if role == "user":
            return content
    return ""


# ============================================================
# 节点 0: Router — 意图识别
# ============================================================

async def router_node(state: AgentState, model=None) -> dict:
    """
    节点0: Router — 判断用户意图，自动选择模块。

    只在 module="auto" 时运行（用户未手动选模块）。
    如果用户已经选了模块（如 "prompt_refiner"），跳过。
    """
    module = state.get("module", "auto")

    # 已经指定了具体模块 → 跳过路由
    if module and module != "auto":
        logger.info(f"[Router] 跳过: 用户已指定 module={module}")
        return {"intent": {"scene": module, "module": module, "label": module, "confidence": 1.0}}

    message = _get_last_user_message(state)
    if not message:
        return {"intent": {"scene": "general", "module": "prompt_refiner", "label": "通用对话", "confidence": 0.5}}

    # 规则快速分类（零延迟 fallback）
    from core.router import route_intent_sync
    intent = route_intent_sync(message, model)

    # 如果规则置信度低且 LLM 可用 → LLM 精判
    if model and intent.get("confidence", 0) < 0.8:
        try:
            from core.router import route_intent
            intent = await route_intent(message, model)
        except Exception as e:
            logger.warning(f"[Router] LLM 分类失败, 使用规则结果: {e}")

    logger.info(
        f"[Router] scene={intent['scene']} module={intent['module']} "
        f"label={intent['label']} confidence={intent['confidence']}"
    )

    # Router 输出更新 module
    return {
        "intent": intent,
        "module": intent["module"],
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
    # 优先用 enriched_query，fallback 到原始消息
    query = state.get("enriched_query", "") or _get_last_user_message(state)
    if not query or rag_service is None:
        return {"rag_context": ""}
    existing = state.get("rag_context", "")
    if existing:
        return {}
    try:
        ctx = await rag_service.query_formatted(query)
    except Exception:
        ctx = ""
    return {"rag_context": ctx}


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

    planner_prompt = f"""{PLANNER_SYSTEM_PROMPT}

{context_block}
## 该模块的信息维度定义
{dims_desc}

## 用户背景
{background or "（未填写）"}

## 额外上下文
{extra_context or "（无）"}

{rag_context or ""}

## 用户最新消息
{message}

请分析这条消息，输出 JSON。如果用户的消息包含指代词或信息不完整，优先追问。"""

    try:
        structured_model = model.bind(response_format={"type": "json_object"})
        response = await structured_model.ainvoke([
            SystemMessage(content=planner_prompt),
            HumanMessage(content="请输出 JSON 分析结果。"),
        ])
        plan = _parse_planner_json(response.content)
    except Exception as e:
        logger.warning(f"[Planner] LLM 失败，降级: {e}")
        plan = _fallback_plan(message, dimensions)

    new_dims = _merge_dimensions_from_plan(existing_dims, plan.get("extracted_dimensions", {}))

    rag_updated = state.get("rag_context", "")
    if rag_service and not rag_updated:
        try:
            rag_updated = await rag_service.query_formatted(message)
        except Exception:
            rag_updated = ""

    return {
        "plan": plan,
        "expressed_dimensions": new_dims,
        "rag_context": rag_updated,
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

    questions = plan.get("clarify_questions", [])
    if not questions:
        questions = _generate_fallback_questions(module, expressed, clarify_round)

    output = _format_clarification_message(questions, completeness, rag_context)

    return {
        "output": output,
        "clarify_round": clarify_round + 1,
    }


# ============================================================
# 节点 3: Execute — ReAct Agent
# ============================================================

async def execute_node(state: AgentState, skills=None, model=None) -> dict:
    skill_name = state.get("module", "prompt_refiner")
    plan = state.get("plan", {})
    background = state.get("background", "")
    rag_context = state.get("rag_context", "")
    extra_context = state.get("extra_context", "")
    expressed = state.get("expressed_dimensions", {})
    message = _get_last_user_message(state)

    skill_system = _SKILL_SYSTEM_PROMPTS.get(skill_name, PROMPT_REFINER_SYSTEM)
    dims_text = format_expressed_dimensions(expressed)

    # ── 三层上下文注入 ──
    l2_summary = state.get("l2_summary", "")
    l1_raw = state.get("l1_raw", "")
    l3_facts = state.get("l3_facts", "")
    last_turn_summary = state.get("last_turn_summary", "")
    checkpoint_feedback = state.get("checkpoint_feedback", "")

    # ── 🔴 已锁定意图 + 工作记忆（最高优先级，先注入）──
    intent = state.get("intent", {})
    locked_block = _build_locked_block(intent, dims_text, state.get("turn_count", 0))

    exec_context_block = locked_block  # 意图+工作记忆放最前面
    if l2_summary:
        exec_context_block += "\n## 🔴 前情提要（滚动摘要）\n" + str(l2_summary) + "\n"
    if l1_raw:
        label = "🟡" if l2_summary else "🟢"
        exec_context_block += "\n## " + label + " 最近对话\n" + str(l1_raw) + "\n"
    if l3_facts:
        exec_context_block += "\n## 🟢 历史语义事实\n" + str(l3_facts) + "\n"
    if checkpoint_feedback:
        exec_context_block += (
            "\n## ⚠️ Planner 语义修正\n"
            "上次执行偏离了方向，请根据以下反馈调整:\n" +
            str(checkpoint_feedback) + "\n"
        )

    full_system_prompt = f"""{skill_system}

{EXECUTOR_SYSTEM_PROMPT}
{exec_context_block}
## 当前任务的上下文
- 目标: {plan.get('goal', '完成用户请求')}
- 执行步骤: {json.dumps(plan.get('execution_plan', []), ensure_ascii=False)}

## 用户背景
{background or "（未填写）"}

## 知识库参考
{rag_context or "（无）"}

## 额外上下文
{extra_context or "（无）"}

## 用户原始需求
{message}
"""

    if skills and skill_name in skills:
        skill_instance = skills[skill_name]
    else:
        skill_instance = None

    from tools import get_tools_for_skill
    tools = get_tools_for_skill(skill_name)

    # ── 执行进度: 如果是从 checkpoint/reflect 重试，告诉 Executor 已经做完了哪些步骤 ──
    completed = state.get("completed_steps", []) or []
    execute_round = state.get("execute_round", 0)
    progress_text = ""
    if completed:
        progress_text = f"\n## 📍 执行进度（第 {execute_round} 轮）\n已完成步骤: {', '.join(completed)}\n如果上述步骤的结果仍然有效，不要重复执行——直接从下一步继续。"

    full_system_prompt = f"""{skill_system}

{EXECUTOR_SYSTEM_PROMPT}{progress_text}
{exec_context_block}
## 当前任务的上下文
- 目标: {plan.get('goal', '完成用户请求')}
- 执行步骤: {json.dumps(plan.get('execution_plan', []), ensure_ascii=False)}

## 用户背景
{background or "（未填写）"}

## 知识库参考
{rag_context or "（无）"}

## 额外上下文
{extra_context or "（无）"}

## 用户原始需求
{message}
"""

    output = ""
    result = {}
    tool_results = []

    try:
        # ── 并行 tool call: 如果底层模型支持（Qwen/DeepSeek），同一轮可以输出多个 tool_call ──
        parallel_model = model.bind_tools(tools, parallel_tool_calls=True)
        react_agent = create_react_agent(model=parallel_model, tools=tools, prompt=full_system_prompt)
        result = await react_agent.ainvoke({"messages": [HumanMessage(content=message)]})

        output_messages = result.get("messages", [])
        for m in reversed(output_messages):
            if isinstance(m, AIMessage) and m.content:
                output = m.content
                break

        if not output and skill_instance:
            output = await _execute_legacy_skill(skill_instance, state, model)

    except Exception as e:
        logger.error(f"[Execute] ReAct Agent 失败: {e}", exc_info=True)
        if skill_instance:
            output = await _execute_legacy_skill(skill_instance, state, model)
        else:
            output = f"执行出错: {str(e)}"

    if isinstance(result, dict):
        for m in result.get("messages", []):
            if hasattr(m, "tool_calls") and m.tool_calls:
                for tc in m.tool_calls:
                    tool_results.append({"name": tc.get("name", "unknown"), "args": tc.get("args", {})})

    # ── 执行进度追踪: 标记本轮完成了哪些 plan 步骤 ──
    new_completed = list(completed)
    plan_steps = plan.get("execution_plan", [])
    if plan_steps and output:
        for step in plan_steps:
            if step not in new_completed:
                new_completed.append(step)

    return {
        "output": output,
        "tool_results": tool_results,
        "completed_steps": new_completed,
        "execute_round": execute_round + 1,
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

## 执行进度
已完成步骤: {', '.join(state.get('completed_steps', []) or []) or '（无记录）'}
执行轮次: 第 {state.get('execute_round', 0)} 轮

## 用户的原始消息
{message}
{context_block}
## 知识库参考（判断技术声明是否有依据）
{rag_brief}

## Executor 的实际输出（前 1500 字符）
{output[:1500]}

请评估语义对齐程度，输出 JSON。"""

        structured_model = model.bind(response_format={"type": "json_object"})
        response = await structured_model.ainvoke([
            SystemMessage(content=checkpoint_prompt),
            HumanMessage(content="请评估语义对齐程度，输出 JSON。"),
        ])
        checkpoint = _parse_checkpoint_json(response.content)
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
    message = _get_last_user_message(state)
    rag_context = state.get("rag_context", "")
    reflection_count = state.get("reflection_count", 0)

    if not output or len(output.strip()) < 50:
        if reflection_count < MAX_REFLECTION_RETRIES:
            return {
                "reflection_count": reflection_count + 1,
                "plan": {**plan, "retry_reason": "输出过短或不完整"},
            }
        return {"reflection_count": reflection_count}

    if reflection_count >= MAX_REFLECTION_RETRIES:
        return {"reflection_count": reflection_count}

    try:
        rag_brief = rag_context[:800] if rag_context else "（无知识库参考）"

        reflect_prompt = f"""{REFLECTOR_SYSTEM_PROMPT}

## 用户原始需求
{message}

## 期望完成的目标
{plan.get('goal', '完成用户请求')}

## 知识库参考（判断技术声明是否有依据）
{rag_brief}

## 实际输出（前 2000 字符）
{output[:2000]}

请评估这段输出是否满足用户需求。输出 JSON。"""

        structured_model = model.bind(response_format={"type": "json_object"})
        response = await structured_model.ainvoke([
            SystemMessage(content=reflect_prompt),
            HumanMessage(content="请评估输出质量，输出 JSON。"),
        ])
        reflection = _parse_reflection_json(response.content)
    except Exception as e:
        logger.warning(f"[Reflector] LLM 失败: {e}")
        reflection = {"pass": True, "score": 7}

    if reflection.get("pass", True):
        return {"reflection_count": reflection_count}
    else:
        retry_hint = reflection.get("suggestions", ["请改进输出质量"])
        return {
            "reflection_count": reflection_count + 1,
            "plan": {**plan, "retry_reason": "; ".join(retry_hint)},
        }


# ============================================================
# 条件路由
# ============================================================

def route_after_planner(state: AgentState) -> Literal["clarify", "execute"]:
    plan = state.get("plan", {})
    clarify_round = state.get("clarify_round", 0)
    if not plan.get("is_complete", False) and clarify_round < MAX_CLARIFY_ROUNDS:
        return "clarify"
    return "execute"


def route_after_reflect(state: AgentState) -> Literal["execute", "__end__"]:
    plan = state.get("plan", {})
    reflection_count = state.get("reflection_count", 0)
    if plan.get("retry_reason") and reflection_count < MAX_REFLECTION_RETRIES:
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

def create_graph(rag_service=None, skills=None, model=None):
    """
    构建 LangGraph 状态图 (V3 — Planner 语义中枢 + 三层上下文)。

    流程:
      START → router → enrich → rag → planner → {clarify | execute}
                                                        ↓
                                                  execute → checkpoint → {reflect | execute}
                                                                              ↓
                                                                        reflect → {execute | END}

    Planner 升级:
      旧 (V2): Planner 只在开头分析一次 → 然后不管了
      新 (V3): Planner 通过 checkpoint_node 在每次 Executor 完成后介入，
              检查语义对齐。如果方向跑偏了，立即给出修正意见 → 回 execute 重试。
              这是一种「持续语义监控」而非一次性分析。
    """
    workflow = StateGraph(AgentState)

    async def _router(state):     return await router_node(state, model)
    async def _enrich(state):     return enrich_query_node(state)
    async def _rag(state):        return await rag_retrieve_node(state, rag_service)
    async def _planner(state):    return await planner_node(state, model, rag_service)
    async def _clarify(state):    return await clarify_node(state, model)
    async def _execute(state):    return await execute_node(state, skills, model)
    async def _checkpoint(state): return await checkpoint_node(state, model)
    async def _reflect(state):    return await reflect_node(state, model)

    workflow.add_node("router", _router)
    workflow.add_node("enrich", _enrich)
    workflow.add_node("rag", _rag)
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
        {"clarify": "clarify", "execute": "execute"},
    )
    workflow.add_edge("clarify", END)
    # ── V3: execute → checkpoint → {reflect | execute} ──
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
    try: return json.loads(content)
    except json.JSONDecodeError: pass
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        try: return json.loads(match.group(0))
        except json.JSONDecodeError: pass
    return {"pass": True, "score": 7}


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
    msg_len = len(message)
    if msg_len < 20:
        return {"is_complete": False, "completeness": 0.2, "goal": "", "extracted_dimensions": {},
                "missing_info": ["需求描述太短"], "clarify_questions": [
                    {"text": "能再详细说说你想做什么吗？", "dimension": "purpose", "hint": "越具体越好"}
                ], "execution_plan": []}
    elif msg_len < 100:
        return {"is_complete": False, "completeness": 0.4, "goal": message[:50], "extracted_dimensions": {},
                "missing_info": ["需要更多细节"], "clarify_questions": [
                    {"text": "能说具体要求吗？比如风格、格式、时间？", "dimension": "details", "hint": ""}
                ], "execution_plan": []}
    else:
        return {"is_complete": True, "completeness": 0.8, "goal": message[:100], "extracted_dimensions": {},
                "missing_info": [], "clarify_questions": [], "execution_plan": ["直接基于用户输入执行"]}


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


def _format_clarification_message(questions: list, completeness: float, rag_context: str = "") -> str:
    lines = []
    progress_pct = int(completeness * 100)
    if progress_pct < 40:
        lines.append("还差一些信息，请帮忙补充：\n")
    elif progress_pct < 70:
        lines.append("再确认几个细节：\n")
    else:
        lines.append("最后确认：\n")

    for i, q in enumerate(questions, 1):
        lines.append(f"**{i}.** {q['text']}")
        lines.append("")

    lines.append(f"（进度 {progress_pct}%）")
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
        lines.append("## 🔴 工作记忆（已确认的需求信息，跨轮持久化，不会丢失）")
        lines.append(dims_text)
        lines.append("")

    if lines:
        lines.insert(0, f"<!-- 第 {turn_count} 轮 -->")

    return "\n".join(lines)


async def _execute_legacy_skill(skill_instance, state: dict, model) -> str:
    from langchain.agents import create_agent
    from langchain_core.messages import SystemMessage, HumanMessage
    from tools import get_tools_for_skill
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
