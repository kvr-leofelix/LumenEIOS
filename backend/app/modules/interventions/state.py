"""Explicit lifecycle transitions for learning interventions."""
from __future__ import annotations

from typing import Dict, Set

# draft → pending_review → approved → assigned → completed
# plus rejected / cancelled terminal (or cancelled from pre-assign states)
ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    "draft": {"pending_review", "cancelled"},
    "pending_review": {"approved", "rejected", "cancelled", "pending_review"},
    "approved": {"assigned", "rejected", "cancelled"},
    "assigned": {"completed", "cancelled"},
    "completed": set(),
    "rejected": set(),
    "cancelled": set(),
}

ASSIGNABLE_STATUSES = {"approved"}
EDITABLE_STATUSES = {"draft", "pending_review"}


class InterventionStateError(Exception):
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


def assert_transition(current: str, target: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InterventionStateError(
            f"Cannot transition intervention from '{current}' to '{target}'."
        )
