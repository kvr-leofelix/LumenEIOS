from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictBool, model_validator
from backend.app.schemas.panchapadi import QuestionStageMapping, StageEvaluation
from backend.app.schemas.assessment_learning import LearningDecision, ApprovedLearning, LearningDraft


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Answer(Input):
    position: StrictInt = Field(ge=0)
    selected_option_index: StrictInt | None = Field(default=None, ge=0)
    answer_text: str | None = Field(default=None, min_length=1, max_length=16000)


class AnswersSubmit(Input):
    request_key: str = Field(min_length=1, max_length=64)
    answers: list[Answer] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def distinct(self):
        if len({a.position for a in self.answers}) != len(self.answers):
            raise ValueError("Duplicate question positions are not allowed.")
        return self


class ReviewedQuestion(Input):
    position: StrictInt = Field(ge=0)
    score: StrictInt = Field(ge=0)
    correct: StrictBool | None = None
    feedback: str = Field(min_length=1, max_length=4000)
    topic_id: str | None = None
    explanation: str | None = Field(default=None, max_length=4000)
    verify_key: StrictBool = False


class AssessmentReview(Input):
    expected_version: StrictInt = Field(ge=1)
    feedback: str = Field(min_length=1, max_length=12000)
    questions: list[ReviewedQuestion] = Field(min_length=1, max_length=100)
    confirm_panchapadi: StrictBool = False
    panchapadi_mappings: list[QuestionStageMapping] | None = None
    learning_plan: list[LearningDecision] | None = Field(default=None, max_length=30)


class PublicQuestion(BaseModel):
    position: int
    id: str | None = None
    text: str
    type: str
    options: list[str]
    marks: int
    competency: str
    correct_answer: str | None = None
    marking_rubric: str | None = None


class QuestionOutcome(BaseModel):
    position: int
    question_id: str | None = None
    competency: str
    score: int | None
    maximum: int
    correct: bool | None
    provenance: str
    feedback: str | None = None
    topic_id: str | None = None
    explanation: str | None = None
    key_verified: bool = False


class ReviewRevision(BaseModel):
    revision_id: str
    reviewer_id: str
    date: str
    feedback: str
    outcomes: list[QuestionOutcome]
    panchapadi: StageEvaluation | None = None
    learning_plan: list[ApprovedLearning] = Field(default_factory=list)


class ResultOut(BaseModel):
    id: str
    assessment_id: str
    assessment_title: str
    student_id: str
    school_id: str
    class_id: str
    subject_id: str
    submission_id: str | None
    version: int
    status: str
    questions: list[PublicQuestion]
    answers: list[Answer]
    automatic_outcomes: list[QuestionOutcome]
    reviews: list[ReviewRevision]
    outcomes: list[QuestionOutcome]
    marks_obtained: int | None
    total_marks: int
    panchapadi: StageEvaluation
    learning_drafts: list[LearningDraft] = Field(default_factory=list)
    evaluation_warnings: list[str] = Field(default_factory=list)
    guidance_status: str | None = None
