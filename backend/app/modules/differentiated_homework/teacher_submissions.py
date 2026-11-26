"""Teacher-facing, read-only views of student submissions. Pure functions: no database I/O and
no writes. Nothing here reads correct_answer or marking_rubric, or computes marks or scores.

Roster: each homework_assignments row names exactly one student (assignment.student_id). That
row is the authoritative roster, so a student with no submission still appears (not_started).
The roster is never derived from submission rows.
"""
from typing import Dict, List, Optional

from backend.app.models.entities import Student
from backend.app.modules.differentiated_homework.draft_service import as_utc
from backend.app.modules.differentiated_homework.models import (
    HomeworkAssignmentRecord,
    HomeworkSubmissionAnswerRecord,
    HomeworkSubmissionRecord,
)
from backend.app.modules.differentiated_homework.schemas import (
    TeacherAssignmentSubmissionsOut,
    TeacherQuestionAnswerOut,
    TeacherStudentSubmissionOut,
    TeacherSubmissionCountsOut,
    TeacherSubmissionDetailOut,
)
from backend.app.modules.differentiated_homework.submission_service import SubmissionMismatch


def _answers_by_position(
    submission: Optional[HomeworkSubmissionRecord], assignment: HomeworkAssignmentRecord
) -> Dict[int, HomeworkSubmissionAnswerRecord]:
    """Map each stored answer to its question position. Refuses inconsistent data."""
    if submission is None:
        return {}
    if submission.assignment_id != assignment.id or submission.student_id != assignment.student_id:
        raise SubmissionMismatch("A stored submission doesn't belong to this assignment.")
    positions = {item.id: item.position for item in assignment.draft.items}
    answers = {}
    for answer in submission.answers:
        if answer.draft_item_id not in positions:
            raise SubmissionMismatch("A stored answer doesn't match this assignment's questions.")
        answers[positions[answer.draft_item_id]] = answer
    return answers


def _state(submission: Optional[HomeworkSubmissionRecord]) -> dict:
    """Status, times and the late flag. is_late is only meaningful once submitted, so it is
    null otherwise: an in-progress submission is never labelled late."""
    if submission is None:
        return {"status": "not_started", "started_at": None, "updated_at": None, "submitted_at": None,
                "is_late": None}
    submitted = submission.status == "submitted"
    return {
        "status": submission.status,
        "started_at": as_utc(submission.started_at),
        "updated_at": as_utc(submission.updated_at),
        "submitted_at": as_utc(submission.submitted_at),
        "is_late": bool(submission.is_late) if submitted else None,
    }


def student_row(
    assignment: HomeworkAssignmentRecord, student: Optional[Student], submission: Optional[HomeworkSubmissionRecord]
) -> TeacherStudentSubmissionOut:
    answers = _answers_by_position(submission, assignment)
    return TeacherStudentSubmissionOut(
        student_id=assignment.student_id,
        student_name=student.name if student is not None else None,
        answered_count=len(answers),
        question_count=len(assignment.draft.items),
        **_state(submission),
    )


def counts(rows: List[TeacherStudentSubmissionOut]) -> TeacherSubmissionCountsOut:
    return TeacherSubmissionCountsOut(
        total_students=len(rows),
        not_started=sum(1 for r in rows if r.status == "not_started"),
        in_progress=sum(1 for r in rows if r.status == "in_progress"),
        submitted=sum(1 for r in rows if r.status == "submitted"),
        submitted_late=sum(1 for r in rows if r.status == "submitted" and r.is_late),
    )


def assignment_overview(
    assignment: HomeworkAssignmentRecord,
    subject_name: Optional[str],
    rows: List[TeacherStudentSubmissionOut],
) -> TeacherAssignmentSubmissionsOut:
    return TeacherAssignmentSubmissionsOut(
        assignment_id=assignment.id,
        subject_id=assignment.subject_id,
        subject_name=subject_name,
        assignment_status=assignment.status,
        assigned_at=as_utc(assignment.assigned_at),
        due_at=as_utc(assignment.due_at),
        question_count=len(assignment.draft.items),
        counts=counts(rows),
        students=rows,
    )


def submission_detail(
    assignment: HomeworkAssignmentRecord, student: Optional[Student], submission: Optional[HomeworkSubmissionRecord]
) -> TeacherSubmissionDetailOut:
    """One student's answers next to the frozen questions (text, type and options only)."""
    answers = _answers_by_position(submission, assignment)
    questions = []
    for item in sorted(assignment.draft.items, key=lambda i: i.position):
        answer = answers.get(item.position)
        questions.append(TeacherQuestionAnswerOut(
            position=item.position,
            text=item.text,
            type=item.type,
            options=list(item.options_json or []),
            answered=answer is not None,
            answer_text=answer.answer_text if answer is not None else None,
            selected_option_index=answer.selected_option_index if answer is not None else None,
        ))
    return TeacherSubmissionDetailOut(
        assignment_id=assignment.id,
        student_id=assignment.student_id,
        student_name=student.name if student is not None else None,
        answered_count=len(answers),
        question_count=len(questions),
        questions=questions,
        **_state(submission),
    )
