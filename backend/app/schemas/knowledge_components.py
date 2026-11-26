from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from backend.app.schemas.common import BaseSchema


class KnowledgeComponentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    subject_id: str = Field(min_length=1, max_length=64)
    topic: str = Field(min_length=1, max_length=200)


class KnowledgeComponentOut(BaseSchema):
    id: str
    name: str
    description: str
    subject_id: str
    subject_name: str
    topic: str


class RelationshipCreate(BaseModel):
    source_id: str = Field(min_length=1, max_length=64)
    target_id: str = Field(min_length=1, max_length=64)
    relationship: Literal["PREREQUISITE_OF", "RELATED_TO", "PART_OF"]


class RelationshipOut(BaseSchema):
    id: str
    source_id: str
    target_id: str
    relationship: str


class DimensionScores(BaseSchema):
    LU: Optional[float] = None
    CU: Optional[float] = None
    CT: Optional[float] = None
    AU: Optional[float] = None


class AttemptHistoryItem(BaseSchema):
    assessed_at: datetime
    question_id: str
    competency: Literal["LU", "CU", "CT", "AU"]
    score: float
    awarded_marks: float
    max_marks: float
    correct: bool


class ConceptRef(BaseSchema):
    id: str
    name: str
    relationship: str
    overall_mastery: Optional[float] = None
    learning_status: str


class KnowledgeGraphNode(BaseSchema):
    id: str
    name: str
    description: str
    subject: str
    topic: str
    overall_mastery: Optional[float] = None
    lu: Optional[float] = None
    cu: Optional[float] = None
    ct: Optional[float] = None
    au: Optional[float] = None
    attempt_count: int = 0
    correct_count: int = 0
    incorrect_count: int = 0
    learning_status: str
    last_assessed_at: Optional[datetime] = None
    latest: DimensionScores
    previous: DimensionScores
    history: list[AttemptHistoryItem]
    prerequisites: list[ConceptRef]
    related: list[ConceptRef]
    recommendations: list[str]


class KnowledgeGraphEdge(BaseSchema):
    source_id: str
    target_id: str
    relationship: str


class KnowledgeGraphOut(BaseSchema):
    nodes: list[KnowledgeGraphNode]
    edges: list[KnowledgeGraphEdge]
    insights: list[str]


class ClassConceptStudentOut(BaseSchema):
    student_id: str
    student_name: str
    learning_status: str
    overall_mastery: Optional[float] = None
    lu: Optional[float] = None
    cu: Optional[float] = None
    ct: Optional[float] = None
    au: Optional[float] = None
    last_assessed_at: Optional[datetime] = None


class ClassConceptEvidenceOut(BaseSchema):
    id: str
    name: str
    topic: str
    student_count: int
    proficient_count: int
    developing_count: int
    needs_improvement_count: int
    average_mastery: Optional[float] = None
    weakest_competency: Optional[str] = None
    last_assessed_at: Optional[datetime] = None
    students: list[ClassConceptStudentOut]


class ClassEvidenceOut(BaseSchema):
    class_id: str
    class_name: str
    subject_id: str
    subject_name: str
    concepts: list[ClassConceptEvidenceOut]


class QuestionMapRequest(BaseModel):
    subject_id: str = Field(min_length=1, max_length=64)
    provider: Literal["gemini", "qwen"] = "gemini"
    questions: list["MapQuestionIn"] = Field(min_length=1, max_length=30)


class MapQuestionIn(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1)
    competency: str = "CU"
    correct_answer: str = ""
    marking_rubric: str = ""


class MappedComponentOut(BaseSchema):
    id: str
    name: str
    relevance: float


class MappedQuestionOut(BaseSchema):
    question_id: str
    components: list[MappedComponentOut]


class QuestionMapOut(BaseSchema):
    questions: list[MappedQuestionOut]


class BlueprintSlotIn(BaseModel):
    kc_id: str = Field(min_length=1, max_length=64)
    include: bool = True
    question_count: int = Field(default=1, ge=0, le=10)
    difficulty: Literal["foundational", "standard", "advanced"] = "standard"


class ClassBlueprintRequest(BaseModel):
    class_id: str = Field(min_length=1, max_length=64)
    subject_id: str = Field(min_length=1, max_length=64)
    total_marks: int = Field(default=20, ge=1, le=200)
    question_count: int = Field(default=4, ge=1, le=30)
    duration_minutes: int = Field(default=40, ge=5, le=180)
    topic: Optional[str] = None
    slots: list[BlueprintSlotIn] = Field(default_factory=list)


class BlueprintConceptOut(BaseSchema):
    id: str
    name: str
    topic: str
    band: str
    student_count: int
    proficient_count: int
    developing_count: int
    needs_improvement_count: int
    average_mastery: Optional[float] = None
    reason: str


class BlueprintQuestionOut(BaseSchema):
    id: str
    text: str
    type: str
    competency: str
    marks: int
    bloom_level: str
    correct_answer: Optional[str] = None
    marking_rubric: Optional[str] = None
    kc_mappings: list[dict]


class BlueprintSlotOut(BaseSchema):
    kc_id: str
    kc_name: str
    band: str
    difficulty: str
    marks: int
    reason: str
    question: Optional[BlueprintQuestionOut] = None


class ClassBlueprintOut(BaseSchema):
    class_id: str
    class_name: str
    subject_id: str
    subject_name: str
    total_marks: int
    question_count: int
    duration_minutes: int
    roster_count: int
    students_without_evidence: int
    concepts: list[BlueprintConceptOut]
    slots: list[BlueprintSlotOut]


class StudentRecommendationOut(BaseSchema):
    kc_id: str
    kc_name: str
    kind: str
    reason: str
    previous_performance: str
    attempt_count: int
    expected_outcome: str
    difficulty: str
    question_type: str
    question: Optional[dict] = None
    needs_generation: bool


class StudentConceptAnalysisItem(BaseSchema):
    id: str
    name: str
    topic: str
    learning_status: str
    overall_mastery: Optional[float] = None
    attempt_count: int
    correct_count: int
    incorrect_count: int
    recommendations: list[str]


class StudentConceptAnalysisOut(BaseSchema):
    student_id: str
    student_name: str
    subject_id: str
    subject_name: str
    assessed_count: int
    not_assessed_count: int
    concepts: list[StudentConceptAnalysisItem]


class FractionSampleStudentOut(BaseSchema):
    student_id: str
    student_name: str
    profile: str
    recommendations: list[StudentRecommendationOut]


class FractionSampleOut(BaseSchema):
    class_id: str
    class_name: str
    subject_id: str
    subject_name: str
    assessment_id: str
    source_reference: str
    students: list[FractionSampleStudentOut]


class DemoWalkthroughOut(BaseSchema):
    student_name: str
    student_email: str
    subject_name: str
    assessment_id: str
    title: str
    class_name: str
    extracted_text: str
    evaluated: bool
    total_marks_obtained: Optional[float] = None
    max_possible_marks: Optional[float] = None
    percentage: Optional[float] = None
    graph: KnowledgeGraphOut
