"""Manual grading of submitted homework. Pure functions: they change ORM objects in memory and
the caller commits once, so each request is saved completely or not at all.

What this does NOT do: no automatic or AI marking, no percentages, grades or thresholds, and no
competency score changes (Student scores, baselines and snapshots are never touched). It never
changes the submission, its answers or the frozen question snapshot.

Answer keys and rubrics: read from the frozen snapshot only in to_teacher_evaluation, for the
authorized marking teacher. Never used to compute marks, and never put into the student result,
the queue, audit text, error messages or logs.

Lifecycle: pending -> marked (finalize: every question has a mark; totals stored) -> released
(the student can see it). marked and released are read-only.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm.attributes import flag_modified

from backend.app.models.entities import Student, generate_uuid
from backend.app.modules.differentiated_homework.draft_service import as_utc
from backend.app.modules.differentiated_homework.models import (
    HomeworkAssignmentRecord,
    HomeworkEvaluationItemRecord,
    HomeworkEvaluationRecord,
    HomeworkSubmissionAnswerRecord,
    HomeworkSubmissionRecord,
)
from backend.app.modules.differentiated_homework.schemas import (
    MAX_FEEDBACK_LENGTH,
    EvaluationMarksUpdate,
    EvaluationTransitionRequest,
    StudentResultItemOut,
    StudentResultOut,
    TeacherEvaluationItemOut,
    TeacherEvaluationOut,
    TeacherEvaluationQueueItemOut,
)
from backend.app.modules.differentiated_homework.submission_service import SubmissionMismatch


class EvaluationError(Exception):
    """Base class. Each subclass maps to one HTTP status in the router."""


class NotEvaluable(EvaluationError):
    """The homework can't be evaluated (not submitted yet)."""


class EvaluationLocked(EvaluationError):
    """The evaluation is finalized or released; ordinary updates are refused."""


class EvaluationVersionConflict(EvaluationError):
    """expected_version doesn't match: someone else changed the evaluation first."""


class EvaluationIncomplete(EvaluationError):
    """Finalize was asked for, but some questions have no mark."""


class EvaluationNotFinalized(EvaluationError):
    """Release was asked for on a pending evaluation."""


@dataclass(frozen=True)
class MarkProblem:
    position: int
    reason: str


class InvalidMarks(EvaluationError):
    """One or more mark updates are invalid. Lists every problem."""

    def __init__(self, problems: List[MarkProblem]):
        self.problems = problems
        super().__init__("; ".join(f"position {p.position}: {p.reason}" for p in problems))


class EvaluationMismatch(SubmissionMismatch):
    """Stored evaluation data is inconsistent with its submission or questions. A server-side
    fault (500), like SubmissionMismatch, which it extends so the same mapping applies."""


# --- Consistency ---------------------------------------------------------------------------


def _answers_by_item(
    assignment: HomeworkAssignmentRecord, submission: HomeworkSubmissionRecord
) -> Dict[str, HomeworkSubmissionAnswerRecord]:
    """The submission's answers keyed by frozen question ID. Fails closed on inconsistent data."""
    if submission.assignment_id != assignment.id or submission.student_id != assignment.student_id:
        raise EvaluationMismatch("The submission doesn't belong to this assignment.")
    item_ids = {item.id for item in assignment.draft.items}
    answers = {}
    for answer in submission.answers:
        if answer.draft_item_id not in item_ids or answer.draft_item_id in answers:
            raise EvaluationMismatch("A stored answer doesn't match this assignment's questions.")
        answers[answer.draft_item_id] = answer
    return answers


