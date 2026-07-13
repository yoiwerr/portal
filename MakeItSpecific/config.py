"""MakeItSpecific global config."""

import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

_env = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env if _env.exists() else Path(__file__).resolve().parent / ".env")


@dataclass
class Config:
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.resolve())
    data_dir: Path = field(default=None)
    knowledge_base_dir: Path = field(default=None)
    export_dir: Path = field(default=None)
    api_host: str = "0.0.0.0"
    api_port: int = 8001
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "chatdemopg"
    pg_user: str = "postgres"
    pg_password: str = ""
    llm_provider: str = "auto"
    llm_model: str = "qwen-plus"
    llm_temperature: float = 0.7
    llm_timeout: float = 120.0
    dashscope_api_key: str = ""
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o"
    local_llm_url: str = ""
    clarify_threshold: float = 0.75
    max_clarify_rounds: int = 3
    max_questions_per_round: int = 5
    max_tool_rounds: int = 10
    agent_timeout: float = 180.0
    rag_top_k: int = 3
    rag_chunk_min: int = 200
    rag_chunk_max: int = 800
    similarity_threshold: float = 0.6
    rerank_enabled: bool = True
    rerank_model: str = "qwen3-rerank"
    rerank_top_k: int = 5
    rerank_coarse_k: int = 20
    memory_enabled: bool = True
    sandbox_enabled: bool = False
    sandbox_timeout: float = 30.0

    def __post_init__(self):
        if self.data_dir is None:
            self.data_dir = self.project_root / "data"
        if self.knowledge_base_dir is None:
            self.knowledge_base_dir = self.project_root / "knowledge_base"
        if self.export_dir is None:
            self.export_dir = self.data_dir / "exports"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_base_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls):
        c = cls()
        for a in ("api_port","api_host","llm_provider","llm_model",
                  "pg_host","pg_port","pg_database","pg_user","pg_password",
                  "deepseek_base_url","deepseek_model","openai_base_url","openai_model",
                  "local_llm_url","rerank_model"):
            ev = os.getenv(a.upper(), "")
            if ev and hasattr(c, a): setattr(c, a, type(getattr(c, a))(ev))
        for a in ("llm_temperature","llm_timeout","max_tool_rounds","agent_timeout",
                  "rag_top_k","rag_chunk_min","rag_chunk_max","similarity_threshold",
                  "rerank_top_k","rerank_coarse_k","sandbox_timeout","max_questions_per_round"):
            ev = os.getenv(a.upper(), "")
            if ev: setattr(c, a, float(ev))
        for a in ("max_clarify_rounds",):
            ev = os.getenv(a.upper(), "")
            if ev: setattr(c, a, int(ev))
        c.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY","")
        c.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY","")
        c.openai_api_key = os.getenv("OPENAI_API_KEY","")
        c.pg_password = os.getenv("PGSQLPASSWORD","")
        c.memory_enabled = os.getenv("MEMORY_ENABLED","true").lower() != "false"
        c.sandbox_enabled = os.getenv("SANDBOX_ENABLED","false").lower() == "true"
        c.rerank_enabled = os.getenv("RERANK_ENABLED","true").lower() != "false"
        return c


config = Config.from_env()
