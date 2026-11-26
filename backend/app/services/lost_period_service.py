"""Lost periods: the single authoritative record of what could not be taught.

One row per (teacher, class, subject, date, period). Lost periods = active rows; lost days = distinct dates among active
rows, so several periods on one date are one day. Corrections withdraw rows softly (status, reason, actor, time) and a
re-recording of a withdrawn period reactivates the same row; nothing is deleted and every change is a plan_audit_events row.
Rows linked to an approved recovery (`schedule_version`) cannot be withdrawn.
"""
from __future__ import annotations

import uuid
from datetime import date as _date
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import User
from backend.app.models.teacher_planning import PlanTopic, TeacherLostPeriod
from backend.app.services import annual_allocation as alloc
from backend.app.services.teacher_plan_service import PlanError, _check_combo, _require_owner, audit, get_calendar, topics_for

# The reason vocabulary of the existing recorder (losses.ts LOSS_REASONS) plus the codes used by the first relational API.
LEGACY_REASONS = ["Election Duties", "Census Duties", "Teacher Training", "Health Drive", "Extreme Weather", "Local Festival",
                  "Administrative Work", "Unplanned school event", "Other"]
REASON_CODES = ["school_closed", "school_event", "teacher_unavailable", "ran_out_of_time", "other"]
LOST_REASONS = set(LEGACY_REASONS) | set(REASON_CODES)
MIN_CORRECTION_REASON = 5


def row_dict(r: TeacherLostPeriod) -> Dict[str, Any]:
    return {"id": r.id, "grade": r.grade, "subject": r.subject, "date": r.lost_date, "period": r.period_number,
            "reason": r.reason_code, "topic_keys": r.topic_keys or [], "notes": r.notes, "batch_id": r.batch_id,
            "status": r.status, "withdrawn_reason": r.withdrawn_reason, "recorded_by": r.recorded_by,
            "recorded_at": r.created_at.isoformat() if r.created_at else None, "schedule_version": r.schedule_version}


def _key(school_id: str, teacher_id: str, year: str, grade: int, subject: str) -> Dict[str, Any]:
    return dict(school_id=school_id, teacher_id=teacher_id, academic_year=year, grade=grade, subject=subject)


async def approved_schedule(db: AsyncSession, school_id: str, teacher_id: str, year: str, grade: int, subject: str):
    """The teacher's APPROVED plan for the class and subject, with its current version's classroom slots, or None."""
    from backend.app.models.teacher_planning import TeacherPlan, TeacherPlanExecution, TeacherPlanVersion
    plan = (await db.execute(select(TeacherPlan).filter_by(school_id=school_id, teacher_id=teacher_id, academic_year=year, grade=grade,
                                                           subject=subject, status="APPROVED"))).scalars().first()
    if plan is None:
        return None
    version = (await db.execute(select(TeacherPlanVersion).filter_by(plan_id=plan.id).order_by(TeacherPlanVersion.version.desc()).limit(1))).scalars().first()
    events = (await db.execute(select(TeacherPlanExecution).filter_by(plan_id=plan.id))).scalars().all()
    superseded = {e.supersedes for e in events if e.supersedes}
    taught = {e.node_key for e in events if e.id not in superseded and e.status == "TAUGHT"}
    owner = {}
    for lesson in version.lessons if version else []:
        for sl in lesson.get("slots") or []:
            owner[(sl.get("date"), sl.get("period"))] = lesson.get("nodeId")
    absorbed = {(x.get("date"), x.get("period")) for x in (version.lost_slots if version else []) or []}
    return {"plan_id": plan.id, "owner": owner, "absorbed": absorbed, "taught": taught}


