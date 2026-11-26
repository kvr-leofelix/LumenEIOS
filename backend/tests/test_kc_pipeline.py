"""Published question mappings, OCR updates, and the two recommendation levels."""
import json

import pytest
from sqlalchemy import func, select

from backend.app.models.entities import (
    Assessment,
    AssignmentOcrUpload,
    ClassSection,
    QuestionBankItem,
    Student,
    StudentOcrHistory,
)
from backend.app.models.knowledge_components import (
    QuestionBankKcMapping,
    QuestionKcMapping,
    StudentKcAttempt,
    StudentKcMastery,
)
from backend.app.services import kc_graph_service
from backend.app.services.kc_recommendation_service import allocate_question_counts, concept_band, practice_kind
from backend.app.api.v1 import ocr as ocr_api


@pytest.mark.asyncio
async def test_teacher_sees_one_students_concept_analysis(client, db_session, teacher_token, student_token):
    teacher = {"Authorization": f"Bearer {teacher_token}"}
    created = await client.post("/api/v1/knowledge-components", headers=teacher, json={
        "name": "Homework fractions",
        "description": "Used by differentiated homework.",
        "subject_id": "sub-math",
        "topic": "Homework analysis",
    })
    assert created.status_code == 201, created.text
    kc_id = created.json()["id"]
    untouched = await client.post("/api/v1/knowledge-components", headers=teacher, json={
        "name": "Homework untouched",
        "description": "No marks yet.",
        "subject_id": "sub-math",
        "topic": "Homework analysis",
    })
    assert untouched.status_code == 201, untouched.text
    db_session.add(StudentKcMastery(
        student_id="user-student-1",
        kc_id=kc_id,
        lu_mastery=32,
        overall_mastery=32,
        attempt_count=2,
        correct_count=0,
        incorrect_count=2,
        learning_status="needs_improvement",
    ))
    await db_session.commit()

    analysis = await client.get("/api/v1/knowledge-components/student-analysis", headers=teacher, params={
        "student_id": "user-student-1",
        "subject_id": "sub-math",
    })
    assert analysis.status_code == 200, analysis.text
    body = analysis.json()
    by_name = {item["name"]: item for item in body["concepts"]}
    assert by_name["Homework fractions"]["overall_mastery"] == 32
    assert by_name["Homework fractions"]["learning_status"] == "needs_improvement"
    assert by_name["Homework untouched"]["overall_mastery"] is None
    assert by_name["Homework untouched"]["learning_status"] == "not_assessed"
    assert (await client.get(
        "/api/v1/knowledge-components/student-analysis",
        headers={"Authorization": f"Bearer {student_token}"},
        params={"student_id": "user-student-1", "subject_id": "sub-math"},
    )).status_code == 403


def test_bands_and_allocation_ignore_missing_evidence():
    assert concept_band({"average_mastery": None, "student_count": 0, "needs_improvement_count": 0}) == "insufficient"
    assert concept_band({"average_mastery": 40, "student_count": 3, "needs_improvement_count": 2}) == "weak"
    assert concept_band({"average_mastery": 61, "student_count": 3, "needs_improvement_count": 1}) == "moderate"
    assert concept_band({"average_mastery": 88, "student_count": 3, "needs_improvement_count": 0}) == "strong"
    assert practice_kind(None, 0) == "diagnostic"
    assert practice_kind(30, 2) == "foundational"
    assert practice_kind(62, 1) == "practice"
    assert practice_kind(90, 1) == "application"
    counts = allocate_question_counts([("compare", "weak"), ("identify", "moderate"), ("generate", "moderate")], 4)
    assert counts["compare"] >= counts["identify"]
    assert sum(counts.values()) == 4


