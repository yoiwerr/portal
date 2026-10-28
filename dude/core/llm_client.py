"""LLM factory — dashscope|deepseek|openai|local|auto."""

import os, logging

logger = logging.getLogger(__name__)

_P = {}


def _reg(name):
    def d(fn): _P[name] = fn; return fn
    return d


@_reg("dashscope")
def _dashscope(c):
    from langchain_community.chat_models.tongyi import ChatTongyi
    key = getattr(c, "dashscope_api_key", "") or os.getenv("DASHSCOPE_API_KEY", "")
    if not key: raise ValueError("DASHSCOPE_API_KEY not set")
    return ChatTongyi(model=getattr(c, "llm_model", "qwen-plus"), dashscope_api_key=key,
                      temperature=getattr(c, "llm_temperature", 0.7), timeout=getattr(c, "llm_timeout", 120.0))


@_reg("deepseek")
def _deepseek(c):
    from langchain_openai import ChatOpenAI
    key = getattr(c, "deepseek_api_key", "") or os.getenv("DEEPSEEK_API_KEY", "")
    if not key: raise ValueError("DEEPSEEK_API_KEY not set")
    return ChatOpenAI(model=getattr(c, "deepseek_model", "deepseek-chat"), api_key=key,
                      base_url=getattr(c, "deepseek_base_url", "https://api.deepseek.com/v1"),
                      temperature=getattr(c, "llm_temperature", 0.7), timeout=getattr(c, "llm_timeout", 120.0))


@_reg("openai")
def _openai(c):
    from langchain_openai import ChatOpenAI
    key = getattr(c, "openai_api_key", "") or os.getenv("OPENAI_API_KEY", "")
    if not key: raise ValueError("OPENAI_API_KEY not set")
    return ChatOpenAI(model=getattr(c, "openai_model", "gpt-4o"), api_key=key,
                      base_url=getattr(c, "openai_base_url", "") or None,
                      temperature=getattr(c, "llm_temperature", 0.7), timeout=getattr(c, "llm_timeout", 120.0))


@_reg("local")
def _local(c):
    from langchain_openai import ChatOpenAI
    base = getattr(c, "local_llm_url", "") or os.getenv("LOCAL_LLM_URL", "")
    return ChatOpenAI(model=getattr(c, "llm_model", "local"), api_key="not-needed",
                      base_url=base or "http://localhost:8000/v1",
                      temperature=getattr(c, "llm_temperature", 0.7), timeout=getattr(c, "llm_timeout", 120.0))


def create_model(config_obj):
    r = (getattr(config_obj, "llm_provider", "") or "").strip().lower()
    if not r or r == "auto":
        for pk, ak in [("dashscope","dashscope_api_key"), ("deepseek","deepseek_api_key"), ("openai","openai_api_key")]:
            if getattr(config_obj, ak, None) or os.getenv(ak.upper()):
                r = pk; break
    if not r: raise ValueError("No LLM provider. Set LLM_PROVIDER or *_API_KEY in .env")
    if r not in _P: raise ValueError(f"Unknown provider: {r}")
    logger.info(f"[LLM] provider={r}")
    return _P[r](config_obj)
