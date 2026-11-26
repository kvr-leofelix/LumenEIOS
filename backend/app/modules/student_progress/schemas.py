"""Pydantic contracts for Unified Student Progress (read-only)."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


SourceType = Literal[
    "differentiated_homework",
    "assessment_studio",
    "answer_sheet_ocr",
    "competency_snapshot",
]

Audience = Literal["educator", "student_or_parent"]

RecommendationKind = Literal[
    "weak_subject",
    "low_competency",
    "improving_trend",
    "declining_trend",
    "missing_assessment",
    "incomplete_homework",
]


class CompetencyScoresOut(BaseModel):
    LU: int
    CU: int
    AU: int
    CT: int
    overall: int


class OptionalCompetencyScoresOut(BaseModel):
    """Subject-scoped scores. Missing dimensions stay null — never zero-filled."""

    LU: Optional[float] = None
    CU: Optional[float] = None
    AU: Optional[float] = None
    CT: Optional[float] = None
    overall: Optional[float] = None


class CompetencyEvidenceOut(BaseModel):
    """One verified, subject-linked competency observation."""

    source_type: SourceType
    source_id: str
    assessment_id: Optional[str] = None
    assignment_id: Optional[str] = None
    title: Optional[str] = None
    occurred_at: Optional[str] = None
    awarded_marks: Optional[int] = None
    max_marks: Optional[int] = None
    scores: Optional[OptionalCompetencyScoresOut] = None
    # Single-dimension remediation evidence (when a full vector is not available).
    dimension: Optional[Literal["LU", "CU", "AU", "CT"]] = None
    dimension_value: Optional[float] = None


class SubjectCompetencyProfileOut(BaseModel):
    student_id: str
    subject_id: str
    subject_name: Optional[str] = None
    status: Literal["available", "partial", "unavailable"]
    scores: Optional[OptionalCompetencyScoresOut] = None
    evidence_count: int = 0
    dimension_evidence_counts: Dict[str, int] = Field(default_factory=dict)
    evidence: List[CompetencyEvidenceOut] = Field(default_factory=list)
    methodology: str = "subject_competency.v1.mean_of_comparable_0_100"


class StudentIdentityOut(BaseModel):
    id: str
    name: str
    roll_no: int
    school_id: str
    class_id: str
    class_name: str
    subject_ids: List[str] = Field(default_factory=list)
    subject_names: List[str] = Field(default_factory=list)


class ProgressEventOut(BaseModel):
    """One verified academic outcome. Missing marks stay null (never zero-filled)."""

    id: str
    source_type: SourceType
    source_id: str
    subject_id: Optional[str] = None
    subject_name: Optional[str] = None
    title: Optional[str] = None
    occurred_at: Optional[str] = None
    awarded_marks: Optional[int] = None
    max_marks: Optional[int] = None
    percentage: Optional[float] = None
    evaluation_status: Optional[str] = None
    is_scanned: Optional[bool] = None
    competency_scores: Optional[CompetencyScoresOut] = None
    feedback: Optional[str] = None
    assignment_id: Optional[str] = None
    assessment_id: Optional[str] = None


class SubjectPerformanceOut(BaseModel):
    subject_id: str
    subject_name: Optional[str] = None
    event_count: int
    comparable_event_count: int = 0
    average_percentage: Optional[float] = None
    latest_percentage: Optional[float] = None
    latest_occurred_at: Optional[str] = None
    competencies: Optional[SubjectCompetencyProfileOut] = None


class CompetencyProgressOut(BaseModel):
    current: CompetencyScoresOut
    baseline: CompetencyScoresOut
    source: str = "students.live_scores"
    history: List[ProgressEventOut] = Field(default_factory=list)


class TrendPointOut(BaseModel):
    occurred_at: str
    percentage: float
    subject_id: Optional[str] = None
    subject_name: Optional[str] = None
    source_type: SourceType
    source_id: str
    title: Optional[str] = None


class SubjectTrendOut(BaseModel):
    subject_id: str
    subject_name: Optional[str] = None
    points: List[TrendPointOut] = Field(default_factory=list)


class RecommendationOut(BaseModel):
    kind: RecommendationKind
    summary: str
    evidence: List[str] = Field(default_factory=list)
    subject_id: Optional[str] = None
    competency: Optional[str] = None


class OverallSummaryOut(BaseModel):
    verified_event_count: int
    average_percentage: Optional[float] = None
    latest_activity_at: Optional[str] = None


class StudentProgressOverviewOut(BaseModel):
    student: StudentIdentityOut
    audience: Audience
    overall: OverallSummaryOut
    subjects: List[SubjectPerformanceOut]
    competencies: CompetencyProgressOut
    subject_competencies: List[SubjectCompetencyProfileOut] = Field(default_factory=list)
    recent_activity: List[ProgressEventOut]
    trends: List[TrendPointOut]
    subject_trends: List[SubjectTrendOut]
    recommendations: List[RecommendationOut]
    generated_at: str


class AssessmentHistoryOut(BaseModel):
    student_id: str
    audience: Audience
    events: List[ProgressEventOut]
    generated_at: str


class CompetencyHistoryOut(BaseModel):
    """Global (unscoped) competency history — not subject-inferred."""

    student_id: str
    current: CompetencyScoresOut
    baseline: CompetencyScoresOut
    source: str
    history: List[ProgressEventOut]
    generated_at: str
    subject_competencies: List[SubjectCompetencyProfileOut] = Field(default_factory=list)


class SubjectProgressOut(BaseModel):
    student_id: str
    subject_id: str
    subject_name: Optional[str] = None
    performance: SubjectPerformanceOut
    competencies: SubjectCompetencyProfileOut
    events: List[ProgressEventOut]
    trend: List[TrendPointOut]
    recommendations: List[RecommendationOut]
    generated_at: str
