"""Adds batch id, soft-withdrawal fields and the approved-schedule link to teacher_lost_periods, revision 007.

Idempotent and additive. Run against a BACKED-UP or ISOLATED database copy.
"""
from sqlalchemy import inspect, text

revision = '007_lost_period_fields'
COLUMNS = {
    'batch_id': 'VARCHAR(64)',
    'status': "VARCHAR(12) NOT NULL DEFAULT 'active'",
    'withdrawn_reason': 'TEXT',
    'withdrawn_by': 'VARCHAR(64)',
    'withdrawn_at': 'DATETIME',
    'schedule_version': 'INTEGER',
}


def upgrade(connection):
    insp = inspect(connection)
    if 'teacher_lost_periods' not in insp.get_table_names():
        return
    have = {c['name'] for c in insp.get_columns('teacher_lost_periods')}
    for name, ddl in COLUMNS.items():
        if name not in have:
            connection.execute(text(f'ALTER TABLE teacher_lost_periods ADD COLUMN {name} {ddl}'))


def downgrade(connection):
    raise RuntimeError('Destructive downgrade forbidden; restore a backup instead')
