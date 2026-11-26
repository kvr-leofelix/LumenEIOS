"""Teacher plans, schedule versions, recovery proposals, execution and evidence (relational, teacher-scoped).

The deterministic scheduling and recovery engine still produces the schedules and proposals (src/lib/planning/*); this
service is where they are validated, authorised, versioned and kept:
  * only the owning teacher creates a plan, records execution/evidence and loses periods;
  * only an Admin/Principal approves or rejects a draft or a recovery proposal;
  * approved schedule versions are built HERE from the stored draft/proposal, never accepted from the client, and are append-only;
  * a proposal never becomes a schedule by being generated, a stale proposal cannot be approved, a rejected one changes nothing;
  * every step is a plan_audit_events row (previous/new values, reason, schedule version, proposal id).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import User
from backend.app.models.teacher_planning import (
    TeacherLostPeriod, TeacherPlan, TeacherPlanEvidence, TeacherPlanExecution, TeacherPlanProposal, TeacherPlanVersion,
)
from backend.app.services import annual_allocation as alloc
from backend.app.services.schedule_validation import validate_schedule
from backend.app.services.teacher_plan_service import PlanError, _check_combo, audit

REVIEWERS = {"admin", "principal"}
EXEC_STATUSES = {"TAUGHT", "PARTIAL", "HOMEWORK", "DEFERRED", "HOMEWORK_COMPLETED"}
BLOCKING_DRAFT_CONFLICTS = {"REQUIREMENT_MISSING", "PREREQUISITE_ORDER"}
PROPOSAL_TRIGGERS = {"EXECUTION", "CONFIG_CHANGE", "LOST_PERIODS"}
MIN_NOTE = 5


def actor_json(u: User) -> Dict[str, str]:
    return {"id": u.id, "name": u.name, "role": u.role}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _is_owner(user: User, plan: TeacherPlan) -> bool:
    return user.role == "teacher" and user.id == plan.teacher_id


def _require_owner(user: User, plan: TeacherPlan) -> None:
    if not _is_owner(user, plan):
        raise PlanError(403, "Only the teacher who owns this plan can do that.")


def _require_reviewer(user: User) -> None:
    if user.role not in REVIEWERS:
        raise PlanError(403, "Only an Admin or Principal can approve or reject.")


async def get_plan(db: AsyncSession, school_id: str, plan_id: str) -> TeacherPlan:
    plan = (await db.execute(select(TeacherPlan).filter_by(id=plan_id, school_id=school_id))).scalars().first()
    if not plan:
        raise PlanError(404, "Plan not found.")
    return plan


async def versions_of(db: AsyncSession, plan_id: str) -> List[TeacherPlanVersion]:
    return list((await db.execute(select(TeacherPlanVersion).filter_by(plan_id=plan_id).order_by(TeacherPlanVersion.version))).scalars().all())


async def _next_seq(db: AsyncSession, model, plan_id: str) -> int:
    return ((await db.execute(select(func.max(model.sequence)).filter_by(plan_id=plan_id))).scalar() or 0) + 1


def version_dict(v: TeacherPlanVersion) -> Dict[str, Any]:
    return {"version": v.version, "lessons": v.lessons, "metrics": v.metrics, "conflicts": v.conflicts, "config": v.config,
            "approvedBy": v.approved_by, "approvedAt": v.approved_at, "reason": v.reason, "proposalId": v.proposal_id, "lostSlots": v.lost_slots or []}


def proposal_dict(x: TeacherPlanProposal) -> Dict[str, Any]:
    out = {**(x.payload or {}), "id": x.id, "createdAt": x.created_at, "createdBy": x.created_by, "trigger": x.trigger, "baseVersion": x.base_version, "status": x.status}
    if x.review:
        out["review"] = x.review
    return out


def execution_dict(e: TeacherPlanExecution) -> Dict[str, Any]:
    return {"id": e.id, "nodeId": e.node_key, "date": e.event_date, "status": e.status, "periodsTaught": e.periods_taught, "note": e.note or "",
            "recordedBy": e.recorded_by, "recordedAt": e.recorded_at, "supersedes": e.supersedes, "scheduleVersion": e.schedule_version}


def evidence_dict(e: TeacherPlanEvidence) -> Dict[str, Any]:
    return {"id": e.id, "nodeId": e.node_key, "kind": e.kind, "reference": e.reference, "result": e.result, "recordedBy": e.recorded_by, "recordedAt": e.recorded_at}


def loss_records(rows: List[TeacherLostPeriod], grade: int, subject: str) -> List[Dict[str, Any]]:
    """Active lost-period rows in the engine's record shape (one per date/batch/reason). Withdrawn rows are not losses."""
    groups: Dict[tuple, List[TeacherLostPeriod]] = {}
    for r in rows:
        if r.status == "active" and r.grade == grade and r.subject == subject:
            groups.setdefault((r.lost_date, r.batch_id or r.id, r.reason_code), []).append(r)
    out = []
    for g in groups.values():
        periods = sorted(r.period_number for r in g)
        out.append({"id": f"{g[0].batch_id or g[0].id}:{g[0].lost_date}", "date": g[0].lost_date, "periodsLost": len(periods), "periods": periods,
                    "reason": g[0].reason_code, "note": g[0].notes or "", "recordedBy": {"id": g[0].recorded_by, "name": "", "role": "teacher"},
                    "recordedAt": g[0].created_at.isoformat() if g[0].created_at else "", "supersedes": None,
                    **({"batchId": g[0].batch_id} if g[0].batch_id else {})})
    return sorted(out, key=lambda r: (r["date"], r["recordedAt"]))


