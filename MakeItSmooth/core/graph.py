"""
MakeItSmooth LangGraph 图定义。

图的执行流程：
  START → rag_retrieve → extract_assess → 条件分支
                                                ├→ clarify → END (等待用户回答)
                                                └→ execute → END (最终输出)

每次用户发送一条消息，图运行一次。
多轮追问通过多次图调用来实现——每次调用时传入累积的 expressed_dimensions。
"""

import re
import json
from typing import TypedDict, Annotated, Literal

from langgraph.graph import StateGraph, END, START

from prompts.templates import (
    MODULE_DIMENSIONS,
    CLARIFICATION_TEMPLATES,
    build_dimensions_desc,
    format_expressed_dimensions,
)
from prompts.system_prompts import (
    PROMPT_REFINER_SYSTEM,
    WORK_ARRANGER_SYSTEM,
    INFO_RETENTION_SYSTEM,
    EXTRACT_SYSTEM_PROMPT,
)


# ============================================================
# 图状态定义
# ============================================================

class AgentState(TypedDict):
    """LangGraph 全局状态。图的每个节点读取并更新此状态。"""

    # 用户输入
    messages: list[dict]          # [{"role": "user", "content": "..."}]
    module: str                   # "prompt_refiner" | "work_arranger" | "info_retention"
    background: str               # 用户背景（来自共用面板）
    extra_context: str            # 从 MD 文件加载的额外上下文

    # 维度追踪（跨轮次累积）
    expressed_dimensions: dict    # {"purpose": "...", "purpose_confidence": 0.8, ...}
    clarify_round: int            # 当前追问轮数

    # 中间计算结果
    rag_context: str              # RAG 检索结果
    completeness: float           # 信息完整度（0-1）

    # 最终输出
    output: str                   # 展示给用户的消息


# ============================================================
# 图节点
# ============================================================

def _get_last_user_message(state: AgentState) -> str:
    """从状态中提取最后一条用户消息文本。"""
    msgs = state.get("messages", [])
    for m in reversed(msgs):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


async def rag_retrieve_node(state: AgentState, rag_service=None) -> dict:
    """
    节点1: RAG 知识检索。
    从 ChromaDB 中检索与用户消息相关的领域知识。
    """
    query = _get_last_user_message(state)
    if not query or rag_service is None:
        return {"rag_context": ""}

    ctx = rag_service.query_formatted(query)
    return {"rag_context": ctx}


async def extract_assess_node(state: AgentState, model=None) -> dict:
    """
    节点2: 维度提取 + 完整度评估。
    Phase 1: 用规则提取（关键词匹配）
    Phase 2: 用 LLM 提取（调用 model.invoke）

    返回: expressed_dimensions, completeness 的更新
    """
    message = _get_last_user_message(state)
    module = state.get("module", "prompt_refiner")

    # 获取该模块的维度定义
    dimensions = MODULE_DIMENSIONS.get(module, {})

    # Phase 1: 规则提取
    expressed = _rule_based_extract_dimensions(message, dimensions)

    # 合并历史维度
    existing = state.get("expressed_dimensions", {}) or {}
    expressed = _merge_dimensions(existing, expressed)

    # 计算完整度
    completeness, gaps = _calculate_completeness(expressed, dimensions)

    return {
        "expressed_dimensions": expressed,
        "completeness": completeness,
    }


async def clarify_node(state: AgentState, model=None) -> dict:
    """
    节点3: 生成追问。
    根据信息缺口生成 1-3 个精准追问。
    """
    module = state.get("module", "prompt_refiner")
    dimensions = MODULE_DIMENSIONS.get(module, {})
    expressed = state.get("expressed_dimensions", {})
    completeness = state.get("completeness", 0)
    clarify_round = state.get("clarify_round", 0)
    rag_context = state.get("rag_context", "")

    # 计算缺口
    _, gaps = _calculate_completeness(expressed, dimensions)

    # 生成追问
    questions = _generate_questions(gaps, clarify_round)

    # 格式化为用户友好的消息
    output = _format_clarification_message(questions, completeness, rag_context)

    return {
        "output": output,
        "clarify_round": clarify_round + 1,
    }


