"""Teacher-scoped plan operations. Every mutation writes its audit event in the same transaction."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import User, generate_uuid
from backend.app.models.teacher_planning import (
    PlanAuditEvent, PlanTopic, SchoolPlanCalendar, TeacherLostPeriod, TeacherPlan, TeacherPlanExecution, TeacherTopicConfig,
    TeacherTopicCoverage, TeacherTopicRelationship,
)
from backend.app.services import annual_allocation as alloc
from backend.app.services import recalculation as recalc

DEFAULT_CALENDAR = {
    "year": "2026-2027", "start": "2026-04-01", "end": "2027-03-31", "weekdays": [1, 2, 3, 4, 5], "entries": [],
    "periodsPerDay": 8, "periodMinutes": 40, "subjectPeriodsPerDay": {"Mathematics": 2, "Science": 2}, "horizonDays": None,
}
SUBJECTS = {"Mathematics", "Science"}
CLASSIFICATIONS = {"core", "non_core", "mixed"}
COVERAGE = {"done", "in_progress", "not_done"}
COVERAGE_SOURCES = {"MANUAL", "EXECUTION"}
DEMO_NOTE = "Hypothetical demonstration default; not official NCERT or expert-approved."


class PlanError(Exception):
    def __init__(self, status_code: int, detail: Any):
        self.status_code, self.detail = status_code, detail


def audit(db: AsyncSession, actor: User, school_id: str, category: str, summary: str, *, teacher_id=None, grade=None,
          subject=None, topic_keys=None, previous=None, new=None, reason=None, schedule_version=None,
          related_event_id=None, related_proposal_id=None, status="recorded") -> PlanAuditEvent:
    ev = PlanAuditEvent(id=generate_uuid(), actor_id=actor.id, actor_name=actor.name, actor_role=actor.role, school_id=school_id,
                        teacher_id=teacher_id, grade=grade, subject=subject, topic_keys=list(topic_keys or []),
                        category=category, status=status, previous_value=previous, new_value=new, reason=reason,
                        schedule_version=schedule_version, related_event_id=related_event_id,
                        related_proposal_id=related_proposal_id, summary=summary[:500])
    db.add(ev)
    return ev


async def get_calendar(db: AsyncSession, school_id: str, year: str) -> Dict[str, Any]:
    res = await db.execute(select(SchoolPlanCalendar).filter_by(school_id=school_id, academic_year=year)
                           .order_by(SchoolPlanCalendar.version.desc()).limit(1))
    row = res.scalars().first()
    return {"version": row.version if row else 0, "config": row.config if row else {**DEFAULT_CALENDAR, "year": year}}


CATALOGUE_REF = "ncert-batch:"


async def topics_for(db: AsyncSession, grade: int, subject: str) -> List[PlanTopic]:
    res = await db.execute(select(PlanTopic).filter_by(grade=grade, subject=subject).order_by(PlanTopic.sort_order, PlanTopic.topic_key))
    rows = list(res.scalars().all())
    # Once the adopted catalogue dataset has topics for this class and subject (source_ref 'ncert-batch:<node id>'), it is the one
    # curriculum. Earlier crosswalk-only rows stay in the table (teacher records still reference them) but are not mixed in.
    adopted = [t for t in rows if (t.source_ref or "").startswith(CATALOGUE_REF)]
    return adopted or rows


def _check_combo(grade: int, subject: str) -> None:
    if subject not in SUBJECTS or grade not in (6, 7, 8):
        raise PlanError(422, "Only Classes VI-VIII Mathematics and Science are supported.")


async def ensure_defaults(db: AsyncSession, actor: User, school_id: str, teacher_id: str, year: str, grade: int,
                          subject: str) -> bool:
    """Fill missing teacher-scoped topic configs deterministically; never changes an existing decision."""
    _check_combo(grade, subject)
    topics = await topics_for(db, grade, subject)
    if not topics:
        return False
    key = dict(school_id=school_id, teacher_id=teacher_id, academic_year=year, grade=grade, subject=subject)
    existing = {c.topic_key: c for c in (await db.execute(select(TeacherTopicConfig).filter_by(**key))).scalars().all()}
    existing_coverage = {c.topic_key for c in (await db.execute(select(TeacherTopicCoverage).filter_by(**key))).scalars().all()}
    missing = [t for t in topics if t.topic_key not in existing]
    missing_coverage = [t for t in topics if t.topic_key not in existing_coverage]
    if not missing and not missing_coverage:
        return False
    cal = await get_calendar(db, school_id, year)
    p = alloc.available_periods(cal["config"], subject)
    ordered = sorted(topics, key=lambda t: (t.sort_order, t.topic_key))
    topic_cap = alloc.capacity(p)["topic_capacity"]
    preserved_total = sum(c.core_periods + c.non_core_periods for c in existing.values()
                          if c.topic_key in {t.topic_key for t in topics})
    # Initial defaults divide only the capacity that is still real: the annual room, limited to the periods left after today.
    remaining_capacity = max(0, min(topic_cap - preserved_total, remaining_window(cal["config"], subject, planning_today())["capacity_left"]))
    rows = {r["topic_key"]: r for r in alloc.topic_allocations(
        [{"topic_key": t.topic_key, "weight": 1} for t in ordered if t.topic_key not in existing], p,
        topic_capacity_override=remaining_capacity)}
    for t in missing:
        row = rows[t.topic_key]
        db.add(TeacherTopicConfig(school_id=school_id, teacher_id=teacher_id, academic_year=year, grade=grade,
                                  subject=subject, topic_key=t.topic_key, classification=row["classification"],
                                  core_periods=row["core"], non_core_periods=row["non_core"],
                                  teaching_mode=row["teaching_mode"], independent_periods=row["independent_periods"], origin="demo_default",
                                  version=1, updated_by=actor.id))
    for t in missing_coverage:
        db.add(TeacherTopicCoverage(school_id=school_id, teacher_id=teacher_id, academic_year=year, grade=grade,
                                    subject=subject, topic_key=t.topic_key, status="not_done", source="MANUAL", updated_by=actor.id))
    if missing or missing_coverage:
        audit(db, actor, school_id, "period_requirement", f"Deterministic demonstration defaults initialized ({len(missing)} topic configs)",
              teacher_id=teacher_id, grade=grade, subject=subject, topic_keys=[t.topic_key for t in missing],
              new={"capacity": alloc.capacity(p), "config_rows_added": len(missing), "coverage_rows_added": len(missing_coverage),
                   "note": DEMO_NOTE}, reason=DEMO_NOTE)
    return True


TAUGHT_STATUSES = ("TAUGHT", "PARTIAL")


def planning_today() -> str:
    """The planning date: the configured PLANNING_TODAY override (tests/demos) or the server's current date."""
    from backend.app.core.config import settings
    return getattr(settings, "PLANNING_TODAY", None) or date.today().isoformat()