async def plan_dict(db: AsyncSession, plan: TeacherPlan) -> Dict[str, Any]:
    versions = await versions_of(db, plan.id)
    props = (await db.execute(select(TeacherPlanProposal).filter_by(plan_id=plan.id).order_by(TeacherPlanProposal.sequence))).scalars().all()
    execs = (await db.execute(select(TeacherPlanExecution).filter_by(plan_id=plan.id).order_by(TeacherPlanExecution.sequence))).scalars().all()
    evid = (await db.execute(select(TeacherPlanEvidence).filter_by(plan_id=plan.id).order_by(TeacherPlanEvidence.sequence))).scalars().all()
    lost = (await db.execute(select(TeacherLostPeriod).filter_by(school_id=plan.school_id, teacher_id=plan.teacher_id, academic_year=plan.academic_year))).scalars().all()
    out: Dict[str, Any] = {
        "id": plan.id, "teacherId": plan.teacher_id, "schoolId": plan.school_id, "grade": plan.grade, "subject": plan.subject,
        "datasetId": plan.dataset_id, "datasetLabel": plan.dataset_label, "datasetKind": plan.dataset_kind, "createdBy": plan.created_by,
        "createdAt": plan.created_at.isoformat() if plan.created_at else "", "config": plan.config, "estimates": plan.estimates, "status": plan.status,
        "draft": plan.draft, "versions": [version_dict(v) for v in versions], "execution": [execution_dict(e) for e in execs],
        "evidence": [evidence_dict(e) for e in evid], "proposals": [proposal_dict(x) for x in props], "losses": loss_records(list(lost), plan.grade, plan.subject),
    }
    if plan.review:
        out["review"] = plan.review
    if plan.superseded_by:
        out["supersededBy"] = plan.superseded_by
    return out


async def list_plans(db: AsyncSession, school_id: str, user: User, year: str, teacher_id: Optional[str] = None) -> List[Dict[str, Any]]:
    q = select(TeacherPlan).filter_by(school_id=school_id, academic_year=year)
    if user.role == "teacher":
        q = q.filter_by(teacher_id=user.id)
    elif user.role in REVIEWERS:
        if teacher_id:
            q = q.filter_by(teacher_id=teacher_id)
    else:
        raise PlanError(403, "Not permitted.")
    rows = (await db.execute(q.order_by(TeacherPlan.created_at, TeacherPlan.id))).scalars().all()
    return [await plan_dict(db, p) for p in rows]


