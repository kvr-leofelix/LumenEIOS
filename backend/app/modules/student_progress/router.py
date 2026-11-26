"""HTTP API for Unified Student Progress (read-only)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import require_bearer_token, require_roles
from backend.app.db.session import get_db
from backend.app.models.entities import User
from backend.app.modules.student_progress import access, service
from backend.app.modules.student_progress.schemas import (
    AssessmentHistoryOut,
    CompetencyHistoryOut,
    StudentProgressOverviewOut,
    SubjectCompetencyProfileOut,
    SubjectProgressOut,
)

router = APIRouter(tags=["Unified Student Progress"], dependencies=[Depends(require_bearer_token)])


@router.get("/students/me/progress", response_model=StudentProgressOverviewOut)
async def my_progress(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("student", authenticated=True)),
):
    try:
        student = await access.require_own_student(db, current_user)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    return await service.build_overview(db, student, audience="student_or_parent")


@router.get("/students/me/progress/history", response_model=AssessmentHistoryOut)
async def my_progress_history(
    subject_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("student", authenticated=True)),
):
    try:
        student = await access.require_own_student(db, current_user)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    return await service.build_history(db, student, "student_or_parent", subject_id=subject_id)


@router.get("/students/me/progress/competencies", response_model=CompetencyHistoryOut)
async def my_competency_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("student", authenticated=True)),
):
    try:
        student = await access.require_own_student(db, current_user)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    return await service.build_competency_history(db, student, audience="student_or_parent")


@router.get(
    "/students/me/progress/subjects/{subject_id}",
    response_model=SubjectProgressOut,
)
async def my_subject_progress(
    subject_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("student", authenticated=True)),
):
    try:
        student = await access.require_own_student(db, current_user)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    return await service.build_subject_progress(db, student, "student_or_parent", subject_id)


@router.get(
    "/students/me/progress/subjects/{subject_id}/competencies",
    response_model=SubjectCompetencyProfileOut,
)
async def my_subject_competencies(
    subject_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("student", authenticated=True)),
):
    try:
        student = await access.require_own_student(db, current_user)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    from backend.app.modules.student_progress import subject_competency

    return await subject_competency.build_subject_competency(
        db, student, subject_id, "student_or_parent"
    )


@router.get("/students/me/progress/subjects/{subject_id}/timeline")
async def my_subject_timeline(
    subject_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("student", authenticated=True)),
):
    # Must be declared before /students/{student_id}/.../timeline so "me" is not captured.
    try:
        student = await access.require_own_student(db, current_user)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    from backend.app.modules.student_progress import timeline as timeline_mod

    return await timeline_mod.build_subject_timeline(
        db, student, subject_id, "student_or_parent"
    )


@router.get("/students/me/progress/subjects/{subject_id}/explanations")
async def my_subject_explanations(
    subject_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("student", authenticated=True)),
):
    try:
        student = await access.require_own_student(db, current_user)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    from backend.app.modules.student_progress import explanations as explanations_mod

    return await explanations_mod.build_progress_explanations(
        db, student, subject_id, "student_or_parent"
    )


@router.get(
    "/parents/me/students/{student_id}/progress",
    response_model=StudentProgressOverviewOut,
)
async def parent_child_progress(
    student_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("parent", authenticated=True)),
):
    try:
        student = await access.require_parent_child(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    return await service.build_overview(db, student, audience="student_or_parent")


@router.get(
    "/parents/me/students/{student_id}/progress/history",
    response_model=AssessmentHistoryOut,
)
async def parent_child_history(
    student_id: str,
    subject_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("parent", authenticated=True)),
):
    try:
        student = await access.require_parent_child(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    return await service.build_history(db, student, "student_or_parent", subject_id=subject_id)


@router.get(
    "/parents/me/students/{student_id}/progress/competencies",
    response_model=CompetencyHistoryOut,
)
async def parent_child_competencies(
    student_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("parent", authenticated=True)),
):
    try:
        student = await access.require_parent_child(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    return await service.build_competency_history(db, student, audience="student_or_parent")


@router.get(
    "/parents/me/students/{student_id}/progress/subjects/{subject_id}",
    response_model=SubjectProgressOut,
)
async def parent_child_subject_progress(
    student_id: str,
    subject_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("parent", authenticated=True)),
):
    try:
        student = await access.require_parent_child(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    return await service.build_subject_progress(db, student, "student_or_parent", subject_id)


@router.get(
    "/parents/me/students/{student_id}/progress/subjects/{subject_id}/competencies",
    response_model=SubjectCompetencyProfileOut,
)
async def parent_child_subject_competencies(
    student_id: str,
    subject_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("parent", authenticated=True)),
):
    try:
        student = await access.require_parent_child(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    from backend.app.modules.student_progress import subject_competency

    return await subject_competency.build_subject_competency(
        db, student, subject_id, "student_or_parent"
    )


@router.get("/students/{student_id}/progress", response_model=StudentProgressOverviewOut)
async def teacher_student_progress(
    student_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
):
    try:
        student = await access.require_educator_student(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    return await service.build_overview(db, student, audience="educator")


@router.get(
    "/students/{student_id}/progress/subjects/{subject_id}",
    response_model=SubjectProgressOut,
)
async def teacher_subject_progress(
    student_id: str,
    subject_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
):
    try:
        student = await access.require_educator_student(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    return await service.build_subject_progress(db, student, "educator", subject_id)


@router.get("/students/{student_id}/progress/history", response_model=AssessmentHistoryOut)
async def teacher_assessment_history(
    student_id: str,
    subject_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
):
    try:
        student = await access.require_educator_student(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    return await service.build_history(db, student, "educator", subject_id=subject_id)


@router.get("/students/{student_id}/progress/competencies", response_model=CompetencyHistoryOut)
async def teacher_competency_history(
    student_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
):
    try:
        student = await access.require_educator_student(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    return await service.build_competency_history(db, student, audience="educator")


@router.get(
    "/students/{student_id}/progress/subjects/{subject_id}/competencies",
    response_model=SubjectCompetencyProfileOut,
)
async def teacher_subject_competencies(
    student_id: str,
    subject_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
):
    try:
        student = await access.require_educator_student(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    from backend.app.modules.student_progress import subject_competency

    return await subject_competency.build_subject_competency(
        db, student, subject_id, "educator"
    )


# --- Longitudinal timeline & explanations (additive; same access rules) ---


@router.get("/students/{student_id}/progress/subjects/{subject_id}/timeline")
async def teacher_subject_timeline(
    student_id: str,
    subject_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
):
    try:
        student = await access.require_educator_student(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    from backend.app.modules.student_progress import timeline as timeline_mod

    return await timeline_mod.build_subject_timeline(db, student, subject_id, "educator")


@router.get("/students/{student_id}/progress/subjects/{subject_id}/timeline/{period_kind}/{period_id}")
async def teacher_period_evidence(
    student_id: str,
    subject_id: str,
    period_kind: str,
    period_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
):
    if period_kind not in {"month", "term"}:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="period_kind must be 'month' or 'term'")
    try:
        student = await access.require_educator_student(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    from backend.app.modules.student_progress import timeline as timeline_mod

    return await timeline_mod.build_period_evidence(
        db,
        student,
        subject_id,
        "educator",
        period_kind=period_kind,  # type: ignore[arg-type]
        period_id=period_id,
    )


@router.get("/students/{student_id}/progress/subjects/{subject_id}/explanations")
async def teacher_subject_explanations(
    student_id: str,
    subject_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
):
    try:
        student = await access.require_educator_student(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    from backend.app.modules.student_progress import explanations as explanations_mod

    return await explanations_mod.build_progress_explanations(
        db, student, subject_id, "educator"
    )


@router.get("/parents/me/students/{student_id}/progress/subjects/{subject_id}/timeline")
async def parent_subject_timeline(
    student_id: str,
    subject_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("parent", authenticated=True)),
):
    try:
        student = await access.require_parent_child(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    from backend.app.modules.student_progress import timeline as timeline_mod

    return await timeline_mod.build_subject_timeline(
        db, student, subject_id, "student_or_parent"
    )


@router.get("/parents/me/students/{student_id}/progress/subjects/{subject_id}/explanations")
async def parent_subject_explanations(
    student_id: str,
    subject_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("parent", authenticated=True)),
):
    try:
        student = await access.require_parent_child(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    from backend.app.modules.student_progress import explanations as explanations_mod

    return await explanations_mod.build_progress_explanations(
        db, student, subject_id, "student_or_parent"
    )
