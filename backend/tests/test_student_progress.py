"""Unified Student Progress: aggregation, source filters, dedupe and authorization."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text

from backend.app.core.security import create_access_token
from backend.app.models.entities import (
    Assessment,
    AssessmentSubmission,
    ClassSection,
    HumanReview,
    ParentStudentLink,
    Student,
    StudentCompetencySnapshot,
    Subject,
    User,
)
from backend.app.modules.differentiated_homework.models import (
    HomeworkAssignmentRecord,
    HomeworkDraftItemRecord,
    HomeworkDraftRecord,
    HomeworkEvaluationItemRecord,
    HomeworkEvaluationRecord,
    HomeworkEvaluationSuggestionRecord,
    HomeworkSubmissionRecord,
    StudentAccountLink,
)
from backend.app.modules.student_progress.service import (
    _percentage,
    build_recommendations,
    build_subject_performance,
)
from backend.app.modules.student_progress.schemas import ProgressEventOut, SubjectPerformanceOut

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
API = "/api/v1"


def uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def bearer(user_id: str, role: str, school_id: str = "school-1") -> dict:
    return {"Authorization": f"Bearer {create_access_token(user_id, school_id=school_id, role=role)}"}


def make_user(role: str, school_id: str) -> User:
    user_id = uid(f"usp-{role}")
    return User(
        id=user_id,
        email=f"{user_id}@test.invalid",
        name=f"USP {role}",
        hashed_password="x",
        role=role,
        school_id=school_id,
    )


def make_student(cls: ClassSection, school_id: str, name: str, **scores) -> Student:
    defaults = dict(
        lu_score=40, cu_score=72, au_score=63, ct_score=54, overall_score=57,
        baseline_lu=30, baseline_cu=50, baseline_au=40, baseline_ct=35, baseline_overall=39,
    )
    defaults.update(scores)
    return Student(
        id=uid("usp-student"),
        school_id=school_id,
        class_id=cls.id,
        class_name=cls.name,
        name=name,
        roll_no=1,
        **defaults,
    )


def make_assignment(student: Student, subject_id: str, created_by: str) -> HomeworkAssignmentRecord:
    items = [
        HomeworkDraftItemRecord(
            position=1,
            source_question_id=uid("src"),
            text="Q1",
            type="mcq",
            options_json=["A", "B"],
            marks=10,
            competency="LU",
            competency_rank=1,
            bloom_level="Apply",
            is_ai_generated=False,
            correct_answer="A",
            marking_rubric=None,
        )
    ]
    draft = HomeworkDraftRecord(
        student_id=student.id,
        school_id=student.school_id,
        subject_id=subject_id,
        created_by=created_by,
        status="assigned",
        requested_questions=1,
        include_ai_generated=False,
        question_count=1,
        total_marks=10,
        shortfall=0,
        notes_json=[],
        rationale_json={"summary": "gap"},
        reviewed_by=created_by,
        items=items,
    )
    return HomeworkAssignmentRecord(
        id=uid("usp-asg"),
        draft=draft,
        student_id=student.id,
        school_id=student.school_id,
        subject_id=subject_id,
        assigned_by=created_by,
        assigned_at=NOW - timedelta(days=5),
        due_at=NOW + timedelta(days=2),
        status="assigned",
    )


def make_submission(assignment: HomeworkAssignmentRecord) -> HomeworkSubmissionRecord:
    return HomeworkSubmissionRecord(
        id=uid("usp-sub"),
        assignment_id=assignment.id,
        student_id=assignment.student_id,
        school_id=assignment.school_id,
        status="submitted",
        is_late=False,
        started_at=NOW - timedelta(days=2),
        updated_at=NOW - timedelta(days=1),
        submitted_at=NOW - timedelta(days=1),
        version=1,
    )


def make_evaluation(
    assignment: HomeworkAssignmentRecord,
    submission: HomeworkSubmissionRecord,
    status: str,
    awarded: int,
    teacher_id: str,
) -> HomeworkEvaluationRecord:
    finalized = status in {"marked", "released"}
    released = status == "released"
    evaluation = HomeworkEvaluationRecord(
        id=uid("usp-eval"),
        submission_id=submission.id,
        assignment_id=assignment.id,
        student_id=assignment.student_id,
        school_id=assignment.school_id,
        status=status,
        total_max=10,
        total_awarded=awarded if finalized else None,
        created_by=teacher_id,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(hours=12),
        finalized_by=teacher_id if finalized else None,
        finalized_at=(NOW - timedelta(hours=12)) if finalized else None,
        released_by=teacher_id if released else None,
        released_at=(NOW - timedelta(hours=6)) if released else None,
        version=1,
        items=[
            HomeworkEvaluationItemRecord(
                position=1,
                draft_item_id=assignment.draft.items[0].id,
                max_marks=10,
                awarded_marks=awarded if finalized else None,
                feedback=None,
                marked_by=teacher_id if finalized else None,
                marked_at=(NOW - timedelta(hours=12)) if finalized else None,
            )
        ],
    )
    return evaluation


@pytest_asyncio.fixture
async def world(db_session):
    """Alice has mixed verified sources; Bob is empty; Cara is other-school."""
    math = Subject(id=uid("usp-math"), name="USP Maths", code=uid("USPM"), grade=8)
    science = Subject(id=uid("usp-sci"), name="USP Science", code=uid("USPS"), grade=8)
    cls1 = ClassSection(
        id=uid("usp-c1"),
        school_id="school-1",
        grade=8,
        section="P",
        name="USP 8-P",
        subject_ids_json=[math.id, science.id],
    )
    cls3 = ClassSection(
        id=uid("usp-c3"),
        school_id="school-3",
        grade=8,
        section="Q",
        name="USP 8-Q",
        subject_ids_json=[math.id],
    )
    alice = make_student(cls1, "school-1", "Alice Progress")
    bob = make_student(cls1, "school-1", "Bob Empty", lu_score=70, cu_score=70, au_score=70, ct_score=70, overall_score=70)
    cara = make_student(cls3, "school-3", "Cara Other")

    teacher = make_user("teacher", "school-1")
    other_teacher = make_user("teacher", "school-3")
    u_alice = make_user("student", "school-1")
    u_bob = make_user("student", "school-1")
    u_parent = make_user("parent", "school-1")
    u_stranger_parent = make_user("parent", "school-1")

    # Homework: released (alice), marked-only (alice), pending (alice — excluded)
    asg_released = make_assignment(alice, math.id, teacher.id)
    asg_marked = make_assignment(alice, science.id, teacher.id)
    asg_pending = make_assignment(alice, math.id, teacher.id)
    # Flush drafts/items so evaluation item FKs resolve.
    db_session.add_all([math, science, cls1, cls3, alice, bob, cara, teacher, other_teacher,
                        u_alice, u_bob, u_parent, u_stranger_parent,
                        asg_released, asg_marked, asg_pending])
    await db_session.flush()

    sub_released = make_submission(asg_released)
    sub_marked = make_submission(asg_marked)
    sub_pending = make_submission(asg_pending)
    db_session.add_all([sub_released, sub_marked, sub_pending])
    await db_session.flush()

    eval_released = make_evaluation(asg_released, sub_released, "released", 8, teacher.id)
    eval_released.items[0].feedback = "Released feedback: show your working next time."
    eval_marked = make_evaluation(asg_marked, sub_marked, "marked", 4, teacher.id)
    eval_marked.items[0].feedback = "Marked-only note: students must not see this yet."
    eval_pending = make_evaluation(asg_pending, sub_pending, "pending", 0, teacher.id)
    # AI suggestion on pending — must never appear in progress payloads.
    suggestion = HomeworkEvaluationSuggestionRecord(
        evaluation_id=eval_pending.id,
        draft_item_id=asg_pending.draft.items[0].id,
        position=1,
        max_marks=10,
        suggested_marks=9,
        correctness="correct",
        confidence="high",
        source="gemini",
        explanation="AI-only — must not count",
        feedback="AI-only feedback",
        needs_teacher_attention=False,
        created_by=teacher.id,
        created_at=NOW,
        updated_at=NOW,
    )
    # Attach suggestion after evaluation has id; SQLAlchemy relationship may need evaluation first.
    eval_pending.ai_suggestions.append(suggestion)

    # Assessment Studio (not scanned) + OCR-scanned submission
    asm_studio = Assessment(
        id=uid("usp-asm-s"),
        school_id="school-1",
        class_id=cls1.id,
        subject_id=math.id,
        title="Studio Quiz",
        cycle_number=1,
        date="2026-11-01",
        duration_minutes=40,
        total_marks=20,
        status="graded",
        competency_focus_json=["LU"],
        questions_json=[],
    )
    asm_ocr = Assessment(
        id=uid("usp-asm-o"),
        school_id="school-1",
        class_id=cls1.id,
        subject_id=science.id,
        title="OCR Worksheet",
        cycle_number=2,
        date="2026-11-05",
        duration_minutes=40,
        total_marks=14,
        status="graded",
        competency_focus_json=["CU"],
        questions_json=[],
    )
    asm_missing = Assessment(
        id=uid("usp-asm-m"),
        school_id="school-1",
        class_id=cls1.id,
        subject_id=math.id,
        title="Missing Paper",
        cycle_number=2,
        date="2026-11-10",
        duration_minutes=40,
        total_marks=25,
        status="scheduled",
        competency_focus_json=[],
        questions_json=[],
    )
    sub_studio = AssessmentSubmission(
        id=uid("usp-asub-s"),
        assessment_id=asm_studio.id,
        student_id=alice.id,
        student_name=alice.name,
        marks_obtained=16,
        total_marks=20,
        percentage=80,
        lu_score=50,
        cu_score=70,
        au_score=60,
        ct_score=55,
        overall_score=59,
        feedback="studio",
        submission_date="2026-11-01",
        is_scanned=False,
    )
    sub_ocr = AssessmentSubmission(
        id=uid("usp-asub-o"),
        assessment_id=asm_ocr.id,
        student_id=alice.id,
        student_name=alice.name,
        marks_obtained=10,
        total_marks=14,
        percentage=71,
        lu_score=48,
        cu_score=75,
        au_score=62,
        ct_score=58,
        overall_score=61,
        feedback="ocr approved",
        submission_date="2026-11-05",
        is_scanned=True,
    )
    # Matching HumanReview for OCR assessment — must NOT double-count.
    review_dup = HumanReview(
        id=uid("usp-hr-dup"),
        ocr_run_id="ocr-1",
        reviewer_id=teacher.id,
        student_id=alice.id,
        assessment_id=asm_ocr.id,
        verified_marks=10,
        total_marks=14,
        verified_data_json=[],
        teacher_notes="duplicate path",
        status="approved",
        reviewed_at=NOW - timedelta(days=3),
    )
    # Orphan HumanReview (no AssessmentSubmission) — should appear once.
    asm_orphan = Assessment(
        id=uid("usp-asm-or"),
        school_id="school-1",
        class_id=cls1.id,
        subject_id=math.id,
        title="Orphan OCR Review",
        cycle_number=2,
        date="2026-11-08",
        duration_minutes=30,
        total_marks=10,
        status="graded",
        competency_focus_json=[],
        questions_json=[],
    )
    review_orphan = HumanReview(
        id=uid("usp-hr-or"),
        ocr_run_id="ocr-2",
        reviewer_id=teacher.id,
        student_id=alice.id,
        assessment_id=asm_orphan.id,
        verified_marks=7,
        total_marks=10,
        verified_data_json=[],
        teacher_notes="INTERNAL OCR NOTE — educator only",
        status="approved",
        reviewed_at=NOW - timedelta(days=2),
    )
    snapshot = StudentCompetencySnapshot(
        id=uid("usp-snap"),
        student_id=alice.id,
        cycle_number=1,
        recorded_at=NOW - timedelta(days=10),
        lu_score=38,
        cu_score=70,
        au_score=60,
        ct_score=50,
        overall_score=54,
        notes="cycle 1",
    )

    db_session.add_all([
        eval_released, eval_marked, eval_pending,
        asm_studio, asm_ocr, asm_missing, asm_orphan,
        sub_studio, sub_ocr, review_dup, review_orphan, snapshot,
        StudentAccountLink(user_id=u_alice.id, student_id=alice.id, created_by=teacher.id),
        StudentAccountLink(user_id=u_bob.id, student_id=bob.id, created_by=teacher.id),
        ParentStudentLink(id=uid("usp-plink"), parent_user_id=u_parent.id, student_id=alice.id),
    ])
    await db_session.commit()

    ids = {
        "alice": alice.id,
        "bob": bob.id,
        "cara": cara.id,
        "math": math.id,
        "science": science.id,
        "teacher": teacher.id,
        "other_teacher": other_teacher.id,
        "u_alice": u_alice.id,
        "u_bob": u_bob.id,
        "u_parent": u_parent.id,
        "u_stranger_parent": u_stranger_parent.id,
        "eval_released": eval_released.id,
        "eval_marked": eval_marked.id,
        "eval_pending": eval_pending.id,
        "sub_studio": sub_studio.id,
        "sub_ocr": sub_ocr.id,
        "review_dup": review_dup.id,
        "review_orphan": review_orphan.id,
        "asm_studio": asm_studio.id,
        "asm_ocr": asm_ocr.id,
        "asm_missing": asm_missing.id,
        "asm_orphan": asm_orphan.id,
        "cls1": cls1.id,
        "cls3": cls3.id,
        "suggestion": suggestion.id if getattr(suggestion, "id", None) else None,
    }
    yield ids

    await db_session.rollback()
    for student_id in (ids["alice"], ids["bob"], ids["cara"]):
        p = {"s": student_id}
        for sql in (
            "DELETE FROM homework_evaluation_ai_suggestions WHERE evaluation_id IN "
            "(SELECT id FROM homework_evaluations WHERE student_id = :s)",
            "DELETE FROM homework_evaluation_items WHERE evaluation_id IN "
            "(SELECT id FROM homework_evaluations WHERE student_id = :s)",
            "DELETE FROM homework_evaluations WHERE student_id = :s",
            "DELETE FROM homework_submission_answers WHERE submission_id IN "
            "(SELECT id FROM homework_submissions WHERE student_id = :s)",
            "DELETE FROM homework_submissions WHERE student_id = :s",
            "DELETE FROM homework_assignments WHERE student_id = :s",
            "DELETE FROM homework_draft_items WHERE draft_id IN "
            "(SELECT id FROM homework_drafts WHERE student_id = :s)",
            "DELETE FROM homework_drafts WHERE student_id = :s",
            "DELETE FROM assessment_submissions WHERE student_id = :s",
            "DELETE FROM human_reviews WHERE student_id = :s",
            "DELETE FROM student_competency_snapshots WHERE student_id = :s",
            "DELETE FROM student_account_links WHERE student_id = :s",
            "DELETE FROM parent_student_links WHERE student_id = :s",
            "DELETE FROM students WHERE id = :s",
        ):
            await db_session.execute(text(sql), p)
    for key in ("teacher", "other_teacher", "u_alice", "u_bob", "u_parent", "u_stranger_parent"):
        await db_session.execute(text("DELETE FROM users WHERE id = :u"), {"u": ids[key]})
    for assessment_id in (ids["asm_studio"], ids["asm_ocr"], ids["asm_missing"], ids["asm_orphan"]):
        await db_session.execute(text("DELETE FROM assessments WHERE id = :a"), {"a": assessment_id})
    for class_id in (ids["cls1"], ids["cls3"]):
        await db_session.execute(text("DELETE FROM classes WHERE id = :c"), {"c": class_id})
    for subject_id in (ids["math"], ids["science"]):
        await db_session.execute(text("DELETE FROM subjects WHERE id = :s"), {"s": subject_id})
    await db_session.commit()


def test_percentage_unavailable_not_zero():
    assert _percentage(None, 10) is None
    assert _percentage(5, None) is None
    assert _percentage(5, 0) is None
    assert _percentage(5, 10) == 50.0


def test_subject_performance_skips_null_percentages():
    events = [
        ProgressEventOut(
            id="a", source_type="assessment_studio", source_id="1", subject_id="math",
            awarded_marks=None, max_marks=10, percentage=None, occurred_at="2026-01-01",
        ),
        ProgressEventOut(
            id="b", source_type="assessment_studio", source_id="2", subject_id="math",
            awarded_marks=8, max_marks=10, percentage=80.0, occurred_at="2026-01-02",
        ),
    ]
    subjects = build_subject_performance(events)
    assert len(subjects) == 1
    assert subjects[0].event_count == 2
    assert subjects[0].comparable_event_count == 1
    assert subjects[0].average_percentage == 80.0


def test_weak_subject_requires_comparable_percentages_not_raw_event_count():
    """One comparable % plus one missing-max row must not trigger weak_subject."""
    student = Student(
        id="s", school_id="school-1", class_id="c", class_name="C", name="X", roll_no=1,
        lu_score=80, cu_score=80, au_score=80, ct_score=80, overall_score=80,
    )
    subjects = [
        SubjectPerformanceOut(
            subject_id="math", subject_name="Maths", event_count=2, comparable_event_count=1,
            average_percentage=40.0, latest_percentage=40.0, latest_occurred_at="2026-01-02",
        )
    ]
    recs = build_recommendations(student, [], subjects, [])
    assert "weak_subject" not in {r.kind for r in recs}


def test_recommendations_weak_subject_and_low_competency():
    student = Student(
        id="s", school_id="school-1", class_id="c", class_name="C", name="X", roll_no=1,
        lu_score=40, cu_score=80, au_score=80, ct_score=80, overall_score=70,
    )
    subjects = [
        SubjectPerformanceOut(
            subject_id="math", subject_name="Maths", event_count=2, comparable_event_count=2,
            average_percentage=40.0, latest_percentage=35.0, latest_occurred_at="2026-01-02",
        )
    ]
    events = [
        ProgressEventOut(
            id="1", source_type="assessment_studio", source_id="1", subject_id="math",
            percentage=45.0, occurred_at="2026-01-01",
        ),
        ProgressEventOut(
            id="2", source_type="assessment_studio", source_id="2", subject_id="math",
            percentage=35.0, occurred_at="2026-01-02",
        ),
    ]
    recs = build_recommendations(student, events, subjects, [])
    kinds = {r.kind for r in recs}
    assert "weak_subject" in kinds
    assert "low_competency" in kinds


@pytest.mark.asyncio
async def test_educator_overview_filters_and_dedupes(client, world):
    res = await client.get(
        f"{API}/students/{world['alice']}/progress",
        headers=bearer(world["teacher"], "teacher"),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["student"]["id"] == world["alice"]
    assert body["audience"] == "educator"

    source_ids = {e["source_id"] for e in body["recent_activity"]}
    # Released + marked homework included for educators.
    assert world["eval_released"] in source_ids
    assert world["eval_marked"] in source_ids
    assert world["eval_pending"] not in source_ids
    # Studio + OCR submission included.
    assert world["sub_studio"] in source_ids
    assert world["sub_ocr"] in source_ids
    # Matching HumanReview excluded; orphan included.
    assert world["review_dup"] not in source_ids
    assert world["review_orphan"] in source_ids

    blob = res.text
    assert "AI-only" not in blob
    assert "gemini" not in blob.lower() or "suggested_marks" not in blob

    # Competencies present as live scores; history separate (snapshots not in recent_activity).
    assert body["competencies"]["current"]["LU"] == 40
    assert body["competencies"]["source"] == "students.live_scores"
    assert any(h["source_type"] == "competency_snapshot" for h in body["competencies"]["history"])

    # Missing marks never forced to zero on empty averages for subjects with only nulls — N/A path.
    assert body["overall"]["verified_event_count"] >= 4
    assert body["overall"]["average_percentage"] is not None

    kinds = {r["kind"] for r in body["recommendations"]}
    assert "missing_assessment" in kinds
    assert "low_competency" in kinds


@pytest.mark.asyncio
async def test_student_sees_only_released_homework(client, world):
    res = await client.get(
        f"{API}/students/me/progress",
        headers=bearer(world["u_alice"], "student"),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["audience"] == "student_or_parent"
    source_ids = {e["source_id"] for e in body["recent_activity"]}
    assert world["eval_released"] in source_ids
    assert world["eval_marked"] not in source_ids
    assert world["eval_pending"] not in source_ids
    blob = res.text
    assert "Released feedback: show your working next time." in blob
    assert "Marked-only note" not in blob
    assert "INTERNAL OCR NOTE" not in blob
    assert "AI-only" not in blob
    assert "suggested_marks" not in blob
    assert "correct_answer" not in blob
    assert "marking_rubric" not in blob


@pytest.mark.asyncio
async def test_parent_linked_child_progress(client, world):
    ok = await client.get(
        f"{API}/parents/me/students/{world['alice']}/progress",
        headers=bearer(world["u_parent"], "parent"),
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["audience"] == "student_or_parent"
    source_ids = {e["source_id"] for e in body["recent_activity"]}
    assert world["eval_marked"] not in source_ids
    assert "Released feedback: show your working next time." in ok.text
    assert "INTERNAL OCR NOTE" not in ok.text
    assert "AI-only" not in ok.text

    denied = await client.get(
        f"{API}/parents/me/students/{world['alice']}/progress",
        headers=bearer(world["u_stranger_parent"], "parent"),
    )
    assert denied.status_code == 404

    # Parent history / competencies for linked child.
    hist = await client.get(
        f"{API}/parents/me/students/{world['alice']}/progress/history",
        headers=bearer(world["u_parent"], "parent"),
    )
    assert hist.status_code == 200
    assert all(e["source_id"] != world["eval_marked"] for e in hist.json()["events"])

    comps = await client.get(
        f"{API}/parents/me/students/{world['alice']}/progress/competencies",
        headers=bearer(world["u_parent"], "parent"),
    )
    assert comps.status_code == 200
    assert comps.json()["current"]["LU"] == 40


@pytest.mark.asyncio
async def test_learner_privacy_and_isolation(client, world):
    """Students/parents cannot reach each other's records or educator-only payloads."""
    # Student cannot use the parent route.
    as_student = await client.get(
        f"{API}/parents/me/students/{world['alice']}/progress",
        headers=bearer(world["u_alice"], "student"),
    )
    assert as_student.status_code == 403

    # Student me/progress cannot be used by a parent.
    as_parent = await client.get(
        f"{API}/students/me/progress",
        headers=bearer(world["u_parent"], "parent"),
    )
    assert as_parent.status_code == 403

    # Parent cannot open another school's / unlinked student.
    other = await client.get(
        f"{API}/parents/me/students/{world['cara']}/progress",
        headers=bearer(world["u_parent"], "parent"),
    )
    assert other.status_code == 404

    # Educator still sees internal OCR notes; learner views do not.
    teacher = await client.get(
        f"{API}/students/{world['alice']}/progress",
        headers=bearer(world["teacher"], "teacher"),
    )
    assert teacher.status_code == 200
    assert "INTERNAL OCR NOTE" in teacher.text
    assert "Marked-only note" in teacher.text