def check_evaluation(
    evaluation: HomeworkEvaluationRecord,
    assignment: HomeworkAssignmentRecord,
    submission: HomeworkSubmissionRecord,
) -> None:
    """Refuse (EvaluationMismatch) if the stored evaluation is inconsistent anywhere:
    - it belongs to a different submission, assignment, student or school;
    - the submission isn't a submitted one (only submitted homework is ever evaluated);
    - its items aren't exactly one per frozen question, with the same positions and maximum marks;
    - once finalized, any question is unmarked, a mark is out of range, or the stored total
      isn't the sum of the marks;
    - the finalize or release details don't match the status.
    The database enforces most of these too; this catches anything written around it."""
    _answers_by_item(assignment, submission)
    if (evaluation.submission_id != submission.id or evaluation.assignment_id != assignment.id
            or evaluation.student_id != assignment.student_id or evaluation.school_id != assignment.school_id):
        raise EvaluationMismatch("The evaluation doesn't belong to this submission.")
    if submission.status != "submitted" or submission.submitted_at is None:
        raise EvaluationMismatch("The evaluation's submission isn't a submitted one.")
    expected = {item.id: (item.position, item.marks) for item in assignment.draft.items}
    actual = {item.draft_item_id: (item.position, item.max_marks) for item in evaluation.items}
    if len(evaluation.items) != len(actual) or actual != expected:
        raise EvaluationMismatch("The evaluation's questions don't match the homework's questions.")
    if evaluation.total_max != sum(max_marks for _, max_marks in expected.values()):
        raise EvaluationMismatch("The evaluation's total doesn't match its questions.")
    for item in evaluation.items:
        if item.awarded_marks is not None and not 0 <= item.awarded_marks <= item.max_marks:
            raise EvaluationMismatch("A stored mark is out of range.")
    if evaluation.status not in ("pending", "marked", "released"):
        raise EvaluationMismatch("The evaluation has an unknown status.")
    if evaluation.status == "pending":
        if evaluation.total_awarded is not None or evaluation.finalized_at is not None:
            raise EvaluationMismatch("A pending evaluation has finalized details.")
    else:
        if any(item.awarded_marks is None for item in evaluation.items):
            raise EvaluationMismatch("A finalized evaluation has an unmarked question.")
        if evaluation.total_awarded != sum(item.awarded_marks for item in evaluation.items):
            raise EvaluationMismatch("The stored total doesn't match the marks.")
        if evaluation.finalized_at is None or evaluation.finalized_by is None:
            raise EvaluationMismatch("A finalized evaluation has no finalize details.")
    if (evaluation.status == "released") != (evaluation.released_at is not None and evaluation.released_by is not None):
        raise EvaluationMismatch("The release details don't match the status.")


# --- Creating ----------------------------------------------------------------------------


def build_evaluation(
    assignment: HomeworkAssignmentRecord,
    submission: Optional[HomeworkSubmissionRecord],
    teacher_id: str,
    now: datetime,
) -> HomeworkEvaluationRecord:
    """A new pending evaluation with one unmarked item per frozen question (answered or not).
    Only for submitted homework. No marks are assigned."""
    if submission is None or submission.status != "submitted":
        raise NotEvaluable("Only submitted homework can be evaluated.")
    _answers_by_item(assignment, submission)
    questions = sorted(assignment.draft.items, key=lambda item: item.position)
    if not questions:
        raise EvaluationMismatch("The homework has no questions.")
    for item in questions:
        if type(item.marks) is not int or item.marks < 0:
            raise EvaluationMismatch("A frozen question has invalid maximum marks.")
    return HomeworkEvaluationRecord(
        id=generate_uuid(),
        submission_id=submission.id,
        assignment_id=assignment.id,
        student_id=assignment.student_id,
        school_id=assignment.school_id,
        status="pending",
        total_max=sum(item.marks for item in questions),
        total_awarded=None,
        created_by=teacher_id,
        created_at=now,
        updated_at=now,
        items=[
            HomeworkEvaluationItemRecord(
                id=generate_uuid(), draft_item_id=item.id, position=item.position, max_marks=item.marks,
                awarded_marks=None, feedback=None, created_at=now,
            )
            for item in questions
        ],
    )


# --- Changing ----------------------------------------------------------------------------


def _check_version(evaluation: HomeworkEvaluationRecord, expected_version: int) -> None:
    if expected_version != evaluation.version:
        raise EvaluationVersionConflict("The evaluation was changed elsewhere; reload it and try again.")