# ----------------------------------------------------------------------------------------------- draft lifecycle
async def create_draft(db: AsyncSession, user: User, school_id: str, teacher_id: str, year: str, body: Dict[str, Any]) -> Dict[str, Any]:
    if user.role != "teacher" or user.id != teacher_id:
        raise PlanError(403, "Only the owning teacher can create their plan.")
    grade, subject = body.get("grade"), body.get("subject")
    _check_combo(grade, subject)
    draft, config = body.get("draft"), body.get("config")
    if not isinstance(draft, dict) or not isinstance(draft.get("lessons"), list) or not isinstance(config, dict):
        raise PlanError(422, "A draft needs a generated schedule and the academic configuration it was built against.")
    for f in ("id", "datasetId", "datasetLabel", "datasetKind"):
        if not isinstance(body.get(f), str) or not body[f]:
            raise PlanError(422, f"Missing {f}.")
    if (await db.execute(select(TeacherPlan.id).filter_by(id=body["id"]))).first():
        raise PlanError(409, "A plan with this id already exists.")
    problems = validate_schedule(draft["lessons"], config, subject, None, "Draft schedule")
    if problems:
        raise PlanError(422, {"message": "Draft schedule rejected.", "errors": problems})
    plan = TeacherPlan(id=body["id"], school_id=school_id, teacher_id=teacher_id, academic_year=year, grade=grade, subject=subject, status="DRAFT",
                       dataset_id=body["datasetId"], dataset_label=body["datasetLabel"], dataset_kind=body["datasetKind"], config=config,
                       estimates=body.get("estimates") or {}, draft=draft, created_by=actor_json(user), origin="teacher")
    db.add(plan)
    await db.flush()
    audit(db, user, school_id, "plan_draft", f"Draft schedule submitted for Class {grade} {subject} ({len(draft['lessons'])} units)", teacher_id=teacher_id,
          grade=grade, subject=subject, topic_keys=[str(l.get("nodeId")) for l in draft["lessons"]],
          new={"plan_id": plan.id, "status": "DRAFT", "metrics": draft.get("metrics")}, related_proposal_id=None, status="pending")
    return {"id": plan.id}


async def _supersede_pending(db: AsyncSession, plan_id: str) -> None:
    for x in (await db.execute(select(TeacherPlanProposal).filter_by(plan_id=plan_id, status="PENDING"))).scalars().all():
        x.status = "SUPERSEDED"


async def review_plan(db: AsyncSession, user: User, school_id: str, plan_id: str, decision: str, note: str) -> Dict[str, Any]:
    _require_reviewer(user)
    plan = await get_plan(db, school_id, plan_id)
    note = (note or "").strip()
    if plan.status != "DRAFT":
        raise PlanError(409, "Only a draft plan can be approved or rejected.")
    at = now_iso()
    review = {"by": actor_json(user), "at": at, "note": note, "decision": decision}
    if decision == "REJECTED":
        if len(note) < MIN_NOTE:
            raise PlanError(422, "A rejection reason is required.")
        plan.status, plan.review = "REJECTED", review
        audit(db, user, school_id, "plan_rejection", f"Draft schedule rejected for Class {plan.grade} {plan.subject}", teacher_id=plan.teacher_id,
              grade=plan.grade, subject=plan.subject, previous={"status": "DRAFT"}, new={"status": "REJECTED", "plan_id": plan.id}, reason=note, status="rejected")
        return {"id": plan.id, "status": plan.status}
    if decision != "APPROVED":
        raise PlanError(422, "Decision must be APPROVED or REJECTED.")
    draft = plan.draft
    if not draft.get("lessons"):
        raise PlanError(422, "A plan without syllabus units cannot be approved.")
    if any(c.get("code") in BLOCKING_DRAFT_CONFLICTS for c in draft.get("conflicts") or []):
        raise PlanError(422, "Resolve missing approved requirements and prerequisite order before approval.")
    problems = validate_schedule(draft["lessons"], plan.config, plan.subject, None, "Schedule version 1")
    if problems:
        raise PlanError(422, {"message": "Schedule rejected.", "errors": problems})
    previous = (await db.execute(select(TeacherPlan).filter_by(
        school_id=school_id, teacher_id=plan.teacher_id, academic_year=plan.academic_year, grade=plan.grade, subject=plan.subject, status="APPROVED"))).scalars().all()
    for old in previous:  # preserved, with its execution history, as SUPERSEDED
        old.status, old.superseded_by = "SUPERSEDED", plan.id
        await _supersede_pending(db, old.id)
    db.add(TeacherPlanVersion(plan_id=plan.id, version=1, lessons=draft["lessons"], metrics=draft.get("metrics") or {}, conflicts=draft.get("conflicts") or [],
                              config=plan.config, approved_by=actor_json(user), approved_at=at, reason=note or "Initial schedule approved", proposal_id=None, lost_slots=[]))
    plan.status, plan.review = "APPROVED", review
    await db.flush()
    ev = audit(db, user, school_id, "plan_approval", f"Schedule approved for Class {plan.grade} {plan.subject} (version 1)", teacher_id=plan.teacher_id,
               grade=plan.grade, subject=plan.subject, previous={"status": "DRAFT", "superseded_plans": [o.id for o in previous]},
               new={"status": "APPROVED", "plan_id": plan.id, "version": 1}, reason=note or None, schedule_version=1, status="approved")
    audit(db, user, school_id, "schedule_version", f"Schedule version 1 created for Class {plan.grade} {plan.subject}", teacher_id=plan.teacher_id,
          grade=plan.grade, subject=plan.subject, previous=None, new={"version": 1, "units": len(draft["lessons"]), "metrics": draft.get("metrics")},
          reason=note or "Initial schedule approved", schedule_version=1, related_event_id=ev.id)
    return {"id": plan.id, "status": plan.status, "version": 1}