@pytest.mark.asyncio
async def test_authorization_boundaries(client, world):
    # Other-school teacher cannot see Alice.
    other = await client.get(
        f"{API}/students/{world['alice']}/progress",
        headers=bearer(world["other_teacher"], "teacher", "school-3"),
    )
    assert other.status_code == 404

    # Student cannot use educator endpoint for another student.
    steal = await client.get(
        f"{API}/students/{world['bob']}/progress",
        headers=bearer(world["u_alice"], "student"),
    )
    assert steal.status_code == 403

    # Empty student still returns structure with unavailable averages.
    empty = await client.get(
        f"{API}/students/{world['bob']}/progress",
        headers=bearer(world["teacher"], "teacher"),
    )
    assert empty.status_code == 200, empty.text
    body = empty.json()
    assert body["overall"]["verified_event_count"] == 0
    assert body["overall"]["average_percentage"] is None
    assert body["recent_activity"] == []
    assert body["subjects"] == []


@pytest.mark.asyncio
async def test_history_and_subject_and_competency_endpoints(client, world):
    headers = bearer(world["teacher"], "teacher")
    history = await client.get(
        f"{API}/students/{world['alice']}/progress/history",
        headers=headers,
    )
    assert history.status_code == 200
    events = history.json()["events"]
    assert all(e["source_type"] != "competency_snapshot" for e in events)

    math_only = await client.get(
        f"{API}/students/{world['alice']}/progress/history",
        headers=headers,
        params={"subject_id": world["math"]},
    )
    assert math_only.status_code == 200
    assert all(e["subject_id"] == world["math"] for e in math_only.json()["events"])

    subject = await client.get(
        f"{API}/students/{world['alice']}/progress/subjects/{world['science']}",
        headers=headers,
    )
    assert subject.status_code == 200
    assert subject.json()["subject_id"] == world["science"]

    comps = await client.get(
        f"{API}/students/{world['alice']}/progress/competencies",
        headers=headers,
    )
    assert comps.status_code == 200
    assert comps.json()["current"]["LU"] == 40
    assert comps.json()["history"]
    # Must not invent / rewrite — live scores unchanged from fixture.
    assert comps.json()["baseline"]["LU"] == 30