def remaining_window(cfg: Dict[str, Any], subject: str, today: str) -> Dict[str, int]:
    """P_rem, R_rem = ceil(0.10 P_rem), T_rem = P_rem - R_rem for the instructional days after `today`."""
    p_rem = alloc.remaining_periods(cfg, subject, today)
    cap = alloc.capacity(p_rem)
    return {"after": today, "days_left": alloc.remaining_days(cfg, today), "periods_left": p_rem, "reserve_left": cap["reserved_periods"], "capacity_left": cap["topic_capacity"]}


async def taught_by_topic(db: AsyncSession, school_id: str, teacher_id: str, year: str, grade: int, subject: str) -> Dict[str, int]:
    """Periods ACTUALLY taught per topic, from this teacher's classroom execution records (corrections supersede; homework and
    deferrals are never teaching). Scheduled periods are not counted here."""
    plan_ids = [pid for (pid,) in (await db.execute(select(TeacherPlan.id).filter_by(school_id=school_id, teacher_id=teacher_id, academic_year=year,
                                                                                    grade=grade, subject=subject))).all()]
    if not plan_ids:
        return {}
    events = (await db.execute(select(TeacherPlanExecution).where(TeacherPlanExecution.plan_id.in_(plan_ids)))).scalars().all()
    replaced = {e.supersedes for e in events if e.supersedes}
    out: Dict[str, int] = {}
    for e in events:
        if e.id in replaced or e.status not in TAUGHT_STATUSES:
            continue
        out[e.node_key] = out.get(e.node_key, 0) + (e.periods_taught or 0)
    return out


