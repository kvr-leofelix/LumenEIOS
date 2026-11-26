"""Teacher-scoped plans, lost periods, oversight views and the central plan log.

Teachers change only their own plan. Principals/Admins inspect and monitor; they have no write route here
for requirements, classifications, relationships or coverage.
"""
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_school_context, get_current_user, require_bearer_token, require_roles
from backend.app.db.session import get_db
from backend.app.models.entities import User
from backend.app.models.teacher_planning import (
    PlanAuditEvent, PlanTopic, SchoolPlanCalendar, TeacherLostPeriod, TeacherTopicConfig, TeacherTopicCoverage,
)
from backend.app.services import annual_allocation as alloc
from backend.app.services import calendar_service as cal
from backend.app.services import lost_period_service as lost
from backend.app.services import plan_service as plan_svc
from backend.app.services import relationship_service as rels
from backend.app.services import teacher_plan_service as svc
from backend.app.services.teacher_plan_service import PlanError

router = APIRouter(prefix="/teacher-plans", tags=["Teacher Plans"], dependencies=[Depends(require_bearer_token)])
oversight = APIRouter(prefix="/plan-oversight", tags=["Plan Oversight"], dependencies=[Depends(require_bearer_token)])
logs = APIRouter(prefix="/plan-logs", tags=["Plan Logs"], dependencies=[Depends(require_bearer_token)])
calendar_router = APIRouter(prefix="/plan-calendar", tags=["Plan Calendar"], dependencies=[Depends(require_bearer_token)])

YEAR = Query("2026-2027")
OVERSIGHT_ROLES = ("admin", "principal")


class Requirement(BaseModel):
    topic_key: str
    core_periods: int
    non_core_periods: int
    classification: Optional[str] = None
    independent_periods: Optional[int] = None
    teaching_mode: Optional[str] = None


class RequirementsIn(BaseModel):
    grade: int
    subject: str
    items: List[Requirement]
    reason: Optional[str] = Field(None, max_length=500)


class CoverageIn(BaseModel):
    grade: int
    subject: str
    topic_key: str
    status: str
    source: str = "MANUAL"
    reason: Optional[str] = Field(None, max_length=500)


class RelationshipIn(BaseModel):
    kind: str = "PREREQUISITE"
    from_key: str
    to_key: str
    explanation: str = ""
    evidence: str = ""
    shared_periods: int = 0
    lead_key: Optional[str] = None
    reason: Optional[str] = Field(None, max_length=500)


class LostIn(BaseModel):
    grade: int
    subject: str
    date: str
    periods: List[int]
    topic_keys: List[str] = []
    reason_code: str
    notes: Optional[str] = Field(None, max_length=1000)


class LostEntry(BaseModel):
    date: str
    periods: List[int]


class LostBatchIn(BaseModel):
    grade: int
    subject: str
    entries: List[LostEntry]
    topic_keys: List[str] = []
    reason_code: str
    notes: Optional[str] = Field(None, max_length=1000)


class LostWithdrawIn(BaseModel):
    grade: int
    subject: str
    date: str
    periods: List[int]
    reason: str


class CalendarIn(BaseModel):
    config: Dict[str, Any]
    reason: str = Field(default="", max_length=500)
    expected_version: Optional[int] = None


def _wrap(exc: PlanError):
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


async def _teacher_in_school(db: AsyncSession, teacher_id: str, school_id: str) -> User:
    t = (await db.execute(select(User).filter(User.id == teacher_id))).scalars().first()
    if not t or t.role != "teacher" or (t.school_id != school_id):
        raise HTTPException(404, "Teacher not found in this school.")
    return t


def _can_view(user: User, teacher_id: str) -> None:
    if user.role == "teacher" and user.id != teacher_id:
        raise HTTPException(403, "Teachers can only view their own plan.")
    if user.role not in ("admin", "principal", "teacher"):
        raise HTTPException(403, "Not permitted.")


@router.post("/{teacher_id}/initialize")
async def initialize(teacher_id: str, grade: int, subject: str, year: str = YEAR, db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user), school: str = Depends(get_current_school_context)):
    try:
        created = await svc.ensure_defaults(db, user, school, teacher_id, year, grade, subject) if user.id == teacher_id and user.role == "teacher" else None
        if created is None:
            raise HTTPException(403, "Only the teacher can initialise their own plan.")
        await db.commit()
    except PlanError as e:
        raise _wrap(e)
    return {"created": created}


