"""Reproducible, idempotent syllabus + default teacher-plan initialisation.

Source of truth (tracked in Git): ``backend/app/seed/data/ncert_review_batch01_structure.json`` - the heading structure
(chapters, numbered sections, numbered subheadings and their PDF-page locators) of the NCERT review batch. It is a structural
inventory only: no page text, outcomes or Core/Non-Core data, and it is not a verified or complete syllabus.

What this module does, always additively:
  1. ``seed_syllabus``    - adds missing ``plan_topics`` (one per teachable leaf topic) and appends the dataset to each school's
                            planning workspace when that school does not hold it yet. Existing rows are never changed.
  2. ``seed_teacher_plans`` - for every teacher who really teaches Mathematics or Science in Classes VI-VIII, fills the topic
                            configurations (Core / Non-Core / Mixed, 2:1 for mixed) and coverage rows that are MISSING, through
                            the same ``ensure_defaults`` the application uses. Teacher edits and coverage are never overwritten.

Running it twice changes nothing. The initial classifications are deterministic planning defaults (a pure function of the
topic key), never official NCERT classifications; a teacher edits them in Course Curriculum.
"""
import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import ClassSection, School, SchoolMembership, User
from backend.app.models.ncert_catalogue import NAMESPACE
from backend.app.models.planning_workspace import PlanningWorkspaceRevision
from backend.app.models.teacher_planning import PlanTopic, SchoolPlanCalendar, TeacherTopicConfig
from backend.app.services import teacher_plan_service as svc

DATASET_PATH = Path(__file__).resolve().parents[1] / "seed" / "data" / "ncert_review_batch01_structure.json"
RELEASE_KEY = "ncert-review-batch-01-structure"
SCHEDULABLE = ("TOPIC", "SUBTOPIC")
EXPECTED_COUNTS = {"CHAPTER": 76, "TOPIC": 353, "SUBTOPIC": 102}
YEAR = "2026-2027"
SUPPORTED_SUBJECTS = ("Mathematics", "Science")
SUPPORTED_GRADES = (6, 7, 8)
SYSTEM = type("SystemActor", (), {"id": "system-curriculum-seed", "name": "Curriculum seed (system)", "role": "system", "school_id": None})()


class SeedError(RuntimeError):
    pass


def load_dataset() -> Dict[str, Any]:
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    counts: Dict[str, int] = {}
    for n in dataset["nodes"]:
        counts[n["kind"]] = counts.get(n["kind"], 0) + 1
    if counts != EXPECTED_COUNTS or len({n["id"] for n in dataset["nodes"]}) != len(dataset["nodes"]):
        raise SeedError(f"Syllabus source is damaged: counts {counts}, expected {EXPECTED_COUNTS} with unique ids.")
    return dataset


