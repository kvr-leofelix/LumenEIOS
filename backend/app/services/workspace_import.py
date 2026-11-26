"""One-time, repeatable import of legacy workspace-document coverage into teacher_topic_coverage.

Rules: a workspace coverage record is per school; the relational store is per teacher. A record is imported only when
exactly one teacher in that school holds a plan for the topic's class and subject. With several candidates the record is
reported as ambiguous and NOT imported (ownership is never guessed). An existing relational value other than the untouched
default is never overwritten, so re-running is a no-op. The workspace revisions are not modified.
"""
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.planning_workspace import PlanningWorkspaceRevision
from backend.app.models.teacher_planning import PlanAuditEvent, PlanTopic, TeacherTopicConfig, TeacherTopicCoverage
from backend.app.services.teacher_plan_service import audit

STATUS = {"DONE": "done", "IN_PROGRESS": "in_progress", "NOT_DONE": "not_done"}
SYSTEM = type("ImportActor", (), {"id": "system-import", "name": "Workspace import", "role": "system", "school_id": None})()


def topic_key_for(node_id: str) -> str:
    """Syllabus node CH-<book>-S<section> corresponds to crosswalk topic XW-<book>-S<section>."""
    return "XW-" + node_id[3:] if node_id.startswith("CH-") else node_id


async def import_workspace_coverage(db: AsyncSession, school_id: str, year: str = "2026-2027") -> Dict[str, Any]:
    latest = (await db.execute(select(PlanningWorkspaceRevision).filter_by(school_id=school_id)
                               .order_by(PlanningWorkspaceRevision.revision.desc()).limit(1))).scalars().first()
    report: Dict[str, Any] = {"imported": [], "skipped_existing": [], "ambiguous": [], "unknown_topic": [], "no_coverage": latest is None}
    if latest is None:
        return report
    for node_id, rec in (latest.state.get("coverage") or {}).items():
        status = STATUS.get(rec.get("status"))
        key = topic_key_for(node_id)
        topic = (await db.execute(select(PlanTopic).filter_by(topic_key=key))).scalars().first()
        if not status or not topic:
            report["unknown_topic"].append(node_id)
            continue
        owners: List[str] = [r[0] for r in (await db.execute(select(TeacherTopicConfig.teacher_id).filter_by(
            school_id=school_id, academic_year=year, grade=topic.grade, subject=topic.subject, topic_key=key).distinct())).all()]
        if len(owners) != 1:
            report["ambiguous"].append({"topic": key, "teachers": owners})
            continue
        row = (await db.execute(select(TeacherTopicCoverage).filter_by(
            school_id=school_id, teacher_id=owners[0], academic_year=year, topic_key=key))).scalars().first()
        events = (await db.execute(select(PlanAuditEvent).filter_by(
            school_id=school_id, teacher_id=owners[0], category="coverage_status"))).scalars().all()
        touched = any(key in (e.topic_keys or []) for e in events)
        if row is None or row.status != "not_done" or touched:
            report["skipped_existing"].append(key)  # the relational value wins; imports never overwrite
            continue
        before = row.status
        row.status, row.source, row.updated_by = status, rec.get("source", "MANUAL"), "system-import"
        audit(db, SYSTEM, school_id, "coverage_status", f"{key}: {before} -> {status} (imported)", teacher_id=owners[0],
              grade=topic.grade, subject=topic.subject, topic_keys=[key], previous={"status": before}, new={"status": status},
              reason=f"Imported once from workspace revision {latest.revision}")
        report["imported"].append(key)
    await db.commit()
    return report


