"""Additive editorial audit table; run after 001, in a backed-up transaction."""
from sqlalchemy import inspect
from backend.app.models.ncert_review import CatalogueMappingDecision

revision = '002_ncert_mapping_decisions'


def upgrade(connection):
    inspector = inspect(connection)
    if 'ncert_relationships' not in inspector.get_table_names():
        raise RuntimeError('Run 001_ncert_catalogue first')
    table = CatalogueMappingDecision.__table__
    if table.name in inspector.get_table_names():
        if {c['name'] for c in inspector.get_columns(table.name)} != set(table.columns.keys()):
            raise RuntimeError('Catalogue review schema mismatch')
    table.create(connection, checkfirst=True)


def downgrade(connection):
    raise RuntimeError('Destructive audit-history downgrade forbidden')
