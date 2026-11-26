"""Teacher-scoped planning records (additive, migration 004).

Shared: `PlanTopic` (syllabus identity). Per teacher: configuration, coverage, relationships, lost periods.
Per school: calendar versions. One structured, append-only `PlanAuditEvent` table backs both the central
Logs page and every module's contextual history.
"""
from sqlalchemy import JSON, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, event

from backend.app.db.session import Base
from backend.app.models.entities import generate_uuid, utc_now


class PlanTopic(Base):
    """Shared syllabus topic identity. Seeded only from source-verified crosswalk rows; no content text."""
    __tablename__ = "plan_topics"

    topic_key = Column(String(64), primary_key=True)
    grade = Column(Integer, nullable=False, index=True)
    subject = Column(String(32), nullable=False, index=True)
    chapter_number = Column(String(16), nullable=False)
    chapter_title = Column(String(255), nullable=False)
    section_label = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=False)
    source_ref = Column(String(128), nullable=True)


class SchoolPlanCalendar(Base):
    """Append-only calendar/timetable versions per school and year; latest version is current."""
    __tablename__ = "school_plan_calendars"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    school_id = Column(String(64), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    academic_year = Column(String(32), nullable=False)
    version = Column(Integer, nullable=False)
    config = Column(JSON, nullable=False)
    reason = Column(Text, nullable=True)
    created_by = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    __table_args__ = (UniqueConstraint("school_id", "academic_year", "version", name="uq_plan_calendar_version"),)


_TEACHER_KEY = dict(nullable=False, index=True)


class TeacherTopicConfig(Base):
    __tablename__ = "teacher_topic_configs"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    school_id = Column(String(64), ForeignKey("schools.id", ondelete="CASCADE"), **_TEACHER_KEY)
    teacher_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), **_TEACHER_KEY)
    academic_year = Column(String(32), nullable=False)
    grade = Column(Integer, nullable=False)
    subject = Column(String(32), nullable=False)
    topic_key = Column(String(64), ForeignKey("plan_topics.topic_key", ondelete="RESTRICT"), nullable=False)
    classification = Column(String(16), nullable=False)  # core | non_core | mixed
    core_periods = Column(Integer, nullable=False)
    non_core_periods = Column(Integer, nullable=False)
    teaching_mode = Column(String(16), nullable=False, default="INDEPENDENT", server_default="INDEPENDENT")  # SHARED | INDEPENDENT (demo default or teacher choice)
    independent_periods = Column(Integer, nullable=False, default=0, server_default="0")  # subset of Non-Core; never classroom completion
    origin = Column(String(24), nullable=False, default="demo_default")  # demo_default | teacher | approved_import
    version = Column(Integer, nullable=False, default=1)
    updated_by = Column(String(64), nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    __table_args__ = (
        UniqueConstraint("school_id", "teacher_id", "academic_year", "grade", "subject", "topic_key", name="uq_teacher_topic_config"),
        CheckConstraint("core_periods >= 0 AND non_core_periods >= 0", name="ck_teacher_topic_config_nonneg"),
        CheckConstraint("independent_periods >= 0 AND independent_periods <= non_core_periods", name="ck_teacher_topic_config_independent_noncore"),
    )


class TeacherTopicCoverage(Base):
    __tablename__ = "teacher_topic_coverage"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    school_id = Column(String(64), ForeignKey("schools.id", ondelete="CASCADE"), **_TEACHER_KEY)
    teacher_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), **_TEACHER_KEY)
    academic_year = Column(String(32), nullable=False)
    grade = Column(Integer, nullable=False)
    subject = Column(String(32), nullable=False)
    topic_key = Column(String(64), ForeignKey("plan_topics.topic_key", ondelete="RESTRICT"), nullable=False)
    status = Column(String(16), nullable=False, default="not_done")  # done | in_progress | not_done
    source = Column(String(12), nullable=False, default="MANUAL", server_default="MANUAL")  # MANUAL | EXECUTION
    updated_by = Column(String(64), nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    __table_args__ = (
        UniqueConstraint("school_id", "teacher_id", "academic_year", "grade", "subject", "topic_key", name="uq_teacher_topic_coverage"),
        CheckConstraint("status IN ('done','in_progress','not_done')", name="ck_teacher_coverage_status"),
    )


class TeacherTopicRelationship(Base):
    __tablename__ = "teacher_topic_relationships"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    school_id = Column(String(64), ForeignKey("schools.id", ondelete="CASCADE"), **_TEACHER_KEY)
    teacher_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), **_TEACHER_KEY)
    academic_year = Column(String(32), nullable=False)
    topic_key = Column(String(64), ForeignKey("plan_topics.topic_key", ondelete="RESTRICT"), nullable=False)
    # PREREQUISITE: prerequisite_key must be taught before topic_key. CROSS_CURRICULAR: prerequisite_key is the "from" unit
    # (Mathematics) and topic_key the "to" unit (Science); sharing is taught once, in lead_topic_key.
    prerequisite_key = Column(String(64), ForeignKey("plan_topics.topic_key", ondelete="RESTRICT"), nullable=False)
    kind = Column(String(16), nullable=False, default="PREREQUISITE", server_default="PREREQUISITE")
    explanation = Column(Text, nullable=True)
    evidence = Column(Text, nullable=True)
    shared_periods = Column(Integer, nullable=False, default=0, server_default="0")
    lead_topic_key = Column(String(64), nullable=True)
    status = Column(String(12), nullable=False, default="active", server_default="active")  # active | removed (soft; history kept)
    origin = Column(String(24), nullable=False, default="teacher", server_default="teacher")  # teacher | approved_import
    created_by = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    __table_args__ = (
        UniqueConstraint("school_id", "teacher_id", "academic_year", "topic_key", "prerequisite_key", name="uq_teacher_topic_relationship"),
        CheckConstraint("topic_key <> prerequisite_key", name="ck_relationship_not_self"),
    )


