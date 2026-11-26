"""Deterministic multi-school demonstration seed for teacher plans (explicit, never run at startup).

Topic identities come from the source-verified research crosswalk (10 sections, Classes VI-VIII). Core/Non-Core
splits are a pure function of the topic key, so every school gets the identical HYPOTHETICAL pattern.
"""
import json
from pathlib import Path
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.security import get_password_hash
from backend.app.models.entities import School, SchoolMembership, User
from backend.app.models.planning_workspace import PlanningWorkspaceRevision
from backend.app.models.teacher_planning import PlanTopic, SchoolPlanCalendar
from backend.app.services import teacher_plan_service as svc

SNAPSHOT = Path(__file__).resolve().parents[3] / "src" / "features" / "curriculum" / "mocks" / "researchSnapshot.json"
YEAR = "2026-2027"
SYSTEM = type("SystemActor", (), {"id": "system-seed", "name": "Demo seed", "role": "system", "school_id": None})()

# per-school hypothetical calendars: different closures so capacities differ
CALENDARS: Dict[str, List[dict]] = {
    "school-1": [{"id": "h1", "type": "HOLIDAY", "label": "Autumn break", "start": "2026-10-19", "end": "2026-10-23"}],
    "school-2": [{"id": "h1", "type": "HOLIDAY", "label": "Winter vacation", "start": "2026-12-24", "end": "2027-01-10"},
                 {"id": "e1", "type": "EXAM", "label": "Mid-term exams", "start": "2026-09-14", "end": "2026-09-25"}],
    "school-3": [{"id": "h1", "type": "HOLIDAY", "label": "Festival closure", "start": "2026-11-05", "end": "2026-11-12"}],
}
# (teacher id, name, email, school); the two teachers in a school share the same class/subject on purpose
TEACHERS = [
    ("user-teacher-1", None, None, "school-1"), ("user-teacher-2", None, None, "school-1"),
    ("demo-plan-teacher-2a", "Demo Teacher 2A", "teacher2a@lumeneios.demo", "school-2"),
    ("demo-plan-teacher-2b", "Demo Teacher 2B", "teacher2b@lumeneios.demo", "school-2"),
    ("user-teacher-3", None, None, "school-3"),
    ("demo-plan-teacher-3b", "Demo Teacher 3B", "teacher3b@lumeneios.demo", "school-3"),
]
PRINCIPALS = [("demo-plan-principal-2", "Demo Principal 2", "principal2@lumeneios.demo", "school-2"),
              ("demo-plan-principal-3", "Demo Principal 3", "principal3@lumeneios.demo", "school-3")]
COMBOS = [(7, "Mathematics"), (8, "Science")]


async def seed_teacher_plan_demo(db: AsyncSession) -> Dict[str, int]:
    rows = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["crosswalk"]
    order: Dict[tuple, int] = {}
    for r in rows:
        k = (int(r["grade"]), r["subject"])
        order[k] = order.get(k, 0) + 1
        if not (await db.execute(select(PlanTopic).filter_by(topic_key=r["mappingId"]))).scalars().first():
            db.add(PlanTopic(topic_key=r["mappingId"], grade=k[0], subject=k[1], chapter_number=str(r["chapterNumber"]),
                             chapter_title=r["chapterTitle"], section_label=f'{r["topicSection"]} {r["topicLabel"]}',
                             sort_order=order[k], source_ref=r.get("chapterSourceId")))
    for school_id, entries in CALENDARS.items():
        if not (await db.execute(select(School.id).filter_by(id=school_id))).first():
            continue
        # A school whose workspace already holds a saved Academic Configuration keeps that real calendar: the hypothetical demo
        # calendar must never shadow it (import_workspace_calendar brings the real one in).
        latest = (await db.execute(select(PlanningWorkspaceRevision).filter_by(school_id=school_id).order_by(PlanningWorkspaceRevision.revision.desc()).limit(1))).scalars().first()
        has_real = bool(latest and (latest.state or {}).get("configHistory"))
        if not has_real and not (await db.execute(select(SchoolPlanCalendar.id).filter_by(school_id=school_id, academic_year=YEAR))).first():
            cfg = {**svc.DEFAULT_CALENDAR, "entries": entries, "subjectPeriodsPerDay": {"Mathematics": 2, "Science": 2}}
            db.add(SchoolPlanCalendar(school_id=school_id, academic_year=YEAR, version=1, config=cfg,
                                      reason="Hypothetical demonstration calendar", created_by="system-seed"))
    await db.flush()
    pw = get_password_hash("demo123")
    created_plans = 0
    for pid, pname, pmail, school_id in PRINCIPALS:
        if (await db.execute(select(School.id).filter_by(id=school_id))).first() and not (await db.execute(select(User.id).filter_by(id=pid))).first():
            db.add(User(id=pid, email=pmail, name=pname, hashed_password=pw, role="principal", school_id=school_id))
            db.add(SchoolMembership(user_id=pid, school_id=school_id, role="principal"))
    await db.flush()
    for tid, name, email, school_id in TEACHERS:
        if not (await db.execute(select(School.id).filter_by(id=school_id))).first():
            continue
        user = (await db.execute(select(User).filter_by(id=tid))).scalars().first()
        if not user and name:
            user = User(id=tid, email=email, name=name, hashed_password=pw, role="teacher", school_id=school_id)
            db.add(user)
            db.add(SchoolMembership(user_id=tid, school_id=school_id, role="teacher"))
            await db.flush()
        if not user:
            continue
        for grade, subject in COMBOS:
            if await svc.ensure_defaults(db, SYSTEM, school_id, tid, YEAR, grade, subject):
                created_plans += 1
    await db.commit()
    return {"plans_created": created_plans}
