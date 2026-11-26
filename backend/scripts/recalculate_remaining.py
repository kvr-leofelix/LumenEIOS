"""Recalculate the REMAINING (untaught) period requirements of every teacher plan in a development/demo database.

  cd apps/lumeneios && DATABASE_URL=sqlite+aiosqlite:///./lumeneios_dev.db python -m backend.scripts.recalculate_remaining

Same function the calendar save uses (services/recalculation.py): Done topics, taught periods and classifications are preserved;
the pool is the instructional time left after today (override with PLANNING_TODAY=YYYY-MM-DD). Idempotent. Audited per plan.
Refuses the protected acceptance databases.
"""
import asyncio
import sys
from pathlib import Path

PROTECTED = {"lumeneios.db", "lumeneios_acceptance.db", "lumeneios_planning_dev.db", "lumeneios_takeover_acceptance.db", "lumeneios_day100.db", "lumeneios_e2e.db"}


async def main() -> int:
    from sqlalchemy import select
    from backend.app.db.session import AsyncSessionLocal, engine
    from backend.app.models.entities import School
    from backend.app.models.teacher_planning import TeacherTopicConfig
    from backend.app.services import syllabus_seed as ss
    from backend.app.services import teacher_plan_service as svc
    name = Path(engine.url.database or "").name
    if not name or name in PROTECTED:
        sys.exit(f"Refusing to modify protected or unnamed database: {name!r}")
    changed = plans = 0
    async with AsyncSessionLocal() as db:
        for (school_id,) in (await db.execute(select(School.id).order_by(School.id))).all():
            cfg = (await svc.get_calendar(db, school_id, ss.YEAR))["config"]
            combos = sorted((await db.execute(select(TeacherTopicConfig.teacher_id, TeacherTopicConfig.grade, TeacherTopicConfig.subject)
                                              .filter_by(school_id=school_id, academic_year=ss.YEAR).distinct())).all())
            for tid, grade, subject in combos:
                res = await svc.recalculate_plan(db, ss.SYSTEM, school_id, tid, ss.YEAR, grade, subject, cfg, "Remaining syllabus recalculated (maintenance command)")
                plans += 1
                changed += res["topics_changed"]
        await db.commit()
    print(f"Database: {Path(engine.url.database).resolve()}\nPlans recalculated: {plans}; topic allocations changed: {changed}; planning date {svc.planning_today()}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
