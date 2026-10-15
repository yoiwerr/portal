"""
Agent 封装层 — FastAPI 的统一入口。V2。

职责:
1. 封装 LangGraph 图的调用细节
2. 管理会话持久化（PostgreSQL）
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

    def __init__(self, model, rag_service=None, session_store=None, config=None, contract_store=None):
        self.model = model
        self.rag = rag_service
        self.sessions = session_store
        self.contract_store = contract_store
        self.config = config

        # ── Context Engine（对话摘要 + 压缩 + L3 LLM提取 + PGVector持久化）──
        # vector_store + embedding_fn 在 _init_memory 后补注入（依赖 rag 初始化）
        self.context_engine = ContextEngine(model=model)

        # ── 记忆系统 ──
        self.session_memory = None
        self.user_profile = None
        self._init_memory()

        # ── 工具服务注入（一次性，不需要每轮对话重复）──
        inject_services(rag_service=rag_service, config=config, agent=self)

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
            config=config,
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
        clarify_round=0, dimensions=None, extra_context="", user_id="",
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
        memory_context = await self._retrieve_memory(message, session_id)

        initial_state = await self._build_initial_state(
            message=message, module=module, background=background,
            session_id=session_id, extra_context=extra_context,
            dimensions=dimensions, clarify_round=clarify_round,
            memory_context=memory_context, user_id=user_id)

        result = await self.graph.ainvoke(initial_state)

        output = result.get("output", "")
        new_dimensions = result.get("expressed_dimensions", {})
        new_clarify_round = result.get("clarify_round", clarify_round)
        plan = result.get("plan", {})
        intent = result.get("intent", {})
        completeness = plan.get("completeness", 0)
        delivery_error = result.get("delivery_error", False)
        complete = plan.get("response_mode") == "plan" and result.get("delivery_validated", False)
        contract = plan.get("contract", {})
        if self.contract_store and contract.get("goal") and plan.get("response_mode") in {"plan", "clarify"}:
            self._save_planning_contract(session_id, contract, completed=complete)

        if delivery_error:
            action_type = "error"
            self.sessions.save_message(session_id=session_id, role="assistant", content=output,
                                       msg_type="error", meta={"delivery_validated": False})
            self.sessions.update_session(session_id=session_id, status="active")
        elif new_clarify_round > clarify_round:
            action_type = "clarify"
            self.sessions.save_message(
                session_id=session_id, role="assistant", content=output,
                msg_type="clarify",
                meta={"progress": completeness, "dimensions": new_dimensions, "intent": intent,
                      "response_mode": plan.get("response_mode"), "delivery_validated": complete},
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
                meta={"progress": completeness, "dimensions": new_dimensions, "intent": intent,
                      "response_mode": plan.get("response_mode"), "delivery_validated": complete},
            )
            self.sessions.update_session(
                session_id=session_id, completeness=completeness, status="completed" if complete else "active",
            )
            # ── 会话结束时自动摘要 ──
            if complete:
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
                "is_complete": complete,
            },
        }

    # ============================================================
    # Token 级流式
    # ============================================================

    async def process_message_stream(
        self, message, module="auto", background="", session_id=None,
        clarify_round=0, dimensions=None, extra_context="", user_id="",
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
        memory_context = await self._retrieve_memory(message, session_id)

        initial_state = await self._build_initial_state(
            message=message, module=module, background=background,
            session_id=session_id, extra_context=extra_context,
            dimensions=dimensions, clarify_round=clarify_round,
            memory_context=memory_context, user_id=user_id)

        input_tokens = _estimate_input_tokens(initial_state)
        logger.info(
            f"[Agent] start session={session_id} input_est={input_tokens} "
            f"module={module}"
        )

        # ── 用 astream 替代 ainvoke ──
        # astream 在每个节点完成后立即 yield 状态更新，不等到全部结束。
        # 这样可以在每个 LLM 调用完成后向前端推送进度事件，
        # 用户能看到"正在分析→正在执行→正在检查"，而不是等两分钟无响应。
        #
        # astream_events 可以捕获 token 但 execute_node 内部子图的 token 不冒泡，
        # 所以我们只用 astream 做节点级进度，不做 token 级流式。
        output = ""
        intent = {}
        new_clarify_round = clarify_round
        new_dims = dimensions or {}
        completeness = 0.0
        tool_results = []
        multi_perspectives = {}
        multi_synthesis = ""
        plan = {}
        delivery_error = False
        delivery_validated = False

        # 节点 → 前端展示的进度文案
        _NODE_PROGRESS = {
            "router": "正在准备新项目规划…",
            "enrich": None,       # 纯数据加工，不展示
            "rag": "正在检索知识库…",
            "gap_analysis": "正在并行检查还缺哪些关键信息…",
            "planner": "正在梳理想法与默认方案…",
            "clarify": "正在整理追问…",
            "execute": "正在整理方案文案…",
            "checkpoint": "正在校验结果…",
            "reflect": "正在质检…",
        }

        try:
            async for chunk in self.graph.astream(initial_state, stream_mode="updates"):
                # chunk 格式: {node_name: state_update_dict}
                for node_name, node_state in chunk.items():
                    # 推送进度事件（跳过无文案的节点）
                    label = _NODE_PROGRESS.get(node_name)
                    if label:
                        yield {"event": "progress", "data": {
                            "node": node_name,
                            "label": label,
                        }}
                    # 收集最终状态（最后一个节点的输出就是结果）
                    if "output" in (node_state or {}):
                        output = node_state.get("output", "") or output
                    if "intent" in (node_state or {}):
                        intent = node_state.get("intent", intent)
                    if "plan" in (node_state or {}):
                        plan = node_state.get("plan", plan)
                    if "delivery_error" in (node_state or {}):
                        delivery_error = node_state["delivery_error"]
                    if "delivery_validated" in (node_state or {}):
                        delivery_validated = node_state["delivery_validated"]
                    if "expressed_dimensions" in (node_state or {}):
                        new_dims = node_state.get("expressed_dimensions", new_dims)
                    if "clarify_round" in (node_state or {}):
                        new_clarify_round = node_state.get("clarify_round", new_clarify_round)
                    if "tool_results" in (node_state or {}):
                        tool_results = node_state.get("tool_results", tool_results)
                    if "multi_agent_perspectives" in (node_state or {}):
                        multi_perspectives = node_state.get("multi_agent_perspectives", {})
                    if "multi_agent_synthesis" in (node_state or {}):
                        multi_synthesis = node_state.get("multi_agent_synthesis", "")

            completeness = plan.get("completeness", completeness)

        except Exception as e:
            logger.error(f"[Agent] Graph 执行失败: {e}", exc_info=True)
            yield {"event": "error", "data": {"detail": str(e)}}
            return

        # ── 推送任务契约事件 ──
        contract = plan.get("contract", {})
        if contract and contract.get("goal") and plan.get("response_mode") in {"plan", "clarify"}:
            if self.contract_store:
                try:
                    self._save_planning_contract(
                        session_id, contract,
                        completed=plan.get("response_mode") == "plan" and delivery_validated,
                    )
                except Exception as e:
                    logger.warning(f"[Contract] 保存失败 (非关键): {e}")
            yield {"event": "contract", "data": {
                "action": "draft",
                "contract": contract,
            }}

        # ── 推送多 Agent 事件 ──
        if multi_perspectives:
            from services.multi_agent import format_panel_for_sse
            for evt in format_panel_for_sse(multi_perspectives):
                yield evt
            if multi_synthesis:
                yield {
                    "event": "multi_agent_synthesis",
                    "data": {"synthesis": multi_synthesis},
                }

        # ── 推送工具调用事件（如果有的话）──
        for tr in tool_results:
            yield {"event": "tool_start", "data": {
                "tool_name": tr.get("name", "unknown"),
                "tool_input": _safe_serialize(tr.get("args", {})),
            }}
            yield {"event": "tool_end", "data": {
                "tool_name": tr.get("name", "unknown"),
                "tool_output": "",
            }}

        if output:
            complete = plan.get("response_mode") == "plan" and delivery_validated
            if delivery_error:
                self.sessions.save_message(session_id=session_id, role="assistant", content=output,
                                           msg_type="error", meta={"delivery_validated": False})
                self.sessions.update_session(session_id=session_id, status="active")
                yield {"event": "error", "data": {"detail": output}}
            elif new_clarify_round > clarify_round:
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
                    msg_type="result", meta={"progress": completeness, "intent": intent,
                                             "response_mode": plan.get("response_mode"), "delivery_validated": complete},
                )
                self.sessions.update_session(
                    session_id=session_id, completeness=completeness, status="completed" if complete else "active",
                )
                yield {"event": "execute", "data": {
                    "type": "execute", "skill": module, "module": module,
                    "message": output, "tool_calls_made": len(tool_results),
                }}
                # ── 会话结束时自动摘要 ──
                if complete:
                    await self._summarize_on_complete(session_id, output, intent)

        # ── 三层上下文更新 ──
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
            f"[Agent] done session={session_id} len={len(output)} "
            f"input_est={input_tokens} module={module} intent={intent.get('label', '?')}"
        )

        yield {"event": "done", "data": {
            "session_id": session_id, "message_id": 0,
            "tokens_used": len(output),
            "input_tokens_est": input_tokens,
            "intent": intent,
        }}

    # ============================================================
    # 记忆: 检索 + 摘要
    # ============================================================

    async def _retrieve_memory(self, message: str, session_id: str = "") -> str:
        """检索相关历史 + 用户画像。

        仅当用户消息明确表达「继续之前工作」时触发，避免新会话被旧记忆污染。
        """
        if not self.session_memory and not self.user_profile:
            return ""

        # ── 新会话首条消息：只有用户明确表示「继续」时才检索 ──
        if session_id and self.sessions:
            msgs = self.sessions.get_conversation(session_id)
            turn_count = sum(1 for m in msgs if m.get("role") == "user")
            if turn_count <= 1:
                resume_signals = ["继续", "上次", "之前", "恢复", "接着", "接上", "回到", "前面", "刚才"]
                if not any(sig in message for sig in resume_signals):
                    logger.info(f"[Memory] 新会话首条消息，无继续信号，跳过记忆检索")
                    return ""

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

    def _save_planning_contract(self, session_id, contract, *, completed=False):
        """Append a same-session version instead of unrelated version-1 drafts."""
        contract["status"] = "completed" if completed else "draft"
        contract["session_id"] = session_id
        previous = self.contract_store.get_latest(session_id)
        if previous:
            contract["contract_id"] = previous["contract_id"]
            self.contract_store.update(previous["contract_id"], contract, increment_version=True)
        else:
            self.contract_store.create(session_id, contract)

    async def _build_initial_state(self, message, module, background, session_id,
                             extra_context, dimensions, clarify_round, memory_context="", user_id="") -> dict:
        # ── Context Engine: 构建对话上下文 ──
        ctx = await self.context_engine.build(
            session_store=self.sessions,
            session_id=session_id,
            current_message=message,
            intent=None,  # 固定规划入口尚未进入，具体回复模式由 Planner 判断
            expressed_dimensions=dimensions,
        )

        # 把记忆上下文拼到 extra_context 前面
        full_extra = extra_context or ""
        if memory_context:
            full_extra = memory_context + "\n\n" + full_extra

        previous_contract = {}
        if self.contract_store:
            try:
                row = self.contract_store.get_latest(session_id)
                previous_contract = row.get("contract", {}) if row else {}
            except Exception as exc:
                logger.warning("[Contract] 当前会话资料读取失败: %s", exc)

        return {
            "messages": [{"role": "user", "content": message}],
            "module": module,
            "background": background or "",
            "extra_context": full_extra.strip(),
            "expressed_dimensions": dimensions,
            "clarify_round": clarify_round,
            "rag_context": "",
            "multi_agent_perspectives": {},
            "multi_agent_synthesis": "",
            "research_skipped": False,
            "research_completed": False,
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
            # ── 用户上下文（用量记录用）──
            "user_id": user_id,
            "session_id": session_id,
            "previous_contract": previous_contract,
            "delivery_error": False,
            "delivery_validated": False,
        }

    def list_sessions(self, module=None):
        return self.sessions.list_sessions(module=module)

    async def delete_session(self, session_id):
        """删除会话及其关联的记忆缓存。"""
        self.sessions.delete_session(session_id)
        if self.context_engine:
            await self.context_engine.cleanup_session(session_id)

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
