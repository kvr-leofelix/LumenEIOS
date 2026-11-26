"""Data shapes for the Differentiated Homework module."""
from datetime import datetime
from typing import Annotated, Dict, List, Literal, Optional, Tuple

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

Competency = Literal["LU", "CU", "AU", "CT"]

# Fixed order, used to break ties when displaying a ranking.
COMPETENCIES: tuple = ("LU", "CU", "AU", "CT")

# Strict: rejects floats, strings and booleans instead of silently converting them.
Score = Annotated[StrictInt, Field(ge=0, le=100)]


class CompetencyProfile(BaseModel):
    """A student's competency scores, as provided by a data source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    student_id: str = Field(min_length=1)
    scores: Dict[Competency, Score]
    baseline: Optional[Dict[Competency, Score]] = None
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _requires_all_four(self) -> "CompetencyProfile":
        for name, values in (("scores", self.scores), ("baseline", self.baseline)):
            if values is not None and set(values) != set(COMPETENCIES):
                raise ValueError(f"{name} must contain exactly LU, CU, AU and CT")
        return self


class CompetencyGap(BaseModel):
    """One competency's position in the ranking."""

    model_config = ConfigDict(frozen=True)

    competency: Competency
    score: int
    rank: int  # 1 = lowest score; tied scores share a rank
    baseline: Optional[int] = None
    change_from_baseline: Optional[int] = None


class GapAnalysis(BaseModel):
    """Result of comparing a student's four competency scores with each other."""

    model_config = ConfigDict(frozen=True)

    student_id: str
    ranked: List[CompetencyGap]  # lowest score first
    weakest: List[Competency]  # lowest scorers; empty when all four are equal
    has_single_weakest: bool
    lowest_score: int
    highest_score: int
    spread: int  # highest minus lowest
    source: str
    notes: List[str]


# --- Question Selection ---------------------------------------------------------


class CandidateQuestion(BaseModel):
    """A question bank item as seen by the selector. Answers and rubrics are never included."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    school_id: str
    subject_id: str
    text: str
    type: str
    marks: StrictInt  # range is checked by the selector, so bad values are reported, not rejected
    competency: str  # raw stored value; free text in the database
    bloom_level: str
    is_ai_generated: bool


class QuestionBankLoad(BaseModel):
    """Questions read from the database, plus the IDs of rows that couldn't be read."""

    model_config = ConfigDict(frozen=True)

    candidates: List[CandidateQuestion]
    malformed_question_ids: List[str]  # skipped because stored values have the wrong type


class SelectionRequest(BaseModel):
    """What the caller wants. Sizes come from the caller; there are no built-in defaults."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    school_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    max_questions: StrictInt = Field(ge=1)
    max_total_marks: Optional[StrictInt] = Field(default=None, ge=1)
    # Required: AI-generated questions have no review status, so the caller must decide.
    include_ai_generated: bool


class SelectedQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    question_id: str
    competency: Competency
    competency_rank: int  # rank of this competency in the gap analysis (1 = weakest)
    marks: int
    type: str
    bloom_level: str
    is_ai_generated: bool
    text: str


class SelectionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    student_id: str
    selected: List[SelectedQuestion]  # in selection order
    total_marks: int
    requested_questions: int
    max_total_marks: Optional[int]
    shortfall: int  # requested_questions minus the number selected
    priority: List[List[Competency]]  # competency groups, weakest first; tied competencies share a group
    eligible_by_competency: Dict[Competency, int]  # passed all filters, before the marks limit
    excluded: Dict[str, int]  # reason -> count
    notes: List[str]


# --- Homework Assembly ----------------------------------------------------------


class DraftItem(BaseModel):
    """One question in a homework draft. Answers, rubrics and options are never included."""

    model_config = ConfigDict(frozen=True)

    position: int  # 1-based, in selection order
    question_id: str
    competency: Competency
    competency_rank: int
    marks: int
    type: str
    bloom_level: str
    is_ai_generated: bool
    text: str


class DraftRationale(BaseModel):
    """Why this homework was assembled, taken directly from the gap analysis. No interpretation."""

    model_config = ConfigDict(frozen=True)

    targeted_competencies: List[Competency]  # in order of first appearance in the selection
    weakest: List[Competency]
    competency_scores: Dict[Competency, int]
    lowest_score: int
    highest_score: int
    score_source: str
    summary: str


class HomeworkDraft(BaseModel):
    """An unsaved homework draft for teacher review. Not an assignment; nothing is stored."""

    model_config = ConfigDict(frozen=True)

    student_id: str
    school_id: str
    subject_id: str
    items: List[DraftItem]
    question_count: int
    total_marks: int
    requested_questions: int
    max_total_marks: Optional[int]
    shortfall: int
    is_complete: bool  # True when every requested question was found
    contains_ai_generated: bool
    rationale: DraftRationale
    notes: List[str]  # gap-analysis notes, then selection notes, then assembly notes


class HomeworkPreviewRequest(BaseModel):
    """Body of POST /students/{student_id}/homework/preview.

    No school_id: the school comes from the student's record on the server. Unknown fields
    are rejected, so a client can't supply one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject_id: str = Field(min_length=1)
    max_questions: StrictInt = Field(ge=1)
    max_total_marks: Optional[StrictInt] = Field(default=None, ge=1)
    include_ai_generated: StrictBool  # required and must be a real true/false
    # Optional chapter/topic filter. Empty = every topic in the subject (previous behaviour).
    topics: Tuple[str, ...] = Field(default=(), max_length=20)