async def import_workspace_requirements(db: AsyncSession, school_id: str, year: str = "2026-2027") -> Dict[str, Any]:
    """One-time import of APPROVED workspace classifications that carry period counts.

    Only a single unambiguous owner receives a value, only over an untouched demo default, and only when the result
    still fits the annual capacity. Everything else is reported and left alone. Imported rows keep origin
    'approved_import' so they are never confused with hypothetical demo defaults or with teacher edits.
    Proposed/rejected workspace records are never imported (they were never approved).
    """
    from backend.app.services import annual_allocation as alloc
    from backend.app.services.teacher_plan_service import get_calendar
    latest = (await db.execute(select(PlanningWorkspaceRevision).filter_by(school_id=school_id)
                               .order_by(PlanningWorkspaceRevision.revision.desc()).limit(1))).scalars().first()
    report: Dict[str, Any] = {"imported": [], "skipped_not_approved": [], "ambiguous": [], "skipped_existing": [],
                              "unknown_topic": [], "over_capacity": []}
    if latest is None:
        return report
    for node_id, rec in (latest.state.get("classifications") or {}).items():
        key = topic_key_for(node_id)
        core, non = rec.get("corePeriods"), rec.get("nonCorePeriods")
        if rec.get("status") != "APPROVED" or not isinstance(core, int) or not isinstance(non, int) or core < 0 or non < 0 or core + non < 1:
            report["skipped_not_approved"].append(node_id)
            continue
        topic = (await db.execute(select(PlanTopic).filter_by(topic_key=key))).scalars().first()
        if not topic:
            report["unknown_topic"].append(node_id)
            continue
        rows = (await db.execute(select(TeacherTopicConfig).filter_by(
            school_id=school_id, academic_year=year, grade=topic.grade, subject=topic.subject, topic_key=key))).scalars().all()
        if len(rows) != 1:
            report["ambiguous"].append({"topic": key, "teachers": [r.teacher_id for r in rows]})
            continue
        row = rows[0]
        if row.origin != "demo_default":
            report["skipped_existing"].append(key)
            continue
        siblings = (await db.execute(select(TeacherTopicConfig).filter_by(
            school_id=school_id, teacher_id=row.teacher_id, academic_year=year, grade=topic.grade, subject=topic.subject))).scalars().all()
        total = sum((core + non) if s.topic_key == key else s.core_periods + s.non_core_periods for s in siblings)
        cal = await get_calendar(db, school_id, year)
        if total > alloc.capacity(alloc.available_periods(cal["config"], topic.subject))["topic_capacity"]:
            report["over_capacity"].append(key)
            continue
        before = {"core_periods": row.core_periods, "non_core_periods": row.non_core_periods, "classification": row.classification}
        cls = "mixed" if core and non else ("core" if core else "non_core")
        row.core_periods, row.non_core_periods, row.classification = core, non, cls
        row.origin, row.version, row.updated_by = "approved_import", row.version + 1, "system-import"
        audit(db, SYSTEM, school_id, "period_requirement", f"{key}: imported approved workspace requirement {core}+{non}",
              teacher_id=row.teacher_id, grade=topic.grade, subject=topic.subject, topic_keys=[key], previous=before,
              new={"core_periods": core, "non_core_periods": non, "classification": cls},
              reason=f"Approved classification imported once from workspace revision {latest.revision}")
        report["imported"].append(key)
    await db.commit()
    return report


async def import_workspace_relationships(db: AsyncSession, school_id: str, year: str = "2026-2027") -> Dict[str, Any]:
    """One-time import of APPROVED workspace relationships.

    The owner is the single teacher in the school who holds BOTH topics in their plan; zero or several holders is reported as
    ambiguous and nothing is written. Imported links pass the same validation as teacher-created ones, never replace an
    existing row (including a link the teacher removed), carry origin 'approved_import', and are audited. Proposed or
    rejected workspace links were never approved and are not imported. Re-running is a no-op.
    """
    from backend.app.models.teacher_planning import TeacherTopicRelationship
    from backend.app.services import relationship_service as rels
    from backend.app.services.teacher_plan_service import PlanError
    latest = (await db.execute(select(PlanningWorkspaceRevision).filter_by(school_id=school_id)
                               .order_by(PlanningWorkspaceRevision.revision.desc()).limit(1))).scalars().first()
    report: Dict[str, Any] = {"imported": [], "skipped_not_approved": [], "ambiguous": [], "skipped_existing": [],
                              "unknown_topic": [], "invalid": []}
    if latest is None:
        return report
    for rel in latest.state.get("relationships") or []:
        rid = rel.get("id")
        if rel.get("status") != "APPROVED":
            report["skipped_not_approved"].append(rid)
            continue
        f, t = topic_key_for(rel.get("fromNodeId", "")), topic_key_for(rel.get("toNodeId", ""))
        found = {x[0] for x in (await db.execute(select(PlanTopic.topic_key).filter(PlanTopic.topic_key.in_([f, t])))).all()}
        if found != {f, t}:
            report["unknown_topic"].append(rid)
            continue
        by_teacher: Dict[str, set] = {}
        for tid, key in (await db.execute(select(TeacherTopicConfig.teacher_id, TeacherTopicConfig.topic_key).filter(
                TeacherTopicConfig.school_id == school_id, TeacherTopicConfig.academic_year == year,
                TeacherTopicConfig.topic_key.in_([f, t])))).all():
            by_teacher.setdefault(tid, set()).add(key)
        owners = [tid for tid, keys in by_teacher.items() if keys == {f, t}]
        if len(owners) != 1:
            report["ambiguous"].append({"relationship": rid, "teachers": owners})
            continue
        exists = (await db.execute(select(TeacherTopicRelationship.id).filter_by(
            school_id=school_id, teacher_id=owners[0], academic_year=year, topic_key=t, prerequisite_key=f))).first() or \
            (rel.get("type") == "CROSS_CURRICULAR" and (await db.execute(select(TeacherTopicRelationship.id).filter_by(
                school_id=school_id, teacher_id=owners[0], academic_year=year, topic_key=f, prerequisite_key=t))).first())
        if exists:
            report["skipped_existing"].append(rid)
            continue
        try:
            await rels.add_relationship(db, SYSTEM, school_id, owners[0], year, kind=rel.get("type", "PREREQUISITE"), from_key=f, to_key=t,
                                        explanation=rel.get("explanation", ""), evidence=rel.get("evidence", ""),
                                        shared_periods=rel.get("sharedPeriods", 0) or 0,
                                        lead_key=topic_key_for(rel["leadNodeId"]) if rel.get("leadNodeId") else None,
                                        reason=f"Approved relationship imported once from workspace revision {latest.revision}", origin="approved_import")
            report["imported"].append(rid)
        except PlanError as e:
            report["invalid"].append({"relationship": rid, "errors": (e.detail or {}).get("errors") if isinstance(e.detail, dict) else [str(e.detail)]})
    await db.commit()
    return report


