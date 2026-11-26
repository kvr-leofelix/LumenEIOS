from typing import Optional, List, Dict, Any, Literal

try:
    from pydantic import BaseModel, Field, field_validator, model_validator
    from backend.app.schemas.common import BaseSchema
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    # Fallback base class if pydantic is not installed in local environment
    class BaseSchema:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        @classmethod
        def model_validate(cls, obj):
            if isinstance(obj, cls):
                return obj
            return cls(**obj)
        def model_dump(self):
            return self.__dict__

    def Field(*args, **kwargs):
        return kwargs.get("default", None) if "default" in kwargs else kwargs.get("default_factory", lambda: None)()


if PYDANTIC_AVAILABLE:
    class StudentInfo(BaseSchema):
        detected_name: Optional[str] = None
        detected_roll_no: Optional[str] = None

    class StepBreakdownItem(BaseSchema):
        criterion: str
        marks_awarded: float = Field(ge=0)
        max: float = Field(gt=0)

    class QuestionEvaluation(BaseSchema):
        question_index: int
        question_id: str
        question_text: str
        competency: Literal["LU", "CU", "AU", "CT"]
        max_marks: float = Field(gt=0)
        student_answer_extracted: str = ""
        status: Literal["attempted", "unattempted", "partially_attempted"] = "attempted"
        awarded_marks: float = Field(ge=0)
        competency_score: float = Field(ge=0, le=100)
        step_breakdown: List[StepBreakdownItem] = Field(default_factory=list)
        feedback: str = ""
        flag_for_review: bool = False
        flag_reason: Optional[str] = None

        @model_validator(mode="after")
        def validate_marks_and_flags(self) -> "QuestionEvaluation":
            # 1. Unattempted questions must receive 0 marks
            if self.status == "unattempted":
                self.awarded_marks = 0.0
                self.competency_score = 0.0
                self.step_breakdown = []

            # 2. Reconcile awarded marks with step breakdown if steps are present
            if self.step_breakdown:
                calc_marks = sum(step.marks_awarded for step in self.step_breakdown)
                if abs(calc_marks - self.awarded_marks) > 0.01:
                    self.awarded_marks = min(calc_marks, self.max_marks)

            # 3. Cap awarded marks at max marks
            if self.awarded_marks > self.max_marks:
                self.awarded_marks = self.max_marks

            # 4. Auto-flag for review if student text contains [unclear] marker in critical answer
            if "[unclear]" in (self.student_answer_extracted or "").lower() and not self.flag_for_review:
                self.flag_for_review = True
                if not self.flag_reason:
                    self.flag_reason = "Illegible / [unclear] marker in extracted student response"

            return self

    class CompetencyScores(BaseSchema):
        LU: Optional[float] = None
        CU: Optional[float] = None
        AU: Optional[float] = None
        CT: Optional[float] = None

    class ScoringSummary(BaseSchema):
        total_marks_obtained: float = Field(ge=0)
        max_possible_marks: float = Field(gt=0)
        percentage: float = Field(ge=0, le=100)
        competency_scores: CompetencyScores = Field(default_factory=CompetencyScores)
        overall_feedback: str = ""
        needs_teacher_review: bool = False
        review_reasons: List[str] = Field(default_factory=list)

    class EvaluationResult(BaseSchema):
        student_info: StudentInfo = Field(default_factory=StudentInfo)
        question_evaluations: List[QuestionEvaluation] = Field(default_factory=list)
        scoring_summary: ScoringSummary

        @model_validator(mode="after")
        def reconcile_summary_and_flags(self) -> "EvaluationResult":
            flagged_questions = [
                q for q in self.question_evaluations if q.flag_for_review
            ]
            if flagged_questions:
                self.scoring_summary.needs_teacher_review = True
                for q in flagged_questions:
                    reason = f"Q{q.question_index}: {q.flag_reason or 'Marked for educator review'}"
                    if reason not in self.scoring_summary.review_reasons:
                        self.scoring_summary.review_reasons.append(reason)

            total_awarded = sum(q.awarded_marks for q in self.question_evaluations)
            total_max = sum(q.max_marks for q in self.question_evaluations)

            if total_max > 0:
                self.scoring_summary.total_marks_obtained = round(total_awarded, 2)
                self.scoring_summary.max_possible_marks = round(total_max, 2)
                self.scoring_summary.percentage = round((total_awarded / total_max) * 100, 2)

            comp_scores: Dict[str, List[float]] = {"LU": [], "CU": [], "AU": [], "CT": []}
            for q in self.question_evaluations:
                if q.competency in comp_scores and q.status != "unattempted":
                    comp_scores[q.competency].append(q.competency_score)

            provided = self.scoring_summary.competency_scores.model_dump(exclude_none=True)
            computed_comps = {}
            for comp, scores in comp_scores.items():
                if scores:
                    computed_comps[comp] = round(sum(scores) / len(scores), 1)
                elif comp in provided:
                    computed_comps[comp] = provided[comp]

            self.scoring_summary.competency_scores = CompetencyScores.model_validate(computed_comps)

            return self

    class RubricCriterion(BaseSchema):
        criterion: str
        marks: float = Field(gt=0)

    class GeneratedAnswerKeyItem(BaseSchema):
        question_index: int
        question_id: str
        question_text: str
        competency: Literal["LU", "CU", "AU", "CT"]
        max_marks: float = Field(gt=0)
        model_solution: str
        marking_rubric: List[RubricCriterion] = Field(default_factory=list)
        essential_keywords: List[str] = Field(default_factory=list)

        @model_validator(mode="after")
        def validate_rubric_sum(self) -> "GeneratedAnswerKeyItem":
            if self.marking_rubric:
                rubric_sum = sum(item.marks for item in self.marking_rubric)
                if abs(rubric_sum - self.max_marks) > 0.05:
                    scale = self.max_marks / rubric_sum
                    for item in self.marking_rubric:
                        item.marks = round(item.marks * scale, 2)
            return self

    class AnswerKeyGenerationResult(BaseSchema):
        subject: str
        generated_answer_key: List[GeneratedAnswerKeyItem] = Field(default_factory=list)

else:
    # Minimal fallback objects when running without Pydantic installed
    class StudentInfo(BaseSchema):
        pass

    class StepBreakdownItem(BaseSchema):
        pass

    class QuestionEvaluation(BaseSchema):
        pass

    class ScoringSummary(BaseSchema):
        pass

    class EvaluationResult(BaseSchema):
        pass

    class RubricCriterion(BaseSchema):
        pass

    class GeneratedAnswerKeyItem(BaseSchema):
        pass

    class AnswerKeyGenerationResult(BaseSchema):
        pass
