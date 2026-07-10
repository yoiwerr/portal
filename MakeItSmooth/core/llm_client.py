"""
LLM 模型工厂 — 多 Provider 支持。

支持的 Provider:
  - dashscope: 阿里通义千问 (ChatTongyi)，原生 tool calling
  - deepseek:  DeepSeek (OpenAI 兼容)，性价比高
  - openai:    OpenAI (ChatOpenAI)，最强推理
  - local:     本地部署 (vLLM / SGLang / Ollama 等 OpenAI 兼容接口)
  - auto:      自动选择第一个可用 provider (dashscope → deepseek → openai)

用法:
    model = create_model(config)
    agent = create_agent(model=model, tools=ALL_TOOLS, system_prompt=...)
"""

import os
import logging
from typing import Optional

from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger(__name__)

# ============================================================
# Provider 注册表
# ============================================================

_PROVIDER_REGISTRY = {}


def _provider(name: str):
    """装饰器：注册 LLM provider 工厂函数。"""
    def decorator(fn):
        _PROVIDER_REGISTRY[name] = fn
        return fn
    return decorator


# ============================================================
# 各 Provider 实现
# ============================================================

@_provider("dashscope")
def _create_dashscope(config) -> BaseChatModel:
    """阿里 DashScope (通义千问) — ChatTongyi 原生 SDK。

    需要环境变量: DASHSCOPE_API_KEY
    """
    from langchain_community.chat_models.tongyi import ChatTongyi

    api_key = getattr(config, "dashscope_api_key", "") or os.getenv("DASHSCOPE_API_KEY", "")
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY 未设置，请在 .env 中配置")

    return ChatTongyi(
        model=getattr(config, "llm_model", "qwen-plus"),
        dashscope_api_key=api_key,
        temperature=getattr(config, "llm_temperature", 0.7),
        timeout=getattr(config, "llm_timeout", 120.0),
    )


@_provider("deepseek")
def _create_deepseek(config) -> BaseChatModel:
    """DeepSeek — OpenAI 兼容接口。

    需要环境变量: DEEPSEEK_API_KEY
    默认 base_url: https://api.deepseek.com/v1
    """
    from langchain_openai import ChatOpenAI

    api_key = getattr(config, "deepseek_api_key", "") or os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 未设置，请在 .env 中配置")

    base_url = getattr(config, "deepseek_base_url", None) or os.getenv(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
    )

    return ChatOpenAI(
        model=getattr(config, "deepseek_model", "deepseek-chat"),
        api_key=api_key,
        base_url=base_url,
        temperature=getattr(config, "llm_temperature", 0.7),
        timeout=getattr(config, "llm_timeout", 120.0),
        max_retries=2,
    )


@_provider("openai")
def _create_openai(config) -> BaseChatModel:
    """OpenAI — ChatOpenAI 原生。

    需要环境变量: OPENAI_API_KEY
    """
    from langchain_openai import ChatOpenAI

    api_key = getattr(config, "openai_api_key", "") or os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY 未设置，请在 .env 中配置")

    return ChatOpenAI(
        model=getattr(config, "openai_model", "gpt-4o"),
        api_key=api_key,
        base_url=getattr(config, "openai_base_url", None) or os.getenv("OPENAI_BASE_URL", None),
        temperature=getattr(config, "llm_temperature", 0.7),
        timeout=getattr(config, "llm_timeout", 120.0),
        max_retries=2,
    )


@_provider("local")
def _create_local(config) -> BaseChatModel:
    """本地部署 — vLLM / SGLang / Ollama 等 OpenAI 兼容接口。

    需要环境变量: LOCAL_LLM_URL (如 http://localhost:8000/v1)
    可选: LOCAL_LLM_API_KEY
    """
    from langchain_openai import ChatOpenAI

    base_url = getattr(config, "local_llm_url", "") or os.getenv("LOCAL_LLM_URL", "")
    if not base_url:
        raise ValueError("LOCAL_LLM_URL 未设置，请在 .env 中配置（如 http://localhost:8000/v1）")

    api_key = os.getenv("LOCAL_LLM_API_KEY", "not-needed")

    return ChatOpenAI(
        model=getattr(config, "llm_model", "qwen3.6-flash"),
        api_key=api_key,
        base_url=base_url,
        temperature=getattr(config, "llm_temperature", 0.7),
        timeout=getattr(config, "llm_timeout", 120.0),
        max_retries=1,
    )


# ============================================================
# 主工厂函数
# ============================================================

def create_model(config) -> BaseChatModel:
    """根据 LLM_PROVIDER 环境变量创建对应的 ChatModel。

    Provider 选择优先级:
      1. 显式配置:  config.llm_provider 或 LLM_PROVIDER 环境变量
      2. auto 模式: 按 dashscope → deepseek → openai 顺序尝试第一个有 API key 的
      3. 兼容旧版:  如果只设置了 DASHSCOPE_API_KEY 且未指定 provider，默认用 dashscope

    模型选择:
      - dashscope: 使用 config.llm_model (默认 qwen-plus)
      - deepseek:  使用 config.deepseek_model (默认 deepseek-chat)
      - openai:    使用 config.openai_model (默认 gpt-4o)
      - local:     使用 config.llm_model (默认 qwen3.6-flash)
    """
    provider = (
        getattr(config, "llm_provider", None)
        or os.getenv("LLM_PROVIDER", "")
        or _auto_detect_provider(config)
    ).strip().lower()

    if not provider:
        raise ValueError(
            "无法确定 LLM provider。请设置 LLM_PROVIDER 环境变量 "
            "(dashscope / deepseek / openai / local)，"
            "或设置对应 provider 的 API key (DASHSCOPE_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY)"
        )

    if provider not in _PROVIDER_REGISTRY:
        available = ", ".join(_PROVIDER_REGISTRY.keys())
        raise ValueError(
            f"不支持的 LLM provider: '{provider}'。"
            f"可用 provider: {available}"
        )

    logger.info(f"[LLM] 使用 provider: {provider}")
    return _PROVIDER_REGISTRY[provider](config)


def _auto_detect_provider(config) -> Optional[str]:
    """自动检测第一个有 API key 的 provider。"""
    # 按优先级检查
    candidates = [
        ("dashscope", "dashscope_api_key", "DASHSCOPE_API_KEY"),
        ("deepseek", "deepseek_api_key", "DEEPSEEK_API_KEY"),
        ("openai", "openai_api_key", "OPENAI_API_KEY"),
    ]
    for name, config_key, env_key in candidates:
        if getattr(config, config_key, None) or os.getenv(env_key):
            logger.info(f"[LLM] 自动检测到 provider: {name}")
            return name
    return None


def get_available_providers() -> list[str]:
    """返回所有已注册的 provider 名称。"""
    return list(_PROVIDER_REGISTRY.keys())


def get_embedding_model(config):
    """创建 Embedding 模型 — 当前仅支持 DashScope text-embedding-v3。

    后续可扩展为多 provider embedding。
    """
    from langchain_community.embeddings import DashScopeEmbeddings

    api_key = getattr(config, "dashscope_api_key", "") or os.getenv("DASHSCOPE_API_KEY", "")
    if not api_key:
        raise ValueError("Embedding 模型需要 DASHSCOPE_API_KEY")

    return DashScopeEmbeddings(
        model="text-embedding-v3",
        dashscope_api_key=api_key,
    )
