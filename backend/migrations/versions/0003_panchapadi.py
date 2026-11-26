"""Add nullable assessment-stage evaluation metadata; no historical data backfill."""
from alembic import op
import sqlalchemy as sa

revision = "0003_panchapadi"
down_revision = "0002_assessment_results"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("learning_assessment_results", sa.Column("panchapadi_json", sa.JSON(), nullable=True))
    op.add_column("learning_assessment_results", sa.Column("panchapadi_version", sa.Integer(), nullable=True))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM learning_assessment_results WHERE panchapadi_json IS NOT NULL")).scalar():
        raise RuntimeError("Panchapadi history exists. Retain these additive columns when rolling back code.")
    op.drop_column("learning_assessment_results", "panchapadi_version")
    op.drop_column("learning_assessment_results", "panchapadi_json")
