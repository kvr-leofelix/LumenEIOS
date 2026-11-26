"""End-to-end AI-assisted homework evaluation on synthetic isolated demo data.

Covers teacher create/assign → student submit → AI suggest → edit/reject/accept via
teacher-approved PATCH → finalize/release → student/parent visibility → security.

By default uses FakeProvider so CI/audit runs are deterministic. Set AI_EVAL_E2E_LIVE=1 to
exercise the real Gemini provider when GEMINI_API_KEY is configured. Live server verification
is also covered by backend/scripts/live_ai_eval_e2e_probe.py.
"""
from __future__ import annotations

import json
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text

from backend.app.core.config import settings
from backend.app.core.security import create_access_token
from backend.app.models.entities import (
    ClassSection, ParentStudentLink, QuestionBankItem, Student, Subject, User,
)
from backend.app.modules.differentiated_homework.models import (
    HomeworkAssignmentRecord,
    HomeworkDraftItemRecord,
    HomeworkDraftRecord,
    HomeworkEvaluationItemRecord,
    HomeworkEvaluationRecord,
    HomeworkEvaluationSuggestionRecord,
    HomeworkSubmissionAnswerRecord,
    HomeworkSubmissionRecord,
    StudentAccountLink,
)
from backend.app.services import ai_gateway


API = "/api/v1"
GEMINI_CONFIGURED = bool(settings.GEMINI_API_KEY.get_secret_value().strip())
GEMINI_LIVE = os.environ.get("AI_EVAL_E2E_LIVE", "").strip() in {"1", "true", "yes"} and GEMINI_CONFIGURED
VERIFICATION_MODE = "live_gemini" if GEMINI_LIVE else "mocked_gemini"


def uid(prefix="aie2e"):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def auth(user, school=None):
    headers = {
        "Authorization": "Bearer " + create_access_token(user.id, role=user.role, school_id=user.school_id),
    }
    if school:
        headers["X-School-Id"] = school
    return headers


class FakeProvider:
    name, model = "gemini", "fake-e2e-model"

    def __init__(self):
        self.calls = []

    async def generate_json(self, *, system, prompt, schema):
        self.calls.append({"system": system, "prompt": prompt})
        # Rubric-aligned partial credit for open-ended items.
        payload = {
            "suggested_marks": 2,
            "correctness": "partially_correct",
            "explanation": "Method is sound; final justification incomplete (teacher review of alternatives OK).",
            "feedback": "Good approach — add one more justifying sentence.",
            "rubric_criteria": [
                {"criterion": "Method", "max_marks": 1, "awarded_marks": 1, "comment": "Clear"},
                {"criterion": "Accuracy", "max_marks": 1, "awarded_marks": 1, "comment": "Mostly"},
                {"criterion": "Justification", "max_marks": 1, "awarded_marks": 0, "comment": "Thin"},
            ],
            "confidence": "medium",
            "needs_teacher_attention": False,
        }
        return json.dumps(payload)


