"""Initialise the full syllabus and the default teacher plans in the database DATABASE_URL points at. Safe to re-run.

  cd apps/lumeneios
  python -m backend.scripts.init_curriculum            # uses DATABASE_URL / .env (default ./lumeneios.db)

Additive and idempotent: creates missing tables, seeds the roster only on an empty database, then adds missing syllabus topics,
the syllabus workspace dataset and the missing Core/Non-Core + coverage rows of every eligible teacher plan. Teacher edits and
coverage already stored are never changed. Refuses the four protected acceptance databases.
"""
import asyncio
import sys
from pathlib import Path

PROTECTED = {"lumeneios.db", "lumeneios_acceptance.db", "lumeneios_planning_dev.db", "lumeneios_takeover_acceptance.db"}


async def main() -> int:
    from backend.app.db.session import AsyncSessionLocal, engine, init_db
    from backend.app.seed.seed_data import seed_database_if_empty
    from backend.app.services import syllabus_seed as ss
    name = Path(engine.url.database or "").name
    if not name:
        sys.exit("Refusing to initialise an unnamed database.")
    if name in PROTECTED:
        sys.exit(f"{name} is a protected database. Point DATABASE_URL at your own file, e.g. sqlite+aiosqlite:///./lumeneios_dev.db")
    await init_db()
    async with AsyncSessionLocal() as db:
        await seed_database_if_empty(db)
        result = await ss.initialise_curriculum(db)
        report = await ss.configuration_report(db)
    print(f"Database: {Path(engine.url.database).resolve()}")
    print("Initialised:", result)
    print("Now holding:", report)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