@pytest.mark.asyncio
async def test_requires_bearer(client, world):
    res = await client.get(f"{API}/students/{world['alice']}/progress")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_empty_history_is_null_not_zero(client, world):
    body = (
        await client.get(
            f"{API}/students/{world['bob']}/progress",
            headers=bearer(world["teacher"], "teacher"),
        )
    ).json()
    assert body["overall"]["verified_event_count"] == 0
    assert body["overall"]["average_percentage"] is None
    assert body["overall"]["latest_activity_at"] is None
    assert body["trends"] == []
    assert body["subject_trends"] == []
    assert "0%" not in str(body["overall"])


@pytest.mark.asyncio
async def test_aggregation_is_read_only(client, world, db_session):
    from sqlalchemy import func, select
    from backend.app.models.entities import AssessmentSubmission, StudentCompetencySnapshot
    from backend.app.modules.differentiated_homework.models import HomeworkEvaluationRecord

    alice = await db_session.get(Student, world["alice"])
    before = {
        "subs": await db_session.scalar(select(func.count()).select_from(AssessmentSubmission)),
        "evals": await db_session.scalar(select(func.count()).select_from(HomeworkEvaluationRecord)),
        "snaps": await db_session.scalar(select(func.count()).select_from(StudentCompetencySnapshot)),
        "lu": alice.lu_score,
        "cu": alice.cu_score,
        "overall": alice.overall_score,
    }
    res = await client.get(
        f"{API}/students/{world['alice']}/progress",
        headers=bearer(world["teacher"], "teacher"),
    )
    assert res.status_code == 200
    await db_session.refresh(alice)
    assert alice.lu_score == before["lu"]
    assert alice.cu_score == before["cu"]
    assert alice.overall_score == before["overall"]
    assert before["subs"] == await db_session.scalar(select(func.count()).select_from(AssessmentSubmission))
    assert before["evals"] == await db_session.scalar(select(func.count()).select_from(HomeworkEvaluationRecord))
    assert before["snaps"] == await db_session.scalar(select(func.count()).select_from(StudentCompetencySnapshot))


