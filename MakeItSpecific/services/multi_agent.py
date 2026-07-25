"""
多立场 Agent Panel — 三 Agent 并行 + 阿福整合。

三个 Agent 以不同决策立场分析同一问题:
  - 实用派 (pragmatist): 优先速度和最小实现，最快落地
  - 稳健派 (conservative): 优先安全和维护成本，长期可维护
  - 创新派 (innovator): 优先差异化与创意，突破常规

触发规则 (硬约束):
  1. 用户明确要求多角度分析/对比方案 (如 "帮我对比" "从不同角度分析" "多个方案")
  2. 需求不明确 (confidence < 0.5) 但用户拒绝追问、坚持要求输出

不触发:
  - 普通问答、单步操作、信息查询
  - 即使 Planner 判断信息不足，只要用户愿意回答问题就不触发
  - 高完整性 (confidence >= 0.7) 的普通执行任务

输出格式 — 结构化对比，不是三篇长文:
  共识 / 分歧 / 每个方案的代价 / 用户真正需要决定什么 / 阿福倾向于哪个方案及原因
"""

import asyncio
import json
import logging
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

# ============================================================
# 触发检测
# ============================================================

# 明确触发词 — 用户说了这些才触发
EXPLICIT_TRIGGERS = [
    "从不同角度", "多角度", "对比方案", "多个方案",
    "优缺点", "利弊", "优劣", "权衡",
    "不同立场", "多视角", "帮我对比", "分析对比",
    "有什么选择", "有哪些方案", "各有什么",
    "哪种更好", "选哪个", "怎么选",
    "帮我分析一下", "帮我评估",
    "对比一下", "对比优劣", "方案对比", "方案比较",
]

# 禁止触发词 — 用户说了这些即使匹配也不触发
SUPPRESS_TRIGGERS = [
    "什么是", "怎么用", "介绍一下", "解释",
    "帮我查", "搜索", "翻译",
]


def should_trigger_multi_agent(message: str, contract: Optional[dict] = None) -> dict:
    """
    判断是否应该触发多 Agent Panel。

    Returns:
        {
            "trigger": bool,
            "reason": str,           # 触发原因
            "method": str | None,    # "explicit" | "unclear_demand" | None
        }
    """
    text = message.lower().strip()
    confidence = (contract or {}).get("confidence", 1.0)

    # Rule 1: 明确触发
    explicit_hits = [t for t in EXPLICIT_TRIGGERS if t in text]
    suppress_hits = [t for t in SUPPRESS_TRIGGERS if t in text]

    if explicit_hits and not suppress_hits:
        return {
            "trigger": True,
            "reason": f"用户明确要求多角度分析 (匹配: {', '.join(explicit_hits[:2])})",
            "method": "explicit",
        }

    # Rule 2: 需求不明确 + 用户拒绝追问 + 坚持要输出
    # 检测信号: 低 confidence + 短消息 + 拒绝性表述
    reject_phrases = ["直接给我", "不用问了", "先输出", "随便", "你看着办", "不用确认", "直接做"]
    has_reject = any(p in text for p in reject_phrases)

    if confidence < 0.5 and has_reject and len(message) > 5:
        return {
            "trigger": True,
            "reason": f"需求不明确(confidence={confidence:.0%})但用户拒绝追问、坚持输出",
            "method": "unclear_demand",
        }

    return {"trigger": False, "reason": "", "method": None}


# ============================================================
# 三立场 System Prompts
# ============================================================

PRAGMATIST_PROMPT = """你是一个**实用派**工程师。你的核心原则：最快落地、最小成本、最简实现。

## 思考方式
- 什么方案能最快跑起来？
- 有没有现成的库/工具可以直接用？
- 能少写一行代码就少写一行
- 先做 MVP，能用再迭代
- 技术选型优先选你熟的、社区大的、坑少的

## 输出要求
- 给出一个具体的、可立刻动手的方案
- 包含: 技术选型、核心步骤（3-5步）、预计时间
- 不过度设计，不引入不必要的复杂度
- 用代码示例说话，不是概念描述

## 你的限制
- 不推荐需要学一周才能上手的新技术
- 不引入超过 3 个新依赖
- 不设计"万一将来要扩展"的预留接口
"""

CONSERVATIVE_PROMPT = """你是一个**稳健派**架构师。你的核心原则：安全第一、可维护、可扩展。

## 思考方式
- 这个方案 6 个月后还有人能维护吗？
- 边界条件都处理了吗？错误情况考虑了吗？
- 有没有安全隐患？数据会不会丢？
- 测试怎么保证？部署出问题怎么回滚？
- 代码变更的影响范围有多大？

## 输出要求
- 给出一个结构稳健、风险可控的方案
- 包含: 架构设计、风险点（至少3个）、缓解措施、测试策略
- 明确指出哪些地方需要人工确认
- 标注每个决策的可逆性（可逆/不可逆/代价高）

## 你的限制
- 不为了追求"优雅"引入不必要的抽象层
- 不推荐你没有充分理由相信它长期可维护的方案
- 数据相关操作必须有备份和回滚方案
"""

