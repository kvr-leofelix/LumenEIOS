"""One-time, repeatable import of the legacy workspace document into the relational teacher-plan tables.

Usage (from apps/lumeneios), ISOLATED database only:
  DATABASE_URL=sqlite+aiosqlite:///./lumeneios_teacherplan_demo.db PYTHONPATH=. venv/Scripts/python.exe backend/scripts/import_workspace_to_teacher_plans.py [--json]

Safety: refuses the four protected databases by name; never modifies workspace revisions; every importer skips ambiguous
ownership, never overwrites an existing relational record and is idempotent (a second run changes nothing).
Order matters: calendar -> requirements -> relationships -> coverage -> plans -> lost periods (a loss is validated against the approved
schedule it belongs to, so the plan must exist first).
"""
import asyncio
import json
import sys
from pathlib import Path

PROTECTED = {"lumeneios.db", "lumeneios_acceptance.db", "lumeneios_planning_dev.db", "lumeneios_takeover_acceptance.db"}


async def main(as_json: bool) -> None:
    from sqlalchemy import select
    from backend.app.db.session import AsyncSessionLocal, engine, init_db
    from backend.app.models.planning_workspace import PlanningWorkspaceRevision
    from backend.app.services import workspace_import as wi
    name = Path(engine.url.database or "").name
    if name in PROTECTED or not name:
        sys.exit(f"Refusing to import into a protected or unnamed database: {name!r}")
    await init_db()
    steps = [("calendar", wi.import_workspace_calendar), ("requirements", wi.import_workspace_requirements), ("relationships", wi.import_workspace_relationships),
             ("coverage", wi.import_workspace_coverage), ("plans", wi.import_workspace_plans), ("lost_periods", wi.import_workspace_losses)]
    report = {}
    async with AsyncSessionLocal() as db:
        schools = [r[0] for r in (await db.execute(select(PlanningWorkspaceRevision.school_id).distinct())).all()]
        for school in sorted(schools):
            report[school] = {}
            for label, fn in steps:
                report[school][label] = await fn(db, school)
    if as_json:
        print(json.dumps(report, indent=2, default=str))
    else:
        for school, parts in report.items():
            print(f"{school}:")
            for label, rep in parts.items():
                print(f"  {label}: " + ", ".join(f"{k}={len(v) if isinstance(v, list) else v}" for k, v in rep.items()))
        if not report:
            print("No workspace revisions found; nothing to import.")


if __name__ == "__main__":
    asyncio.run(main("--json" in sys.argv))