# ----------------------------------------------------------------------------------------------- execution / evidence
def _effective(events: List[TeacherPlanExecution], node: Optional[str] = None) -> List[TeacherPlanExecution]:
    superseded = {e.supersedes for e in events if e.supersedes}
    return [e for e in events if e.id not in superseded and (node is None or e.node_key == node)]


async def record_execution(db: AsyncSession, user: User, school_id: str, plan_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    plan = await get_plan(db, school_id, plan_id)
    _require_owner(user, plan)
    if plan.status != "APPROVED":
        raise PlanError(409, "Execution can only be recorded against an approved plan.")
    versions = await versions_of(db, plan.id)
    current = versions[-1]
    node, date, status = body.get("nodeId"), body.get("date"), body.get("status")
    if node not in {l.get("nodeId") for l in current.lessons}:
        raise PlanError(422, "This unit is not part of the approved schedule.")
    if status not in EXEC_STATUSES:
        raise PlanError(422, f"Status must be one of {sorted(EXEC_STATUSES)}.")
    if date not in set(alloc.instructional_dates(plan.config, apply_horizon=False)):
        raise PlanError(422, f"{date} is not an instructional day in this plan's academic calendar.")
    periods = body.get("periodsTaught", 0)
    if not isinstance(periods, int) or isinstance(periods, bool) or periods < 0:
        raise PlanError(422, "Periods taught must be a whole number.")
    events = list((await db.execute(select(TeacherPlanExecution).filter_by(plan_id=plan.id))).scalars().all())
    sup = body.get("supersedes")
    if sup:
        target = next((e for e in events if e.id == sup), None)
        if not target or target.node_key != node or any(e.supersedes == sup for e in events):
            raise PlanError(422, "A correction must supersede a current record of the same unit.")
    if (await db.execute(select(TeacherPlanExecution.id).filter_by(id=body.get("id")))).first():
        raise PlanError(409, "This execution record already exists.")
    ev = TeacherPlanExecution(id=body["id"], plan_id=plan.id, node_key=node, event_date=date, status=status, periods_taught=periods, note=(body.get("note") or "").strip(),
                              recorded_by=actor_json(user), recorded_at=now_iso(), supersedes=sup, schedule_version=current.version, sequence=await _next_seq(db, TeacherPlanExecution, plan.id))
    db.add(ev)
    await db.flush()
    audit(db, user, school_id, "teaching_execution", f"{status} recorded for {node} on {date}", teacher_id=plan.teacher_id, grade=plan.grade, subject=plan.subject,
          topic_keys=[node], previous={"supersedes": sup} if sup else None, new={"status": status, "date": date, "periods_taught": periods, "plan_id": plan.id},
          reason=ev.note or None, schedule_version=current.version, related_event_id=None)
    return execution_dict(ev)


async def record_evidence(db: AsyncSession, user: User, school_id: str, plan_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    plan = await get_plan(db, school_id, plan_id)
    _require_owner(user, plan)
    if plan.status != "APPROVED":
        raise PlanError(409, "Evidence can only be recorded against an approved plan.")
    current = (await versions_of(db, plan.id))[-1]
    node = body.get("nodeId")
    if node not in {l.get("nodeId") for l in current.lessons}:
        raise PlanError(422, "Unit not found in the approved schedule.")
    events = list((await db.execute(select(TeacherPlanExecution).filter_by(plan_id=plan.id))).scalars().all())
    if not any(e.status == "TAUGHT" for e in _effective(events, node) if e.status != "HOMEWORK_COMPLETED"):
        raise PlanError(422, "Evidence of mastery can only be recorded after the unit has been taught; homework alone is not sufficient.")
    if body.get("kind") not in ("ASSESSMENT", "OBSERVATION"):
        raise PlanError(422, "Evidence kind must be ASSESSMENT or OBSERVATION.")
    if len((body.get("reference") or "").strip()) < 3:
        raise PlanError(422, "An assessment or evidence reference is required.")
    if not (body.get("result") or "").strip():
        raise PlanError(422, "Record the assessment result or observation.")
    if (await db.execute(select(TeacherPlanEvidence.id).filter_by(id=body.get("id")))).first():
        raise PlanError(409, "This evidence record already exists.")
    ev = TeacherPlanEvidence(id=body["id"], plan_id=plan.id, node_key=node, kind=body["kind"], reference=body["reference"].strip(), result=body["result"].strip(),
                             recorded_by=actor_json(user), recorded_at=now_iso(), sequence=await _next_seq(db, TeacherPlanEvidence, plan.id))
    db.add(ev)
    await db.flush()
    audit(db, user, school_id, "teaching_execution", f"Assessment evidence recorded for {node}", teacher_id=plan.teacher_id, grade=plan.grade, subject=plan.subject,
          topic_keys=[node], new={"kind": ev.kind, "reference": ev.reference, "plan_id": plan.id}, schedule_version=current.version)
    return evidence_dict(ev)


# ----------------------------------------------------------------------------------------------- proposals
async def create_proposal(db: AsyncSession, user: User, school_id: str, plan_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    plan = await get_plan(db, school_id, plan_id)
    if not (_is_owner(user, plan) or user.role in REVIEWERS):
        raise PlanError(403, "Only the plan's teacher or an Admin/Principal can propose a schedule change.")
    if plan.status != "APPROVED":
        raise PlanError(409, "Recovery can only be proposed for an approved plan.")
    versions = await versions_of(db, plan.id)
    current = versions[-1]
    if body.get("baseVersion") != current.version:
        raise PlanError(409, "The approved schedule changed after this proposal was generated. Regenerate the proposal.")
    if not isinstance(body.get("id"), str) or not body["id"]:
        raise PlanError(422, "Missing proposal id.")
    if (await db.execute(select(TeacherPlanProposal.id).filter_by(id=body["id"]))).first():
        raise PlanError(409, "A proposal with this id already exists.")
    trig = body.get("trigger") or {}
    if trig.get("kind") not in PROPOSAL_TRIGGERS:
        raise PlanError(422, "Unknown proposal trigger.")
    problems = validate_schedule(body.get("lessons"), body.get("config"), plan.subject, current.lessons, f"Recovery proposal {body['id']}")
    if problems:
        raise PlanError(422, {"message": "Proposal rejected.", "errors": problems})
    await _supersede_pending(db, plan.id)  # a newer proposal replaces any pending one; the old one is kept as SUPERSEDED
    payload = {k: v for k, v in body.items() if k not in ("id", "status", "review", "createdBy", "createdAt", "baseVersion", "trigger")}
    seq = await _next_seq(db, TeacherPlanProposal, plan.id)
    prop = TeacherPlanProposal(id=body["id"], plan_id=plan.id, base_version=current.version, status="PENDING", trigger=trig, created_by=actor_json(user),
                               created_at=now_iso(), payload=payload, sequence=seq)
    db.add(prop)
    await db.flush()
    audit(db, user, school_id, "recovery_proposal", f"Recovery proposed for Class {plan.grade} {plan.subject} ({trig.get('kind')})", teacher_id=plan.teacher_id,
          grade=plan.grade, subject=plan.subject, topic_keys=[c.get("nodeId") for c in payload.get("changes", []) if isinstance(c, dict)],
          previous={"version": current.version, "plan_id": plan.id}, new={"proposal_id": prop.id, "base_version": current.version, "changes": payload.get("changes"),
                                                                       "lost_slots": payload.get("lostSlots"), "metrics": payload.get("metrics")},
          reason="; ".join(payload.get("explanation") or [])[:500] or None, schedule_version=current.version, related_proposal_id=prop.id, status="pending")
    return proposal_dict(prop)


async def supersede_pending(db: AsyncSession, user: User, school_id: str, plan_id: str, reason: str) -> Dict[str, Any]:
    plan = await get_plan(db, school_id, plan_id)
    if not (_is_owner(user, plan) or user.role in REVIEWERS):
        raise PlanError(403, "Not permitted.")
    pending = (await db.execute(select(TeacherPlanProposal).filter_by(plan_id=plan.id, status="PENDING"))).scalars().all()
    for x in pending:
        x.status = "SUPERSEDED"
        audit(db, user, school_id, "recovery_proposal", f"Proposal {x.id} superseded", teacher_id=plan.teacher_id, grade=plan.grade, subject=plan.subject,
              previous={"status": "PENDING"}, new={"status": "SUPERSEDED"}, reason=reason or "Nothing remains to change after the latest records", related_proposal_id=x.id, status="superseded")
    return {"superseded": [x.id for x in pending]}


async def review_proposal(db: AsyncSession, user: User, school_id: str, plan_id: str, proposal_id: str, decision: str, note: str) -> Dict[str, Any]:
    _require_reviewer(user)
    plan = await get_plan(db, school_id, plan_id)
    prop = (await db.execute(select(TeacherPlanProposal).filter_by(id=proposal_id, plan_id=plan.id))).scalars().first()
    if not prop:
        raise PlanError(404, "Proposal not found.")
    if prop.status != "PENDING":
        raise PlanError(409, "Only a pending proposal can be approved or rejected.")
    note = (note or "").strip()
    at = now_iso()
    versions = await versions_of(db, plan.id)
    current = versions[-1]
    if decision == "REJECTED":
        if len(note) < MIN_NOTE:
            raise PlanError(422, "A rejection reason is required.")
        prop.status, prop.review = "REJECTED", {"by": actor_json(user), "at": at, "note": note}
        audit(db, user, school_id, "recovery_rejection", f"Recovery proposal rejected for Class {plan.grade} {plan.subject}; the approved schedule is unchanged",
              teacher_id=plan.teacher_id, grade=plan.grade, subject=plan.subject, previous={"status": "PENDING", "version": current.version},
              new={"status": "REJECTED", "version": current.version}, reason=note, schedule_version=current.version, related_proposal_id=prop.id, status="rejected")
        return {"id": prop.id, "status": prop.status}
    if decision != "APPROVED":
        raise PlanError(422, "Decision must be APPROVED or REJECTED.")
    if plan.status != "APPROVED":
        raise PlanError(409, "The plan is no longer the approved plan.")
    if prop.base_version != current.version:
        raise PlanError(409, "The approved schedule changed after this proposal was generated. Regenerate the proposal.")
    payload = prop.payload
    problems = validate_schedule(payload.get("lessons"), payload.get("config"), plan.subject, current.lessons, f"Schedule version {current.version + 1}")
    if problems:
        raise PlanError(422, {"message": "Schedule rejected.", "errors": problems})
    kind = (prop.trigger or {}).get("kind")
    reason = note or ("Recalculated for updated Academic Configuration" if kind == "CONFIG_CHANGE" else "Lost-period recovery approved" if kind == "LOST_PERIODS" else "Recovery proposal approved")
    new_no = current.version + 1
    lost_slots = payload.get("lostSlots") if payload.get("lostSlots") is not None else (current.lost_slots or [])
    db.add(TeacherPlanVersion(plan_id=plan.id, version=new_no, lessons=payload["lessons"], metrics=payload.get("metrics") or {}, conflicts=payload.get("conflicts") or [],
                              config=payload["config"], approved_by=actor_json(user), approved_at=at, reason=reason, proposal_id=prop.id, lost_slots=lost_slots))
    prop.status, prop.review = "APPROVED", {"by": actor_json(user), "at": at, "note": note}
    plan.config = payload["config"]
    linked = await _link_lost(db, plan, lost_slots, new_no)
    await db.flush()
    ev = audit(db, user, school_id, "recovery_approval", f"Recovery proposal approved for Class {plan.grade} {plan.subject} (version {new_no})", teacher_id=plan.teacher_id,
               grade=plan.grade, subject=plan.subject, previous={"version": current.version, "status": "PENDING"},
               new={"version": new_no, "status": "APPROVED", "changes": payload.get("changes"), "lost_periods_linked": linked}, reason=note or None,
               schedule_version=new_no, related_proposal_id=prop.id, status="approved")
    audit(db, user, school_id, "schedule_version", f"Schedule version {new_no} created for Class {plan.grade} {plan.subject}", teacher_id=plan.teacher_id,
          grade=plan.grade, subject=plan.subject, previous={"version": current.version, "metrics": current.metrics}, new={"version": new_no, "metrics": payload.get("metrics")},
          reason=reason, schedule_version=new_no, related_proposal_id=prop.id, related_event_id=ev.id)
    return {"id": prop.id, "status": prop.status, "version": new_no}


async def _link_lost(db: AsyncSession, plan: TeacherPlan, lost_slots: List[Dict[str, Any]], version: int) -> int:
    """Lost periods absorbed by an approved version become immutable (they can no longer be withdrawn)."""
    n = 0
    for s in lost_slots or []:
        row = (await db.execute(select(TeacherLostPeriod).filter_by(school_id=plan.school_id, teacher_id=plan.teacher_id, academic_year=plan.academic_year,
                                                                     grade=plan.grade, subject=plan.subject, lost_date=s.get("date"), period_number=s.get("period"),
                                                                     status="active"))).scalars().first()
        if row is not None and row.schedule_version is None:
            row.schedule_version = version
            n += 1
    return n


# ----------------------------------------------------------------------------------------------- oversight figures
async def relink_lost_rows(db: AsyncSession, school_id: str, teacher_id: str, year: str, grade: int, subject: str) -> int:
    """Idempotent: every lost period that a stored schedule version absorbed is linked to the first version that did."""
    n = 0
    await db.flush()  # the session does not autoflush: make just-added versions and rows visible to the queries below
    plans = (await db.execute(select(TeacherPlan).filter_by(school_id=school_id, teacher_id=teacher_id, academic_year=year, grade=grade, subject=subject))).scalars().all()
    for plan in plans:
        for v in await versions_of(db, plan.id):
            n += await _link_lost(db, plan, v.lost_slots or [], v.version)
    return n


def plan_figures(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Scheduled / taught / outstanding-Core figures for an APPROVED plan, from its current version and effective execution."""
    versions = plan["versions"]
    if plan["status"] != "APPROVED" or not versions:
        return {}
    current = versions[-1]
    superseded = {e["supersedes"] for e in plan["execution"] if e.get("supersedes")}
    events = [e for e in plan["execution"] if e["id"] not in superseded and e["status"] != "HOMEWORK_COMPLETED"]
    scheduled = taught = outstanding_core = 0
    for l in current["lessons"]:
        required = l.get("requiredPeriods") or 0
        classroom = max(0, required - (l.get("independentPeriods") or 0))
        core = l.get("corePeriods") if l.get("corePeriods") is not None else (required if l.get("classification") != "NON_CORE" else 0)
        mine = [e for e in events if e["nodeId"] == l["nodeId"]]
        complete = any(e["status"] == "TAUGHT" for e in mine)
        partial = sum(e["periodsTaught"] for e in mine if e["status"] == "PARTIAL")
        taught_here = classroom if complete else min(partial, classroom)
        scheduled += len(l.get("slots") or [])
        taught += taught_here
        if not complete:
            outstanding_core += max(0, core - min(taught_here, core))
    pending = [x for x in plan["proposals"] if x["status"] == "PENDING"]
    return {"scheduled_periods": scheduled, "taught_periods": taught, "outstanding_core_periods": outstanding_core,
            "pending_proposals": len(pending), "schedule_version": current["version"]}
