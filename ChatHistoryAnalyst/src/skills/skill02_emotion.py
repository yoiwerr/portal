# src/skills/skill02_emotion.py
import json
import re
from fastapi import HTTPException
from src.schemas import AnalysisRequest, EmotionIndices
from src.core_llm import base_llm
from src.tools import ALL_TOOLS
from langchain_core.messages import SystemMessage, HumanMessage
from langchain.agents import create_agent

agent_executor = create_agent(model=base_llm, tools=ALL_TOOLS)

EMOTION_INDICES_SCHEMA = json.dumps(EmotionIndices.model_json_schema(), ensure_ascii=False)


async def execute_emotion_skill(request: AnalysisRequest) -> EmotionIndices:
    if not request.recent_chat:
        raise HTTPException(status_code=400, detail="分析失败：近期聊天记录不能为空。")

    try:
        # 构造轻量上下文摘要（仅用于 LLM 了解对话概况，不做详细分析）
        chat_summary = _build_chat_summary(request.recent_chat, request.target_person)

        sys_msg = SystemMessage(content=f"""你是资深心理分析师，擅长将聊天对话转化为**量化心理指数**。

## 你的分析流程

步骤1: 调用 search_chat_context(query="消息量 响应时间 主动性", target_person="{request.target_person}")
        → 获取**纯结构化统计指标**（消息量、比例、响应间隔秒数、发起/终结次数、逐轮时序）
        → 注意：返回的是原始数据，你需要根据下方的「指标解读标准」自行判断其含义
步骤2: 调用 search_psychology_knowledge(query="真诚度 回避行为 冷暴力 情绪识别")
        → 获取心理学理论框架来支撑你的指数评分
步骤3: 如需核实具体措辞，调用 deep_read_message(message_query="...", target_person="{request.target_person}")
        → 获取相关原始消息全文，印证你的判断
步骤4: 综合以上信息，输出量化指数 JSON。不要包含任何 Markdown 代码块标签，不要有前言后语。

## 指标解读标准

拿到 search_chat_context 返回的统计数据后，按以下参考区间判断：

### 消息比例（我/对方）→ 辅助真诚指数、回避指数
| 比例范围 | 含义参考 |
|----------|----------|
| < 0.4 | 对方消息量远超我方 |
| 0.4 ~ 2.5 | 沟通量基本对等 |
| > 2.5 | 我方单向输出，对方回应稀疏 |

### 响应时间（对方→我）→ 辅助回避指数、冷暴力指数
| 平均响应间隔 | 含义参考 |
|-------------|----------|
| < 5 分钟 | 秒回，沟通紧密 |
| 5 分钟 ~ 1 小时 | 正常节奏 |
| 1 小时 ~ 6 小时 | 轻度延迟，可能回避 |
| > 6 小时 | 明显回避 / 冷暴力信号 |

### 发起/终结模式 → 辅助真诚指数、情绪稳定性
- 对方发起次数远少于我方 → 对方缺乏主动性
- 对方终结次数远多于我方 → 对方倾向于结束对话
- 双方接近 → 互动双向均衡

### 消息长度波动 → 辅助情绪稳定性
- 对方消息长度大幅波动（时短时长）→ 情绪不稳定信号
- 对方消息长度稳定 → 情绪较稳定

### 始终以实际数据为准。数据不足时基于对话摘要推断并在 reasoning 中注明。

## 指数定义（每个指数 0-100）

### 1. 真诚指数 (sincerity_index)
衡量对方语言与内心真实想法的一致性。
- 0-30: 高度虚伪/套路化 — 回复空洞、大量表情包掩饰、系统性回避直接问题
- 31-60: 有限真诚 — 选择性回答、部分话题闪烁其词、谨慎控制信息暴露
- 61-85: 基本真诚 — 愿意坦露但有所保留、偶尔使用防御性语言
- 86-100: 高度真诚 — 主动分享脆弱、语言前后一致性强、不惧暴露真实想法
判断维度: 语言一致性、自我暴露程度、承诺兑现线索、表情包/语气词占比、是否有前后矛盾

### 2. 回避指数 (avoidance_index)
衡量对方逃避直接沟通的程度。
- 0-25: 正面回应 — 几乎不回避任何直接问题，愿意深入讨论
- 26-55: 轻度回避 — 偶尔转移话题或答非所问，个别问题闪烁其词
- 56-80: 中度回避 — 系统性避开特定话题，回复延迟明显，常说"再说吧""不知道"
- 81-100: 极度回避 — 几乎不直接回答任何问题，持续已读不回，用表情包敷衍
判断维度: 话题转移频率、敷衍回应("嗯""哦""好")占比、关键问题回答率、响应时间异常延长

### 3. 冷暴力指数 (cold_violence_index)
衡量对方情感回应的缺失与刻意冷漠程度。
- 0-20: 无冷暴力 — 沟通积极、情感回应充分、愿意表达情绪
- 21-50: 轻度冷暴力 — 偶尔冷漠、延迟回复无解释、情绪表达稀薄
- 51-75: 中度冷暴力 — 频繁长时间沉默、情感抽离、已读不回、以单字回应
- 76-100: 重度冷暴力 — 完全情感冻结、拒绝沟通、刻意无视对方情绪需求
判断维度: 长时间沉默间隔频率、情感回应缺失度、"已读不回"模式、主动联系意愿、对被忽视的反馈

### 4. 情绪稳定性 (emotional_stability)
衡量对方情绪状态的波动幅度。
- 0-30: 极度不稳定 — 忽冷忽热、前后情绪反差巨大、让人捉摸不定
- 31-60: 中度波动 — 有明显情绪起伏，受外界因素影响大
- 61-85: 基本稳定 — 情绪有波动但在正常范围，可以预测
- 86-100: 极其稳定 — 情绪始终如一，不受对话内容影响过度波动
判断维度: 情绪转变速度、前后消息情感一致性、极端情绪的频繁程度

### 5. 主导情绪 (dominant_emotion)
当前对话中最突出的情绪标签，精简为2-4字,如: '焦虑'、'开心'、'冷漠'、'试探'、'愤怒'、'敷衍'、'温柔'、'防备'、'暧昧'、'疏离'

### 6. 情感变化趋势 (emotion_trajectory)
一句话描述近N条消息中的情感走向。如: '持续升温：从冷淡逐渐变得主动和温暖'、'逐渐冷却：从热情回复转为简短敷衍'、'波动剧烈：时而亲密时而疏远，无明显规律'

必须严格遵循以下 JSON Schema 规范：
{EMOTION_INDICES_SCHEMA}""")

        user_msg = HumanMessage(content=f"""目标人物：{request.target_person}
补充背景：{request.background_info or "无"}

## 当前对话摘要（仅用于快速定位，请通过工具获取详细分析数据）
{chat_summary}

请按照步骤执行分析，直接输出 JSON 结果。""")

        result = await agent_executor.ainvoke({"messages": [sys_msg, user_msg]})
        raw_output = result["messages"][-1].content

        json_match = re.search(r'\{.*\}', raw_output, re.DOTALL)
        if not json_match:
            raise ValueError("大模型未返回可解析的 JSON 结构")

        clean_json_str = json_match.group(0)
        return EmotionIndices.model_validate_json(clean_json_str)

    except Exception as e:
        import traceback
        print(f"Error in emotion skill: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"情感分析执行失败: {str(e)}")


def _build_chat_summary(chats, target_person: str) -> str:
    """构建轻量摘要，仅让 LLM 理解对话轮廓。详细分析由工具检索完成。"""
    if not chats:
        return "无聊天记录"

    senders = list(set(c.sender for c in chats))
    msg_count = len(chats)
    target_msgs = [c for c in chats if c.sender == target_person]
    other_msgs = [c for c in chats if c.sender != target_person]

    lines = [
        f"- 参与者: {', '.join(senders)}",
        f"- 消息总数: {msg_count} (目标人物 {target_person}: {len(target_msgs)} 条, 其他: {len(other_msgs)} 条)",
        f"- 时间范围: {chats[0].timestamp} → {chats[-1].timestamp}",
        "- 最近 5 条消息:",
    ]
    for c in chats[-5:]:
        lines.append(f"  [{c.timestamp}] {c.sender}: {c.content[:80]}{'...' if len(c.content) > 80 else ''}")

    return "\n".join(lines)