async def _validate_entry(db: AsyncSession, cal: Dict[str, Any], subject: str, lost_date: str, periods: List[int], schedule=None, importing: bool = False) -> None:
    try:
        _date.fromisoformat(lost_date)
    except (TypeError, ValueError):
        raise PlanError(422, f"Invalid date: {lost_date!r}")
    if not periods or any((not isinstance(n, int)) or isinstance(n, bool) or n < 1 for n in periods) or len(set(periods)) != len(periods):
        raise PlanError(422, "Provide one or more distinct period numbers (1 or higher).")
    if schedule is not None:
        # An approved schedule keeps the calendar it was approved against, so a period is valid when it is a classroom period of that
        # schedule (the school's current timetable may have changed since), and a topic already recorded as taught cannot lose a period.
        for n in periods:
            node = schedule["owner"].get((lost_date, n))
            if node is None:
                if importing and (lost_date, n) in schedule["absorbed"]:
                    continue  # history: a loss an earlier approved recovery already absorbed (import only)
                if (lost_date, n) in schedule["absorbed"]:
                    raise PlanError(409, f"{lost_date} period {n} was already recorded as lost and absorbed by an approved recovery.")
                raise PlanError(422, f"{lost_date} period {n} is not a classroom period of the approved schedule.")
            if node in schedule["taught"] and not importing:
                raise PlanError(422, f'"{node}" is recorded as taught. Correct the classroom execution record before recording a loss for it.')
        return
    if lost_date not in set(alloc.instructional_dates(cal["config"])):
        raise PlanError(422, f"{lost_date} is not an instructional day in this school's calendar.")
    scheduled = alloc.subject_periods_for_date(cal["config"], subject, lost_date)
    if max(periods) > scheduled:
        raise PlanError(422, f"Only {scheduled} {subject} period(s) are timetabled on {lost_date}.")


async def record_batch(db: AsyncSession, actor: User, school_id: str, teacher_id: str, year: str, grade: int, subject: str,
                       entries: List[Dict[str, Any]], topic_keys: List[str], reason: str, notes: Optional[str],
                       batch_id: Optional[str] = None, origin_note: Optional[str] = None, created_at=None, recorded_by: Optional[str] = None,
                       skip_owner_check: bool = False, importing: bool = False) -> Dict[str, Any]:
    """All-or-nothing: every (date, period) in `entries` is validated before any row is written."""
    if not skip_owner_check:
        _require_owner(actor, school_id, teacher_id)
    _check_combo(grade, subject)
    if reason not in LOST_REASONS:
        raise PlanError(422, f"Reason must be one of {sorted(LOST_REASONS)}.")
    if not entries:
        raise PlanError(422, "Select at least one lost period.")
    known = {t.topic_key for t in await topics_for(db, grade, subject)}
    if any(k not in known for k in topic_keys):
        raise PlanError(422, "Affected topic is not part of this class and subject.")
    cal = await get_calendar(db, school_id, year)
    schedule = await approved_schedule(db, school_id, teacher_id, year, grade, subject)
    seen = set()
    for e in entries:
        await _validate_entry(db, cal, subject, e["date"], e["periods"], schedule, importing)
        for n in e["periods"]:
            if (e["date"], n) in seen:
                raise PlanError(422, "Each period can be selected only once.")
            seen.add((e["date"], n))
    key = _key(school_id, teacher_id, year, grade, subject)
    existing = {(r.lost_date, r.period_number): r for r in (await db.execute(select(TeacherLostPeriod).filter_by(**key))).scalars().all()}
    dup = sorted(f"{d} period {n}" for d, n in seen if (d, n) in existing and existing[(d, n)].status == "active")
    if dup:
        raise PlanError(409, f"Already recorded as lost: {', '.join(dup)}.")
    batch = batch_id or uuid.uuid4().hex
    rows: List[TeacherLostPeriod] = []
    for e in entries:
        for n in sorted(e["periods"]):
            prior = existing.get((e["date"], n))
            if prior:  # a withdrawn period lost again: same row, back to active, the withdrawal stays in the audit trail
                prior.status, prior.withdrawn_reason, prior.withdrawn_by, prior.withdrawn_at = "active", None, None, None
                prior.reason_code, prior.notes, prior.topic_keys, prior.batch_id = reason, notes, topic_keys, batch
                prior.recorded_by = recorded_by or actor.id
                rows.append(prior)
            else:
                row = TeacherLostPeriod(**key, lost_date=e["date"], period_number=n, topic_keys=topic_keys, reason_code=reason,
                                        notes=notes, recorded_by=recorded_by or actor.id, batch_id=batch, status="active")
                if created_at is not None:
                    row.created_at = created_at
                db.add(row)
                rows.append(row)
    await db.flush()
    ev_ids: Dict[str, str] = {}
    for e in sorted(entries, key=lambda x: x["date"]):
        periods = sorted(e["periods"])
        ev = audit(db, actor, school_id, "lost_period", f"Lost period(s) {periods} on {e['date']} ({reason})", teacher_id=teacher_id,
                   grade=grade, subject=subject, topic_keys=topic_keys,
                   new={"date": e["date"], "periods": periods, "reason": reason, "notes": notes, "batch_id": batch}, reason=origin_note or reason)
        ev_ids[e["date"]] = ev.id
        others = [p for (d, p), r in existing.items() if d == e["date"] and r.status == "active"]
        if not others:  # first active period on this date: a new lost day
            audit(db, actor, school_id, "lost_day", f"Lost day {e['date']}", teacher_id=teacher_id, grade=grade, subject=subject,
                  topic_keys=topic_keys, new={"date": e["date"]}, reason=origin_note or reason, related_event_id=ev.id)
    return {"batch_id": batch, "records": [row_dict(r) for r in rows]}