def eligible_units(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mirror of the frontend rule (syllabus.ts eligibleUnits): TOPIC/SUBTOPIC nodes that are not the heading of teachable children."""
    parents = {n["parentId"] for n in nodes if n["kind"] in SCHEDULABLE and n.get("parentId")}
    return [n for n in nodes if n["kind"] in SCHEDULABLE and n["id"] not in parents]


def catalogue_node_uuid(dataset_node_id: str) -> str:
    """Same deterministic id the catalogue importer gives the node (identity uuid5, then release-scoped node uuid5)."""
    authority = re.sub(r"^ncert-review-", "ncert-review:", dataset_node_id, count=1)
    identity = str(uuid.uuid5(NAMESPACE, authority))
    return str(uuid.uuid5(NAMESPACE, RELEASE_KEY + ":" + identity))


def plan_topic_rows(dataset: Dict[str, Any]) -> List[Dict[str, Any]]:
    nodes = dataset["nodes"]
    by_id = {n["id"]: n for n in nodes}
    book_index = {t["id"]: i for i, t in enumerate(dataset["textbooks"])}

    def chapter_of(n: Dict[str, Any]) -> Dict[str, Any]:
        cur = n
        while cur["kind"] != "CHAPTER":
            cur = by_id[cur["parentId"]]
        return cur

    groups: Dict[Tuple[int, str], List[Dict[str, Any]]] = {}
    for u in eligible_units(nodes):
        groups.setdefault((u["grade"], u["subject"]), []).append(u)
    rows: List[Dict[str, Any]] = []
    for (grade, subject), members in sorted(groups.items()):
        members.sort(key=lambda n: (book_index.get(n["textbookId"], 99), n["sequence"]))
        for order, n in enumerate(members, start=1):
            ch = chapter_of(n)
            if len(n["id"]) > 64:
                raise SeedError(f"Topic id longer than 64 characters: {n['id']}")
            rows.append({"topic_key": n["id"], "grade": grade, "subject": subject, "chapter_number": str(ch.get("number") or ""),
                         "chapter_title": ch["title"], "section_label": f"{n['number']} {n['title']}".strip()[:255],
                         "sort_order": order, "source_ref": svc.CATALOGUE_REF + catalogue_node_uuid(n["id"])})
    return rows


async def seed_syllabus(db: AsyncSession) -> Dict[str, int]:
    """Add missing plan topics and the dataset to each school workspace. Never edits or deletes anything."""
    dataset = load_dataset()
    have = {k for (k,) in (await db.execute(select(PlanTopic.topic_key))).all()}
    added = 0
    for r in plan_topic_rows(dataset):
        if r["topic_key"] not in have:
            db.add(PlanTopic(**r))
            added += 1
    datasets_added = 0
    for (school_id,) in (await db.execute(select(School.id).order_by(School.id))).all():
        latest = (await db.execute(select(PlanningWorkspaceRevision).filter_by(school_id=school_id)
                                   .order_by(PlanningWorkspaceRevision.revision.desc()).limit(1))).scalars().first()
        state = dict(latest.state) if latest and isinstance(latest.state, dict) else {
            "schemaVersion": 2, "config": {}, "configHistory": [], "datasets": [], "classifications": {}, "relationships": [],
            "plans": [], "coverage": {}, "asOf": None, "audit": []}
        if any(d.get("id") == dataset["id"] for d in state.get("datasets", [])):
            continue
        # Another dataset already supplying the same node ids must not be duplicated.
        state["datasets"] = [*state.get("datasets", []), dataset]
        db.add(PlanningWorkspaceRevision(
            school_id=school_id, revision=(latest.revision if latest else 0) + 1, action="SYLLABUS_IMPORT",
            summary=f"Curriculum seed: '{dataset['label']}' (heading structure only, unverified)", actor_id=SYSTEM.id,
            actor_name=SYSTEM.name, actor_role="admin", state=state))
        datasets_added += 1
    await db.flush()
    return {"plan_topics_added": added, "workspace_datasets_added": datasets_added}


async def teaching_assignments(db: AsyncSession) -> List[Tuple[str, str, int, str]]:
    """(school_id, teacher_id, grade, subject) for every teacher who really teaches Class VI-VIII Mathematics or Science.

    Truth comes from the class sections a teacher's school runs and the subject the teacher is a member for; a teacher whose
    subject is not Mathematics/Science (e.g. English, Chemistry) is NOT eligible and gets no plan.
    """
    from backend.app.seed.seed_data import TEACHERS, SUBJECTS
    subject_name = {s["id"]: s["name"] for s in SUBJECTS}
    out: List[Tuple[str, str, int, str]] = []
    teachers = (await db.execute(select(User).filter_by(role="teacher").order_by(User.id))).scalars().all()
    roster = {f"user-teacher-{t['key']}": t for t in TEACHERS}
    for u in teachers:
        sch = roster.get(u.id)
        if not sch:
            continue
        subject = subject_name.get(sch["subject"])
        if subject not in SUPPORTED_SUBJECTS:
            continue
        school_id = u.school_id
        grades = {c.grade for c in (await db.execute(select(ClassSection).filter_by(school_id=school_id))).scalars().all()}
        for g in sorted(grades & set(sch["grades"]) & set(SUPPORTED_GRADES)):
            out.append((school_id, u.id, g, subject))
    return out


async def seed_teacher_plans(db: AsyncSession, year: str = YEAR) -> Dict[str, int]:
    """Create the missing deterministic configuration and coverage rows for every eligible teacher plan.

    Eligible = the roster assignments above plus every plan combination a teacher already holds in this database (an upgraded
    database keeps its own teachers), always under the academic year that plan already uses.
    """
    combos: Dict[Tuple[str, str, str, int, str], None] = {(s, t, year, g, sub): None for s, t, g, sub in await teaching_assignments(db)}
    for row in (await db.execute(select(TeacherTopicConfig.school_id, TeacherTopicConfig.teacher_id, TeacherTopicConfig.academic_year,
                                        TeacherTopicConfig.grade, TeacherTopicConfig.subject).distinct())).all():
        if row[4] in SUPPORTED_SUBJECTS and row[3] in SUPPORTED_GRADES:
            combos[tuple(row)] = None
    plans = filled = 0
    for school_id, teacher_id, plan_year, grade, subject in sorted(combos):
        plans += 1
        if await svc.ensure_defaults(db, SYSTEM, school_id, teacher_id, plan_year, grade, subject):
            filled += 1
    return {"eligible_plans": plans, "plans_filled": filled}


DEFAULT_PER_DAY = {"Mathematics": 2, "Science": 2}
SEEDED_BY = {"system-seed", "system-curriculum-seed"}


async def align_default_calendars(db: AsyncSession) -> Dict[str, int]:
    """Bring demonstration/default calendars to the default timetable (2 Mathematics + 2 Science periods per instructional day).

    Only calendars that are still the unmodified seeded demonstration default are touched (latest version written by the seed);
    a calendar a school's Admin/Principal saved is a customisation and is never changed. A school with no saved calendar uses the
    backend default (now 2+2) directly. Every affected teacher plan's remaining allocation is then recalculated, so required
    periods always match the capacity. Idempotent: once a school is on 2+2 nothing happens."""
    aligned = recalculated = 0
    await db.flush()  # the session does not autoflush: make plan rows added earlier in this run visible to the queries below
    schools = [s for (s,) in (await db.execute(select(School.id).order_by(School.id))).all()]
    for school_id in schools:
        latest = (await db.execute(select(SchoolPlanCalendar).filter_by(school_id=school_id, academic_year=YEAR)
                                   .order_by(SchoolPlanCalendar.version.desc()).limit(1))).scalars().first()
        has_plans = (await db.execute(select(TeacherTopicConfig.id).filter_by(school_id=school_id, academic_year=YEAR).limit(1))).first()
        if latest is None:
            if not has_plans:
                continue
            # No saved calendar: record the default (2+2) as version 1 once, so this correction can never run again for the school.
            cfg = {**svc.DEFAULT_CALENDAR, "year": YEAR}
            db.add(SchoolPlanCalendar(school_id=school_id, academic_year=YEAR, version=1, config=cfg, created_by=SYSTEM.id,
                                      reason="Default timetable: 2 Mathematics + 2 Science periods per instructional day"))
            await db.flush()
            aligned += 1
        elif latest.created_by in SEEDED_BY and (latest.config.get("subjectPeriodsPerDay") or {}) != DEFAULT_PER_DAY:
            cfg = {**latest.config, "subjectPeriodsPerDay": dict(DEFAULT_PER_DAY)}
            db.add(SchoolPlanCalendar(school_id=school_id, academic_year=YEAR, version=latest.version + 1, config=cfg, created_by=SYSTEM.id,
                                      reason="Default timetable corrected to 2 Mathematics + 2 Science periods per instructional day"))
            await db.flush()
            aligned += 1
        else:
            continue  # a customised school calendar is preserved
        for tid, grade, subject in sorted((await db.execute(select(TeacherTopicConfig.teacher_id, TeacherTopicConfig.grade, TeacherTopicConfig.subject)
                                                            .filter_by(school_id=school_id, academic_year=YEAR).distinct())).all()):
            res = await svc.recalculate_plan(db, SYSTEM, school_id, tid, YEAR, grade, subject, cfg, "Default timetable is 2 Mathematics + 2 Science periods per day")
            recalculated += 1 if res["topics_changed"] else 0
    return {"calendars_aligned": aligned, "plans_recalculated": recalculated}


async def initialise_curriculum(db: AsyncSession) -> Dict[str, int]:
    out = await seed_syllabus(db)
    out.update(await seed_teacher_plans(db))
    out.update(await align_default_calendars(db))
    await db.commit()
    return out


async def configuration_report(db: AsyncSession) -> Dict[str, Any]:
    """Counts used by the init script and acceptance report."""
    total_topics = len((await db.execute(select(PlanTopic.topic_key).where(PlanTopic.source_ref.like(svc.CATALOGUE_REF + "%")))).all())
    combos = (await db.execute(select(TeacherTopicConfig.school_id, TeacherTopicConfig.teacher_id, TeacherTopicConfig.grade,
                                      TeacherTopicConfig.subject).distinct())).all()
    cfgs = len((await db.execute(select(TeacherTopicConfig.id))).all())
    return {"catalogue_topics": total_topics, "teacher_plans_with_configs": len(combos), "topic_configurations": cfgs}