@pytest.mark.asyncio
async def test_duplicate_assessment_and_ocr_deduped(client, world, db_session):
    """Latest AssessmentSubmission wins; matching HumanReview is omitted."""
    asm = Assessment(
        id=uid("usp-dup-asm"),
        school_id="school-1",
        class_id=(await db_session.get(Student, world["alice"])).class_id,
        subject_id=world["math"],
        title="Duplicate Grade Paper",
        cycle_number=3,
        date="2026-11-12",
        total_marks=10,
        status="graded",
        competency_focus_json=[],
        questions_json=[],
    )
    older = AssessmentSubmission(
        id=uid("usp-dup-old"),
        assessment_id=asm.id,
        student_id=world["alice"],
        student_name="Alice",
        marks_obtained=3,
        total_marks=10,
        percentage=30,
        lu_score=40, cu_score=40, au_score=40, ct_score=40, overall_score=40,
        feedback="older",
        submission_date="2026-11-11",
        is_scanned=True,
        created_at=NOW - timedelta(days=2),
    )
    newer = AssessmentSubmission(
        id=uid("usp-dup-new"),
        assessment_id=asm.id,
        student_id=world["alice"],
        student_name="Alice",
        marks_obtained=9,
        total_marks=10,
        percentage=90,
        lu_score=50, cu_score=50, au_score=50, ct_score=50, overall_score=50,
        feedback="newer",
        submission_date="2026-11-12",
        is_scanned=True,
        created_at=NOW - timedelta(hours=1),
    )
    review = HumanReview(
        id=uid("usp-dup-hr"),
        ocr_run_id="ocr-dup",
        reviewer_id=world["teacher"],
        student_id=world["alice"],
        assessment_id=asm.id,
        verified_marks=9,
        total_marks=10,
        verified_data_json=[],
        teacher_notes="should not double-count",
        status="approved",
        reviewed_at=NOW,
    )
    db_session.add_all([asm, older, newer, review])
    await db_session.commit()

    history = await client.get(
        f"{API}/students/{world['alice']}/progress/history",
        headers=bearer(world["teacher"], "teacher"),
    )
    assert history.status_code == 200
    events = history.json()["events"]
    for this_asm in [e for e in events if e.get("assessment_id") == asm.id]:
        assert this_asm["source_id"] == newer.id
        assert this_asm["awarded_marks"] == 9
    assert sum(1 for e in events if e.get("assessment_id") == asm.id) == 1
    assert review.id not in {e["source_id"] for e in events}

    await db_session.execute(text("DELETE FROM human_reviews WHERE id = :i"), {"i": review.id})
    await db_session.execute(text("DELETE FROM assessment_submissions WHERE assessment_id = :a"), {"a": asm.id})
    await db_session.execute(text("DELETE FROM assessments WHERE id = :a"), {"a": asm.id})
    await db_session.commit()