# --- Saved homework drafts ------------------------------------------------------------

DraftStatus = Literal["draft", "approved", "rejected", "assigned"]


class QuestionSnapshot(BaseModel):
    """Full copy of a question bank item for saving. INTERNAL: includes the answer key and
    rubric, so it must never be used as an API response model."""

    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    type: str
    options_json: List[object]
    marks: StrictInt
    competency: str
    bloom_level: str
    is_ai_generated: bool
    correct_answer: Optional[str] = None
    marking_rubric: Optional[str] = None


class HomeworkDraftSaveRequest(HomeworkPreviewRequest):
    """Same settings as the preview. The server regenerates the draft and saves that.

    expected_question_ids: optional. If given, the save is refused (409) unless the regenerated
    draft has exactly these questions in this order, so the teacher saves what they previewed.
    """

    expected_question_ids: Optional[List[str]] = None


class DraftReviewRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    note: Optional[str] = Field(default=None, max_length=2000)


class SavedDraftItemOut(BaseModel):
    """A saved question as shown to teachers. No answer key or rubric."""

    model_config = ConfigDict(frozen=True)

    position: int
    source_question_id: str
    text: str
    type: str
    options: List[object]
    marks: int
    competency: Competency
    competency_rank: int
    bloom_level: str
    is_ai_generated: bool


class SavedDraftSummaryOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    student_id: str
    school_id: str
    subject_id: str
    status: DraftStatus
    created_by: str
    question_count: int
    total_marks: int
    created_at: datetime
    updated_at: datetime
    # Display labels for teacher lists; None when the record no longer exists.
    student_name: Optional[str] = None
    subject_name: Optional[str] = None


class SavedDraftOut(SavedDraftSummaryOut):
    requested_questions: int
    max_total_marks: Optional[int]
    include_ai_generated: bool
    shortfall: int
    is_complete: bool
    rationale: DraftRationale
    notes: List[str]
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    review_note: Optional[str]
    items: List[SavedDraftItemOut]


# --- Homework assignments ------------------------------------------------------------

AssignmentStatus = Literal["assigned"]