async def import_workspace_losses(db: AsyncSession, school_id: str, year: str = "2026-2027") -> Dict[str, Any]:
    """One-time import of the workspace's effective (non-superseded) lost-period records into teacher_lost_periods.

    Owner: the recording teacher when they hold a plan for that class and subject (their own action is unambiguous
    evidence); otherwise the single teacher holding that plan; several candidates is ambiguous and nothing is written.
    Dates, periods and reasons are preserved as recorded. No topic is invented (topic_keys stay empty). Records without
    explicit period numbers are reported as incomplete. A (date, period) that already has a relational row is never
    touched. Invalid dates/periods under the school's calendar are reported, not forced. Superseded records are history
    and are not imported. Re-running is a no-op.
    """
    from datetime import datetime
    from backend.app.models.teacher_planning import TeacherLostPeriod
    from backend.app.services import lost_period_service as lost
    from backend.app.services.teacher_plan_service import PlanError
    latest = (await db.execute(select(PlanningWorkspaceRevision).filter_by(school_id=school_id)
                               .order_by(PlanningWorkspaceRevision.revision.desc()).limit(1))).scalars().first()
    report: Dict[str, Any] = {"imported": [], "skipped_existing": [], "ambiguous": [], "incomplete": [], "invalid": [], "superseded_ignored": 0}
    if latest is None:
        return report
    revision, state = latest.revision, latest.state  # plain values: a savepoint rollback must not expire `latest`
    for plan in state.get("plans") or []:
        records = plan.get("losses") or []
        superseded = {r.get("supersedes") for r in records if r.get("supersedes")}
        grade, subject = plan.get("grade"), plan.get("subject")
        holders = [r[0] for r in (await db.execute(select(TeacherTopicConfig.teacher_id).filter_by(
            school_id=school_id, academic_year=year, grade=grade, subject=subject).distinct())).all()]
        for rec in records:
            rid = rec.get("id")
            if rid in superseded or rec.get("supersedes"):
                report["superseded_ignored"] += 1
                continue
            periods = rec.get("periods")
            if not periods:
                report["incomplete"].append({"record": rid, "reason": "no explicit period numbers"})
                continue
            by = (rec.get("recordedBy") or {})
            owner = by.get("id") if by.get("role") == "teacher" and by.get("id") in holders else (holders[0] if len(holders) == 1 else None)
            if owner is None:
                report["ambiguous"].append({"record": rid, "teachers": holders})
                continue
            existing = {r.period_number for r in (await db.execute(select(TeacherLostPeriod).filter_by(
                school_id=school_id, teacher_id=owner, academic_year=year, grade=grade, subject=subject, lost_date=rec["date"]))).scalars().all()}
            if existing & set(periods):
                report["skipped_existing"].append(rid)
                continue
            try:
                when = datetime.fromisoformat(rec["recordedAt"].replace("Z", "+00:00")).replace(tzinfo=None) if rec.get("recordedAt") else None
                actor = type("Importer", (), {"id": "system-import", "name": "Workspace import", "role": "system", "school_id": None})()
                async with db.begin_nested():  # a rejected record rolls back alone; earlier imports are kept
                    await lost.record_batch(db, actor, school_id, owner, year, grade, subject, [{"date": rec["date"], "periods": list(periods)}], [],
                                            rec.get("reason", ""), rec.get("note") or None, batch_id=rec.get("batchId"),
                                            origin_note=f"Imported once from workspace revision {revision}", created_at=when,
                                            recorded_by=by.get("id") or "system-import", skip_owner_check=True, importing=True)
                from backend.app.services.plan_service import relink_lost_rows
                await relink_lost_rows(db, school_id, owner, year, grade, subject)
                report["imported"].append(rid)
            except PlanError as e:
                report["invalid"].append({"record": rid, "error": str(e.detail)})
    await db.commit()
    return report


