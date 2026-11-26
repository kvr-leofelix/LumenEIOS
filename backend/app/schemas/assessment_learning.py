"""Bounded model drafts and explicit educator decisions; never confirmed by AI."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from backend.app.schemas.panchapadi import Stage


class WrittenMark(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    score: StrictInt | None = Field(default=None, ge=0)
    correct: bool | None = None
    explanation: str = Field(min_length=1, max_length=4000)
    feedback: str = Field(min_length=1, max_length=4000)
    insufficient_evidence: bool = False
    demonstrated_concepts: list[str] = Field(default_factory=list, max_length=20)
    partial_concepts: list[str] = Field(default_factory=list, max_length=20)
    missing_concepts: list[str] = Field(default_factory=list, max_length=20)


class QuestionGuidance(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_concept: str | None = Field(default=None, max_length=2000)
    misunderstanding: str | None = Field(default=None, max_length=2000)
    explanation: str = Field(min_length=1, max_length=3000)
    activity: str = Field(min_length=1, max_length=3000)
    practice_question: str | None = Field(default=None, max_length=2000)


class LearningDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: Literal["support", "teach_back", "mission"]
    positions: list[StrictInt] = Field(min_length=1, max_length=100)
    stage: Stage
    title: str = Field(min_length=1, max_length=255)
    explanation: str = Field(min_length=1, max_length=4000)
    learning_tip: str = Field(min_length=1, max_length=4000)
    scenario: str = Field(min_length=1, max_length=4000)
    instructions: str = Field(min_length=1, max_length=8000)
    expected_submission: str = Field(min_length=1, max_length=2000)
    objective: str = Field(min_length=1, max_length=2000)
    rubric: str = Field(min_length=1, max_length=4000)


class LearningDrafts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    drafts: list[LearningDraft] = Field(min_length=3, max_length=3)


class LearningDecision(LearningDraft):
    decision: Literal["draft", "approved", "rejected"] = "draft"
    topic_id: str | None = None


class ApprovedLearning(LearningDecision):
    activity_id: str | None = None
    assignment_id: str | None = None
