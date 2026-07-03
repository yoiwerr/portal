"""
所有 Prompt 模板（中文）。
包含：追问模板、执行模板、分类模板、提取模板。
"""

import json
from typing import List

# ============================================================
# 信息维度定义（每个模块有哪些维度需要补全）
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
MODULE_DIMENSIONS = {
    "prompt_refiner": PROMPT_REFINER_DIMENSIONS,
    "work_arranger": WORK_ARRANGER_DIMENSIONS,
    "info_retention": INFO_RETENTION_DIMENSIONS,
}


# ============================================================
# 追问模板（每个维度预置追问话术）
# ============================================================

CLARIFICATION_TEMPLATES = {
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
# 模块执行 Prompt 模板
# ============================================================

PROMPT_REFINER_EXECUTION_TEMPLATE = """你是一个专业的 AI 提示词优化师。请根据以下信息，生成 2-3 个优化后的提示词版本。

## 用户背景
{background}

## 原始提示词/需求
{original_message}

## 已确认的需求信息
{expressed_dimensions}

## 知识库参考
{rag_context}

## 输出要求
请严格按照以下格式输出（每个版本用 ## 分隔）：

## 版本 A - [版本名称]
**策略**: [使用的提示词策略，如 Chain-of-Thought / Few-Shot / 角色扮演]
**推荐模型**: [适用模型名称]
**风格**: [简洁实用 / 详细教程 / 创意发散 / 结构化报告]

```
[完整的优化提示词文本]
```

**为什么选这个版本**: [一句话理由]

---

## 版本 B - [版本名称]
(同上格式)

---

## 版本 C - [版本名称] (可选)
(同上格式)

## 💡 使用建议
- 如果目标是 XX，推荐版本 A
- 如果想要 YY 效果，推荐版本 B
- ...
"""

WORK_ARRANGER_EXECUTION_TEMPLATE = """你是一个工作流程规划专家。请根据以下信息，生成完整的项目工作计划。

## 项目背景
{background}

## 工作需求
{original_message}

## 已确认的需求信息
{expressed_dimensions}

## 知识库参考
{rag_context}

## 输出要求
请按以下结构输出完整的 Markdown 工作计划：

### 📋 项目概述
（一句话概述项目目标和范围）

### ⚠️ 不确定性声明
（信息不够确定的维度用 *斜体* 标注，并给出 "如果...则..." 的建议）

### 📊 阶段划分与任务

| 阶段 | 任务 | 预估时间 | 优先级 | 依赖 |
|------|------|---------|--------|------|
| Phase 1: ... | ... | ... | 🔴高 | - |
| Phase 2: ... | ... | ... | 🟡中 | Phase 1 |

### 🛠 工具与资源推荐
- **工具名称**: 推荐理由和链接（如有）
- ...

### ⚡ 风险与注意事项
1. ...
2. ...

### 🎯 MVP 范围
（哪些是第一个版本必须包含的）

### 📅 建议时间线
```
Week 1: ...
Week 2: ...
...
```

### 🚀 下一步行动
1. **立刻可以做**: ...
2. **本周内**: ...
3. **下周**: ...

---

> 💡 搜索功能将在 Phase 2 集成，届时可获取最新工具和资源信息。
"""

INFO_RETENTION_EXECUTION_TEMPLATE = """你是一个信息整理和知识管理助手。请将以下信息整理为结构化文档。

## 用户背景
{background}

## 留存需求
{original_message}

## 已确认的需求信息
{expressed_dimensions}

## 知识库参考
{rag_context}

## 额外上下文（从加载的文件中读取）
{extra_context}

## 输出要求
输出一份结构化的 Markdown 文档，包含：

### 📌 核心信息
（最重要的内容摘要）

### 📝 详细内容
（完整信息，保持用户原意）

### � 关键决策点
（如果有的话）

### 🔄 下次使用时关注
- ...
- ...

### 📅 时效性标注
- 适用时间范围: ...
- 建议复查周期: ...
"""


# ============================================================
# 维度提取 Prompt
# ============================================================

EXTRACT_DIMENSIONS_PROMPT = """从以下用户消息中提取已明确表达的信息维度。

维度定义:
{dimensions_desc}

用户消息:
{message}

请以 JSON 格式输出。对每个维度：
- 如果用户明确提到了，输出提取的值
- 如果用户暗示了但没有明确说，输出值并标记 confidence 为 0.3-0.5
- 如果完全没有提到，输出 null

输出格式（只输出 JSON，不要其他任何内容）:
{{
  "dimension_key": "提取的值或null",
  "dimension_key_confidence": 0.9
}}

注意：
- confidence 表示你对这个维度提取的确定程度（0=完全不确定, 1=非常确定）
- 只在用户明确表达的情况下给高 confidence
"""


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
        if value and value != "null":
            conf = dimensions.get(f"{key}_confidence", 0.5)
            conf_icon = "✅" if conf > 0.7 else "🤔"
            lines.append(f"- {conf_icon} **{key}**: {value}")
    return "\n".join(lines) if lines else "（尚未提取到任何维度信息）"
