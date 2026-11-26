from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from backend.app.schemas.panchapadi import AssessmentStages

Competency = Literal["LU", "CU", "AU", "CT"]
Stage = Literal["Adheeti", "Bodh", "Abhyas", "Prayog", "Prasar"]
Kind = Literal["support", "teach_back", "mission"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TopicCreate(Input):
    class_id: str
    subject_id: str
    title: str = Field(min_length=1, max_length=255)


class ActivityCreate(Input):
    topic_id: str
    kind: Kind
    title: str = Field(min_length=1, max_length=255)
    instructions: str = Field(min_length=1, max_length=12000)
    rubric: str = Field(min_length=1, max_length=12000)
    competency: Competency
    stage: Stage


class AssignmentCreate(Input):
    student_ids: list[str] = Field(min_length=1, max_length=200)
    request_key: str = Field(min_length=1, max_length=64)
    due_at: datetime | None = None
    intervention_for: str | None = None


class AttemptCreate(Input):
    response: str = Field(min_length=1, max_length=16000)
    request_key: str = Field(min_length=1, max_length=64)
    hints: StrictInt | None = Field(default=None, ge=0, le=1000)


class Observation(Input):
    key: str = Field(min_length=1, max_length=60)
    score: float = Field(ge=0, allow_inf_nan=False)
    maximum: float = Field(gt=0, allow_inf_nan=False)
    correct: bool | None = None

    @model_validator(mode="after")
    def valid_score(self):
        if self.score > self.maximum:
            raise ValueError("Score cannot exceed the denominator.")
        return self


class Review(Input):
    expected_version: StrictInt
    feedback: str = Field(min_length=1, max_length=12000)
    outcome: str = Field(min_length=1, max_length=4000)
    completed: bool
    observations: list[Observation] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def unique_observations(self):
        if len({o.key for o in self.observations}) != len(self.observations):
            raise ValueError("Observation keys must be distinct.")
        if self.observations and not self.completed:
            raise ValueError("Scored evidence requires a completed activity.")
        return self


class TeachBackFeedback(Input):
    correctly_understood: list[str] = Field(max_length=20)
    missing_concepts: list[str] = Field(max_length=20)
    misconceptions: list[str] = Field(max_length=20)
    strengths: list[str] = Field(max_length=20)
    next_step: str = Field(min_length=1, max_length=3000)

    @model_validator(mode="after")
    def bounded_feedback(self):
        for items in (self.correctly_understood, self.missing_concepts, self.misconceptions, self.strengths):
            if any(not item.strip() or len(item) > 3000 for item in items):
                raise ValueError("Feedback items must contain 1–3000 characters.")
        return self


class TopicOut(BaseModel):
    id: str
    school_id: str
    class_id: str
    subject_id: str
    title: str


class ActivityOut(ActivityCreate):
    id: str
    version: int


class Snapshot(ActivityOut):
    topic_id: str | None = None
    topic_title: str
    subject_id: str
    class_id: str
    assessment_result_id: str | None = None
    assessment_id: str | None = None
    evidence_positions: list[int] = Field(default_factory=list)
    generation: str | None = None


class EvaluationOut(BaseModel):
    kind: Literal["teacher", "ai", "ai_failure"]
    date: datetime
    revision_id: str | None = None
    feedback: TeachBackFeedback | str | None = None
    outcome: str | None = None
    error: str | None = None
    completed: bool | None = None
    reviewer_id: str | None = None


class AttemptOut(BaseModel):
    id: str
    assignment_id: str
    response: str
    hints: int | None
    submitted_at: datetime
    evaluations: list[EvaluationOut]
    completed: bool
    version: int


class AssignmentOut(BaseModel):
    id: str
    student_id: str
    snapshot: Snapshot
    assigned_at: datetime
    due_at: datetime | None
    intervention_for: str | None
    attempts: list[AttemptOut]


class StudentScope(BaseModel):
    id: str
    name: str
    class_id: str
    school_id: str


class SubjectScope(BaseModel):
    id: str
    name: str


class ClassScope(BaseModel):
    id: str
    name: str
    school_id: str
    subjects: list[SubjectScope]


class ScopeOut(BaseModel):
    students: list[StudentScope]
    classes: list[ClassScope]
    schools: list[SubjectScope]


class SourceOut(BaseModel):
    id: str
    assignment_id: str
    attempt_id: str
    score: float
    maximum: float
    correct: bool | None
    hints: int | None
    recorded_at: datetime
    source: str


class FindingOut(BaseModel):
    subject_id: str
    topic_id: str
    topic: str
    competency: Competency
    observations: int
    activities: int
    score_pct: float | None
    status: str
    reason: str
    rule: str
    suggestion: str
    sources: list[SourceOut]


class SupportOut(BaseModel):
    student_id: str
    findings: list[FindingOut]
    empty_message: str | None
    assessment_findings: list["AssessmentFinding"] = Field(default_factory=list)
    panchapadi_assessments: list[AssessmentStages] = Field(default_factory=list)


class AssessmentObservation(BaseModel):
    id: str
    result_id: str
    submission_id: str
    assessment_id: str
    assessment_title: str
    subject_id: str
    topic_id: str | None
    topic: str | None
    competency: Competency
    score: float
    maximum: float
    correct: bool | None
    source: str
    recorded_at: datetime
    provenance: str
    scoring_basis: str


class AssessmentFinding(BaseModel):
    subject_id: str
    topic_id: str | None
    topic: str | None
    competency: Competency
    observations: int
    assessments: int
    score_pct: float
    reason: str
    status: str
    suggestion: str
    sources: list[AssessmentObservation]


class TimelineEvent(BaseModel):
    kind: str
    date: datetime
    title: str
    stage: Stage | None
    topic: str | None
    subject_id: str | None
    competency: Competency | None
    detail: str
    assignment_id: str | None = None
    intervention_for: str | None = None


class TrendPoint(BaseModel):
    date: datetime
    score_pct: float


class TrendOut(BaseModel):
    subject_id: str
    topic_id: str
    topic: str
    competency: Competency
    scoring_basis: str
    points: list[TrendPoint]
    change: float | None


class JourneyOut(BaseModel):
    student_id: str
    timeline: list[TimelineEvent]
    trends: list[TrendOut]
    participation: int
    completed_assignments: int
    verified_observations: int
    stages: dict[Stage, int]
    assessment_observations: list[AssessmentObservation] = Field(default_factory=list)
    panchapadi_assessments: list[AssessmentStages] = Field(default_factory=list)


class SummaryOut(BaseModel):
    students: int
    assignments: int
    completed_assignments: int


class AssignmentCreated(BaseModel):
    assignment_ids: list[str]