@pytest.mark.asyncio
async def test_published_mapping_is_what_ocr_updates(client, db_session, monkeypatch, teacher_token):
    teacher = {"Authorization": f"Bearer {teacher_token}"}
    created = {}
    for name in ("Identify a unit", "Scale both terms", "Unrelated remainder"):
        response = await client.post("/api/v1/knowledge-components", headers=teacher, json={
            "name": name, "description": name, "subject_id": "sub-math", "topic": "Pipeline fractions",
        })
        assert response.status_code == 201, response.text
        created[name] = response.json()["id"]

    db_session.add(QuestionBankItem(
        id="bank-pipeline-generate", school_id="school-1", subject_id="sub-math",
        text="Find an equivalent fraction of 2/3 with denominator 12.",
        type="short", correct_answer="8/12", marking_rubric="Multiply by 4.",
        marks=2, competency="CU", bloom_level="Apply",
    ))
    await db_session.commit()

    paper = await client.post("/api/v1/classes/class-8a/assessments", headers=teacher, json={
        "title": "Fraction mapping paper",
        "subject_id": "sub-math",
        "date": "2026-11-19",
        "total_marks": 4,
        "competency_focus": ["CU", "AU"],
        "questions": [
            {
                "id": "bank-pipeline-generate",
                "text": "Find an equivalent fraction of 2/3 with denominator 12.",
                "type": "short",
                "marks": 2,
                "competency": "CU",
                "bloom_level": "Apply",
                "correct_answer": "8/12",
                "marking_rubric": "Multiply by 4.",
                "kc_mappings": [
                    {"kc_id": created["Scale both terms"], "relevance": 0.7},
                    {"kc_id": created["Identify a unit"], "relevance": 0.3},
                ],
            },
            {
                "text": "What is 1/2 of 10?",
                "type": "short",
                "marks": 2,
                "competency": "AU",
                "bloom_level": "Apply",
                "correct_answer": "5",
                "marking_rubric": "Half of 10 is 5.",
                "kc_mappings": [],
            },
        ],
    })
    assert paper.status_code == 201, paper.text
    assessment_id = paper.json()["id"]
    rejected = await client.post("/api/v1/classes/class-8a/assessments", headers=teacher, json={
        "title": "Bad mapping",
        "subject_id": "sub-math",
        "date": "2026-11-19",
        "total_marks": 2,
        "competency_focus": ["LU"],
        "questions": [{
            "text": "Name a fraction.",
            "type": "short",
            "marks": 2,
            "competency": "LU",
            "bloom_level": "Remember",
            "correct_answer": "1/2",
            "marking_rubric": "Any fraction.",
            "kc_mappings": [{"kc_id": "not-a-real-kc", "relevance": 1}],
        }],
    })
    assert rejected.status_code == 422

    db_session.add(QuestionBankKcMapping(
        question_bank_item_id="bank-pipeline-generate",
        kc_id=created["Unrelated remainder"],
        relevance=1,
    ))
    db_session.add(StudentOcrHistory(
        id="hist-pipeline-1", student_id="user-student-1", file_name="fractions.png",
        extracted_text="8/12 and 5", pages_processed=1,
    ))
    db_session.add(AssignmentOcrUpload(history_id="hist-pipeline-1", assessment_id=assessment_id))
    db_session.add(StudentOcrHistory(
        id="hist-pipeline-unclear", student_id="user-student-1", file_name="blur.png",
        extracted_text="[unclear]", pages_processed=1,
    ))
    db_session.add(AssignmentOcrUpload(history_id="hist-pipeline-unclear", assessment_id=assessment_id))
    await db_session.commit()

    class FakeProvider:
        mapping_calls = 0

        async def generate_json(self, *, system, prompt, schema):
            if schema.__name__ == "KcMappingResponse":
                self.mapping_calls += 1
                raise AssertionError("A published mapping must not ask the model for new ids.")
            unclear = "[unclear]" in prompt
            if unclear:
                return json.dumps({
                    "question_evaluations": [
                        {
                            "question_id": "1", "question_index": 1,
                            "question_text": "Find an equivalent fraction of 2/3 with denominator 12.",
                            "competency": "CU", "max_marks": 2, "awarded_marks": 0, "competency_score": 0,
                            "student_answer_extracted": "[unclear]", "status": "attempted",
                        },
                        {
                            "question_id": "2", "question_index": 2, "question_text": "What is 1/2 of 10?",
                            "competency": "AU", "max_marks": 2, "awarded_marks": 0, "competency_score": 0,
                            "student_answer_extracted": "[unclear]", "status": "attempted",
                        },
                    ],
                    "scoring_summary": {"total_marks_obtained": 0, "max_possible_marks": 4, "percentage": 0},
                })
            return json.dumps({
                "question_evaluations": [
                    {
                        "question_id": "1", "question_index": 1,
                        "question_text": "Find an equivalent fraction of 2/3 with denominator 12.",
                        "competency": "CU", "max_marks": 2, "awarded_marks": 1, "competency_score": 50,
                        "student_answer_extracted": "4/12", "status": "attempted",
                    },
                    {
                        "question_id": "2", "question_index": 2, "question_text": "What is 1/2 of 10?",
                        "competency": "AU", "max_marks": 2, "awarded_marks": 2, "competency_score": 100,
                        "student_answer_extracted": "5", "status": "attempted",
                    },
                ],
                "scoring_summary": {"total_marks_obtained": 3, "max_possible_marks": 4, "percentage": 75},
            })

    provider = FakeProvider()
    monkeypatch.setattr(ocr_api, "get_ai_provider", lambda: provider)
    monkeypatch.setattr(kc_graph_service, "get_ai_provider", lambda: provider)
    # Evaluation defaults to the local Qwen provider; keep this test offline and deterministic.
    monkeypatch.setattr(ocr_api, "QwenTextProvider", lambda: provider)
    monkeypatch.setattr(kc_graph_service, "QwenTextProvider", lambda: provider)

    async def evaluate(text, history_id=None):
        body = {"assessment_id": assessment_id, "extracted_text": text}
        if history_id:
            body["history_id"] = history_id
        return await client.post("/api/v1/ocr/evaluate-scan", headers=teacher, json=body)

    first = await evaluate("8/12 and 5", "hist-pipeline-1")
    assert first.status_code == 200, first.text
    second = await evaluate("8/12 and 5", "hist-pipeline-1")
    assert second.status_code == 200, second.text
    unclear = await evaluate("[unclear]", "hist-pipeline-unclear")
    assert unclear.status_code == 200, unclear.text
    assert provider.mapping_calls == 0

    await db_session.rollback()
    attempts = list((await db_session.scalars(
        select(StudentKcAttempt).where(StudentKcAttempt.assessment_id == assessment_id)
    )).all())
    assert {(row.kc_id, row.question_id) for row in attempts} == {
        (created["Scale both terms"], "1"),
        (created["Identify a unit"], "1"),
    }
    weights = {row.kc_id: row.relevance for row in attempts}
    assert weights[created["Scale both terms"]] == 0.7
    assert weights[created["Identify a unit"]] == 0.3
    assert all(row.score == 50 for row in attempts)
    mastery = list((await db_session.scalars(
        select(StudentKcMastery).where(StudentKcMastery.kc_id.in_(created.values()))
    )).all())
    by_kc = {row.kc_id: row for row in mastery}
    assert created["Unrelated remainder"] not in by_kc
    assert by_kc[created["Scale both terms"]].attempt_count == 1
    stored = list((await db_session.scalars(
        select(QuestionKcMapping).where(QuestionKcMapping.assessment_id == assessment_id)
    )).all())
    assert {row.kc_id for row in stored} == {created["Scale both terms"], created["Identify a unit"]}
    assert await db_session.scalar(select(func.count()).select_from(Assessment).where(Assessment.title == "Bad mapping")) == 0


