"""Differentiated Homework topic filter: teachers choose which chapter(s) homework comes from."""
from __future__ import annotations

import pytest
from sqlalchemy import delete

from backend.app.models.entities import QuestionBankItem, Subject
from backend.tests.test_homework_legacy_security import auth, uid, world  # noqa: F401  (fixture)


@pytest.mark.asyncio
async def test_teacher_limits_homework_to_chosen_topics(client, world, db_session):
    student = world["students"][0]
    subject = Subject(id=world["subject"], name="Topic Maths", code=uid(), grade=8)
    world["classes"][0].subject_ids_json = [subject.id]
    db_session.add(subject)
    await db_session.commit()
    teacher = auth(world["users"]["teacher"])

    async def call(method, path, body=None, code=200):
        response = await client.request(method, "/api/v1" + path, json=body, headers=teacher)
        assert response.status_code == code, response.text
        return response.json()

    created = []
    try:
        for topic, competency in [("Mensuration", "LU"), ("  mensuration ", "CU"), ("Algebra", "LU"), ("Algebra", "AU")]:
            q = await call("POST", "/assessments/question-bank", {
                "subject_id": subject.id, "type": "short", "text": f"{topic.strip()} question {uid()}",
                "correct_answer": "answer", "marking_rubric": "1 mark", "marks": 1,
                "competency": competency, "bloom_level": "Apply", "topic": topic,
            }, code=201)
            created.append(q["id"])
        assert q["topic"] == "Algebra"

        topics = await call("GET", f"/assessments/question-bank/topics?subject_id={subject.id}")
        names = {t["topic"].casefold(): t for t in topics["topics"]}
        assert names["mensuration"]["count"] == 2          # case/space variants are one topic
        assert names["algebra"]["by_competency"] == {"LU": 1, "AU": 1}
        assert topics["untagged"] >= 1                      # the fixture's untagged question

        request = {"subject_id": subject.id, "max_questions": 10, "include_ai_generated": False,
                   "topics": ["MENSURATION"]}
        preview = await call("POST", f"/students/{student.id}/homework/preview", request)
        assert preview["question_count"] == 2
        assert {item["question_id"] for item in preview["items"]} == set(created[:2])
        assert any("Limited to topic(s): MENSURATION" in note for note in preview["notes"])

        everything = await call("POST", f"/students/{student.id}/homework/preview",
                                {**request, "topics": []})
        assert everything["question_count"] >= 4            # no filter = whole subject, as before

        draft = await call("POST", f"/students/{student.id}/homework/drafts",
                           {**request, "expected_question_ids": [i["question_id"] for i in preview["items"]]}, code=201)
        assert draft["question_count"] == 2

        # Retag and clear a topic through the edit endpoint.
        edited = await call("PUT", f"/assessments/questions/{created[2]}", {"topic": "Geometry"})
        assert edited["topic"] == "Geometry"
        cleared = await call("PUT", f"/assessments/questions/{created[2]}", {"topic": ""})
        assert cleared["topic"] is None
    finally:
        await db_session.execute(delete(QuestionBankItem).where(QuestionBankItem.id.in_(created)))
        await db_session.execute(delete(Subject).where(Subject.id == subject.id))
        await db_session.commit()


@pytest.mark.asyncio
async def test_topic_filter_is_bounded(client, world):
    response = await client.post(
        f"/api/v1/students/{world['students'][0].id}/homework/preview",
        json={"subject_id": world["subject"], "max_questions": 1, "include_ai_generated": False,
              "topics": [f"t{i}" for i in range(21)]},
        headers=auth(world["users"]["teacher"]),
    )
    assert response.status_code == 422
