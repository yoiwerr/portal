"""
Context Engine — 三层对话上下文管理（V3）。

三层架构:
  L1 原始窗口    — 最近 3 轮完整原文，保证当前对话流畅（零成本）
  L2 滚动摘要    — 每轮对话后增量更新，覆盖全部历史但压缩（LLM 调用）
  L3 语义事实    — 从每轮提取原子事实，存入内存字典，按需关键词召回（零额外 LLM 调用）

与旧版的差异:
  旧 (V2):  按轮数阈值切换 — ≤2 无历史 / 3-7 完整 / ≥8 LLM 压缩
  新 (V3):  三层始终同时生效 — L1 始终保留 / L2 始终更新 / L3 始终提取
           L1+L2 直接注入 prompt（预计算），L3 按需检索

用法:
    engine = ContextEngine(model=llm, max_summary_tokens=256)

    # 对话前：构建上下文
    ctx = await engine.build(session_store, session_id, current_message, intent, dimensions)
    # ctx.l1_raw, ctx.l2_summary, ctx.l3_facts, ctx.enriched_query

    # 对话后：更新 L2 摘要 + 提取 L3 事实
    await engine.update_after_turn(messages, session_id, turn_output)
"""

import json
import hashlib
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class ConversationContext:
    """三层对话上下文数据包。"""

    __slots__ = (
        "turn_count",
        "l1_raw",            # L1: 最近 3 轮完整原文 (Markdown)
        "l2_summary",        # L2: 滚动摘要（全部历史的压缩版）
        "l3_facts",          # L3: 从历史中召回的语义事实（按需检索）
        "last_turn_summary", # 上轮规则摘要（兼容旧字段）
        "enriched_query",    # RAG 增强 query
    )

    def __init__(self):
        self.turn_count: int = 0
        self.l1_raw: str = ""
        self.l2_summary: str = ""
        self.l3_facts: str = ""
        self.last_turn_summary: str = ""
        self.enriched_query: str = ""

    def to_dict(self) -> dict:
        return {
            "turn_count": self.turn_count,
            "l1_raw": self.l1_raw,
            "l2_summary": self.l2_summary,
            "l3_facts": self.l3_facts,
            "last_turn_summary": self.last_turn_summary,
            "enriched_query": self.enriched_query,
        }