INNOVATOR_PROMPT = """你是一个**创新派**技术探索者。你的核心原则：差异化、突破常规、前瞻性。

## 思考方式
- 有没有更聪明的方法？大家都在用的不一定是最好的
- 新技术有没有可能大幅简化这个问题？
- 这个方案能否让最终产品区别于同类？
- 用户的隐性需求可能是什么？表面需求之外还想达到什么效果？
- 有没有跨领域的思路可以借鉴？

## 输出要求
- 给出一个突破常规的、差异化明显的方案
- 包含: 创新点、与常规做法的对比、潜在收益、适用条件
- 如果有新兴技术/工具可以用，列出并说明为什么值得冒险
- 标注方案的"惊喜因子"——哪些地方会让用户觉得"原来还可以这样"

## 你的限制
- 不推荐你了解不深的技术（不能基于"听说过"就推荐）
- 创新方案必须说明风险——什么东西可能不 work
- 不能为了炫技而推荐复杂度高的方案
"""

# ============================================================
# 阿福整合 Prompt
# ============================================================

SYNTHESIZER_PROMPT = """你是 阿福，一个 AI 协作管家。你刚收到了三个不同立场的 AI 对同一问题的分析：

- **实用派**：优先速度和最小实现
- **稳健派**：优先安全和维护成本
- **创新派**：优先差异化与创意

你的任务是把三份分析整合为一份**结构化对比**，帮助用户做出决策。

## 输出格式（Markdown）

### 🤝 共识
（三个立场都认同的核心观点，3-5条）

### ⚡ 分歧
（关键分歧点，每个分歧说明三方的不同立场）

### 💰 每个方案的代价

| 方案 | 时间成本 | 风险等级 | 技术债务 | 适合场景 |
|------|---------|---------|---------|---------|
| 实用派 | ... | ... | ... | ... |
| 稳健派 | ... | ... | ... | ... |
| 创新派 | ... | ... | ... | ... |

### 🎯 你需要决定的
（列出用户真正需要在意的 2-3 个关键决策点，不是技术细节，而是权衡取舍）

### 💡 阿福的建议
（如果有明确倾向，说明原因；如果取决于场景，说明什么情况下选哪个）

## 规则
- 不要说"三方都很好"——必须有明确立场
- 不要重复三方的原始输出，提炼要点
- 分歧点是价值所在，不要掩盖分歧
- 决策点必须是用户能理解的，不要用技术黑话
- 总长度控制在 500 字以内，这是一份决策辅助，不是三篇论文
"""


# ============================================================
# MultiAgentPanel
# ============================================================

