"""School academic calendar versions, validation, recalculation previews and teacher-facing impact.

The calendar (term dates, holidays/exams/events, timetable periods per subject per day) lives only in school_plan_calendars:
append-only versions, each with who/when/why and an audit event holding the capacity before and after. Saving a version
automatically recalculates the REMAINING (untaught) period requirements of every teacher plan (services/recalculation.py): Done topics,
taught periods and classifications are preserved, any shortfall is reported, and approved schedules keep the calendar snapshot they were
approved against until a recalculation proposal is approved. Previews run the identical function without writing.

Allocation rules are those of annual_allocation.py and are not duplicated here:
P = scheduled subject periods on instructional days, R = ceil(10% of P), T = P - R, equal weights, largest remainder, 2:1 mixed split.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import User
from backend.app.models.teacher_planning import SchoolPlanCalendar, TeacherPlan, TeacherTopicConfig
from backend.app.services import annual_allocation as alloc
from backend.app.services.teacher_plan_service import DEFAULT_CALENDAR, PlanError, SUBJECTS, audit, get_calendar, recalculate_plan, topics_for

SUBJECT_LIST = sorted(SUBJECTS)
ENTRY_TYPES = {"HOLIDAY", "VACATION", "EXAM", "EVENT"}


def validate_config(c: Any) -> List[str]:
    """Port of src/lib/planning/calendar.ts validateConfig, so the server never stores a calendar the planner would refuse."""
    if not isinstance(c, dict):
        return ["Calendar must be an object."]
    errors: List[str] = []
    year = c.get("year", "")
    try:
        a, b = str(year).split("-")
        if int(b) != int(a) + 1:
            raise ValueError
    except ValueError:
        errors.append("Academic year must be two consecutive years, e.g. 2026-2027.")
        a = b = ""
    try:
        start, end = date.fromisoformat(c["start"]), date.fromisoformat(c["end"])
        if start >= end:
            errors.append("Calendar end must be after calendar start.")
        if a and (not c["start"].startswith(a) or not c["end"].startswith(b)):
            errors.append(f"Calendar must start in {a} and end in {b}.")
        if (end - start).days + 1 > 366:
            errors.append("Calendar cannot exceed 366 days.")
    except (KeyError, TypeError, ValueError):
        errors.append("Calendar start and end must be valid dates.")
        start = end = None
    wd = c.get("weekdays")
    if not isinstance(wd, list) or not wd or any((not isinstance(x, int)) or x < 0 or x > 6 for x in wd):
        errors.append("Select at least one school working weekday.")
    per_day, minutes = c.get("periodsPerDay"), c.get("periodMinutes")
    if not isinstance(per_day, int) or isinstance(per_day, bool) or not 1 <= per_day <= 12:
        errors.append("Periods per day must be a whole number from 1 to 12.")
    if not isinstance(minutes, int) or isinstance(minutes, bool) or not 10 <= minutes <= 180:
        errors.append("Period duration must be a whole number of minutes from 10 to 180.")
    spd, total = c.get("subjectPeriodsPerDay"), 0
    if not isinstance(spd, dict):
        errors.append("Subject periods per day are required.")
    else:
        for s in SUBJECT_LIST:
            n = spd.get(s)
            if not isinstance(n, int) or isinstance(n, bool) or n < 0:
                errors.append(f"{s} periods per day must be a whole number of 0 or more.")
            else:
                total += n
        if isinstance(per_day, int) and total > per_day:
            errors.append(f"Mathematics and Science periods ({total}) exceed the {per_day} periods in a school day.")
    horizon = c.get("horizonDays")
    if horizon is not None and (not isinstance(horizon, int) or isinstance(horizon, bool) or horizon < 1):
        errors.append("Planning horizon must be a whole number of days or empty.")
    seen, spans = set(), []
    for i, e in enumerate(c.get("entries") or []):
        name = (e.get("label") or "").strip() if isinstance(e, dict) else ""
        if not isinstance(e, dict) or not name:
            errors.append(f"Calendar entry {i + 1} needs a description.")
            continue
        if e.get("id") in seen:
            errors.append(f'Calendar entry "{name}" is duplicated.')
        seen.add(e.get("id"))
        if e.get("type") not in ENTRY_TYPES:
            errors.append(f'"{name}" has an unknown type.')
        try:
            s, f = date.fromisoformat(e["start"]), date.fromisoformat(e["end"])
        except (KeyError, TypeError, ValueError):
            errors.append(f'"{name}" has an invalid date.')
            continue
        if s > f:
            errors.append(f'"{name}" ends before it starts.')
        if start and end and (s < start or f > end):
            errors.append(f'"{name}" falls outside the academic calendar.')
        spans.append((name, s, f))
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            if spans[i][1] <= spans[j][2] and spans[j][1] <= spans[i][2]:
                errors.append(f'Conflict: "{spans[i][0]}" overlaps "{spans[j][0]}".')
    return errors


def capacity_by_subject(config: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
    return {s: alloc.capacity(alloc.available_periods(config, s)) for s in SUBJECT_LIST}


def same_config(a: Any, b: Any) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _version_dict(row: SchoolPlanCalendar, who: Dict[str, Any] | None = None) -> Dict[str, Any]:
    who = who or {}
    return {"version": row.version, "reason": row.reason, "created_by": row.created_by, "created_by_name": who.get("name", row.created_by),
            "created_by_role": who.get("role", "system"), "created_at": row.created_at.isoformat() if row.created_at else None,
            "config": row.config, "capacity": capacity_by_subject(row.config)}


async def history(db: AsyncSession, school_id: str, year: str) -> List[Dict[str, Any]]:
    rows = (await db.execute(select(SchoolPlanCalendar).filter_by(school_id=school_id, academic_year=year).order_by(SchoolPlanCalendar.version))).scalars().all()
    users = {u.id: {"name": u.name, "role": u.role} for u in (await db.execute(select(User).filter(User.id.in_({r.created_by for r in rows})))).scalars().all()}
    return [_version_dict(r, users.get(r.created_by)) for r in rows]


async def current(db: AsyncSession, school_id: str, year: str) -> Dict[str, Any]:
    cal = await get_calendar(db, school_id, year)
    return {"version": cal["version"], "config": cal["config"], "capacity": capacity_by_subject(cal["config"])}


async def _combos(db: AsyncSession, school_id: str, year: str, teacher_id: Optional[str]) -> List[tuple]:
    q = select(TeacherTopicConfig.teacher_id, TeacherTopicConfig.grade, TeacherTopicConfig.subject).filter_by(school_id=school_id, academic_year=year).distinct()
    if teacher_id:
        q = q.filter(TeacherTopicConfig.teacher_id == teacher_id)
    return sorted((await db.execute(q)).all())


async def _impact_rows(db: AsyncSession, school_id: str, year: str, old_cfg: Dict[str, Any], new_cfg: Dict[str, Any], teacher_id: Optional[str]) -> List[Dict[str, Any]]:
    """Per teacher plan: capacity before/after and the recalculated remaining allocation under the new calendar (read-only; the same
    function `save` applies). Done topics, taught periods and classifications are preserved by the recalculation itself."""
    out: List[Dict[str, Any]] = []
    names = {u.id: u.name for u in (await db.execute(select(User).filter(User.school_id == school_id))).scalars().all()}
    plans = (await db.execute(select(TeacherPlan).filter_by(school_id=school_id, academic_year=year, status="APPROVED"))).scalars().all()
    for tid, grade, subject in await _combos(db, school_id, year, teacher_id):
        res = await recalculate_plan(db, None, school_id, tid, year, grade, subject, new_cfg, "preview", write=False)
        rows = res["rows"]
        before = alloc.capacity(alloc.available_periods(old_cfg, subject))
        after = res["capacity"]
        total = sum(r["core"] + r["non_core"] for r in rows)
        new_total = sum(r["new_core"] + r["new_non_core"] for r in rows)
        approved = next((p for p in plans if p.teacher_id == tid and p.grade == grade and p.subject == subject), None)
        out.append({
            "teacher_id": tid, "teacher_name": names.get(tid, tid), "grade": grade, "subject": subject,
            "capacity_before": before, "capacity_after": after, "saved_total": total, "recalculated_total": new_total,
            "remaining_before": before["topic_capacity"] - total, "remaining_after": after["topic_capacity"] - new_total,
            "deficit_after": res["total_shortfall"], "needs_teacher_review": not res["fits"],
            "periods_gained_or_lost": after["topic_capacity"] - before["topic_capacity"],
            "core_requirements_fit": res["core_shortfall"] == 0, "core_shortfall": res["core_shortfall"], "total_shortfall": res["total_shortfall"],
            "insufficient_capacity": not res["fits"], "pool": res["pool"], "done_topics_preserved": res["done_topics"],
            "taught_floor_periods": res["taught_floor_periods"], "topics_changed": res["topics_changed"],
            "topics": [{
                "topic_key": r["topic_key"], "section": r["section"], "classification": r["classification"], "teaching_mode": r["teaching_mode"], "origin": r["origin"],
                "state": r["state"], "coverage": r["coverage"], "taught": r.get("taught", 0),
                "original_allocation": r["core"] + r["non_core"], "default_before": r["core"] + r["non_core"],
                "revised_allocation": r["new_core"] + r["new_non_core"], "allocation_change": r["new_core"] + r["new_non_core"] - (r["core"] + r["non_core"]),
                "original_classroom": r["core"] + r["non_core"] - r["independent"], "revised_classroom": r["new_core"] + r["new_non_core"] - r["new_independent"],
                "classroom_change": (r["new_core"] + r["new_non_core"] - r["new_independent"]) - (r["core"] + r["non_core"] - r["independent"]),
                "original_independent": r["independent"], "revised_independent": r["new_independent"], "independent_change": r["new_independent"] - r["independent"],
                "saved": r["core"] + r["non_core"], "saved_core": r["core"], "revised_core": r["new_core"], "revised_non_core": r["new_non_core"],
                "default_after": r["new_core"] + r["new_non_core"], "is_affected": r["changed"],
                "customization_conflict": r["origin"] == "teacher" and r["changed"],
            } for r in rows],
            "approved_schedule": None if approved is None else {
                "plan_id": approved.id, "calendar_differs": not same_config(approved.config, new_cfg),
                "capacity_conflict": (approved.draft.get("metrics", {}).get("requiredPeriods", 0) > after["topic_capacity"]),
                "note": "The approved schedule keeps its calendar snapshot until a recalculation proposal is approved."},
        })
    return out


async def preview(db: AsyncSession, user: User, school_id: str, year: str, new_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Read-only. Teachers see their own plans' impact; Admin/Principal see every teacher's."""
    problems = validate_config(new_cfg)
    if problems:
        raise PlanError(422, {"message": "Calendar rejected.", "errors": problems})
    cur = await get_calendar(db, school_id, year)
    rows = await _impact_rows(db, school_id, year, cur["config"], new_cfg, user.id if user.role == "teacher" else None)
    return {"current_version": cur["version"], "proposed_version": cur["version"] + 1, "unchanged": same_config(cur["config"], new_cfg),
            "capacity_before": capacity_by_subject(cur["config"]), "capacity_after": capacity_by_subject(new_cfg), "impact": rows,
            "teacher_configurations_changed": False, "will_recalculate_remaining_syllabus": True}