@router.get("/{teacher_id}/requirements")
async def all_requirements(teacher_id: str, year: str = YEAR, db: AsyncSession = Depends(get_db),
                           user: User = Depends(get_current_user), school: str = Depends(get_current_school_context)):
    """Every requirement the teacher holds, across classes and subjects. This is what the scheduling engine consumes."""
    _can_view(user, teacher_id)
    await _teacher_in_school(db, teacher_id, school)
    rows = (await db.execute(select(TeacherTopicConfig).filter_by(school_id=school, teacher_id=teacher_id, academic_year=year))).scalars().all()
    current: Dict[Any, set] = {}
    for g, s in {(r.grade, r.subject) for r in rows}:
        current[(g, s)] = {t.topic_key for t in await svc.topics_for(db, g, s)}
    rows = [r for r in rows if r.topic_key in current[(r.grade, r.subject)]]
    return {"teacher_id": teacher_id, "academic_year": year, "items": [
        {"topic_key": r.topic_key, "grade": r.grade, "subject": r.subject, "classification": r.classification,
         "core_periods": r.core_periods, "non_core_periods": r.non_core_periods,
         "independent_periods": r.independent_periods, "teaching_mode": r.teaching_mode,
         "classroom_periods": r.core_periods + r.non_core_periods - r.independent_periods,
         "origin": r.origin, "version": r.version}
        for r in sorted(rows, key=lambda r: (r.grade, r.subject, r.topic_key))]}


@router.get("/{teacher_id}")
async def get_plan(teacher_id: str, grade: int, subject: str, year: str = YEAR, db: AsyncSession = Depends(get_db),
                   user: User = Depends(get_current_user), school: str = Depends(get_current_school_context)):
    _can_view(user, teacher_id)
    await _teacher_in_school(db, teacher_id, school)
    try:
        return await svc.build_plan(db, school, teacher_id, year, grade, subject)
    except PlanError as e:
        raise _wrap(e)


@router.put("/{teacher_id}/requirements")
async def put_requirements(teacher_id: str, body: RequirementsIn, year: str = YEAR, db: AsyncSession = Depends(get_db),
                           user: User = Depends(get_current_user), school: str = Depends(get_current_school_context)):
    try:
        out = await svc.save_requirements(db, user, school, teacher_id, year, body.grade, body.subject,
                                          [i.model_dump(exclude_none=True) for i in body.items], body.reason)
        await db.commit()
        return out
    except PlanError as e:
        await db.rollback()
        raise _wrap(e)


@router.put("/{teacher_id}/coverage")
async def put_coverage(teacher_id: str, body: CoverageIn, year: str = YEAR, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user), school: str = Depends(get_current_school_context)):
    try:
        out = await svc.set_coverage(db, user, school, teacher_id, year, body.grade, body.subject, body.topic_key, body.status, body.reason, body.source)
        await db.commit()
        return out
    except PlanError as e:
        await db.rollback()
        raise _wrap(e)


@router.get("/{teacher_id}/relationships")
async def get_relationships(teacher_id: str, year: str = YEAR, include_removed: bool = False, db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user), school: str = Depends(get_current_school_context)):
    _can_view(user, teacher_id)
    await _teacher_in_school(db, teacher_id, school)
    return {"teacher_id": teacher_id, "academic_year": year, "items": await rels.list_relationships(db, school, teacher_id, year, include_removed)}


@router.post("/{teacher_id}/relationships", status_code=201)
async def post_relationship(teacher_id: str, body: RelationshipIn, year: str = YEAR, db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user), school: str = Depends(get_current_school_context)):
    try:
        out = await rels.add_relationship(db, user, school, teacher_id, year, kind=body.kind, from_key=body.from_key, to_key=body.to_key,
                                          explanation=body.explanation, evidence=body.evidence, shared_periods=body.shared_periods,
                                          lead_key=body.lead_key, reason=body.reason)
        await db.commit()
        return out
    except PlanError as e:
        await db.rollback()
        raise _wrap(e)