async def withdraw(db: AsyncSession, actor: User, school_id: str, teacher_id: str, year: str, grade: int, subject: str,
                   lost_date: str, periods: List[int], reason: str) -> Dict[str, Any]:
    """Correction: the periods were not lost after all. Requires a reason; refused once a recovery using them is approved."""
    _require_owner(actor, school_id, teacher_id)
    _check_combo(grade, subject)
    if len((reason or "").strip()) < MIN_CORRECTION_REASON:
        raise PlanError(422, f"Explain the correction (at least {MIN_CORRECTION_REASON} characters).")
    if not periods or len(set(periods)) != len(periods):
        raise PlanError(422, "Select one or more distinct periods to withdraw.")
    key = _key(school_id, teacher_id, year, grade, subject)
    rows = {r.period_number: r for r in (await db.execute(select(TeacherLostPeriod).filter_by(**key, lost_date=lost_date))).scalars().all()}
    missing = [n for n in periods if n not in rows or rows[n].status != "active"]
    if missing:
        raise PlanError(404, f"No active lost record for period(s) {sorted(missing)} on {lost_date}.")
    approved = [n for n in periods if rows[n].schedule_version is not None]
    if approved:
        raise PlanError(409, f"Period(s) {sorted(approved)} already have an approved recovery (schedule version {rows[approved[0]].schedule_version}). An approved version cannot be undone by editing a loss record.")
    from datetime import datetime, timezone
    for n in periods:
        r = rows[n]
        r.status, r.withdrawn_reason, r.withdrawn_by, r.withdrawn_at = "withdrawn", reason.strip(), actor.id, datetime.now(timezone.utc)
    await db.flush()
    ev = audit(db, actor, school_id, "lost_period", f"Withdrawn: period(s) {sorted(periods)} on {lost_date}", teacher_id=teacher_id,
               grade=grade, subject=subject, topic_keys=rows[periods[0]].topic_keys or [], status="withdrawn",
               previous={"date": lost_date, "periods": sorted(periods), "status": "active"},
               new={"date": lost_date, "periods": sorted(periods), "status": "withdrawn"}, reason=reason.strip())
    remaining = [n for n, r in rows.items() if r.status == "active"]
    if not remaining:
        audit(db, actor, school_id, "lost_day", f"Lost day {lost_date} withdrawn", teacher_id=teacher_id, grade=grade, subject=subject,
              status="withdrawn", previous={"date": lost_date}, new=None, reason=reason.strip(), related_event_id=ev.id)
    return {"date": lost_date, "withdrawn": sorted(periods), "lost_day_remains": bool(remaining)}