async def execute_node(state: AgentState, skills=None, model=None) -> dict:
    """
    节点4: 执行 Skill。
    调用对应 Skill（LangChain Agent + Tools 模式）生成最终输出。
    """
    from skills.base import SkillContext

    skill_name = state.get("module", "prompt_refiner")
    message = _get_last_user_message(state)

    dims_text = format_expressed_dimensions(state.get("expressed_dimensions", {}))
    completeness = state.get("completeness", 0)

    context = SkillContext(
        original_message=message,
        expressed_dimensions=state.get("expressed_dimensions", {}),
        background=state.get("background", ""),
        rag_context=state.get("rag_context", ""),
        extra_context=state.get("extra_context", ""),
        completeness=completeness,
    )

    if skills and skill_name in skills:
        skill_instance = skills[skill_name]
        skill_output = await skill_instance.execute(context, model)

        header = _format_execute_header(dims_text, completeness)
        output = header + "\n" + skill_output
    else:
        output = f"未知模块: {skill_name}"

    return {"output": output}


# ============================================================
# 条件路由
# ============================================================

def route_after_assess(state: AgentState) -> Literal["clarify", "execute"]:
    """
    根据完整度和追问轮数决定下一步：
    - 完整度 < 阈值 且 追问轮数 < 上限 → clarify
    - 否则 → execute
    """
    completeness = state.get("completeness", 0)
    clarify_round = state.get("clarify_round", 0)
    max_rounds = 5
    threshold = 0.75

    if completeness < threshold and clarify_round < max_rounds:
        return "clarify"
    return "execute"


# ============================================================
# 构建图
# ============================================================

def create_graph(rag_service=None, skills=None, model=None):
    """
    构建并编译 LangGraph 状态图。

    Args:
        rag_service: RAG 检索服务实例
        skills: Skill 字典 {"prompt_refiner": PromptRefiner(), ...}
        model: LangChain 兼容的 ChatModel（ChatOpenAI）

    Returns:
        编译好的 LangGraph Runnable
    """
    workflow = StateGraph(AgentState)

    # 添加节点（用闭包捕获依赖）
    async def _rag(state):
        return await rag_retrieve_node(state, rag_service)
    async def _assess(state):
        return await extract_assess_node(state, model)
    async def _clarify(state):
        return await clarify_node(state, model)
    async def _execute(state):
        return await execute_node(state, skills, model)

    workflow.add_node("rag", _rag)
    workflow.add_node("assess", _assess)
    workflow.add_node("clarify", _clarify)
    workflow.add_node("execute", _execute)

    # 添加边
    workflow.add_edge(START, "rag")
    workflow.add_edge("rag", "assess")
    workflow.add_conditional_edges(
        "assess",
        route_after_assess,
        {
            "clarify": "clarify",
            "execute": "execute",
        }
    )
    workflow.add_edge("clarify", END)
    workflow.add_edge("execute", END)

    return workflow.compile()


# ============================================================
# 维度提取（规则版，Phase 1）
# ============================================================

