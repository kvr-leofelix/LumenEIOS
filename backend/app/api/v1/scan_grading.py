"""Handwritten-work grading: student uploads -> OCR text -> evaluator draft -> teacher publishes the grade.

Students upload photos/PDFs of handwritten answers against an open assignment (Upload Beta). OCR text is
stored as StudentOcrHistory linked to the assignment. The teacher opens the class list for the assignment,
runs the evaluator (POST /ocr/evaluate-scan) on a student's text, reviews/edits the marks, and publishes:

    POST /assessments/{assessment_id}/grade
        -> AssessmentSubmission (is_scanned) with marks and per-competency scores
        -> the student's LU/CU/AU/CT parameters move towards the competencies this work assessed
        -> a progress snapshot, and notifications to the student and their parents.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import require_roles, user_school_ids
from backend.app.db.session import get_db
from backend.app.models.entities import (
    Assessment, AssessmentSubmission, AssignmentOcrUpload, AuditEvent, ClassSection, Notification,
    ParentStudentLink, Student, StudentOcrHistory, Subject, User, utc_now,
)
from backend.app.services.kc_graph_service import record_teacher_confirmed_marks
from backend.app.services.competency_update import (
    DIMENSIONS, apply_observation, clamp, dimension_scores_from_questions, snapshot,
)

router = APIRouter(tags=["Assessments"])
EDUCATORS = ("admin", "principal", "teacher")


async def _assessment_for(db: AsyncSession, user: User, assessment_id: str) -> Assessment:
    assessment = await db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    if user.role != "admin" and assessment.school_id not in await user_school_ids(db, user):
        raise HTTPException(status_code=404, detail="Assignment not found.")
    return assessment


def _questions(assessment: Assessment) -> List[dict]:
    out = []
    for index, q in enumerate(assessment.questions_json or [], start=1):
        out.append({
            "index": index, "text": q.get("text", ""), "marks": q.get("marks") or 0,
            "competency": q.get("competency"), "type": q.get("type"), "options": q.get("options") or [],
            "correct_answer": q.get("correct_answer") or q.get("correctAnswer"),
            "marking_rubric": q.get("marking_rubric") or q.get("markingRubric"),
            "topic": q.get("topic"),
        })
    return out


@router.get("/assessments/{assessment_id}/uploads")
async def assignment_uploads(
    assessment_id: str,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles(*EDUCATORS)),
):
    """Every student in the assignment's class, their uploaded handwritten work and grading status."""
    assessment = await _assessment_for(db, educator, assessment_id)
    section = await db.get(ClassSection, assessment.class_id)
    subject = await db.get(Subject, assessment.subject_id)
    students = (await db.execute(select(Student).filter(Student.class_id == assessment.class_id)
                                 .order_by(Student.roll_no))).scalars().all()
    uploads = (await db.execute(
        select(StudentOcrHistory)
        .join(AssignmentOcrUpload, AssignmentOcrUpload.history_id == StudentOcrHistory.id)
        .filter(AssignmentOcrUpload.assessment_id == assessment_id)
        .order_by(StudentOcrHistory.created_at.desc())
    )).scalars().all()
    by_student: dict = {}
    for row in uploads:
        by_student.setdefault(row.student_id, []).append({
            "history_id": row.id, "file_name": row.file_name, "extracted_text": row.extracted_text,
            "pages_processed": row.pages_processed, "uploaded_at": row.created_at.isoformat() if row.created_at else None,
        })
    graded = {s.student_id: s for s in (await db.execute(
        select(AssessmentSubmission).filter(AssessmentSubmission.assessment_id == assessment_id))).scalars().all()}
    return {
        "assessment": {"id": assessment.id, "title": assessment.title, "date": assessment.date,
                       "status": assessment.status, "total_marks": assessment.total_marks,
                       "class_id": assessment.class_id, "class_name": section.name if section else None,
                       "subject_id": assessment.subject_id, "subject_name": subject.name if subject else None,
                       "questions": _questions(assessment)},
        "students": [{
            "student_id": st.id, "name": st.name, "roll_no": st.roll_no,
            "uploads": by_student.get(st.id, []),
            "grade": ({"submission_id": graded[st.id].id, "marks_obtained": graded[st.id].marks_obtained,
                       "total_marks": graded[st.id].total_marks, "percentage": graded[st.id].percentage,
                       "feedback": graded[st.id].feedback, "graded_on": graded[st.id].submission_date}
                      if st.id in graded else None),
        } for st in students],
        "summary": {"students": len(students), "uploaded": len(by_student),
                    "graded": sum(1 for st in students if st.id in graded)},
    }


class GradeItem(BaseModel):
    question_index: int = Field(ge=1)
    awarded_marks: float = Field(ge=0)
    feedback: Optional[str] = Field(default=None, max_length=2000)


class PublishGradeRequest(BaseModel):
    student_id: str
    history_id: Optional[str] = None
    items: List[GradeItem] = Field(min_length=1)
    overall_feedback: Optional[str] = Field(default=None, max_length=4000)
    evaluated_by: Optional[str] = Field(default=None, max_length=50)  # "qwen", "gemini" or "teacher"