async def recalculation_inputs(db: AsyncSession, school_id: str, teacher_id: str, year: str, grade: int, subject: str) -> List[Dict[str, Any]]:
    """Persisted configuration + coverage + taught periods of one teacher plan, in syllabus order (the recalculation's only input)."""
    topics = await topics_for(db, grade, subject)
    key = dict(school_id=school_id, teacher_id=teacher_id, academic_year=year, grade=grade, subject=subject)
    cfgs = {c.topic_key: c for c in (await db.execute(select(TeacherTopicConfig).filter_by(**key))).scalars().all()}
    cov = {c.topic_key: c.status for c in (await db.execute(select(TeacherTopicCoverage).filter_by(**key))).scalars().all()}
    taught = await taught_by_topic(db, school_id, teacher_id, year, grade, subject)
    return [{"topic_key": t.topic_key, "section": t.section_label, "classification": cfgs[t.topic_key].classification,
             "core": cfgs[t.topic_key].core_periods, "non_core": cfgs[t.topic_key].non_core_periods,
             "independent": cfgs[t.topic_key].independent_periods, "teaching_mode": cfgs[t.topic_key].teaching_mode,
             "origin": cfgs[t.topic_key].origin, "coverage": cov.get(t.topic_key, "not_done"), "taught": taught.get(t.topic_key, 0)}
            for t in sorted(topics, key=lambda t: (t.sort_order, t.topic_key)) if t.topic_key in cfgs]


async def recalculate_plan(db: AsyncSession, actor: User, school_id: str, teacher_id: str, year: str, grade: int, subject: str,
                           cfg: Dict[str, Any], reason: str, write: bool = True, today: Optional[str] = None) -> Dict[str, Any]:
    """Recompute the remaining (untaught) allocation of one teacher plan for calendar `cfg`. Done topics, taught periods and every
    persisted classification are preserved. With write=False nothing is stored (preview)."""
    inputs = await recalculation_inputs(db, school_id, teacher_id, year, grade, subject)
    cap = alloc.capacity(alloc.available_periods(cfg, subject))
    window = remaining_window(cfg, subject, today or planning_today())
    res = recalc.compute(inputs, cap["topic_capacity"], window["capacity_left"])
    res["capacity"] = cap
    res["window"] = window
    changed = [r for r in res["rows"] if r["changed"]]
    res["topics_changed"] = len(changed)
    if write and changed:
        key = dict(school_id=school_id, teacher_id=teacher_id, academic_year=year, grade=grade, subject=subject)
        cfgs = {c.topic_key: c for c in (await db.execute(select(TeacherTopicConfig).filter_by(**key))).scalars().all()}
        for r in changed:
            c = cfgs[r["topic_key"]]
            c.core_periods, c.non_core_periods, c.independent_periods = r["new_core"], r["new_non_core"], r["new_independent"]
            c.version, c.updated_by = c.version + 1, actor.id
    if write and (changed or not res["fits"]):
        audit(db, actor, school_id, "calendar_recalculation",
              f"Remaining syllabus recalculated for Class {grade} {subject}: topic capacity {cap['topic_capacity']}, {res['topics_changed']} untaught topic(s) changed"
              + ("" if res["fits"] else f"; SHORTFALL core={res['core_shortfall']} total={res['total_shortfall']}"),
              teacher_id=teacher_id, grade=grade, subject=subject, topic_keys=[r["topic_key"] for r in changed][:200],
              previous={"core": res["before"]["core"], "non_core": res["before"]["non_core"]},
              new={"core": res["after"]["core"], "non_core": res["after"]["non_core"], "capacity": cap, "window": window, "pool": res["pool"],
                   "done_topics_preserved": res["done_topics"], "taught_floor_periods": res["taught_floor_periods"],
                   "core_shortfall": res["core_shortfall"], "total_shortfall": res["total_shortfall"]},
              reason=reason)
    return res


