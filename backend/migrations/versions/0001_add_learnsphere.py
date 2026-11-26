"""Add LearnSphere only. Existing application tables and records are untouched."""
from alembic import op
from backend.migrations.v1_schema import Base

revision = "0001_learnsphere"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    for table in Base.metadata.sorted_tables:
        if table.name.startswith("learning_"):
            table.create(bind=op.get_bind(), checkfirst=False)


def downgrade():
    from sqlalchemy import select, func
    tables = [t for t in Base.metadata.sorted_tables if t.name.startswith("learning_")]
    if any(op.get_bind().scalar(select(func.count()).select_from(t)) for t in tables):
        raise RuntimeError("Downgrade refused: learning history exists. Roll back code and retain tables.")
    for table in reversed(tables):
        op.drop_table(table.name)
