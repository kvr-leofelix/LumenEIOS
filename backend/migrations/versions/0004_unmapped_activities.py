"""Allow assessment-generated activities without an invented topic mapping."""
from alembic import op
import sqlalchemy as sa

revision = "0004_unmapped_activities"
down_revision = "0003_panchapadi"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite needs a table copy for nullability changes. Alembic preserves rows,
    # indexes and foreign keys; the migration runner verifies original values.
    checks=(sa.CheckConstraint("kind IN ('support','teach_back','mission')",name="ck_activity_kind"),
        sa.CheckConstraint("competency IN ('LU','CU','AU','CT')",name="ck_activity_competency"),
        sa.CheckConstraint("stage IN ('Adheeti','Bodh','Abhyas','Prayog','Prasar')",name="ck_activity_stage"))
    with op.batch_alter_table("learning_activities",reflect_kwargs={"resolve_fks":False},table_args=checks) as batch:
        batch.alter_column("topic_id", existing_type=sa.String(64), nullable=True)


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM learning_activities WHERE topic_id IS NULL")).scalar():
        raise RuntimeError("Unmapped assessment activities exist; retain nullable topic links when rolling back code.")
    with op.batch_alter_table("learning_activities",reflect_kwargs={"resolve_fks":False}) as batch:
        batch.alter_column("topic_id", existing_type=sa.String(64), nullable=False)