class ContextEngine:
    """三层上下文引擎。

    L1 (原始窗口): 始终保留最近 3 轮完整原文，零 LLM 调用。
    L2 (滚动摘要): 每轮对话后增量更新。格式：「用户想要...。已确定: ...。上次: ...」
    L3 (语义事实): LLM 精准提取偏好/决策/约束，存入 PGVector 支持跨会话语义召回。

    参数:
        model:             LLM 实例（用于 L2 摘要 + L3 事实提取）
        max_summary_tokens: L2 摘要最大 token 数（默认 256）
        l1_max_turns:       L1 保留的最近轮数（默认 3）
        vector_store:       PGVector 实例（用于 L3 持久化，可选）
        embedding_fn:       embedding 函数（用于 L3 向量检索，可选）
    """

    L1_MAX_TURNS = 3
    DEFAULT_MAX_SUMMARY_TOKENS = 256

    # L3 LLM 提取 prompt
    L3_EXTRACT_PROMPT = """你是信息提取器。从以下对话中提取用户的关键事实。

## 规则
- 只提取用户明确表达的信息，不要推测
- 每条事实必须是陈述句（不是疑问、不是假设）
- 分类: 偏好 / 决策 / 约束 / 技术栈 / 目标 / 其他
- 每条事实用第三人称，一句话说清楚

## 示例
对话: "我喜欢简洁风格。不要Redux。必须一个月完成。决定用Vercel。"

输出 JSON:
{
  "facts": [
    {"text": "用户偏好简洁风格", "category": "偏好", "confidence": 0.9},
    {"text": "用户明确拒绝 Redux", "category": "约束", "confidence": 1.0},
    {"text": "项目截止时间一个月", "category": "约束", "confidence": 1.0},
    {"text": "用户已决定用 Vercel 部署", "category": "决策", "confidence": 1.0}
  ]
}

## 当前对话
{last_turn_text}

只输出 JSON，不要其他内容。"""

    def __init__(
        self,
        model=None,
        max_summary_tokens: int = None,
        vector_store=None,
        embedding_fn=None,
    ):
        self.model = model
        self.max_summary_tokens = max_summary_tokens or self.DEFAULT_MAX_SUMMARY_TOKENS
        self.vector_store = vector_store        # PGVectorStore (可选)
        self.embedding_fn = embedding_fn        # embedding 函数 (可选)

        # ── 运行时状态 ──
        self._running_summary: str = ""         # L2 滚动摘要
        self._fact_store: dict[str, list[str]] = {}      # L3 内存后备 {session_id: [事实列表]}
        self._fact_timestamps: dict[str, list[int]] = {} # L3 事实时间戳

    # ============================================================
    # 主入口 — 对话前
    # ============================================================

    async def build(
        self,
        session_store,
        session_id: str,
        current_message: str,
        intent: dict = None,
        expressed_dimensions: dict = None,
    ) -> ConversationContext:
        """构建当前轮次的完整三层上下文。"""
        ctx = ConversationContext()

        if not session_store or not session_id:
            ctx.enriched_query = _build_enriched_query(
                current_message, intent, expressed_dimensions,
            )
            return ctx

        messages = session_store.get_conversation(session_id)
        ctx.turn_count = _count_turns(messages)

        # ── 主题切换检测: 换话题时重置 L2 摘要 ──
        if self._detect_topic_switch(current_message, ctx.turn_count):
            logger.info(
                f"[ContextEngine] 检测到话题切换 (会话 {session_id}, 轮次 {ctx.turn_count})"
            )
            self._running_summary = ""
            # 清空该会话的内存 L3 事实（旧话题偏好不污染新话题）
            if session_id in self._fact_store:
                self._fact_store[session_id] = []
                self._fact_timestamps[session_id] = []

        # ── L1: 最近 3 轮原文 ──
        ctx.l1_raw = _format_recent_history(messages, max_turns=self.L1_MAX_TURNS)

        # ── L2: 滚动摘要 ──
        ctx.l2_summary = self._running_summary

        # ── L3: 语义事实检索（异步, PGVector + 内存后备）──
        ctx.l3_facts = await self._retrieve_facts(session_id, current_message)

        # ── 上轮规则摘要（兼容旧字段）──
        ctx.last_turn_summary = _extract_last_turn(messages)

        # ── RAG 增强 query (上下文驱动) ──
        ctx.enriched_query = _build_enriched_query(
            current_message, intent, expressed_dimensions,
            ctx.last_turn_summary, ctx.l2_summary, ctx.l3_facts,
        )

        return ctx

    # ============================================================
    # 对话后 — 更新 L2 + 提取 L3
    # ============================================================

    async def update_after_turn(
        self,
        messages: list,
        session_id: str,
        turn_output: str = "",
    ):
        """每轮对话结束后调用：更新 L2 滚动摘要 + 提取 L3 原子事实。"""
        turn_count = _count_turns(messages)
        if turn_count <= 1:
            return  # 第一轮不需要摘要

        # ── L2: 增量更新滚动摘要 ──
        await self._update_summary(messages, turn_count, turn_output)

        # ── L3: 提取并存储原子事实 ──
        await self._extract_and_store_facts(messages, session_id, turn_count)

    # ============================================================
    # L2: 滚动摘要（增量更新）
    # ============================================================

    async def _update_summary(self, messages: list, turn_count: int, turn_output: str):
        """增量更新 L2 滚动摘要。

        不重建全部历史，而是「旧摘要 + 本轮新内容 → 新摘要」。
        """
        if not self.model:
            return

        new_turns_text = _format_recent_turns_for_summary(messages, last_n=1, turn_output=turn_output)
        if not new_turns_text.strip():
            return

        old_summary = self._running_summary or "（这是对话的开始）"
        max_chars = self.max_summary_tokens * 3  # 粗略: 1 token ≈ 3 字符（中文约 1.5）

        prompt = (
            f"你是一个对话摘要助手。请将以下本轮对话合并到已有摘要中，生成新的滚动摘要。\n\n"
            f"## 已有摘要\n"
            f"{old_summary}\n\n"
            f"## 本轮对话内容\n"
            f"{new_turns_text}\n\n"
            f"## 要求\n"
            f"- 严格控制在 {max_chars} 字符以内\n"
            f"- 保留：用户的核心需求、已做出的决策、关键约束条件、重要偏好\n"
            f"- 丢弃：追问的来回细节、问候语、过渡语句、工具调用的中间结果\n"
            f"- 使用第三人称：'用户想要...。已确定: ...。上次: ...'\n"
            f"- 如果本轮没有新信息，保持已有摘要不变\n\n"
            f"## 新的滚动摘要（直接输出，不要任何前缀或后缀）"
        )

        try:
            from langchain_core.messages import SystemMessage, HumanMessage

            response = await self.model.ainvoke([
                SystemMessage(content="你是对话摘要助手。输出简洁的摘要，不编造信息。"),
                HumanMessage(content=prompt),
            ])
            summary = response.content.strip()
            if len(summary) > max_chars * 2:
                summary = summary[:max_chars] + "..."

            self._running_summary = summary
            self._last_summary_turn = turn_count

            logger.info(
                f"[ContextEngine] L2 摘要更新: {turn_count} 轮, "
                f"{len(summary)} 字符"
            )
        except Exception as e:
            logger.warning(f"[ContextEngine] L2 摘要更新失败 (非关键): {e}")

    # ============================================================
    # 主题切换检测
    # ============================================================

    def _detect_topic_switch(self, current_message: str, turn_count: int) -> bool:
        """检测用户是否切换了话题，需要重置 L2 摘要。

        两级检测:
          L1 快检: keyword 重叠率 — 当前消息 vs L2 摘要 + L1 最近对话
          L2 精检: LLM 轻量判断 — 仅在 L1 不确定时启用

        触发条件:
          - 第 1 轮不检测（没有历史可对比）
          - L2 摘要为空时不检测（没有旧话题可对比）
          - keyword 重叠为 0 → 直接判定切换
          - keyword 重叠率 < 20% → LLM 精检
          - keyword 重叠率 ≥ 20% → 同一话题，不切换
        """
        if turn_count <= 1:
            return False

        # 早期对话（≤4 轮）仍在澄清需求，不检测话题切换
        # — keyword 不重叠大概率是因为细节还没说全，不是真的换话题
        if turn_count <= 4:
            return False

        if not self._running_summary:
            return False

        # ── L1 快检: keyword 重叠率 ──
        msg_keywords = set(_extract_query_keywords(current_message))
        if not msg_keywords:
            return False

        # 从 L2 摘要中提取关键词
        summary_keywords = set(_extract_query_keywords(self._running_summary))
        all_old_keywords = summary_keywords

        # 也从 L3 事实中提取（如果有内存后备数据）
        for sid, facts in self._fact_store.items():
            for fact in facts[-20:]:  # 最多取最近 20 条
                all_old_keywords |= set(_extract_query_keywords(fact))

        if not all_old_keywords:
            return False

        overlap = msg_keywords & all_old_keywords
        overlap_ratio = len(overlap) / len(msg_keywords) if msg_keywords else 0

        # 零重叠 → 肯定是换话题了
        if len(overlap) == 0:
            logger.info(
                f"[ContextEngine] 话题切换: keyword 零重叠 "
                f"(msg={msg_keywords}, old_topic={list(all_old_keywords)[:10]})"
            )
            return True

        # 高重叠 → 肯定没换
        if overlap_ratio >= 0.3:
            return False

        # 中间地带 (0 < overlap_ratio < 0.3) → 暂时保守处理，不重置
        # 未来可加 LLM 精检:
        #   prompt = f"旧话题关键词: {old_kw}\n新消息: {msg}\n是否换了话题？回答 yes/no"
        #   result = await self.model.ainvoke(...)
        return False

    # ============================================================
    # L3: 语义事实 — LLM 提取 + PGVector 持久化
    # ============================================================

    async def _extract_and_store_facts(self, messages: list, session_id: str, turn_count: int):
        """从本轮对话提取原子事实，存入 PGVector（主）+ 内存字典（后备）。

        主路径: LLM 结构化提取 → embedding → PGVector session_memory 表
        后备:   规则正则提取 → 内存字典（LLM 不可用时自动降级）
        """
        last_pair = _get_last_pair_text(messages)
        if not last_pair:
            return

        facts = []

        # ── 主路径: LLM 提取 ──
        if self.model:
            try:
                facts = await self._extract_facts_llm(last_pair)
                logger.info(
                    f"[ContextEngine] L3 LLM 提取 {len(facts)} 条事实 "
                    f"(会话 {session_id}, 轮次 {turn_count})"
                )
            except Exception as e:
                logger.warning(f"[ContextEngine] L3 LLM 提取失败，降级规则提取: {e}")
                facts = _extract_atomic_facts(last_pair)
        else:
            facts = _extract_atomic_facts(last_pair)

        if not facts:
            return

        # ── 持久化到 PGVector（优先）──
        if self.vector_store and self.embedding_fn:
            try:
                await self._persist_facts_to_pg(session_id, turn_count, facts)
            except Exception as e:
                logger.warning(f"[ContextEngine] L3 PGVector 写入失败，降级内存: {e}")
                self._store_facts_memory(session_id, turn_count, facts)
        else:
            # 后备: 内存字典
            self._store_facts_memory(session_id, turn_count, facts)

        logger.info(
            f"[ContextEngine] L3 累计事实: 会话 {session_id} → "
            f"{len(self._fact_store.get(session_id, []))} 条 (内存后备)"
        )

    async def _extract_facts_llm(self, text: str) -> list[str]:
        """LLM 结构化提取原子事实。"""
        from langchain_core.messages import SystemMessage, HumanMessage

        prompt = self.L3_EXTRACT_PROMPT.format(last_turn_text=text[:1500])

        try:
            structured_model = self.model.bind(response_format={"type": "json_object"})
        except Exception:
            structured_model = self.model

        response = await structured_model.ainvoke([
            SystemMessage(content="你是信息提取器。只输出 JSON，不要其他内容。"),
            HumanMessage(content=prompt),
        ])

        data = _safe_parse_json(response.content)
        raw_facts = data.get("facts", []) if isinstance(data, dict) else []

        facts = []
        for f in raw_facts:
            text_val = f.get("text", "").strip()
            category = f.get("category", "其他")
            if text_val and len(text_val) >= 3:
                facts.append(f"{text_val} [{category}]")

        return facts[:10]

    async def _persist_facts_to_pg(
        self, session_id: str, turn_count: int, facts: list[str],
    ):
        """将 L3 事实写入 PGVector session_memory 表。"""
        doc_text = "\n".join(facts)
        embedding = self.embedding_fn([doc_text])[0]

        import hashlib
        fact_id = hashlib.md5(f"{session_id}:{turn_count}".encode()).hexdigest()[:16]

        await self.vector_store.add(
            collection="session_memory",
            documents=[doc_text],
            embeddings=[embedding],
            metadatas=[{
                "session_id": session_id,
                "turn_number": turn_count,
                "fact_count": len(facts),
                "type": "l3_facts",
            }],
            ids=[fact_id],
        )

    def _store_facts_memory(self, session_id: str, turn_count: int, facts: list[str]):
        """后备: 存入内存字典。"""
        if session_id not in self._fact_store:
            self._fact_store[session_id] = []
            self._fact_timestamps[session_id] = []

        existing = set(self._fact_store[session_id])
        for fact in facts:
            fact_key = fact.strip().lower()
            if fact_key not in existing:
                self._fact_store[session_id].append(fact.strip())
                self._fact_timestamps[session_id].append(turn_count)
                existing.add(fact_key)

        # 清理超过 50 条的旧事实（TTL 改为数量限制）
        if len(self._fact_store[session_id]) > 50:
            self._fact_store[session_id] = self._fact_store[session_id][-50:]
            self._fact_timestamps[session_id] = self._fact_timestamps[session_id][-50:]

    async def _retrieve_facts(self, session_id: str, query: str) -> str:
        """从 L3 事实库中召回相关事实。

        主路径: PGVector 向量相似度检索（语义匹配，跨会话可用）
        后备:   内存字典关键词匹配（LLM 不可用时）
        """
        # ── 主路径: PGVector 语义检索 ──
        if self.vector_store and self.embedding_fn:
            try:
                query_emb = self.embedding_fn([query])[0]
                results = await self.vector_store.search(
                    collection="session_memory",
                    query_embedding=query_emb,
                    top_k=5,
                    filter_meta={"session_id": session_id, "type": "l3_facts"},
                )
                if results:
                    facts = []
                    for r in results:
                        score = r.get("score", 0)
                        if score >= 0.5:  # 相似度阈值
                            doc = r.get("document", "")
                            facts.append(doc)

                    if facts:
                        lines = ["以下是从此前对话中召回的语义事实：", ""]
                        for f_text in facts:
                            for line in f_text.split("\n"):
                                line = line.strip()
                                if line:
                                    lines.append(f"- {line}")
                        return "\n".join(lines)
            except Exception as e:
                logger.warning(f"[ContextEngine] L3 PGVector 检索失败，降级关键词: {e}")

        # ── 后备: 内存字典关键词匹配 ──
        return self._retrieve_facts_memory(session_id, query)

    def _retrieve_facts_memory(self, session_id: str, query: str) -> str:
        """后备: 从内存字典中关键词召回。"""
        if session_id not in self._fact_store:
            return ""

        facts = self._fact_store.get(session_id, [])
        if not facts:
            return ""

        keywords = _extract_query_keywords(query)
        if not keywords:
            return ""

        scored = []
        for fact in facts:
            score = sum(1 for kw in keywords if kw.lower() in fact.lower())
            if score > 0:
                scored.append((score, fact))

        if not scored:
            return ""

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:5]

        lines = ["以下是从此前对话中召回的语义事实：", ""]
        for score, fact in top:
            lines.append(f"- {fact}")
        return "\n".join(lines)

    # ============================================================
    # 注入
    # ============================================================

    @staticmethod
    def inject_to_prompt(base_prompt: str, ctx: ConversationContext) -> str:
        """将三层上下文按 🔴🟡🟢⚪ 层级注入到 prompt。

        🔴 L2 滚动摘要 — 最高优先级，必须了解
        🟡 L1 最近原文 — 当前对话的准确上下文
        🟢 L3 语义事实 — 从历史召回的补充信息
        ⚪ 原始上下文 — 仅用于理解意图
        """
        parts = [base_prompt]

        if ctx.l2_summary:
            parts.append(
                f"\n\n## 🔴 前情提要（必须了解）\n"
                f"以下是本次对话的滚动摘要，你必须在回答时考虑这些信息：\n"
                f"{ctx.l2_summary}"
            )

        if ctx.last_turn_summary and not ctx.l2_summary:
            # 前几轮还没有 L2 摘要时，用上轮摘要顶替
            parts.append(
                f"\n\n## 🔴 上一轮对话\n"
                f"{ctx.last_turn_summary}"
            )

        if ctx.l1_raw:
            label = "🟡" if ctx.l2_summary else "🟢"
            parts.append(
                f"\n\n## {label} 最近对话\n"
                f"{ctx.l1_raw}"
            )

        if ctx.l3_facts:
            parts.append(
                f"\n\n## 🟢 历史语义事实（从对话中自动提取）\n"
                f"{ctx.l3_facts}"
            )

        return "\n".join(parts)


