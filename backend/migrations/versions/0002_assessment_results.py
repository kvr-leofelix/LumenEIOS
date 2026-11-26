"""Add a genuine assessment response/evidence source, without changing existing tables."""
from alembic import op
import sqlalchemy as sa

revision = "0002_assessment_results"
down_revision = "0001_learnsphere"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("learning_assessment_results",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("assessment_id", sa.String(64), sa.ForeignKey("assessments.id"), nullable=False),
        sa.Column("student_id", sa.String(64), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("school_id", sa.String(64), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("class_id", sa.String(64), sa.ForeignKey("classes.id"), nullable=False),
        sa.Column("subject_id", sa.String(64), sa.ForeignKey("subjects.id"), nullable=False),
        sa.Column("submission_id", sa.String(64), sa.ForeignKey("assessment_submissions.id"), nullable=True, unique=True),
        sa.Column("request_key", sa.String(64), nullable=False),
        sa.Column("questions_json", sa.JSON(), nullable=False),
        sa.Column("answers_json", sa.JSON(), nullable=False),
        sa.Column("automatic_json", sa.JSON(), nullable=False),
        sa.Column("reviews_json", sa.JSON(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("assessment_id", "student_id", name="uq_assessment_result_student"))
    for column in ("assessment_id", "student_id", "school_id"):
        op.create_index("ix_learning_assessment_results_"+column, "learning_assessment_results", [column])


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT count(*) FROM learning_assessment_results")).scalar():
        raise RuntimeError("Assessment history exists. Retain the additive table when rolling back code.")
    op.drop_table("learning_assessment_results")
