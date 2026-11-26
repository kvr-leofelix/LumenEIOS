"""Add AI-assisted learning interventions (proposals assigned through Differentiated Homework)."""
from alembic import op
import sqlalchemy as sa

revision = "0005_learning_interventions"
down_revision = "0004_unmapped_activities"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learning_interventions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("school_id", sa.String(64), nullable=False),
        sa.Column("student_id", sa.String(64), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_id", sa.String(64), nullable=False),
        sa.Column("competency", sa.String(20), nullable=False),
        sa.Column("finding_kind", sa.String(64), nullable=True),
        sa.Column("gap_summary", sa.Text(), nullable=False),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("baseline_score", sa.Float(), nullable=True),
        sa.Column("baseline_checkpoint_json", sa.JSON(), nullable=False),
        sa.Column("learning_objective", sa.Text(), nullable=False),
        sa.Column("recommended_activities_json", sa.JSON(), nullable=False),
        sa.Column("suggested_duration_days", sa.Integer(), nullable=True),
        sa.Column("practice_recommendation_json", sa.JSON(), nullable=False),
        sa.Column("expected_outcome", sa.Text(), nullable=False),
        sa.Column("reassessment_criteria", sa.Text(), nullable=False),
        sa.Column("ai_provider", sa.String(50), nullable=True),
        sa.Column("ai_model", sa.String(100), nullable=True),
        sa.Column("ai_generated", sa.Boolean(), nullable=False),
        sa.Column("teacher_edited", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("created_by_user_id", sa.String(64), nullable=False),
        sa.Column("reviewed_by_user_id", sa.String(64), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("assigned_homework_id", sa.String(64), nullable=True),
        sa.Column("follow_up_evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("follow_up_checkpoint_json", sa.JSON(), nullable=False),
        sa.Column("outcome_status", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    for column in ("school_id", "student_id", "subject_id", "status", "assigned_homework_id"):
        op.create_index("ix_learning_interventions_" + column, "learning_interventions", [column])


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT count(*) FROM learning_interventions")).scalar():
        raise RuntimeError("Intervention history exists. Retain the additive table when rolling back code.")
    op.drop_table("learning_interventions")
