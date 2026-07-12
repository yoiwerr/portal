"""
意图识别 Router — 替代手动选模块。

纯 LLM 文本分类，不需要 tool、MCP、Agent Loop。
一次 bare model.invoke() 判断用户想干什么。

场景代码:
  - prompt_optimize → 写/改/优化提示词
  - work_plan       → 规划项目/安排任务
  - info_organize   → 整理信息/保存文档
  - research        → 调研/搜索/对比分析
  - code_help       → 审查代码/写测试/重构
  - general         → 闲聊或无法归类

模块映射:
  prompt_optimize → prompt_refiner
  work_plan       → work_arranger
  info_organize   → info_retention
  research        → work_arranger (先当工作计划处理)
  code_help       → prompt_refiner (先当提示词处理)
  general         → prompt_refiner (默认)

用法:
    intent = await route_intent("帮我写个提示词", model)
    # → "prompt_optimize"
"""

import re
import logging

from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

# ── 场景定义 ──

ROUTER_SYSTEM_PROMPT = """你是一个意图分类器。分析用户输入，判断属于哪个场景。

场景定义（只输出场景代码，不要解释）:

- prompt_optimize: 写/改/优化 AI 提示词；生成产品文案/营销文案/翻译；润色文字
- work_plan: 规划项目；安排任务/排期；设计工作流；评估方案可行性
- info_organize: 整理/保存/导出信息；总结对话；记录决策；留存知识
- research: 调研技术选型；对比方案/产品；搜索最新资讯；出调研报告
- code_help: 审查代码；找 bug；写测试；重构建议；解释代码逻辑
- general: 闲聊、问候、无法归类的其他问题

用户: {message}
场景: """

# ── 场景 → 模块映射 ──

SCENE_TO_MODULE = {
    "prompt_optimize": "prompt_refiner",
    "work_plan": "work_arranger",
    "info_organize": "info_retention",
    "research": "work_arranger",       # 调研任务 → 工作计划流
    "code_help": "prompt_refiner",     # 代码任务 → 提示词流（临时，后续建独立 Skill）
    "general": "prompt_refiner",       # 默认
}

SCENE_LABELS = {
    "prompt_optimize": "提示词优化",
    "work_plan": "工作安排",
    "info_organize": "信息整理",
    "research": "调研分析",
    "code_help": "代码帮助",
    "general": "通用对话",
}


async def route_intent(message: str, model) -> dict:
    """
    一次轻量 LLM 调用，判断用户意图。

    Args:
        message: 用户输入文本
        model: LangChain ChatModel

    Returns:
        {
            "scene": "prompt_optimize",
            "module": "prompt_refiner",
            "label": "提示词优化",
            "confidence": 0.9,    # 预留，当前模型不输出置信度
        }
    """
    try:
        response = await model.ainvoke([
            SystemMessage(content="你是意图分类器。只输出场景代码，不要解释。"),
            HumanMessage(content=ROUTER_SYSTEM_PROMPT.format(message=message)),
        ])

        raw = response.content.strip().lower()
        scene = _clean_scene(raw)

        logger.info(f"[Router] 意图: {scene} ← \"{message[:80]}\"")

    except Exception as e:
        logger.warning(f"[Router] 调用失败，降级为 general: {e}")
        scene = "general"

    module = SCENE_TO_MODULE.get(scene, "prompt_refiner")
    label = SCENE_LABELS.get(scene, "通用对话")

    return {
        "scene": scene,
        "module": module,
        "label": label,
        "confidence": 0.9,
    }


def route_intent_sync(message: str, model) -> dict:
    """
    同步版 Router（用于非 async 环境）。

    使用规则匹配做快速分类，不调用 LLM。
    准确率低于 LLM 版，但零延迟，适合做 fallback。
    """
    scene = _rule_based_route(message)
    module = SCENE_TO_MODULE.get(scene, "prompt_refiner")
    label = SCENE_LABELS.get(scene, "通用对话")

    logger.info(f"[Router] 规则意图: {scene} ← \"{message[:80]}\"")

    return {
        "scene": scene,
        "module": module,
        "label": label,
        "confidence": 0.5,  # 规则版的置信度较低
    }


# ── 内部 ──

def _clean_scene(raw: str) -> str:
    """清理 LLM 输出，提取有效的场景代码。"""
    valid = {"prompt_optimize", "work_plan", "info_organize", "research", "code_help", "general"}

    # 直接匹配
    for scene in valid:
        if scene in raw:
            return scene

    # 模糊匹配
    mapping = {
        "prompt": "prompt_optimize",
        "优化": "prompt_optimize",
        "文案": "prompt_optimize",
        "提示词": "prompt_optimize",
        "工作": "work_plan",
        "计划": "work_plan",
        "安排": "work_plan",
        "项目": "work_plan",
        "整理": "info_organize",
        "保存": "info_organize",
        "总结": "info_organize",
        "留存": "info_organize",
        "调研": "research",
        "搜索": "research",
        "对比": "research",
        "代码": "code_help",
        "bug": "code_help",
        "测试": "code_help",
        "审查": "code_help",
    }
    for keyword, scene in mapping.items():
        if keyword in raw:
            return scene

    return "general"


def _rule_based_route(message: str) -> str:
    """
    纯规则意图分类（不调 LLM，用作 fallback 或快速测试）。

    优先级: 关键词密度最高的场景获胜。
    """
    rules = [
        ("prompt_optimize", [
            "提示词", "prompt", "文案", "翻译", "润色", "改写",
            "写一个", "生成", "优化这个", "措辞",
        ]),
        ("work_plan", [
            "安排", "计划", "项目", "排期", "任务", "工作流",
            "怎么做", "步骤", "方案", "规划", "流程",
        ]),
        ("info_organize", [
            "整理", "保存", "留存", "总结", "导出", "记录",
            "归档", "笔记",
        ]),
        ("research", [
            "调研", "对比", "选型", "推荐", "哪个好", "有什么区别",
            "搜索", "最新", "技术趋势",
        ]),
        ("code_help", [
            "代码", "bug", "测试", "重构", "审查", "review",
            "报错", "出错", "函数", "class", "def ", "import",
        ]),
    ]

    scores = {}
    for scene, keywords in rules:
        score = 0
        for kw in keywords:
            if kw.lower() in message.lower():
                score += 1
        scores[scene] = score

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "general"
    return best