class AssignRequest(BaseModel):
    """Body of POST /homework/drafts/{draft_id}/assign. Student, school and teacher come from
    the draft and the logged-in user, never from the client."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    due_at: Optional[AwareDatetime] = None  # must include a time zone; checked to be in the future


class AssignmentSummaryOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    draft_id: str
    student_id: str
    school_id: str
    subject_id: str
    status: AssignmentStatus
    assigned_by: str
    assigned_at: datetime
    due_at: Optional[datetime]
    question_count: int
    total_marks: int
    student_name: Optional[str] = None
    subject_name: Optional[str] = None


class AssignmentOut(AssignmentSummaryOut):
    items: List[SavedDraftItemOut]  # the draft's frozen snapshots; no answer key or rubric


# --- Student account links and student-facing homework ------------------------------


class StudentAccountLinkCreate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: str = Field(min_length=1)
    student_id: str = Field(min_length=1)


class StudentAccountLinkOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    user_id: str
    student_id: str
    created_by: str
    created_at: datetime


class StudentAccountLinkListItemOut(StudentAccountLinkOut):
    """A link as listed for admins. IDs and existence flags only: no names, emails or other
    personal details. is_stale is true when the linked User or Student no longer exists; such a
    link grants no access but blocks relinking until it is deleted by its ID."""

    user_exists: bool
    student_exists: bool
    is_stale: bool


class StudentAssignmentItemOut(BaseModel):
    """A question as a student sees it: no answer key, rubric, competency, rank, Bloom level,
    AI flag or source question ID."""

    model_config = ConfigDict(frozen=True)

    position: int
    text: str
    type: str
    options: List[object]
    marks: int


class StudentAssignmentSummaryOut(BaseModel):
    """No teacher-only fields: no draft ID, school, assigning teacher or review data."""

    model_config = ConfigDict(frozen=True)

    id: str
    subject_id: str
    subject_name: Optional[str]
    status: AssignmentStatus
    assigned_at: datetime
    due_at: Optional[datetime]
    question_count: int
    total_marks: int


class StudentAssignmentOut(StudentAssignmentSummaryOut):
    items: List[StudentAssignmentItemOut]


# --- Parent discovery (read-only) ------------------------------------------------------


class ParentChildOut(BaseModel):
    """A student linked to the logged-in parent through ParentStudentLink. Name and class
    only; no scores, rosters or other students."""

    id: str
    name: str
    class_name: str
    school_id: str


class ParentAssignmentSummaryOut(StudentAssignmentSummaryOut):
    """An assignment in the student's own list (and a linked parent's view of it), plus progress
    flags. Never includes questions, answers, keys, rubrics or unreleased marks."""

    submission_status: Literal["not_started", "in_progress", "submitted"]
    result_released: bool


# --- Student answer submissions ---------------------------------------------------------

SubmissionStatus = Literal["in_progress", "submitted"]

# Payload limits, not teaching rules. Named here so they're documented and testable.
MAX_ANSWER_TEXT_LENGTH = 10_000  # characters per text answer
MAX_ANSWER_UPDATES = 500  # entries per request; real requests are bounded by the question count

ANSWER_ACTIONS = ("answer_text", "selected_option_index", "clear")


class AnswerUpdate(BaseModel):
    """One change to one question, by its 1-based position. Exactly one of:
    - {"position": 2, "answer_text": "..."}       set a text answer (short, descriptive, practical)
    - {"position": 1, "selected_option_index": 0} set an MCQ answer (0-based index into options)
    - {"position": 3, "clear": true}              remove the existing answer

    An explicit null is rejected rather than read as "clear": in this module's other request
    schemas, null means "not provided", so clearing has its own explicit form.
    Questions not listed in a request keep their current answers.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    position: StrictInt = Field(ge=1)
    answer_text: Optional[str] = Field(default=None, max_length=MAX_ANSWER_TEXT_LENGTH)
    selected_option_index: Optional[StrictInt] = Field(default=None, ge=0)
    clear: Optional[Literal[True]] = None

    @model_validator(mode="after")
    def _exactly_one_action(self) -> "AnswerUpdate":
        given = [name for name in ANSWER_ACTIONS if name in self.model_fields_set]
        if len(given) != 1:
            raise ValueError("give exactly one of answer_text, selected_option_index or clear")
        if getattr(self, given[0]) is None:
            raise ValueError(f"{given[0]} can't be null; use clear: true to remove an answer")
        if self.answer_text is not None and not self.answer_text.strip():
            raise ValueError("answer_text can't be blank; use clear: true to remove an answer")
        return self

    @property
    def action(self) -> str:
        return next(name for name in ANSWER_ACTIONS if name in self.model_fields_set)


