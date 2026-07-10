"""
L2 跨会话记忆 — 会话摘要向量化存储。

每次会话结束（或用户主动触发）时:
1. LLM 生成对话摘要（关键决策、用户偏好、技术栈、待办项）
2. 摘要向量化存入 PGVector session_memory 表
3. 新会话开始时自动检索相关历史，注入上下文

用法:
    mem = SessionMemory(vector_store, embedding_model, llm_model)
    await mem.summarize_and_store(session_id, messages)
    relevant = await mem.retrieve("React 项目", top_k=5)
"""

import json
import hashlib
import logging
from datetime import datetime
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

SUMMARIZE_SESSION_PROMPT = """你是一个对话摘要助手。请将以下对话提炼为结构化摘要。

## 要求
- 提取关键决策和结论
- 提取用户的技术偏好（语言、框架、工具）
- 提取用户提到的项目/任务名称
- 提取未完成的待办项
- 用 3-5 句话概括对话核心内容

## 输出格式（JSON）
{
  "title": "对话标题（≤20字）",
  "summary": "3-5句话的对话摘要",
  "decisions": ["决策1", "决策2"],
  "tech_stack": ["技术1", "技术2"],
  "projects": ["项目名1"],
  "todos": ["待办1", "待办2"],
  "tags": ["标签1", "标签2"]
}

## 对话内容"""


class SessionMemory:
    """L2 跨会话记忆管理器。

    使用 PGVector session_memory 表存储对话摘要。
    """

    COLLECTION = "session_memory"

    def __init__(self, vector_store, embedding_model, llm_model=None):
        """
        Args:
            vector_store: PGVectorStore 实例
            embedding_model: DashScopeEmbeddings 实例（用于生成 embedding）
            llm_model: LangChain ChatModel（用于生成摘要，可选）
        """
        self.store = vector_store
        self.embedding = embedding_model
        self.llm = llm_model

    async def summarize_and_store(
        self,
        session_id: str,
        messages: list,
        module: str = "",
    ) -> Optional[str]:
        """对会话进行摘要并存入 PGVector。"""
        if self.llm is None:
            logger.warning("[Memory] 无 LLM 模型，跳过摘要生成")
            return None

        convo_text = self._format_messages(messages)
        if len(convo_text) < 50:
            return None

        # LLM 生成摘要
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=SUMMARIZE_SESSION_PROMPT),
                HumanMessage(content=convo_text[:4000]),
            ])
            summary_data = self._parse_summary_json(response.content)
        except Exception as e:
            logger.error(f"[Memory] 摘要生成失败: {e}")
            return None

        summary_json = json.dumps(summary_data, ensure_ascii=False)

        # 生成 embedding
        try:
            emb = self.embedding.embed_query(summary_json)
        except Exception as e:
            logger.error(f"[Memory] Embedding 生成失败: {e}")
            emb = [0.0] * 1024  # fallback

        # 写入 PGVector
        try:
            chunk_id = hashlib.md5(
                f"{session_id}:{datetime.now().isoformat()}".encode()
            ).hexdigest()[:16]

            await self.store.add(
                collection=self.COLLECTION,
                documents=[summary_json],
                embeddings=[emb],
                metadatas=[{
                    "session_id": session_id,
                    "module": module,
                    "title": summary_data.get("title", ""),
                    "tags": ", ".join(summary_data.get("tags", [])),
                    "created_at": datetime.now().isoformat(),
                }],
                ids=[chunk_id],
            )
            logger.info(f"[Memory] 会话摘要已存储: {summary_data.get('title', '')}")
            return summary_json
        except Exception as e:
            logger.error(f"[Memory] 写入失败: {e}")
            return None

    async def retrieve(self, query: str, top_k: int = 5) -> str:
        """检索与当前查询相关的历史会话摘要。"""
        try:
            query_emb = self.embedding.embed_query(query)
            results = await self.store.search(
                collection=self.COLLECTION,
                query_embedding=query_emb,
                top_k=top_k,
            )
        except Exception as e:
            logger.warning(f"[Memory] 检索失败: {e}")
            return ""

        if not results:
            return ""

        lines = ["### 🧠 历史相关对话\n"]
        for i, r in enumerate(results, 1):
            meta = r.get("metadata", {})
            doc = r.get("document", "")
            try:
                data = json.loads(doc)
                title = data.get("title", meta.get("title", "未命名"))
                summary = data.get("summary", doc[:200])
            except (json.JSONDecodeError, TypeError):
                title = meta.get("title", "未命名")
                summary = doc[:200]

            ts = meta.get("created_at", "")[:10]
            lines.append(f"**{i}. {title}** ({ts})")
            lines.append(f"   {summary[:300]}")
            lines.append("")

        return "\n".join(lines)

    async def get_stats(self) -> dict:
        try:
            count = await self.store.count(self.COLLECTION)
            return {"count": count}
        except Exception:
            return {"count": 0}

    def _format_messages(self, messages: list) -> str:
        lines = []
        for m in messages[-20:]:
            role = m.get("role", "unknown") if isinstance(m, dict) else getattr(m, "role", "")
            content = m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
            label = {"user": "👤 用户", "assistant": "🤖 AI"}.get(role, role)
            lines.append(f"{label}: {content[:500]}")
        return "\n".join(lines)

    def _parse_summary_json(self, text: str) -> dict:
        import re
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "title": "会话摘要", "summary": text[:500],
            "decisions": [], "tech_stack": [], "projects": [], "todos": [], "tags": [],
        }
