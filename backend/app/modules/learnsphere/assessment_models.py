"""Assessment-source extension; never represents an assessment as a learning activity."""
from sqlalchemy import Column, String, Integer, JSON, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.app.db.session import Base
from backend.app.models.entities import generate_uuid, utc_now


class AssessmentResultRecord(Base):
    __tablename__ = "learning_assessment_results"
    id = Column(String(64), primary_key=True, default=generate_uuid)
    assessment_id = Column(String(64), ForeignKey("assessments.id"), nullable=False, index=True)
    student_id = Column(String(64), ForeignKey("students.id"), nullable=False, index=True)
    school_id = Column(String(64), ForeignKey("schools.id"), nullable=False, index=True)
    class_id = Column(String(64), ForeignKey("classes.id"), nullable=False)
    subject_id = Column(String(64), ForeignKey("subjects.id"), nullable=False)
    submission_id = Column(String(64), ForeignKey("assessment_submissions.id"), nullable=True, unique=True)
    submission = relationship("AssessmentSubmission")
    request_key = Column(String(64), nullable=False)
    questions_json = Column(JSON, nullable=False)
    answers_json = Column(JSON, nullable=False)
    automatic_json = Column(JSON, nullable=False)
    reviews_json = Column(JSON, default=list, nullable=False)
    # Nullable additive columns: old results/reviews remain untouched. AI metadata
    # has its own CAS version so background evaluation does not stale grade forms.
    panchapadi_json = Column(JSON, nullable=True)
    panchapadi_version = Column(Integer, nullable=True)
    submitted_at = Column(DateTime, default=utc_now, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (UniqueConstraint("assessment_id", "student_id", name="uq_assessment_result_student"),)