async def import_workspace_plans(db: AsyncSession, school_id: str, year: str = "2026-2027") -> Dict[str, Any]:
    """One-time import of workspace plans, with their schedule versions, proposals, execution and evidence, kept exactly as recorded.

    Owner: the teacher who created the plan when they hold a plan for that class and subject; otherwise the single holder;
    several candidates is ambiguous and nothing is written. No approval, proposal or execution is invented or altered
    (statuses, reviewers, timestamps and notes are copied). A plan whose stored schedules fail the structural checks, or an
    APPROVED plan that would collide with an owner's existing APPROVED plan for the same class and subject, is reported
    and skipped. An existing plan id is never touched. Lost periods are imported separately (import_workspace_losses).
    """
    from backend.app.models.teacher_planning import (
        TeacherPlan, TeacherPlanEvidence, TeacherPlanExecution, TeacherPlanProposal, TeacherPlanVersion,
    )
    from backend.app.services.schedule_validation import validate_schedule
    latest = (await db.execute(select(PlanningWorkspaceRevision).filter_by(school_id=school_id)
                               .order_by(PlanningWorkspaceRevision.revision.desc()).limit(1))).scalars().first()
    report: Dict[str, Any] = {"imported": [], "skipped_existing": [], "ambiguous": [], "invalid": [], "conflicts": []}
    if latest is None:
        return report
    revision, state = latest.revision, latest.state
    for plan in state.get("plans") or []:
        pid, grade, subject = plan.get("id"), plan.get("grade"), plan.get("subject")
        if (await db.execute(select(TeacherPlan.id).filter_by(id=pid))).first():
            report["skipped_existing"].append(pid)
            continue
        holders = [r[0] for r in (await db.execute(select(TeacherTopicConfig.teacher_id).filter_by(
            school_id=school_id, academic_year=year, grade=grade, subject=subject).distinct())).all()]
        by = plan.get("createdBy") or {}
        owner = by.get("id") if by.get("role") == "teacher" and by.get("id") in holders else (holders[0] if len(holders) == 1 else None)
        if owner is None:
            report["ambiguous"].append({"plan": pid, "teachers": holders})
            continue
        problems: List[str] = []
        prev = None
        for v in plan.get("versions") or []:
            problems += validate_schedule(v.get("lessons"), v.get("config"), subject, None, f"Plan {pid} version {v.get('version')}")
            prev = v
        if not isinstance(plan.get("draft"), dict) or not isinstance(plan.get("config"), dict):
            problems.append(f"Plan {pid}: draft or configuration missing.")
        if problems:
            report["invalid"].append({"plan": pid, "errors": problems[:5]})
            continue
        if plan.get("status") == "APPROVED" and (await db.execute(select(TeacherPlan.id).filter_by(
                school_id=school_id, teacher_id=owner, academic_year=year, grade=grade, subject=subject, status="APPROVED"))).first():
            report["conflicts"].append({"plan": pid, "reason": "owner already has an approved plan for this class and subject"})
            continue
        async with db.begin_nested():
            db.add(TeacherPlan(id=pid, school_id=school_id, teacher_id=owner, academic_year=year, grade=grade, subject=subject, status=plan.get("status", "DRAFT"),
                               dataset_id=plan.get("datasetId", ""), dataset_label=plan.get("datasetLabel", ""), dataset_kind=plan.get("datasetKind", ""),
                               config=plan["config"], estimates=plan.get("estimates") or {}, draft=plan["draft"], created_by=by or {"id": owner, "name": "", "role": "teacher"},
                               review=plan.get("review"), superseded_by=plan.get("supersededBy"), origin="workspace_import"))
            await db.flush()
            for v in plan.get("versions") or []:
                db.add(TeacherPlanVersion(plan_id=pid, version=v["version"], lessons=v["lessons"], metrics=v.get("metrics") or {}, conflicts=v.get("conflicts") or [],
                                          config=v["config"], approved_by=v.get("approvedBy") or {}, approved_at=v.get("approvedAt", ""), reason=v.get("reason", ""),
                                          proposal_id=v.get("proposalId"), lost_slots=v.get("lostSlots") or []))
            for i, x in enumerate(plan.get("proposals") or []):
                payload = {k: val for k, val in x.items() if k not in ("id", "status", "review", "createdBy", "createdAt", "baseVersion", "trigger")}
                db.add(TeacherPlanProposal(id=x["id"], plan_id=pid, base_version=x.get("baseVersion", 0), status=x.get("status", "PENDING"), trigger=x.get("trigger") or {},
                                           created_by=x.get("createdBy") or {}, created_at=x.get("createdAt", ""), payload=payload, review=x.get("review"), sequence=i + 1))
            for i, e in enumerate(plan.get("execution") or []):
                db.add(TeacherPlanExecution(id=e["id"], plan_id=pid, node_key=e["nodeId"], event_date=e["date"], status=e["status"], periods_taught=e.get("periodsTaught", 0),
                                            note=e.get("note", ""), recorded_by=e.get("recordedBy") or {}, recorded_at=e.get("recordedAt", ""), supersedes=e.get("supersedes"),
                                            schedule_version=e.get("scheduleVersion", 1), sequence=i + 1))
            for i, e in enumerate(plan.get("evidence") or []):
                db.add(TeacherPlanEvidence(id=e["id"], plan_id=pid, node_key=e["nodeId"], kind=e.get("kind", "ASSESSMENT"), reference=e.get("reference", ""),
                                           result=e.get("result", ""), recorded_by=e.get("recordedBy") or {}, recorded_at=e.get("recordedAt", ""), sequence=i + 1))
            # Lost periods that an already-approved version absorbed stay immutable, as they were in the workspace.
            from backend.app.services.plan_service import relink_lost_rows
            await relink_lost_rows(db, school_id, owner, year, grade, subject)
            audit(db, SYSTEM, school_id, "schedule_change", f"Plan {pid} imported from the workspace document ({plan.get('status')}, {len(plan.get('versions') or [])} version(s))",
                  teacher_id=owner, grade=grade, subject=subject, new={"plan_id": pid, "status": plan.get("status"), "versions": len(plan.get("versions") or [])},
                  reason=f"Imported once from workspace revision {revision}; nothing was re-approved or altered", status="imported")
        report["imported"].append(pid)
    await db.commit()
    return report


