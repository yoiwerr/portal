"""
工程规范顾问 — 按任务节点触发的知识补充能力。

不是固定模块，不在每次回复后机械附加规范清单。
当用户需求触发特定工程场景时，自动检索相关知识卡片，
根据风险等级以建议/确认/阻断三级输出。

架构:
  识别用户当前任务
  → 判断是否触发工程场景
  → 检索相关知识卡片
  → 根据相关性和风险等级筛选
  → 以建议、确认或警告的形式补充回复
"""

import json
import logging
import re
from typing import Optional, Union

logger = logging.getLogger(__name__)

# ============================================================
# 三级输出模式
# ============================================================

OUTPUT_MODE = {
    "suggestion": {
        "level": 1,
        "label": "建议级",
        "description": "只影响开发效率或可维护性，简短补充，不打断任务",
        "action": "inject_context",   # 注入到执行上下文，不打断
    },
    "confirm_before_action": {
        "level": 2,
        "label": "确认级",
        "description": "可能造成返工、泄露或不可逆影响，需要在继续前确认",
        "action": "ask_confirm",      # 暂停并向用户确认
    },
    "block_if_found": {
        "level": 3,
        "label": "阻断级",
        "description": "已发现明显安全或不可逆风险，应暂停操作并说明处理方式",
        "action": "block",            # 硬阻断，不继续执行
    },
}

# ============================================================
# EngineeringAdvisor
# ============================================================