class SubmissionAnswersUpdate(BaseModel):
    """A partial save. expected_version must be omitted when no submission exists yet, and must
    equal the current version otherwise. Each position may appear at most once."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_version: Optional[StrictInt] = Field(default=None, ge=1)
    answers: List[AnswerUpdate] = Field(default_factory=list, max_length=MAX_ANSWER_UPDATES)

    @model_validator(mode="after")
    def _unique_positions(self) -> "SubmissionAnswersUpdate":
        positions = [a.position for a in self.answers]
        repeated = sorted({p for p in positions if positions.count(p) > 1})
        if repeated:
            raise ValueError(f"each position may appear only once; repeated: {repeated}")
        return self


class SubmissionFinalizeRequest(BaseModel):
    """Final submit. expected_version is omitted only when nothing has been saved yet, which
    submits a blank submission."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_version: Optional[StrictInt] = Field(default=None, ge=1)


class AnswerProblemOut(BaseModel):
    """One entry of a 422 answer-validation error: which question and why."""

    model_config = ConfigDict(frozen=True)

    position: int
    reason: str


class SubmissionAnswerOut(BaseModel):
    """A stored answer as the student sees it. No answer key, rubric or marks."""

    model_config = ConfigDict(frozen=True)

    position: int
    answer_text: Optional[str]
    selected_option_index: Optional[int]


# What a student sees. "not_started" is a view state only: nothing is stored until the first
# save, and the stored statuses stay SubmissionStatus.
SubmissionViewStatus = Literal["not_started", "in_progress", "submitted"]


class HomeworkSubmissionOut(BaseModel):
    """A student's submission, in one shape for all three states. No marks, score, grade,
    feedback or teacher-only data.

    not_started: id, version and the timestamps are null, and answers is empty. A null version
    means "omit expected_version on the first save"."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str]
    assignment_id: str
    status: SubmissionViewStatus
    version: Optional[int]  # send back as expected_version on the next change
    is_late: bool
    started_at: Optional[datetime]
    updated_at: Optional[datetime]
    submitted_at: Optional[datetime]
    answered_count: int
    question_count: int
    answers: List[SubmissionAnswerOut]  # answered questions only, by position


# --- Teacher-facing, read-only submission views ---------------------------------------------
# Separate from the student schemas. Never included: answer keys, rubrics, marks, scores,
# grades, feedback, competency or Bloom data, source question IDs, and the submission's
# internal version.


class TeacherSubmissionCountsOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_students: int
    not_started: int
    in_progress: int
    submitted: int
    submitted_late: int


class TeacherStudentSubmissionOut(BaseModel):
    """One student's progress on the assignment. is_late is null until submitted."""

    model_config = ConfigDict(frozen=True)

    student_id: str
    student_name: Optional[str]  # null only if the Student record no longer exists
    status: SubmissionViewStatus
    started_at: Optional[datetime]
    updated_at: Optional[datetime]
    submitted_at: Optional[datetime]
    is_late: Optional[bool]
    answered_count: int
    question_count: int


class TeacherAssignmentSubmissionsOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    assignment_id: str
    subject_id: str
    subject_name: Optional[str]
    assignment_status: AssignmentStatus
    assigned_at: datetime
    due_at: Optional[datetime]
    question_count: int
    counts: TeacherSubmissionCountsOut
    students: List[TeacherStudentSubmissionOut]


class TeacherQuestionAnswerOut(BaseModel):
    """A frozen question (text, type and options only) with the student's answer, if any."""

    model_config = ConfigDict(frozen=True)

    position: int
    text: str
    type: str
    options: List[object]
    answered: bool
    answer_text: Optional[str]
    selected_option_index: Optional[int]


class TeacherSubmissionDetailOut(TeacherStudentSubmissionOut):
    assignment_id: str
    questions: List[TeacherQuestionAnswerOut]  # every question, by position


# --- Homework evaluations (manual grading) ---------------------------------------------------
# Marks are whole numbers, like every other marks column in the project (the frozen question's
# `marks`, AssessmentSubmission.marks_obtained). StrictInt rejects floats, NaN, infinity,
# booleans and strings. No percentages, grades or thresholds are computed anywhere.