class TeacherLostPeriod(Base):
    """One row per lost (date, period). Lost days are the distinct dates; lost periods the rows."""
    __tablename__ = "teacher_lost_periods"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    school_id = Column(String(64), ForeignKey("schools.id", ondelete="CASCADE"), **_TEACHER_KEY)
    teacher_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), **_TEACHER_KEY)
    academic_year = Column(String(32), nullable=False)
    grade = Column(Integer, nullable=False)
    subject = Column(String(32), nullable=False)
    lost_date = Column(String(10), nullable=False, index=True)
    period_number = Column(Integer, nullable=False)
    topic_keys = Column(JSON, nullable=False, default=list)
    reason_code = Column(String(32), nullable=False)
    notes = Column(Text, nullable=True)
    recorded_by = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    batch_id = Column(String(64), nullable=True)  # rows recorded in one submission share it
    status = Column(String(12), nullable=False, default="active", server_default="active")  # active | withdrawn (correction)
    withdrawn_reason = Column(Text, nullable=True)
    withdrawn_by = Column(String(64), nullable=True)
    withdrawn_at = Column(DateTime, nullable=True)
    schedule_version = Column(Integer, nullable=True)  # set when an approved recovery absorbs this loss (Step 5); then immutable
    __table_args__ = (
        UniqueConstraint("school_id", "teacher_id", "academic_year", "grade", "subject", "lost_date", "period_number", name="uq_teacher_lost_period"),
        CheckConstraint("period_number >= 1", name="ck_lost_period_positive"),
    )


class TeacherPlan(Base):
    """A teacher's teaching plan for one class and subject. Never shared between teachers."""
    __tablename__ = "teacher_plans"

    id = Column(String(64), primary_key=True)  # client-generated 'plan-...' ids are kept so imported history stays addressable
    school_id = Column(String(64), ForeignKey("schools.id", ondelete="CASCADE"), **_TEACHER_KEY)
    teacher_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), **_TEACHER_KEY)
    academic_year = Column(String(32), nullable=False)
    grade = Column(Integer, nullable=False)
    subject = Column(String(32), nullable=False)
    status = Column(String(12), nullable=False, default="DRAFT")  # DRAFT | APPROVED | SUPERSEDED | REJECTED
    dataset_id = Column(String(128), nullable=False)
    dataset_label = Column(String(255), nullable=False)
    dataset_kind = Column(String(64), nullable=False)
    config = Column(JSON, nullable=False)  # calendar snapshot the schedule was built against
    estimates = Column(JSON, nullable=False, default=dict)
    draft = Column(JSON, nullable=False)  # the generated ScheduleResult submitted for approval (immutable)
    created_by = Column(JSON, nullable=False)  # actor {id, name, role}
    created_at = Column(DateTime, default=utc_now, nullable=False)
    review = Column(JSON, nullable=True)  # {by, at, note, decision}
    superseded_by = Column(String(64), nullable=True)
    origin = Column(String(24), nullable=False, default="teacher")  # teacher | workspace_import