@pytest_asyncio.fixture
async def e2e(db_session, client, monkeypatch):
    """Isolated school-1 teacher/student/parent plus a school-3 teacher and unlinked student."""
    subject = Subject(id=uid("subj"), name="E2E AI Eval Maths", code=uid("E2E"), grade=8)
    cls1 = ClassSection(id=uid("c1"), school_id="school-1", grade=8, section="E", name="E2E-1",
                        subject_ids_json=[subject.id])
    cls3 = ClassSection(id=uid("c3"), school_id="school-3", grade=8, section="F", name="E2E-3",
                        subject_ids_json=[subject.id])
    student = Student(
        id=uid("stu"), school_id="school-1", class_id=cls1.id, class_name=cls1.name, name="E2E Learner",
        roll_no=1, lu_score=35, cu_score=70, au_score=65, ct_score=60, overall_score=55,
        baseline_lu=30, baseline_cu=50, baseline_au=45, baseline_ct=40, baseline_overall=40,
    )
    other_student = Student(
        id=uid("ostu"), school_id="school-1", class_id=cls1.id, class_name=cls1.name, name="Other Learner",
        roll_no=2, lu_score=40, cu_score=70, au_score=60, ct_score=50, overall_score=55,
        baseline_lu=30, baseline_cu=50, baseline_au=40, baseline_ct=35, baseline_overall=39,
    )
    users = {
        "teacher": User(id=uid("teach"), email=uid("t") + "@test.invalid", name="E2E Teacher",
                        hashed_password="x", role="teacher", school_id="school-1"),
        "teacher3": User(id=uid("teach3"), email=uid("t3") + "@test.invalid", name="Other School Teacher",
                         hashed_password="x", role="teacher", school_id="school-3"),
        "student": User(id=uid("ust"), email=uid("s") + "@test.invalid", name="E2E Student User",
                        hashed_password="x", role="student", school_id="school-1"),
        "other_student": User(id=uid("uos"), email=uid("os") + "@test.invalid", name="Other Student User",
                              hashed_password="x", role="student", school_id="school-1"),
        "parent": User(id=uid("upar"), email=uid("p") + "@test.invalid", name="E2E Parent",
                       hashed_password="x", role="parent", school_id="school-1"),
    }
    bank = [
        QuestionBankItem(
            id=uid("q-mcq"), school_id="school-1", subject_id=subject.id,
            text="E2E MCQ: area of a 4m by 3m rectangle?", type="mcq",
            options_json=["7 m²", "12 m²", "14 m²", "24 m²"], correct_answer="12 m²",
            marking_rubric="Full marks for the correct option.", marks=2, competency="LU",
            bloom_level="Apply", is_ai_generated=False,
        ),
        QuestionBankItem(
            id=uid("q-short"), school_id="school-1", subject_id=subject.id,
            text="E2E Short: state the area formula for a rectangle.", type="short",
            options_json=[], correct_answer="A = l × b",
            marking_rubric="Method 1; Accuracy 1; Justification 1", marks=3, competency="LU",
            bloom_level="Understand", is_ai_generated=False,
        ),
        QuestionBankItem(
            id=uid("q-desc"), school_id="school-1", subject_id=subject.id,
            text="E2E Descriptive: explain how you would fence a rectangular garden.", type="descriptive",
            options_json=[], correct_answer="Measure perimeter then buy fencing to match.",
            marking_rubric="Method 1; Accuracy 1; Justification 1", marks=3, competency="LU",
            bloom_level="Evaluate", is_ai_generated=False,
        ),
    ]
    fake = FakeProvider()
    if not GEMINI_LIVE:
        monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: fake)

    db_session.add_all([
        subject, cls1, cls3, student, other_student, *users.values(), *bank,
        StudentAccountLink(user_id=users["student"].id, student_id=student.id, created_by=users["teacher"].id),
        StudentAccountLink(user_id=users["other_student"].id, student_id=other_student.id,
                           created_by=users["teacher"].id),
        ParentStudentLink(id=uid("plink"), parent_user_id=users["parent"].id, student_id=student.id),
    ])
    await db_session.commit()

    ctx = {
        "subject": subject, "student": student, "other_student": other_student, "users": users,
        "bank": bank, "fake": fake, "classes": [cls1, cls3], "mode": VERIFICATION_MODE,
    }
    yield ctx

    await db_session.rollback()
    sid = student.id
    await db_session.execute(text(
        "DELETE FROM homework_evaluation_ai_suggestions WHERE evaluation_id IN "
        "(SELECT id FROM homework_evaluations WHERE student_id = :s)"
    ), {"s": sid})
    for model in (
        HomeworkEvaluationItemRecord, HomeworkEvaluationRecord, HomeworkSubmissionAnswerRecord,
        HomeworkSubmissionRecord, HomeworkAssignmentRecord, HomeworkDraftItemRecord, HomeworkDraftRecord,
    ):
        if model is HomeworkEvaluationItemRecord:
            await db_session.execute(delete(model).where(model.evaluation_id.in_(
                select(HomeworkEvaluationRecord.id).where(HomeworkEvaluationRecord.student_id == sid)
            )))
        elif model is HomeworkSubmissionAnswerRecord:
            await db_session.execute(delete(model).where(model.submission_id.in_(
                select(HomeworkSubmissionRecord.id).where(HomeworkSubmissionRecord.student_id == sid)
            )))
        elif model is HomeworkDraftItemRecord:
            await db_session.execute(delete(model).where(model.draft_id.in_(
                select(HomeworkDraftRecord.id).where(HomeworkDraftRecord.student_id == sid)
            )))
        else:
            await db_session.execute(delete(model).where(getattr(model, "student_id") == sid))
    await db_session.execute(delete(StudentAccountLink).where(StudentAccountLink.student_id.in_([sid, other_student.id])))
    await db_session.execute(delete(ParentStudentLink).where(ParentStudentLink.student_id == sid))
    await db_session.execute(delete(QuestionBankItem).where(QuestionBankItem.subject_id == subject.id))
    await db_session.execute(delete(Student).where(Student.id.in_([sid, other_student.id])))
    for u in users.values():
        await db_session.execute(delete(User).where(User.id == u.id))
    for c in (cls1, cls3):
        await db_session.execute(delete(ClassSection).where(ClassSection.id == c.id))
    await db_session.execute(delete(Subject).where(Subject.id == subject.id))
    await db_session.commit()


