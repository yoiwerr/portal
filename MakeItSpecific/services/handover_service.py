"""
项目交接卡生成服务。

每次会话/任务结束时，LLM 根据对话记录 + 任务契约生成结构化交接卡。
支持双格式输出: JSON (机器可读, 用于恢复) + Markdown (人类可读, 用于下载)。

交接卡的 8 个字段:
  1. 当前目标       — 本次任务最终目标
  2. 已完成事项     — 已交付的产物和完成的工作
  3. 已确认决策     — 技术上/业务上的确定选择
  4. 未解决问题     — 阻塞或悬而未决的事项
  5. 下一步行动     — 建议的后续步骤（含优先级）
  6. 关键文件       — 涉及或产出的重要文件
  7. 新发现的用户偏好 — 本次对话中学到的用户习惯
  8. 下次需验证的信息 — 下次会话需要当场确认的事项
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from services.session_store import SessionStore

logger = logging.getLogger(__name__)

# ============================================================
# Handover card JSON schema (told to LLM)
# ============================================================

HANDOVER_SYSTEM_PROMPT = """你是 阿福，一个 AI 协作管家。请根据当前对话记录生成一份"项目交接卡"。

交接卡的作用：让下一次打开这个项目时，任何 AI 或人都能在 30 秒内了解当前状态、快速恢复工作。

## 输出格式 — 必须是合法 JSON

{
  "meta": {
    "session_id": "会话ID",
    "generated_at": "ISO8601 时间",
    "version": "1.0"
  },
  "current_goal": "一句话 — 本次任务要完成什么",
  "completed": [
    "已完成的具体事项，每项一句话"
  ],
  "decisions": [
    {"what": "决策内容", "why": "原因（可选）"}
  ],
  "open_issues": [
    {"issue": "未解决的问题", "blocker": true/false}
  ],
  "next_steps": [
    {"step": "建议的下一步", "priority": "high|medium|low"}
  ],
  "key_files": [
    {"path": "文件路径", "note": "说明"}
  ],
  "user_preferences": [
    "本次新发现的用户偏好或工作习惯"
  ],
  "verify_next_time": [
    "下次会话开始时需要向用户确认的事项"
  ]
}

## 规则
- 只写本次对话中明确出现的信息，不要编造
- 已完成事项 = 实际交付的产物，不是"讨论过"
- 已确认决策 = 用户明确说"用XX"或"确定XX"，不是 AI 的建议
- 如果某个字段没有内容，返回空数组 []，不要编造
- key_files 只列本次对话中实际涉及或产出的文件
"""


# ============================================================
# HandoverService
# ============================================================

class HandoverService:
    """项目交接卡生成器。"""

    def __init__(self, model=None):
        """
        Args:
            model: LangChain chat model (用于 LLM 生成交接卡)
        """
        self.model = model

    # ============================================================
    # 核心: LLM 生成
    # ============================================================

    async def generate(
        self,
        session_id: str,
        session_store: SessionStore,
        contract: Optional[dict] = None,
    ) -> dict:
        """
        根据会话对话记录生成交接卡 JSON。

        Args:
            session_id: 会话 ID
            session_store: 会话存储实例
            contract: 可选的任务契约 dict

        Returns:
            交接卡 dict (8 字段 + meta)
        """
        messages = session_store.get_conversation(session_id)
        conversation_text = session_store.get_conversation_text(session_id)
        session = session_store.get_session(session_id)

        if not messages or len(messages) < 2:
            return self._empty_handover(session_id, "对话太短，无法生成交接卡")

        # ── 构建 prompt ──
        contract_text = ""
        if contract and contract.get("goal"):
            contract_text = f"""
## 任务契约
- 目标: {contract.get('goal', '')}
- 要做: {', '.join(contract.get('scope', {}).get('in', contract.get('scope', {}).get('in_', [])))}
- 不做: {', '.join(contract.get('scope', {}).get('out', []))}
- 约束: {'; '.join(contract.get('constraints', []))}
- 验收标准: {'; '.join(contract.get('acceptance', []))}
"""

        handover_prompt = f"""{HANDOVER_SYSTEM_PROMPT}

