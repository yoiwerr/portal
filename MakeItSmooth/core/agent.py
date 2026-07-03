"""
Agent 封装层 —— FastAPI 的统一入口。

职责：
1. 封装 LangGraph 图的调用细节
2. 管理会话持久化（SQLite）
3. 协调 Skills（LangChain Agent + Tools 模式）
4. 提供导出、历史加载等辅助接口
"""

from pathlib import Path

from core.graph import create_graph
from services.rag_service import RAGService
from services.session_store import SessionStore
from tools.search import set_tool_services


class Agent:
    """
    MakeItSmooth Agent。

    每次用户发送消息时调用 process_message()。
    内部：
      1. LangGraph 图做维度提取 + 完整度评估 → 追问 or 执行
      2. 执行时调用 skills/ 下的 LangChain Agent
    """

    def __init__(
        self,
        model,
        rag_service: RAGService = None,
        session_store: SessionStore = None,
        config=None,
    ):
        self.model = model              # ChatOpenAI（LangChain 兼容）
        self.rag = rag_service
        self.sessions = session_store
        self.config = config

        # 注册三个 Skill（LangChain Agent 模式）
        from skills.prompt_refiner import PromptRefiner
        from skills.work_arranger import WorkArranger
        from skills.info_retention import InfoRetention

        self.skills = {
            "prompt_refiner": PromptRefiner(),
            "work_arranger": WorkArranger(),
            "info_retention": InfoRetention(),
        }

        # 构建 LangGraph 图
        self.graph = create_graph(
            rag_service=rag_service,
            skills=self.skills,
            model=model,
        )

    # ============================================================
    # 主入口
    # ============================================================

    async def process_message(
        self,
        message: str,
        module: str,
        background: str = "",
        session_id: str = None,
        clarify_round: int = 0,
        dimensions: dict = None,
        extra_context: str = "",
    ) -> dict:
        """处理一条用户消息。返回 clarify 或 execute 结果。"""

        if not session_id:
            session_id = self.sessions.create_session(
                module=module, background=background,
            )

        set_tool_services(
            rag_service=self.rag,
            session_store=self.sessions,
            session_id=session_id,
        )

        self.sessions.save_message(
            session_id=session_id, role="user",
            content=message, msg_type="input",
        )

        initial_state = {
            "messages": [{"role": "user", "content": message}],
            "module": module,
            "background": background or "",
            "extra_context": extra_context or "",
            "expressed_dimensions": dimensions or {},
            "clarify_round": clarify_round,
            "rag_context": "",
            "completeness": 0.0,
            "output": "",
        }

        result = await self.graph.ainvoke(initial_state)
        output = result.get("output", "")
        new_dimensions = result.get("expressed_dimensions", {})
        new_completeness = result.get("completeness", 0)
        new_clarify_round = result.get("clarify_round", clarify_round)

        if new_clarify_round > clarify_round:
            action_type = "clarify"
            is_complete = False
            self.sessions.save_message(
                session_id=session_id, role="assistant",
                content=output, msg_type="clarify",
                meta={"progress": new_completeness, "dimensions": new_dimensions},
            )
            self.sessions.update_session(
                session_id=session_id,
                clarify_rounds=new_clarify_round,
                completeness=new_completeness,
            )
        else:
            action_type = "execute"
            is_complete = True
            self.sessions.save_message(
                session_id=session_id, role="assistant",
                content=output, msg_type="result",
                meta={"progress": new_completeness, "dimensions": new_dimensions},
            )
            self.sessions.update_session(
                session_id=session_id,
                completeness=new_completeness,
                status="completed",
            )

        return {
            "type": action_type,
            "session_id": session_id,
            "message": output,
            "state_update": {
                "clarify_round": new_clarify_round,
                "dimensions": new_dimensions,
                "is_complete": is_complete,
            },
        }

    # ============================================================
    # 辅助接口
    # ============================================================

    def list_sessions(self, module: str = None) -> list[dict]:
        return self.sessions.list_sessions(module=module)

    def export_session(self, session_id: str) -> str:
        from services.md_export import export_session_to_md
        return str(export_session_to_md(
            session_id=session_id,
            session_store=self.sessions,
            output_dir=self.export_dir,
        ))

    def load_md_context(self, file_paths: list[str]) -> str:
        from services.md_export import load_multiple_md_files
        return load_multiple_md_files([Path(p) for p in file_paths])

    @property
    def export_dir(self):
        if self.config:
            return self.config.export_dir
        return Path("data/exports")
