# src/skills/skill01_imitate.py
from fastapi import HTTPException
from src.schemas import AnalysisRequest
from src.core_llm import base_llm
from src.tools import ALL_TOOLS
from langchain_core.messages import SystemMessage, HumanMessage
from langchain.agents import create_agent

agent_executor = create_agent(model=base_llm, tools=ALL_TOOLS)


async def execute_imitate_skill(request: AnalysisRequest):
    # 1. 前置校验：如果没有聊天记录，直接报 400 错误
    if not request.recent_chat:
        raise HTTPException(status_code=400, detail="未提供近期聊天记录，无法进行分析。")

    try:
        chat_context = "\n".join([f"[{c.timestamp}] {c.sender}: {c.content}" for c in request.recent_chat])

        sys_msg = SystemMessage(content="你是一个顶级的聊天模仿大师。你需要精准模仿目标人物的语气。\n"
                                        "在模仿前，请务必调用 search_chat_history 工具，并将 target_person 参数设为目标人物名称，以过滤出该人物专属的历史发言。"
                                        "结合历史记录和当前上下文来把握对方的语气、用词习惯和口头禅。\n"
                                        "如果涉及不懂的梗或外部实时信息（如天气、新闻），请调用 web_search。\n"
                                        "如果需要心理学知识辅助理解人物性格，可调用 search_psychology_knowledge。")

        user_msg = HumanMessage(content=f"目标人物：{request.target_person}\n"
                                        f"补充背景：{request.background_info}\n"
                                        f"近期聊天记录：\n{chat_context}\n\n"
                                        f"请预测并模仿 {request.target_person} 的下一句回复。直接输出你要回复的一句话，不要任何多余解释。")

        response = await agent_executor.ainvoke({"messages": [sys_msg, user_msg]})
        final_reply = response["messages"][-1].content

        return {"reply": final_reply}

    except Exception as e:
        # 2. 捕获底层错误（如数据库插入失败、大模型调用超时等），返回 500 错误
        print(f"Error in imitate skill: {str(e)}")  # 在后端终端打印真实错误日志方便调试
        raise HTTPException(status_code=500, detail=f"模仿技能执行失败，内部错误：{str(e)}")