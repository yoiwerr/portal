"""
知识库管理接口。

GET  /api/knowledge/search?q=  — 目录/关键词读取已审阅 Wiki
GET  /api/knowledge/stats       — Wiki 状态
POST /api/knowledge/reindex     — 兼容旧入口，返回 410
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from routers.deps import require_user

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge"], dependencies=[Depends(require_user)])

_agent = None


def set_agent(agent):
    global _agent
    _agent = agent


@router.get("/search")
async def search_knowledge(q: str = Query(max_length=2000), top_k: int = Query(default=5, ge=1, le=8)):
    """按目录与关键词读取本地 Wiki；不会触发外部请求。"""
    if _agent is None or getattr(_agent, "knowledge", None) is None:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    return {"results": [{"name": page["title"], "description": page["text"][:200],
                         "path": page["path"], "reviewed_at": page["reviewed_at"],
                         "sources": page.get("sources", []), "matched_keywords": page["matched_keywords"],
                         "release": page.get("release"), "mode": page.get("mode"),
                         "compiled_at": page.get("compiled_at"), "page_sha256": page.get("page_sha256")}
                        for page in _agent.knowledge.search(q, top_k)], "query": q, "backend": "llm-wiki"}


@router.get("/stats")
async def get_kb_stats():
    """获取知识库统计信息。"""
    if _agent is None or getattr(_agent, "knowledge", None) is None:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    return _agent.knowledge.stats()


@router.post("/reindex")
async def reindex_knowledge():
    """兼容旧入口，显式告知不再构建向量索引。"""
    raise HTTPException(status_code=410, detail="已切换 LLM Wiki。请由管理员执行 wiki_tools.cli 编译、检查并发布候选版本；聊天服务不修改知识库。")