@pytest.mark.asyncio
async def test_date_normalization_orders_chronologically(client, world, db_session):
    from backend.app.modules.student_progress.service import _iso, build_trends
    from backend.app.modules.student_progress.schemas import ProgressEventOut

    assert _iso("2026-11-05").startswith("2026-11-05T00:00:00")
    events = [
        ProgressEventOut(
            id="later", source_type="assessment_studio", source_id="2",
            awarded_marks=8, max_marks=10, percentage=80.0,
            occurred_at=_iso("2026-11-05T15:00:00+00:00"),
        ),
        ProgressEventOut(
            id="earlier", source_type="assessment_studio", source_id="1",
            awarded_marks=5, max_marks=10, percentage=50.0,
            occurred_at=_iso("2026-11-05"),
        ),
    ]
    trends, _ = build_trends(events)
    assert [p.source_id for p in trends] == ["1", "2"]


def test_insufficient_trend_points_skip_trend_recommendations():
    from backend.app.modules.student_progress.schemas import TrendPointOut

    student = Student(
        id="s", school_id="school-1", class_id="c", class_name="C", name="X", roll_no=1,
        lu_score=80, cu_score=80, au_score=80, ct_score=80, overall_score=80,
    )
    trends = [
        TrendPointOut(
            occurred_at="2026-01-01T00:00:00+00:00", percentage=40.0,
            source_type="assessment_studio", source_id="a",
        ),
        TrendPointOut(
            occurred_at="2026-02-01T00:00:00+00:00", percentage=90.0,
            source_type="assessment_studio", source_id="b",
        ),
    ]
    recs = build_recommendations(student, [], [], trends)
    assert "improving_trend" not in {r.kind for r in recs}
    assert "declining_trend" not in {r.kind for r in recs}


