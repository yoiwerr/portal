"""
MakeItSmooth LangGraph 图定义 — V2 ReAct Agentic Loop + Router。

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
)

logger = logging.getLogger(__name__)

# ── 常量 ──
MAX_REFLECTION_RETRIES = 2
DEFAULT_MAX_TOOL_ROUNDS = 10
CLARIFY_THRESHOLD = 0.75
MAX_CLARIFY_ROUNDS = 5


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
    enriched_query: str           # RAG 用增强 query（原 query + 上下文拼接）
    tool_results: list
    output: str
    reflection_count: int
    intent: dict


# ── Skill System Prompt 映射 ──
_SKILL_SYSTEM_PROMPTS = {
    "prompt_refiner": PROMPT_REFINER_SYSTEM,
    "work_arranger": WORK_ARRANGER_SYSTEM,
    "info_retention": INFO_RETENTION_SYSTEM,
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
    在 RAG 检索前，用上下文补全用户的原始 query。

    不做 LLM 调用，纯规则拼接:
    - 已有维度信息（来自历史对话/追问轮次）
    - 意图对应的搜索关键词
    - 解决"那个项目"→"React博客项目"的指代问题

    拼接格式: [关键词] [上下文] [原始消息]
    """
    message = _get_last_user_message(state)
    intent = state.get("intent", {})
    expressed = state.get("expressed_dimensions", {})

    context_parts = []

    # 1. 从已有维度提取关键词
    for key, val in expressed.items():
        if key.endswith("_confidence"):
            continue
        if val and str(val) != "null" and len(str(val)) > 1:
            context_parts.append(str(val))

    # 2. 意图 → 搜索关键词
    scene = intent.get("scene", "")
    scene_keywords = {
        "prompt_optimize": "提示词优化 提示词工程 prompt engineering",
        "work_plan":       "工作安排 项目计划 任务分解 工作流",
        "info_organize":   "信息整理 知识管理 文档保存",
        "research":        "技术选型 方案对比 调研分析",
        "code_help":       "代码审查 调试 测试 重构",
    }
    if scene in scene_keywords:
        context_parts.append(scene_keywords[scene])

    # 可选: 拼背景
    bg = state.get("background", "")
    if bg and len(bg) > 3:
        context_parts.append(bg)

    # 拼接 enriched query
    if context_parts:
        enriched = " ".join(context_parts) + " " + message
    else:
        enriched = message

    # 去重去噪
    enriched = " ".join(dict.fromkeys(enriched.split()))  # 去重但保序
    enriched = enriched[:500]  # 限制长度，防止 embedding 稀释

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

    planner_prompt = f"""{PLANNER_SYSTEM_PROMPT}

## 当前模块: {module}
## 意图识别: {intent.get('label', '未知')} (置信度: {intent.get('confidence', 0)})

## 该模块的信息维度定义
{dims_desc}

## 用户背景
{background or "（未填写）"}

## 额外上下文
{extra_context or "（无）"}

{rag_context or ""}

## 已确认的信息
{existing_dims_text}

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

    full_system_prompt = f"""{skill_system}

{EXECUTOR_SYSTEM_PROMPT}

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

## 已确认的需求信息
{dims_text}
"""

    if skills and skill_name in skills:
        skill_instance = skills[skill_name]
    else:
        skill_instance = None

    from tools import get_tools_for_skill
    tools = get_tools_for_skill(skill_name)

    output = ""
    result = {}
    tool_results = []

    try:
        react_agent = create_react_agent(model=model, tools=tools, prompt=full_system_prompt)
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

    return {"output": output, "tool_results": tool_results}


# ============================================================
# 节点 4: Reflect
# ============================================================

async def reflect_node(state: AgentState, model=None) -> dict:
    output = state.get("output", "")
    plan = state.get("plan", {})
    message = _get_last_user_message(state)
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
        reflect_prompt = f"""{REFLECTOR_SYSTEM_PROMPT}

## 用户原始需求
{message}

## 期望完成的目标
{plan.get('goal', '完成用户请求')}

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


# ============================================================
# 构建图
# ============================================================

def create_graph(rag_service=None, skills=None, model=None):
    """
    构建 LangGraph 状态图 (V2 + Router)。

    流程: START → router → rag → planner → {clarify | execute → reflect → {execute | END}}
    """
    workflow = StateGraph(AgentState)

    async def _router(state):  return await router_node(state, model)
    async def _enrich(state): return enrich_query_node(state)
    async def _rag(state):     return await rag_retrieve_node(state, rag_service)
    async def _planner(state): return await planner_node(state, model, rag_service)
    async def _clarify(state): return await clarify_node(state, model)
    async def _execute(state): return await execute_node(state, skills, model)
    async def _reflect(state): return await reflect_node(state, model)

    workflow.add_node("router", _router)
    workflow.add_node("enrich", _enrich)
    workflow.add_node("rag", _rag)
    workflow.add_node("planner", _planner)
    workflow.add_node("clarify", _clarify)
    workflow.add_node("execute", _execute)
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
    workflow.add_edge("execute", "reflect")
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


def _generate_fallback_questions(module: str, expressed: dict, clarify_round: int, max_q: int = 3) -> list:
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
    if progress_pct < 30:    lines.append("我来帮你理清需求。先了解几个基本信息：\n")
    elif progress_pct < 55:  lines.append("很好，已经了解了基础信息。再补充几个细节：\n")
    elif progress_pct < 75:  lines.append("差不多了，最后确认几个点：\n")
    else:                    lines.append("信息基本齐了。\n")
    for i, q in enumerate(questions, 1):
        lines.append(f"**{i}.** {q['text']}")
        if q.get("hint"): lines.append(f"   *（{q['hint']}）*")
        lines.append("")
    if rag_context and "未找到" not in rag_context:
        lines.append("---\n（已从知识库中找到相关资料，会在生成时参考）")
    lines.append(f"---\n信息完整度: {progress_pct}%  |  本轮追问: {len(questions)} 个问题")
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