async def overview(db: AsyncSession, school_id: str, teacher_id: str, year: str, grade: int, subject: str, today: Optional[str]) -> Dict[str, Any]:
    key = _key(school_id, teacher_id, year, grade, subject)
    rows = (await db.execute(select(TeacherLostPeriod).filter_by(**key).order_by(TeacherLostPeriod.lost_date.desc(), TeacherLostPeriod.period_number))).scalars().all()
    active = [r for r in rows if r.status == "active"]
    cal = await get_calendar(db, school_id, year)
    recs = [{"date": r.lost_date, "period": r.period_number} for r in active]
    counts = alloc.day_counts(cal["config"], today, [r["date"] for r in recs])
    return {**counts, **alloc.lost_summary(recs),
            "log": [{"id": r.id, "date": r.lost_date, "period": r.period_number, "reason": r.reason_code, "topic_keys": r.topic_keys, "notes": r.notes}
                    for r in active[:50]],
            "records": [row_dict(r) for r in rows]}  # includes withdrawn rows so history is visible


async def all_records(db: AsyncSession, school_id: str, teacher_id: str, year: str) -> List[Dict[str, Any]]:
    rows = (await db.execute(select(TeacherLostPeriod).filter_by(school_id=school_id, teacher_id=teacher_id, academic_year=year)
                             .order_by(TeacherLostPeriod.grade, TeacherLostPeriod.subject, TeacherLostPeriod.lost_date,
                                       TeacherLostPeriod.period_number))).scalars().all()
    return [row_dict(r) for r in rows]


async def school_lost_days(db: AsyncSession, school_ids, *, teacher_id: Optional[str] = None,
                           grades: Optional[Iterable[int]] = None) -> List[Dict[str, Any]]:
    """Lost teaching days per school, from the same records the Time-Aware Engine uses (dashboards and calendar).

    Teachers record lost periods against their plans (teacher_lost_periods). A date with any active lost period is one
    lost teaching day for the school, however many periods or classes it affected, matching the engine's "lost days"."""
    rows = (await db.execute(
        select(TeacherLostPeriod).filter(TeacherLostPeriod.school_id.in_(school_ids), TeacherLostPeriod.status == "active",
                                         *([TeacherLostPeriod.teacher_id == teacher_id] if teacher_id else []),
                                         *([TeacherLostPeriod.grade.in_(list(grades))] if grades is not None else []))
        .order_by(TeacherLostPeriod.lost_date))).scalars().all()
    recorders = {r.recorded_by for r in rows}
    names = dict((await db.execute(select(User.id, User.name).filter(User.id.in_(recorders)))).all()) if recorders else {}
    days: dict = {}
    for r in rows:
        day = days.setdefault((r.school_id, r.lost_date), {"reasons": [], "classes": set(), "periods": 0, "by": []})
        reason = r.reason_code.replace("_", " ")
        reason = reason[:1].upper() + reason[1:]
        if reason not in day["reasons"]:
            day["reasons"].append(reason)
        day["classes"].add(f"Class {r.grade} {r.subject}")
        day["periods"] += 1
        name = names.get(r.recorded_by, r.recorded_by)
        if name not in day["by"]:
            day["by"].append(name)
    return [{"id": f"{school}:{date}", "schoolId": school, "date": date, "reason": ", ".join(d["reasons"]), "daysLost": 1,
             "recordedBy": ", ".join(d["by"]),
             "notes": f"{d['periods']} period{'' if d['periods'] == 1 else 's'} lost · {', '.join(sorted(d['classes']))}"}
            for (school, date), d in days.items()]
