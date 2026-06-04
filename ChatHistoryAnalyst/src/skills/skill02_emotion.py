# src/skills/skill02_emotion.py
import json
import re
from fastapi import HTTPException
from src.schemas import AnalysisRequest, EmotionResponse
from src.core_llm import base_llm
from src.tools import ALL_TOOLS
from langchain_core.messages import SystemMessage, HumanMessage
from langchain.agents import create_agent

agent_executor = create_agent(model=base_llm, tools=ALL_TOOLS)

# 动态获取 Pydantic 模型定义的 Schema，不再手动拼接易错的字符串
EMOTION_SCHEMA_STR = json.dumps(EmotionResponse.model_json_schema(), ensure_ascii=False)


async def execute_emotion_skill(request: AnalysisRequest) -> EmotionResponse:
    if not request.recent_chat:
        raise HTTPException(status_code=400, detail="分析失败：近期聊天记录不能为空。")

    try:
        chat_context = "\n".join(
            [f"[{c.timestamp}] {c.sender}: {c.content}" for c in request.recent_chat]
        )

        sys_msg = SystemMessage(content=f"""你是高级心理分析师。按以下步骤完成任务：

步骤1: 调用 search_chat_history 检索历史发言，必须传入 target_person 参数为目标人物名称。
步骤2: 调用 search_psychology_knowledge 搜索相关的心理学理论。
步骤3: 如需要，可调用 web_search 获取实时信息。
步骤4: 综合分析后，以严格的 JSON 格式输出最终结果。不要包含任何 Markdown 代码块标签，不要有任何前言后语。
必须严格遵循以下 JSON Schema 规范：
{EMOTION_SCHEMA_STR}""")

        user_msg = HumanMessage(content=f"""目标人物：{request.target_person}
补充背景：{request.background_info or "无"}
当前聊天内容：
{chat_context}

请按照以上步骤进行分析，直接输出 JSON 结果。""")

        result = await agent_executor.ainvoke({"messages": [sys_msg, user_msg]})
        raw_output = result["messages"][-1].content

        # 【核心修复】使用正则表达式提取大括号及内部内容，彻底抛弃 split()
        # 无论大模型是否加上了 ```json 或者输出了多余的废话，都能精准命中 JSON
        json_match = re.search(r'\{.*\}', raw_output, re.DOTALL)
        if not json_match:
            raise ValueError("大模型未返回可解析的 JSON 结构")

        clean_json_str = json_match.group(0)
        return EmotionResponse.model_validate_json(clean_json_str)

    except Exception as e:
        import traceback
        print(f"Error in emotion skill: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"情感分析执行失败: {str(e)}")