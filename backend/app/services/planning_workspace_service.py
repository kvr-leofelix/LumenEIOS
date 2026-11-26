"""Server-side authority checks for the legacy planning-workspace document.

STATUS: every planning responsibility that used to live in this document now lives in relational, teacher-scoped tables
(calendar, requirements/classifications, relationships, coverage, lost periods, plans/versions/proposals/execution/evidence, audit).
What remains writable here is only `datasets` (admin syllabus imports) and `asOf` (the reviewer-set planning date). Every migrated
field is frozen: the document keeps its history readable (for the one-time import and for audit) and rejects any change to it,
for every role, whatever action the client declares. The actions that used to write those fields are refused outright (410).
"""
import json
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

REVIEWERS = {"admin", "principal"}

ACTION_ROLES: Dict[str, set] = {
    "SYLLABUS_IMPORT": {"admin"},
    "PLANNING_DATE": REVIEWERS,
}

# Responsibilities that moved to the relational teacher-plan tables. The workspace endpoint refuses these actions outright (410),
# so no stale client can use them to mutate migrated data; the document keeps its history readable.
MIGRATED_ACTIONS: Dict[str, str] = {
    "CONFIG_SAVE": "PUT /api/v1/plan-calendar",
    "CLASSIFICATION_PROPOSE": "PUT /api/v1/teacher-plans/{teacher}/requirements",
    "CLASSIFICATION_REVIEW": "PUT /api/v1/teacher-plans/{teacher}/requirements",
    "RELATIONSHIP_PROPOSE": "POST /api/v1/teacher-plans/{teacher}/relationships",
    "RELATIONSHIP_REVIEW": "POST /api/v1/teacher-plans/{teacher}/relationships",
    "PLAN_DRAFT": "POST /api/v1/teacher-plans/{teacher}/plans",
    "PLAN_REVIEW": "POST /api/v1/plans/{plan}/review",
    "EXECUTION_RECORD": "POST /api/v1/plans/{plan}/execution",
    "EVIDENCE_RECORD": "POST /api/v1/plans/{plan}/evidence",
    "LOSS_RECORD": "POST /api/v1/teacher-plans/{teacher}/lost-periods",
    "RECOVERY_PROPOSE": "POST /api/v1/plans/{plan}/proposals",
    "RECOVERY_REVIEW": "POST /api/v1/plans/{plan}/proposals/{id}/review",
    "COVERAGE_UPDATE": "PUT /api/v1/teacher-plans/{teacher}/coverage",
}


MAX_STATE_BYTES = 5_000_000



def _same(a: Any, b: Any) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _is_prefix(old: List[Any], new: List[Any]) -> bool:
    return len(new) >= len(old) and all(_same(x, y) for x, y in zip(old, new))


def _by_id(items: List[Dict[str, Any]], key: str = "id") -> Dict[str, Dict[str, Any]]:
    return {str(i.get(key)): i for i in items if isinstance(i, dict)}


def validate_shape(state: Any) -> Optional[str]:
    if not isinstance(state, dict):
        return "Workspace must be an object."
    if state.get("schemaVersion") != 2:
        return "Unsupported workspace schemaVersion."
    for key in ("configHistory", "datasets", "relationships", "plans", "audit"):
        if not isinstance(state.get(key), list):
            return f"Workspace field '{key}' must be a list."
    if not isinstance(state.get("classifications"), dict) or not isinstance(state.get("config"), dict):
        return "Workspace config/classifications are malformed."
    if "coverage" in state and not isinstance(state["coverage"], dict):
        return "Workspace field 'coverage' must be an object."
    as_of = state.get("asOf")
    if as_of is not None:
        try:
            date.fromisoformat(as_of)
        except (TypeError, ValueError):
            return "Workspace field 'asOf' must be a yyyy-mm-dd date or null."
    if len(json.dumps(state)) > MAX_STATE_BYTES:
        return "Workspace exceeds the 5 MB limit."
    return None


