"""Explicit historical processing; backs up SQLite and only changes evaluation metadata."""
import argparse
import asyncio
import sqlite3
import uuid
from pathlib import Path
from sqlalchemy.engine import make_url
from backend.app.core.config import settings
from backend.scripts.migrate_learnsphere import column_inventory, fingerprint


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result-id',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    url=make_url(settings.DATABASE_URL)
    if not url.drivername.startswith('sqlite') or not url.database or url.database==':memory:':
        parser.error('This backup-verifying local runner requires the configured existing SQLite file.')
    path=Path(url.database).resolve()
    root=Path(__file__).resolve().parents[2]
    if not path.is_relative_to(root) or not path.is_file():
        parser.error('The configured database must already exist inside this project.')
    uri=path.as_uri()+'?mode=ro'
    with sqlite3.connect(uri,uri=True) as db:
        record=db.execute('SELECT r.questions_json,r.answers_json,r.reviews_json FROM learning_assessment_results r JOIN assessments a ON a.id=r.assessment_id JOIN students s ON s.id=r.student_id WHERE r.id=? AND r.school_id=a.school_id AND r.class_id=a.class_id AND r.subject_id=a.subject_id AND s.school_id=r.school_id',(args.result_id,)).fetchone()
        if not record:
            parser.error('Existing result with consistent assessment/student relationships required.')
        cols=column_inventory(db)
        cols['learning_assessment_results']=[c for c in cols['learning_assessment_results'] if c not in {'panchapadi_json','panchapadi_version'}]
        before=fingerprint(db,cols)
        other_metadata=list(db.execute('SELECT id,panchapadi_json,panchapadi_version FROM learning_assessment_results WHERE id<>? ORDER BY id',(args.result_id,)))
        if not args.apply:
            print('Existing saved answers and review found. Validation only; --apply creates a backup and provisional evaluation metadata.')
            return
        backup=root/'migration_backups'/('assessment-learning-'+uuid.uuid4().hex+'.backup.db')
        backup.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(backup) as destination:
            db.backup(destination)
            assert fingerprint(destination,cols)==before and destination.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    print('Verified backup:',backup,flush=True)
    from backend.app.services.panchapadi import evaluate_saved_result
    asyncio.run(evaluate_saved_result(args.result_id))
    with sqlite3.connect(uri,uri=True) as db:
        assert fingerprint(db,cols)==before, 'Original values changed during processing; inspect backup before further writes.'
        assert list(db.execute('SELECT id,panchapadi_json,panchapadi_version FROM learning_assessment_results WHERE id<>? ORDER BY id',(args.result_id,)))==other_metadata
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        import json
        metadata=json.loads(db.execute('SELECT panchapadi_json FROM learning_assessment_results WHERE id=?',(args.result_id,)).fetchone()[0])
        attempt=metadata['attempts'][-1]
        print('Original rows, answers and all reviews preserved. Evaluation:',attempt['status'])
        for stage in attempt['stages']:
            print(stage['stage'],stage['score_pct'],stage['status'],stage['evidence_count'],'scored question(s)')
        print('Learning drafts:',len(attempt.get('learning_drafts',[])),attempt.get('guidance_status'))


if __name__=='__main__':
    main()
