"""
MakeItSmooth 全局配置。

推理引擎: 多 Provider 支持 (DashScope / DeepSeek / OpenAI / Local)
Agent 框架: LangGraph + LangChain
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """全局配置，通过环境变量覆盖默认值。"""

    # === 项目路径 ===
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.resolve())
    data_dir: Path = field(default=None)
    db_path: Path = field(default=None)
    knowledge_base_dir: Path = field(default=None)
    export_dir: Path = field(default=None)

    # === PostgreSQL (PGVector — 与 ChatLab 共用) ===
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "makeitsmooth"
    pg_user: str = "postgres"
    pg_password: str = ""

    # === 服务配置 ===
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # === LLM Provider 选择 ===
    # 支持: dashscope | deepseek | openai | local | auto (自动检测)
    llm_provider: str = "auto"
    llm_model: str = "qwen-plus"           # 默认模型 (dashscope / local 使用)
    llm_temperature: float = 0.7
    llm_timeout: float = 120.0

    # === 各 Provider 专属配置 ===
    # DashScope
    dashscope_api_key: str = ""

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # OpenAI
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o"

    # Local (vLLM / SGLang / Ollama)
    local_llm_url: str = ""

    # === 追问引擎配置 ===
    clarify_threshold: float = 0.75
    max_clarify_rounds: int = 5
    max_questions_per_round: int = 3

    # === Agent 配置 ===
    max_tool_rounds: int = 10              # ReAct Agent 最大工具调用轮数
    agent_timeout: float = 180.0           # Agent 总超时

    # === RAG 配置 ===
    rag_top_k: int = 3
    rag_chunk_min: int = 200
    rag_chunk_max: int = 800
    similarity_threshold: float = 0.6

    # === Rerank 配置 ===
    rerank_enabled: bool = True
    rerank_model: str = "qwen3-rerank"       # 百炼 Rerank: qwen3-rerank / gte-rerank-v2
    rerank_top_k: int = 5                     # 粗筛 top-N → Rerank → 精排 top-K
    rerank_coarse_k: int = 20                 # 粗筛时的候选数（用于 Rerank 输入）

    # === 搜索 API ===
    search_api_key: str = ""               # Tavily / Brave Search API key
    search_api_url: str = ""               # 可选，自定义搜索 API URL

    # === 记忆系统 ===
    memory_enabled: bool = True            # L2/L3 记忆开关
    memory_max_summaries: int = 100        # 最多保留 100 个会话摘要

    # === 沙箱 ===
    sandbox_enabled: bool = False          # Python 代码执行沙箱 (安全风险，默认关闭)
    sandbox_timeout: float = 30.0          # 沙箱执行超时

    def __post_init__(self):
        if self.data_dir is None:
            self.data_dir = self.project_root / "data"

        project_root_str = str(self.project_root)
        self._is_wsl_on_windows = (
            project_root_str.startswith("\\\\wsl.localhost\\")
            or project_root_str.startswith("//wsl.localhost/")
        )

        if self._is_wsl_on_windows:
            windows_tmp = Path(os.environ.get("TEMP", os.path.expanduser("~"))) / ".makeitsmooth"
            windows_tmp.mkdir(parents=True, exist_ok=True)
            if self.db_path is None:
                self.db_path = windows_tmp / "makeitsmooth.db"
        else:
            if self.db_path is None:
                self.db_path = self.data_dir / "makeitsmooth.db"

        if self.knowledge_base_dir is None:
            self.knowledge_base_dir = self.project_root / "knowledge_base"
        if self.export_dir is None:
            self.export_dir = self.data_dir / "exports"

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_base_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "Config":
        config = cls()
        config.api_port = int(os.getenv("API_PORT", str(config.api_port)))
        config.api_host = os.getenv("API_HOST", config.api_host)

        # LLM Provider
        config.llm_provider = os.getenv("LLM_PROVIDER", config.llm_provider)
        config.llm_model = os.getenv("LLM_MODEL", config.llm_model)
        config.llm_temperature = float(os.getenv("LLM_TEMPERATURE", str(config.llm_temperature)))
        config.llm_timeout = float(os.getenv("LLM_TIMEOUT", str(config.llm_timeout)))

        # 各 Provider API keys
        config.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY", "")
        config.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
        config.deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", config.deepseek_base_url)
        config.deepseek_model = os.getenv("DEEPSEEK_MODEL", config.deepseek_model)
        config.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        config.openai_base_url = os.getenv("OPENAI_BASE_URL", "")
        config.openai_model = os.getenv("OPENAI_MODEL", config.openai_model)
        config.local_llm_url = os.getenv("LOCAL_LLM_URL", "")

        # Agent
        config.max_tool_rounds = int(os.getenv("MAX_TOOL_ROUNDS", str(config.max_tool_rounds)))
        config.agent_timeout = float(os.getenv("AGENT_TIMEOUT", str(config.agent_timeout)))

        # Search
        config.search_api_key = os.getenv("SEARCH_API_KEY", "")
        config.search_api_url = os.getenv("SEARCH_API_URL", "")

        # PostgreSQL (PGVector)
        config.pg_host = os.getenv("DB_HOST", config.pg_host)
        config.pg_port = int(os.getenv("DB_PORT", str(config.pg_port)))
        config.pg_database = os.getenv("DB_NAME", config.pg_database)
        config.pg_user = os.getenv("DB_USER", config.pg_user)
        config.pg_password = os.getenv("PGSQLPASSWORD", "")

        # Memory
        config.memory_enabled = os.getenv("MEMORY_ENABLED", "true").lower() != "false"

        # RAG
        config.rag_top_k = int(os.getenv("RAG_TOP_K", str(config.rag_top_k)))
        config.similarity_threshold = float(os.getenv("SIMILARITY_THRESHOLD", str(config.similarity_threshold)))

        # Rerank
        config.rerank_enabled = os.getenv("RERANK_ENABLED", "true").lower() != "false"
        config.rerank_model = os.getenv("RERANK_MODEL", config.rerank_model)
        config.rerank_top_k = int(os.getenv("RERANK_TOP_K", str(config.rerank_top_k)))
        config.rerank_coarse_k = int(os.getenv("RERANK_COARSE_K", str(config.rerank_coarse_k)))

        # Sandbox
        config.sandbox_enabled = os.getenv("SANDBOX_ENABLED", "false").lower() == "true"
        config.sandbox_timeout = float(os.getenv("SANDBOX_TIMEOUT", str(config.sandbox_timeout)))

        return config


config = Config.from_env()