# ============================================================
# 工具函数
# ============================================================

def _count_turns(messages: list) -> int:
    return sum(1 for m in messages if m.get("role") == "user")


def _extract_last_turn(messages: list) -> str:
    """规则提取上轮摘要：最后一对 user→assistant。"""
    if len(messages) < 2:
        return ""

    last_user = None
    last_assistant = None
    last_assistant_type = ""

    for m in reversed(messages):
        role = m.get("role", "")
        content = str(m.get("content", "")).strip()
        if role == "assistant" and last_assistant is None:
            last_assistant = content
            last_assistant_type = m.get("msg_type", "")
        elif role == "user" and last_user is None:
            last_user = content
        if last_user and last_assistant is not None:
            break

    if not last_user:
        return ""

    parts = [f"👤 用户: {last_user[:200]}"]
    if last_assistant:
        if last_assistant_type == "clarify":
            parts.append("🤖 AI 追问了更多信息")
        else:
            preview = last_assistant[:200].replace("\n", " ")
            parts.append(f"🤖 AI: {preview}")

    return "\n".join(parts)


def _format_recent_history(messages: list, max_turns: int = 3) -> str:
    """L1: 格式化最近 N 轮完整对话历史。"""
    pairs = _messages_to_pairs(messages)
    recent = pairs[-max_turns:] if len(pairs) > max_turns else pairs

    lines = []
    for i, pair in enumerate(recent):
        turn_num = len(pairs) - len(recent) + i + 1
        lines.append(f"### 第 {turn_num} 轮")
        lines.append(f"用户: {pair.get('user', '')[:300]}")
        if pair.get("assistant"):
            assistant_text = pair["assistant"][:300].replace("\n", " ")
            lines.append(f"AI: {assistant_text}")
        lines.append("")

    return "\n".join(lines)


