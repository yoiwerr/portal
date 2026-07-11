"""
MakeItSmooth - 个人工作流增强 Agent

框架: LangGraph + LangChain Agent + FastAPI
向量库: PostgreSQL + PGVector (与 ChatLab 共用)
推理: 多 Provider (DashScope / DeepSeek / OpenAI / Local)

启动方式:
    python app.py
    打开 http://127.0.0.1:8000 查看首页
    API 文档: http://127.0.0.1:8000/docs
"""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import config
from services.session_store import SessionStore
from services.vector_store import PGVectorStore, build_connection_string
from services.rag_service import RAGService
from core.llm_client import create_model
from core.agent import Agent
from routers import chat, sessions, knowledge, feedback

# ── 全局服务引用（由 lifespan 初始化） ──
session_store: SessionStore = None
rag_service: RAGService = None
agent: Agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan — 启动时初始化所有服务，关闭时清理。"""
    global session_store, rag_service, agent

    print("=" * 60)
    print("  MakeItSmooth - 个人工作流增强 Agent")
    print("  LangGraph + LangChain Agent + FastAPI")
    print(f"  Provider: {config.llm_provider} | Model: {config.llm_model}")
    print(f"  Vector DB: PostgreSQL + PGVector")
    print(f"  Embedding: text-embedding-v4")
    print("=" * 60)

    print(f"\n[Data]   {config.data_dir}")
    print(f"[SQLite] {config.db_path}")
    print(f"[RAG]    {config.knowledge_base_dir}")
    print(f"[PG]     {config.pg_host}:{config.pg_port}/{config.pg_database}")

    # ── 1. SQLite 会话存储 ──
    print("\n[Init] SQLite 会话存储...")
    session_store = SessionStore(config.db_path)

    # ── 2. PGVector 向量库 ──
    print("[Init] PGVector 向量库...")
    conn_str = build_connection_string(config)
    vector_store = PGVectorStore(conn_str)
    await vector_store.ensure_tables()
    print(f"  [OK] PGVector 表就绪: {list(PGVectorStore.COLLECTIONS.keys())}")

    # ── 3. RAG 服务 ──
    print("[Init] RAG 服务...")
    rag_service = RAGService(
        vector_store=vector_store,
        knowledge_base_dir=config.knowledge_base_dir,
        api_key=config.dashscope_api_key,
        chunk_min=config.rag_chunk_min,
        chunk_max=config.rag_chunk_max,
        similarity_threshold=config.similarity_threshold,
        rerank_enabled=config.rerank_enabled,
        rerank_model=config.rerank_model,
        rerank_top_k=config.rerank_top_k,
        rerank_coarse_k=config.rerank_coarse_k,
    )
    await rag_service.ensure_ready()

    stats = await rag_service.get_kb_stats()
    print(f"  [OK] 知识库: {stats['source_files']} 个源文件, {stats['chunk_count']} 个片段")
    if stats['source_files'] > 0 and stats['chunk_count'] == 0:
        print("  [RAG] 首次运行，正在索引知识库...")
        count = await rag_service.ingest_knowledge_base()
        print(f"  [RAG] 已索引 {count} 个知识片段")

    # ── 4. LLM 模型 ──
    print("[Init] LLM 模型...")
    model = create_model(config)
    print(f"  [OK] {config.llm_provider}: {config.llm_model}")

    # ── 5. Agent ──
    print("[Init] Agent（LangGraph ReAct + Skills）...")
    agent = Agent(
        model=model,
        rag_service=rag_service,
        session_store=session_store,
        config=config,
    )

    # ── 注入路由 ──
    chat.set_agent(agent)
    sessions.set_agent(agent)
    knowledge.set_agent(agent)
    feedback.set_agent(agent)

    print("\n  [OK] 全部服务就绪!")
    print("=" * 60)

    yield  # ← 应用运行中

    # ── 关闭清理 ──
    print("\n[Shutdown] 关闭连接...")
    vector_store.close()
    print("  [OK] 已关闭")


def create_app() -> FastAPI:
    """构建 FastAPI 应用。"""

    app = FastAPI(
        title="MakeItSmooth API",
        description="个人工作流增强 Agent — 引导式对话 + Skill 执行",
        version="2.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 路由 ──
    app.include_router(chat.router)
    app.include_router(sessions.router)
    app.include_router(knowledge.router)
    app.include_router(feedback.router)

    # ── 静态文件 + 首页 ──
    static_dir = config.project_root / "static"

    @app.get("/", response_class=HTMLResponse)
    async def homepage():
        with open(static_dir / "index.html", encoding="utf-8") as f:
            return f.read()

    if static_dir.exists():
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
        kb_stats = {}
        if rag_service:
            try:
                kb_stats = await rag_service.get_kb_stats()
            except Exception:
                kb_stats = {"error": "PG 连接失败"}

        return {
            "status": "ok",
            "provider": config.llm_provider,
            "llm": config.llm_model,
            "vector_db": "pgvector",
            "pg_host": f"{config.pg_host}:{config.pg_port}/{config.pg_database}",
            "kb_stats": kb_stats,
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
