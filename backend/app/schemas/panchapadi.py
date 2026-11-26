"""Explicit cognitive-demand mappings, independent of competency labels."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

Stage = Literal["Adheeti", "Bodh", "Abhyas", "Prayog", "Prasar"]
STAGES = ("Adheeti", "Bodh", "Abhyas", "Prayog", "Prasar")


class StageMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    stage: Stage
    reasoning: str = Field(min_length=1, max_length=3000)
    prerequisite_test: StrictBool = False
    procedural_practice: StrictBool = False
    independent_extension: StrictBool = False


class QuestionStageMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: StrictInt = Field(ge=0)
    mappings: list[StageMapping] = Field(max_length=5)

    @model_validator(mode="after")
    def distinct_stages(self):
        if len({m.stage for m in self.mappings}) != len(self.mappings):
            raise ValueError("A question may contribute only once to each stage.")
        return self


class StageClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    questions: list[QuestionStageMapping] = Field(max_length=100)


class StageContribution(BaseModel):
    position: int
    question_id: str | None
    reasoning: str
    score: float | None
    maximum: float
    eligible: bool
    exclusion_reason: str | None


class StageScore(BaseModel):
    stage: Stage
    score_pct: float | None
    earned_marks: float | None
    maximum_marks: float | None
    evidence_count: int
    status: str
    explanation: str
    teacher_verified: bool
    contributions: list[StageContribution]


class StageEvaluation(BaseModel):
    status: str
    attempt_id: str | None = None
    date: str | None = None
    error: str | None = None
    mapping: list[QuestionStageMapping] = Field(default_factory=list)
    stages: list[StageScore]
    review_revision_id: str | None = None
    teacher_verified: bool = False


class AssessmentStages(BaseModel):
    result_id: str
    assessment_id: str
    assessment_name: str
    subject_id: str
    assessed_at: str
    evaluation: StageEvaluation
    learning_plan: list[dict] = Field(default_factory=list)


class StageHistoryPoint(BaseModel):
    teacher_verified: bool = False
    result_id: str
    assessment_id: str
    assessment_name: str
    subject_id: str
    assessed_at: str
    score_pct: float | None
    earned_marks: float | None
    maximum_marks: float | None
    evidence_count: int
    status: str
    explanation: str
    review_revision_id: str | None


class StageHistory(BaseModel):
    stage: Stage
    points: list[StageHistoryPoint]


class PanchapadiHistory(BaseModel):
    student_id: str
    graphs: list[StageHistory]