EvaluationStatus = Literal["pending", "marked", "released"]
MAX_FEEDBACK_LENGTH = 2000  # the same limit as a draft review note
MAX_MARK_UPDATES = 500


class EvaluationMarkUpdate(BaseModel):
    """A change to one question's mark and/or feedback, by its 1-based position.

    Give awarded_marks, feedback, or both. Fields left out keep their values. null is rejected
    (as in the answer-save request); send feedback "" to clear it. A mark can be changed while
    the evaluation is pending, but not removed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    position: StrictInt = Field(ge=1)
    awarded_marks: Optional[StrictInt] = Field(default=None, ge=0)
    feedback: Optional[str] = Field(default=None, max_length=MAX_FEEDBACK_LENGTH)

    @model_validator(mode="after")
    def _something_to_change(self) -> "EvaluationMarkUpdate":
        given = {"awarded_marks", "feedback"} & self.model_fields_set
        if not given:
            raise ValueError("give awarded_marks, feedback, or both")
        for name in given:
            if getattr(self, name) is None:
                raise ValueError(f"{name} can't be null")
        return self


class EvaluationMarksUpdate(BaseModel):
    """Several question updates applied together (all or nothing), against the current version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_version: StrictInt = Field(ge=1)
    items: List[EvaluationMarkUpdate] = Field(min_length=1, max_length=MAX_MARK_UPDATES)

    @model_validator(mode="after")
    def _unique_positions(self) -> "EvaluationMarksUpdate":
        positions = [i.position for i in self.items]
        repeated = sorted({p for p in positions if positions.count(p) > 1})
        if repeated:
            raise ValueError(f"each position may appear only once; repeated: {repeated}")
        return self


class EvaluationTransitionRequest(BaseModel):
    """Body of finalize and release."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_version: StrictInt = Field(ge=1)


class TeacherEvaluationItemOut(BaseModel):
    """One question for the marking teacher: the frozen question, its frozen answer key and
    rubric, the student's answer, and the mark.

    TEACHER-ONLY: correct_answer and marking_rubric come from the question's frozen snapshot
    (HomeworkDraftItemRecord), not the live question bank, exactly as stored (text; for an MCQ
    the key is the option text). null when the snapshot has none. This schema must only be used
    by the authorized grading endpoints, never in a student or parent response."""

    model_config = ConfigDict(frozen=True)

    position: int
    text: str
    type: str
    options: List[object]
    max_marks: int
    answered: bool
    answer_text: Optional[str]
    selected_option_index: Optional[int]
    awarded_marks: Optional[int]  # null until marked
    feedback: Optional[str]
    marked_by: Optional[str]
    marked_at: Optional[datetime]
    correct_answer: Optional[str]  # teacher-only, from the frozen snapshot
    marking_rubric: Optional[str]  # teacher-only, from the frozen snapshot


class TeacherEvaluationOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    assignment_id: str
    student_id: str
    student_name: Optional[str]
    status: EvaluationStatus
    version: int  # send back as expected_version
    submitted_at: datetime
    is_late: bool
    total_max: int
    total_awarded: Optional[int]  # set when finalized
    marked_count: int
    question_count: int
    created_by: str
    created_at: datetime
    updated_at: datetime
    finalized_by: Optional[str]
    finalized_at: Optional[datetime]
    released_by: Optional[str]
    released_at: Optional[datetime]
    items: List[TeacherEvaluationItemOut]


class TeacherEvaluationQueueItemOut(BaseModel):
    """A submitted homework and how far its evaluation has got."""

    model_config = ConfigDict(frozen=True)

    student_id: str
    student_name: Optional[str]
    submitted_at: datetime
    is_late: bool
    evaluation_status: Literal["not_started", "pending", "marked", "released"]
    evaluation_id: Optional[str]
    marked_count: int
    question_count: int


class StudentResultItemOut(BaseModel):
    """A released mark as the student sees it. No answer key, rubric or marking metadata."""

    model_config = ConfigDict(frozen=True)

    position: int
    text: str
    type: str
    options: List[object]
    answer_text: Optional[str]
    selected_option_index: Optional[int]
    max_marks: int
    awarded_marks: int
    feedback: Optional[str]


class StudentResultOut(BaseModel):
    """Released results only. No evaluation ID, version, teacher IDs or internal timestamps."""

    model_config = ConfigDict(frozen=True)

    assignment_id: str
    released_at: datetime
    total_awarded: int
    total_max: int
    items: List[StudentResultItemOut]


# --- AI-assisted evaluation suggestions (teacher-only; never student/parent) -----------------
# Suggestions never finalize, release, or write awarded_marks. Teachers apply marks via PATCH.

SuggestionCorrectness = Literal["correct", "partially_correct", "incorrect", "undetermined"]
# Ordinal heuristic only — not a calibrated probability.
SuggestionConfidence = Literal["high", "medium", "low"]
SuggestionSource = Literal["deterministic_mcq", "gemini", "qwen", "teacher_required"]
# Which model marks open-ended answers: the local Qwen model (works offline) or Gemini.
SuggestionModel = Literal["gemini", "qwen"]
MAX_SUGGESTION_POSITIONS = 500
MAX_EXPLANATION_LENGTH = 4000
MAX_RUBRIC_CRITERIA = 20


class RubricCriterionSuggestion(BaseModel):
    """One rubric criterion with suggested marks. Teacher-only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion: str = Field(min_length=1, max_length=500)
    max_marks: StrictInt = Field(ge=0)
    awarded_marks: StrictInt = Field(ge=0)
    comment: Optional[str] = Field(default=None, max_length=1000)


