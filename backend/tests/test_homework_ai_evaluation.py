"""AI-assisted homework evaluation suggestions (teacher-only).

  POST /api/v1/homework/assignments/{id}/evaluation/ai-suggestions
  GET  /api/v1/homework/assignments/{id}/evaluation/ai-suggestions
  POST /api/v1/homework/assignments/{id}/evaluation/ai-suggestions/rerun

Suggestions never write awarded_marks, never finalize/release, and never call a real Gemini
provider in these tests.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text

import backend.app.modules.differentiated_homework.router as homework_router
from backend.app.core.security import create_access_token
from backend.app.models.entities import ClassSection, Student, Subject, User
from backend.app.modules.differentiated_homework import ai_evaluation_service as ai_eval
from backend.app.modules.differentiated_homework.ai_evaluation_service import (
    build_evaluation_prompt,
    classify_answer_text,
    score_mcq,
    teacher_required_suggestion,
    validate_ai_suggestion,
)
from backend.app.services.ai_gateway import AIInvalidResponse, AINotConfigured, AIProviderTimeout
from backend.app.modules.differentiated_homework.models import (
    HomeworkAssignmentRecord,
    HomeworkDraftItemRecord,
    HomeworkDraftRecord,
    HomeworkEvaluationRecord,
    HomeworkSubmissionAnswerRecord,
    StudentAccountLink,
)
from backend.app.services import ai_gateway


BASE = "/api/v1/homework/assignments/{}"
EVAL = BASE + "/evaluation"
SUGGEST = EVAL + "/ai-suggestions"
RERUN = SUGGEST + "/rerun"
ITEMS = EVAL + "/items"
FINALIZE = EVAL + "/finalize"
STUDENT_SUB = "/api/v1/students/me/homework/assignments/{}/submission"
RESULT = "/api/v1/students/me/homework/assignments/{}/evaluation"
NOW = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)


def uid(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def bearer(user_id, role, school_id="school-1"):
    return {"Authorization": f"Bearer {create_access_token(user_id, school_id=school_id, role=role)}"}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


class FakeProvider:
    name, model = "gemini", "fake-eval-model"

    def __init__(self, *payloads, error=None):
        self.payloads, self.error, self.calls = list(payloads), error, []

    async def generate_json(self, *, system, prompt, schema):
        self.calls.append({"system": system, "prompt": prompt, "schema": schema.__name__})
        if self.error:
            raise self.error
        payload = self.payloads[min(len(self.calls), len(self.payloads)) - 1]
        return payload if isinstance(payload, str) else json.dumps(payload)


def gemini_ok(marks=2, max_marks=3, correctness="partially_correct", attention=False, criteria="auto"):
    if criteria == "auto":
        # Keep criterion totals consistent with suggested_marks (validation requires this).
        if marks <= 0:
            criteria = [{"criterion": "Overall", "max_marks": max_marks, "awarded_marks": 0, "comment": "No credit"}]
        elif marks >= max_marks:
            criteria = [{"criterion": "Overall", "max_marks": max_marks, "awarded_marks": max_marks, "comment": "Full"}]
        else:
            criteria = [
                {"criterion": "Method", "max_marks": max(1, marks), "awarded_marks": marks, "comment": "Partial method"},
                {"criterion": "Accuracy", "max_marks": max_marks - max(1, marks), "awarded_marks": 0, "comment": "Final answer off"},
            ]
    return {
        "suggested_marks": marks,
        "correctness": correctness,
        "explanation": "Approach is sound; final answer needs correction (partial credit).",
        "feedback": "Good method — check the final step and units next time.",
        "rubric_criteria": criteria or [],
        "confidence": "medium",
        "needs_teacher_attention": attention,
    }


@pytest_asyncio.fixture
async def world(db_session, client, monkeypatch):
    """Alice submitted MCQ+short+descriptive. Cara is another school. Teacher2 owns a blank submit."""
    subj = Subject(id=uid("aie-subj"), name="AI Eval Maths", code=uid("AIE"), grade=8)
    cls1 = ClassSection(id=uid("aie-c1"), school_id="school-1", grade=8, section="A", name="AIE 1",
                        subject_ids_json=[subj.id])
    cls3 = ClassSection(id=uid("aie-c3"), school_id="school-3", grade=8, section="B", name="AIE 3",
                        subject_ids_json=[subj.id])
    alice = Student(id=uid("aie-alice"), school_id="school-1", class_id=cls1.id, class_name=cls1.name,
                    name="Alice", roll_no=1, lu_score=40, cu_score=70, au_score=60, ct_score=50,
                    overall_score=55, baseline_lu=30, baseline_cu=50, baseline_au=40, baseline_ct=35,
                    baseline_overall=39)
    cara = Student(id=uid("aie-cara"), school_id="school-3", class_id=cls3.id, class_name=cls3.name,
                   name="Cara", roll_no=1, lu_score=40, cu_score=70, au_score=60, ct_score=50,
                   overall_score=55, baseline_lu=30, baseline_cu=50, baseline_au=40, baseline_ct=35,
                   baseline_overall=39)
    u_alice = User(id=uid("aie-ualice"), email="aie-alice@test.invalid", name="Alice U",
                   hashed_password="x", role="student", school_id="school-1")
    u_cara = User(id=uid("aie-ucara"), email="aie-cara@test.invalid", name="Cara U",
                  hashed_password="x", role="student", school_id="school-3")
    u_teacher2 = User(id=uid("aie-t2"), email="aie-t2@test.invalid", name="Teacher 2",
                      hashed_password="x", role="teacher", school_id="school-1")

    def assignment(student, created_by, *, mcq_key="B", short_rubric="1 for method; 1 for answer; 1 for units"):
        items = [
            HomeworkDraftItemRecord(
                position=1, source_question_id=uid("src"), text="MCQ: pick the area", type="mcq",
                options_json=["7", "12", "14", "24"], marks=3, competency="AU", competency_rank=1,
                bloom_level="Apply", is_ai_generated=False, correct_answer=mcq_key,
                marking_rubric="Full marks for the correct option.",
            ),
            HomeworkDraftItemRecord(
                position=2, source_question_id=uid("src"), text="Short: explain the area formula",
                type="short", options_json=[], marks=3, competency="CU", competency_rank=2,
                bloom_level="Understand", is_ai_generated=False, correct_answer="A = l × b",
                marking_rubric=short_rubric,
            ),
            HomeworkDraftItemRecord(
                position=3, source_question_id=uid("src"), text="Describe how you would fence a garden",
                type="descriptive", options_json=[], marks=3, competency="CT", competency_rank=3,
                bloom_level="Evaluate", is_ai_generated=False, correct_answer=None,
                marking_rubric="Clarity 1; Method 1; Justification 1",
            ),
        ]
        draft = HomeworkDraftRecord(
            student_id=student.id, school_id=student.school_id, subject_id=subj.id, created_by=created_by,
            status="assigned", requested_questions=3, include_ai_generated=False, question_count=3,
            total_marks=9, shortfall=0, notes_json=[],
            rationale_json={"targeted_competencies": ["AU"], "weakest": ["AU"],
                            "competency_scores": {"LU": 40, "CU": 70, "AU": 60, "CT": 50},
                            "lowest_score": 40, "highest_score": 70, "score_source": "test",
                            "summary": "test"},
            reviewed_by=created_by, review_note="ok", items=items,
        )
        return HomeworkAssignmentRecord(
            id=uid("aie-asg"), draft=draft, student_id=student.id, school_id=student.school_id,
            subject_id=subj.id, assigned_by=created_by, assigned_at=NOW - timedelta(days=1),
            due_at=NOW + timedelta(days=2), status="assigned",
        )

    a_alice = assignment(alice, "user-teacher-1")
    a_cara = assignment(cara, "user-teacher-3")
    a_other = assignment(alice, u_teacher2.id)

    db_session.add_all([subj, cls1, cls3, alice, cara, u_alice, u_cara, u_teacher2, a_alice, a_cara, a_other,
                        StudentAccountLink(user_id=u_alice.id, student_id=alice.id, created_by="user-admin"),
                        StudentAccountLink(user_id=u_cara.id, student_id=cara.id, created_by="user-admin")])
    await db_session.commit()

    ids = {
        "alice": alice.id, "cara": cara.id, "u_alice": u_alice.id, "u_cara": u_cara.id,
        "u_teacher2": u_teacher2.id, "a_alice": a_alice.id, "a_cara": a_cara.id, "a_other": a_other.id,
        "classes": [cls1.id, cls3.id], "subject": subj.id,
    }

    monkeypatch.setattr(homework_router, "utc_now", lambda: NOW)

    res = await client.put(
        STUDENT_SUB.format(ids["a_alice"]), headers=bearer(ids["u_alice"], "student"),
        json={"answers": [
            {"position": 1, "selected_option_index": 1},  # "12" — matches key B
            {"position": 2, "answer_text": "Area equals length times breadth."},
            {"position": 3, "answer_text": "Measure the perimeter then buy fencing."},
        ]},
    )
    assert res.status_code == 201, res.text
    res = await client.post(STUDENT_SUB.format(ids["a_alice"]) + "/submit",
                            headers=bearer(ids["u_alice"], "student"), json={"expected_version": 1})
    assert res.status_code == 200, res.text
    res = await client.post(STUDENT_SUB.format(ids["a_cara"]) + "/submit",
                            headers=bearer(ids["u_cara"], "student", "school-3"), json={})
    assert res.status_code == 200, res.text

    monkeypatch.undo()
    yield ids

    await db_session.rollback()
    for key in ("a_alice", "a_cara", "a_other"):
        await db_session.execute(text("DELETE FROM audit_events WHERE details LIKE :d"), {"d": f"%{ids[key]}%"})
    for student_id in (ids["alice"], ids["cara"]):
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
            "DELETE FROM homework_draft_items WHERE draft_id IN (SELECT id FROM homework_drafts WHERE student_id = :s)",
            "DELETE FROM homework_drafts WHERE student_id = :s",
            "DELETE FROM student_account_links WHERE student_id = :s",
            "DELETE FROM students WHERE id = :s",
        ):
            await db_session.execute(text(sql), p)
    for key in ("u_alice", "u_cara", "u_teacher2"):
        await db_session.execute(text("DELETE FROM users WHERE id = :u"), {"u": ids[key]})
    for class_id in ids["classes"]:
        await db_session.execute(text("DELETE FROM classes WHERE id = :c"), {"c": class_id})
    await db_session.execute(text("DELETE FROM subjects WHERE id = :j"), {"j": ids["subject"]})
    await db_session.commit()


async def start_eval(client, assignment_id, headers):
    res = await client.post(EVAL.format(assignment_id), headers=headers)
    assert res.status_code in (200, 201), res.text
    return res.json()


# --- Unit: MCQ + validation -----------------------------------------------------------------


def test_mcq_deterministic_correct_and_incorrect():
    correct = score_mcq(
        position=1, draft_item_id="d1", max_marks=3, options=["7", "12", "14", "24"],
        correct_answer="B",
        answer=HomeworkSubmissionAnswerRecord(selected_option_index=1, answer_text=None),
    )
    assert correct.suggested_marks == 3 and correct.correctness == "correct"
    assert correct.source == "deterministic_mcq" and correct.confidence == "high"

    wrong = score_mcq(
        position=1, draft_item_id="d1", max_marks=3, options=["7", "12", "14", "24"],
        correct_answer="12",
        answer=HomeworkSubmissionAnswerRecord(selected_option_index=0, answer_text=None),
    )
    assert wrong.suggested_marks == 0 and wrong.correctness == "incorrect"


def test_mcq_missing_answer_key_flags_attention():
    suggestion = score_mcq(
        position=1, draft_item_id="d1", max_marks=2, options=["A", "B"], correct_answer=None,
        answer=HomeworkSubmissionAnswerRecord(selected_option_index=0, answer_text=None),
    )
    assert suggestion.correctness == "undetermined"
    assert suggestion.needs_teacher_attention is True
    assert suggestion.suggested_marks == 0


def test_validate_ai_suggestion_rejects_impossible_marks_and_malformed():
    ok = validate_ai_suggestion(json.dumps(gemini_ok(marks=2)), max_marks=3, has_rubric=True)
    assert ok.suggested_marks == 2 and ok.correctness == "partially_correct"

    with pytest.raises(AIInvalidResponse):
        validate_ai_suggestion(json.dumps(gemini_ok(marks=9)), max_marks=3, has_rubric=True)
    with pytest.raises(AIInvalidResponse):
        validate_ai_suggestion("not-json", max_marks=3, has_rubric=True)
    with pytest.raises(AIInvalidResponse):
        validate_ai_suggestion(json.dumps({**gemini_ok(), "correctness": "excellent"}), max_marks=3, has_rubric=True)
    with pytest.raises(AIInvalidResponse):
        bad = gemini_ok(criteria=[{"criterion": "X", "max_marks": 1, "awarded_marks": 5, "comment": "no"}])
        validate_ai_suggestion(json.dumps(bad), max_marks=3, has_rubric=True)
    # Criterion max sum above question max.
    with pytest.raises(AIInvalidResponse):
        validate_ai_suggestion(json.dumps(gemini_ok(
            marks=2,
            criteria=[
                {"criterion": "A", "max_marks": 2, "awarded_marks": 1, "comment": ""},
                {"criterion": "B", "max_marks": 2, "awarded_marks": 1, "comment": ""},
            ],
        )), max_marks=3, has_rubric=True)
    # Criterion awarded sum must equal suggested_marks.
    with pytest.raises(AIInvalidResponse):
        validate_ai_suggestion(json.dumps(gemini_ok(
            marks=2,
            criteria=[{"criterion": "A", "max_marks": 3, "awarded_marks": 1, "comment": ""}],
        )), max_marks=3, has_rubric=True)
    # Numeric confidence is not an ordinal heuristic label.
    with pytest.raises(AIInvalidResponse):
        validate_ai_suggestion(json.dumps({**gemini_ok(marks=2, criteria=[]), "confidence": 0.91}),
                               max_marks=3, has_rubric=True)
    with pytest.raises(AIInvalidResponse):
        validate_ai_suggestion(json.dumps({**gemini_ok(marks=2, criteria=[]), "confidence": "91%"}),
                               max_marks=3, has_rubric=True)


def test_prompt_encodes_partial_credit_alternatives_and_excludes_pii():
    system, prompt = build_evaluation_prompt(
        question_type="descriptive",
        question_text="Explain area",
        options=[],
        correct_answer="A=lb",
        marking_rubric="method + answer",
        max_marks=3,
        learner_answer="length times breadth",
        answer_quality="usable",
    )
    blob = system + "\n" + prompt
    for expected in ("partial marks", "equivalent", "spelling", "conceptual", "calibrated probability",
                     "never invent"):
        assert expected in blob.casefold()
    for banned in ("Alice", "alice@", "school-1", "user-teacher", "student_id", "user-"):
        assert banned.casefold() not in blob.casefold()


def test_classify_answer_text_detects_missing_and_uncertain_ocr():
    assert classify_answer_text(None) == "missing"
    assert classify_answer_text("   ") == "missing"
    assert classify_answer_text("[OCR uncertain] perimeter maybe 12") == "uncertain"
    assert classify_answer_text("illegible handwriting near the diagram") == "uncertain"
    assert classify_answer_text("Area = l × b for a rectangle.") == "usable"


def test_teacher_required_suggestion_never_invents_key():
    suggestion = teacher_required_suggestion(
        position=2, draft_item_id="d", max_marks=3,
        reason="No key or rubric.", feedback="Teacher will mark.",
    )
    assert suggestion.source == "teacher_required"
    assert suggestion.needs_teacher_attention is True
    assert suggestion.correctness == "undetermined"
    assert suggestion.suggested_marks == 0
    assert suggestion.model is None


# --- API ------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_suggestions_mcq_deterministic_and_ai_open_ended(world, client, monkeypatch, teacher_token):
    fake = FakeProvider(gemini_ok(marks=2), gemini_ok(marks=2, correctness="partially_correct"))
    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: fake)
    headers = auth(teacher_token)
    started = await start_eval(client, world["a_alice"], headers)
    version = started["version"]

    res = await client.post(SUGGEST.format(world["a_alice"]), headers=headers, json={})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["evaluation_id"] == started["id"]
    assert body["evaluation_version"] == version
    assert len(body["items"]) == 3

    by_pos = {item["position"]: item for item in body["items"]}
    assert by_pos[1]["source"] == "deterministic_mcq"
    assert by_pos[1]["suggested_marks"] == 3
    assert by_pos[1]["correctness"] == "correct"
    assert by_pos[2]["source"] == "gemini" and by_pos[2]["suggested_marks"] == 2
    assert by_pos[3]["source"] == "gemini"
    assert "explanation" in by_pos[2] and "feedback" in by_pos[2]
    assert by_pos[2]["rubric_criteria"]
    # Two open-ended questions → two Gemini calls; MCQ must not call the provider.
    assert len(fake.calls) == 2
    for call in fake.calls:
        assert "Alice" not in call["prompt"]
        assert world["alice"] not in call["prompt"]

    # Marks on the evaluation remain untouched.
    loaded = await client.get(EVAL.format(world["a_alice"]), headers=headers)
    assert loaded.status_code == 200
    assert loaded.json()["version"] == version
    assert all(item["awarded_marks"] is None for item in loaded.json()["items"])
    assert loaded.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_duplicate_generate_conflicts_until_rerun(world, client, monkeypatch, teacher_token):
    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: FakeProvider(gemini_ok(), gemini_ok()))
    headers = auth(teacher_token)
    await start_eval(client, world["a_alice"], headers)

    first = await client.post(SUGGEST.format(world["a_alice"]), headers=headers, json={})
    assert first.status_code == 201, first.text
    dup = await client.post(SUGGEST.format(world["a_alice"]), headers=headers, json={})
    assert dup.status_code == 409
    assert "re-run" in dup.json()["detail"].lower() or "replace" in dup.json()["detail"].lower()

    # GET returns the stored set.
    got = await client.get(SUGGEST.format(world["a_alice"]), headers=headers)
    assert got.status_code == 200
    assert len(got.json()["items"]) == 3

    fake2 = FakeProvider(gemini_ok(marks=1), gemini_ok(marks=0, correctness="incorrect"))
    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: fake2)
    rerun = await client.post(RERUN.format(world["a_alice"]), headers=headers, json={})
    assert rerun.status_code == 200, rerun.text
    by_pos = {i["position"]: i for i in rerun.json()["items"]}
    assert by_pos[2]["suggested_marks"] == 1
    assert by_pos[3]["suggested_marks"] == 0


@pytest.mark.asyncio
async def test_malformed_ai_output_returns_bad_gateway(world, client, monkeypatch, teacher_token):
    monkeypatch.setattr(
        ai_gateway, "get_ai_provider",
        lambda: FakeProvider({"suggested_marks": 99, "correctness": "correct",
                              "explanation": "x", "feedback": "y"}),
    )
    headers = auth(teacher_token)
    await start_eval(client, world["a_alice"], headers)
    # Restrict to the short-answer item so only the bad AI payload is used.
    res = await client.post(SUGGEST.format(world["a_alice"]), headers=headers, json={"positions": [2]})
    assert res.status_code == 502
    assert "AI" in res.json()["detail"] or "understood" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_missing_answer_key_mcq_still_returns_attention_suggestion(world, client, monkeypatch, db_session,
                                                                         teacher_token):
    # Clear the frozen MCQ key on Alice's draft item.
    assignment = (await db_session.execute(
        select(HomeworkAssignmentRecord).filter(HomeworkAssignmentRecord.id == world["a_alice"])
    )).scalars().one()
    for item in assignment.draft.items:
        if item.position == 1:
            item.correct_answer = None
    await db_session.commit()

    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: FakeProvider(gemini_ok(), gemini_ok()))
    headers = auth(teacher_token)
    await start_eval(client, world["a_alice"], headers)
    res = await client.post(SUGGEST.format(world["a_alice"]), headers=headers, json={"positions": [1]})
    assert res.status_code == 201, res.text
    item = res.json()["items"][0]
    assert item["position"] == 1
    assert item["needs_teacher_attention"] is True
    assert item["correctness"] == "undetermined"
    assert item["source"] == "deterministic_mcq"


@pytest.mark.asyncio
async def test_authorization_failures(world, client, monkeypatch, teacher_token, other_school_teacher_token,
                                      student_token):
    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: FakeProvider(gemini_ok(), gemini_ok()))
    # Owner teacher can start; other-school teacher cannot see the assignment.
    await start_eval(client, world["a_alice"], auth(teacher_token))

    denied = await client.post(SUGGEST.format(world["a_alice"]), headers=auth(other_school_teacher_token), json={})
    assert denied.status_code == 404

    other_teacher = await client.post(
        SUGGEST.format(world["a_alice"]), headers=bearer(world["u_teacher2"], "teacher"), json={}
    )
    assert other_teacher.status_code == 404

    student = await client.post(SUGGEST.format(world["a_alice"]), headers=auth(student_token), json={})
    assert student.status_code == 403

    # Student result endpoint must not expose suggestions or keys even after generate.
    await client.post(SUGGEST.format(world["a_alice"]), headers=auth(teacher_token), json={})
    result = await client.get(RESULT.format(world["a_alice"]), headers=bearer(world["u_alice"], "student"))
    assert result.status_code == 404  # not released


@pytest.mark.asyncio
async def test_suggestions_blocked_after_finalize(world, client, monkeypatch, teacher_token):
    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: FakeProvider(gemini_ok(), gemini_ok()))
    headers = auth(teacher_token)
    started = await start_eval(client, world["a_alice"], headers)
    # Apply marks manually and finalize.
    res = await client.patch(ITEMS.format(world["a_alice"]), headers=headers, json={
        "expected_version": started["version"],
        "items": [{"position": 1, "awarded_marks": 3}, {"position": 2, "awarded_marks": 2},
                  {"position": 3, "awarded_marks": 1}],
    })
    assert res.status_code == 200, res.text
    fin = await client.post(FINALIZE.format(world["a_alice"]), headers=headers,
                            json={"expected_version": res.json()["version"]})
    assert fin.status_code == 200, fin.text

    blocked = await client.post(SUGGEST.format(world["a_alice"]), headers=headers, json={"replace": True})
    assert blocked.status_code == 409

    rerun = await client.post(RERUN.format(world["a_alice"]), headers=headers, json={})
    assert rerun.status_code == 409


@pytest.mark.asyncio
async def test_get_without_generate_is_404(world, client, teacher_token):
    headers = auth(teacher_token)
    await start_eval(client, world["a_alice"], headers)
    res = await client.get(SUGGEST.format(world["a_alice"]), headers=headers)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_replace_true_allows_overwrite_without_rerun_path(world, client, monkeypatch, teacher_token):
    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: FakeProvider(gemini_ok(marks=2), gemini_ok(marks=2)))
    headers = auth(teacher_token)
    await start_eval(client, world["a_alice"], headers)
    assert (await client.post(SUGGEST.format(world["a_alice"]), headers=headers, json={})).status_code == 201

    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: FakeProvider(gemini_ok(marks=0), gemini_ok(marks=0)))
    again = await client.post(SUGGEST.format(world["a_alice"]), headers=headers, json={"replace": True})
    assert again.status_code == 201
    assert {i["suggested_marks"] for i in again.json()["items"] if i["source"] == "gemini"} == {0}


@pytest.mark.asyncio
async def test_suggestions_never_mutate_competency_or_submission(world, client, monkeypatch, teacher_token, db_session):
    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: FakeProvider(gemini_ok(), gemini_ok()))
    headers = auth(teacher_token)
    await start_eval(client, world["a_alice"], headers)

    before = (await db_session.execute(select(Student).filter(Student.id == world["alice"]))).scalars().one()
    scores = (before.lu_score, before.cu_score, before.au_score, before.ct_score)

    res = await client.post(SUGGEST.format(world["a_alice"]), headers=headers, json={})
    assert res.status_code == 201

    await db_session.refresh(before)
    assert (before.lu_score, before.cu_score, before.au_score, before.ct_score) == scores

    answers = (await db_session.execute(
        text("SELECT answer_text, selected_option_index FROM homework_submission_answers "
             "WHERE submission_id IN (SELECT id FROM homework_submissions WHERE assignment_id = :a) "
             "ORDER BY draft_item_id"),
        {"a": world["a_alice"]},
    )).all()
    assert any(row[1] == 1 for row in answers)  # MCQ selection preserved
    assert any((row[0] or "").startswith("Area equals") for row in answers)


@pytest.mark.asyncio
async def test_open_ended_without_key_or_rubric_requires_teacher_no_gemini(world, client, monkeypatch, db_session,
                                                                          teacher_token):
    assignment = (await db_session.execute(
        select(HomeworkAssignmentRecord).filter(HomeworkAssignmentRecord.id == world["a_alice"])
    )).scalars().one()
    for item in assignment.draft.items:
        if item.position == 3:
            item.correct_answer = None
            item.marking_rubric = None
    await db_session.commit()

    fake = FakeProvider(gemini_ok())
    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: fake)
    headers = auth(teacher_token)
    await start_eval(client, world["a_alice"], headers)
    res = await client.post(SUGGEST.format(world["a_alice"]), headers=headers, json={"positions": [3]})
    assert res.status_code == 201, res.text
    item = res.json()["items"][0]
    assert item["source"] == "teacher_required"
    assert item["needs_teacher_attention"] is True
    assert item["correctness"] == "undetermined"
    assert fake.calls == []


@pytest.mark.asyncio
async def test_uncertain_ocr_answer_requires_teacher_without_gemini(world, client, monkeypatch, db_session,
                                                                    teacher_token):
    # Overwrite the short-answer text with an OCR-uncertain marker.
    await db_session.execute(
        text(
            "UPDATE homework_submission_answers SET answer_text = :t "
            "WHERE submission_id IN (SELECT id FROM homework_submissions WHERE assignment_id = :a) "
            "AND draft_item_id IN (SELECT id FROM homework_draft_items WHERE position = 2 "
            "AND draft_id IN (SELECT draft_id FROM homework_assignments WHERE id = :a))"
        ),
        {"t": "[OCR uncertain] area maybe length x width", "a": world["a_alice"]},
    )
    await db_session.commit()

    fake = FakeProvider(gemini_ok())
    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: fake)
    headers = auth(teacher_token)
    await start_eval(client, world["a_alice"], headers)
    res = await client.post(SUGGEST.format(world["a_alice"]), headers=headers, json={"positions": [2]})
    assert res.status_code == 201, res.text
    item = res.json()["items"][0]
    assert item["source"] == "teacher_required"
    assert item["needs_teacher_attention"] is True
    assert "OCR" in item["explanation"] or "uncertain" in item["explanation"].lower()
    assert fake.calls == []


@pytest.mark.asyncio
async def test_gemini_failure_preserves_teacher_marks_and_submission(world, client, monkeypatch, teacher_token,
                                                                     db_session):
    monkeypatch.setattr(ai_gateway, "get_ai_provider",
                        lambda: FakeProvider(error=AIProviderTimeout()))
    headers = auth(teacher_token)
    started = await start_eval(client, world["a_alice"], headers)
    # Teacher saves a mark before AI is attempted.
    saved = await client.patch(ITEMS.format(world["a_alice"]), headers=headers, json={
        "expected_version": started["version"],
        "items": [{"position": 1, "awarded_marks": 3, "feedback": "Teacher already marked MCQ."}],
    })
    assert saved.status_code == 200, saved.text
    version = saved.json()["version"]

    failed = await client.post(SUGGEST.format(world["a_alice"]), headers=headers, json={"positions": [2]})
    assert failed.status_code == 504

    loaded = await client.get(EVAL.format(world["a_alice"]), headers=headers)
    assert loaded.status_code == 200
    body = loaded.json()
    assert body["version"] == version
    assert body["status"] == "pending"
    q1 = next(q for q in body["items"] if q["position"] == 1)
    assert q1["awarded_marks"] == 3
    assert q1["feedback"] == "Teacher already marked MCQ."
    # No suggestion rows persisted after failure.
    assert (await client.get(SUGGEST.format(world["a_alice"]), headers=headers)).status_code == 404

    answers = (await db_session.execute(
        text("SELECT COUNT(*) FROM homework_submission_answers WHERE submission_id IN "
             "(SELECT id FROM homework_submissions WHERE assignment_id = :a)"),
        {"a": world["a_alice"]},
    )).scalar()
    assert answers == 3


@pytest.mark.asyncio
async def test_rerun_does_not_overwrite_teacher_approved_marks(world, client, monkeypatch, teacher_token):
    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: FakeProvider(gemini_ok(), gemini_ok()))
    headers = auth(teacher_token)
    started = await start_eval(client, world["a_alice"], headers)
    await client.post(SUGGEST.format(world["a_alice"]), headers=headers, json={})
    marked = await client.patch(ITEMS.format(world["a_alice"]), headers=headers, json={
        "expected_version": started["version"],
        "items": [{"position": 2, "awarded_marks": 3, "feedback": "Teacher override."}],
    })
    assert marked.status_code == 200, marked.text
    teacher_version = marked.json()["version"]

    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: FakeProvider(gemini_ok(marks=0), gemini_ok(marks=1)))
    rerun = await client.post(RERUN.format(world["a_alice"]), headers=headers, json={})
    assert rerun.status_code == 200, rerun.text

    loaded = await client.get(EVAL.format(world["a_alice"]), headers=headers)
    body = loaded.json()
    assert body["version"] == teacher_version
    q2 = next(q for q in body["items"] if q["position"] == 2)
    assert q2["awarded_marks"] == 3
    assert q2["feedback"] == "Teacher override."
    # Suggestion payload may change, but it is not the approved mark.
    by_pos = {i["position"]: i for i in rerun.json()["items"]}
    assert by_pos[2]["suggested_marks"] == 0


@pytest.mark.asyncio
async def test_unconfigured_gemini_returns_503_without_side_effects(world, client, monkeypatch, teacher_token):
    def boom():
        raise AINotConfigured()

    monkeypatch.setattr(ai_gateway, "get_ai_provider", boom)
    headers = auth(teacher_token)
    started = await start_eval(client, world["a_alice"], headers)
    res = await client.post(SUGGEST.format(world["a_alice"]), headers=headers, json={"positions": [2]})
    assert res.status_code == 503
    loaded = await client.get(EVAL.format(world["a_alice"]), headers=headers)
    assert loaded.json()["version"] == started["version"]
    assert all(q["awarded_marks"] is None for q in loaded.json()["items"])


@pytest.mark.asyncio
async def test_teacher_can_mark_with_the_local_qwen_model(world, client, monkeypatch, teacher_token):
    """provider='qwen' marks open-ended answers with the local Qwen model (works offline) and never calls Gemini;
    the MCQ is still scored from its key. Qwen's fenced JSON is accepted and the suggestion is labelled 'qwen'."""
    def gemini_forbidden():
        raise AssertionError("Gemini must not be used when Qwen is chosen")
    monkeypatch.setattr(ai_gateway, "get_ai_provider", gemini_forbidden)
    qwen = FakeProvider("```json\n" + json.dumps(gemini_ok(marks=2)) + "\n```",
                        json.dumps({"_WireSuggestion": gemini_ok(marks=1)}))
    qwen.name, qwen.model = "qwen", "Qwen/Qwen2.5-VL-3B-Instruct-AWQ"
    monkeypatch.setattr(ai_gateway, "QwenTextProvider", lambda: qwen)
    headers = auth(teacher_token)
    await start_eval(client, world["a_alice"], headers)

    res = await client.post(SUGGEST.format(world["a_alice"]), headers=headers, json={"provider": "qwen"})
    assert res.status_code == 201, res.text
    by_pos = {item["position"]: item for item in res.json()["items"]}
    assert by_pos[1]["source"] == "deterministic_mcq"
    assert (by_pos[2]["source"], by_pos[2]["suggested_marks"]) == ("qwen", 2)
    assert (by_pos[3]["source"], by_pos[3]["suggested_marks"]) == ("qwen", 1)
    assert len(qwen.calls) == 2

    # Re-running with Gemini replaces them with Gemini suggestions.
    gemini = FakeProvider(gemini_ok(marks=3), gemini_ok(marks=3))
    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: gemini)
    rerun = await client.post(RERUN.format(world["a_alice"]), headers=headers, json={"provider": "gemini"})
    assert rerun.status_code == 200, rerun.text
    assert {i["source"] for i in rerun.json()["items"] if i["position"] > 1} == {"gemini"}


@pytest.mark.asyncio
async def test_unavailable_qwen_marking_is_reported_and_unknown_models_refused(world, client, monkeypatch, teacher_token):
    monkeypatch.setattr(ai_gateway, "QwenTextProvider", lambda: FakeProvider(error=ai_gateway.QwenUnavailable()))
    headers = auth(teacher_token)
    await start_eval(client, world["a_alice"], headers)
    res = await client.post(SUGGEST.format(world["a_alice"]), headers=headers, json={"provider": "qwen"})
    assert res.status_code == 503 and "Qwen is not available" in res.json()["detail"]
    bad = await client.post(SUGGEST.format(world["a_alice"]), headers=headers, json={"provider": "gpt"})
    assert bad.status_code == 422
