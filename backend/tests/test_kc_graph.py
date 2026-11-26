import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from backend.app.core.security import create_access_token
from backend.app.models.entities import Assessment, AssignmentOcrUpload, StudentOcrHistory, User, utc_now
from backend.app.models.knowledge_components import StudentKcAttempt, StudentKcMastery
from backend.app.modules.differentiated_homework.models import StudentAccountLink
from backend.app.services.evaluation_service import parse_and_validate_evaluation
from backend.app.services.kc_graph_service import (
    KcMappingResponse,
    _accepted_links,
    evaluation_is_reliable,
    latest_and_previous,
    mastery_from_attempts,
    question_concept_labels,
    recommendations_for,
)
from backend.app.services import kc_graph_service
from backend.app.services.kc_demo_walkthrough import paper_for
from backend.app.api.v1 import ocr as ocr_api


def _attempt(competency, score, relevance=1, days_ago=0):
    return SimpleNamespace(
        competency=competency,
        score=score,
        relevance=relevance,
        assessed_at=utc_now() - timedelta(days=days_ago),
    )


def test_mastery_keeps_dimensions_separate_and_uses_equal_weights():
    now = utc_now()
    summary = mastery_from_attempts([
        _attempt("LU", 80),
        _attempt("CU", 40),
    ], now)
    assert summary["lu"] == 80
    assert summary["cu"] == 40
    assert summary["ct"] is None
    assert summary["au"] is None
    assert summary["overall"] == 60
    assert summary["learning_status"] == "developing"


def test_mastery_weights_recency_relevance_and_partial_scores():
    now = utc_now()
    faded = mastery_from_attempts([
        _attempt("AU", 100, days_ago=60),
        _attempt("AU", 0, days_ago=0),
    ], now)
    assert faded["au"] == 20

    weighted = mastery_from_attempts([
        _attempt("CU", 100, relevance=0.5),
        _attempt("CU", 0, relevance=1),
    ], now)
    assert weighted["cu"] == 33.3
    assert weighted["learning_status"] == "needs_improvement"


def test_recommendations_use_only_assessed_evidence():
    assert recommendations_for("Chain Rule", {"lu": 40, "cu": 35, "ct": None, "au": None}, []) == [
        "Strengthen foundational understanding of Chain Rule before taking on new problems.",
    ]
    assert recommendations_for("Chain Rule", {"lu": 85, "cu": 80, "ct": 45, "au": None}, []) == [
        "Practice reasoning-based exercises on Chain Rule.",
    ]
    assert recommendations_for("Chain Rule", {"lu": 85, "cu": 80, "ct": 80, "au": 30}, []) == [
        "Practice applying Chain Rule in new situations.",
    ]
    assert recommendations_for("Chain Rule", {"lu": 40, "cu": 40, "ct": None, "au": None}, [("Limits", None)]) == [
        "Strengthen foundational understanding of Chain Rule before taking on new problems.",
    ]
    revisited = recommendations_for("Chain Rule", {"lu": 80, "cu": 80, "ct": 80, "au": 80}, [("Limits", 30)])
    assert revisited == ["Revisit Limits before advancing in Chain Rule."]


def test_unknown_component_ids_are_dropped_and_duplicates_collapse():
    raw = KcMappingResponse.model_validate({
        "questions": [{
            "question_id": "1",
            "components": [
                {"id": "kc-chain", "relevance": 0.4},
                {"id": "kc-chain", "relevance": 0.9},
                {"id": "made-up", "relevance": 1},
                {"id": "kc-zero", "relevance": 0},
            ],
        }],
    })
    assert _accepted_links(raw, {"kc-chain", "kc-zero"}) == {"1": [("kc-chain", 0.9)]}


def test_unclear_ocr_is_not_a_reliable_evaluation():
    result = parse_and_validate_evaluation(json.dumps({
        "question_evaluations": [{
            "question_index": 1, "question_id": "1", "question_text": "Differentiate sin(x^2).",
            "competency": "CU", "max_marks": 2, "awarded_marks": 2, "competency_score": 90,
            "student_answer_extracted": "2x cos(x^2) [unclear]", "status": "attempted",
        }],
        "scoring_summary": {"total_marks_obtained": 2, "max_possible_marks": 2, "percentage": 100},
    }))
    assert result.question_evaluations[0].flag_for_review
    assert evaluation_is_reliable(result) is False
    latest, previous = latest_and_previous([
        _attempt("LU", 50, days_ago=2),
        _attempt("LU", 70, days_ago=0),
    ])
    assert latest["LU"] == 70
    assert previous["LU"] == 50
    assert latest["AU"] is None


