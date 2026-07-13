# src/core_llm.py
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# portal/.env 统一管理所有环境变量
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

api_key = os.getenv("DEEPSEEK_API_KEY")

if not api_key:
    raise ValueError("未在环境变量中找到 DEEPSEEK_API_KEY，请检查 .env 文件。")

base_llm = ChatOpenAI(
    model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    api_key=api_key,
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    temperature=0.3,
)

# 保留视觉模型用于 OCR（未来可替换为 DeepSeek Vision 或其他模型）
vision_llm = ChatOpenAI(
    model=os.getenv("DEEPSEEK_VISION_MODEL", "deepseek-chat"),
    api_key=api_key,
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    temperature=0.1,
)
