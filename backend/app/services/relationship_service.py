"""Teacher-specific topic relationships (prerequisites and Mathematics-Science links).

Domain rules are those of the former workspace governance (validateRelationship): both units exist, no self link,
explanation >= 20 characters, evidence required, cross-curricular links join Mathematics and Science and name a lead unit
when periods are shared, a prerequisite cannot come from a later class, no duplicates. Added here: the teacher must hold
both topics in their own plans, and prerequisite cycles are rejected because they make the order unschedulable.
Removal is soft; every change is a plan_audit_events row.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import User
from backend.app.models.teacher_planning import PlanTopic, TeacherTopicConfig, TeacherTopicRelationship
from backend.app.services.teacher_plan_service import PlanError, _require_owner, audit

REL_KINDS = {"PREREQUISITE", "CROSS_CURRICULAR"}


def rel_dict(r: TeacherTopicRelationship) -> Dict[str, Any]:
    return {"id": r.id, "kind": r.kind, "from_key": r.prerequisite_key, "to_key": r.topic_key, "explanation": r.explanation,
            "evidence": r.evidence, "shared_periods": r.shared_periods, "lead_key": r.lead_topic_key, "status": r.status,
            "origin": r.origin, "created_by": r.created_by, "created_at": r.created_at.isoformat() if r.created_at else None}


def creates_cycle(edges: List[tuple], new_from: str, new_to: str) -> bool:
    """True when `new_to` can already reach `new_from`, i.e. adding from->to would close a loop."""
    graph: Dict[str, List[str]] = {}
    for f, t in edges:
        graph.setdefault(f, []).append(t)
    stack, seen = [new_to], set()
    while stack:
        n = stack.pop()
        if n == new_from:
            return True
        if n in seen:
            continue
        seen.add(n)
        stack.extend(graph.get(n, []))
    return False


async def validate_relationship(db: AsyncSession, school_id: str, teacher_id: str, year: str, kind: str, from_key: str, to_key: str,
                                explanation: str, evidence: str, shared_periods: int, lead_key: Optional[str]) -> List[str]:
    errors: List[str] = []
    if kind not in REL_KINDS:
        return ["Relationship type must be PREREQUISITE or CROSS_CURRICULAR."]
    if from_key == to_key:
        errors.append("A unit cannot relate to itself.")
    topics = {t.topic_key: t for t in (await db.execute(select(PlanTopic).filter(PlanTopic.topic_key.in_([from_key, to_key])))).scalars().all()}
    if len(topics) != len({from_key, to_key}):
        return errors + ["Both units must exist in the syllabus."]
    if len((explanation or "").strip()) < 20:
        errors.append("Explain the conceptual relationship (at least 20 characters).")
    if not (evidence or "").strip():
        errors.append("Evidence grounded in the syllabus sources is required (e.g. both section locators).")
    held = {r[0] for r in (await db.execute(select(TeacherTopicConfig.topic_key).filter(
        TeacherTopicConfig.school_id == school_id, TeacherTopicConfig.teacher_id == teacher_id,
        TeacherTopicConfig.academic_year == year, TeacherTopicConfig.topic_key.in_([from_key, to_key])))).all()}
    if held != {from_key, to_key}:
        errors.append("A teacher can only relate topics that are part of their own plans.")
    f, t = topics[from_key], topics[to_key]
    if from_key != to_key:
        if kind == "CROSS_CURRICULAR":
            if f.subject == t.subject:
                errors.append("A cross-curricular link must connect Mathematics and Science.")
            if not isinstance(shared_periods, int) or isinstance(shared_periods, bool) or shared_periods < 0:
                errors.append("Shared periods must be a whole number of 0 or more.")
            elif shared_periods > 0 and lead_key not in (from_key, to_key):
                errors.append("Choose which unit teaches the shared portion.")
        elif f.grade > t.grade:
            errors.append("A prerequisite cannot come from a later class.")
    existing = (await db.execute(select(TeacherTopicRelationship).filter_by(
        school_id=school_id, teacher_id=teacher_id, academic_year=year, status="active"))).scalars().all()
    for x in existing:
        same = x.kind == kind and ((x.prerequisite_key == from_key and x.topic_key == to_key) or
                                   (kind == "CROSS_CURRICULAR" and x.prerequisite_key == to_key and x.topic_key == from_key))
        if same:
            errors.append("This relationship already exists.")
            break
    if kind == "PREREQUISITE" and from_key != to_key:
        if creates_cycle([(x.prerequisite_key, x.topic_key) for x in existing if x.kind == "PREREQUISITE"], from_key, to_key):
            errors.append("This prerequisite would create a cycle in the prerequisite order.")
    return errors


async def add_relationship(db: AsyncSession, actor: User, school_id: str, teacher_id: str, year: str, *, kind: str = "PREREQUISITE",
                           from_key: str, to_key: str, explanation: str, evidence: str, shared_periods: int = 0,
                           lead_key: Optional[str] = None, reason: Optional[str] = None, origin: str = "teacher") -> Dict[str, Any]:
    if origin == "teacher":
        _require_owner(actor, school_id, teacher_id)
    errors = await validate_relationship(db, school_id, teacher_id, year, kind, from_key, to_key, explanation, evidence, shared_periods, lead_key)
    if errors:
        raise PlanError(422, {"message": "Relationship rejected.", "errors": errors})
    shared = shared_periods if kind == "CROSS_CURRICULAR" else 0
    lead = lead_key if kind == "CROSS_CURRICULAR" and shared > 0 else None
    prior = (await db.execute(select(TeacherTopicRelationship).filter_by(
        school_id=school_id, teacher_id=teacher_id, academic_year=year, topic_key=to_key, prerequisite_key=from_key))).scalars().first()
    if prior:  # re-adding a removed link reactivates the same row; the earlier removal stays in the audit history
        before = rel_dict(prior)
        prior.kind, prior.explanation, prior.evidence = kind, explanation.strip(), evidence.strip()
        prior.shared_periods, prior.lead_topic_key, prior.status, prior.origin = shared, lead, "active", origin
        rel = prior
    else:
        rel = TeacherTopicRelationship(school_id=school_id, teacher_id=teacher_id, academic_year=year, topic_key=to_key,
                                       prerequisite_key=from_key, kind=kind, explanation=explanation.strip(), evidence=evidence.strip(),
                                       shared_periods=shared, lead_topic_key=lead, status="active", origin=origin, created_by=actor.id)
        db.add(rel)
        before = None
    await db.flush()
    audit(db, actor, school_id, "topic_relationship", f"{kind.lower()}: {from_key} -> {to_key} added", teacher_id=teacher_id,
          topic_keys=[from_key, to_key], previous=before, new=rel_dict(rel), reason=reason or explanation.strip())
    return rel_dict(rel)


async def remove_relationship(db: AsyncSession, actor: User, school_id: str, teacher_id: str, year: str, rel_id: str,
                              reason: Optional[str]) -> Dict[str, Any]:
    _require_owner(actor, school_id, teacher_id)
    rel = (await db.execute(select(TeacherTopicRelationship).filter_by(
        id=rel_id, school_id=school_id, teacher_id=teacher_id, academic_year=year))).scalars().first()
    if not rel or rel.status != "active":
        raise PlanError(404, "Relationship not found.")
    before = rel_dict(rel)
    rel.status = "removed"  # soft: row and audit trail are kept
    audit(db, actor, school_id, "topic_relationship", f"{rel.kind.lower()}: {rel.prerequisite_key} -> {rel.topic_key} removed",
          teacher_id=teacher_id, topic_keys=[rel.prerequisite_key, rel.topic_key], previous=before, new=rel_dict(rel), reason=reason)
    return rel_dict(rel)


async def list_relationships(db: AsyncSession, school_id: str, teacher_id: str, year: str, include_removed: bool = False) -> List[Dict[str, Any]]:
    q = select(TeacherTopicRelationship).filter_by(school_id=school_id, teacher_id=teacher_id, academic_year=year)
    if not include_removed:
        q = q.filter_by(status="active")
    rows = (await db.execute(q.order_by(TeacherTopicRelationship.created_at, TeacherTopicRelationship.id))).scalars().all()
    return [rel_dict(r) for r in rows]
