"""
所有 Prompt 模板和维度定义。

V2: 移除硬编码正则 (DIALOGUE_DIMENSION_DEFS)。
    维度提取改为 LLM structured output，此文件仅保留维度定义和工具函数。
    追问模板作为 Planner 的参考上下文使用。
"""

from typing import List, Dict, Any


# ============================================================
# 信息维度定义（每个模块有哪些维度需要补全）
# 用作 LLM Planner 的上下文，指导它从用户消息中提取哪些维度
# ============================================================

PROMPT_REFINER_DIMENSIONS = {
    "purpose": {
        "label": "核心目的",
        "weight": 0.25,
        "required": True,
        "hint": "这个提示词要完成什么任务？"
    },
    "target_model": {
        "label": "目标模型",
        "weight": 0.15,
        "required": False,
        "hint": "准备在哪个模型上使用？（如 Qwen、DeepSeek、Claude 等）"
    },
    "output_style": {
        "label": "输出风格",
        "weight": 0.20,
        "required": True,
        "hint": "简洁实用 / 详细教程 / 创意发散 / 结构化报告？"
    },
    "constraints": {
        "label": "约束条件",
        "weight": 0.15,
        "required": False,
        "hint": "字数/格式/语言/安全限制等"
    },
    "target_audience": {
        "label": "目标受众",
        "weight": 0.15,
        "required": False,
        "hint": "这个提示词的输出是给谁看的？"
    },
    "examples": {
        "label": "参考示例",
        "weight": 0.10,
        "required": False,
        "hint": "有没有期望的输出参考？"
    },
}

WORK_ARRANGER_DIMENSIONS = {
    "project_purpose": {
        "label": "项目目的",
        "weight": 0.25,
        "required": True,
        "hint": "做这个项目/任务的核心目标是什么？"
    },
    "scope": {
        "label": "项目范围",
        "weight": 0.15,
        "required": True,
        "hint": "是大项目还是小任务？个人还是团队？"
    },
    "time_constraint": {
        "label": "时间约束",
        "weight": 0.15,
        "required": True,
        "hint": "什么时候需要完成？"
    },
    "resources": {
        "label": "可用资源",
        "weight": 0.15,
        "required": False,
        "hint": "有什么工具、人员、预算可用？"
    },
    "deliverables": {
        "label": "交付物",
        "weight": 0.15,
        "required": True,
        "hint": "最终要产出什么？代码、文档、设计图？"
    },
    "priority": {
        "label": "优先级",
        "weight": 0.10,
        "required": False,
        "hint": "哪些是必须做的，哪些可以延后？"
    },
    "constraints": {
        "label": "特殊约束",
        "weight": 0.05,
        "required": False,
        "hint": "技术限制、合规要求、依赖条件等"
    },
}

INFO_RETENTION_DIMENSIONS = {
    "content": {
        "label": "留存内容",
        "weight": 0.50,
        "required": True,
        "hint": "想保存什么信息？"
    },
    "format": {
        "label": "输出格式",
        "weight": 0.30,
        "required": False,
        "hint": "Markdown 文档 / 结构化数据 / 纯文本？"
    },
    "usage": {
        "label": "后续用途",
        "weight": 0.20,
        "required": False,
        "hint": "下次什么时候用？怎么用？"
    },
}

# 模块 → 维度映射
MODULE_DIMENSIONS: Dict[str, Dict] = {
    "prompt_refiner": PROMPT_REFINER_DIMENSIONS,
    "work_arranger": WORK_ARRANGER_DIMENSIONS,
    "info_retention": INFO_RETENTION_DIMENSIONS,
}


# ============================================================
# 追问模板（参考用 — Planner 可以从中选问题也可以自己编）
# ============================================================

