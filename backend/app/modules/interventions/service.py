"""CRUD, transitions and homework assignment for learning interventions."""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import LearningIntervention, Student, User, utc_now
from backend.app.modules.differentiated_homework.intervention_assign import (
    InterventionHomeworkAssignError,
    assign_intervention_via_dh,
)
from backend.app.modules.interventions import state as state_mod
from backend.app.modules.interventions.schemas import (
    InterventionAssignRequest,
    InterventionEditRequest,
    InterventionOut,
)


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def to_out(row: LearningIntervention) -> InterventionOut:
    return InterventionOut(
        id=row.id,
        school_id=row.school_id,
        student_id=row.student_id,
        subject_id=row.subject_id,
        competency=row.competency,
        finding_kind=row.finding_kind,
        gap_summary=row.gap_summary,
        evidence_refs=list(row.evidence_refs_json or []),
        baseline_score=row.baseline_score,
        baseline_checkpoint=dict(row.baseline_checkpoint_json or {}),
        learning_objective=row.learning_objective or "",
        recommended_activities=list(row.recommended_activities_json or []),
        suggested_duration_days=row.suggested_duration_days,
        practice_recommendation=dict(row.practice_recommendation_json or {}),
        expected_outcome=row.expected_outcome or "",
        reassessment_criteria=row.reassessment_criteria or "",
        ai_provider=row.ai_provider,
        ai_model=row.ai_model,
        ai_generated=bool(row.ai_generated),
        teacher_edited=bool(row.teacher_edited),
        status=row.status,
        created_by_user_id=row.created_by_user_id,
        reviewed_by_user_id=row.reviewed_by_user_id,
        review_notes=row.review_notes,
        assigned_homework_id=row.assigned_homework_id,
        follow_up_evidence_refs=list(row.follow_up_evidence_refs_json or []),
        follow_up_checkpoint=dict(row.follow_up_checkpoint_json or {}),
        outcome_status=row.outcome_status,
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
        reviewed_at=_iso(row.reviewed_at),
        assigned_at=_iso(row.assigned_at),
        completed_at=_iso(row.completed_at),
    )


async def list_for_student(
    db: AsyncSession, student: Student, *, status: Optional[str] = None
) -> List[LearningIntervention]:
    q = select(LearningIntervention).where(
        LearningIntervention.student_id == student.id,
        LearningIntervention.school_id == student.school_id,
    )
    if status:
        q = q.where(LearningIntervention.status == status)
    q = q.order_by(LearningIntervention.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def get_for_student(
    db: AsyncSession, student: Student, intervention_id: str
) -> Optional[LearningIntervention]:
    row = await db.get(LearningIntervention, intervention_id)
    if row is None:
        return None
    if row.student_id != student.id or row.school_id != student.school_id:
        return None
    return row


async def edit_intervention(
    db: AsyncSession,
    row: LearningIntervention,
    teacher: User,
    payload: InterventionEditRequest,
) -> LearningIntervention:
    if row.status not in state_mod.EDITABLE_STATUSES:
        raise state_mod.InterventionStateError(
            f"Cannot edit intervention in status '{row.status}'."
        )
    if payload.learning_objective is not None:
        row.learning_objective = payload.learning_objective.strip()
    if payload.recommended_activities is not None:
        row.recommended_activities_json = [
            a.strip() for a in payload.recommended_activities if a and str(a).strip()
        ]
    if payload.suggested_duration_days is not None:
        row.suggested_duration_days = payload.suggested_duration_days
    if payload.practice_recommendation is not None:
        row.practice_recommendation_json = payload.practice_recommendation
    if payload.expected_outcome is not None:
        row.expected_outcome = payload.expected_outcome.strip()
    if payload.reassessment_criteria is not None:
        row.reassessment_criteria = payload.reassessment_criteria.strip()
    if payload.review_notes is not None:
        row.review_notes = payload.review_notes
    row.teacher_edited = True
    row.updated_at = utc_now()
    if row.status == "draft":
        state_mod.assert_transition(row.status, "pending_review")
        row.status = "pending_review"
    await db.flush()
    await db.refresh(row)
    return row


async def approve(
    db: AsyncSession, row: LearningIntervention, teacher: User, notes: Optional[str] = None
) -> LearningIntervention:
    state_mod.assert_transition(row.status, "approved")
    row.status = "approved"
    row.reviewed_by_user_id = teacher.id
    row.reviewed_at = utc_now()
    if notes is not None:
        row.review_notes = notes
    row.updated_at = utc_now()
    await db.flush()
    await db.refresh(row)
    return row


async def reject(
    db: AsyncSession, row: LearningIntervention, teacher: User, notes: Optional[str] = None
) -> LearningIntervention:
    state_mod.assert_transition(row.status, "rejected")
    row.status = "rejected"
    row.reviewed_by_user_id = teacher.id
    row.reviewed_at = utc_now()
    if notes is not None:
        row.review_notes = notes
    row.updated_at = utc_now()
    await db.flush()
    await db.refresh(row)
    return row


async def cancel(
    db: AsyncSession, row: LearningIntervention, teacher: User, notes: Optional[str] = None
) -> LearningIntervention:
    state_mod.assert_transition(row.status, "cancelled")
    row.status = "cancelled"
    row.reviewed_by_user_id = teacher.id
    row.reviewed_at = utc_now()
    if notes is not None:
        row.review_notes = notes
    row.updated_at = utc_now()
    await db.flush()
    await db.refresh(row)
    return row


async def assign_via_homework(
    db: AsyncSession,
    row: LearningIntervention,
    student: Student,
    teacher: User,
    payload: InterventionAssignRequest,
) -> LearningIntervention:
    """Assign via the full Differentiated Homework workflow (draft → approve → assign).

    Does not create legacy HomeworkRemediation rows. AI bank items are not required;
    selection uses include_ai_generated=False so Gemini is never a prerequisite.
    """
    if row.status not in state_mod.ASSIGNABLE_STATUSES:
        raise state_mod.InterventionStateError(
            f"Only approved interventions can be assigned (current: '{row.status}')."
        )
    state_mod.assert_transition(row.status, "assigned")

    try:
        assignment = await assign_intervention_via_dh(
            db,
            student=student,
            teacher=teacher,
            subject_id=row.subject_id,
            due_date=payload.due_date,
            include_ai_generated=False,
        )
    except InterventionHomeworkAssignError:
        # Preserve status_code (422/404/409/…) for the HTTP layer.
        raise

    row.assigned_homework_id = assignment.id
    row.status = "assigned"
    row.assigned_at = utc_now()
    row.reviewed_by_user_id = row.reviewed_by_user_id or teacher.id
    row.updated_at = utc_now()
    await db.flush()
    await db.refresh(row)
    return row


async def mark_completed(
    db: AsyncSession, row: LearningIntervention, teacher: User
) -> LearningIntervention:
    state_mod.assert_transition(row.status, "completed")
    row.status = "completed"
    row.completed_at = utc_now()
    row.updated_at = utc_now()
    await db.flush()
    await db.refresh(row)
    return row
