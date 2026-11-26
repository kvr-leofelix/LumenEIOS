"""Adds teacher_topic_coverage.source (MANUAL | EXECUTION), revision 005. Idempotent, additive, no data loss.

Run against a BACKED-UP or ISOLATED database copy.
"""
from sqlalchemy import inspect, text

revision = '005_coverage_source'


def upgrade(connection):
    insp = inspect(connection)
    if 'teacher_topic_coverage' not in insp.get_table_names():
        return  # create_all will build the table with the column
    if 'source' not in {c['name'] for c in insp.get_columns('teacher_topic_coverage')}:
        connection.execute(text("ALTER TABLE teacher_topic_coverage ADD COLUMN source VARCHAR(12) NOT NULL DEFAULT 'MANUAL'"))


def downgrade(connection):
    raise RuntimeError('Destructive downgrade forbidden; restore a backup instead')