@router.delete("/{teacher_id}/relationships/{rel_id}")
async def delete_relationship(teacher_id: str, rel_id: str, reason: Optional[str] = None, year: str = YEAR, db: AsyncSession = Depends(get_db),
                              user: User = Depends(get_current_user), school: str = Depends(get_current_school_context)):
    try:
        out = await rels.remove_relationship(db, user, school, teacher_id, year, rel_id, reason)
        await db.commit()
        return out
    except PlanError as e:
        await db.rollback()
        raise _wrap(e)


@router.post("/{teacher_id}/lost-periods", status_code=201)
async def post_lost(teacher_id: str, body: LostIn, year: str = YEAR, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user), school: str = Depends(get_current_school_context)):
    try:
        out = await lost.record_batch(db, user, school, teacher_id, year, body.grade, body.subject,
                                      [{"date": body.date, "periods": body.periods}], body.topic_keys, body.reason_code, body.notes)
        await db.commit()
        return {"date": body.date, "periods": sorted(body.periods), **out}
    except PlanError as e:
        await db.rollback()
        raise _wrap(e)


@router.post("/{teacher_id}/lost-periods/batch", status_code=201)
async def post_lost_batch(teacher_id: str, body: LostBatchIn, year: str = YEAR, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user), school: str = Depends(get_current_school_context)):
    """Several dates in one atomic submission: either every period is recorded or none is."""
    try:
        out = await lost.record_batch(db, user, school, teacher_id, year, body.grade, body.subject,
                                      [e.model_dump() for e in body.entries], body.topic_keys, body.reason_code, body.notes)
        await db.commit()
        return out
    except PlanError as e:
        await db.rollback()
        raise _wrap(e)


@router.post("/{teacher_id}/lost-periods/withdraw")
async def post_lost_withdraw(teacher_id: str, body: LostWithdrawIn, year: str = YEAR, db: AsyncSession = Depends(get_db),
                             user: User = Depends(get_current_user), school: str = Depends(get_current_school_context)):
    try:
        out = await lost.withdraw(db, user, school, teacher_id, year, body.grade, body.subject, body.date, body.periods, body.reason)
        await db.commit()
        return out
    except PlanError as e:
        await db.rollback()
        raise _wrap(e)


@router.get("/{teacher_id}/lost-periods/all")
async def get_lost_all(teacher_id: str, year: str = YEAR, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
                       school: str = Depends(get_current_school_context)):
    """Every lost-period row for the teacher across classes and subjects (active and withdrawn)."""
    _can_view(user, teacher_id)
    await _teacher_in_school(db, teacher_id, school)
    return {"teacher_id": teacher_id, "academic_year": year, "items": await lost.all_records(db, school, teacher_id, year)}


@router.get("/{teacher_id}/lost-periods")
async def get_lost(teacher_id: str, grade: int, subject: str, year: str = YEAR, today: Optional[str] = None,
                   db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
                   school: str = Depends(get_current_school_context)):
    _can_view(user, teacher_id)
    await _teacher_in_school(db, teacher_id, school)
    return await lost.overview(db, school, teacher_id, year, grade, subject, today or date.today().isoformat())


@router.get("/{teacher_id}/calendar-impact")
async def teacher_calendar_impact(teacher_id: str, grade: int, subject: str, year: str = YEAR, db: AsyncSession = Depends(get_db),
                                  user: User = Depends(get_current_user), school: str = Depends(get_current_school_context)):
    """How the latest calendar change affected this teacher's annual allocation. Read-only for everyone."""
    _can_view(user, teacher_id)
    await _teacher_in_school(db, teacher_id, school)
    return await cal.teacher_impact(db, school, year, teacher_id, grade, subject)


# ------------------------------------------------------------------ oversight
async def _plans_in_school(db: AsyncSession, school: str, year: str, grade=None, subject=None, teacher_id=None):
    q = select(TeacherTopicConfig.teacher_id, TeacherTopicConfig.grade, TeacherTopicConfig.subject).filter_by(
        school_id=school, academic_year=year).distinct()
    if grade:
        q = q.filter(TeacherTopicConfig.grade == grade)
    if subject:
        q = q.filter(TeacherTopicConfig.subject == subject)
    if teacher_id:
        q = q.filter(TeacherTopicConfig.teacher_id == teacher_id)
    return sorted((await db.execute(q)).all(), key=lambda r: (r[0], r[1], r[2]))


