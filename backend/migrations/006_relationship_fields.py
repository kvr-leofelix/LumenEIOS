"""Adds relationship kind/explanation/evidence/shared periods/lead/status/origin to teacher_topic_relationships, revision 006.

Idempotent and additive. Run against a BACKED-UP or ISOLATED database copy.
"""
from sqlalchemy import inspect, text

revision = '006_relationship_fields'
COLUMNS = {
    'kind': "VARCHAR(16) NOT NULL DEFAULT 'PREREQUISITE'",
    'explanation': 'TEXT',
    'evidence': 'TEXT',
    'shared_periods': 'INTEGER NOT NULL DEFAULT 0',
    'lead_topic_key': 'VARCHAR(64)',
    'status': "VARCHAR(12) NOT NULL DEFAULT 'active'",
    'origin': "VARCHAR(24) NOT NULL DEFAULT 'teacher'",
}


def upgrade(connection):
    insp = inspect(connection)
    if 'teacher_topic_relationships' not in insp.get_table_names():
        return
    have = {c['name'] for c in insp.get_columns('teacher_topic_relationships')}
    for name, ddl in COLUMNS.items():
        if name not in have:
            connection.execute(text(f'ALTER TABLE teacher_topic_relationships ADD COLUMN {name} {ddl}'))


def downgrade(connection):
    raise RuntimeError('Destructive downgrade forbidden; restore a backup instead')