class TeacherPlanVersion(Base):
    """Append-only schedule versions. Version 1 is the original approved schedule and is never overwritten."""
    __tablename__ = "teacher_plan_versions"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    plan_id = Column(String(64), ForeignKey("teacher_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    lessons = Column(JSON, nullable=False)
    metrics = Column(JSON, nullable=False)
    conflicts = Column(JSON, nullable=False)
    config = Column(JSON, nullable=False)
    approved_by = Column(JSON, nullable=False)
    approved_at = Column(String(40), nullable=False)
    reason = Column(Text, nullable=False)
    proposal_id = Column(String(64), nullable=True)
    lost_slots = Column(JSON, nullable=False, default=list)
    __table_args__ = (UniqueConstraint("plan_id", "version", name="uq_plan_version"),)


class TeacherPlanProposal(Base):
    """Recovery / recalculation proposals. Only an approved proposal ever becomes a schedule version."""
    __tablename__ = "teacher_plan_proposals"

    id = Column(String(64), primary_key=True)
    plan_id = Column(String(64), ForeignKey("teacher_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    base_version = Column(Integer, nullable=False)
    status = Column(String(12), nullable=False, default="PENDING")  # PENDING | APPROVED | REJECTED | SUPERSEDED
    trigger = Column(JSON, nullable=False)
    created_by = Column(JSON, nullable=False)
    created_at = Column(String(40), nullable=False)
    payload = Column(JSON, nullable=False)  # the engine's proposal body: lessons, metrics, conflicts, changes, explanation, lostSlots, lossDays ...
    review = Column(JSON, nullable=True)  # {by, at, note}
    sequence = Column(Integer, nullable=False, default=0)


class TeacherPlanExecution(Base):
    """Actual teaching execution. Append-only; a correction is a new event that supersedes an earlier one."""
    __tablename__ = "teacher_plan_execution"

    id = Column(String(64), primary_key=True)
    plan_id = Column(String(64), ForeignKey("teacher_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    node_key = Column(String(64), nullable=False)
    event_date = Column(String(10), nullable=False)
    status = Column(String(24), nullable=False)  # TAUGHT | PARTIAL | HOMEWORK | DEFERRED | HOMEWORK_COMPLETED
    periods_taught = Column(Integer, nullable=False, default=0)
    note = Column(Text, nullable=True)
    recorded_by = Column(JSON, nullable=False)
    recorded_at = Column(String(40), nullable=False)
    supersedes = Column(String(64), nullable=True)
    schedule_version = Column(Integer, nullable=False)
    sequence = Column(Integer, nullable=False, default=0)


class TeacherPlanEvidence(Base):
    __tablename__ = "teacher_plan_evidence"

    id = Column(String(64), primary_key=True)
    plan_id = Column(String(64), ForeignKey("teacher_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    node_key = Column(String(64), nullable=False)
    kind = Column(String(16), nullable=False)
    reference = Column(Text, nullable=False)
    result = Column(Text, nullable=False)
    recorded_by = Column(JSON, nullable=False)
    recorded_at = Column(String(40), nullable=False)
    sequence = Column(Integer, nullable=False, default=0)


class PlanAuditEvent(Base):
    """Append-only. Corrections are new events that reference the original via `related_event_id`."""
    __tablename__ = "plan_audit_events"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    occurred_at = Column(DateTime, default=utc_now, nullable=False, index=True)
    actor_id = Column(String(64), nullable=False)
    actor_name = Column(String(255), nullable=False)
    actor_role = Column(String(32), nullable=False)
    school_id = Column(String(64), nullable=False, index=True)
    teacher_id = Column(String(64), nullable=True, index=True)
    grade = Column(Integer, nullable=True)
    subject = Column(String(32), nullable=True)
    topic_keys = Column(JSON, nullable=False, default=list)
    category = Column(String(40), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="recorded")
    previous_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    reason = Column(Text, nullable=True)
    schedule_version = Column(Integer, nullable=True)
    related_event_id = Column(String(64), nullable=True)
    related_proposal_id = Column(String(64), nullable=True)
    summary = Column(String(500), nullable=False)


class AppendOnlyError(RuntimeError):
    pass


@event.listens_for(PlanAuditEvent, "before_update")
def _block_update(mapper, connection, target):
    raise AppendOnlyError("Plan audit events are append-only; record a correcting event instead.")


@event.listens_for(PlanAuditEvent, "before_delete")
def _block_delete(mapper, connection, target):
    raise AppendOnlyError("Plan audit events are append-only and cannot be deleted.")


TEACHER_PLANNING_MODELS = [PlanTopic, SchoolPlanCalendar, TeacherTopicConfig, TeacherTopicCoverage,
                           TeacherTopicRelationship, TeacherLostPeriod, TeacherPlan, TeacherPlanVersion, TeacherPlanProposal,
                           TeacherPlanExecution, TeacherPlanEvidence, PlanAuditEvent]


def _forbid(msg):
    def guard(mapper, connection, target):
        raise AppendOnlyError(msg)
    return guard


for _model, _what in ((TeacherPlanVersion, "Schedule versions"), (TeacherPlanExecution, "Execution records"), (TeacherPlanEvidence, "Evidence records")):
    event.listen(_model, "before_update", _forbid(f"{_what} are append-only; record a new one instead."))
    event.listen(_model, "before_delete", _forbid(f"{_what} are append-only and cannot be deleted."))
