"""Bridge: approved learning interventions → full Differentiated Homework assignment.

Uses the existing DH pipeline (gap analysis → bank selection → draft → approve → assign).
Never creates legacy HomeworkRemediation rows. AI-generated bank items are opt-in and
default OFF so ordinary assignment works without Gemini.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import Student, User
from backend.app.modules.differentiated_homework.draft_service import (
    StaleQuestion,
    apply_review,
    build_assignment,
    build_draft_record,
)
from backend.app.modules.differentiated_homework.models import HomeworkAssignmentRecord
from backend.app.modules.differentiated_homework.question_bank_adapter import load_question_snapshots
from backend.app.modules.differentiated_homework.schemas import HomeworkDraftSaveRequest


class InterventionHomeworkAssignError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _parse_due_at(due_date: str) -> datetime:
    text = (due_date or "").strip()
    if not text:
        raise InterventionHomeworkAssignError(422, "due_date is required.")
    # Accept YYYY-MM-DD or full ISO-8601.
    try:
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            due = datetime(int(text[0:4]), int(text[5:7]), int(text[8:10]), 23, 59, 59, tzinfo=timezone.utc)
        else:
            due = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise InterventionHomeworkAssignError(
            422, "due_date must be YYYY-MM-DD or an ISO-8601 datetime."
        ) from exc
    if due <= datetime.now(timezone.utc):
        raise InterventionHomeworkAssignError(422, "The due date must be in the future.")
    return due


async def assign_intervention_via_dh(
    db: AsyncSession,
    *,
    student: Student,
    teacher: User,
    subject_id: str,
    due_date: str,
    max_questions: int = 3,
    include_ai_generated: bool = False,
) -> HomeworkAssignmentRecord:
    """Create and assign a real DH homework assignment for the student.

    Reuses the same generation path as POST /students/{id}/homework/drafts so question
    selection stays school-scoped and bank-backed. Does not call any AI provider unless
    include_ai_generated=True and AI bank items already exist.
    """
    # Import locally to avoid circular imports with router helpers.
    from backend.app.modules.differentiated_homework import router as hw_router

    body = HomeworkDraftSaveRequest(
        subject_id=subject_id,
        max_questions=max_questions,
        include_ai_generated=include_ai_generated,
        expected_question_ids=None,
    )
    try:
        draft = await hw_router._generate_draft(db, teacher, student.id, body)
    except HTTPException as exc:
        raise InterventionHomeworkAssignError(exc.status_code, str(exc.detail)) from exc

    question_ids = [item.question_id for item in draft.items]
    if not question_ids:
        raise InterventionHomeworkAssignError(
            422,
            "No suitable questions in the central bank for this subject. "
            "Add questions in Differentiated Homework → Question bank, then assign again.",
        )

    snapshots = await load_question_snapshots(db, question_ids, draft.school_id, draft.subject_id)
    try:
        record = build_draft_record(draft, snapshots, body, created_by=teacher.id)
    except StaleQuestion as exc:
        raise InterventionHomeworkAssignError(
            status.HTTP_409_CONFLICT,
            "A selected question changed while saving. Preview again in Differentiated Homework.",
        ) from exc

    # Note on the draft that it originated from an approved intervention (audit trail only).
    notes = list(record.notes_json or [])
    notes.append("Created from an approved learning intervention via the DH assignment workflow.")
    record.notes_json = notes

    db.add(record)
    await db.flush()

    apply_review(record, "approve", teacher.id, "Auto-approved from approved intervention assign.")
    apply_review(record, "assign", teacher.id, None)
    assignment = build_assignment(record, teacher.id, _parse_due_at(due_date))
    db.add(assignment)
    await db.flush()
    await db.refresh(assignment)
    return assignment