DIALOGUE_DIMENSION_DEFS = {
    "prompt_refiner": [
        ("purpose",         25, True,  [
            r'(?:目的|目标是?|想做|要(?:做|完成|生成)|希望|打算)[：:]*[【\[]*(.+?)(?:[】\]\n。，,]|$)',
        ]),
        ("output_style",    20, True,  [
            r'(?:风格)[：:]*[【\[]*(.{2,20})(?:[】\]\n。，,]|$)',
            r'风格(\S{2,20})(?:的|，|。|\n|$)',
            r'(?:简洁|详细|专业|幽默|正式|随意|创意|结构化|活泼|严谨|轻松)[^\n。，,]{0,10}',
        ]),
        ("target_model",    15, False, [
            r'(?:模型|LLM)[：:]*[【\[]*(.+?)(?:[】\]\n。，,]|$)',
            r'(?:用|使用|跑在)[【\[]*((?:Qwen|DeepSeek|Claude|GPT|Llama|Gemini|ChatGLM|Mistral|Gemma|Phi|Yi)[\w\-.]*)[^\n。，,]*',
        ]),
        ("constraints",     15, False, [
            r'(?:限制|约束|要求|必须|不能|不要|禁止)[：:]*[【\[]*(.+?)(?:[】\]\n。，,]|$)',
        ]),
        ("target_audience", 15, False, [
            r'(?:受众|面向|给|读者|观众|用户|人群|新手|专家)[：:]*[【\[]*(.{2,30})(?:[】\]\n。，,]|$)',
        ]),
        ("examples",        10, False, []),
    ],
    "work_arranger": [
        ("project_purpose", 25, True,  [
            r'(?:项目|目标|要做)[：:]*[【\[]*(.+?)(?:[】\]\n。，,]|$)',
            r'(?:做|完成|实现)(?:一个?|什么)?[【\[]*(.{2,40})(?:项目|任务|工作)',
        ]),
        ("scope",           15, True,  [
            r'(?:范围|规模|涉及)[：:]*[【\[]*(.+?)(?:[】\]\n。，,]|$)',
            r'(?:个人|团队|公司|开源)[^\n。，,]{0,10}',
        ]),
        ("time_constraint", 15, True,  [
            r'(?:时间|日期|周期|多久|周|月|天)[：:]*[【\[]*(.{2,30})(?:[】\]\n。，,]|$)',
            r'([一二两三四五六七八九十\d]+)\s*(?:天|周|个月|月|小时|日)',
            r'(?:大概|大约|预计)\s*([一二两三四五六七八九十\d]+\s*(?:天|周|个月|月|小时))',
        ]),
        ("deliverables",    15, True,  [
            r'(?:交付|产出|输出|成果|最终)[：:]*[【\[]*(.+?)(?:[】\]\n。，,]|$)',
        ]),
        ("resources",       15, False, [
            r'(?:资源|工具|预算|人员|利用)[：:]*[【\[]*(.+?)(?:[】\]\n。，,]|$)',
        ]),
        ("priority",        10, False, [
            r'(?:优先|重要|关键|核心|主要)[：:]*[【\[]*(.+?)(?:[】\]\n。，,]|$)',
        ]),
        ("constraints",      5, False, [
            r'(?:限制|约束|要求|必须|不能|不要)[：:]*[【\[]*(.+?)(?:[】\]\n。，,]|$)',
        ]),
    ],
    "info_retention": [
        ("content",         50, True,  [
            r'(?:留存|保存|整理|记录)[：:]*[【\[]*(.+?)(?:[】\]\n。，,]|$)',
        ]),
        ("format",          30, False, [
            r'(?:格式)[：:]*[【\[]*(.{2,20})(?:[】\]\n。，,]|$)',
        ]),
        ("usage",           20, False, [
            r'(?:用途|下次|使用)[：:]*[【\[]*(.+?)(?:[】\]\n。，,]|$)',
        ]),
    ],
}


def _rule_based_extract_dimensions(message: str, dimensions: dict) -> dict:
    """用正则规则从消息中提取已表达的维度。Phase 2 可替换为 LLM 调用。"""
    expressed = {}
    dim_defs = DIALOGUE_DIMENSION_DEFS.get(
        # 反向查找模块名
        _reverse_module_lookup(dimensions),
        []
    )

    for dim_key, _weight, _required, patterns in dim_defs:
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                value = match.group(1).strip() if match.lastindex else match.group(0).strip()
                if value and len(value) >= 2:
                    expressed[dim_key] = value[:100]
                    expressed[f"{dim_key}_confidence"] = 0.8
                    break

    return expressed


def _reverse_module_lookup(dimensions: dict) -> str:
    """根据维度字典反查模块名。"""
    from prompts.templates import MODULE_DIMENSIONS
    for name, dims in MODULE_DIMENSIONS.items():
        if dims == dimensions:
            return name
    return "prompt_refiner"


def _merge_dimensions(existing: dict, new: dict) -> dict:
    """合并新旧维度。confidence 更高的覆盖低的。"""
    merged = dict(existing)
    for key, value in new.items():
        if key.endswith("_confidence"):
            dim_key = key[:-len("_confidence")]
            existing_conf = existing.get(key, 0)
            if value > existing_conf:
                merged[key] = value
                if dim_key in new:
                    merged[dim_key] = new[dim_key]
        else:
            if key not in merged or not merged[key]:
                merged[key] = value
                merged[f"{key}_confidence"] = new.get(f"{key}_confidence", 0.5)
    return merged