CLARIFICATION_TEMPLATES: Dict[str, List[str]] = {
    # 提示词工程相关
    "purpose": [
        "你做这个的主要目的是什么？想让 AI 帮你完成什么任务？",
        "能再具体说说你想达到的效果吗？",
    ],
    "target_model": [
        "你打算用哪个模型来运行这个提示词？不同的模型适合不同的提示策略。",
        "有计划在特定模型上使用吗？比如 Qwen、DeepSeek、Claude 等？",
    ],
    "output_style": [
        "你偏好什么样的输出风格？简洁实用还是详细教程式？",
        "输出需要特定的格式吗？比如要不要分步骤、要不要带示例？",
    ],
    "constraints": [
        "对输出有什么限制吗？比如字数、语言、需要避免的内容？",
        "有没有特别需要注意的约束条件？",
    ],
    "target_audience": [
        "这个提示词的输出是给谁看的？对技术要求高吗？",
        "目标受众是什么水平？新手、熟练者还是专家？",
    ],
    "examples": [
        "有没有你期望的参考示例或输出样本？",
        "有没有类似的优质输出可以参考？",
    ],

    # 工作安排相关
    "project_purpose": [
        "做这个项目的核心目标是什么？解决了什么问题？",
        "能跟我多说一下这个项目的背景和初衷吗？",
    ],
    "scope": [
        "这个项目大概的规模和范围？是个人项目还是团队协作？",
        "涉及到多少个模块/功能点？",
    ],
    "time_constraint": [
        "时间上有什么限制吗？有没有明确的截止日期？",
        "是全职投入还是业余时间做？大概每周能投入多长时间？",
    ],
    "resources": [
        "有哪些现成的资源可以利用？工具、文档、人员？",
        "有没有可以参考的类似项目或资料？",
    ],
    "deliverables": [
        "最终要产出什么？代码、设计稿、文档，还是其他？",
        "有没有确定的交付物清单？",
    ],
    "priority": [
        "哪些是最重要的、必须优先完成的？",
        "如果时间不够，哪些功能可以延后到后续版本？",
    ],

    # 信息留存相关
    "content": [
        "你想保存哪些信息？对话记录、生成的提示词、还是工作计划？",
        "方便说下这些信息的来源和用途吗？",
    ],
    "format": [
        "你希望以什么格式保存？Markdown 文档、表格还是纯文本？",
        "有偏好的文档结构吗？",
    ],
    "usage": [
        "这些信息下次会在什么场景下使用？",
        "你希望再次使用时能快速找到哪些关键信息？",
    ],
}

# ============================================================
# 维度提示（用于追问时给用户举例）
# ============================================================

DIMENSION_HINTS: Dict[str, str] = {
    "purpose": "比如：生成产品文案、写代码注释、翻译文档...",
    "target_model": "比如：Qwen3-8B、DeepSeek-R1、Claude...",
    "output_style": "简洁实用 / 详细教程 / 结构化 / 创意发散",
    "target_audience": "比如：技术团队、普通用户、管理层...",
    "project_purpose": "比如：学习新技术、搭建个人网站、团队效率工具...",
    "scope": "个人项目 / 团队协作 / 企业级",
    "time_constraint": "比如：1周内 / 1个月内 / 长期项目",
    "deliverables": "比如：代码仓库、上线网站、设计文档...",
}


# ============================================================
# 工具函数
# ============================================================

def build_dimensions_desc(dimensions: dict) -> str:
    """将维度字典转为可读的描述文本。"""
    lines = []
    for key, dim in dimensions.items():
        required = "（必填）" if dim.get("required") else "（可选）"
        lines.append(f"- {key}: {dim['label']}{required} — {dim.get('hint', '')}")
    return "\n".join(lines)


def format_expressed_dimensions(dimensions: dict) -> str:
    """将已表达的维度格式化为人类可读的列表。"""
    lines = []
    for key, value in dimensions.items():
        if key.endswith("_confidence"):
            continue
        if value and str(value) != "null":
            conf = dimensions.get(f"{key}_confidence", 0.5)
            if isinstance(conf, (int, float)):
                conf_icon = "✅" if conf > 0.7 else "🤔" if conf > 0.3 else "❓"
            else:
                conf_icon = "🤔"
            lines.append(f"- {conf_icon} **{key}**: {value}")
    return "\n".join(lines) if lines else "（尚未提取到任何维度信息）"


def get_dimension_hint(dim_key: str) -> str:
    """获取某个维度的提示文本。"""
    return DIMENSION_HINTS.get(dim_key, "")


def get_clarification_templates(dim_key: str) -> List[str]:
    """获取某个维度的追问模板。"""
    return CLARIFICATION_TEMPLATES.get(dim_key, [f"关于「{dim_key}」，能再多说一些吗？"])


def calculate_completeness(expressed: dict, dimensions: dict) -> tuple:
    """
    计算信息完整度（保留原有逻辑，用于快速检查）。

    返回: (completeness, gaps_list)
    """
    total_weight = sum(d["weight"] for d in dimensions.values())
    covered_weight = 0.0
    gaps = []

    for key, dim in dimensions.items():
        if key in expressed and expressed[key]:
            confidence = expressed.get(f"{key}_confidence", 0.5)
            if isinstance(confidence, (int, float)):
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
