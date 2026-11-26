"""Additive teacher-planning tables, revision 004. No data import, no destructive downgrade.

Run inside an engine.begin transaction against a BACKED-UP or ISOLATED database copy.
Note: the backend's startup init_db() also creates these tables (Base.metadata.create_all) on whichever
DATABASE_URL it is started with - start it against an isolated copy if the original DB must stay untouched.
"""
from sqlalchemy import inspect

from backend.app.models.teacher_planning import TEACHER_PLANNING_MODELS

revision = '004_teacher_planning'


def upgrade(connection):
    inspector = inspect(connection)
    existing = set(inspector.get_table_names())
    for model in TEACHER_PLANNING_MODELS:
        table = model.__table__
        if table.name in existing:
            continue  # an existing table is brought up to date by the later additive migrations (005, 006, ...)
        table.create(connection, checkfirst=True)


def downgrade(connection):
    raise RuntimeError('Destructive planning-history downgrade forbidden; restore a backup instead')
