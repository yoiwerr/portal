# src/skills/skill03_atmosphere.py
import json
import re
from fastapi import HTTPException
from src.schemas import AnalysisRequest, RelationDynamics
from src.core_llm import base_llm
from src.tools import ALL_TOOLS
from langchain_core.messages import SystemMessage, HumanMessage
from langchain.agents import create_agent

agent_executor = create_agent(model=base_llm, tools=ALL_TOOLS)

RELATION_DYNAMICS_SCHEMA = json.dumps(RelationDynamics.model_json_schema(), ensure_ascii=False)


async def execute_atmosphere_skill(request: AnalysisRequest) -> RelationDynamics:
    if not request.recent_chat:
        raise HTTPException(status_code=400, detail="分析失败：近期聊天记录不能为空。")

    try:
        chat_summary = _build_chat_summary(request.recent_chat, request.target_person)

        sys_msg = SystemMessage(content=f"""你是资深人际关系动力学专家，擅长将聊天互动转化为**量化关系指标**和**可执行的行动建议**。

## 你的分析流程

步骤1: 调用 search_chat_context(query="消息量 响应时间 主动性 发起 终结", target_person="{request.target_person}")
        → 获取**纯结构化统计指标**（消息量、比例、响应间隔秒数、发起/终结次数、逐轮时序）
        → 注意：返回的是原始数据，你需要根据下方的「指标解读标准」自行判断权力关系
步骤2: 调用 search_psychology_knowledge(query="权力动态 沟通姿态 萨提亚 依恋理论")
        → 获取人际关系心理学理论框架
步骤3: 如需要，调用 deep_read_message(message_query="...", target_person="{request.target_person}")
        → 核实关键对话片段的原文措辞
步骤4: 综合信息分析，直接输出 JSON。不要包含 Markdown 代码块标签，不要有前言后语。

## 指标解读标准

拿到 search_chat_context 返回的统计数据后，按以下参考区间判断权力动态：

### 消息比例 → 辅助掌控力分配
| 我/对方消息比 | 含义参考 |
|-------------|----------|
| < 0.5 | 对方消息更多，对方可能处于情感低位（更在意） |
| 0.5 ~ 2.0 | 沟通量基本对等 |
| > 2.0 | 我方消息更多，我方可能处于情感低位（更追逐） |

注意：主动发消息更多的一方通常处于关系低位——"谁更想聊，谁更被动"。

### 响应时间 → 辅助掌控力分配
| 谁响应更慢 | 含义参考 |
|-----------|----------|
| 对方→我明显慢于我→对方 | 对方掌控节奏，处于高位 |
| 我→对方明显慢于对方→我 | 我方掌控节奏，处于高位 |
| 双方接近 | 权力对等 |

### 发起/终结模式 → 辅助掌控力分配 & 沟通姿态
- 谁更多发起对话 → 谁更依赖这段关系
- 谁更多终结对话 → 谁更倾向于控制关系节奏
- 对方发起少 + 终结多 → 对方可能处于高位（抽离姿态）
- 对方发起多 + 终结少 → 对方可能处于低位（追逐姿态）

### 消息长度 → 辅助沟通姿态判断
- 短回复方("嗯""好""知道了") → 可能是掌控方（信息即权力）
- 长回复方 → 可能在解释/讨好/追逐
- 对方消息短于我方 1/2 以下 → 对方可能超理性或指责型

### 始终以实际数据为准。数据不足时基于对话摘要推断并在 analysis 中注明。

## 指数定义

### 1. 掌控力分配 (control_strength)
分析谁在主导这段对话的节奏、话题和走向。输出格式: {{"target_person": 65, "me": 35}}（合计 100）。
- 谁发起话题的频率更高？
- 谁决定话题何时切换或结束？
- 谁的回应更短/更长？（更短回复方通常是掌控方——"信息即权力"的反面）
- 谁设定了回复的时间期望？（谁更着急等回复 = 谁处于低位）
- 谁更多地使用封闭式回应（"嗯""好""知道了"）来终结话题？

### 2. 掌控力分析 (control_analysis)
100-200字的分析：权力不对等的具体表现、谁在高位谁在低位、关系是否健康平衡。

### 3. 沟通姿态 (communication_posture)
识别目标人物的主要沟通姿态（基于萨提亚模式）：
- "讨好型" — 过度迎合、不敢表达真实需求、优先照顾对方感受
- "指责型" — 习惯性批评、推卸责任、用攻击保护自己
- "超理性" — 过度讲道理、回避情感交流、用逻辑筑墙
- "打岔型" — 用幽默/转移话题逃避严肃沟通
- "一致型" — 既表达真实感受又尊重对方（最健康的姿态）
- "混合型-讨好+超理性" — 多种姿态的可观察混合

### 4. 关系进度条 (relation_progress) — 四个维度，各 0-100

**确定性 (certainty)** — 关系定义是否清晰
- 0-25: 完全没有定义，不知道彼此算什么关系
- 26-55: 有些默契但从未明确讨论
- 56-80: 关系框架基本清晰，双方有共识
- 81-100: 关系明确定义，双方认知一致

**暧昧度 (ambiguity)** — 言行中暧昧信号的强度
- 0-25: 纯友谊/事务性沟通，无任何暧昧信号
- 26-55: 偶尔含有模糊暗示但总体保持距离
- 56-80: 暧昧信号明显，试探性语言频繁
- 81-100: 高度暧昧，双方心照不宣，就差捅破

**亲近度 (closeness)** — 情感距离
- 0-25: 疏远/陌生，交流停留在表面客套
- 26-55: 有一定熟悉度但情感距离较远
- 56-80: 比较亲近，愿意分享个人话题
- 81-100: 亲密无间，无话不谈，深度情感连接

**可能性 (possibility)** — 关系往前发展的概率
- 0-25: 几乎不可能，对方明显无意愿或已有归属
- 26-55: 有一定可能但需长期经营
- 56-80: 大概率可以推进，对方态度积极
- 81-100: 必然发展，只差时机或主动迈出一步

**progress_summary**: 1-2句话总结四个维度的综合判断，点出最关键的那个维度

### 5. 气氛总结 (atmosphere_summary)
对当前聊天气氛的整体简短总结，10字以内。如: '紧张僵持'、'轻松暧昧'、'单方面迎合'、'礼貌疏离'、'温暖亲密'

### 6. 权力动态 (power_dynamic)
200-300字的深度分析：明确指出哪一方处于权力高位/低位，给出 3 条以上具体的判断依据，并评估这种权力结构对关系健康度的影响。

### 7. 行动建议 (actionable_suggestions)
至少 3 条，覆盖不同类别。每条包含：
- category: "立即行动" | "长期策略" | "风险预警"
- priority: 1-5 (5=最紧急/最重要)
- suggestion: 具体可执行的建议，50-100字
- expected_effect: 采取后的预期效果，20-50字

必须严格遵循以下 JSON Schema 规范：
{RELATION_DYNAMICS_SCHEMA}""")

        user_msg = HumanMessage(content=f"""目标人物：{request.target_person}
补充背景：{request.background_info or "无"}

## 当前对话摘要（仅用于快速定位，请通过工具获取详细数据）
{chat_summary}

请执行分析，直接输出 JSON 结果。""")

        result = await agent_executor.ainvoke({"messages": [sys_msg, user_msg]})
        raw_output = result["messages"][-1].content

        json_match = re.search(r'\{.*\}', raw_output, re.DOTALL)
        if not json_match:
            raise ValueError("大模型未返回可解析的 JSON 结构")

        clean_json_str = json_match.group(0)
        return RelationDynamics.model_validate_json(clean_json_str)

    except Exception as e:
        import traceback
        print(f"Error in atmosphere skill: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"气氛分析执行失败: {str(e)}")


def _build_chat_summary(chats, target_person: str) -> str:
    """构建轻量摘要。"""
    if not chats:
        return "无聊天记录"

    senders = list(set(c.sender for c in chats))
    msg_count = len(chats)
    target_msgs = [c for c in chats if c.sender == target_person]

    lines = [
        f"- 参与者: {', '.join(senders)}",
        f"- 消息总数: {msg_count} (目标人物: {len(target_msgs)} 条)",
        f"- 时间范围: {chats[0].timestamp} → {chats[-1].timestamp}",
        "- 最近 5 条消息:",
    ]
    for c in chats[-5:]:
        lines.append(f"  [{c.timestamp}] {c.sender}: {c.content[:80]}{'...' if len(c.content) > 80 else ''}")

    return "\n".join(lines)
