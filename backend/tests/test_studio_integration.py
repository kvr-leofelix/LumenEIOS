"""Additional source behavior adapted to KVR's current per-question generation path."""
import json
import pytest
from backend.app.services.llm_service import QwenQuestionStudioService, QwenQuestionStudioInferenceError, parse_studio_questions
from backend.app.services.web_source import WebSource
from backend.tests.test_learnsphere import learning


def test_distribution_reaches_each_generation_slot_and_retains_new_checks(monkeypatch):
    service = QwenQuestionStudioService()
    calls = []
    def checked(subject, mcq, theory, bloom, topic, context, slot, existing, competency=None):
        calls.append((mcq, theory, slot, competency, len(existing)))
        return [{"id":str(slot),"text": "Question " + str(slot),"type":"mcq" if mcq else "short",
                 "competency":competency,"correct_answer":"An answer","marking_rubric":"A rubric"}]
    monkeypatch.setattr(service, "_generate_checked", checked)
    result = service._generate_sync(None,"s","Science",None,None,2,2,"Analyze",None,
        [WebSource("https://example.test/chapter","Chapter","Grounded chapter content.")],
        {"LU":1,"CU":1,"AU":1,"CT":1})
    assert calls == [(1,0,0,"LU",0),(1,0,1,"CU",1),(0,1,2,"AU",2),(0,1,3,"CT",3)]
    assert [q["competency"] for q in result] == ["LU","CU","AU","CT"]
    assert all(q["source_document_names"] == ["https://example.test/chapter"] for q in result)


def test_explicit_competency_is_constrained_and_never_relabelled(monkeypatch):
    service = QwenQuestionStudioService()
    captured = []
    def generate(prompt, **kwargs):
        captured.append((prompt,kwargs["output_schema"]))
        return json.dumps({"theory":[{"text":"Explain the idea.","type":"short","competency":"CU",
            "correct_answer":"A reasoned answer.","marking_rubric":"Explain a relationship."}]})
    monkeypatch.setattr(service,"_generate_text",generate)
    with pytest.raises(ValueError,match="requested primary competency"):
        service._generate_question_batch("Science",0,1,"Analyze",None,"Actual source",competency="CT")
    assert len(captured) == 2
    assert all(schema["properties"]["theory"]["items"]["properties"]["competency"] == {"enum":["CT"]} for _,schema in captured)
    assert "must test CT" in captured[0][0]


def test_short_distribution_batch_is_rejected_instead_of_saved(monkeypatch):
    service = QwenQuestionStudioService()
    monkeypatch.setattr(service,"_generate_checked",lambda *args,**kwargs: [])
    with pytest.raises(QwenQuestionStudioInferenceError,match="no questions were saved"):
        service._generate_sync(None,"s","Science",None,None,1,0,"Analyze",None,
            [WebSource("https://example.test","Chapter","Actual source")],{"LU":1,"CU":0,"AU":0,"CT":0})


def test_duplicate_options_ignore_labels_case_and_spacing():
    raw=json.dumps({"mcqs":[{"type":"mcq","text":"Which value?","options":["A. 3 cm","B.  3  CM","C. 4 cm","D. 5 cm"],
        "correct_answer":"A. 3 cm","marking_rubric":"Use the length.","competency":"AU"}]})
    with pytest.raises(ValueError,match="distinct options"):
        parse_studio_questions(raw,1,0)


@pytest.mark.asyncio
async def test_subject_allocation_authorizes_target_without_class_teacher_role(client, db_session, learning):
    from backend.app.models.entities import TeacherAssignment
    l=learning
    db_session.add(TeacherAssignment(teacher_id=l.users["otherteacher"].id, school_id=l.school, class_id=l.cls, subject_id=l.subject))
    await db_session.commit()
    headers=l.headers["otherteacher"]
    response=await client.get("/api/v1/assessments/targets",headers=headers)
    assert response.status_code==200
    assert l.cls in {item["id"] for item in response.json()}
    created=await client.post(f"/api/v1/classes/{l.cls}/assessments",headers=headers,json={
        "class_id":l.cls,"subject_id":l.subject,"title":"Allocated subject assessment","date":"2026-11-19",
        "questions":[{"id":"allocation-question","text":"Explain the concept","type":"short","marks":2,"competency":"CU","bloom_level":"Understand"}],
        "competency_focus":["CU"]})
    assert created.status_code==201,created.text