async def save(db: AsyncSession, user: User, school_id: str, year: str, new_cfg: Dict[str, Any], reason: str, expected_version: Optional[int]) -> Dict[str, Any]:
    if user.role not in ("admin", "principal"):
        raise PlanError(403, "Only an Admin or Principal can change the academic calendar.")
    problems = validate_config(new_cfg)
    if problems:
        raise PlanError(422, {"message": "Calendar rejected.", "errors": problems})
    cur = await get_calendar(db, school_id, year)
    if expected_version is not None and expected_version != cur["version"]:
        raise PlanError(409, "A different Academic Configuration was saved while you were editing. Review it, then save again.")
    if cur["version"] and same_config(cur["config"], new_cfg):
        raise PlanError(422, "The calendar is unchanged; there is nothing to save.")
    if len((reason or "").strip()) < 3:
        raise PlanError(422, "A reason for the calendar change is required.")
    number = cur["version"] + 1
    db.add(SchoolPlanCalendar(school_id=school_id, academic_year=year, version=number, config=new_cfg, reason=reason.strip(), created_by=user.id))
    await db.flush()
    # Automatic recalculation of every teacher plan's REMAINING (untaught) allocation under the new calendar.
    recalculated: List[Dict[str, Any]] = []
    for tid, grade, subject in await _combos(db, school_id, year, None):
        res = await recalculate_plan(db, user, school_id, tid, year, grade, subject, new_cfg, f"Calendar version {number}: {reason.strip()}", write=True)
        recalculated.append({"teacher_id": tid, "grade": grade, "subject": subject, "topics_changed": res["topics_changed"], "topic_capacity": res["capacity"]["topic_capacity"],
                             "core_shortfall": res["core_shortfall"], "total_shortfall": res["total_shortfall"], "fits": res["fits"]})
    impacted = [r for r in recalculated if not r["fits"]]
    audit(db, user, school_id, "calendar_change", f"Calendar version {number} saved ({reason.strip()})",
          previous={"version": cur["version"], "capacity": capacity_by_subject(cur["config"])},
          new={"version": number, "capacity": capacity_by_subject(new_cfg), "teachers_needing_review": [f"{r['teacher_id']}:{r['grade']}:{r['subject']}" for r in impacted],
               "plans_recalculated": len(recalculated), "topics_changed": sum(r["topics_changed"] for r in recalculated)},
          reason=reason.strip(), schedule_version=None)
    return {"version": number, "teachers_needing_review": len(impacted), "plans_recalculated": len(recalculated),
            "topics_changed": sum(r["topics_changed"] for r in recalculated), "recalculated": recalculated}


async def teacher_impact(db: AsyncSession, school_id: str, year: str, teacher_id: str, grade: int, subject: str) -> Dict[str, Any]:
    """How the latest calendar change affected this teacher's annual allocation (current version versus the one before)."""
    versions = await history(db, school_id, year)
    cur = versions[-1] if versions else {"version": 0, "config": {**DEFAULT_CALENDAR, "year": year}, "reason": None, "created_at": None, "capacity": capacity_by_subject(DEFAULT_CALENDAR)}
    prev = versions[-2] if len(versions) > 1 else None
    rows = [r for r in await _impact_rows(db, school_id, year, (prev or cur)["config"], cur["config"], teacher_id) if r["grade"] == grade and r["subject"] == subject]
    return {"current_version": cur["version"], "previous_version": prev["version"] if prev else None, "changed_at": cur.get("created_at"), "reason": cur.get("reason"),
            "has_previous": prev is not None, "impact": rows[0] if rows else None}