@pytest.mark.asyncio
async def test_evaluation_updates_only_the_linked_student_graph(client, db_session, monkeypatch, teacher_token, student_token):
    db_session.add(User(
        id="user-ananya-kc", email="ananya-kc@example.com", name="Ananya Patel",
        hashed_password="not-used", role="student", school_id="school-1",
    ))
    db_session.add(StudentAccountLink(user_id="user-ananya-kc", student_id="student-ananya", created_by="user-admin"))
    db_session.add(Assessment(
        id="kc-eval-paper", school_id="school-1", class_id="class-8a", subject_id="sub-math",
        title="Chain rule", date="2026-11-14", total_marks=4, status="scheduled",
        questions_json=[
            {
                "text": "State what the chain rule is.", "type": "short", "marks": 2, "competency": "LU",
                "correctAnswer": "A derivative of a composition.", "markingRubric": "Credit the composition statement.",
            },
            {
                "text": "Differentiate sin(x^2).", "type": "short", "marks": 2, "competency": "CU",
                "correctAnswer": "2x cos(x^2)", "markingRubric": "Credit the chain rule.",
            },
        ],
    ))
    db_session.add(StudentOcrHistory(
        id="hist-kc-1", student_id="user-student-1", file_name="sheet.png",
        extracted_text="Q1 chain rule. Q2 2x cos(x^2)", pages_processed=1,
    ))
    db_session.add(AssignmentOcrUpload(history_id="hist-kc-1", assessment_id="kc-eval-paper"))
    db_session.add(StudentOcrHistory(
        id="hist-kc-unclear", student_id="user-student-1", file_name="blur.png",
        extracted_text="Q1 [unclear]", pages_processed=1,
    ))
    db_session.add(AssignmentOcrUpload(history_id="hist-kc-unclear", assessment_id="kc-eval-paper"))
    await db_session.commit()

    teacher = {"Authorization": f"Bearer {teacher_token}"}
    created = {}
    for name, topic in (("Limits", "Calculus"), ("Chain Rule", "Calculus"), ("Differentiation", "Calculus")):
        response = await client.post("/api/v1/knowledge-components", headers=teacher, json={
            "name": name, "description": f"{name} in calculus.", "subject_id": "sub-math", "topic": topic,
        })
        assert response.status_code == 201, response.text
        created[name] = response.json()["id"]
    duplicate = await client.post("/api/v1/knowledge-components", headers=teacher, json={
        "name": " chain   rule ", "description": "same", "subject_id": "sub-math", "topic": "Calculus",
    })
    assert duplicate.status_code == 409
    edge = await client.post("/api/v1/knowledge-components/relationships", headers=teacher, json={
        "source_id": created["Limits"], "target_id": created["Chain Rule"], "relationship": "PREREQUISITE_OF",
    })
    assert edge.status_code == 201, edge.text
    listed = await client.get(
        "/api/v1/knowledge-components/relationships", headers=teacher, params={"subject_id": "sub-math"},
    )
    assert listed.status_code == 200, listed.text
    assert any(
        item["source_id"] == created["Limits"] and item["relationship"] == "PREREQUISITE_OF"
        for item in listed.json()
    )
    assert (await client.get(
        "/api/v1/knowledge-components/relationships",
        headers={"Authorization": f"Bearer {student_token}"},
    )).status_code == 403
    cycle = await client.post("/api/v1/knowledge-components/relationships", headers=teacher, json={
        "source_id": created["Chain Rule"], "target_id": created["Limits"], "relationship": "PREREQUISITE_OF",
    })
    assert cycle.status_code == 422
    self_edge = await client.post("/api/v1/knowledge-components/relationships", headers=teacher, json={
        "source_id": created["Limits"], "target_id": created["Limits"], "relationship": "RELATED_TO",
    })
    assert self_edge.status_code == 422
    missing = await client.post("/api/v1/knowledge-components/relationships", headers=teacher, json={
        "source_id": created["Limits"], "target_id": "does-not-exist", "relationship": "PART_OF",
    })
    assert missing.status_code == 404
    assert (await client.post(
        "/api/v1/knowledge-components", headers={"Authorization": f"Bearer {student_token}"},
        json={"name": "Limits", "subject_id": "sub-math", "topic": "Calculus"},
    )).status_code == 403

    class FakeProvider:
        mapping_calls = 0

        async def generate_json(self, *, system, prompt, schema):
            if schema.__name__ == "KcMappingResponse":
                self.mapping_calls += 1
                return json.dumps({"questions": [
                    {"question_id": "1", "components": [
                        {"id": created["Chain Rule"], "relevance": 1},
                        {"id": created["Differentiation"], "relevance": 0.5},
                        {"id": "not-a-real-component", "relevance": 1},
                    ]},
                    {"question_id": "2", "components": [
                        {"id": created["Chain Rule"], "relevance": 1},
                        {"id": created["Limits"], "relevance": 1},
                    ]},
                ]})
            assert "State what the chain rule is." in prompt
            unclear = "Q1 [unclear]" in prompt
            return json.dumps({
                "question_evaluations": [
                    {
                        "question_id": "1", "question_index": 1, "question_text": "State what the chain rule is.",
                        "competency": "LU", "max_marks": 2, "awarded_marks": 0 if unclear else 1,
                        "competency_score": 10 if unclear else 40,
                        "student_answer_extracted": "[unclear]" if unclear else "derivative of a composition",
                        "status": "attempted",
                    },
                    {
                        "question_id": "2", "question_index": 2, "question_text": "Differentiate sin(x^2).",
                        "competency": "CU", "max_marks": 2, "awarded_marks": 0,
                        "competency_score": 30,
                        "student_answer_extracted": "[unclear]" if unclear else "2x cos(x^2)",
                        "status": "attempted",
                    },
                ],
                "scoring_summary": {"total_marks_obtained": 1, "max_possible_marks": 4, "percentage": 25},
            })

    provider = FakeProvider()
    monkeypatch.setattr(ocr_api, "get_ai_provider", lambda: provider)
    monkeypatch.setattr(kc_graph_service, "get_ai_provider", lambda: provider)

    async def evaluate(text):
        return await client.post("/api/v1/ocr/evaluate-scan", headers=teacher, json={
            "assessment_id": "kc-eval-paper", "extracted_text": text, "provider": "gemini",
        })

    first = await evaluate("Q1 chain rule. Q2 2x cos(x^2)")
    assert first.status_code == 200, first.text
    assert first.json()["scoring_summary"]["competency_scores"]["LU"] == 40
    assert first.json()["scoring_summary"]["competency_scores"]["CU"] == 30
    second = await evaluate("Q1 chain rule. Q2 2x cos(x^2)")
    assert second.status_code == 200, second.text
    unclear = await evaluate("Q1 [unclear]")
    assert unclear.status_code == 200, unclear.text
    assert provider.mapping_calls == 1

    await db_session.rollback()
    attempt_count = await db_session.scalar(
        select(func.count()).select_from(StudentKcAttempt).where(StudentKcAttempt.assessment_id == "kc-eval-paper")
    )
    assert attempt_count == 4

    graph = await client.get("/api/v1/students/me/knowledge-graph", headers={"Authorization": f"Bearer {student_token}"})
    assert graph.status_code == 200, graph.text
    by_name = {node["name"]: node for node in graph.json()["nodes"]}
    assert {"Chain Rule", "Differentiation", "Limits"} <= set(by_name)
    chain = by_name["Chain Rule"]
    assert chain["lu"] == 40
    assert chain["cu"] == 30
    assert chain["ct"] is None
    assert chain["au"] is None
    assert chain["overall_mastery"] == 35
    assert chain["learning_status"] == "needs_improvement"
    assert chain["attempt_count"] == 2
    assert chain["correct_count"] == 1
    assert chain["incorrect_count"] == 1
    assert chain["latest"]["LU"] == 40
    assert chain["previous"]["LU"] is None
    assert len(chain["history"]) == 2
    assert any(item["name"] == "Limits" for item in chain["prerequisites"])
    assert any(note.startswith("Strengthen foundational understanding") for note in chain["recommendations"])
    assert any(note.startswith("Revisit Limits") for note in chain["recommendations"])
    assert by_name["Limits"]["cu"] == 30
    assert by_name["Limits"]["lu"] is None
    assert by_name["Differentiation"]["recommendations"] == []
    assert by_name["Differentiation"]["lu"] == 40
    assert by_name["Differentiation"]["cu"] is None

    ananya = create_access_token("user-ananya-kc", school_id="school-1", role="student")
    other = await client.get(
        "/api/v1/students/me/knowledge-graph?student_id=user-student-1",
        headers={"Authorization": f"Bearer {ananya}"},
    )
    assert other.status_code == 200, other.text
    ananya_nodes = {node["name"]: node for node in other.json()["nodes"]}
    assert ananya_nodes["Chain Rule"]["lu"] is None
    assert ananya_nodes["Chain Rule"]["attempt_count"] == 0
    assert ananya_nodes["Chain Rule"]["learning_status"] == "not_assessed"
    assert (await client.get("/api/v1/students/me/knowledge-graph", headers=teacher)).status_code == 403


