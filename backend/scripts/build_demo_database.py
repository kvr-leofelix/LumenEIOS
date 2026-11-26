"""Build (or rebuild) the LumenEIOS demonstration database.

    python -m backend.scripts.build_demo_database            # build if the database is missing or empty
    python -m backend.scripts.build_demo_database --fresh    # back up the current database and rebuild it

Creates two CBSE schools (Classes 6-8, sections A and B, 20 students each) with a session of graded history,
teacher plans and open work, then writes docs/LOGIN_CREDENTIALS.md. The previous database is kept as
lumeneios.db.backup-<timestamp> when --fresh is used.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)


def sqlite_path() -> Path | None:
    from backend.app.core.config import settings
    url = settings.DATABASE_URL
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return None
    return (APP_DIR / url[len(prefix):]).resolve() if not url[len(prefix):].startswith("/") else Path(url[len(prefix):])


async def build(fresh: bool) -> None:
    path = sqlite_path()
    if fresh and path and path.exists():
        backup = path.with_name(f"{path.name}.backup-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.move(path, backup)
        for extra in ("-wal", "-shm"):
            side = path.with_name(path.name + extra)
            if side.exists():
                side.unlink()
        print(f"Previous database moved to {backup.name}")

    from sqlalchemy import select
    import backend.app.main  # noqa: F401  (registers every model)
    from backend.app.db.session import AsyncSessionLocal, engine, init_db
    from backend.app.models.entities import School
    from backend.app.seed.seed_data import seed_database_if_empty
    from backend.app.services.syllabus_seed import initialise_curriculum

    await init_db()
    async with AsyncSessionLocal() as session:
        already = (await session.execute(select(School.id).limit(1))).first()
        if already and not fresh:
            print("The database already has data. Use --fresh to rebuild it.")
            await engine.dispose()
            return
        print("Building schools, classes, students and the 2026-27 session history...")
        await seed_database_if_empty(session)
    async with AsyncSessionLocal() as session:
        print("Initialising the NCERT syllabus and teacher plans...")
        print("  ", await initialise_curriculum(session))
    from backend.scripts.demo_scenario import run_scenario
    print("Recording classroom activity (homework, uploads, evaluations)...")
    await run_scenario()
    await engine.dispose()
    from backend.scripts.write_credentials import write_credentials
    out = write_credentials()
    print(f"Login credentials written to {out.relative_to(APP_DIR)}")
    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fresh", action="store_true", help="back up the current database and rebuild it")
    args = parser.parse_args()
    asyncio.run(build(args.fresh))


if __name__ == "__main__":
    main()
