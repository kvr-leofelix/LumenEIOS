from backend.app.db.session import Base
from backend.app.models.entities import (
    User,
    School,
    SchoolMembership,
    ClassSection,
    Subject,
    Student,
    ParentStudentLink,
    InstructionalDisruption,
    Assessment,
    AssessmentSubmission,
    StudentCompetencySnapshot,
    HomeworkRemediation,
    LearningIntervention,
    CurriculumDay,
    CurriculumProposal,
    CrossCurricularProposal,
    Document,
    OCRRun,
    HumanReview,
    DatasetExample,
    ModelEvaluation,
    ModelDeployment,
    Notification,
    Announcement,
    AuditEvent,
)

__all__ = [
    "Base",
    "User",
    "School",
    "SchoolMembership",
    "ClassSection",
    "Subject",
    "Student",
    "ParentStudentLink",
    "InstructionalDisruption",
    "Assessment",
    "AssessmentSubmission",
    "StudentCompetencySnapshot",
    "HomeworkRemediation",
    "LearningIntervention",
    "CurriculumDay",
    "CurriculumProposal",
    "CrossCurricularProposal",
    "Document",
    "OCRRun",
    "HumanReview",
    "DatasetExample",
    "ModelEvaluation",
    "ModelDeployment",
    "Notification",
    "Announcement",
    "AuditEvent",
]


# Explicit catalogue registration; existing model exports remain unchanged.
from backend.app.models.ncert_catalogue import CATALOGUE_MODELS
from backend.app.models.ncert_review import CatalogueMappingDecision
from backend.app.models.planning_workspace import PlanningWorkspaceRevision  # noqa: E402,F401

# Teacher-scoped planning tables (migration 004).
from backend.app.models.teacher_planning import TEACHER_PLANNING_MODELS

# Knowledge-component catalogue and per-student mastery. New tables only.
from backend.app.models.knowledge_components import (  # noqa: E402,F401
    KnowledgeComponent,
    KnowledgeComponentDetail,
    KnowledgeComponentRelationship,
    QuestionBankKcMapping,
    QuestionKcMapping,
    StudentKcAttempt,
    StudentKcMastery,
    StudentQuestionRecommendation,
)

# LearnSphere / assessment-result tables, so init_db sees them regardless of router import order.
from backend.app.modules.learnsphere import models as _learnsphere_models  # noqa: E402,F401
from backend.app.modules.learnsphere import assessment_models as _learnsphere_assessment_models  # noqa: E402,F401

# Personal calendar tasks and deadlines. New table only.
from backend.app.models.calendar_events import PersonalCalendarEvent  # noqa: E402,F401
