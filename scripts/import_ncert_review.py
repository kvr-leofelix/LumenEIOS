"""Audit / stage the NCERT review package. Dry-run unless --apply is given.

  python scripts/import_ncert_review.py --zip ../../LumenEIOS_NCERT_Review_Batch_01.zip            # audit only
  python scripts/import_ncert_review.py --zip ... --apply --database path/to/COPY.db               # stage DRAFT structure

--apply requires an explicit database file, refuses the original application database (lumeneios.db), runs the
additive catalogue migrations first, and never publishes. Back up first; stage into a copy.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, event  # noqa: E402

from backend.app.services import ncert_review_import as imp  # noqa: E402


def _migration(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'backend' / 'migrations' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--zip', required=True)
    ap.add_argument('--register', default=str(ROOT / 'docs' / 'NCERT_SOURCE_REGISTER.csv'))
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--database')
    ap.add_argument('--report-out')
    args = ap.parse_args()

    package = imp.read_package(args.zip)
    register = imp.read_register(args.register)
    if not args.apply:
        report = imp.public_report(imp.audit(package, register))
        text = json.dumps(report, indent=2, ensure_ascii=False)
        if args.report_out:
            Path(args.report_out).write_text(text, encoding='utf-8')
        print(text)
        return 0 if report['valid'] else 1

    if not args.database:
        sys.exit('--apply needs --database <copy>')
    db = Path(args.database).resolve()
    if db.name == 'lumeneios.db':
        sys.exit('Refusing to stage into the original application database. Use a copy.')
    if not db.exists():
        sys.exit(f'Database copy not found: {db}')
    engine = create_engine(f'sqlite:///{db}')

    @event.listens_for(engine, 'connect')
    def _fk(dbapi, _):
        dbapi.execute('PRAGMA foreign_keys=ON')

    with engine.begin() as conn:
        _migration('001_ncert_catalogue').upgrade(conn)
        result = imp.stage(conn, package, register)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.report_out:
        Path(args.report_out).write_text(text, encoding='utf-8')
    print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
