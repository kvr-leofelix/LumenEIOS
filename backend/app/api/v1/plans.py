"""Teacher plans API: drafts, approval, execution, evidence and recovery proposals (see services/plan_service.py)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_school_context, get_current_user, require_bearer_token
from backend.app.db.session import get_db
from backend.app.models.entities import User
from backend.app.services import plan_service as plans
from backend.app.services.teacher_plan_service import PlanError

router = APIRouter(tags=["Teacher Plans"], dependencies=[Depends(require_bearer_token)])
YEAR = "2026-2027"


class Body(BaseModel):
    model_config = ConfigDict(extra="allow")


class Review(BaseModel):
    decision: str
    note: str = ""


class Supersede(BaseModel):
    reason: str = ""


def _wrap(e: PlanError):
    return HTTPException(status_code=e.status_code, detail=e.detail)


async def _run(db: AsyncSession, coro):
    try:
        out = await coro
        await db.commit()
        return out
    except PlanError as e:
        await db.rollback()
        raise _wrap(e)


@router.get("/plans")
async def list_plans(teacher_id: Optional[str] = None, year: str = YEAR, db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user), school: str = Depends(get_current_school_context)):
    """A teacher sees their own plans; an Admin/Principal sees every teacher's plans in the school, each kept separate."""
    try:
        return {"school_id": school, "academic_year": year, "plans": await plans.list_plans(db, school, user, year, teacher_id)}
    except PlanError as e:
        raise _wrap(e)


@router.post("/teacher-plans/{teacher_id}/plans", status_code=201)
async def create_plan(teacher_id: str, body: Body, year: str = YEAR, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user), school: str = Depends(get_current_school_context)):
    return await _run(db, plans.create_draft(db, user, school, teacher_id, year, body.model_dump()))


@router.post("/plans/{plan_id}/review")
async def review_plan(plan_id: str, body: Review, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
                      school: str = Depends(get_current_school_context)):
    return await _run(db, plans.review_plan(db, user, school, plan_id, body.decision, body.note))


@router.post("/plans/{plan_id}/execution", status_code=201)
async def post_execution(plan_id: str, body: Body, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
                         school: str = Depends(get_current_school_context)):
    return await _run(db, plans.record_execution(db, user, school, plan_id, body.model_dump()))


@router.post("/plans/{plan_id}/evidence", status_code=201)
async def post_evidence(plan_id: str, body: Body, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
                        school: str = Depends(get_current_school_context)):
    return await _run(db, plans.record_evidence(db, user, school, plan_id, body.model_dump()))


@router.post("/plans/{plan_id}/proposals", status_code=201)
async def post_proposal(plan_id: str, body: Body, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
                        school: str = Depends(get_current_school_context)):
    return await _run(db, plans.create_proposal(db, user, school, plan_id, body.model_dump()))


@router.post("/plans/{plan_id}/proposals/supersede")
async def supersede(plan_id: str, body: Supersede, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
                    school: str = Depends(get_current_school_context)):
    return await _run(db, plans.supersede_pending(db, user, school, plan_id, body.reason))


@router.post("/plans/{plan_id}/proposals/{proposal_id}/review")
async def review_proposal(plan_id: str, proposal_id: str, body: Review, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
                          school: str = Depends(get_current_school_context)):
    return await _run(db, plans.review_proposal(db, user, school, plan_id, proposal_id, body.decision, body.note))
