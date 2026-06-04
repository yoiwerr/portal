# src/skills/skill03_atmosphere.py
import json
import re
from fastapi import HTTPException
from src.schemas import AnalysisRequest, AtmosphereResponse
from src.core_llm import base_llm
from src.tools import ALL_TOOLS
from langchain_core.messages import SystemMessage, HumanMessage
from langchain.agents import create_agent

agent_executor = create_agent(model=base_llm, tools=ALL_TOOLS)

# 动态生成 Schema
ATMOSPHERE_SCHEMA_STR = json.dumps(AtmosphereResponse.model_json_schema(), ensure_ascii=False)


async def execute_atmosphere_skill(request: AnalysisRequest) -> AtmosphereResponse:
    if not request.recent_chat:
        raise HTTPException(status_code=400, detail="分析失败：近期聊天记录不能为空。")

    try:
        chat_context = "\n".join(
            [f"[{c.timestamp}] {c.sender}: {c.content}" for c in request.recent_chat]
        )

        sys_msg = SystemMessage(content=f"""你是资深人际关系与谈判专家。按以下步骤完成任务：

步骤1: 调用 search_chat_history 检索历史聊天记录，必须传入 target_person 参数为目标人物名称，以判断长期的关系模式。
步骤2: 调用 search_psychology_knowledge 获取人际动态心理学理论。
步骤3: 如有需要，调用 web_search。
步骤4: 综合上述信息进行分析。最终结果必须以严格的 JSON 格式输出。不要包含任何 Markdown 代码块标签，不要有前言后语。
必须严格遵循以下 JSON Schema 规范：
{ATMOSPHERE_SCHEMA_STR}""")

        user_msg = HumanMessage(content=f"""目标人物：{request.target_person}
补充背景：{request.background_info or "无"}
当前聊天内容：
{chat_context}

请执行分析，直接输出 JSON 结果。""")

        result = await agent_executor.ainvoke({"messages": [sys_msg, user_msg]})
        raw_output = result["messages"][-1].content

        # 【核心修复】正则表达式安全提取，防止 split 崩溃
        json_match = re.search(r'\{.*\}', raw_output, re.DOTALL)
        if not json_match:
            raise ValueError("大模型未返回可解析的 JSON 结构")

        clean_json_str = json_match.group(0)
        return AtmosphereResponse.model_validate_json(clean_json_str)

    except Exception as e:
        import traceback
        print(f"Error in atmosphere skill: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"气氛分析执行失败: {str(e)}")