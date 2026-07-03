"""
LLM 模型工厂。

参照 ChatLab src/core_llm.py 的简洁模式。
本地推理引擎: SGLang (OpenAI-compatible API) → LangChain ChatOpenAI 直连。

用法:
    model = create_model(config)
    agent = create_agent(model=model, tools=ALL_TOOLS, system_prompt=...)

后续换模型:
    换 Ollama:  ChatOpenAI(base_url="http://localhost:11434/v1", model="qwen3:8b")
    换你自己的: ChatOpenAI(base_url="http://localhost:xxxx/v1", model="your-model")
"""

from langchain_openai import ChatOpenAI


def create_model(config=None):
    """
    创建 LangChain 兼容的 ChatModel。

    通过 ChatOpenAI 连接 SGLang（暴露 OpenAI 兼容 API）。
    后续换 Ollama / vLLM / 自训练模型都只需改 base_url + model。
    """
    base_url = "http://localhost:30000/v1"
    model_name = "deepseek-r1-7b"
    timeout = 120.0
    temperature = 0.7

    if config is not None:
        base_url = getattr(config, "sglang_base_url", base_url)
        model_name = getattr(config, "sglang_model", model_name)
        timeout = getattr(config, "sglang_timeout", timeout)
        temperature = getattr(config, "llm_temperature", temperature)

    return ChatOpenAI(
        base_url=base_url,
        api_key="not-needed",           # 本地模型不需要 API key
        model=model_name,
        temperature=temperature,
        timeout=timeout,
        max_retries=2,
    )