class EngineeringAdvisor:
    """工程规范顾问 — 场景检测 + 知识检索 + 分级输出。

    用法:
        advisor = EngineeringAdvisor(rag_service)
        result = await advisor.check(message, contract, rag_context)

        if result["mode"] == "block":
            # 返回阻断消息，不进入 execute
        elif result["mode"] == "confirm":
            # 返回确认问题，类似 clarify 流程
        else:
            # 注入上下文继续执行
    """

    def __init__(self, rag_service=None):
        self.rag = rag_service

    # ============================================================
    # 核心方法: 场景检测 + 检索 + 分级
    # ============================================================

    async def check(
        self,
        message: str,
        contract: Optional[dict] = None,
        rag_context: str = "",
    ) -> dict:
        """
        检测当前任务是否触发工程场景。

        Args:
            message: 用户当前消息
            contract: 可选的任务契约
            rag_context: 已有的 RAG 上下文（可与工程知识合并）

        Returns:
            {
                "triggered": bool,          # 是否触发了任何工程场景
                "mode": "silent|suggestion|confirm|block",
                "advisories": [             # 匹配到的工程建议列表
                    {
                        "scenario": str,    # 场景名
                        "risk_level": str,  # low|medium|high
                        "output_mode": str, # suggestion|confirm_before_action|block_if_found
                        "level": int,       # 1|2|3
                        "card_id": str,     # 知识卡片 ID
                        "checks": [str],    # 检查项
                        "content": str,     # 建议内容
                    }
                ],
                "block_message": str,       # 阻断消息（仅 block 模式）
                "confirm_questions": [str], # 确认问题（仅 confirm 模式）
                "context_injection": str,   # 上下文注入（suggestion 模式）
            }
        """
        result = {
            "triggered": False,
            "mode": "silent",
            "advisories": [],
            "block_message": "",
            "confirm_questions": [],
            "context_injection": "",
        }

        # ── Step 1: 场景检测 ──
        task_text = self._build_task_text(message, contract)
        triggered_scenarios = self._detect_scenarios(task_text)

        if not triggered_scenarios:
            return result

        # ── Step 2: 内置触发器匹配（RAG 可后期接入）──
        # 当前 knowledge_chunks collection 的 metadata 结构与内置触发器一致，
        # RAG 检索待 chunk_type 索引完善后再接入。
        cards = self._fallback_match(triggered_scenarios, task_text)

        if not cards:
            return result

        # ── Step 3: 按风险等级排序 + 筛选 ──
        advisories = []
        for card in cards:
            metadata = card.get("metadata", {})
            document = card.get("document", "")

            risk = metadata.get("risk_level", "medium")
            output_mode = metadata.get("output_mode", "suggestion")

            # 解析 document 中的 YAML frontmatter 提取 checks 和 suggestion
            parsed = self._parse_card_document(document)

            advisories.append({
                "scenario": metadata.get("scenario", parsed.get("scenario", "")),
                "risk_level": risk,
                "output_mode": output_mode,
                "level": OUTPUT_MODE.get(output_mode, {}).get("level", 1),
                "card_id": card.get("id", ""),
                "checks": metadata.get("checks", parsed.get("checks", [])),
                "content": metadata.get("suggestion", parsed.get("suggestion", document[:500])),
            })

        # 按 level 降序排列（阻断 > 确认 > 建议）
        advisories.sort(key=lambda a: a["level"], reverse=True)

        result["triggered"] = True
        result["advisories"] = advisories

        # ── Step 4: 确定输出模式（取最高等级） ──
        max_level = max(a["level"] for a in advisories)

        if max_level >= 3:
            result["mode"] = "block"
            result["block_message"] = self._format_block_message(advisories)
        elif max_level >= 2:
            result["mode"] = "confirm"
            result["confirm_questions"] = self._format_confirm_questions(advisories)
        else:
            result["mode"] = "suggestion"
            result["context_injection"] = self._format_suggestion_context(advisories)

        return result

    # ============================================================
    # 场景检测
    # ============================================================

    # 内置场景触发器（RAG 不可用时的降级方案）
    BUILTIN_TRIGGERS = {
        "公开提交 Git 仓库": {
            "keywords": ["github", "git", "push", "提交", "开源", "公开", "仓库", "上传代码", "发布到"],
            "risk_level": "high",
            "output_mode": "confirm_before_action",
            "checks": [
                "是否存在密钥或 Token",
                "是否包含个人信息",
                "是否配置 .gitignore",
                "Git 历史是否存在敏感内容",
            ],
            "content": "提交前确认 .env/密钥文件在 .gitignore、没有真实数据被提交。如果曾提交过密钥，需要清理 Git 历史并轮换密钥。",
        },
        "Python 项目依赖管理": {
            "keywords": ["python", "pip", "依赖", "requirements", "venv", "虚拟环境", "pyproject", "uv"],
            "risk_level": "medium",
            "output_mode": "suggestion",
            "checks": [
                "是否使用虚拟环境",
                "依赖是否锁定版本",
                "是否区分生产和开发依赖",
            ],
            "content": "长期维护的 Python 项目建议使用 uv 管理依赖、提交 lock 文件、CI 锁定版本确保可复现。",
        },
        "数据库操作与数据安全": {
            "keywords": ["数据库", "删除", "drop", "delete", "迁移", "migration", "postgres", "mysql", "备份", "生产"],
            "risk_level": "high",
            "output_mode": "confirm_before_action",
            "checks": [
                "执行前是否已备份",
                "DELETE/UPDATE 是否带 WHERE 条件",
                "迁移是否有回滚方案",
                "是否在生产环境直接操作",
            ],
            "content": "数据操作前必须备份。DELETE/UPDATE 先用 SELECT 验证影响范围。迁移脚本必须有回滚方案。不在生产环境直接测试。",
        },
        "API 密钥与凭证管理": {
            "keywords": ["api key", "token", "密钥", "密码", "secret", "凭证", "环境变量", ".env", "硬编码", "api_key"],
            "risk_level": "high",
            "output_mode": "block_if_found",
            "checks": [
                "代码中是否硬编码了密钥",
                "是否通过环境变量读取",
                ".env 是否在 .gitignore",
                "是否有 .env.example 模板",
            ],
            "content": "绝对不在代码中硬编码密钥。使用环境变量。如果已经提交，立即轮换密钥并清理 Git 历史。",
        },
        "部署与发布": {
            "keywords": ["部署", "deploy", "发布", "上线", "生产环境", "production", "docker", "构建"],
            "risk_level": "medium",
            "output_mode": "confirm_before_action",
            "checks": [
                "是否在非主分支上测试过",
                "是否有回滚方案",
                "环境变量/密钥是否配置正确",
                "数据库迁移是否已准备",
            ],
            "content": "部署前确认：在测试环境验证过、有回滚方案、环境变量已配置、数据库迁移已就绪。",
        },
        "文件写入与系统操作": {
            "keywords": ["写文件", "删除文件", "rm", "sudo", "chmod", "覆盖", "删除目录", "格式化"],
            "risk_level": "high",
            "output_mode": "confirm_before_action",
            "checks": [
                "是否确认了目标路径正确",
                "是否有备份或版本控制",
                "操作是否可逆",
            ],
            "content": "文件删除/覆盖操作前确认路径正确、有备份或 git 保护。不可逆操作需要二次确认。",
        },
    }

    def _detect_scenarios(self, task_text: str) -> list[str]:
        """检测任务文本中触发了哪些工程场景。"""
        text_lower = task_text.lower()
        triggered = []

        for scenario, config in self.BUILTIN_TRIGGERS.items():
            keywords = config["keywords"]
            matches = sum(1 for kw in keywords if kw in text_lower)
            if matches >= 1:
                triggered.append(scenario)

        return triggered

    def _build_task_text(self, message: str, contract: Optional[dict]) -> str:
        """合并用户消息和契约信息用于场景检测。"""
        parts = [message]
        if contract:
            goal = contract.get("goal", "")
            if goal:
                parts.append(goal)
            scope_in = contract.get("scope", {}).get("in", contract.get("scope", {}).get("in_", []))
            if scope_in:
                parts.append(" ".join(scope_in))
            constraints = contract.get("constraints", [])
            if constraints:
                parts.append(" ".join(constraints))
        return " ".join(parts)

    # ============================================================
    # 降级匹配（RAG 不可用）
    # ============================================================

    def _fallback_match(self, scenarios: list[str], task_text: str) -> list[dict]:
        """RAG 不可用时，直接用内置触发器匹配。"""
        cards = []
        for scenario in scenarios:
            config = self.BUILTIN_TRIGGERS.get(scenario)
            if config:
                cards.append({
                    "id": f"builtin:{scenario}",
                    "document": config.get("content", ""),
                    "metadata": {
                        "scenario": scenario,
                        "risk_level": config.get("risk_level", "medium"),
                        "output_mode": config.get("output_mode", "suggestion"),
                        "checks": config.get("checks", []),
                        "suggestion": config.get("content", ""),
                    },
                    "score": 0.9,  # 内置匹配视为高分
                })
        return cards

    # ============================================================
    # 卡片文档解析 (YAML frontmatter)
    # ============================================================

    def _parse_card_document(self, document: str) -> dict:
        """从 Markdown 文档中解析 YAML frontmatter。"""
        result = {}
        if not document:
            return result

        doc = document.strip()
        if not doc.startswith("---"):
            return result

        parts = doc.split("---", 2)
        if len(parts) < 3:
            return result

        frontmatter = parts[1].strip()
        try:
            # 简单 YAML 解析（不用 pyyaml 依赖）
            for line in frontmatter.split("\n"):
                line = line.strip()
                if ":" not in line:
                    continue
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()

                if value.startswith("[") and value.endswith("]"):
                    # 列表
                    items = [v.strip().strip("\"'") for v in value[1:-1].split("\n")]
                    result[key] = [i.lstrip("- ") for i in items if i.strip()]
                elif value.startswith("|"):
                    # 多行文本（后续行由缩进标识）
                    result[key] = ""
                else:
                    result[key] = value.strip("\"'")

            # 提取 suggestion（frontmatter 后面的 markdown body 的 first paragraph）
            body = parts[2].strip()
            if body:
                # 取第一段非标题文本
                for para in body.split("\n\n"):
                    para = para.strip()
                    if para and not para.startswith("#"):
                        result["body"] = para[:500]
                        break
        except Exception:
            pass

        return result

    # ============================================================
    # 输出格式化
    # ============================================================

    def _format_suggestion_context(self, advisories: list[dict]) -> str:
        """建议级：注入到执行上下文的简短提示。"""
        if not advisories:
            return ""

        lines = []
        for a in advisories[:2]:  # 最多 2 条建议
            lines.append(f"> 💡 **{a['scenario']}**: {a['content'][:200]}")

        return "\n".join(lines)

    def _format_confirm_questions(self, advisories: list[dict]) -> list[str]:
        """确认级：生成需要用户确认的问题。"""
        questions = []
        for a in advisories:
            checks = a.get("checks", [])
            if checks:
                question = f"关于「{a['scenario']}」——"
                if len(checks) <= 2:
                    question += " 已确认 " + "、".join(checks) + "？"
                else:
                    question += f" 已确认 {checks[0]} 和 {checks[1]} 等 {len(checks)} 项？"
                questions.append(question)
            else:
                questions.append(f"开始前确认：{a['content'][:120]}")
        return questions[:3]  # 最多 3 个问题

    def _format_block_message(self, advisories: list[dict]) -> str:
        """阻断级：生成暂停消息。"""
        lines = ["## ⛔ 发现安全/工程风险，已暂停执行", ""]
        for a in advisories:
            if a["level"] >= 3:
                lines.append(f"### 🚫 {a['scenario']}")
                lines.append("")
                lines.append(a["content"][:300])
                lines.append("")
                checks = a.get("checks", [])
                if checks:
                    lines.append("**处理步骤：**")
                    for i, c in enumerate(checks, 1):
                        lines.append(f"{i}. {c}")
                    lines.append("")
        lines.append("请先处理上述问题后再继续。")
        return "\n".join(lines)
