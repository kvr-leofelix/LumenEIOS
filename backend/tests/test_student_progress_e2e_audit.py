"""Final Unified Student Progress E2E + security audit on synthetic isolated data.

Covers teacher / student / parent flows, data correctness, and isolation.
Does not mutate production databases; uses the pytest temp SQLite from conftest.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

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

API = "/api/v1"
NOW = datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc)


def uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def bearer(user_id: str, role: str, school_id: str = "school-1") -> dict:
    return {"Authorization": f"Bearer {create_access_token(user_id, school_id=school_id, role=role)}"}


@pytest_asyncio.fixture
async def audit_world(db_session):
    math = Subject(id=uid("aud-math"), name="Audit Maths", code=uid("AUDM"), grade=8)
    sci = Subject(id=uid("aud-sci"), name="Audit Science", code=uid("AUDS"), grade=8)
    cls1 = ClassSection(
        id=uid("aud-c1"), school_id="school-1", grade=8, section="A", name="Audit 8-A",
        subject_ids_json=[math.id, sci.id],
    )
    cls3 = ClassSection(
        id=uid("aud-c3"), school_id="school-3", grade=8, section="B", name="Audit 8-B",
        subject_ids_json=[math.id],
    )
    alice = Student(
        id=uid("aud-alice"), school_id="school-1", class_id=cls1.id, class_name=cls1.name,
        name="Audit Alice", roll_no=1, lu_score=42, cu_score=71, au_score=60, ct_score=55, overall_score=57,
        baseline_lu=30, baseline_cu=50, baseline_au=40, baseline_ct=35, baseline_overall=39,
    )
    bob = Student(
        id=uid("aud-bob"), school_id="school-1", class_id=cls1.id, class_name=cls1.name,
        name="Audit Bob", roll_no=2, lu_score=70, cu_score=70, au_score=70, ct_score=70, overall_score=70,
        baseline_lu=60, baseline_cu=60, baseline_au=60, baseline_ct=60, baseline_overall=60,
    )
    cara = Student(
        id=uid("aud-cara"), school_id="school-3", class_id=cls3.id, class_name=cls3.name,
        name="Audit Cara", roll_no=1, lu_score=50, cu_score=50, au_score=50, ct_score=50, overall_score=50,
        baseline_lu=40, baseline_cu=40, baseline_au=40, baseline_ct=40, baseline_overall=40,
    )
    teacher = User(id=uid("aud-t"), email=f"{uid('t')}@test.invalid", name="T", hashed_password="x",
                   role="teacher", school_id="school-1")
    other_teacher = User(id=uid("aud-ot"), email=f"{uid('ot')}@test.invalid", name="OT", hashed_password="x",
                         role="teacher", school_id="school-3")
    u_alice = User(id=uid("aud-ua"), email=f"{uid('ua')}@test.invalid", name="UA", hashed_password="x",
                   role="student", school_id="school-1")
    u_bob = User(id=uid("aud-ub"), email=f"{uid('ub')}@test.invalid", name="UB", hashed_password="x",
                 role="student", school_id="school-1")
    u_parent = User(id=uid("aud-p"), email=f"{uid('p')}@test.invalid", name="P", hashed_password="x",
                    role="parent", school_id="school-1")
    u_stranger = User(id=uid("aud-sp"), email=f"{uid('sp')}@test.invalid", name="SP", hashed_password="x",
                      role="parent", school_id="school-1")

    def assignment(student, subject_id, created_by, marks=10):
        item = HomeworkDraftItemRecord(
            position=1, source_question_id=uid("src"), text="Q", type="short", options_json=[],
            marks=marks, competency="LU", competency_rank=1, bloom_level="Apply",
            is_ai_generated=False, correct_answer="KEY-SECRET", marking_rubric="RUBRIC-SECRET",
        )
        draft = HomeworkDraftRecord(
            student_id=student.id, school_id=student.school_id, subject_id=subject_id,
            created_by=created_by, status="assigned", requested_questions=1,
            include_ai_generated=False, question_count=1, total_marks=marks, shortfall=0,
            notes_json=[], rationale_json={}, reviewed_by=created_by, items=[item],
        )
        return HomeworkAssignmentRecord(
            id=uid("aud-asg"), draft=draft, student_id=student.id, school_id=student.school_id,
            subject_id=subject_id, assigned_by=created_by, assigned_at=NOW - timedelta(days=3),
            due_at=NOW + timedelta(days=1), status="assigned",
        )

    asg_released = assignment(alice, math.id, teacher.id)
    asg_marked = assignment(alice, sci.id, teacher.id)
    db_session.add_all([math, sci, cls1, cls3, alice, bob, cara, teacher, other_teacher,
                        u_alice, u_bob, u_parent, u_stranger, asg_released, asg_marked])
    await db_session.flush()

    def submission(asg):
        return HomeworkSubmissionRecord(
            id=uid("aud-sub"), assignment_id=asg.id, student_id=asg.student_id, school_id=asg.school_id,
            status="submitted", is_late=False, started_at=NOW - timedelta(days=2),
            updated_at=NOW - timedelta(days=1), submitted_at=NOW - timedelta(days=1), version=1,
        )

    sub_r, sub_m = submission(asg_released), submission(asg_marked)
    db_session.add_all([sub_r, sub_m])
    await db_session.flush()

    def evaluation(asg, sub, status, awarded, feedback=None):
        finalized = status in {"marked", "released"}
        released = status == "released"
        return HomeworkEvaluationRecord(
            id=uid("aud-ev"), submission_id=sub.id, assignment_id=asg.id, student_id=asg.student_id,
            school_id=asg.school_id, status=status, total_max=10,
            total_awarded=awarded if finalized else None, created_by=teacher.id,
            created_at=NOW - timedelta(days=1), updated_at=NOW - timedelta(hours=6),
            finalized_by=teacher.id if finalized else None,
            finalized_at=(NOW - timedelta(hours=6)) if finalized else None,
            released_by=teacher.id if released else None,
            released_at=(NOW - timedelta(hours=3)) if released else None, version=1,
            items=[HomeworkEvaluationItemRecord(
                position=1, draft_item_id=asg.draft.items[0].id, max_marks=10,
                awarded_marks=awarded if finalized else None, feedback=feedback,
                marked_by=teacher.id if finalized else None,
                marked_at=(NOW - timedelta(hours=6)) if finalized else None,
            )],
        )

    ev_released = evaluation(asg_released, sub_r, "released", 8, "Released coaching note")
    ev_marked = evaluation(asg_marked, sub_m, "marked", 3, "Unreleased teacher note")
    ai = HomeworkEvaluationSuggestionRecord(
        evaluation_id=ev_marked.id, draft_item_id=asg_marked.draft.items[0].id, position=1,
        max_marks=10, suggested_marks=9, correctness="correct", confidence="high", source="gemini",
        explanation="AI-ONLY explanation must never surface", feedback="AI-ONLY feedback",
        needs_teacher_attention=False, created_by=teacher.id, created_at=NOW, updated_at=NOW,
    )
    ev_marked.ai_suggestions.append(ai)

    asm = Assessment(
        id=uid("aud-asm"), school_id="school-1", class_id=cls1.id, subject_id=math.id,
        title="Audit Studio Quiz", cycle_number=1, date="2026-11-10", total_marks=20, status="graded",
        competency_focus_json=["LU"], questions_json=[],
    )
    older = AssessmentSubmission(
        id=uid("aud-old"), assessment_id=asm.id, student_id=alice.id, student_name=alice.name,
        marks_obtained=10, total_marks=20, percentage=50, lu_score=40, cu_score=40, au_score=40,
        ct_score=40, overall_score=40, feedback="older duplicate", submission_date="2026-11-09",
        is_scanned=True, created_at=NOW - timedelta(days=4),
    )
    newer = AssessmentSubmission(
        id=uid("aud-new"), assessment_id=asm.id, student_id=alice.id, student_name=alice.name,
        marks_obtained=16, total_marks=20, percentage=80, lu_score=48, cu_score=70, au_score=62,
        ct_score=55, overall_score=59, feedback="Verified studio feedback", submission_date="2026-11-10",
        is_scanned=False, created_at=NOW - timedelta(days=2),
    )
    review = HumanReview(
        id=uid("aud-hr"), ocr_run_id="ocr", reviewer_id=teacher.id, student_id=alice.id,
        assessment_id=asm.id, verified_marks=16, total_marks=20, verified_data_json=[],
        teacher_notes="INTERNAL OCR NOTE", status="approved", reviewed_at=NOW - timedelta(days=2),
    )
    snap = StudentCompetencySnapshot(
        id=uid("aud-snap"), student_id=alice.id, cycle_number=1, recorded_at=NOW - timedelta(days=8),
        lu_score=38, cu_score=68, au_score=58, ct_score=50, overall_score=53, notes="cycle1",
    )
    db_session.add_all([
        ev_released, ev_marked, asm, older, newer, review, snap,
        StudentAccountLink(user_id=u_alice.id, student_id=alice.id, created_by=teacher.id),
        StudentAccountLink(user_id=u_bob.id, student_id=bob.id, created_by=teacher.id),
        ParentStudentLink(id=uid("aud-pl"), parent_user_id=u_parent.id, student_id=alice.id),
        ParentStudentLink(id=uid("aud-pl2"), parent_user_id=u_parent.id, student_id=bob.id),
    ])
    await db_session.commit()

    ids = {
        "alice": alice.id, "bob": bob.id, "cara": cara.id, "math": math.id, "sci": sci.id,
        "teacher": teacher.id, "other_teacher": other_teacher.id,
        "u_alice": u_alice.id, "u_bob": u_bob.id, "u_parent": u_parent.id, "u_stranger": u_stranger.id,
        "ev_released": ev_released.id, "ev_marked": ev_marked.id, "asg_released": asg_released.id,
        "asm": asm.id, "newer": newer.id, "older": older.id, "review": review.id,
        "cls1": cls1.id, "cls3": cls3.id,
    }
    yield ids

    await db_session.rollback()
    for sid in (ids["alice"], ids["bob"], ids["cara"]):
        p = {"s": sid}
        for sql in (
            "DELETE FROM homework_evaluation_ai_suggestions WHERE evaluation_id IN "
            "(SELECT id FROM homework_evaluations WHERE student_id = :s)",
            "DELETE FROM homework_evaluation_items WHERE evaluation_id IN "
            "(SELECT id FROM homework_evaluations WHERE student_id = :s)",
            "DELETE FROM homework_evaluations WHERE student_id = :s",
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
    for key in ("teacher", "other_teacher", "u_alice", "u_bob", "u_parent", "u_stranger"):
        await db_session.execute(text("DELETE FROM users WHERE id = :u"), {"u": ids[key]})
    await db_session.execute(text("DELETE FROM assessments WHERE id = :a"), {"a": ids["asm"]})
    await db_session.execute(text("DELETE FROM classes WHERE id = :c"), {"c": ids["cls1"]})
    await db_session.execute(text("DELETE FROM classes WHERE id = :c"), {"c": ids["cls3"]})
    await db_session.execute(text("DELETE FROM subjects WHERE id = :s"), {"s": ids["math"]})
    await db_session.execute(text("DELETE FROM subjects WHERE id = :s"), {"s": ids["sci"]})
    await db_session.commit()


@pytest.mark.asyncio
async def test_final_progress_e2e_security_audit(client, audit_world, db_session):
    w = audit_world
    th = bearer(w["teacher"], "teacher")
    st = bearer(w["u_alice"], "student")
    other_st = bearer(w["u_bob"], "student")
    parent = bearer(w["u_parent"], "parent")
    stranger = bearer(w["u_stranger"], "parent")
    other_school = bearer(w["other_teacher"], "teacher", "school-3")

    before_subs = await db_session.scalar(select(func.count()).select_from(AssessmentSubmission))
    before_lu = (await db_session.get(Student, w["alice"])).lu_score

    # --- Teacher 1–7 ---
    t0 = time.perf_counter()
    overview = await client.get(f"{API}/students/{w['alice']}/progress", headers=th)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert body["student"]["id"] == w["alice"]
    assert body["audience"] == "educator"
    assert body["overall"]["verified_event_count"] >= 2
    assert body["overall"]["average_percentage"] is not None
    assert elapsed_ms < 5000, f"overview too slow: {elapsed_ms:.1f}ms"

    subject = await client.get(
        f"{API}/students/{w['alice']}/progress/subjects/{w['math']}", headers=th,
    )
    assert subject.status_code == 200
    assert subject.json()["subject_id"] == w["math"]
    assert subject.json()["events"]

    history = await client.get(f"{API}/students/{w['alice']}/progress/history", headers=th)
    assert history.status_code == 200
    events = history.json()["events"]
    source_ids = {e["source_id"] for e in events}
    assert w["ev_released"] in source_ids
    assert w["ev_marked"] in source_ids  # educator sees marked
    assert w["newer"] in source_ids
    assert w["older"] not in source_ids  # duplicate submission collapsed
    assert w["review"] not in source_ids  # OCR not double-counted
    assert "AI-ONLY" not in history.text
    assert "suggested_marks" not in history.text
    assert "KEY-SECRET" not in history.text
    assert "RUBRIC-SECRET" not in history.text

    # Chronological: occurred_at descending in recent_activity / history
    stamps = [e["occurred_at"] for e in events if e.get("occurred_at")]
    assert stamps == sorted(stamps, reverse=True)

    # Subject grouping
    by_subject = {}
    for e in events:
        if e.get("subject_id"):
            by_subject.setdefault(e["subject_id"], 0)
            by_subject[e["subject_id"]] += 1
    assert w["math"] in by_subject

    comps = await client.get(f"{API}/students/{w['alice']}/progress/competencies", headers=th)
    assert comps.status_code == 200
    assert comps.json()["current"]["LU"] == 42
    assert comps.json()["history"]

    # Navigate to original records: assignment_id / assessment_id present on events
    released_event = next(e for e in events if e["source_id"] == w["ev_released"])
    assert released_event["assignment_id"] == w["asg_released"]
    studio_event = next(e for e in events if e["source_id"] == w["newer"])
    assert studio_event["assessment_id"] == w["asm"]

    # --- Student 8–10 ---
    mine = await client.get(f"{API}/students/me/progress", headers=st)
    assert mine.status_code == 200
    mine_body = mine.json()
    assert mine_body["audience"] == "student_or_parent"
    mine_ids = {e["source_id"] for e in mine_body["recent_activity"]}
    assert w["ev_released"] in mine_ids
    assert w["ev_marked"] not in mine_ids
    assert "Released coaching note" in mine.text
    assert "Unreleased teacher note" not in mine.text
    assert "INTERNAL OCR NOTE" not in mine.text
    assert "AI-ONLY" not in mine.text

    # --- Parent 11–13 (multi-child + privacy) ---
    child_a = await client.get(f"{API}/parents/me/students/{w['alice']}/progress", headers=parent)
    child_b = await client.get(f"{API}/parents/me/students/{w['bob']}/progress", headers=parent)
    assert child_a.status_code == 200
    assert child_b.status_code == 200
    assert child_a.json()["student"]["id"] == w["alice"]
    assert child_b.json()["student"]["id"] == w["bob"]
    assert w["ev_marked"] not in {e["source_id"] for e in child_a.json()["recent_activity"]}
    assert "Unreleased teacher note" not in child_a.text
    assert "INTERNAL OCR NOTE" not in child_a.text
    assert "AI-ONLY" not in child_a.text
    assert "KEY-SECRET" not in child_a.text

    # Empty child history: Bob has no verified events → null average, not zero
    assert child_b.json()["overall"]["verified_event_count"] == 0
    assert child_b.json()["overall"]["average_percentage"] is None

    # --- Security 19–22 ---
    assert (await client.get(f"{API}/students/me/progress", headers=other_st)).status_code == 200
    # Bob's me progress is Bob, not Alice
    assert (await client.get(f"{API}/students/me/progress", headers=other_st)).json()["student"]["id"] == w["bob"]
    assert (await client.get(f"{API}/students/{w['alice']}/progress", headers=other_st)).status_code == 403
    assert (await client.get(f"{API}/parents/me/students/{w['alice']}/progress", headers=stranger)).status_code == 404
    assert (await client.get(f"{API}/students/{w['alice']}/progress", headers=other_school)).status_code == 404
    assert (await client.get(f"{API}/parents/me/students/{w['alice']}/progress", headers=st)).status_code == 403

    # Read-only: source tables unchanged
    await db_session.refresh(await db_session.get(Student, w["alice"]))
    alice = await db_session.get(Student, w["alice"])
    assert alice.lu_score == before_lu
    assert before_subs == await db_session.scalar(select(func.count()).select_from(AssessmentSubmission))