def _touch(evaluation: HomeworkEvaluationRecord, now: datetime) -> None:
    """Always write the evaluation row so its version goes up, even for item-only changes and
    repeated timestamps (the same approach as submissions)."""
    evaluation.updated_at = now
    flag_modified(evaluation, "updated_at")


def apply_marks(
    evaluation: HomeworkEvaluationRecord,
    request: EvaluationMarksUpdate,
    teacher_id: str,
    now: datetime,
) -> None:
    """Set marks and/or feedback on some questions of a pending evaluation. Everything is checked
    before anything changes; one bad entry rejects the whole request."""
    if evaluation.status != "pending":
        raise EvaluationLocked("This evaluation has been finalized and can't be changed.")
    _check_version(evaluation, request.expected_version)

    items = {item.position: item for item in evaluation.items}
    problems: List[MarkProblem] = []
    seen = set()
    for update in request.items:
        if update.position in seen:
            problems.append(MarkProblem(update.position, "this position appears more than once"))
            continue
        seen.add(update.position)
        item = items.get(update.position)
        if item is None:
            problems.append(MarkProblem(update.position, "there is no question at this position"))
            continue
        given = update.model_fields_set
        if "awarded_marks" in given:
            mark = update.awarded_marks
            if type(mark) is not int or not 0 <= mark <= item.max_marks:
                problems.append(MarkProblem(update.position, f"awarded_marks must be a whole number from 0 to "
                                                             f"{item.max_marks}"))
        if "feedback" in given:
            if update.feedback is None or len(update.feedback) > MAX_FEEDBACK_LENGTH:
                problems.append(MarkProblem(update.position, f"feedback must be text of at most "
                                                             f"{MAX_FEEDBACK_LENGTH} characters"))
    if problems:
        raise InvalidMarks(problems)

    for update in request.items:
        item = items[update.position]
        given = update.model_fields_set
        if "awarded_marks" in given:
            item.awarded_marks = update.awarded_marks
        if "feedback" in given:
            item.feedback = update.feedback if update.feedback.strip() else None
        item.marked_by = teacher_id
        item.marked_at = now
    _touch(evaluation, now)


def finalize_evaluation(
    evaluation: HomeworkEvaluationRecord, request: EvaluationTransitionRequest, teacher_id: str, now: datetime
) -> None:
    """pending -> marked. Every question needs an explicit mark (0 included). Stores the totals."""
    if evaluation.status != "pending":
        raise EvaluationLocked("This evaluation has already been finalized.")
    _check_version(evaluation, request.expected_version)
    unmarked = [item.position for item in evaluation.items if item.awarded_marks is None]
    if unmarked:
        raise EvaluationIncomplete(f"Every question needs a mark before finalizing. Unmarked: {unmarked}.")
    evaluation.total_awarded = sum(item.awarded_marks for item in evaluation.items)
    evaluation.total_max = sum(item.max_marks for item in evaluation.items)
    evaluation.status = "marked"
    evaluation.finalized_by = teacher_id
    evaluation.finalized_at = now
    _touch(evaluation, now)


def release_evaluation(
    evaluation: HomeworkEvaluationRecord, request: EvaluationTransitionRequest, teacher_id: str, now: datetime
) -> bool:
    """marked -> released. Idempotent: an already released evaluation is left exactly as it is
    and False is returned (the caller then writes nothing). True when released now."""
    if evaluation.status == "released":
        return False
    if evaluation.status != "marked":
        raise EvaluationNotFinalized("Only a finalized evaluation can be released.")
    _check_version(evaluation, request.expected_version)
    evaluation.status = "released"
    evaluation.released_by = teacher_id
    evaluation.released_at = now
    _touch(evaluation, now)
    return True


# --- Output ------------------------------------------------------------------------------