def _format_recent_turns_for_summary(messages: list, last_n: int = 1, turn_output: str = "") -> str:
    """为 L2 增量更新准备的本轮对话文本。"""
    pairs = _messages_to_pairs(messages)
    recent = pairs[-last_n:] if len(pairs) > last_n else pairs

    lines = []
    for pair in recent:
        user = pair.get("user", "")[:300]
        assistant = pair.get("assistant", "")[:300].replace("\n", " ")
        if turn_output:
            assistant = turn_output[:300].replace("\n", " ")
        lines.append(f"用户: {user}")
        if assistant:
            lines.append(f"AI: {assistant}")

    return "\n".join(lines)


def _messages_to_pairs(messages: list) -> list[dict]:
    """消息列表 → user-assistant 配对。"""
    pairs = []
    current_pair = {}

    for m in messages:
        role = m.get("role", "")
        content = str(m.get("content", "")).strip()
        if role == "user":
            if current_pair:
                pairs.append(current_pair)
            current_pair = {"user": content}
        elif role == "assistant":
            if "user" not in current_pair:
                current_pair["user"] = "(系统消息)"
            current_pair["assistant"] = content

    if current_pair:
        pairs.append(current_pair)

    return pairs


def _get_last_pair_text(messages: list) -> str:
    """获取最近一轮 user→assistant 的合并文本（用于 L3 事实提取）。"""
    pairs = _messages_to_pairs(messages)
    if not pairs:
        return ""
    last = pairs[-1]
    return f"用户: {last.get('user', '')}\nAI: {last.get('assistant', '')}"


