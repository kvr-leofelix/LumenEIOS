"""Regression: full Differentiated Homework workflow without any AI provider.

Teacher: browse bank → preview (include_ai_generated=False) → draft → approve → assign →
inspect submission → manual evaluate → release.
Student: open → save → submit → see released feedback.
Optional AI suggestions remain covered by test_homework_ai_evaluation.py.
"""
from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from backend.app.models.entities import Subject
from backend.app.modules.differentiated_homework.models import (
    HomeworkAssignmentRecord,
    HomeworkDraftItemRecord,
    HomeworkDraftRecord,
    HomeworkEvaluationItemRecord,
    HomeworkEvaluationRecord,
    HomeworkSubmissionAnswerRecord,
    HomeworkSubmissionRecord,
)
from backend.tests.test_homework_legacy_security import auth, uid, world


@pytest.mark.asyncio
async def test_manual_dh_workflow_without_gemini(client, world, db_session, monkeypatch):
    # Hard fail if anything tries to reach a live AI provider.
    monkeypatch.setattr(
        "backend.app.services.ai_gateway.get_ai_provider",
        lambda: (_ for _ in ()).throw(
            AssertionError("AI provider must not be required for the manual DH workflow.")
        ),
    )

    student = world["students"][0]
    sid = student.id
    subject = Subject(id=world["subject"], name="Manual Maths", code=uid(), grade=8)
    world["classes"][0].subject_ids_json = [subject.id]
    db_session.add(subject)
    await db_session.commit()

    teacher = auth(world["users"]["teacher"])
    learner = auth(world["users"]["student"])
    parent = auth(world["users"]["parent"])

    async def call(method, path, body=None, headers=teacher, code=200):
        response = await client.request(method, "/api/v1" + path, json=body, headers=headers)
        assert response.status_code == code, response.text
        return response.json()

    try:
        # 1) Central bank already has school-scoped questions from the world fixture.
        bank = await call("GET", f"/assessments/question-bank?subject_id={subject.id}")
        assert any(q["id"] == world["questions"][0].id for q in bank)
        assert bank[0]["correct_answer"].startswith("SECRET-KEY-")

        # 2) Assemble + assign without AI bank items.
        request = {"subject_id": subject.id, "max_questions": 1, "include_ai_generated": False}
        preview = await call("POST", f"/students/{sid}/homework/preview", request)
        assert preview["question_count"] == 1
        draft = await call(
            "POST",
            f"/students/{sid}/homework/drafts",
            {**request, "expected_question_ids": [q["question_id"] for q in preview["items"]]},
            code=201,
        )
        await call("POST", f"/homework/drafts/{draft['id']}/approve")
        assignment = await call("POST", f"/homework/drafts/{draft['id']}/assign", code=201)
        aid = assignment["id"]

        # 3) Student opens, saves, submits.
        detail = await call("GET", f"/students/me/homework/assignments/{aid}", headers=learner)
        assert "correct_answer" not in str(detail)
        submission = await call(
            "PUT",
            f"/students/me/homework/assignments/{aid}/submission",
            {"answers": [{"position": 1, "selected_option_index": 0}]},
            headers=learner,
            code=201,
        )
        await call(
            "POST",
            f"/students/me/homework/assignments/{aid}/submission/submit",
            {"expected_version": submission["version"]},
            headers=learner,
        )

        # 4) Teacher inspects + manual evaluation (no AI suggestions endpoint called).
        inspected = await call("GET", f"/homework/assignments/{aid}/submissions/{sid}")
        assert inspected["status"] == "submitted"
        evaluation = await call("POST", f"/homework/assignments/{aid}/evaluation", code=201)
        evaluation = await call(
            "PATCH",
            f"/homework/assignments/{aid}/evaluation/items",
            {
                "expected_version": evaluation["version"],
                "items": [{"position": 1, "awarded_marks": 1, "feedback": "Manual mark — no AI."}],
            },
        )
        evaluation = await call(
            "POST",
            f"/homework/assignments/{aid}/evaluation/finalize",
            {"expected_version": evaluation["version"]},
        )
        await call(
            "POST",
            f"/homework/assignments/{aid}/evaluation/release",
            {"expected_version": evaluation["version"]},
        )

        # 5) Student + parent see released feedback.
        result = await call(
            "GET", f"/students/me/homework/assignments/{aid}/evaluation", headers=learner
        )
        parent_result = await call(
            "GET",
            f"/parents/me/students/{sid}/homework/assignments/{aid}/evaluation",
            headers=parent,
        )
        assert result == parent_result
        assert result["items"][0]["feedback"] == "Manual mark — no AI."
        assert "SECRET" not in str(result)
    finally:
        await db_session.rollback()
        drafts = select(HomeworkDraftRecord.id).where(HomeworkDraftRecord.student_id == sid)
        submissions = select(HomeworkSubmissionRecord.id).where(
            HomeworkSubmissionRecord.student_id == sid
        )
        evaluations = select(HomeworkEvaluationRecord.id).where(
            HomeworkEvaluationRecord.student_id == sid
        )
        await db_session.execute(
            delete(HomeworkEvaluationItemRecord).where(
                HomeworkEvaluationItemRecord.evaluation_id.in_(evaluations)
            )
        )
        await db_session.execute(
            delete(HomeworkEvaluationRecord).where(HomeworkEvaluationRecord.student_id == sid)
        )
        await db_session.execute(
            delete(HomeworkSubmissionAnswerRecord).where(
                HomeworkSubmissionAnswerRecord.submission_id.in_(submissions)
            )
        )
        await db_session.execute(
            delete(HomeworkSubmissionRecord).where(HomeworkSubmissionRecord.student_id == sid)
        )
        await db_session.execute(
            delete(HomeworkAssignmentRecord).where(HomeworkAssignmentRecord.student_id == sid)
        )
        await db_session.execute(
            delete(HomeworkDraftItemRecord).where(HomeworkDraftItemRecord.draft_id.in_(drafts))
        )
        await db_session.execute(
            delete(HomeworkDraftRecord).where(HomeworkDraftRecord.student_id == sid)
        )
        await db_session.execute(delete(Subject).where(Subject.id == subject.id))
        await db_session.commit()
