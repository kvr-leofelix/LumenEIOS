"""Additive planning-workspace revision table, revision 003. No data import, no destructive downgrade.

Run inside an engine.begin transaction against a BACKED-UP or ISOLATED database copy.
Note: the backend's startup init_db() also creates this table (Base.metadata.create_all) on whichever
DATABASE_URL it is started with — start it against an isolated copy if the original DB must stay untouched.
"""
from sqlalchemy import inspect

from backend.app.models.planning_workspace import PlanningWorkspaceRevision

revision = '003_planning_workspace'


def upgrade(connection):
    inspector = inspect(connection)
    table = PlanningWorkspaceRevision.__table__
    if table.name in inspector.get_table_names():
        if {c['name'] for c in inspector.get_columns(table.name)} != set(table.columns.keys()):
            raise RuntimeError('Planning workspace schema mismatch')
    table.create(connection, checkfirst=True)


def downgrade(connection):
    raise RuntimeError('Destructive planning-history downgrade forbidden; restore a backup instead')