@router.post("/assessments/{assessment_id}/grade")
async def publish_grade(
    assessment_id: str,
    req: PublishGradeRequest,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles(*EDUCATORS)),
):
    """Publish a teacher-confirmed grade for one student's handwritten work and update their parameters."""
    assessment = await _assessment_for(db, educator, assessment_id)
    student = await db.get(Student, req.student_id)
    if not student or student.class_id != assessment.class_id:
        raise HTTPException(status_code=404, detail="That student is not in this assignment's class.")
    if req.history_id:
        link = await db.get(AssignmentOcrUpload, req.history_id)
        history = await db.get(StudentOcrHistory, req.history_id)
        if not link or link.assessment_id != assessment_id or not history or history.student_id != student.id:
            raise HTTPException(status_code=404, detail="That upload does not belong to this student and assignment.")

    questions = {q["index"]: q for q in _questions(assessment)}
    given = {item.question_index: item for item in req.items}
    if set(given) != set(questions):
        raise HTTPException(status_code=422, detail="Give marks for every question of the assignment (0 is allowed).")
    graded = []
    for index, q in questions.items():
        item = given[index]
        if item.awarded_marks > q["marks"]:
            raise HTTPException(status_code=422, detail=f"Question {index}: at most {q['marks']} marks.")
        graded.append({"competency": q["competency"], "awarded_marks": item.awarded_marks, "max_marks": q["marks"]})

    total = sum(q["marks"] for q in questions.values()) or assessment.total_marks
    obtained = round(sum(g["awarded_marks"] for g in graded))
    pct = clamp(100 * obtained / total) if total else 0
    dims = dimension_scores_from_questions(graded)
    before = {d: getattr(student, {"LU": "lu_score", "CU": "cu_score", "AU": "au_score", "CT": "ct_score"}[d])
              for d in DIMENSIONS} | {"overall": student.overall_score}
    per_question = " ".join(f"Q{i}: {given[i].feedback.strip().rstrip('.;')}." for i in sorted(given) if given[i].feedback and given[i].feedback.strip())
    feedback = " ".join(x for x in [req.overall_feedback, per_question] if x) or None

    existing = (await db.execute(select(AssessmentSubmission).filter_by(
        assessment_id=assessment_id, student_id=student.id))).scalars().first()
    today = utc_now().date().isoformat()
    if existing:
        # Re-grading corrects the marks; the parameters already moved once for this work.
        existing.marks_obtained, existing.total_marks, existing.percentage = obtained, total, pct
        existing.feedback, existing.submission_date = feedback, today
        for d, col in (("LU", "lu_score"), ("CU", "cu_score"), ("AU", "au_score"), ("CT", "ct_score")):
            if d in dims:
                setattr(existing, col, dims[d])
        submission, after = existing, before
    else:
        submission = AssessmentSubmission(
            assessment_id=assessment_id, student_id=student.id, student_name=student.name,
            marks_obtained=obtained, total_marks=total, percentage=pct,
            lu_score=dims.get("LU", student.lu_score), cu_score=dims.get("CU", student.cu_score),
            au_score=dims.get("AU", student.au_score), ct_score=dims.get("CT", student.ct_score),
            overall_score=clamp(sum(dims.values()) / len(dims)) if dims else pct,
            feedback=feedback, submission_date=today, is_scanned=True,
        )
        db.add(submission)
        await db.flush()
        # Weight by how much evidence the work carries: a 7-mark worksheet nudges, a 25+ mark paper counts fully.
        weight = round(0.1 + 0.3 * min(1.0, total / 25), 3)
        after = apply_observation(student, dims, weight=weight)
        db.add(snapshot(student, cycle_number=assessment.cycle_number, subject_id=assessment.subject_id,
                        assessment_id=assessment_id, submission_id=submission.id,
                        notes=f"Graded: {assessment.title} ({obtained}/{total})"))

    # Teacher-confirmed marks also reach the concept graph through the paper's confirmed concept links.
    await record_teacher_confirmed_marks(
        db, assessment=assessment, student_id=student.id,
        source_key=req.history_id or f"submission:{submission.id}",
        marks={item.question_index: item.awarded_marks for item in req.items},
    )
    subject = await db.get(Subject, assessment.subject_id)
    message = (f"{student.name} scored {obtained}/{total} ({pct}%) in {assessment.title}."
               + (f" Teacher's note: {req.overall_feedback}" if req.overall_feedback else ""))
    db.add(Notification(user_id=student.id, title="Your work has been graded", message=message,
                        type="success", link="/student/dashboard"))
    parents = (await db.execute(select(ParentStudentLink.parent_user_id).filter_by(student_id=student.id))).scalars().all()
    for parent_id in parents:
        db.add(Notification(user_id=parent_id, title=f"New result: {subject.name if subject else 'assignment'}",
                            message=message, type="info", link="/parent/dashboard"))
    db.add(AuditEvent(timestamp=utc_now().strftime("%Y-%m-%d %H:%M"), user_id=educator.id, user_name=educator.name,
                      action="Published handwritten-work grade",
                      details=f"{assessment.title}: {student.name} {obtained}/{total} ({pct}%)"
                              + (f", evaluated by {req.evaluated_by}" if req.evaluated_by else ""),
                      category="assessment"))
    await db.commit()
    return {"submission_id": submission.id, "student_id": student.id, "student_name": student.name,
            "marks_obtained": obtained, "total_marks": total, "percentage": pct,
            "competency_scores": dims, "parameters_before": before, "parameters_after": after,
            "regraded": bool(existing)}
