"""Teacher-confirmed marks reach the concept graph through the paper's confirmed concept links only."""
import uuid

import pytest
from sqlalchemy import select

from backend.app.api.v1 import ocr as ocr_api
from backend.app.models.entities import Assessment, Student
from backend.app.models.knowledge_components import StudentKcAttempt, StudentKcMastery
from backend.app.services import kc_graph_service
from backend.tests.test_assessment_learnsphere_connection import answers, assessment, review
from backend.tests.test_learnsphere import learning  # noqa: F401  (fixture)


def _no_model(*_args, **_kwargs):
    raise AssertionError("Teacher-confirmed marks must not ask a model for concept links.")


@pytest.mark.asyncio
async def test_published_handwritten_grade_updates_the_graph_once(client, db_session, monkeypatch, teacher_token):
    monkeypatch.setattr(kc_graph_service, "get_ai_provider", _no_model)
    monkeypatch.setattr(kc_graph_service, "QwenTextProvider", _no_model)
    monkeypatch.setattr(ocr_api, "get_ai_provider", _no_model)
    student = await db_session.scalar(select(Student).where(Student.class_id == "class-8a", Student.school_id == "school-1"))
    concept = await kc_graph_service.create_component(
        db_session, name=f"Doubling {uuid.uuid4().hex[:6]}", description="", subject_id="sub-math", topic="Multiplication")
    student_id, concept_id = student.id, concept.id
    paper_id = "kc-confirmed-" + uuid.uuid4().hex[:8]
    db_session.add(Assessment(
        id=paper_id, school_id="school-1", class_id="class-8a", subject_id="sub-math", title="Doubling",
        date="2026-11-11", total_marks=4, status="scheduled",
        questions_json=[
            {"text": "What is twice 6?", "type": "short", "marks": 2, "competency": "AU", "correct_answer": "12",
             "kc_mappings": [{"kc_id": concept_id, "relevance": 1}]},
            {"text": "Explain doubling.", "type": "short", "marks": 2, "competency": "CU", "correct_answer": "x2"},
        ],
    ))
    await db_session.commit()
    headers = {"Authorization": f"Bearer {teacher_token}"}

    async def publish(first, second):
        response = await client.post(f"/api/v1/assessments/{paper_id}/grade", headers=headers, json={
            "student_id": student_id, "items": [
                {"question_index": 1, "awarded_marks": first}, {"question_index": 2, "awarded_marks": second}]})
        assert response.status_code == 200, response.text

    await publish(1, 2)
    db_session.expire_all()
    attempts = list((await db_session.scalars(select(StudentKcAttempt).where(
        StudentKcAttempt.student_id == student_id, StudentKcAttempt.assessment_id == paper_id))).all())
    assert [(a.question_id, a.kc_id, a.score, a.competency) for a in attempts] == [("1", concept_id, 50.0, "AU")]
    # a corrected grade replaces the earlier row instead of adding a second one
    await publish(2, 2)
    db_session.expire_all()
    attempts = list((await db_session.scalars(select(StudentKcAttempt).where(
        StudentKcAttempt.student_id == student_id, StudentKcAttempt.assessment_id == paper_id))).all())
    assert [(a.question_id, a.score) for a in attempts] == [("1", 100.0)]
    mastery = await db_session.scalar(select(StudentKcMastery).where(
        StudentKcMastery.student_id == student_id, StudentKcMastery.kc_id == concept_id))
    assert mastery.au_mastery == 100.0 and mastery.attempt_count == 1


@pytest.mark.asyncio
async def test_reviewed_online_quiz_updates_the_graph(client, learning, db_session, monkeypatch):  # noqa: F811
    monkeypatch.setattr(kc_graph_service, "get_ai_provider", _no_model)
    monkeypatch.setattr(kc_graph_service, "QwenTextProvider", _no_model)
    l = learning
    concept = await kc_graph_service.create_component(
        db_session, name=f"Addition {uuid.uuid4().hex[:6]}", description="", subject_id=l.subject, topic="Number")
    concept_id = concept.id
    await db_session.commit()
    paper = await assessment(client, l)
    stored = await db_session.get(Assessment, paper["id"])
    questions = [dict(q) for q in stored.questions_json]
    questions[0]["kc_mappings"] = [{"kc_id": concept_id, "relevance": 1}]  # only the first question is linked
    stored.questions_json = questions
    await db_session.commit()
    result = (await client.post(f"/api/v1/assessments/{paper['id']}/answers", headers=l.headers["student"], json=answers())).json()
    reviewed = await client.post(f"/api/v1/assessments/results/{result['id']}/review", headers=l.headers["teacher"], json=review(result))
    assert reviewed.status_code == 200, reviewed.text
    db_session.expire_all()
    attempts = list((await db_session.scalars(select(StudentKcAttempt).where(
        StudentKcAttempt.student_id == l.student, StudentKcAttempt.assessment_id == paper["id"]))).all())
    assert [(a.question_id, a.kc_id, a.score, a.source_key) for a in attempts] == [
        ("1", concept_id, 100.0, f"assessment-result:{result['id']}")]
