"""Additive catalogue foundation, revision 001. No data import or destructive downgrade.

Run upgrade inside an engine.begin transaction, after backing up an existing DB.
Inspect existing ncert_* tables before upgrading: create_all is not a schema updater.
"""
from sqlalchemy import inspect
from backend.app.models.ncert_catalogue import catalogue_metadata

revision = '001_ncert_catalogue'


def upgrade(connection):
    metadata = catalogue_metadata()
    inspector = inspect(connection)
    existing = set(inspector.get_table_names())
    # Fail closed on incompatible partial/old catalogue schemas.
    for table in metadata.tables.values():
        if table.name in existing:
            actual = {c['name'] for c in inspector.get_columns(table.name)}
            if actual != set(table.columns.keys()):
                raise RuntimeError('Catalogue schema mismatch: ' + table.name)
    metadata.create_all(connection, checkfirst=True)


def downgrade(connection):
    raise RuntimeError('Destructive catalogue downgrade forbidden; restore backup or withdraw release')
