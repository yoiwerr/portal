"""
MakeItSmooth - 个人工作流增强 Agent

框架: LangGraph + LangChain Agent + FastAPI
推理: DashScope (通义千问)

启动方式:
    python app.py
    打开 http://127.0.0.1:8000 查看首页
    API 文档: http://127.0.0.1:8000/docs
"""

import os
import sys
from pathlib import Path

# ── 抑制 ChromaDB telemetry (chromadb 0.5.x 在 WSL 环境中有 posthog capture 签名不兼容) ──
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import config
from services.session_store import SessionStore
from services.rag_service import RAGService
from core.llm_client import create_model
from core.agent import Agent
from routers import chat, sessions, knowledge


def create_app() -> FastAPI:
    """构建 FastAPI 应用。参照 ChatLab src/main.py 的结构。"""

    app = FastAPI(
        title="MakeItSmooth API",
        description="个人工作流增强 Agent — 引导式对话 + Skill 执行",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 初始化服务 ──
    print("=" * 60)
    print("  MakeItSmooth - 个人工作流增强 Agent")
    print("  LangGraph + LangChain Agent + FastAPI")
    print(f"  LLM: {config.llm_model} @ DashScope")
    print(f"  Embedding: text-embedding-v3")
    print("=" * 60)

    print(f"\n[Data] {config.data_dir}")
    print(f"[DB]   {config.db_path}")
    print(f"[RAG]  {config.knowledge_base_dir}")

    print("\n[Init] 初始化服务...")
    session_store = SessionStore(config.db_path)
    rag_service = RAGService(config.chroma_path, config.knowledge_base_dir, api_key=config.dashscope_api_key)
    model = create_model(config)

    stats = rag_service.get_kb_stats()
    print(f"[RAG] 知识库状态: {stats['source_files']} 个源文件, {stats['chunk_count']} 个片段")
    if stats['source_files'] > 0 and stats['chunk_count'] == 0:
        print("[RAG] 首次运行，正在索引知识库...")
        count = rag_service.ingest_knowledge_base()
        print(f"[RAG] 已索引 {count} 个知识片段")

    print("[Init] 初始化 Agent（LangGraph 图 + Skills）...")
    agent = Agent(
        model=model,
        rag_service=rag_service,
        session_store=session_store,
        config=config,
    )

    # ── 注册路由 ──
    chat.set_agent(agent)
    sessions.set_agent(agent)
    knowledge.set_agent(agent)

    app.include_router(chat.router)
    app.include_router(sessions.router)
    app.include_router(knowledge.router)

    # ── 静态文件 + 首页 ──
    static_dir = config.project_root / "static"

    @app.get("/", response_class=HTMLResponse)
    async def homepage():
        with open(static_dir / "index.html", encoding="utf-8") as f:
            return f.read()

    if static_dir.exists():
        # StaticFiles with cache headers (7d) for production
        from starlette.staticfiles import StaticFiles as _SF
        class _CachedStaticFiles(_SF):
            async def __call__(self, scope, receive, send):
                async def _send(msg):
                    if msg["type"] == "http.response.start":
                        headers = {h[0]: h[1] for h in msg.get("headers", [])}
                        headers.setdefault(b"cache-control", b"public, max-age=604800")
                        msg["headers"] = [(k, v) for k, v in headers.items()]
                    await send(msg)
                await super().__call__(scope, receive, _send)
        app.mount("/css", _CachedStaticFiles(directory=str(static_dir / "css")), name="css")
        app.mount("/js", _CachedStaticFiles(directory=str(static_dir / "js")), name="js")

    # ── 健康检查 ──
    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "llm": config.llm_model,
            "provider": "dashscope",
            "kb_stats": rag_service.get_kb_stats(),
        }

    return app


# ── 应用实例 ──
app = create_app()


if __name__ == "__main__":
    import uvicorn

    host = config.api_host
    port = config.api_port

    print("\n" + "=" * 60)
    print("  [OK] 准备就绪!")
    print(f"  首页:     http://{host}:{port}")
    print(f"  API 文档: http://{host}:{port}/docs")
    print("  按 Ctrl+C 停止")
    print("=" * 60 + "\n")

    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=True,
        log_level="info",
    )