async def build_plan(db: AsyncSession, school_id: str, teacher_id: str, year: str, grade: int, subject: str) -> Dict:
    _check_combo(grade, subject)
    cal = await get_calendar(db, school_id, year)
    p = alloc.available_periods(cal["config"], subject)
    cap = alloc.capacity(p)
    topics = {t.topic_key: t for t in await topics_for(db, grade, subject)}
    key = dict(school_id=school_id, teacher_id=teacher_id, academic_year=year, grade=grade, subject=subject)
    cfgs = [c for c in (await db.execute(select(TeacherTopicConfig).filter_by(**key))).scalars().all() if c.topic_key in topics]
    cov_rows = {c.topic_key: c for c in (await db.execute(select(TeacherTopicCoverage).filter_by(**key))).scalars().all()}
    cov = {k: c.status for k, c in cov_rows.items()}
    rels = (await db.execute(select(TeacherTopicRelationship).filter_by(
        school_id=school_id, teacher_id=teacher_id, academic_year=year, status="active", kind="PREREQUISITE"))).scalars().all()
    rows = []
    for c in sorted(cfgs, key=lambda c: (topics[c.topic_key].sort_order, c.topic_key)):
        t = topics[c.topic_key]
        rows.append({"topic_key": c.topic_key, "chapter_number": t.chapter_number, "chapter_title": t.chapter_title,
                     "section": t.section_label, "classification": c.classification, "core_periods": c.core_periods,
                     "non_core_periods": c.non_core_periods, "teaching_mode": c.teaching_mode,
                     "independent_periods": c.independent_periods, "classroom_periods": c.core_periods + c.non_core_periods - c.independent_periods,
                     "origin": c.origin, "version": c.version,
                     "coverage": cov.get(c.topic_key, "not_done"),
                     "coverage_source": cov_rows[c.topic_key].source if c.topic_key in cov_rows else "MANUAL",
                     "coverage_updated_at": cov_rows[c.topic_key].updated_at.isoformat() if c.topic_key in cov_rows and cov_rows[c.topic_key].updated_at else None,
                     "prerequisites": [r.prerequisite_key for r in rels if r.topic_key == c.topic_key]})
    inputs = await recalculation_inputs(db, school_id, teacher_id, year, grade, subject)
    window = remaining_window(cal["config"], subject, planning_today())
    comp = recalc.compute(inputs, cap["topic_capacity"], window["capacity_left"])
    by_key = {r["topic_key"]: r for r in comp["rows"]}
    for r in rows:
        x = by_key.get(r["topic_key"], {})
        r["taught_periods"] = x.get("taught", 0)
        r["remaining_core"], r["remaining_non_core"] = x.get("remaining_core", 0), x.get("remaining_non_core", 0)
    summary = {
        "periods_per_day": int((cal["config"].get("subjectPeriodsPerDay") or {}).get(subject, 0) or 0),
        "instructional_days": len(alloc.instructional_dates(cal["config"], apply_horizon=False)),
        "required_core": sum(r["core_periods"] for r in rows), "required_non_core": sum(r["non_core_periods"] for r in rows),
        "taught_periods": sum(r["taught_periods"] for r in rows), "done_topics": comp["done_topics"], "open_topics": comp["open_topics"],
        "remaining_required_core": sum(r["remaining_core"] for r in rows), "remaining_required_non_core": sum(r["remaining_non_core"] for r in rows),
        "window": window, "remaining_capacity": comp["pool"], "locked_topics": comp["locked_topics"], "locked_remaining_periods": comp["locked_remaining_periods"], "overcommitted_periods": comp["overcommitted_periods"], "unallocated_capacity": cap["topic_capacity"] - sum(r["core_periods"] + r["non_core_periods"] for r in rows), "core_shortfall": comp["core_shortfall"], "total_shortfall": comp["total_shortfall"], "fits": comp["fits"],
    }
    last = (await db.execute(select(PlanAuditEvent).filter_by(school_id=school_id, teacher_id=teacher_id, grade=grade, subject=subject,
                                                              category="calendar_recalculation").order_by(PlanAuditEvent.occurred_at.desc()).limit(1))).scalars().first()
    summary["last_recalculation"] = None if not last else {"at": last.occurred_at.isoformat(), "summary": last.summary, "previous": last.previous_value, "new": last.new_value, "reason": last.reason}
    check = alloc.validate_requirements(rows, cap["topic_capacity"])
    check["unallocated_topics"] = sum(1 for r in rows if r["core_periods"] + r["non_core_periods"] == 0)
    owner = (await db.execute(select(User.name).filter_by(id=teacher_id))).scalar()
    return {"school_id": school_id, "teacher_id": teacher_id, "teacher_name": owner, "academic_year": year, "grade": grade, "subject": subject,
            "calendar_version": cal["version"], "capacity": cap, "allocation": check, "topics": rows,
            "topic_count": len(topics), "configured_topic_count": len(cfgs), "summary": summary,
            "coverage": coverage_stats(r["coverage"] for r in rows)}