def _question_rows(assignment, submission, evaluation):
    """(frozen question, answer or None, evaluation item) for every question, by position."""
    answers = _answers_by_item(assignment, submission)
    items = {item.draft_item_id: item for item in evaluation.items}
    for question in sorted(assignment.draft.items, key=lambda q: q.position):
        yield question, answers.get(question.id), items[question.id]


def to_teacher_evaluation(
    evaluation: HomeworkEvaluationRecord,
    assignment: HomeworkAssignmentRecord,
    submission: HomeworkSubmissionRecord,
    student: Optional[Student],
) -> TeacherEvaluationOut:
    check_evaluation(evaluation, assignment, submission)
    rows = [
        TeacherEvaluationItemOut(
            position=question.position, text=question.text, type=question.type,
            options=list(question.options_json or []), max_marks=item.max_marks, answered=answer is not None,
            answer_text=answer.answer_text if answer else None,
            selected_option_index=answer.selected_option_index if answer else None,
            awarded_marks=item.awarded_marks, feedback=item.feedback, marked_by=item.marked_by,
            marked_at=as_utc(item.marked_at),
            # Teacher-only, from the frozen snapshot, exactly as stored; null when absent.
            correct_answer=question.correct_answer, marking_rubric=question.marking_rubric,
        )
        for question, answer, item in _question_rows(assignment, submission, evaluation)
    ]
    return TeacherEvaluationOut(
        id=evaluation.id, assignment_id=assignment.id, student_id=assignment.student_id,
        student_name=student.name if student is not None else None, status=evaluation.status,
        version=evaluation.version, submitted_at=as_utc(submission.submitted_at), is_late=bool(submission.is_late),
        total_max=evaluation.total_max, total_awarded=evaluation.total_awarded,
        marked_count=sum(1 for r in rows if r.awarded_marks is not None), question_count=len(rows),
        created_by=evaluation.created_by, created_at=as_utc(evaluation.created_at),
        updated_at=as_utc(evaluation.updated_at), finalized_by=evaluation.finalized_by,
        finalized_at=as_utc(evaluation.finalized_at), released_by=evaluation.released_by,
        released_at=as_utc(evaluation.released_at), items=rows,
    )


def to_queue_item(
    assignment: HomeworkAssignmentRecord,
    submission: HomeworkSubmissionRecord,
    student: Optional[Student],
    evaluation: Optional[HomeworkEvaluationRecord],
) -> TeacherEvaluationQueueItemOut:
    if evaluation is not None:
        check_evaluation(evaluation, assignment, submission)
    else:
        _answers_by_item(assignment, submission)
    return TeacherEvaluationQueueItemOut(
        student_id=assignment.student_id,
        student_name=student.name if student is not None else None,
        submitted_at=as_utc(submission.submitted_at),
        is_late=bool(submission.is_late),
        evaluation_status=evaluation.status if evaluation is not None else "not_started",
        evaluation_id=evaluation.id if evaluation is not None else None,
        marked_count=sum(1 for i in evaluation.items if i.awarded_marks is not None) if evaluation else 0,
        question_count=len(assignment.draft.items),
    )


def to_student_result(
    evaluation: HomeworkEvaluationRecord,
    assignment: HomeworkAssignmentRecord,
    submission: HomeworkSubmissionRecord,
) -> StudentResultOut:
    """Released results only; the caller must already have checked the status."""
    if evaluation.status != "released":
        raise EvaluationMismatch("Only released results can be shown to a student.")
    check_evaluation(evaluation, assignment, submission)
    items = [
        StudentResultItemOut(
            position=question.position, text=question.text, type=question.type,
            options=list(question.options_json or []),
            answer_text=answer.answer_text if answer else None,
            selected_option_index=answer.selected_option_index if answer else None,
            max_marks=item.max_marks, awarded_marks=item.awarded_marks, feedback=item.feedback,
        )
        for question, answer, item in _question_rows(assignment, submission, evaluation)
    ]
    return StudentResultOut(
        assignment_id=assignment.id, released_at=as_utc(evaluation.released_at),
        total_awarded=evaluation.total_awarded, total_max=evaluation.total_max, items=items,
    )