async def import_workspace_calendar(db: AsyncSession, school_id: str, year: str = "2026-2027") -> Dict[str, Any]:
    """One-time import of the workspace's Academic Configuration as calendar version 1. A school-level setting has no
    ownership ambiguity. Never replaces an existing calendar version; an invalid stored configuration is reported, not forced.
    The workspace's own configuration history stays in its revisions."""
    from backend.app.models.teacher_planning import SchoolPlanCalendar
    from backend.app.services import calendar_service as cal
    latest = (await db.execute(select(PlanningWorkspaceRevision).filter_by(school_id=school_id)
                               .order_by(PlanningWorkspaceRevision.revision.desc()).limit(1))).scalars().first()
    report: Dict[str, Any] = {"imported": [], "skipped_existing": [], "invalid": [], "no_configuration": False}
    if latest is None or not (latest.state or {}).get("configHistory"):
        report["no_configuration"] = True  # the workspace never saved a configuration: the default calendar applies
        return report
    if (await db.execute(select(SchoolPlanCalendar.id).filter_by(school_id=school_id, academic_year=year))).first():
        report["skipped_existing"].append("calendar")
        return report
    config, revision = latest.state["config"], latest.revision
    problems = cal.validate_config(config)
    if problems or config.get("year") != year:
        report["invalid"].append({"errors": problems or [f"configuration year {config.get('year')} is not {year}"]})
        return report
    db.add(SchoolPlanCalendar(school_id=school_id, academic_year=year, version=1, config=config, reason=f"Imported once from workspace revision {revision}", created_by="system-import"))
    audit(db, SYSTEM, school_id, "calendar_change", "Calendar version 1 imported from the workspace document",
          new={"version": 1, "capacity": cal.capacity_by_subject(config)}, reason=f"Imported once from workspace revision {revision}", status="imported")
    report["imported"].append("calendar")
    await db.commit()
    return report
