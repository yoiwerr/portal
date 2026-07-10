# src/skills/skill01_imitate.py
from fastapi import HTTPException
from src.schemas import AnalysisRequest
from src.core_llm import base_llm
from src.tools import ALL_TOOLS
from langchain_core.messages import SystemMessage, HumanMessage
from langchain.agents import create_agent

agent_executor = create_agent(model=base_llm, tools=ALL_TOOLS)


async def execute_imitate_skill(request: AnalysisRequest):
    if not request.recent_chat:
        raise HTTPException(status_code=400, detail="未提供近期聊天记录，无法进行分析。")

    try:
        chat_summary = _build_chat_summary(request.recent_chat, request.target_person)

        sys_msg = SystemMessage(content=f"""你是一个顶级的对话风格分析师和聊天模仿大师。你需要精准模仿目标人物的语气。

## 你的分析流程

步骤1: 调用 search_chat_context(query="互动模式 消息量 响应速度", target_person="{request.target_person}")
        → 获取目标人物的对话统计特征（消息长度、响应模式、主动性），构建人物画像
步骤2: 调用 deep_read_message(message_query="...", target_person="{request.target_person}")
        → 获取目标人物的原始发言样本，仔细研究其用词、句式、语气
步骤3: 如涉及不懂的梗或外部实时信息，调用 web_search
步骤4: 如需要心理学知识辅助理解人物性格，调用 search_psychology_knowledge

## 输出要求

你需要输出一个 JSON，包含两个字段：
1. "reply": 模仿 {request.target_person} 的语气，预测其下一句回复。直接一句话，不要多余解释。
2. "speech_fingerprint": 100-150字的语气指纹分析，包含：
   - 用词偏好（口语化/书面化、惯用词、语气词规律）
   - 句式特征（短句还是长句、是否喜欢反问、是否常用省略号）
   - 口头禅或标志性表达（如有）
   - 回复风格（直接/含蓄、热情/冷淡、幽默/严肃）

严格输出 JSON 格式: {{"reply": "回复内容", "speech_fingerprint": "语气指纹描述"}}
不要包含 Markdown 代码块标签，不要有任何前言后语。""")

        user_msg = HumanMessage(content=f"""目标人物：{request.target_person}
补充背景：{request.background_info or "无"}

## 当前对话摘要
{chat_summary}

请分析并模仿 {request.target_person} 的语气，输出 JSON。""")

        result = await agent_executor.ainvoke({"messages": [sys_msg, user_msg]})
        raw_output = result["messages"][-1].content

        # 安全提取 JSON
        import re
        import json
        json_match = re.search(r'\{.*\}', raw_output, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(0))
            return {
                "reply": parsed.get("reply", raw_output),
                "speech_fingerprint": parsed.get("speech_fingerprint", ""),
            }

        # Fallback: 如果无法解析 JSON，整个输出作为 reply
        return {"reply": raw_output.strip(), "speech_fingerprint": ""}

    except Exception as e:
        print(f"Error in imitate skill: {str(e)}")
        raise HTTPException(status_code=500, detail=f"模仿技能执行失败，内部错误：{str(e)}")


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