@pytest.mark.asyncio
async def test_sample_walkthrough_updates_the_student_persona(client, db_session, teacher_token, student_token):
    teacher = {"Authorization": f"Bearer {teacher_token}"}
    student = {"Authorization": f"Bearer {student_token}"}
    old = await client.post("/api/v1/knowledge-components", headers=teacher, json={
        "name": "Expressions", "description": "An older sample.", "subject_id": "sub-math", "topic": "Legacy",
    })
    assert old.status_code == 201, old.text

    preview = await client.get(
        "/api/v1/knowledge-components/demo-walkthrough", headers=teacher, params={"subject_id": "sub-math"},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["evaluated"] is False
    paper = await db_session.get(Assessment, "demo-kc-sub-math")
    await db_session.refresh(paper)
    first = paper.questions_json[0]
    assert first["correct_answer"].strip()
    assert first["marks"] > 0
    assert first["competency"] in {"LU", "CU", "AU", "CT"}
    preview_names = [node["name"] for node in preview.json()["graph"]["nodes"]]
    assert preview_names.count("Expressions") == 1
    assert any(node["name"] == "Units" and node["learning_status"] == "not_assessed" for node in preview.json()["graph"]["nodes"])

    marked = await client.post(
        "/api/v1/knowledge-components/demo-walkthrough", headers=teacher, params={"subject_id": "sub-math"},
    )
    assert marked.status_code == 200, marked.text
    body = marked.json()
    by_name = {node["name"]: node for node in body["graph"]["nodes"]}
    assert by_name["Number line"]["learning_status"] == "proficient"
    assert by_name["Expressions"]["learning_status"] == "needs_improvement"
    assert by_name["Units"]["learning_status"] == "not_assessed"
    assert any(note.startswith("Revisit Expressions") for note in by_name["Equations"]["recommendations"])
    assert body["percentage"] is not None

    again = await client.post(
        "/api/v1/knowledge-components/demo-walkthrough", headers=teacher, params={"subject_id": "sub-math"},
    )
    again_by = {node["name"]: node for node in again.json()["graph"]["nodes"]}
    assert again_by["Expressions"]["attempt_count"] == by_name["Expressions"]["attempt_count"]

    visible = await client.get("/api/v1/students/me/knowledge-graph", headers=student)
    student_nodes = {node["name"]: node for node in visible.json()["nodes"]}
    assert student_nodes["Number line"]["learning_status"] == "proficient"
    assert student_nodes["Units"]["learning_status"] == "not_assessed"
    assert (await client.post(
        "/api/v1/knowledge-components/demo-walkthrough",
        headers=student,
        params={"subject_id": "sub-math"},
    )).status_code == 403


@pytest.mark.asyncio
async def test_ocr_evaluation_marks_the_sample_paper(client, monkeypatch, teacher_token):
    teacher = {"Authorization": f"Bearer {teacher_token}"}
    preview = await client.get(
        "/api/v1/knowledge-components/demo-walkthrough", headers=teacher, params={"subject_id": "sub-math"},
    )
    assert preview.status_code == 200, preview.text
    paper = paper_for("Mathematics")

    class FakeProvider:
        async def generate_json(self, *, system, prompt, schema):
            if schema.__name__ == "KcMappingResponse":
                return json.dumps({"questions": []})
            evaluations = [
                {
                    "question_id": str(index),
                    "question_index": index,
                    "question_text": item["text"],
                    "competency": item["competency"],
                    "max_marks": 2,
                    "awarded_marks": item["awarded"],
                    "competency_score": item["score"],
                    "student_answer_extracted": item["answer"],
                    "status": "attempted",
                    "feedback": "Sample marking.",
                }
                for index, item in enumerate(paper["questions"], start=1)
            ]
            return json.dumps({
                "question_evaluations": evaluations,
                "scoring_summary": {"total_marks_obtained": 1, "max_possible_marks": 14, "percentage": 1},
            })

    monkeypatch.setattr(ocr_api, "QwenTextProvider", lambda: FakeProvider())
    monkeypatch.setattr(kc_graph_service, "QwenTextProvider", lambda: FakeProvider())
    response = await client.post("/api/v1/ocr/evaluate-scan", headers=teacher, json={
        "assessment_id": "demo-kc-sub-math",
        "extracted_text": preview.json()["extracted_text"],
        "provider": "qwen",
        "history_id": "demo-kc-history-sub-math",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["question_evaluations"]) == 7
    assert body["scoring_summary"]["max_possible_marks"] == 14
    assert body["question_evaluations"][0]["awarded_marks"] > 0


@pytest.mark.asyncio
async def test_unlinked_scan_does_not_write_mastery(client, db_session, monkeypatch, teacher_token):
    db_session.add(Assessment(
        id="kc-unlinked-paper", school_id="school-1", class_id="class-8a", subject_id="sub-math",
        title="Unlinked", date="2026-11-14", total_marks=2, status="scheduled",
        questions_json=[{
            "text": "What is twice 6?", "type": "short", "marks": 2, "competency": "AU",
            "correctAnswer": "12", "markingRubric": "Award 2 marks for 12.",
        }],
    ))
    await db_session.commit()

    class FakeProvider:
        async def generate_json(self, *, system, prompt, schema):
            if schema.__name__ == "KcMappingResponse":
                return json.dumps({"questions": []})
            return json.dumps({
                "question_evaluations": [{
                    "question_id": "1", "question_index": 1, "question_text": "What is twice 6?",
                    "competency": "AU", "max_marks": 2, "awarded_marks": 2, "competency_score": 100,
                    "student_answer_extracted": "12", "status": "attempted",
                }],
                "scoring_summary": {"total_marks_obtained": 2, "max_possible_marks": 2, "percentage": 100},
            })

    monkeypatch.setattr(ocr_api, "get_ai_provider", lambda: FakeProvider())
    monkeypatch.setattr(kc_graph_service, "get_ai_provider", lambda: FakeProvider())
    response = await client.post("/api/v1/ocr/evaluate-scan", headers={"Authorization": f"Bearer {teacher_token}"}, json={
        "assessment_id": "kc-unlinked-paper", "extracted_text": "12", "provider": "gemini",
    })
    assert response.status_code == 200, response.text
    await db_session.rollback()
    count = await db_session.scalar(
        select(func.count()).select_from(StudentKcAttempt).where(StudentKcAttempt.assessment_id == "kc-unlinked-paper")
    )
    assert count == 0


def test_question_labels_match_a_whole_concept_name():
    assert question_concept_labels(
        "Use Chemical Bonding to explain a covalent bond.",
        ["Chemical Bonding", "Atom"],
    ) == ["Chemical Bonding"]
    assert question_concept_labels("Copy the class register.", ["Chemical Bonding"]) == []


@pytest.mark.asyncio
async def test_class_evidence_lists_only_assessed_students(client, db_session, teacher_token, student_token):
    teacher = {"Authorization": f"Bearer {teacher_token}"}
    created = await client.post("/api/v1/knowledge-components", headers=teacher, json={
        "name": "Place value", "description": "The value a digit has because of its position.",
        "subject_id": "sub-math", "topic": "Number sense",
    })
    assert created.status_code == 201, created.text
    skipped = await client.post("/api/v1/knowledge-components", headers=teacher, json={
        "name": "Roman numerals", "description": "An older way to write numbers.",
        "subject_id": "sub-math", "topic": "Number sense",
    })
    assert skipped.status_code == 201, skipped.text
    db_session.add(StudentKcMastery(
        student_id="user-student-1",
        kc_id=created.json()["id"],
        lu_mastery=30,
        cu_mastery=40,
        overall_mastery=35,
        learning_status="needs_improvement",
        attempt_count=2,
        correct_count=0,
        incorrect_count=2,
        last_assessed_at=utc_now(),
    ))
    await db_session.commit()

    evidence = await client.get(
        "/api/v1/knowledge-components/class-evidence",
        headers=teacher,
        params={"class_id": "class-8a", "subject_id": "sub-math"},
    )
    assert evidence.status_code == 200, evidence.text
    body = evidence.json()
    place = next(item for item in body["concepts"] if item["name"] == "Place value")
    assert place["needs_improvement_count"] == 1
    assert place["weakest_competency"] == "LU"
    assert place["average_mastery"] == 35
    assert place["students"][0]["student_name"] == "Aarav Patel"
    assert all(item["name"] != "Roman numerals" for item in body["concepts"])
    assert (await client.get(
        "/api/v1/knowledge-components/class-evidence",
        headers={"Authorization": f"Bearer {student_token}"},
        params={"class_id": "class-8a", "subject_id": "sub-math"},
    )).status_code == 403
