from typing import Optional, List, Any, Literal
from pydantic import BaseModel, Field, StrictInt, model_validator
from backend.app.schemas.common import BaseSchema


class QuestionKcLink(BaseSchema):
    kc_id: str
    relevance: float = 1.0


class QuestionSchema(BaseSchema):
    id: Optional[str] = None
    text: str
    type: str  # mcq, short, descriptive, practical
    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None
    marking_rubric: Optional[str] = None
    marks: int = 1
    competency: str  # LU, CU, AU, CT
    bloom_level: str  # Remember, Understand, Apply, Analyze, Evaluate, Create
    source_document_ids: Optional[List[str]] = None
    source_document_names: Optional[List[str]] = None
    is_ai_generated: Optional[bool] = False
    # Present only after a teacher confirms catalogue ids. None keeps the older evaluation-time mapping.
    kc_mappings: Optional[List[QuestionKcLink]] = None
    difficulty: Optional[str] = None


class CompetencyDistribution(BaseModel):
    model_config = {"extra": "forbid"}
    LU: StrictInt = Field(default=0, ge=0)
    CU: StrictInt = Field(default=0, ge=0)
    AU: StrictInt = Field(default=0, ge=0)
    CT: StrictInt = Field(default=0, ge=0)


class GenerateQuestionsRequest(BaseModel):
    subject_id: str
    subject_name: Optional[str] = None
    source_document_ids: List[str] = []
    # Learning-resource links (Wikipedia, BYJU'S, ...) used with or instead of the chapter PDF.
    source_urls: List[str] = []
    mcq_count: StrictInt = Field(default=3, ge=0, le=15)
    theory_count: StrictInt = Field(default=2, ge=0, le=10)
    total_count: StrictInt | None = Field(default=None, ge=1, le=25)
    selected_competencies: list[Literal["LU", "CU", "AU", "CT"]] | None = None
    bloom_level: str = "Apply"
    focus_topic: Optional[str] = None
    # Topic/chapter the saved questions are filed under (falls back to focus_topic).
    bank_topic: Optional[str] = None
    save_to_bank: bool = True

    competency_distribution: Optional[CompetencyDistribution] = None

    @model_validator(mode="after")
    def validate_distribution(self):
        total = self.mcq_count + self.theory_count
        if total == 0 or (self.total_count is not None and self.total_count != total):
            raise ValueError("Question type counts must equal the positive total.")
        if self.selected_competencies is not None:
            from backend.app.lib.question_distribution import distribute
            proposed = distribute(total, self.selected_competencies)
            if self.competency_distribution is None:
                self.competency_distribution = CompetencyDistribution(**proposed)
            elif any(self.competency_distribution.model_dump()[c] for c in proposed if c not in self.selected_competencies):
                raise ValueError("Unselected competencies must have zero questions.")
        if self.competency_distribution is not None:
            total = sum(self.competency_distribution.model_dump().values())
            if total == 0 or total != self.mcq_count + self.theory_count:
                raise ValueError("Competency counts must include at least one question and equal the requested total.")
        return self


class RegenerateQuestionRequest(BaseModel):
    subject_id: Optional[str] = None
    question_type: str = "mcq"
    bloom_level: str = "Apply"
    competency: str = "CU"
    source_document_ids: List[str] = []
    source_document_names: List[str] = []
    current_text: str = ""
    custom_instruction: Optional[str] = None


class QuestionCreateRequest(BaseModel):
    """A teacher-written question-bank item (no AI involved)."""
    subject_id: str
    text: str
    type: str = "mcq"
    options: List[str] = []
    correct_answer: str = ""
    marking_rubric: str = ""
    marks: int = 1
    competency: str = "CU"
    bloom_level: str = "Understand"
    topic: Optional[str] = None
    grade: Optional[int] = None


class QuestionUpdateRequest(BaseModel):
    text: Optional[str] = None
    type: Optional[str] = None
    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None
    marking_rubric: Optional[str] = None
    marks: Optional[int] = None
    competency: Optional[str] = None
    bloom_level: Optional[str] = None
    topic: Optional[str] = None  # "" clears it
    grade: Optional[int] = None  # 0 clears it


class AssessmentCreate(BaseModel):
    class_id: Optional[str] = "class-8a"
    subject_id: str
    title: str
    cycle_number: int = 1
    date: str
    duration_minutes: int = 45
    total_marks: int = 25
    questions: List[QuestionSchema]
    competency_focus: List[str]


class AssessmentOut(BaseSchema):
    id: str
    school_id: str
    class_id: str
    subject_id: str
    title: str
    cycle_number: int
    date: str
    duration_minutes: int
    total_marks: int
    status: str
    competency_focus_json: List[str]
    questions_json: List[Any]


class SubmissionCreate(BaseModel):
    student_id: str
    marks_obtained: int
    total_marks: int
    lu_score: int
    cu_score: int
    au_score: int
    ct_score: int
    feedback: Optional[str] = None
    is_scanned: bool = False


class SubmissionOut(BaseSchema):
    id: str
    assessment_id: str
    student_id: str
    student_name: str
    marks_obtained: int
    total_marks: int
    percentage: int
    scores: dict
    feedback: Optional[str] = None
    submission_date: str
    is_scanned: bool


class AssignmentSubject(BaseModel):
    id: str
    name: str


class AssignmentTarget(BaseModel):
    id: str
    name: str
    school_id: str
    school_name: str
    subjects: List[AssignmentSubject]


class UploadQuestion(BaseModel):
    id: Optional[str] = None
    text: str
    type: str
    options: Optional[List[str]] = None
    marks: int
    competency: Optional[str] = None


class UploadAssignment(BaseModel):
    id: str
    title: str
    date: str
    class_name: str
    subject_name: str
    total_marks: int
    uploaded: bool
    questions: List[UploadQuestion]