class AIEvaluationSuggestRequest(BaseModel):
    """Generate suggestions for some or all questions of a pending evaluation.

    With replace=false (default), the request fails if suggestions already exist for any
    requested position. Re-run uses replace=true (or the dedicated re-run endpoint)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    positions: Optional[List[StrictInt]] = Field(default=None, max_length=MAX_SUGGESTION_POSITIONS)
    replace: StrictBool = False
    provider: SuggestionModel = "gemini"

    @model_validator(mode="after")
    def _positions_ok(self) -> "AIEvaluationSuggestRequest":
        if self.positions is None:
            return self
        if not self.positions:
            raise ValueError("positions, when given, must not be empty")
        if any(p < 1 for p in self.positions):
            raise ValueError("positions must be integers >= 1")
        repeated = sorted({p for p in self.positions if self.positions.count(p) > 1})
        if repeated:
            raise ValueError(f"each position may appear only once; repeated: {repeated}")
        return self


class AIEvaluationRerunRequest(BaseModel):
    """Replace stored suggestions for some or all positions of a pending evaluation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    positions: Optional[List[StrictInt]] = Field(default=None, max_length=MAX_SUGGESTION_POSITIONS)
    provider: SuggestionModel = "gemini"

    @model_validator(mode="after")
    def _positions_ok(self) -> "AIEvaluationRerunRequest":
        if self.positions is None:
            return self
        if not self.positions:
            raise ValueError("positions, when given, must not be empty")
        if any(p < 1 for p in self.positions):
            raise ValueError("positions must be integers >= 1")
        repeated = sorted({p for p in self.positions if self.positions.count(p) > 1})
        if repeated:
            raise ValueError(f"each position may appear only once; repeated: {repeated}")
        return self


class AIEvaluationSuggestionItemOut(BaseModel):
    """One teacher-only suggestion. explanation is internal reasoning; feedback is student-facing
    text the teacher may adopt. Never returned on student/parent result endpoints."""

    model_config = ConfigDict(frozen=True)

    position: int
    suggested_marks: int
    max_marks: int
    correctness: SuggestionCorrectness
    explanation: str
    feedback: str
    rubric_criteria: Optional[List[RubricCriterionSuggestion]]
    confidence: SuggestionConfidence
    needs_teacher_attention: bool
    source: SuggestionSource
    model: Optional[str]
    updated_at: datetime


class AIEvaluationSuggestionsOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    evaluation_id: str
    assignment_id: str
    evaluation_status: EvaluationStatus
    evaluation_version: int  # unchanged by suggestion generate/re-run
    items: List[AIEvaluationSuggestionItemOut]