@oversight.get("/planning")
async def planning_oversight(year: str = YEAR, grade: Optional[int] = None, subject: Optional[str] = None,
                             teacher_id: Optional[str] = None, today: Optional[str] = None,
                             db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(*OVERSIGHT_ROLES)),
                             school: str = Depends(get_current_school_context)):
    """One row per teacher plan (never merged). A figure that cannot be derived is null, never zero."""
    today = today or date.today().isoformat()
    names = {u.id: u.name for u in (await db.execute(select(User).filter(User.school_id == school))).scalars().all()}
    all_plans = await plan_svc.list_plans(db, school, user, year)
    rows = []
    for tid, g, s in await _plans_in_school(db, school, year, grade, subject, teacher_id):
        plan = await svc.build_plan(db, school, tid, year, g, s)
        lost_ov = await lost.overview(db, school, tid, year, g, s, today)
        mine = [p for p in all_plans if p["teacherId"] == tid and p["grade"] == g and p["subject"] == s]
        approved = next((p for p in mine if p["status"] == "APPROVED"), None)
        latest = approved or (mine[-1] if mine else None)
        figures = plan_svc.plan_figures(approved) if approved else {}
        required = sum(t["core_periods"] + t["non_core_periods"] for t in plan["topics"])
        pending_drafts = [p["id"] for p in mine if p["status"] == "DRAFT"]
        unmet = plan["allocation"]["remaining"] < 0
        core_out = figures.get("outstanding_core_periods")
        pending_n = figures.get("pending_proposals")
        shortfall = bool(approved) and any(c.get("code") == "TIME_SHORTFALL" for c in (approved["versions"][-1]["conflicts"] or []))
        if unmet or shortfall:
            indicator = "red"
        elif lost_ov["lost_periods"] or pending_n or pending_drafts:
            indicator = "amber"
        else:
            indicator = "green"
        rows.append({"teacher_id": tid, "teacher_name": names.get(tid, tid), "grade": g, "subject": s,
                     "config_status": "within_capacity" if plan["allocation"]["valid"] else "over_capacity",
                     "teaching_days_completed": lost_ov["completed_days"], "teaching_days_remaining": lost_ov["remaining_days"],
                     "lost_days": lost_ov["lost_days"], "lost_periods": lost_ov["lost_periods"],
                     "required_periods": required,
                     "scheduled_periods": figures.get("scheduled_periods"), "taught_periods": figures.get("taught_periods"),
                     "outstanding_core_periods": core_out,
                     "pending_proposals": pending_n, "pending_drafts": len(pending_drafts),
                     "approval_status": latest["status"] if latest else "NO_PLAN",
                     "schedule_version": figures.get("schedule_version"),
                     "plan_id": approved["id"] if approved else (latest["id"] if latest else None),
                     "capacity": plan["capacity"], "calendar_version": plan["calendar_version"], "indicator": indicator})
    return {"school_id": school, "academic_year": year, "rows": rows,
            "note": "Figures that are null have no approved schedule behind them yet; they are not zero."}


@oversight.get("/curriculum")
async def curriculum_oversight(year: str = YEAR, grade: Optional[int] = None, subject: Optional[str] = None,
                               teacher_id: Optional[str] = None, db: AsyncSession = Depends(get_db),
                               user: User = Depends(require_roles(*OVERSIGHT_ROLES)),
                               school: str = Depends(get_current_school_context)):
    names = {u.id: u.name for u in (await db.execute(select(User).filter(User.school_id == school))).scalars().all()}
    rows = []
    for tid, g, s in await _plans_in_school(db, school, year, grade, subject, teacher_id):
        plan = await svc.build_plan(db, school, tid, year, g, s)
        chapters: Dict[str, Dict] = {}
        for t in plan["topics"]:
            ch = chapters.setdefault(t["chapter_number"], {"chapter_number": t["chapter_number"], "chapter_title": t["chapter_title"], "topics": []})
            ch["topics"].append({"topic_key": t["topic_key"], "section": t["section"], "status": t["coverage"]})
        for ch in chapters.values():
            ch["stats"] = svc.coverage_stats(x["status"] for x in ch["topics"])
        rows.append({"teacher_id": tid, "teacher_name": names.get(tid, tid), "grade": g, "subject": s,
                     **plan["coverage"], "chapters": list(chapters.values())})
    return {"school_id": school, "academic_year": year, "rows": rows}