def test_zero_max_marks_not_comparable():
    from backend.app.modules.student_progress.service import build_trends

    assert _percentage(0, 0) is None
    assert _percentage(5, 0) is None
    events = [
        ProgressEventOut(
            id="z", source_type="assessment_studio", source_id="z",
            awarded_marks=0, max_marks=0, percentage=None,
            occurred_at="2026-01-01T00:00:00+00:00",
        ),
        ProgressEventOut(
            id="ok", source_type="assessment_studio", source_id="ok",
            awarded_marks=5, max_marks=10, percentage=50.0,
            occurred_at="2026-01-02T00:00:00+00:00",
        ),
    ]
    trends, _ = build_trends(events)
    assert [p.source_id for p in trends] == ["ok"]


@pytest.mark.asyncio
async def test_parent_multiple_linked_children(client, world, db_session):
    # Link Bob to the same parent as Alice.
    db_session.add(
        ParentStudentLink(
            id=uid("usp-plink2"),
            parent_user_id=world["u_parent"],
            student_id=world["bob"],
        )
    )
    await db_session.commit()

    headers = bearer(world["u_parent"], "parent")
    alice = await client.get(f"{API}/parents/me/students/{world['alice']}/progress", headers=headers)
    bob = await client.get(f"{API}/parents/me/students/{world['bob']}/progress", headers=headers)
    cara = await client.get(f"{API}/parents/me/students/{world['cara']}/progress", headers=headers)
    assert alice.status_code == 200
    assert bob.status_code == 200
    assert alice.json()["student"]["id"] == world["alice"]
    assert bob.json()["student"]["id"] == world["bob"]
    assert cara.status_code == 404

    await db_session.execute(
        text("DELETE FROM parent_student_links WHERE student_id = :s AND parent_user_id = :p"),
        {"s": world["bob"], "p": world["u_parent"]},
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_cross_school_assessment_excluded(client, world, db_session):
    asm = Assessment(
        id=uid("usp-xschool"),
        school_id="school-3",
        class_id=uid("foreign-class"),
        subject_id=world["math"],
        title="Other school paper",
        cycle_number=1,
        date="2026-11-01",
        total_marks=10,
        status="graded",
        competency_focus_json=[],
        questions_json=[],
    )
    sub = AssessmentSubmission(
        id=uid("usp-xschool-sub"),
        assessment_id=asm.id,
        student_id=world["alice"],
        student_name="Alice",
        marks_obtained=10,
        total_marks=10,
        percentage=100,
        lu_score=90, cu_score=90, au_score=90, ct_score=90, overall_score=90,
        feedback="should be filtered by school",
        submission_date="2026-11-01",
        is_scanned=False,
    )
    db_session.add_all([asm, sub])
    await db_session.commit()

    history = await client.get(
        f"{API}/students/{world['alice']}/progress/history",
        headers=bearer(world["teacher"], "teacher"),
    )
    assert history.status_code == 200
    assert sub.id not in {e["source_id"] for e in history.json()["events"]}

    await db_session.execute(text("DELETE FROM assessment_submissions WHERE id = :i"), {"i": sub.id})
    await db_session.execute(text("DELETE FROM assessments WHERE id = :i"), {"i": asm.id})
    await db_session.commit()
