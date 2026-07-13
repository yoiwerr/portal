"""
Agent 封装层 — FastAPI 的统一入口。V2。

职责:
1. 封装 LangGraph 图的调用细节
2. 管理会话持久化（SQLite）
3. 协调 Skills + 6 核心 Tools
4. astream_events() 支持真正的 token 级流式输出
5. 记忆系统: 会话开始检索历史 + 画像 / 会话结束自动摘要
"""

import logging
from pathlib import Path
from typing import AsyncIterator

from core.graph import create_graph
from core.context_engine import ContextEngine
from services.rag_service import RAGService
from services.session_store import SessionStore
from tools import inject_services

logger = logging.getLogger(__name__)


class Agent:

    def __init__(self, model, rag_service=None, session_store=None, config=None):
        self.model = model
        self.rag = rag_service
        self.sessions = session_store
        self.config = config

        # ── Context Engine（对话摘要 + 压缩 + L3 LLM提取 + PGVector持久化）──
        # vector_store + embedding_fn 在 _init_memory 后补注入（依赖 rag 初始化）
        self.context_engine = ContextEngine(model=model)

        # ── 记忆系统 ──
        self.session_memory = None
        self.user_profile = None
        self._init_memory()

        # ── 工具服务注入（一次性，不需要每轮对话重复）──
        inject_services(rag_service=rag_service, config=config)

        # ── Skills ──
        from skills.prompt_refiner import PromptRefiner
        from skills.work_arranger import WorkArranger
        from skills.info_retention import InfoRetention

        self.skills = {
            "prompt_refiner": PromptRefiner(),
            "work_arranger": WorkArranger(),
            "info_retention": InfoRetention(),
        }
        from skills.code_review import CodeReview
        self.skills["code_review"] = CodeReview()

        # ── LangGraph 图 ──
        self.graph = create_graph(
            rag_service=rag_service, skills=self.skills, model=model,
        )

    def _init_memory(self):
        """初始化 L2/L3 记忆系统（依赖 PGVector + Embedding，可选）。"""
        if not self.rag or not self.config:
            return
        memory_enabled = getattr(self.config, "memory_enabled", True)
        if not memory_enabled:
            return

        try:
            from memory.session_memory import SessionMemory
            from memory.user_profile import UserProfile

            embed_model = self.rag.embedding_model
            vector_store = self.rag.store

            self.session_memory = SessionMemory(
                vector_store=vector_store,
                embedding_model=embed_model,
                llm_model=self.model,
            )
            self.user_profile = UserProfile(
                vector_store=vector_store,
                embedding_model=embed_model,
                llm_model=self.model,
            )
            # ── 注入 vector_store + embedding_fn 到 ContextEngine ──
            self.context_engine.vector_store = vector_store
            self.context_engine.embedding_fn = embed_model.embed_documents

            logger.info("[Memory] L2/L3 记忆系统已初始化 (ContextEngine L3 已接入 PGVector)")
        except Exception as e:
            logger.warning(f"[Memory] 初始化失败 (可忽略): {e}")

    # ============================================================
    # 兼容旧版
    # ============================================================

    async def process_message(
        self, message, module="auto", background="", session_id=None,
        clarify_round=0, dimensions=None, extra_context="",
    ) -> dict:
        if dimensions is None:
            dimensions = {}
        if not session_id:
            session_id = self.sessions.create_session(
                module=module, background=background,
            )

        self.sessions.save_message(session_id=session_id, role="user",
                                   content=message, msg_type="input")

        # ── 记忆注入 ──
        memory_context = await self._retrieve_memory(message)

        initial_state = await self._build_initial_state(
            message=message, module=module, background=background,
            session_id=session_id, extra_context=extra_context,
            dimensions=dimensions, clarify_round=clarify_round,
            memory_context=memory_context,
        )

        result = await self.graph.ainvoke(initial_state)

        output = result.get("output", "")
        new_dimensions = result.get("expressed_dimensions", {})
        new_clarify_round = result.get("clarify_round", clarify_round)
        plan = result.get("plan", {})
        intent = result.get("intent", {})
        completeness = plan.get("completeness", 0)

        if new_clarify_round > clarify_round:
            action_type = "clarify"
            self.sessions.save_message(
                session_id=session_id, role="assistant", content=output,
                msg_type="clarify",
                meta={"progress": completeness, "dimensions": new_dimensions, "intent": intent},
            )
            self.sessions.update_session(
                session_id=session_id, clarify_rounds=new_clarify_round,
                completeness=completeness,
            )
        else:
            action_type = "execute"
            self.sessions.save_message(
                session_id=session_id, role="assistant", content=output,
                msg_type="result",
                meta={"progress": completeness, "dimensions": new_dimensions, "intent": intent},
            )
            self.sessions.update_session(
                session_id=session_id, completeness=completeness, status="completed",
            )
            # ── 会话结束时自动摘要 ──
            await self._summarize_on_complete(session_id, output, intent)

        # ── 三层上下文更新：每轮对话后更新 L2 摘要 + 提取 L3 事实 ──
        try:
            messages = self.sessions.get_conversation(session_id)
            await self.context_engine.update_after_turn(
                messages=messages,
                session_id=session_id,
                turn_output=output,
            )
        except Exception as e:
            logger.warning(f"[ContextEngine] 更新失败 (非关键): {e}")

        return {
            "type": action_type, "session_id": session_id, "message": output,
            "state_update": {
                "clarify_round": new_clarify_round, "dimensions": new_dimensions,
                "is_complete": action_type == "execute",
            },
        }

    # ============================================================
    # Token 级流式
    # ============================================================

    async def process_message_stream(
        self, message, module="auto", background="", session_id=None,
        clarify_round=0, dimensions=None, extra_context="",
    ) -> AsyncIterator[dict]:
        if dimensions is None:
            dimensions = {}
        if not session_id:
            session_id = self.sessions.create_session(
                module=module, background=background,
            )

        self.sessions.save_message(session_id=session_id, role="user",
                                   content=message, msg_type="input")

        yield {"event": "session", "data": {
            "session_id": session_id, "module": module,
            "model": getattr(self.config, "llm_model", "unknown"),
        }}

        # ── 记忆注入 ──
        memory_context = await self._retrieve_memory(message)

        initial_state = await self._build_initial_state(
            message=message, module=module, background=background,
            session_id=session_id, extra_context=extra_context,
            dimensions=dimensions, clarify_round=clarify_round,
            memory_context=memory_context,
        )

        # ── 估算输入 token: 序列化 initial_state 用 cl100k_base 计数 ──
        input_tokens = _estimate_input_tokens(initial_state)
        logger.info(
            f"[Agent] start session={session_id} input_est={input_tokens} "
            f"module={module}"
        )

        full_output = ""
        token_count = 0
        final_state = None

        try:
            async for event in self.graph.astream_events(initial_state, version="v2"):
                kind = event.get("event", "")

                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk", None)
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        token_text = chunk.content
                        full_output += token_text
                        token_count += 1
                        yield {"event": "token", "data": {
                            "content": token_text, "token_index": token_count,
                        }}

                elif kind == "on_tool_start":
                    yield {"event": "tool_start", "data": {
                        "tool_name": event.get("name", "unknown"),
                        "tool_input": _safe_serialize(event.get("data", {}).get("input", {})),
                    }}

                elif kind == "on_tool_end":
                    yield {"event": "tool_end", "data": {
                        "tool_name": event.get("name", "unknown"),
                        "tool_output": str(event.get("data", {}).get("output", ""))[:500],
                    }}

        except Exception as e:
            logger.error(f"[Agent] Stream 失败: {e}", exc_info=True)
            yield {"event": "error", "data": {"detail": str(e)}}
            return

        output = full_output
        new_clarify_round = clarify_round
        new_dims = dimensions or {}
        intent = {}
        completeness = 0

        # 从 state 取 output（clarify 节点不走 LLM stream，full_output 为空）
        try:
            raw_state = self.graph.get_state(initial_state)
            if raw_state:
                final_values = raw_state.values if hasattr(raw_state, "values") else raw_state
                state_output = final_values.get("output", "")
                if state_output:
                    output = state_output
                new_clarify_round = final_values.get("clarify_round", clarify_round)
                new_dims = final_values.get("expressed_dimensions", {})
                intent = final_values.get("intent", {})
                plan = final_values.get("plan", {})
                completeness = plan.get("completeness", 0)
        except Exception:
            pass

        if output:
            if new_clarify_round > clarify_round:
                self.sessions.save_message(
                    session_id=session_id, role="assistant", content=output,
                    msg_type="clarify", meta={"progress": completeness, "intent": intent},
                )
                self.sessions.update_session(
                    session_id=session_id, clarify_rounds=new_clarify_round,
                    completeness=completeness,
                )
                yield {"event": "clarify", "data": {
                    "type": "clarify", "progress": completeness, "module": module,
                    "message": output,
                }}
            else:
                self.sessions.save_message(
                    session_id=session_id, role="assistant", content=output,
                    msg_type="result", meta={"progress": completeness, "intent": intent},
                )
                self.sessions.update_session(
                    session_id=session_id, completeness=completeness, status="completed",
                )
                yield {"event": "execute", "data": {
                    "type": "execute", "skill": module, "module": module,
                    "message": output, "tool_calls_made": 0,
                }}
                # ── 会话结束时自动摘要 ──
                await self._summarize_on_complete(session_id, output, intent)

        # ── 三层上下文更新：每轮对话后更新 L2 摘要 + 提取 L3 事实 ──
        try:
            messages = self.sessions.get_conversation(session_id)
            await self.context_engine.update_after_turn(
                messages=messages,
                session_id=session_id,
                turn_output=output,
            )
        except Exception as e:
            logger.warning(f"[ContextEngine] 更新失败 (非关键): {e}")

        logger.info(
            f"[Agent] done session={session_id} tokens={token_count} "
            f"input_est={input_tokens} module={module} intent={intent.get('label', '?')}"
        )

        yield {"event": "done", "data": {
            "session_id": session_id, "message_id": 0,
            "tokens_used": token_count,
            "input_tokens_est": input_tokens,
            "intent": intent,
        }}

    # ============================================================
    # 记忆: 检索 + 摘要
    # ============================================================

    async def _retrieve_memory(self, message: str) -> str:
        """会话开始时检索相关历史 + 用户画像。"""
        parts = []

        if self.session_memory:
            try:
                hist = await self.session_memory.retrieve(message, top_k=3)
                if hist:
                    parts.append(hist)
            except Exception as e:
                logger.warning(f"[Memory] 检索失败: {e}")

        if self.user_profile:
            try:
                profile = await self.user_profile.format_for_context()
                if profile:
                    parts.append(profile)
            except Exception as e:
                logger.warning(f"[Profile] 获取失败: {e}")

        return "\n".join(parts) if parts else ""

    async def _summarize_on_complete(self, session_id: str, output: str, intent: dict):
        """会话任务完成时异步触发摘要。不阻塞主流程。"""
        if not self.session_memory or not self.user_profile:
            return

        try:
            messages = self.sessions.get_conversation(session_id)
            if len(messages) < 3:
                return  # 太短不摘要

            module = intent.get("module", "")

            # L2: 会话摘要
            summary = await self.session_memory.summarize_and_store(
                session_id=session_id, messages=messages, module=module,
            )

            # L3: 用户画像更新
            if summary:
                import json
                try:
                    summary_data = json.loads(summary)
                except json.JSONDecodeError:
                    summary_data = {"summary": output[:500]}
                await self.user_profile.update_from_summary(summary_data)

        except Exception as e:
            logger.warning(f"[Memory] 摘要/画像更新失败 (非关键): {e}")

    # ============================================================
    # 工具方法
    # ============================================================

    async def _build_initial_state(self, message, module, background, session_id,
                             extra_context, dimensions, clarify_round, memory_context="") -> dict:
        # ── Context Engine: 构建对话上下文 ──
        ctx = await self.context_engine.build(
            session_store=self.sessions,
            session_id=session_id,
            current_message=message,
            intent=None,  # intent 此时尚未识别，Router 会在 graph 中处理
            expressed_dimensions=dimensions,
        )

        # 把记忆上下文拼到 extra_context 前面
        full_extra = extra_context or ""
        if memory_context:
            full_extra = memory_context + "\n\n" + full_extra

        return {
            "messages": [{"role": "user", "content": message}],
            "module": module,
            "background": background or "",
            "extra_context": full_extra.strip(),
            "expressed_dimensions": dimensions,
            "clarify_round": clarify_round,
            "rag_context": "",
            "enriched_query": ctx.enriched_query,
            "plan": {},
            "tool_results": [],
            "reflection_count": 0,
            "output": "",
            "intent": {},
            # ── 三层上下文注入 ──
            "l1_raw": ctx.l1_raw,
            "l2_summary": ctx.l2_summary,
            "l3_facts": ctx.l3_facts,
            "last_turn_summary": ctx.last_turn_summary,
            "turn_count": ctx.turn_count,
            # ── Planner checkpoint ──
            "checkpoint_feedback": "",
            "checkpoint_retry_count": 0,
            # ── 执行进度追踪 ──
            "completed_steps": [],
            "execute_round": 0,
        }

    def list_sessions(self, module=None):
        return self.sessions.list_sessions(module=module)

    def export_session(self, session_id):
        from services.md_export import export_session_to_md
        return str(export_session_to_md(
            session_id=session_id, session_store=self.sessions,
            output_dir=self.export_dir,
        ))

    def load_md_context(self, file_paths):
        from services.md_export import load_multiple_md_files
        return load_multiple_md_files([Path(p) for p in file_paths])

    @property
    def export_dir(self):
        return self.config.export_dir if self.config else Path("data/exports")


def _safe_serialize(obj):
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_safe_serialize(v) for v in obj]
    elif hasattr(obj, "__dict__"):
        return str(obj)
    try:
        import json; json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


def _estimate_input_tokens(initial_state: dict) -> int:
    """估算 initial_state 的 token 数 — 用字符数/因子 粗略估计。

    不做精确计数（精确需要跑 tiktoken 且 LLM 的 tokenizer 不一定匹配）。
    用途: 日志中的成本估算信号，不是计费用。
    """
    try:
        import json
        text = json.dumps(initial_state, ensure_ascii=False, default=str)
        chars = len(text)
        # 中文≈1.5 char/token, 英文≈4 char/token, 混合取≈2.5
        return max(1, int(chars / 2.5))
    except Exception:
        return 0