from backend.app.services.schedule_validation import _teaching_dates, validate_schedule  # noqa: F401  (kept importable here for compatibility)


def authorize_changes(old: Optional[Dict[str, Any]], new: Dict[str, Any], role: str) -> List[str]:
    """Returns every violation (empty list = allowed)."""
    v: List[str] = []
    old = old or {
        "config": None,
        "configHistory": [],
        "datasets": [],
        "classifications": {},
        "relationships": [],
        "plans": [],
        "coverage": {},
        "audit": [],
    }

    # The planning date ("today" for pace) is a reviewer-level setting, like the academic calendar
    if (old.get("asOf") or None) != (new.get("asOf") or None) and role not in REVIEWERS:
        v.append("Only an Admin or Principal can change the planning date.")

    # Syllabus coverage now lives in teacher_topic_coverage (one record per teacher and topic). The workspace document
    # keeps any legacy values readable for the one-time import but never accepts a change to them, so no second store exists.
    if not _same(old.get("coverage") or {}, new.get("coverage") or {}):
        v.append("Syllabus coverage is stored per teacher (PUT /teacher-plans/{teacher}/coverage); the workspace document no longer accepts coverage changes.")

    # The academic calendar lives in school_plan_calendars (PUT /plan-calendar): versioned, validated, audited. The document keeps
    # its historical configuration readable for the one-time import and accepts no change to it.
    if old["config"] is not None and not _same(old["config"], new["config"]):
        v.append("The academic calendar is stored as versions (PUT /plan-calendar); the workspace document no longer accepts changes to it.")
    if not _same(old["configHistory"], new["configHistory"]):
        v.append("The academic calendar is stored as versions (PUT /plan-calendar); the workspace document no longer accepts changes to it.")

    # Syllabus datasets
    if not _is_prefix(old["datasets"], new["datasets"]):
        v.append("Syllabus datasets cannot be edited or removed once stored.")
    elif len(new["datasets"]) > len(old["datasets"]) and role != "admin":
        v.append("Only an Admin can add syllabus datasets.")

    # Classifications and period requirements now live in teacher_topic_configs (PUT /teacher-plans/{teacher}/requirements).
    # Historical values stay readable and are never deleted, but the document accepts no change to them, so it cannot
    # hold a second, conflicting copy of what the teacher saved.
    if not _same(old["classifications"], new["classifications"]):
        v.append("Classifications and period requirements are stored per teacher (PUT /teacher-plans/{teacher}/requirements); the workspace document no longer accepts changes to them.")

    # Topic relationships now live in teacher_topic_relationships (POST/DELETE /teacher-plans/{teacher}/relationships).
    # Historical values stay readable and are never deleted; the document accepts no change to them.
    if not _same(old["relationships"], new["relationships"]):
        v.append("Topic relationships are stored per teacher (POST /teacher-plans/{teacher}/relationships); the workspace document no longer accepts changes to them.")

    # Plans, schedule versions, proposals, approvals, execution and evidence now live in teacher_plans and its child tables
    # (/api/v1/plans, /api/v1/teacher-plans/{teacher}/plans), one set per teacher. The document keeps its historical plans
    # readable for the one-time import, and accepts no change to them (no addition, edit or removal), so it cannot hold a
    # second, conflicting copy of any plan.
    if not _same(old["plans"], new["plans"]):
        v.append("Plans, schedule versions, proposals and execution are stored per teacher (/api/v1/plans); the workspace document no longer accepts changes to them.")

    # Audit trail
    if not _is_prefix(old["audit"], new["audit"]):
        v.append("The audit trail is append-only.")
    elif len(new["audit"]) == len(old["audit"]):
        v.append("Each change must add an audit entry.")
    return sorted(set(v))


def stamp_audit(old_len: int, new_state: Dict[str, Any], actor: Dict[str, str]) -> None:
    """Replaces client-supplied actor identity on new audit entries with the authenticated user."""
    for entry in new_state["audit"][old_len:]:
        entry["actor"] = dict(actor)
