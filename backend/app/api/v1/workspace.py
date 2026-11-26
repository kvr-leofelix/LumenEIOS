"""Role-scoped workspace snapshot that powers the dashboards (camelCase, matching src/types).

    admin      every school the account manages
    principal  their school
    teacher    their school (the students of the classes they teach are listed first-class via teacherAssignments)
    student    their own record, their class and the assessments set for it
    parent     their linked children, their classes and assessments

Answer keys and rubrics are removed from assessments for students and parents.
"""
from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user, user_school_ids
from backend.app.db.session import get_db
from backend.app.models.entities import (
    Assessment, AssessmentSubmission, AssignmentOcrUpload, ClassSection, ParentStudentLink, School, Student,
    StudentCompetencySnapshot, StudentOcrHistory, Subject, TeacherAssignment, User,
)
from backend.app.modules.differentiated_homework.student_access import resolve_linked_student
from backend.app.services.lost_period_service import school_lost_days

router = APIRouter(tags=["Workspace"])


def _scores(o, prefix: str = "") -> dict:
    g = lambda name: getattr(o, f"{prefix}{name}")  # noqa: E731
    if prefix:
        return {"LU": g("lu"), "CU": g("cu"), "AU": g("au"), "CT": g("ct"), "overall": g("overall")}
    return {"LU": o.lu_score, "CU": o.cu_score, "AU": o.au_score, "CT": o.ct_score, "overall": o.overall_score}


def school_out(s: School) -> dict:
    return {"id": s.id, "name": s.name, "location": s.location, "state": s.state,
            "infrastructureTier": s.infrastructure_tier, "academicYear": s.academic_year,
            "principalId": s.principal_id or "", "principalName": s.principal_name or "",
            "studentCount": s.student_count, "teacherCount": s.teacher_count, "classCount": s.class_count,
            "pacingRisk": s.pacing_risk, "description": s.description or "",
            "officialWorkingDays": s.official_working_days}


def class_out(c: ClassSection) -> dict:
    return {"id": c.id, "schoolId": c.school_id, "grade": c.grade, "section": c.section, "name": c.name,
            "classTeacherId": c.class_teacher_id or "", "classTeacherName": c.class_teacher_name or "",
            "studentCount": c.student_count, "subjectIds": list(c.subject_ids_json or [])}


def student_out(s: Student, parents: Dict[str, List[str]]) -> dict:
    return {"id": s.id, "schoolId": s.school_id, "classId": s.class_id, "className": s.class_name, "name": s.name,
            "rollNo": s.roll_no, "admissionNo": s.admission_no, "dateOfBirth": s.date_of_birth,
            "gender": s.gender if s.gender in ("M", "F") else "Other", "attendancePct": s.attendance_pct,
            "competencies": _scores(s), "baselineCompetencies": _scores(s, "baseline_"),
            "learningModality": s.learning_modality, "parentId": s.parent_id or "",
            "parentNames": parents.get(s.id, []),
            "homeworkCompletionRate": s.homework_completion_rate, "needsSupport": bool(s.needs_support),
            "supportArea": s.support_area or None,
            "joinedYear": int("20" + s.admission_no[3:5]) if s.admission_no and s.admission_no[3:5].isdigit() else None}


def assessment_out(a: Assessment, hide_keys: bool) -> dict:
    questions = []
    for i, q in enumerate(a.questions_json or [], start=1):
        item = {"id": q.get("id") or f"{a.id}-q{i}", "assessmentId": a.id, "subjectId": a.subject_id,
                "text": q.get("text", ""), "type": q.get("type", "short"), "options": q.get("options") or [],
                "marks": q.get("marks") or 0, "competency": q.get("competency") or "CU",
                "bloomLevel": q.get("bloom_level") or q.get("bloomLevel") or "Understand", "topic": q.get("topic")}
        if not hide_keys:
            item["correctAnswer"] = q.get("correct_answer") or q.get("correctAnswer")
            item["markingRubric"] = q.get("marking_rubric") or q.get("markingRubric")
        questions.append(item)
    return {"id": a.id, "schoolId": a.school_id, "classId": a.class_id, "subjectId": a.subject_id, "title": a.title,
            "cycleNumber": a.cycle_number, "date": a.date, "durationMinutes": a.duration_minutes,
            "totalMarks": a.total_marks, "questions": questions,
            "status": a.status if a.status in ("draft", "scheduled", "graded") else "graded",
            "competencyFocus": list(a.competency_focus_json or [])}