def _calculate_completeness(expressed: dict, dimensions: dict) -> tuple[float, list]:
    """
    计算信息完整度。
    返回: (completeness, gaps_list)
    """
    total_weight = sum(d["weight"] for d in dimensions.values())
    covered_weight = 0.0
    gaps = []

    for key, dim in dimensions.items():
        if key in expressed and expressed[key]:
            confidence = expressed.get(f"{key}_confidence", 0.5)
            covered_weight += dim["weight"] * confidence
        else:
            gaps.append({
                "key": key,
                "label": dim["label"],
                "weight": dim["weight"],
                "is_required": dim.get("required", False),
            })

    completeness = covered_weight / total_weight if total_weight > 0 else 0
    gaps.sort(key=lambda g: (not g["is_required"], -g["weight"]))
    return completeness, gaps


# ============================================================
# 追问生成
# ============================================================

def _generate_questions(gaps: list, clarify_round: int, max_q: int = 3) -> list[dict]:
    """根据缺口生成追问列表。"""
    questions = []
    # 首轮优先问必填
    if clarify_round == 0:
        gaps = sorted(gaps, key=lambda g: (not g["is_required"], -g["weight"]))

    for gap in gaps[:6]:
        templates = CLARIFICATION_TEMPLATES.get(gap["key"], [])
        if templates:
            idx = clarify_round % len(templates)
            text = templates[idx]
        else:
            text = f"关于「{gap['label']}」，能再多说一些吗？"

        hint = _DIMENSION_HINTS.get(gap["key"], "")
        questions.append({"id": f"q_{gap['key']}", "text": text, "dimension": gap["key"], "hint": hint})

    return questions[:max_q]


_DIMENSION_HINTS = {
    "purpose": "比如：生成产品文案、写代码注释、翻译文档...",
    "target_model": "比如：Qwen3-8B、DeepSeek-R1、Claude...",
    "output_style": "简洁实用 / 详细教程 / 结构化 / 创意发散",
    "target_audience": "比如：技术团队、普通用户、管理层...",
    "project_purpose": "比如：学习新技术、搭建个人网站、团队效率工具...",
    "scope": "个人项目 / 团队协作 / 企业级",
    "time_constraint": "比如：1周内 / 1个月内 / 长期项目",
    "deliverables": "比如：代码仓库、上线网站、设计文档...",
}


def _format_clarification_message(questions: list, completeness: float, rag_context: str = "") -> str:
    """格式化追问消息。"""
    lines = []
    progress_pct = int(completeness * 100)

    if progress_pct < 30:
        lines.append("我来帮你理清需求。先了解几个基本信息：\n")
    elif progress_pct < 55:
        lines.append("很好，已经了解了基础信息。再补充几个细节：\n")
    elif progress_pct < 75:
        lines.append("差不多了，最后确认几个点：\n")
    else:
        lines.append("信息基本齐了。\n")

    for i, q in enumerate(questions, 1):
        lines.append(f"**{i}.** {q['text']}")
        if q.get("hint"):
            lines.append(f"   *（{q['hint']}）*")
        lines.append("")

    # 如果 RAG 有相关知识，简要提示
    if rag_context and "未找到" not in rag_context:
        lines.append("---")
        lines.append("（已从知识库中找到相关资料，会在生成时参考）")

    lines.append(f"---")
    lines.append(f"信息完整度: {progress_pct}%  |  本轮追问: {len(questions)} 个问题")

    return "\n".join(lines)


def _format_execute_header(dims_text: str, completeness: float) -> str:
    """格式化执行前的头部信息。"""
    lines = [
        "需求分析完成，开始生成结果...\n",
        f"信息完整度: {int(completeness * 100)}%",
    ]
    if dims_text and "未提取" not in dims_text:
        lines.append(f"\n已确认的信息:\n{dims_text}")
    lines.append("\n---\n")
    return "\n".join(lines)
