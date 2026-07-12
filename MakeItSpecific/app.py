"""MakeItSpecific — FastAPI + LangGraph + LangChain."""

import logging, sys
from pathlib import Path
from contextlib import asynccontextmanager

ROOT = Path(__file__).resolve().parent
(ROOT / "data" / "logs").mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] %(name)s | %(message)s",
    datefmt="%m-%d %H:%M:%S", stream=sys.stdout)
logging.getLogger("httpx").setLevel(logging.WARNING)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from config import config
from services.session_store import SessionStore
from services.vector_store import PGVectorStore, build_connection_string
from services.rag_service import RAGService
from core.llm_client import create_model
from core.agent import Agent
from routers import chat, sessions, knowledge

ss = None; rag = None; agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ss, rag, agent

    p = config.llm_provider
    if p == "deepseek": m = config.deepseek_model
    elif p == "openai": m = config.openai_model
    else: m = config.llm_model

    print("=" * 60)
    print(f"  MakeItSpecific — Provider: {p} | Model: {m}")
    print("=" * 60)

    ss = SessionStore(config.db_path)

    conn = build_connection_string(config)
    vs = PGVectorStore(conn)
    await vs.ensure_tables()

    rag = RAGService(
        vector_store=vs,
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
    await rag.ensure_ready()
    stats = await rag.get_kb_stats()
    print(f"  KB: {stats['source_files']} files, {stats['chunk_count']} chunks")
    if stats['source_files'] > 0:
        await rag.ingest_knowledge_base()

    model = create_model(config)
    agent = Agent(model=model, rag_service=rag, session_store=ss, config=config)
    chat.set_agent(agent); sessions.set_agent(agent); knowledge.set_agent(agent)

    print("  [OK] ready\n")
    yield
    vs.close()


app = FastAPI(title="MakeItSpecific", version="3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(chat.router); app.include_router(sessions.router); app.include_router(knowledge.router)

STATIC = ROOT / "static"

@app.get("/", response_class=HTMLResponse)
async def homepage():
    return (STATIC / "index.html").read_text(encoding="utf-8")

@app.get("/api/health")
async def health():
    return {"status": "ok", "provider": config.llm_provider}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=config.api_host, port=config.api_port, reload=True, log_level="info")