class MultiAgentPanel:
    """三立场 Agent Panel + 阿福整合。"""

    PERSPECTIVES = {
        "pragmatist": {
            "label": "实用派",
            "icon": "⚡",
            "system_prompt": PRAGMATIST_PROMPT,
            "color": "#4CAF50",
        },
        "conservative": {
            "label": "稳健派",
            "icon": "🛡️",
            "system_prompt": CONSERVATIVE_PROMPT,
            "color": "#2196F3",
        },
        "innovator": {
            "label": "创新派",
            "icon": "🚀",
            "system_prompt": INNOVATOR_PROMPT,
            "color": "#FF9800",
        },
    }

    def __init__(self, model):
        """
        Args:
            model: LangChain chat model (会被三个 Agent 共享调用)
        """
        self.model = model

    # ============================================================
    # 核心: 并行执行 + 整合
    # ============================================================

    async def run_panel(
        self,
        message: str,
        background: str = "",
        rag_context: str = "",
    ) -> dict:
        """
        并行运行三个立场 Agent，然后由阿福整合。

        Returns:
            {
                "triggered": True,
                "perspectives": {
                    "pragmatist": {"label": "实用派", "icon": "⚡", "output": "...", "elapsed_ms": 1234},
                    "conservative": {"label": "稳健派", "icon": "🛡️", "output": "...", "elapsed_ms": 1234},
                    "innovator": {"label": "创新派", "icon": "🚀", "output": "...", "elapsed_ms": 1234},
                },
                "synthesis": "markdown structured comparison",
                "raw_synthesis": {...},  # parsed JSON synthesis
            }
        """
        # 构建每个 Agent 的 prompt
        context = f"## 用户背景\n{background or '（未填写）'}\n\n## 知识库参考\n{rag_context or '（无）'}\n\n## 用户问题\n{message}"

        # ── 并行执行三个 Agent ──
        async def run_one(key: str):
            start = asyncio.get_event_loop().time()
            config = self.PERSPECTIVES[key]
            full_prompt = f"{config['system_prompt']}\n\n{context}\n\n请基于你的立场给出方案分析。"
            try:
                response = await self.model.ainvoke([
                    SystemMessage(content=full_prompt),
                    HumanMessage(content="请给出你的分析和建议。"),
                ])
                output = response.content
            except Exception as e:
                logger.error(f"[MultiAgent] {key} 失败: {e}")
                output = f"({config['label']}分析生成失败: {str(e)})"
            elapsed = int((asyncio.get_event_loop().time() - start) * 1000)
            return key, output, elapsed

        tasks = [run_one(k) for k in self.PERSPECTIVES]
        results = await asyncio.gather(*tasks)

        perspectives = {}
        perspective_outputs = {}
        for key, output, elapsed in results:
            config = self.PERSPECTIVES[key]
            perspectives[key] = {
                "label": config["label"],
                "icon": config["icon"],
                "color": config["color"],
                "output": output,
                "elapsed_ms": elapsed,
            }
            perspective_outputs[key] = output

        # ── 阿福整合 ──
        synthesis = await self._synthesize(
            message=message,
            pragmatist=perspective_outputs["pragmatist"],
            conservative=perspective_outputs["conservative"],
            innovator=perspective_outputs["innovator"],
        )

        logger.info(
            f"[MultiAgent] Panel 完成 | "
            f"pragmatist={perspectives['pragmatist']['elapsed_ms']}ms "
            f"conservative={perspectives['conservative']['elapsed_ms']}ms "
            f"innovator={perspectives['innovator']['elapsed_ms']}ms "
            f"synthesis_len={len(synthesis)}"
        )

        return {
            "triggered": True,
            "perspectives": perspectives,
            "synthesis": synthesis,
        }

    async def _synthesize(
        self,
        message: str,
        pragmatist: str,
        conservative: str,
        innovator: str,
    ) -> str:
        """阿福读取三方输出，生成结构化对比。"""
        prompt = f"""{SYNTHESIZER_PROMPT}

## 用户原始问题
{message}

## 实用派的分析
{pragmatist[:2500]}

## 稳健派的分析
{conservative[:2500]}

## 创新派的分析
{innovator[:2500]}

请基于以上三份分析，输出结构化对比。直接输出 Markdown，不要前导说明。"""

        try:
            response = await self.model.ainvoke([
                SystemMessage(content=prompt),
                HumanMessage(content="请输出结构化对比。"),
            ])
            return response.content
        except Exception as e:
            logger.error(f"[MultiAgent] 整合失败: {e}")
            return self._fallback_synthesis(pragmatist, conservative, innovator)

    def _fallback_synthesis(self, pragmatist: str, conservative: str, innovator: str) -> str:
        """LLM 整合失败时的降级模板。"""
        return f"""### 🤝 共识
（三个立场自动生成，请手动对比）

### ⚡ 分歧
三个立场给出了不同侧重点的分析。

### 💰 每个方案的代价
| 方案 | 适合场景 |
|------|---------|
| ⚡ 实用派 | 快速上线、验证想法 |
| 🛡️ 稳健派 | 长期维护、团队协作 |
| 🚀 创新派 | 差异化竞争、技术探索 |

### 🎯 你需要决定的
请根据你的实际情况选择最合适的方案。

### 💡 阿福的建议
三种分析已给出。如果你告诉我更多上下文（团队规模、时间限制、项目阶段），我可以给出更具体的推荐。

---

<details>
<summary>⚡ 实用派原始分析</summary>

{pragmatist[:800]}
</details>

<details>
<summary>🛡️ 稳健派原始分析</summary>

{conservative[:800]}
</details>

<details>
<summary>🚀 创新派原始分析</summary>

{innovator[:800]}
</details>"""


# ============================================================
# 工具函数
# ============================================================

def format_panel_for_sse(perspectives: dict) -> list[dict]:
    """将多 Agent 结果格式化为 SSE 事件序列。"""
    events = []

    for key, p in perspectives.items():
        events.append({
            "event": "multi_agent_perspective",
            "data": {
                "key": key,
                "label": p["label"],
                "icon": p["icon"],
                "color": p["color"],
                "output": p["output"],
                "elapsed_ms": p["elapsed_ms"],
            },
        })

    return events


def format_synthesis_for_sse(synthesis: str) -> dict:
    """将整合结果格式化为 SSE 事件。"""
    return {
        "event": "multi_agent_synthesis",
        "data": {
            "synthesis": synthesis,
        },
    }
