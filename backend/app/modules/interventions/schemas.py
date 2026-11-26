"""Pydantic schemas for interventions (API + AI structured output)."""
from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

CompetencyDim = Literal["LU", "CU", "AU", "CT"]
InterventionStatus = Literal[
    "draft",
    "pending_review",
    "approved",
    "assigned",
    "completed",
    "rejected",
    "cancelled",
]


class AIInterventionContent(BaseModel):
    """Strict schema for AI-generated proposal *content* only.

    Evidence references and scores are attached by the backend from verified
    ledger data — the model must not invent them.
    """

    ai_temperature: ClassVar[float] = 0.4  # grounded planning: some variety, little invention

    learning_objective: str = Field(min_length=8, max_length=800)
    recommended_activities: List[str] = Field(min_length=1, max_length=8)
    suggested_duration_days: int = Field(ge=3, le=60)
    practice_type: Literal["differentiated_homework", "question_studio", "mixed"] = (
        "differentiated_homework"
    )
    practice_outline: str = Field(min_length=8, max_length=1200)
    expected_outcome: str = Field(min_length=8, max_length=800)
    reassessment_criteria: str = Field(min_length=8, max_length=800)

    @field_validator("recommended_activities")
    @classmethod
    def non_empty_activities(cls, value: List[str]) -> List[str]:
        cleaned = [a.strip() for a in value if a and str(a).strip()]
        if not cleaned:
            raise ValueError("At least one recommended activity is required.")
        return cleaned[:8]


class GenerateInterventionRequest(BaseModel):
    subject_id: str
    competency: Optional[CompetencyDim] = None
    finding_kind: Optional[str] = None


class InterventionEditRequest(BaseModel):
    learning_objective: Optional[str] = None
    recommended_activities: Optional[List[str]] = None
    suggested_duration_days: Optional[int] = Field(default=None, ge=3, le=60)
    practice_recommendation: Optional[Dict[str, Any]] = None
    expected_outcome: Optional[str] = None
    reassessment_criteria: Optional[str] = None
    review_notes: Optional[str] = None


class InterventionReviewRequest(BaseModel):
    review_notes: Optional[str] = None


class InterventionAssignRequest(BaseModel):
    """Assign via the full Differentiated Homework draft → approve → assign workflow.

    title/description are retained for API compatibility but are not used to create
    legacy HomeworkRemediation rows; questions come from the central bank.
    """

    due_date: str = Field(min_length=8, max_length=32)
    title: Optional[str] = None
    description: Optional[str] = None


class InterventionOut(BaseModel):
    id: str
    school_id: str
    student_id: str
    subject_id: str
    competency: str
    finding_kind: Optional[str] = None
    gap_summary: str
    evidence_refs: List[Any] = Field(default_factory=list)
    baseline_score: Optional[float] = None
    baseline_checkpoint: Dict[str, Any] = Field(default_factory=dict)
    learning_objective: str
    recommended_activities: List[str] = Field(default_factory=list)
    suggested_duration_days: Optional[int] = None
    practice_recommendation: Dict[str, Any] = Field(default_factory=dict)
    expected_outcome: str
    reassessment_criteria: str
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    ai_generated: bool = True
    teacher_edited: bool = False
    status: str
    created_by_user_id: str
    reviewed_by_user_id: Optional[str] = None
    review_notes: Optional[str] = None
    assigned_homework_id: Optional[str] = None
    follow_up_evidence_refs: List[Any] = Field(default_factory=list)
    follow_up_checkpoint: Dict[str, Any] = Field(default_factory=dict)
    outcome_status: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    reviewed_at: Optional[str] = None
    assigned_at: Optional[str] = None
    completed_at: Optional[str] = None
    proposal_disclaimer: str = (
        "AI-generated proposal for teacher review only. "
        "Not verified competency evidence and never used in scoring."
    )