# ------------------------------------------------------------------ central log
@logs.get("")
async def list_logs(school_filter: Optional[str] = Query(None, alias="school"), teacher_id: Optional[str] = None,
                    grade: Optional[int] = None, subject: Optional[str] = None, category: Optional[str] = None,
                    status: Optional[str] = None, topic_key: Optional[str] = None, proposal_id: Optional[str] = None,
                    schedule_version: Optional[int] = None, date_from: Optional[str] = None,
                    date_to: Optional[str] = None, limit: int = Query(100, le=500), offset: int = 0,
                    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
                    school: str = Depends(get_current_school_context)):
    """Same records power the central Logs page and every module's contextual history link."""
    if user.role not in ("admin", "principal", "teacher"):
        raise HTTPException(403, "Not permitted.")
    q = select(PlanAuditEvent).filter(PlanAuditEvent.school_id == school)  # school scope is never client-selectable
    if user.role == "teacher":
        q = q.filter(PlanAuditEvent.teacher_id == user.id)
    elif teacher_id:
        q = q.filter(PlanAuditEvent.teacher_id == teacher_id)
    for col, val in ((PlanAuditEvent.grade, grade), (PlanAuditEvent.subject, subject),
                     (PlanAuditEvent.category, category), (PlanAuditEvent.status, status),
                     (PlanAuditEvent.related_proposal_id, proposal_id), (PlanAuditEvent.schedule_version, schedule_version)):
        if val is not None:
            q = q.filter(col == val)
    if date_from:
        q = q.filter(PlanAuditEvent.occurred_at >= date_from)
    if date_to:
        q = q.filter(PlanAuditEvent.occurred_at < f"{date_to}T23:59:59.999999")
    rows = (await db.execute(q.order_by(PlanAuditEvent.occurred_at.desc(), PlanAuditEvent.id.desc()))).scalars().all()
    if topic_key:
        rows = [r for r in rows if topic_key in (r.topic_keys or [])]
    page = rows[offset:offset + limit]
    return {"total": len(rows), "items": [{
        "id": r.id, "occurred_at": r.occurred_at.isoformat(), "actor_id": r.actor_id, "actor_name": r.actor_name,
        "actor_role": r.actor_role, "school_id": r.school_id, "teacher_id": r.teacher_id, "grade": r.grade,
        "subject": r.subject, "topic_keys": r.topic_keys, "category": r.category, "status": r.status,
        "previous_value": r.previous_value, "new_value": r.new_value, "reason": r.reason,
        "schedule_version": r.schedule_version, "related_event_id": r.related_event_id,
        "related_proposal_id": r.related_proposal_id, "summary": r.summary} for r in page]}


# ------------------------------------------------------------------ calendar
@calendar_router.get("")
async def get_plan_calendar(year: str = YEAR, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
                            school: str = Depends(get_current_school_context)):
    cur = await cal.current(db, school, year)
    return {**cur, "available_periods": {s: v["available_periods"] for s, v in cur["capacity"].items()}}


@calendar_router.get("/history")
async def get_plan_calendar_history(year: str = YEAR, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
                                    school: str = Depends(get_current_school_context)):
    """Every saved version, oldest first. Versions are append-only; none is ever rewritten."""
    if user.role not in ("admin", "principal", "teacher"):
        raise HTTPException(403, "Not permitted.")
    return {"school_id": school, "academic_year": year, "versions": await cal.history(db, school, year)}


@calendar_router.post("/preview")
async def preview_calendar(body: CalendarIn, year: str = YEAR, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
                           school: str = Depends(get_current_school_context)):
    """Revised capacity and each plan's resulting headroom. Writes nothing. Teachers see their own; reviewers see all."""
    if user.role not in ("admin", "principal", "teacher"):
        raise HTTPException(403, "Not permitted.")
    try:
        return await cal.preview(db, user, school, year, body.config)
    except PlanError as e:
        raise _wrap(e)


@calendar_router.put("")
async def put_plan_calendar(body: CalendarIn, year: str = YEAR, db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user), school: str = Depends(get_current_school_context)):
    """New calendar version. Teacher requirements and approved schedules are never rewritten; plans that no longer fit are flagged."""
    try:
        out = await cal.save(db, user, school, year, body.config, body.reason, body.expected_version)
        await db.commit()
        return out
    except PlanError as e:
        await db.rollback()
        raise _wrap(e)