def coverage_stats(statuses: Iterable[str]) -> Dict[str, Any]:
    s = list(statuses)
    done, prog = s.count("done"), s.count("in_progress")
    total = len(s)
    return {"eligible": total, "done": done, "in_progress": prog, "not_done": total - done - prog,
            "percent": round(100 * done / total, 1) if total else 0.0}


def _require_owner(actor: User, school_id: str, teacher_id: str) -> None:
    if actor.role != "teacher" or actor.id != teacher_id:
        raise PlanError(403, "Only the owning teacher can change their own plan.")
    if actor.school_id and actor.school_id != school_id:
        raise PlanError(403, "Teacher does not belong to this school.")


async def save_requirements(db: AsyncSession, actor: User, school_id: str, teacher_id: str, year: str, grade: int,
                            subject: str, items: List[Dict], reason: Optional[str]) -> Dict:
    _require_owner(actor, school_id, teacher_id)
    _check_combo(grade, subject)
    await ensure_defaults(db, actor, school_id, teacher_id, year, grade, subject)
    await db.flush()
    key = dict(school_id=school_id, teacher_id=teacher_id, academic_year=year, grade=grade, subject=subject)
    current = {t.topic_key for t in await topics_for(db, grade, subject)}
    cfgs = {c.topic_key: c for c in (await db.execute(select(TeacherTopicConfig).filter_by(**key))).scalars().all() if c.topic_key in current}
    errors: List[str] = []
    proposed = {k: {"topic_key": k, "core_periods": c.core_periods, "non_core_periods": c.non_core_periods,
                    "independent_periods": c.independent_periods, "teaching_mode": c.teaching_mode,
                    "classification": c.classification} for k, c in cfgs.items()}
    for it in items:
        k = it["topic_key"]
        if k not in cfgs:
            errors.append(f"Unknown topic {k}.")
            continue
        cls = it.get("classification", proposed[k]["classification"])
        if cls not in CLASSIFICATIONS:
            errors.append(f"{k}: invalid classification.")
            continue
        independent = it.get("independent_periods", min(proposed[k]["independent_periods"], it["non_core_periods"]))
        mode = it.get("teaching_mode", proposed[k]["teaching_mode"])
        if not isinstance(independent, int) or isinstance(independent, bool) or independent < 0 or independent > it["non_core_periods"]:
            errors.append(f"{k}: independent periods must be between 0 and Non-Core periods.")
        if mode not in ("SHARED", "INDEPENDENT"):
            errors.append(f"{k}: teaching mode must be SHARED or INDEPENDENT.")
        proposed[k].update(core_periods=it["core_periods"], non_core_periods=it["non_core_periods"],
                           independent_periods=independent, teaching_mode=mode, classification=cls)
        nc, c = it["non_core_periods"], it["core_periods"]
        if isinstance(nc, int) and isinstance(c, int):
            if cls == "core" and nc:
                errors.append(f"{k}: a Core topic cannot carry Non-Core periods; mark it mixed.")
            if cls == "non_core" and c:
                errors.append(f"{k}: a Non-Core topic cannot carry Core periods; mark it mixed.")
    cal = await get_calendar(db, school_id, year)
    cap = alloc.capacity(alloc.available_periods(cal["config"], subject))
    check = alloc.validate_requirements(proposed.values(), cap["topic_capacity"])
    check["errors"] = errors + check["errors"]
    check["valid"] = not check["errors"]
    if not check["valid"]:
        # nothing is written, so an over-capacity configuration can never persist
        raise PlanError(422, {"message": "Requirements rejected.", **check})
    changed = []
    for it in items:
        c = cfgs[it["topic_key"]]
        new = proposed[it["topic_key"]]
        if (c.core_periods, c.non_core_periods, c.classification, c.independent_periods, c.teaching_mode) == (
                new["core_periods"], new["non_core_periods"], new["classification"], new["independent_periods"], new["teaching_mode"]):
            continue
        before = {"core_periods": c.core_periods, "non_core_periods": c.non_core_periods, "classification": c.classification,
                  "independent_periods": c.independent_periods, "teaching_mode": c.teaching_mode}
        after = {k: new[k] for k in before}
        c.core_periods, c.non_core_periods, c.classification = after["core_periods"], after["non_core_periods"], after["classification"]
        c.independent_periods, c.teaching_mode = after["independent_periods"], after["teaching_mode"]
        c.origin, c.version, c.updated_by = "teacher", c.version + 1, actor.id
        changed.append(c.topic_key)
        cat = "topic_classification" if before["classification"] != after["classification"] else "period_requirement"
        audit(db, actor, school_id, cat, f"{c.topic_key}: {before} -> {after}", teacher_id=teacher_id, grade=grade,
              subject=subject, topic_keys=[c.topic_key], previous=before, new=after, reason=reason)
    return {"changed": changed, "allocation": check}


