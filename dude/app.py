"""dude — AI 工作流增强 Agent (FastAPI + LangGraph + LangChain)."""

import logging, sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from contextlib import asynccontextmanager

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))

# 日志：终端 + 文件双写，单文件 5MB，保留 3 个备份
_file_handler = RotatingFileHandler(
    LOG_DIR / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)-5s] %(name)s | %(message)s", datefmt="%m-%d %H:%M:%S",
))
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] %(name)s | %(message)s",
    datefmt="%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout), _file_handler],
)
logging.getLogger("httpx").setLevel(logging.WARNING)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import config
from services.session_store import SessionStore
from services.database import build_connection_string
from services.published_wiki import PublishedWikiService
from services.contract_store import ContractStore
from core.llm_client import create_model
from core.agent import Agent
from routers import chat, sessions, knowledge, feedback, files, handover

ss = None; cs = None; agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ss, cs, agent
    ss = cs = agent = None
    for router in (chat, sessions, knowledge, feedback, handover):
        router.set_agent(None)

    p = config.llm_provider
    if p == "deepseek": m = config.deepseek_model
    elif p == "openai": m = config.openai_model
    else: m = config.llm_model

    print("=" * 60)
    print(f"  dude — Provider: {p} | Model: {m}")
    print("=" * 60)

    try:
        conn_string = build_connection_string(config)

        ss = SessionStore(conn_string)
        cs = ContractStore(conn_string)  # 任务契约持久化

        wiki = PublishedWikiService(config.wiki_published_dir, seed_root=ROOT / "wiki",
                                    allow_seed=config.wiki_allow_seed)
        print(f"  Wiki: {wiki.stats()['source_files']} pages; mode={wiki.stats()['mode']}; no embedding startup")

        model = create_model(config)
        agent = Agent(model=model, knowledge_service=wiki, session_store=ss, config=config, contract_store=cs)
        chat.set_agent(agent); sessions.set_agent(agent); knowledge.set_agent(agent); feedback.set_agent(agent); handover.set_agent(agent)

        print("  [OK] ready\n")
    except Exception as e:
        print(f"  [FAIL] 启动失败 (部分功能不可用): {e}")
        import traceback; traceback.print_exc()
        # 不抛异常 — 让 app 启动以便健康检查和静态文件可用
        # agent 保持 None，依赖它的端点返回 503

    yield

    # 清理
    if ss is not None: ss.close()
    if cs is not None: cs.close()


app = FastAPI(title="dude", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(chat.router); app.include_router(sessions.router); app.include_router(knowledge.router); app.include_router(feedback.router); app.include_router(files.router); app.include_router(handover.router)

STATIC = ROOT / "static"

# 静态文件挂载 — 本地开发 + Docker 共用（nginx 反代会透传 /css/ /js/ 路径）
app.mount("/css", StaticFiles(directory=str(STATIC / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(STATIC / "js")), name="js")
app.mount("/source", StaticFiles(directory=str(STATIC / "source")), name="source")

@app.get("/", response_class=HTMLResponse)
async def homepage():
    return (STATIC / "index.html").read_text(encoding="utf-8")

@app.get("/api/health")
async def health():
    deps = {"postgres": False, "agent": agent is not None}
    # 快速 DB 连通性检查
    if ss is not None:
        try:
            cur = ss.conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            deps["postgres"] = True
        except Exception:
            pass

    degraded = not deps["postgres"] or not deps["agent"]
    status_code = 503 if degraded else 200
    return JSONResponse(
        content={"status": "degraded" if degraded else "ok",
                 "provider": config.llm_provider, "deps": deps},
        status_code=status_code,
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=config.api_host, port=config.api_port,
                reload=True, log_level="info")
