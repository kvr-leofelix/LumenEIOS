"""Writes a planning-syllabus import (JSON) from the validated NCERT review package: headings + page locators only.

  python scripts/build_planning_import.py --zip ../../LumenEIOS_NCERT_Review_Batch_01.zip --out <path outside the repo>.json

The file is imported by an Admin through Time-Aware Engine > Syllabus & classification (existing import). It contains
textbook headings, so keep it out of the repository (source policy: no textbook text is committed).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services import ncert_review_import as imp  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--zip', required=True)
    ap.add_argument('--register', default=str(ROOT / 'docs' / 'NCERT_SOURCE_REGISTER.csv'))
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    out = Path(a.out).resolve()
    if ROOT.parent.parent in out.parents:
        sys.exit('Refusing to write textbook headings inside the repository; choose a path outside it.')
    doc = imp.to_planning_import(imp.read_package(a.zip), imp.read_register(a.register))
    out.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
    print(f"wrote {out}: {len(doc['textbooks'])} textbooks, {len(doc['nodes'])} nodes")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
