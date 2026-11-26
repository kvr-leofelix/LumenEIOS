"""Personal calendar items (tasks and deadlines a user adds for themselves).

Everything else on the calendar (holidays, exams, session days, assessments, homework deadlines) is derived from
existing records at read time, so this is the only table the calendar owns. New table only: created by create_all,
no existing table is altered.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text

from backend.app.db.session import Base
from backend.app.models.entities import generate_uuid, utc_now


class PersonalCalendarEvent(Base):
    __tablename__ = "personal_calendar_events"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    school_id = Column(String(64), nullable=True)
    title = Column(String(120), nullable=False)
    kind = Column(String(20), default="TASK", nullable=False)  # TASK or DEADLINE
    start_date = Column(String(10), nullable=False, index=True)  # ISO YYYY-MM-DD
    end_date = Column(String(10), nullable=True)  # ISO, inclusive; empty for a single day
    notes = Column(Text, nullable=True)
    is_done = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
