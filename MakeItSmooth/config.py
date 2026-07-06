"""
MakeItSmooth 全局配置。

推理引擎: DashScope (通义千问) — 对齐 ChatLab
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
    chroma_path: Path = field(default=None)
    knowledge_base_dir: Path = field(default=None)
    export_dir: Path = field(default=None)

    # === 服务配置 ===
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # === LLM 配置（DashScope，对齐 ChatLab） ===
    dashscope_api_key: str = ""
    llm_model: str = "qwen3.6-flash"
    llm_temperature: float = 0.7
    llm_timeout: float = 120.0

    # === 追问引擎配置 ===
    clarify_threshold: float = 0.75
    max_clarify_rounds: int = 5
    max_questions_per_round: int = 3

    # === RAG 配置 ===
    rag_top_k: int = 3
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50

    # === 搜索 API（Phase 2） ===
    search_api_key: str = ""
    search_api_url: str = ""

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
            if self.chroma_path is None:
                self.chroma_path = windows_tmp / "chroma"
        else:
            if self.db_path is None:
                self.db_path = self.data_dir / "makeitsmooth.db"
            if self.chroma_path is None:
                self.chroma_path = self.data_dir / "chroma"

        if self.knowledge_base_dir is None:
            self.knowledge_base_dir = self.project_root / "knowledge_base"
        if self.export_dir is None:
            self.export_dir = self.data_dir / "exports"

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_path.mkdir(parents=True, exist_ok=True)
        self.knowledge_base_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "Config":
        config = cls()
        config.api_port = int(os.getenv("API_PORT", str(config.api_port)))
        config.api_host = os.getenv("API_HOST", config.api_host)
        config.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY", "")
        config.llm_model = os.getenv("LLM_MODEL", config.llm_model)
        config.search_api_key = os.getenv("SEARCH_API_KEY", "")
        return config


config = Config.from_env()
