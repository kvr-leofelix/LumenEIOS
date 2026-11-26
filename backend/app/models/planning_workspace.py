"""Append-only revisions of the curriculum-planning workspace (one document per school).

Each save inserts a new row; rows are never updated or deleted, so every configuration, approval,
execution record and recovery decision remains recoverable. The (school_id, revision) unique
constraint makes concurrent writers fail instead of overwriting each other.
"""
from sqlalchemy import JSON, CheckConstraint, Column, DateTime, Integer, String, Text, UniqueConstraint

from backend.app.db.session import Base
from backend.app.models.entities import generate_uuid, utc_now


class PlanningWorkspaceRevision(Base):
    __tablename__ = "planning_workspace_revisions"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    school_id = Column(String(64), nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    action = Column(String(40), nullable=False)
    summary = Column(Text, nullable=False)
    actor_id = Column(String(64), nullable=False)
    actor_name = Column(String(255), nullable=False)
    actor_role = Column(String(50), nullable=False)
    state = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("school_id", "revision", name="uq_planning_workspace_school_revision"),
        CheckConstraint("revision >= 1", name="ck_planning_workspace_revision_positive"),
    )