async def set_coverage(db: AsyncSession, actor: User, school_id: str, teacher_id: str, year: str, grade: int,
                       subject: str, topic_key: str, status: str, reason: Optional[str], source: str = "MANUAL") -> Dict:
    _require_owner(actor, school_id, teacher_id)
    if status not in COVERAGE:
        raise PlanError(422, "Status must be done, in_progress or not_done.")
    if source not in COVERAGE_SOURCES:
        raise PlanError(422, "Source must be MANUAL or EXECUTION.")
    await ensure_defaults(db, actor, school_id, teacher_id, year, grade, subject)
    await db.flush()
    res = await db.execute(select(TeacherTopicCoverage).filter_by(
        school_id=school_id, teacher_id=teacher_id, academic_year=year, grade=grade, subject=subject, topic_key=topic_key))
    row = res.scalars().first()
    if not row:
        raise PlanError(404, "Topic is not part of this teacher's plan.")
    if row.status != status:
        before, before_src = row.status, row.source
        row.status, row.source, row.updated_by = status, source, actor.id
        audit(db, actor, school_id, "coverage_status", f"{topic_key}: {before} -> {status} ({source})", teacher_id=teacher_id,
              grade=grade, subject=subject, topic_keys=[topic_key], previous={"status": before, "source": before_src},
              new={"status": status, "source": source}, reason=reason)
    return {"topic_key": topic_key, "status": status, "source": row.source}
