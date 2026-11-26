"""Teacher APIs for AI-assisted learning interventions."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import require_bearer_token, require_roles
from backend.app.db.session import get_db
from backend.app.models.entities import User
from backend.app.modules.differentiated_homework.intervention_assign import (
    InterventionHomeworkAssignError,
)
from backend.app.modules.interventions import generation, service, state
from backend.app.modules.interventions.schemas import (
    GenerateInterventionRequest,
    InterventionAssignRequest,
    InterventionEditRequest,
    InterventionOut,
    InterventionReviewRequest,
)
from backend.app.modules.student_progress import access

router = APIRouter(tags=["Learning Interventions"], dependencies=[Depends(require_bearer_token)])


def _state_http(exc: state.InterventionStateError) -> HTTPException:
    return HTTPException(status_code=409, detail=exc.detail)


def _gen_http(exc: generation.InterventionGenerationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post(
    "/students/{student_id}/interventions/generate",
    response_model=InterventionOut,
    status_code=201,
)
async def generate_intervention(
    student_id: str,
    body: GenerateInterventionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
):
    """Teacher-triggered AI proposal. Lands in pending_review — never assigned."""
    try:
        student = await access.require_educator_student(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    try:
        row = await generation.generate_intervention_proposal(
            db,
            student=student,
            teacher=current_user,
            subject_id=body.subject_id,
            competency=body.competency,
            finding_kind=body.finding_kind,
        )
    except generation.InterventionGenerationError as exc:
        raise _gen_http(exc) from exc
    await db.commit()
    return service.to_out(row)


@router.get("/students/{student_id}/interventions", response_model=List[InterventionOut])
async def list_interventions(
    student_id: str,
    status: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
):
    try:
        student = await access.require_educator_student(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    rows = await service.list_for_student(db, student, status=status)
    return [service.to_out(r) for r in rows]


@router.get(
    "/students/{student_id}/interventions/{intervention_id}",
    response_model=InterventionOut,
)
async def get_intervention(
    student_id: str,
    intervention_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
):
    try:
        student = await access.require_educator_student(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    row = await service.get_for_student(db, student, intervention_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Intervention not found.")
    return service.to_out(row)


@router.patch(
    "/students/{student_id}/interventions/{intervention_id}",
    response_model=InterventionOut,
)
async def edit_intervention(
    student_id: str,
    intervention_id: str,
    body: InterventionEditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
):
    try:
        student = await access.require_educator_student(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    row = await service.get_for_student(db, student, intervention_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Intervention not found.")
    try:
        row = await service.edit_intervention(db, row, current_user, body)
    except state.InterventionStateError as exc:
        raise _state_http(exc) from exc
    await db.commit()
    return service.to_out(row)


@router.post(
    "/students/{student_id}/interventions/{intervention_id}/approve",
    response_model=InterventionOut,
)
async def approve_intervention(
    student_id: str,
    intervention_id: str,
    body: InterventionReviewRequest = InterventionReviewRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
):
    try:
        student = await access.require_educator_student(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    row = await service.get_for_student(db, student, intervention_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Intervention not found.")
    try:
        row = await service.approve(db, row, current_user, body.review_notes)
    except state.InterventionStateError as exc:
        raise _state_http(exc) from exc
    await db.commit()
    return service.to_out(row)


@router.post(
    "/students/{student_id}/interventions/{intervention_id}/reject",
    response_model=InterventionOut,
)
async def reject_intervention(
    student_id: str,
    intervention_id: str,
    body: InterventionReviewRequest = InterventionReviewRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
):
    try:
        student = await access.require_educator_student(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    row = await service.get_for_student(db, student, intervention_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Intervention not found.")
    try:
        row = await service.reject(db, row, current_user, body.review_notes)
    except state.InterventionStateError as exc:
        raise _state_http(exc) from exc
    await db.commit()
    return service.to_out(row)


@router.post(
    "/students/{student_id}/interventions/{intervention_id}/assign",
    response_model=InterventionOut,
)
async def assign_intervention(
    student_id: str,
    intervention_id: str,
    body: InterventionAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
):
    """Assign only after approval — creates a full Differentiated Homework assignment."""
    try:
        student = await access.require_educator_student(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    row = await service.get_for_student(db, student, intervention_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Intervention not found.")
    try:
        row = await service.assign_via_homework(db, row, student, current_user, body)
    except InterventionHomeworkAssignError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except state.InterventionStateError as exc:
        raise _state_http(exc) from exc
    await db.commit()
    return service.to_out(row)


@router.post(
    "/students/{student_id}/interventions/{intervention_id}/cancel",
    response_model=InterventionOut,
)
async def cancel_intervention(
    student_id: str,
    intervention_id: str,
    body: InterventionReviewRequest = InterventionReviewRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
):
    try:
        student = await access.require_educator_student(db, current_user, student_id)
    except access.ProgressAccessError as exc:
        raise access.as_http(exc) from exc
    row = await service.get_for_student(db, student, intervention_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Intervention not found.")
    try:
        row = await service.cancel(db, row, current_user, body.review_notes)
    except state.InterventionStateError as exc:
        raise _state_http(exc) from exc
    await db.commit()
    return service.to_out(row)