@pytest.mark.asyncio
async def test_fraction_sample_separates_student_and_class_recommendations(client, db_session, teacher_token, student_token):
    db_session.add(ClassSection(
        id="class-6-fractions",
        school_id="school-1",
        grade=6,
        section="A",
        name="Class 6-A",
        class_teacher_id="user-teacher-1",
        class_teacher_name="Vikram Sengupta",
        student_count=3,
        subject_ids_json=["sub-math"],
    ))
    await db_session.commit()
    teacher = {"Authorization": f"Bearer {teacher_token}"}
    loaded = await client.post("/api/v1/knowledge-components/sample-fractions", headers=teacher)
    assert loaded.status_code == 200, loaded.text
    body = loaded.json()
    assert "not an official NCERT" in body["source_reference"]
    by_profile = {student["profile"]: student for student in body["students"]}
    assert {item["kind"] for item in by_profile["strong"]["recommendations"]} == {"application"}
    assert "practice" in {item["kind"] for item in by_profile["partial"]["recommendations"]}
    assert "foundational" in {item["kind"] for item in by_profile["weak"]["recommendations"]}
    assert "application" not in {item["kind"] for item in by_profile["weak"]["recommendations"]}
    assert by_profile["strong"]["recommendations"][0]["question"]["text"]

    again = await client.post("/api/v1/knowledge-components/sample-fractions", headers=teacher)
    assert again.status_code == 200, again.text
    await db_session.rollback()
    meera = await db_session.scalar(
        select(StudentKcMastery).where(
            StudentKcMastery.student_id == "demo-fraction-meera",
            StudentKcMastery.overall_mastery >= 75,
        )
    )
    assert meera is not None
    meera_attempts = await db_session.scalar(
        select(func.count()).select_from(StudentKcAttempt).where(StudentKcAttempt.student_id == "demo-fraction-meera")
    )
    assert meera_attempts == 4

    db_session.add(Student(
        id="demo-fraction-rohan", school_id="school-1", class_id="class-6-fractions",
        class_name="Class 6-A", name="Demo Rohan", roll_no=34,
    ))
    await db_session.commit()
    blueprint = await client.post("/api/v1/knowledge-components/class-blueprint", headers=teacher, json={
        "class_id": "class-6-fractions",
        "subject_id": "sub-math",
        "total_marks": 8,
        "question_count": 4,
        "duration_minutes": 30,
        "topic": "Fractions",
    })
    assert blueprint.status_code == 200, blueprint.text
    report = blueprint.json()
    assert report["students_without_evidence"] == 1
    concepts = {item["name"]: item for item in report["concepts"]}
    assert concepts["Compare equivalent fractions"]["band"] == "weak"
    assert concepts["Compare equivalent fractions"]["average_mastery"] != 0
    assert concepts["Fraction of a quantity"]["band"] == "insufficient"
    assert concepts["Fraction of a quantity"]["average_mastery"] is None
    compare_slots = [slot for slot in report["slots"] if slot["kc_name"] == "Compare equivalent fractions"]
    assert compare_slots
    assert compare_slots[0]["difficulty"] == "foundational"
    assert "revision" in compare_slots[0]["reason"] or "foundational" in compare_slots[0]["reason"]

    narrowed = await client.post("/api/v1/knowledge-components/class-blueprint", headers=teacher, json={
        "class_id": "class-6-fractions",
        "subject_id": "sub-math",
        "total_marks": 4,
        "question_count": 1,
        "duration_minutes": 20,
        "slots": [{
            "kc_id": concepts["Identify a fraction"]["id"],
            "include": True,
            "question_count": 1,
            "difficulty": "standard",
        }],
    })
    assert narrowed.status_code == 200, narrowed.text
    assert [slot["kc_name"] for slot in narrowed.json()["slots"]] == ["Identify a fraction"]
    assert (await client.post(
        "/api/v1/knowledge-components/class-blueprint",
        headers={"Authorization": f"Bearer {student_token}"},
        json={"class_id": "class-6-fractions", "subject_id": "sub-math"},
    )).status_code == 403
