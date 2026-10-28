"""Deterministic artifact dependencies for one new project in one session."""

from copy import deepcopy
from datetime import datetime, timezone

# Scope and the actual usage flow can be clarified together once the goal is
# known. Acceptance is meaningful only after those two artifacts exist.
ARTIFACTS = {
    "goal": (),
    "scope.in": ("goal",),
    "main_flow": ("goal",),
    "acceptance": ("scope.in", "main_flow"),
}


def workflow_for(contract, blockers=()):
    values = {**contract, "scope.in": contract.get("scope", {}).get("in", [])}
    done = [name for name in ARTIFACTS if values.get(name)]
    missing = [name for name in ARTIFACTS if name not in done]
    ready = [name for name in missing if all(dep in done for dep in ARTIFACTS[name])]
    blocked = {name: [dep for dep in ARTIFACTS[name] if dep not in done]
               for name in missing if name not in ready}
    stage = ("idea" if "goal" in missing else "usage" if any(
        name in missing for name in ("scope.in", "main_flow")) else
        "acceptance" if missing else "resolve_conflicts" if blockers else "ready")
    return {"stage": stage, "completed": done, "ready": ready,
            "blocked": blocked, "blocking_questions": list(blockers)}


def stamp_project_state(contract, previous, message):
    """Record extraction provenance without claiming model inference is proof.

    Even confirmed_requirements is an extraction, not an independent user
    confirmation. Defaults are labelled separately from those extractions.
    """
    contract = deepcopy(contract)
    previous = previous or {}
    now = datetime.now(timezone.utc).isoformat()
    provenance = deepcopy(previous.get("provenance", {}))
    for field in ("goal", "target_users", "scope", "main_flow", "acceptance",
                  "constraints", "confirmed_requirements", "assumptions", "pending_questions"):
        if field not in provenance or contract.get(field) != previous.get(field):
            provenance[field] = {
                "kind": "default" if field == "assumptions" or (
                    field == "target_users" and contract.get(field) == "个人或小规模使用（默认假设）"
                ) else "model_extracted",
                "evidence": "normalization_or_model_extraction",
                "updated_at": now,
                "verified_by_user": False,
            }
    contract["schema_version"] = 1
    contract["provenance"] = provenance
    return contract
