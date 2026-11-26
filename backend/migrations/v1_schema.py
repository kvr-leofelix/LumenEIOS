from sqlalchemy import Column, String, Text, Integer, Float, Boolean, DateTime, ForeignKey, JSON, UniqueConstraint, CheckConstraint
# Frozen v1 schema: do not import application models into historical migrations.
import uuid
from datetime import datetime, timezone
from sqlalchemy import Table
from sqlalchemy.orm import declarative_base
Base = declarative_base()
def generate_uuid():
    return str(uuid.uuid4())
def utc_now():
    return datetime.now(timezone.utc)
for name in ('schools', 'classes', 'subjects', 'users', 'students'):
    Table(name, Base.metadata, Column('id', String(64), primary_key=True))


class LearningTopic(Base):
    __tablename__ = "learning_topics"
    id = Column(String(64), primary_key=True, default=generate_uuid)
    school_id = Column(String(64), ForeignKey("schools.id"), nullable=False, index=True)
    class_id = Column(String(64), ForeignKey("classes.id"), nullable=False, index=True)
    subject_id = Column(String(64), ForeignKey("subjects.id"), nullable=False)
    title = Column(String(255), nullable=False)
    created_by = Column(String(64), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class LearningActivity(Base):
    __tablename__ = "learning_activities"
    id = Column(String(64), primary_key=True, default=generate_uuid)
    topic_id = Column(String(64), ForeignKey("learning_topics.id"), nullable=False, index=True)
    kind = Column(String(30), nullable=False)
    title = Column(String(255), nullable=False)
    instructions = Column(Text, nullable=False)
    rubric = Column(Text, nullable=False)
    competency = Column(String(2), nullable=False)
    stage = Column(String(20), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    created_by = Column(String(64), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    __table_args__ = (
        CheckConstraint("kind IN ('support','teach_back','mission')"),
        CheckConstraint("competency IN ('LU','CU','AU','CT')"),
        CheckConstraint("stage IN ('Adheeti','Bodh','Abhyas','Prayog','Prasar')"),
    )


class LearningAssignment(Base):
    __tablename__ = "learning_assignments"
    id = Column(String(64), primary_key=True, default=generate_uuid)
    activity_id = Column(String(64), ForeignKey("learning_activities.id"), nullable=False)
    student_id = Column(String(64), ForeignKey("students.id"), nullable=False, index=True)
    school_id = Column(String(64), ForeignKey("schools.id"), nullable=False, index=True)
    snapshot = Column(JSON, nullable=False)
    assigned_by = Column(String(64), ForeignKey("users.id"), nullable=False)
    request_key = Column(String(64), nullable=False)
    intervention_for = Column(String(64), ForeignKey("learning_assignments.id"), nullable=True)
    assigned_at = Column(DateTime, default=utc_now, nullable=False)
    due_at = Column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("assigned_by", "request_key", "student_id"),)


class LearningAttempt(Base):
    __tablename__ = "learning_attempts"
    id = Column(String(64), primary_key=True, default=generate_uuid)
    assignment_id = Column(String(64), ForeignKey("learning_assignments.id"), nullable=False, index=True)
    request_key = Column(String(64), nullable=False)
    response = Column(Text, nullable=False)
    hints = Column(Integer, nullable=True)
    submitted_at = Column(DateTime, default=utc_now, nullable=False)
    # Revisions are appended, never replaced. AI revisions carry no verified score.
    evaluations = Column(JSON, default=list, nullable=False)
    completed = Column(Boolean, default=False, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (UniqueConstraint("assignment_id", "request_key"),
                      CheckConstraint("hints IS NULL OR hints >= 0"))


class LearningEvidence(Base):
    __tablename__ = "learning_evidence"
    id = Column(String(64), primary_key=True, default=generate_uuid)
    student_id = Column(String(64), ForeignKey("students.id"), nullable=False, index=True)
    assignment_id = Column(String(64), ForeignKey("learning_assignments.id"), nullable=False, index=True)
    attempt_id = Column(String(64), ForeignKey("learning_attempts.id"), nullable=False)
    source = Column(String(50), nullable=False)
    observation_key = Column(String(100), nullable=False)
    competency = Column(String(2), nullable=False)
    score = Column(Float, nullable=True)
    maximum = Column(Float, nullable=True)
    correct = Column(Boolean, nullable=True)
    provenance = Column(String(30), nullable=False)
    scoring_basis = Column(String(64), nullable=False)
    recorded_at = Column(DateTime, default=utc_now, nullable=False)
    __table_args__ = (
        UniqueConstraint("source", "attempt_id", "observation_key"),
        CheckConstraint("(score IS NULL AND maximum IS NULL) OR (score IS NOT NULL AND maximum IS NOT NULL AND maximum > 0 AND score >= 0 AND score <= maximum)"),
        CheckConstraint("competency IN ('LU','CU','AU','CT')"),
        CheckConstraint("provenance IN ('confirmed','submitted','legacy_uncertain','simulated')"),
    )