def _extract_atomic_facts(text: str) -> list[str]:
    """规则提取原子事实 — 从文本中识别用户偏好/决策/约束。

    匹配模式:
    - "我用/我喜欢/我偏好/我习惯/我擅长"
    - "不要/不想/不喜欢/排斥/讨厌"
    - "必须/一定/确定/肯定"
    - "选了/选择/决定/定了/就用"
    - 明确的技术/工具/平台名称
    """
    facts = []

    # 偏好声明
    preference_patterns = [
        r'(?:我[^。！？.!?\n]{0,15}(?:用|喜欢|偏好|习惯|擅长|倾向|推荐))[^。！？.!?\n]{0,30}',
        r'(?:不要|不想|不喜欢|排斥|讨厌|避免)[^。！？.!?\n]{0,40}',
        r'(?:必须|一定|确定|肯定|非得|务必)[^。！？.!?\n]{0,40}',
        r'(?:选了|选择|决定|定了|就用|确定了|敲定了)[^。！？.!?\n]{0,40}',
    ]

    for pattern in preference_patterns:
        matches = re.findall(pattern, text)
        for m in matches:
            cleaned = m.strip().rstrip("，,。.")
            if len(cleaned) >= 4:  # 过滤太短的
                facts.append(cleaned)

    # 技术栈声明
    tech_keywords = [
        "React", "Vue", "Angular", "Svelte", "Next", "Nuxt",
        "TypeScript", "JavaScript", "Python", "Go", "Rust", "Java",
        "Node", "Deno", "Bun", "Django", "Flask", "FastAPI",
        "PostgreSQL", "MySQL", "MongoDB", "Redis", "SQLite",
        "Docker", "Kubernetes", "AWS", "阿里云", "腾讯云",
        "Vercel", "Netlify", "Cloudflare",
        "OpenAI", "Claude", "DeepSeek", "Qwen", "Llama",
        "Tailwind", "shadcn", "Ant Design", "Element",
        "VSCode", "Cursor", "Copilot",
    ]
    text_lower = text.lower()
    for tech in tech_keywords:
        if tech.lower() in text_lower:
            # 找到包含该关键词的完整短句
            idx = text_lower.find(tech.lower())
            start = max(0, idx - 10)
            end = min(len(text), idx + len(tech) + 30)
            snippet = text[start:end].strip().rstrip("，,。.")
            if len(snippet) >= 4:
                facts.append(f"技术栈: {snippet}")

    # 时间/资源约束
    constraint_patterns = [
        r'(?:截止|DDL|deadline|前完成|前交付|前上线)[^。！？.!?\n]{0,30}',
        r'(?:预算|花费|费用)[^。！？.!?\n]{0,30}',
        r'\d+[个天周月年][^。！？.!?\n]{0,20}(?:完成|交付|上线|做完)',
    ]
    for pattern in constraint_patterns:
        matches = re.findall(pattern, text)
        for m in matches:
            cleaned = m.strip().rstrip("，,。.")
            if len(cleaned) >= 4:
                facts.append(f"约束: {cleaned}")

    # 去重 + 限制数量
    seen = set()
    unique = []
    for f in facts:
        key = f.strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(f.strip())

    return unique[:10]


