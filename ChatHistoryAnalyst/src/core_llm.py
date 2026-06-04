# src/core_llm.py
import os
from dotenv import load_dotenv
# 弃用有 Bug 的 OpenAI 兼容层
# from langchain.chat_models import init_chat_model

# 引入原生的 通义千问 模块
from langchain_community.chat_models.tongyi import ChatTongyi

load_dotenv()

api_key = os.getenv("DASHSCOPE_API_KEY")

if not api_key:
    raise ValueError("未在环境变量中找到 DASHSCOPE_API_KEY，请检查 .env 文件。")

# 使用原生 API，完美支持 Agent 工具调用，彻底避开 OpenAI 兼容层转换崩溃问题
base_llm = ChatTongyi(
    model="qwen3-max",
    dashscope_api_key=api_key
)
vision_llm = ChatTongyi(
    model="qwen3-omni-flash",
    dashscope_api_key=api_key
)
