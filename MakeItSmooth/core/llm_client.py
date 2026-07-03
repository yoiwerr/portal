"""
LLM 模型工厂 — 对齐 ChatLab src/core_llm.py。

推理引擎: DashScope (通义千问) → LangChain ChatTongyi 直连。
无需本地 GPU，有 API key 即可。

用法:
    model = create_model(config)
    agent = create_agent(model=model, tools=ALL_TOOLS, system_prompt=...)
"""

from langchain_community.chat_models.tongyi import ChatTongyi


def create_model(config=None):
    """
    创建 LangChain 兼容的 ChatModel。

    使用 ChatTongyi 原生 API，完美支持 Agent 工具调用，
    彻底避开 OpenAI 兼容层转换问题。
    """
    api_key = ""
    model_name = "qwen3-max"
    temperature = 0.7
    timeout = 120.0

    if config is not None:
        api_key = getattr(config, "dashscope_api_key", api_key)
        model_name = getattr(config, "llm_model", model_name)
        temperature = getattr(config, "llm_temperature", temperature)
        timeout = getattr(config, "llm_timeout", timeout)

    if not api_key:
        raise ValueError(
            "未在环境变量中找到 DASHSCOPE_API_KEY，"
            "请在 .env 中设置或传入 config.dashscope_api_key"
        )

    return ChatTongyi(
        model=model_name,
        dashscope_api_key=api_key,
        temperature=temperature,
        timeout=timeout,
    )