## 会话信息
- 会话ID: {session_id}
- 模块: {session.get('module', 'auto') if session else 'auto'}
- 消息数: {len(messages)}
{contract_text}
## 对话记录
{conversation_text[:6000]}

请根据上述对话记录，生成 JSON 格式的交接卡。只输出 JSON，不要其他内容。"""

        # ── 尝试 LLM 生成 ──
        if self.model:
            try:
                from langchain_core.messages import SystemMessage, HumanMessage

                structured_model = self.model.bind(
                    response_format={"type": "json_object"}
                )
                response = await structured_model.ainvoke([
                    SystemMessage(content=handover_prompt),
                    HumanMessage(content="请输出 JSON。"),
                ])
                result = self._parse_json(response.content)
                if result and result.get("current_goal"):
                    result.setdefault("meta", {})
                    result["meta"]["session_id"] = session_id
                    result["meta"]["generated_at"] = datetime.now(timezone.utc).isoformat()
                    result["meta"]["version"] = "1.0"
                    logger.info(f"[Handover] LLM 生成成功 session={session_id}")
                    return result
            except Exception as e:
                logger.warning(f"[Handover] LLM 生成失败，降级到规则: {e}")

        # ── 规则降级 ──
        return self._rule_based_handover(session_id, messages, contract)

    # ============================================================
    # 降级: 规则生成
    # ============================================================

    def _rule_based_handover(
        self, session_id: str, messages: list, contract: Optional[dict] = None
    ) -> dict:
        """LLM 不可用时，从对话记录中规则提取。"""
        # 提取用户消息摘要
        user_msgs = [m for m in messages if m.get("role") == "user"]
        assistant_msgs = [m for m in messages if m.get("role") == "assistant"]

        # 目标 — 优先从 contract 取
        goal = ""
        if contract and contract.get("goal"):
            goal = contract["goal"]
        elif user_msgs:
            goal = user_msgs[0].get("content", "")[:100]

        # 已完成事项 — 从 assistant 消息中找交付物
        completed = []
        deliverable_keywords = ["创建", "生成", "完成", "实现", "配置", "安装", "部署", "修复"]

        for m in assistant_msgs:
            content = m.get("content", "")
            for kw in deliverable_keywords:
                if kw in content:
                    # 截取包含关键词的句子
                    for sentence in content.split("。"):
                        if kw in sentence and len(sentence) > 5:
                            completed.append(sentence.strip()[:120])
                            break
                    if len(completed) >= 5:
                        break
            if len(completed) >= 5:
                break

        # 决策 — 从用户消息中找明确选择
        decisions = []
        decision_keywords = ["用", "选", "确定", "决定", "就用", "按"]
        for m in user_msgs:
            content = m.get("content", "")
            for kw in decision_keywords:
                if kw in content:
                    decisions.append({"what": content[:120], "why": ""})
                    break
            if len(decisions) >= 3:
                break

        # 未解决问题 — 空（规则无法判断）
        open_issues = []

        # 下一步 — 从 contract deliverables 推断
        next_steps = []
        if contract and contract.get("deliverables", {}).get("artifacts"):
            for a in contract["deliverables"]["artifacts"]:
                next_steps.append({"step": f"完成 {a}", "priority": "medium"})
        if not next_steps and goal:
            next_steps.append({"step": f"继续完成: {goal}", "priority": "high"})

        return {
            "meta": {
                "session_id": session_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "version": "1.0",
                "method": "rule_based",
            },
            "current_goal": goal,
            "completed": completed[:8] or [],
            "decisions": decisions[:8] or [],
            "open_issues": open_issues,
            "next_steps": next_steps[:8] or [],
            "key_files": [],
            "user_preferences": [],
            "verify_next_time": [],
        }

    def _empty_handover(self, session_id: str, reason: str = "") -> dict:
        return {
            "meta": {
                "session_id": session_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "version": "1.0",
                "note": reason,
            },
            "current_goal": "",
            "completed": [],
            "decisions": [],
            "open_issues": [],
            "next_steps": [],
            "key_files": [],
            "user_preferences": [],
            "verify_next_time": [],
        }

    # ============================================================
    # 格式转换
    # ============================================================

    @staticmethod
    def to_markdown(handover: dict) -> str:
        """将交接卡 JSON 渲染为 Markdown 文本。"""
        meta = handover.get("meta", {})
        lines = [
            "# 🧾 项目交接卡",
            "",
            f"> 会话: `{meta.get('session_id', '?')}`",
            f"> 生成时间: {meta.get('generated_at', '?')[:19]}",
            "",
            "---",
            "",
        ]

        # 1. 当前目标
        goal = handover.get("current_goal", "")
        if goal:
            lines.append("## 🎯 当前目标")
            lines.append("")
            lines.append(goal)
            lines.append("")

        # 2. 已完成事项
        completed = handover.get("completed", [])
        if completed:
            lines.append("## ✅ 已完成事项")
            lines.append("")
            for item in completed:
                lines.append(f"- [x] {item}")
            lines.append("")

        # 3. 已确认决策
        decisions = handover.get("decisions", [])
        if decisions:
            lines.append("## 📌 已确认决策")
            lines.append("")
            for d in decisions:
                what = d.get("what", str(d))
                why = d.get("why", "")
                line = f"- **{what}**"
                if why:
                    line += f" — _{why}_"
                lines.append(line)
            lines.append("")

        # 4. 未解决问题
        issues = handover.get("open_issues", [])
        if issues:
            lines.append("## ⚠️ 未解决问题")
            lines.append("")
            for item in issues:
                iss = item.get("issue", str(item))
                blocker = "🚫 阻塞" if item.get("blocker") else "待处理"
                lines.append(f"- [{blocker}] {iss}")
            lines.append("")

        # 5. 下一步行动
        steps = handover.get("next_steps", [])
        if steps:
            lines.append("## 🚀 下一步行动")
            lines.append("")
            for s in steps:
                step = s.get("step", str(s))
                pri = s.get("priority", "medium")
                icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(pri, "⚪")
                lines.append(f"- {icon} {step}")
            lines.append("")

        # 6. 关键文件
        files = handover.get("key_files", [])
        if files:
            lines.append("## 📁 关键文件")
            lines.append("")
            for f in files:
                path = f.get("path", str(f))
                note = f.get("note", "")
                line = f"- `{path}`"
                if note:
                    line += f" — {note}"
                lines.append(line)
            lines.append("")

        # 7. 新发现的用户偏好
        prefs = handover.get("user_preferences", [])
        if prefs:
            lines.append("## 💡 新发现的用户偏好")
            lines.append("")
            for p in prefs:
                lines.append(f"- {p}")
            lines.append("")

        # 8. 下次需验证
        verify = handover.get("verify_next_time", [])
        if verify:
            lines.append("## 🔄 下次需验证")
            lines.append("")
            for v in verify:
                lines.append(f"- [ ] {v}")
            lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        lines.append("*由阿福 Alfred 自动生成 · 下次导入可恢复工作状态*")

        return "\n".join(lines)

    @staticmethod
    def to_json_str(handover: dict) -> str:
        """交接卡 JSON 序列化。"""
        return json.dumps(handover, ensure_ascii=False, indent=2)

    # ============================================================
    # 导入恢复
    # ============================================================

    @staticmethod
    def parse_from_text(text: str) -> Optional[dict]:
        """
        从文本中解析交接卡。支持 JSON 和 Markdown 两种格式。

        Returns:
            handover dict 或 None
        """
        text = text.strip()

        # 尝试 JSON
        try:
            data = json.loads(text)
            if "current_goal" in data or "meta" in data:
                return data
        except json.JSONDecodeError:
            pass

        # 尝试从文本中提取 JSON 块
        import re
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                if "current_goal" in data or "meta" in data:
                    return data
            except json.JSONDecodeError:
                pass

        # 尝试从 Markdown 中提取字段
        return HandoverService._parse_from_markdown(text)

    @staticmethod
    def _parse_from_markdown(text: str) -> Optional[dict]:
        """从 Markdown 格式的交接卡中提取字段。"""
        import re

        result = {
            "meta": {"version": "1.0", "method": "markdown_parsed"},
            "current_goal": "",
            "completed": [],
            "decisions": [],
            "open_issues": [],
            "next_steps": [],
            "key_files": [],
            "user_preferences": [],
            "verify_next_time": [],
        }

        # Extract sections by ## headers
        sections = {
            "当前目标": "current_goal",
            "已完成事项": "completed",
            "已确认决策": "decisions",
            "未解决问题": "open_issues",
            "下一步行动": "next_steps",
            "关键文件": "key_files",
            "新发现的用户偏好": "user_preferences",
            "下次需验证": "verify_next_time",
        }

        for cn_header, key in sections.items():
            # Match "## header ... content until next ## or end"
            pattern = rf'##\s*[^#]*{cn_header}[^\n]*\n(.*?)(?=\n##\s|\Z)'
            match = re.search(pattern, text, re.DOTALL)
            if not match:
                continue

            section_text = match.group(1).strip()

            if key == "current_goal":
                # First non-empty paragraph
                lines = [l.strip() for l in section_text.split("\n") if l.strip() and not l.strip().startswith(">")]
                if lines:
                    result[key] = lines[0]

            elif key in ("completed", "user_preferences", "verify_next_time"):
                # Extract list items
                items = re.findall(r'[-*]\s*(?:\[x\]\s*)?(.*)', section_text)
                result[key] = [item.strip() for item in items if item.strip()]

            elif key == "decisions":
                items = re.findall(r'[-*]\s*\*\*(.*?)\*\*(.*)', section_text)
                result[key] = [{"what": m[0].strip(), "why": m[1].strip(" —_")} for m in items]

            elif key == "open_issues":
                items = re.findall(r'[-*]\s*(?:\[([^\]]*)\]\s*)?(.*)', section_text)
                result[key] = [
                    {"issue": m[1].strip(), "blocker": "阻塞" in m[0] or "blocker" in m[0].lower()}
                    for m in items if m[1].strip()
                ]

            elif key == "next_steps":
                items = re.findall(r'[-*]\s*(?:🔴|🟡|🟢|⚪)\s*(.*)', section_text)
                result[key] = [{"step": item.strip(), "priority": "medium"} for item in items if item.strip()]

            elif key == "key_files":
                items = re.findall(r'[-*]\s*`([^`]+)`\s*(.*)', section_text)
                result[key] = [{"path": m[0].strip(), "note": m[1].strip(" —")} for m in items]

        if result["current_goal"] or result["completed"]:
            return result
        return None

    @staticmethod
    def to_context_string(handover: dict) -> str:
        """
        将交接卡转为 LLM 上下文注入文本。
        用于新会话开始时，让 Agent 了解之前的工作状态。
        """
        if not handover or not handover.get("current_goal"):
            return ""

        lines = ["## 🧾 上次项目交接卡（恢复工作状态）", ""]

        goal = handover.get("current_goal", "")
        if goal:
            lines.append(f"**上次目标**: {goal}")
            lines.append("")

        completed = handover.get("completed", [])
        if completed:
            lines.append("**已完成**:")
            for c in completed[:5]:
                lines.append(f"  - {c}")
            lines.append("")

        decisions = handover.get("decisions", [])
        if decisions:
            lines.append("**已确认决策**:")
            for d in decisions[:5]:
                what = d.get("what", str(d))
                lines.append(f"  - {what}")
            lines.append("")

        issues = handover.get("open_issues", [])
        if issues:
            lines.append("**未解决问题**:")
            for iss in issues[:5]:
                lines.append(f"  - {iss.get('issue', str(iss))}")
            lines.append("")

        steps = handover.get("next_steps", [])
        if steps:
            lines.append("**建议下一步**:")
            for s in steps[:3]:
                lines.append(f"  - {s.get('step', str(s))}")
            lines.append("")

        verify = handover.get("verify_next_time", [])
        if verify:
            lines.append("**需向用户确认**:")
            for v in verify[:3]:
                lines.append(f"  - [ ] {v}")
            lines.append("")

        lines.append("---")
        lines.append("*以上为上次工作状态。请基于此继续推进，如有不确定处优先向用户确认。*")

        return "\n".join(lines)

    # ============================================================
    # 工具
    # ============================================================

    @staticmethod
    def _parse_json(content: str) -> Optional[dict]:
        import re
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return None
