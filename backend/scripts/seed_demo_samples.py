"""Add the deterministic demonstration samples (see backend/app/seed/demo_samples.py) to a development/demo database.

  cd apps/lumeneios && DATABASE_URL=sqlite+aiosqlite:///./lumeneios_dev.db python -m backend.scripts.seed_demo_samples

Run backend.scripts.init_curriculum first. Refuses the protected acceptance databases.
"""
import asyncio
import sys
from pathlib import Path

PROTECTED = {"lumeneios.db", "lumeneios_acceptance.db", "lumeneios_planning_dev.db", "lumeneios_takeover_acceptance.db", "lumeneios_day100.db", "lumeneios_e2e.db"}


async def main() -> int:
    from backend.app.db.session import AsyncSessionLocal, engine
    from backend.app.seed.demo_samples import seed_demo_samples
    name = Path(engine.url.database or "").name
    if not name or name in PROTECTED:
        sys.exit(f"Refusing to modify protected or unnamed database: {name!r}")
    async with AsyncSessionLocal() as db:
        print(f"Database: {Path(engine.url.database).resolve()}")
        print("Demo samples:", await seed_demo_samples(db))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