@pytest.mark.asyncio
async def test_ai_assisted_evaluation_end_to_end_workflow(client, e2e, db_session):
    """Steps 1–24 of the AI-assisted evaluation verification checklist."""
    teacher = auth(e2e["users"]["teacher"])
    student = auth(e2e["users"]["student"])
    parent = auth(e2e["users"]["parent"])
    other_student = auth(e2e["users"]["other_student"])
    other_school = auth(e2e["users"]["teacher3"])
    sid = e2e["student"].id
    bank_ids = [q.id for q in e2e["bank"]]

    async def call(method, path, body=None, headers=teacher, code=200):
        kwargs = {"headers": headers}
        if body is not None:
            kwargs["json"] = body
        response = await client.request(method, API + path, **kwargs)
        assert response.status_code == code, f"{method} {path} -> {response.status_code}: {response.text}"
        if response.content:
            try:
                return response.json()
            except Exception:
                return response.text
        return None

    # --- Teacher: create mixed homework and assign -----------------------------------------
    gap = await call("GET", f"/students/{sid}/homework/gap-analysis")
    assert "LU" in gap["weakest"]

    preview_req = {"subject_id": e2e["subject"].id, "max_questions": 3, "include_ai_generated": False}
    preview = await call("POST", f"/students/{sid}/homework/preview", preview_req)
    assert preview["question_count"] == 3
    preview_ids = [item["question_id"] for item in preview["items"]]
    assert set(preview_ids) == set(bank_ids)

    draft = await call(
        "POST", f"/students/{sid}/homework/drafts",
        {**preview_req, "expected_question_ids": preview_ids}, code=201,
    )
    await call("POST", f"/homework/drafts/{draft['id']}/approve")
    assignment = await call("POST", f"/homework/drafts/{draft['id']}/assign", code=201)
    aid = assignment["id"]
    types = {item["type"] for item in draft["items"]}
    assert {"mcq", "short", "descriptive"} <= types

    # --- Student: view, answer, submit -----------------------------------------------------
    me_base = f"/students/me/homework/assignments/{aid}"
    detail = await call("GET", me_base, headers=student)
    blob = json.dumps(detail)
    assert "correct_answer" not in blob and "marking_rubric" not in blob
    assert "SECRET" not in blob

    # Map bank order from draft positions.
    by_pos = {item["position"]: item for item in draft["items"]}
    mcq_pos = next(p for p, q in by_pos.items() if q["type"] == "mcq")
    short_pos = next(p for p, q in by_pos.items() if q["type"] == "short")
    desc_pos = next(p for p, q in by_pos.items() if q["type"] == "descriptive")
    # Correct MCQ option "12 m²" is index 1 in the seeded options.
    answers = [
        {"position": mcq_pos, "selected_option_index": 1},
        {"position": short_pos, "answer_text": "Area equals length times breadth (A = l × b)."},
        {"position": desc_pos, "answer_text": "Measure the perimeter, then buy fencing to match that length."},
    ]
    submission = await call("PUT", me_base + "/submission", {"answers": answers}, headers=student, code=201)
    await call("POST", me_base + "/submission/submit", {"expected_version": submission["version"]}, headers=student)

    # --- Teacher: open submission, AI suggest ----------------------------------------------
    overview = await call("GET", f"/homework/assignments/{aid}/submissions")
    assert overview["students"][0]["status"] == "submitted"
    inspected = await call("GET", f"/homework/assignments/{aid}/submissions/{sid}")
    assert inspected["status"] == "submitted"

    grading = f"/homework/assignments/{aid}/evaluation"
    evaluation = await call("POST", grading, code=201)
    assert evaluation["status"] == "pending"
    version_before_ai = evaluation["version"]

    suggestions = await call("POST", grading + "/ai-suggestions", {}, code=201)
    assert suggestions["evaluation_version"] == version_before_ai
    assert len(suggestions["items"]) == 3
    by_sug = {item["position"]: item for item in suggestions["items"]}

    # MCQ deterministic when key resolves.
    assert by_sug[mcq_pos]["source"] == "deterministic_mcq"
    assert by_sug[mcq_pos]["suggested_marks"] == by_sug[mcq_pos]["max_marks"]
    assert by_sug[mcq_pos]["correctness"] == "correct"

    # Descriptive / short: rubric-based (live Gemini or mock).
    for pos in (short_pos, desc_pos):
        assert by_sug[pos]["source"] in {"gemini", "teacher_required"}
        if by_sug[pos]["source"] == "gemini":
            assert by_sug[pos]["rubric_criteria"]
            assert 0 <= by_sug[pos]["suggested_marks"] <= by_sug[pos]["max_marks"]
            assert by_sug[pos]["explanation"]
            assert by_sug[pos]["feedback"]
        assert "correct_answer" not in by_sug[pos]

    if not GEMINI_LIVE:
        assert len(e2e["fake"].calls) >= 1
        for call_payload in e2e["fake"].calls:
            assert e2e["student"].name not in call_payload["prompt"]
            assert sid not in call_payload["prompt"]
            assert e2e["users"]["student"].email not in call_payload["prompt"]

    # Reload evaluation: AI must not have written awarded_marks or bumped version.
    evaluation = await call("GET", grading)
    assert evaluation["version"] == version_before_ai
    assert all(item["awarded_marks"] is None for item in evaluation["items"])

    # Edit one suggestion (short): teacher chooses different marks than AI.
    edited_marks = 1 if by_sug[short_pos]["suggested_marks"] != 1 else 2
    # Reject descriptive suggestion: mark manually with 0 instead of accepting AI.
    # Accept MCQ suggestion: use AI suggested marks.
    accept_mcq = by_sug[mcq_pos]["suggested_marks"]
    evaluation = await call("PATCH", grading + "/items", {
        "expected_version": evaluation["version"],
        "items": [
            {"position": mcq_pos, "awarded_marks": accept_mcq, "feedback": by_sug[mcq_pos]["feedback"]},
            {"position": short_pos, "awarded_marks": edited_marks, "feedback": "Teacher edit of AI suggestion."},
            {"position": desc_pos, "awarded_marks": 0, "feedback": "Rejected AI suggestion; needs rewrite."},
        ],
    })
    assert evaluation["items"]
    saved = {item["position"]: item for item in evaluation["items"]}
    assert saved[mcq_pos]["awarded_marks"] == accept_mcq
    assert saved[short_pos]["awarded_marks"] == edited_marks
    assert saved[desc_pos]["awarded_marks"] == 0

    # AI cannot finalize/release by itself — only explicit teacher transitions.
    evaluation = await call("POST", grading + "/finalize", {"expected_version": evaluation["version"]})
    assert evaluation["status"] == "marked"
    await call("GET", me_base + "/evaluation", headers=student, code=404)
    parent_path = f"/parents/me/students/{sid}/homework/assignments/{aid}/evaluation"
    await call("GET", parent_path, headers=parent, code=404)

    evaluation = await call("POST", grading + "/release", {"expected_version": evaluation["version"]})
    assert evaluation["status"] == "released"

    # --- Student & parent released results; no keys / AI internals -------------------------
    student_result = await call("GET", me_base + "/evaluation", headers=student)
    parent_result = await call("GET", parent_path, headers=parent)
    assert student_result == parent_result
    assert student_result["total_awarded"] == accept_mcq + edited_marks + 0
    hidden = ("correct_answer", "marking_rubric", "explanation", "suggested_marks",
              "needs_teacher_attention", "rubric_criteria", "confidence", "ai-suggestions",
              "version", "marked_by", "SECRET")
    result_text = json.dumps(student_result)
    for token in hidden:
        assert token not in result_text

    # Suggestions endpoint remains teacher-only after release (locked for regenerate).
    await call("GET", grading + "/ai-suggestions", code=200)  # teacher can still read stored
    await call("POST", grading + "/ai-suggestions/rerun", {}, code=409)  # cannot change after finalize

    # --- Security --------------------------------------------------------------------------
    await call("GET", me_base, headers=other_student, code=404)
    await call("GET", me_base + "/evaluation", headers=other_student, code=404)
    await call("GET", grading, headers=other_student, code=403)
    await call("POST", grading + "/ai-suggestions", {}, headers=other_student, code=403)

    await call("GET", grading, headers=other_school, code=404)
    await call("POST", grading + "/ai-suggestions", {}, headers=other_school, code=404)

    # Students cannot invoke teacher evaluation endpoints.
    await call("POST", grading, headers=student, code=403)
    await call("POST", grading + "/finalize", {"expected_version": 1}, headers=student, code=403)
    await call("POST", grading + "/release", {"expected_version": 1}, headers=student, code=403)

    # Record mode for humans reading the pytest output.
    print(f"\n[AI-EVAL E2E] verification_mode={e2e['mode']} assignment={aid}")
    assert e2e["mode"] in {"live_gemini", "mocked_gemini"}
