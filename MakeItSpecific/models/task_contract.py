"""
TaskContract — 任务契约 Pydantic 模型。

把用户模糊的想法整理成结构化契约，作为全链路唯一真相源 (Single Source of Truth)。
Planner → Clarify → Execute → Checkpoint → Reflector 全部基于契约工作。

字段对应 阿福产品规划 中的 7 个契约维度。
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


# ============================================================
# 子模型
# ============================================================

class Scope(BaseModel):
    """工作范围：要做什么 + 不要做什么。out 比 in 更重要。"""
    in_: list[str] = Field(
        default_factory=list,
        alias="in",
        description="要做什么"
    )
    out: list[str] = Field(
        default_factory=list,
        description="不要做什么 — 防 Agent 跑偏的关键边界"
    )

    model_config = {"populate_by_name": True}


class Permissions(BaseModel):
    """Agent 执行权限 — 允许读什么、写什么、执行什么。

    默认策略: 读全项目，写需确认，执行需确认。
    初期版本简化，写权限默认是 'ask'。
    """
    read: str | list[str] = Field(
        default="project",
        description='"project" | "all" | ["src/**", ...]'
    )
    write: str | list[str] = Field(
        default="ask",
        description='"ask" | "none" | ["src/components/*", ...]'
    )
    execute: str | list[str] = Field(
        default="ask",
        description='"ask" | "none" | ["npm test", ...]'
    )
    api: list[str] = Field(default_factory=list, description="允许调用的外部 API 列表")
    shell: list[str] = Field(default_factory=list, description="允许的 shell 命令模式")


# ============================================================
# 主模型
# ============================================================

class TaskContract(BaseModel):
    """任务契约 — AI Agent 执行前的轻量工作约定。

    不是完整需求文档，而是经过用户确认的可执行任务说明书。
    典型长度: 200-400 字，够准确但不冗长。
    """

    # ── 标识 ──
    contract_id: str = Field(
        default_factory=lambda: f"tc_{uuid.uuid4().hex[:12]}",
        description="契约唯一 ID"
    )
    session_id: str = Field(default="", description="关联会话 ID")
    version: int = Field(default=1, ge=1, description="契约版本号，增量更新时递增")

    # ── 7 个核心字段 ──
    goal: str = Field(
        default="",
        description="最终目标 — 一句话，用户真正要完成什么（不超过 50 字）"
    )
    scope: Scope = Field(default_factory=Scope, description="工作范围")
    constraints: list[str] = Field(
        default_factory=list,
        description="硬约束 — 不能突破的技术/业务/时间限制"
    )
    acceptance: list[str] = Field(
        default_factory=list,
        description="验收标准 — 可验证的完成条件"
    )
    risks: list[str] = Field(
        default_factory=list,
        description="风险边界 — 触及时必须暂停并询问用户"
    )
    permissions: Permissions = Field(
        default_factory=Permissions,
        description="Agent 执行权限"
    )
    deliverables: dict = Field(
        default_factory=lambda: {"format": "代码改动", "artifacts": []},
        description="期望交付物 — 格式 + 产物列表"
    )

    # ── 元信息 ──
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Planner 对契约完整度的评分 (0-1)。< 0.75 触发 Clarify"
    )
    status: str = Field(
        default="draft",
        description="draft | confirmed | executing | completed | archived"
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="信息不足的字段名列表，用于驱动 Clarify 追问"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="创建时间"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="最后更新时间"
    )
    confirmed_by_user: bool = Field(
        default=False,
        description="是否已经用户确认"
    )

    model_config = {"populate_by_name": True}

    # ============================================================
    # 工具方法
    # ============================================================

    def is_ready(self, threshold: float = 0.75) -> bool:
        """判断契约是否足够完整，可以进入执行阶段。"""
        return self.confidence >= threshold

    def touch(self):
        """更新 updated_at 时间戳。"""
        self.updated_at = datetime.now(timezone.utc)

    def increment_version(self):
        """增量更新时版本号 +1。"""
        self.version += 1
        self.touch()

    def missing_required_fields(self) -> list[str]:
        """返回必填但为空的字段列表。"""
        required = []
        if not self.goal:
            required.append("goal")
        if not self.scope.in_:
            required.append("scope.in")
        return required

    @classmethod
    def from_planner_json(cls, data: dict, session_id: str = "") -> "TaskContract":
        """从 Planner LLM 输出的 JSON 构建契约。兼容旧格式和新格式。"""
        contract_data = data.get("contract", {})
        if not contract_data:
            # 兼容旧版 Planner JSON（没有 contract 嵌套字段）
            contract_data = _migrate_legacy_plan(data)

        scope_data = contract_data.get("scope", {})
        perms_data = contract_data.get("permissions", {})

        return cls(
            contract_id=f"tc_{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            version=contract_data.get("version", 1),
            goal=contract_data.get("goal", data.get("goal", "")),
            scope=Scope(
                in_=scope_data.get("in", scope_data.get("in_", [])),
                out=scope_data.get("out", []),
            ),
            constraints=contract_data.get("constraints", []),
            acceptance=contract_data.get("acceptance", []),
            risks=contract_data.get("risks", []),
            permissions=Permissions(**perms_data) if perms_data else Permissions(),
            deliverables=contract_data.get("deliverables", {"format": "代码改动", "artifacts": []}),
            confidence=contract_data.get("confidence", data.get("completeness", 0.0)),
            missing_fields=data.get("missing_fields", data.get("missing_info", [])),
            confirmed_by_user=contract_data.get("confirmed_by_user", False),
        )

    def to_legacy_dimensions(self) -> dict:
        """将契约映射回旧的 expressed_dimensions 格式（向后兼容）。

        现有系统（Execute/Checkpoint）通过 expressed_dimensions 接收上下文，
        在完全迁移前，这个方法保证旧节点不报错。
        """
        dims = {}
        if self.goal:
            dims["purpose"] = self.goal
            dims["purpose_confidence"] = self.confidence
        if self.scope.in_:
            dims["scope"] = ", ".join(self.scope.in_)
            dims["scope_confidence"] = self.confidence
        if self.constraints:
            dims["constraints"] = "; ".join(self.constraints)
            dims["constraints_confidence"] = self.confidence
        if self.deliverables.get("artifacts"):
            dims["deliverables"] = ", ".join(self.deliverables["artifacts"])
            dims["deliverables_confidence"] = self.confidence
        return dims


# ============================================================
# 内部辅助
# ============================================================

def _migrate_legacy_plan(plan: dict) -> dict:
    """将旧版 Planner JSON (expressed_dimensions 格式) 迁移到 contract 格式。"""
    dims = plan.get("extracted_dimensions", {})
    return {
        "goal": plan.get("goal", ""),
        "confidence": plan.get("completeness", 0.0),
        "scope": {
            "in": [v.get("value", "") for k, v in dims.items()
                   if isinstance(v, dict) and v.get("value") and k != "constraints"],
            "out": [],
        },
        "constraints": (
            [dims["constraints"]["value"]] if isinstance(dims.get("constraints"), dict)
            and dims["constraints"].get("value") else []
        ),
        "acceptance": [],
        "risks": [],
        "permissions": {},
        "deliverables": {"format": "代码改动", "artifacts": []},
    }
