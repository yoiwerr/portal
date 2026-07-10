"""
知识库管理接口。

GET  /api/knowledge/search?q=  — 搜索知识库 (PGVector)
GET  /api/knowledge/stats       — 知识库统计
POST /api/knowledge/reindex     — 重建索引
"""

from fastapi import APIRouter, HTTPException

from models.schemas import KnowledgeResult

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge"])

_agent = None


def set_agent(agent):
    global _agent
    _agent = agent


@router.get("/search")
async def search_knowledge(q: str, top_k: int = 5):
    """搜索本地知识库（PGVector 向量检索）。"""
    if _agent is None or _agent.rag is None:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    chunks = await _agent.rag.query(q, top_k=top_k)
    results = []
    for i, chunk in enumerate(chunks):
        results.append(KnowledgeResult(
            name=f"结果 {i+1}",
            description=chunk[:200],
            relevance=1.0 - (i * 0.15),
        ))
    return {"results": results, "query": q}


@router.get("/stats")
async def get_kb_stats():
    """获取知识库统计信息。"""
    if _agent is None or _agent.rag is None:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    return await _agent.rag.get_kb_stats()


@router.post("/reindex")
async def reindex_knowledge():
    """重建知识库索引。"""
    if _agent is None or _agent.rag is None:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    try:
        count = await _agent.rag.reindex_all()
        return {"ok": True, "indexed_chunks": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"索引失败: {str(e)}")
