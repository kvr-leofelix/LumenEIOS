"""Seed the deterministic teacher-plan demo into an ISOLATED database only.

Usage (from apps/lumeneios):
  DATABASE_URL=sqlite+aiosqlite:///./lumeneios_teacherplan_demo.db PYTHONPATH=. venv/Scripts/python.exe backend/scripts/seed_teacher_plan_demo.py
Refuses the four protected databases by name. Create the demo DB by copying lumeneios.db first.
"""
import asyncio
import sys
from pathlib import Path

PROTECTED = {"lumeneios.db", "lumeneios_acceptance.db", "lumeneios_planning_dev.db", "lumeneios_takeover_acceptance.db"}


async def main() -> None:
    from backend.app.db.session import AsyncSessionLocal, engine, init_db
    from backend.app.seed.seed_data import seed_database_if_empty
    from backend.app.seed.teacher_plan_demo import seed_teacher_plan_demo
    name = Path(engine.url.database or "").name
    if name in PROTECTED or not name:
        sys.exit(f"Refusing to seed protected or unnamed database: {name!r}")
    await init_db()
    async with AsyncSessionLocal() as s:
        await seed_database_if_empty(s)
        print(await seed_teacher_plan_demo(s))


if __name__ == "__main__":
    asyncio.run(main())