def _safe_parse_json(content: str) -> dict:
    """健壮的 JSON 解析 — 处理 markdown 代码块包裹、模型额外文本等。"""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 代码块
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试提取第一个 { ... } 块
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从 LLM 输出中解析 JSON: {content[:200]}...")


def _extract_query_keywords(query: str) -> list[str]:
    """从 query 中提取核心关键词（用于 L3 检索匹配）。"""
    # 移除标点和停用词
    cleaned = re.sub(r'[，。！？、：；""''（）\s]+', ' ', query)
    words = cleaned.split()

    # 过滤短词和停用词
    stopwords = {
        "我", "你", "他", "她", "它", "们", "的", "了", "是", "在",
        "有", "和", "与", "或", "不", "也", "都", "就", "还", "要",
        "会", "能", "可以", "这个", "那个", "什么", "怎么", "为什么",
        "一个", "一种", "一下", "一些", "一点", "有点",
    }

    keywords = []
    for w in words:
        if len(w) >= 2 and w.lower() not in stopwords:
            keywords.append(w)

    # 保留不超过 10 个关键词（避免噪音）
    return keywords[:10]


def _build_enriched_query(
    message: str,
    intent: dict = None,
    expressed_dimensions: dict = None,
    last_turn_summary: str = "",
    l2_summary: str = "",
    l3_facts: str = "",
) -> str:
    """为 RAG 构建增强 query — 上下文驱动，不生成虚假信息。

    原则:
      1. 长 query (>80 字符): 不加任何上下文，保护原始语义
      2. 中 query (30-80): 只加 L3 相关事实 + 已确认维度
      3. 短 query (<30): 多源信号组合 (L3 + dims + L2)
      4. 只组合用户真实提供的信息，不从虚空中扩写

    信号源 (全部来自用户真实对话历史):
      L3 语义事实         — 用户明确说过的偏好/决策/约束 (权重最高)
      expressed_dimensions — 已确认的结构化需求信息
      L2 滚动摘要         — 长对话的核心脉络
      last_turn_summary   — 上一轮的上下文
    """
    # ── 长 query: 不加任何上下文 ──
    if len(message) >= 80:
        return message[:500]

    # ── 中 query (30-80): 只加高置信度信号 ──
    if len(message) >= 30:
        parts = [message]

        # L3 相关事实
        if l3_facts:
            relevant = _filter_facts_by_query(l3_facts, message)
            if relevant:
                parts.append(relevant)

        # 已确认维度
        if expressed_dimensions:
            dim_parts = []
            for key, val in expressed_dimensions.items():
                if key.endswith("_confidence"):
                    continue
                if val and str(val) != "null" and len(str(val)) > 1:
                    dim_parts.append(str(val))
            if dim_parts:
                parts.append(" ".join(dim_parts)[:100])

        return " ".join(parts)[:500]

    # ── 短 query (<30): 多源信号组合 ──
    # 检测话题切换 — 如果用户突然换话题，不注入旧上下文
    if _is_topic_switch(message, l2_summary, l3_facts):
        return message[:500]

    parts = [message]
    signals_added = 0

    # L3 语义事实 — 用户明确说过的偏好/决策 (权重 0.4)
    if l3_facts and signals_added < 3:
        l3_text = l3_facts.replace(
            "以下是从此前对话中召回的语义事实：\n", ""
        ).replace("- ", "")
        if l3_text.strip():
            parts.append(l3_text[:200])
            signals_added += 1

    # expressed_dimensions — 已确认的需求维度 (权重 0.3)
    if expressed_dimensions and signals_added < 3:
        dim_parts = []
        for key, val in expressed_dimensions.items():
            if key.endswith("_confidence"):
                continue
            if val and str(val) != "null" and len(str(val)) > 1:
                dim_parts.append(str(val))
        if dim_parts:
            parts.append(" ".join(dim_parts)[:150])
            signals_added += 1

    # L2 滚动摘要 — 长对话脉络 (权重 0.2)
    if l2_summary and signals_added < 2:
        parts.append(l2_summary[:150])
        signals_added += 1

    # 上轮摘要 — 即时上下文 (权重 0.1)
    if last_turn_summary and signals_added < 2:
        # 只取用户说了什么
        user_part = last_turn_summary.split("\n")[0] if "\n" in last_turn_summary else last_turn_summary[:100]
        parts.append(user_part[:100])

    enriched = " ".join(parts)[:500]
    return enriched


def _filter_facts_by_query(l3_facts: str, query: str) -> str:
    """只保留和 query 关键词相关的 L3 事实。"""
    keywords = _extract_query_keywords(query)
    if not keywords:
        return ""

    relevant = []
    for line in l3_facts.split("\n"):
        line = line.lstrip("- ").strip()
        if not line:
            continue
        score = sum(1 for kw in keywords if kw.lower() in line.lower())
        if score > 0:
            relevant.append(line)

    return " ".join(relevant[:3]) if relevant else ""


def _is_topic_switch(query: str, l2_summary: str = "", l3_facts: str = "") -> bool:
    """检测话题切换 — 用户突然问了一个和之前对话完全无关的问题。

    简单策略: 如果 L2 摘要和 query 的关键词重叠为 0 → 话题切换。
    """
    if not l2_summary and not l3_facts:
        return False

    query_keywords = set(_extract_query_keywords(query))
    if not query_keywords:
        return False

    context_text = (l2_summary or "") + " " + (l3_facts or "")
    context_keywords = set(_extract_query_keywords(context_text))
    overlap = query_keywords & context_keywords

    return len(overlap) == 0