def result_out(r: AssessmentSubmission) -> dict:
    return {"id": r.id, "assessmentId": r.assessment_id, "studentId": r.student_id, "studentName": r.student_name,
            "marksObtained": r.marks_obtained, "totalMarks": r.total_marks, "percentage": r.percentage,
            "scores": _scores(r), "feedback": r.feedback, "submissionDate": r.submission_date,
            "isScanned": bool(r.is_scanned)}


@router.get("/workspace")
async def workspace(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    role = user.role
    if role == "admin":
        school_ids = {s for (s,) in (await db.execute(select(School.id))).all()}
    else:
        school_ids = await user_school_ids(db, user)

    own_students: List[Student] = []
    if role == "student":
        me = await resolve_linked_student(db, user)
        own_students = [me] if me else []
    elif role == "parent":
        child_ids = (await db.execute(select(ParentStudentLink.student_id).filter_by(parent_user_id=user.id))).scalars().all()
        own_students = list((await db.execute(select(Student).filter(Student.id.in_(child_ids)))).scalars().all()) if child_ids else []
    learner_view = role in ("student", "parent")

    schools = (await db.execute(select(School).filter(School.id.in_(school_ids)).order_by(School.name))).scalars().all()
    if learner_view:
        class_ids = {s.class_id for s in own_students}
        classes = (await db.execute(select(ClassSection).filter(ClassSection.id.in_(class_ids)))).scalars().all()
        students = own_students
    else:
        classes = (await db.execute(select(ClassSection).filter(ClassSection.school_id.in_(school_ids))
                                    .order_by(ClassSection.school_id, ClassSection.grade, ClassSection.section))).scalars().all()
        students = (await db.execute(select(Student).filter(Student.school_id.in_(school_ids))
                                     .order_by(Student.class_id, Student.roll_no))).scalars().all()
    class_ids = [c.id for c in classes]
    student_ids = [s.id for s in students]

    parent_rows = (await db.execute(select(ParentStudentLink.student_id, User.name)
                                    .join(User, User.id == ParentStudentLink.parent_user_id)
                                    .filter(ParentStudentLink.student_id.in_(student_ids)))).all() if student_ids else []
    parents: Dict[str, List[str]] = {}
    for sid, name in parent_rows:
        parents.setdefault(sid, []).append(name)

    assessments = (await db.execute(select(Assessment).filter(Assessment.class_id.in_(class_ids))
                                    .order_by(Assessment.date, Assessment.title))).scalars().all() if class_ids else []
    results = (await db.execute(select(AssessmentSubmission).filter(AssessmentSubmission.student_id.in_(student_ids))
                                .order_by(AssessmentSubmission.submission_date))).scalars().all() if student_ids else []
    snapshots = (await db.execute(select(StudentCompetencySnapshot)
                                  .filter(StudentCompetencySnapshot.student_id.in_(student_ids))
                                  .order_by(StudentCompetencySnapshot.recorded_at))).scalars().all() if student_ids else []
    subjects = (await db.execute(select(Subject).order_by(Subject.name))).scalars().all()

    teachers, assignments = [], []
    if not learner_view:
        assignments = (await db.execute(select(TeacherAssignment).filter(TeacherAssignment.school_id.in_(school_ids)))).scalars().all()
        teachers = (await db.execute(select(User).filter(User.role == "teacher", User.school_id.in_(school_ids))
                                     .order_by(User.name))).scalars().all()
    else:
        # Learners see who teaches them (name and subject only).
        assignments = (await db.execute(select(TeacherAssignment).filter(TeacherAssignment.class_id.in_(class_ids)))).scalars().all()
        teacher_ids = {a.teacher_id for a in assignments}
        teachers = (await db.execute(select(User).filter(User.id.in_(teacher_ids)))).scalars().all() if teacher_ids else []

    # Class-level averages give learners and parents context without exposing classmates.
    class_averages: Dict[str, dict] = {}
    if class_ids:
        peers = (await db.execute(select(Student).filter(Student.class_id.in_(class_ids)))).scalars().all()
        for cid in class_ids:
            group = [p for p in peers if p.class_id == cid]
            if group:
                class_averages[cid] = {k: round(sum(_scores(p)[k] for p in group) / len(group))
                                       for k in ("LU", "CU", "AU", "CT", "overall")}
        if learner_view:
            exam_avg: Dict[str, float] = {}
            rows = (await db.execute(select(AssessmentSubmission.assessment_id, AssessmentSubmission.percentage)
                                     .join(Assessment, Assessment.id == AssessmentSubmission.assessment_id)
                                     .filter(Assessment.class_id.in_(class_ids)))).all()
            sums: Dict[str, List[int]] = {}
            for aid, pct in rows:
                sums.setdefault(aid, []).append(pct)
            exam_avg = {aid: round(sum(v) / len(v)) for aid, v in sums.items()}
        else:
            exam_avg = {}

    # Educators: handwritten uploads per open assignment that still need evaluating (no published grade yet).
    pending_uploads: Dict[str, int] = {}
    uploaded_students: Dict[str, int] = {}
    if not learner_view and class_ids:
        rows = (await db.execute(
            select(AssignmentOcrUpload.assessment_id, StudentOcrHistory.student_id)
            .join(StudentOcrHistory, StudentOcrHistory.id == AssignmentOcrUpload.history_id)
            .join(Assessment, Assessment.id == AssignmentOcrUpload.assessment_id)
            .filter(Assessment.class_id.in_(class_ids)))).all()
        graded = {(r.assessment_id, r.student_id) for r in results}
        seen = set()
        for aid, sid in rows:
            if (aid, sid) in seen:
                continue
            seen.add((aid, sid))
            uploaded_students[aid] = uploaded_students.get(aid, 0) + 1
            if (aid, sid) not in graded:
                pending_uploads[aid] = pending_uploads.get(aid, 0) + 1
    elif learner_view and student_ids:
        rows = (await db.execute(
            select(AssignmentOcrUpload.assessment_id)
            .join(StudentOcrHistory, StudentOcrHistory.id == AssignmentOcrUpload.history_id)
            .filter(StudentOcrHistory.student_id.in_(student_ids)))).scalars().all()
        for aid in rows:
            uploaded_students[aid] = 1

    disruptions = [] if learner_view else await school_lost_days(db, school_ids)

    return {
        "role": role,
        "disruptions": disruptions,
        "pendingUploads": pending_uploads,
        "uploadedCounts": uploaded_students,
        "schools": [school_out(s) for s in schools],
        "classes": [class_out(c) for c in classes],
        "subjects": [{"id": s.id, "name": s.name, "code": s.code, "grade": s.grade, "iconName": s.icon_name} for s in subjects],
        "students": [student_out(s, parents) for s in students],
        "teachers": [{"id": t.id, "name": t.name, "email": "" if learner_view else t.email, "schoolId": t.school_id,
                      "designation": t.designation or "", "role": "teacher"} for t in teachers],
        "teacherAssignments": [{"teacherId": a.teacher_id, "classId": a.class_id, "subjectId": a.subject_id,
                                "schoolId": a.school_id} for a in assignments],
        "assessments": [assessment_out(a, learner_view) for a in assessments],
        "assessmentResults": [result_out(r) for r in results],
        "snapshots": [{"studentId": s.student_id, "recordedAt": s.recorded_at.isoformat() if s.recorded_at else None,
                       "cycleNumber": s.cycle_number, "scores": _scores(s), "notes": s.notes} for s in snapshots],
        "classAverages": class_averages,
        "assessmentAverages": exam_avg if class_ids else {},
    }
