"""Knowledge Component graph tables.

These are new tables on the existing SQLAlchemy Base. Startup `create_all` creates
missing tables and does not alter `students`, `assessment_submissions`, or the
OCR tables. The catalogue is shared. Mastery and attempt rows are per student.

Relationships are written only by a teacher or admin. Question mapping may name
an existing component id; it cannot insert a component or an edge.
"""
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from backend.app.db.session import Base
from backend.app.models.entities import generate_uuid, utc_now

RELATIONSHIP_TYPES = ("PREREQUISITE_OF", "RELATED_TO", "PART_OF")
COMPETENCIES = ("LU", "CU", "CT", "AU")
LEARNING_STATUSES = ("not_assessed", "proficient", "developing", "needs_improvement")


class KnowledgeComponent(Base):
    __tablename__ = "knowledge_components"
    __table_args__ = (
        UniqueConstraint("subject_id", "name_key", "topic_key", name="uq_knowledge_component_identity"),
    )

    id = Column(String(64), primary_key=True, default=generate_uuid)
    name = Column(String(200), nullable=False)
    name_key = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    subject_id = Column(String(64), ForeignKey("subjects.id"), nullable=False, index=True)
    subject_name = Column(String(100), nullable=False)
    topic = Column(String(200), nullable=False)
    topic_key = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class KnowledgeComponentRelationship(Base):
    __tablename__ = "knowledge_component_relationships"
    __table_args__ = (
        CheckConstraint(
            "relationship IN ('PREREQUISITE_OF', 'RELATED_TO', 'PART_OF')",
            name="ck_kc_relationship_type",
        ),
        UniqueConstraint("source_id", "target_id", "relationship", name="uq_kc_relationship"),
    )

    id = Column(String(64), primary_key=True, default=generate_uuid)
    source_id = Column(String(64), ForeignKey("knowledge_components.id", ondelete="CASCADE"), nullable=False, index=True)
    target_id = Column(String(64), ForeignKey("knowledge_components.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship = Column(String(40), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class QuestionKcMapping(Base):
    __tablename__ = "question_kc_mappings"
    __table_args__ = (
        UniqueConstraint("assessment_id", "question_id", "kc_id", name="uq_question_kc_mapping"),
    )

    id = Column(String(64), primary_key=True, default=generate_uuid)
    assessment_id = Column(String(64), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(String(64), nullable=False)
    question_text_hash = Column(String(64), nullable=False)
    kc_id = Column(String(64), ForeignKey("knowledge_components.id", ondelete="CASCADE"), nullable=False, index=True)
    relevance = Column(Float, nullable=False, default=1.0)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class StudentKcMastery(Base):
    __tablename__ = "student_kc_mastery"
    __table_args__ = (
        CheckConstraint(
            "learning_status IN ('not_assessed', 'proficient', 'developing', 'needs_improvement')",
            name="ck_student_kc_learning_status",
        ),
        UniqueConstraint("student_id", "kc_id", name="uq_student_kc_mastery"),
    )

    id = Column(String(64), primary_key=True, default=generate_uuid)
    student_id = Column(String(64), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    kc_id = Column(String(64), ForeignKey("knowledge_components.id", ondelete="CASCADE"), nullable=False, index=True)
    lu_mastery = Column(Float, nullable=True)
    cu_mastery = Column(Float, nullable=True)
    ct_mastery = Column(Float, nullable=True)
    au_mastery = Column(Float, nullable=True)
    overall_mastery = Column(Float, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    correct_count = Column(Integer, nullable=False, default=0)
    incorrect_count = Column(Integer, nullable=False, default=0)
    learning_status = Column(String(40), nullable=False, default="not_assessed")
    last_assessed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=utc_now, nullable=False)


class KnowledgeComponentDetail(Base):
    """Optional curriculum metadata. The concept row stays the identity."""

    __tablename__ = "knowledge_component_details"

    kc_id = Column(String(64), ForeignKey("knowledge_components.id", ondelete="CASCADE"), primary_key=True)
    grade_label = Column(String(20), nullable=False, default="")
    chapter = Column(String(200), nullable=False, default="")
    subtopic = Column(String(200), nullable=False, default="")
    learning_objective = Column(Text, nullable=False, default="")
    difficulty = Column(String(40), nullable=False, default="standard")
    assessment_criteria = Column(Text, nullable=False, default="")
    source_reference = Column(Text, nullable=False, default="")
    stable_code = Column(String(80), nullable=True, unique=True)


class QuestionBankKcMapping(Base):
    """Teacher-confirmed concepts for a bank question, before a paper is published."""

    __tablename__ = "question_bank_kc_mappings"
    __table_args__ = (
        UniqueConstraint("question_bank_item_id", "kc_id", name="uq_bank_kc_mapping"),
    )

    id = Column(String(64), primary_key=True, default=generate_uuid)
    question_bank_item_id = Column(
        String(64), ForeignKey("question_bank_items.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    kc_id = Column(String(64), ForeignKey("knowledge_components.id", ondelete="CASCADE"), nullable=False, index=True)
    relevance = Column(Float, nullable=False, default=1.0)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class StudentQuestionRecommendation(Base):
    """A bank question already offered to one student. The next pass skips it."""

    __tablename__ = "student_question_recommendations"
    __table_args__ = (
        UniqueConstraint("student_id", "question_bank_item_id", name="uq_student_question_recommendation"),
    )

    id = Column(String(64), primary_key=True, default=generate_uuid)
    student_id = Column(String(64), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    question_bank_item_id = Column(
        String(64), ForeignKey("question_bank_items.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    kc_id = Column(String(64), ForeignKey("knowledge_components.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(40), nullable=False)
    reason = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=utc_now, nullable=False)


class StudentKcAttempt(Base):
    """One question-level observation. Mastery is recalculated from these rows."""

    __tablename__ = "student_kc_attempts"
    __table_args__ = (
        CheckConstraint("competency IN ('LU', 'CU', 'CT', 'AU')", name="ck_student_kc_attempt_competency"),
        UniqueConstraint(
            "student_id", "source_key", "question_id", "kc_id", name="uq_student_kc_attempt",
        ),
    )

    id = Column(String(64), primary_key=True, default=generate_uuid)
    student_id = Column(String(64), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    kc_id = Column(String(64), ForeignKey("knowledge_components.id", ondelete="CASCADE"), nullable=False, index=True)
    assessment_id = Column(String(64), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(String(64), nullable=False)
    source_key = Column(String(64), nullable=False)
    competency = Column(String(8), nullable=False)
    score = Column(Float, nullable=False)
    relevance = Column(Float, nullable=False)
    awarded_marks = Column(Float, nullable=False)
    max_marks = Column(Float, nullable=False)
    correct = Column(Boolean, nullable=False, default=False)
    assessed_at = Column(DateTime, default=utc_now, nullable=False)
