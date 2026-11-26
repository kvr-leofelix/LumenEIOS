"""Adopt the existing NCERT review-batch curriculum into a WORKING database copy. Dry-run unless --apply is given.

  python backend/scripts/adopt_curriculum.py --source-db <day100.db> --dataset-json <recovered_ncert_dataset.json> --database lumeneios_teacherplan_demo.db
  ... --apply --backup-dir <folder outside the repo>

Additive and idempotent: copies ncert_* rows verbatim, adds plan_topics for the dataset's own node ids, appends one workspace revision per
school carrying the original dataset, and creates default requirement/coverage rows (never overwriting) for teachers who already hold
a plan. Refuses the protected databases. A byte-for-byte backup of the target is written first when --apply is used.
"""
import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.services import curriculum_adoption as ad  # noqa: E402


async def _teacher_defaults(db_path: Path) -> int:
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    from sqlalchemy import select
    from backend.app.db.session import AsyncSessionLocal
    from backend.app.models.entities import User
    from backend.app.models.teacher_planning import TeacherTopicConfig
    from backend.app.services import teacher_plan_service as svc

    created = 0
    async with AsyncSessionLocal() as db:
        combos = (await db.execute(select(TeacherTopicConfig.school_id, TeacherTopicConfig.teacher_id, TeacherTopicConfig.academic_year,
                                          TeacherTopicConfig.grade, TeacherTopicConfig.subject).distinct())).all()
        for school, teacher, year, grade, subject in sorted(combos):
            actor = (await db.execute(select(User).filter_by(id=teacher))).scalars().first()
            if actor and await svc.ensure_defaults(db, actor, school, teacher, year, grade, subject):
                created += 1
        await db.commit()
    return created


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-db", required=True)
    ap.add_argument("--dataset-json", required=True)
    ap.add_argument("--database", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup-dir")
    ap.add_argument("--report-out")
    a = ap.parse_args()

    target = Path(a.database).resolve()
    ad.refuse_protected(target)
    if not target.exists():
        sys.exit(f"Target database not found: {target}")
    dataset = json.loads(Path(a.dataset_json).read_text(encoding="utf-8"))
    src = ad.ro_connect(a.source_db)
    verified = ad.verify_source(src, dataset)
    topics = ad.plan_topic_rows(dataset, verified["node_uuid"])
    report = {"target": str(target), "source_db": str(Path(a.source_db).resolve()), "source_sha256": ad.sha256_file(a.source_db),
              "dataset_sha256": ad.sha256_file(a.dataset_json), "curriculum_counts": verified["counts"],
              "planning_units": len(topics), "dataset_label": dataset["label"], "dataset_kind": dataset.get("kind"),
              "metadata_note": dataset.get("description")}
    con = sqlite3.connect(f"file:{target.as_posix()}?mode=rw", uri=True, isolation_level=None)
    con.execute("PRAGMA foreign_keys=OFF")
    report["legacy_mapping_proposal"] = ad.legacy_mapping_report(con, dataset)
    if not a.apply:
        report["mode"] = "dry-run (nothing written)"
        print(json.dumps(report, indent=2))
        return 0
    if not a.backup_dir:
        sys.exit("--apply requires --backup-dir (a folder for the byte-for-byte backup of the target).")
    backup = Path(a.backup_dir) / f"{target.stem}.pre-adoption-{datetime.now():%Y%m%d-%H%M%S}.db"
    shutil.copy2(target, backup)
    report["backup"] = {"path": str(backup), "sha256": ad.sha256_file(backup)}
    ad.attach_source(con, a.source_db)
    con.execute("BEGIN IMMEDIATE")
    try:
        report["catalogue_rows_added"] = ad.copy_catalogue(con)
        report["plan_topics_added"] = ad.insert_plan_topics(con, topics)
        report["workspace_revisions"] = ad.add_workspace_dataset(con, dataset)
        bad = con.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise ad.AdoptionError(f"foreign key violations: {bad[:3]}")
        con.execute("COMMIT")
        con.execute("DETACH DATABASE src")
    except Exception:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    report["teacher_plans_given_default_rows"] = asyncio.run(_teacher_defaults(target))
    report["mode"] = "applied"
    text = json.dumps(report, indent=2)
    if a.report_out:
        Path(a.report_out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
