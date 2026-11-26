"""Synthetic LearnSphere-only automation; no real school data or live inference."""
import copy
import json
import uuid
import pytest
from sqlalchemy import select, func
from backend.tests.test_learnsphere import learning
from backend.tests.test_panchapadi import submit_assessment, review_body
from backend.app.modules.learnsphere.automation import classify_competencies, current_competencies
from backend.app.modules.learnsphere.assessment_models import AssessmentResultRecord
from backend.app.modules.learnsphere.models import LearningAssignment, LearningAttempt
from backend.app.services.llm_service import qwen_question_studio, QwenQuestionStudioService, QwenQuestionStudioInferenceError
from backend.app.services.panchapadi import evaluate_saved_result, calculate_stages


@pytest.mark.asyncio
async def test_classifier_uses_question_evidence_not_stored_tags(monkeypatch):
    captured = []
    async def draft(instruction, content, schema, validator):
        captured.append((instruction, content))
        parsed = schema(questions=[
            {"position":0,"label":"AU","confidence":0.92,"reason":"The learner applies the supplied area method to a new problem."},
            {"position":1,"label":"CT","confidence":0.4,"reason":"The objective and expected reasoning are unclear."},
        ])
        validator(parsed)
        return parsed
    monkeypatch.setattr(qwen_question_studio, "_assessment_draft", draft)
    questions = [{"position":i,"text":"Apply a method" if i==0 else "Discuss it",
        "competency":"LU","correct_answer":"A reasoned calculation","marking_rubric":"Credit the method",
        "learning_objective":"Use a formula","topic":"Area","bloom_level":"Apply"} for i in range(2)]
    mapped = await classify_competencies(questions, "Mathematics", ["Area"])
    assert mapped[0]["label"]=="AU" and mapped[0]["status"]=="provisional"
    assert mapped[1]["label"] is None and mapped[1]["status"]=="requires_review"
    assert mapped[1]["suggested_label"]=="CT" and mapped[1]["reason"]
    assert mapped[0]["source_references"] and mapped[0]["question_fingerprint"]
    assert "competency" not in captured[0][1]["questions"][0]
    assert captured[0][1]["subject"]=="Mathematics" and captured[0][1]["questions"][0]["topic"]=="Area"
    assert "NOT Panchapadi" in captured[0][0]


@pytest.mark.asyncio
async def test_classifier_rejects_wrong_question_coverage(monkeypatch):
    calls = []
    def wrong(prompt, **kwargs):
        calls.append(prompt)
        return json.dumps({"questions":[{"position":99,"label":"CU","confidence":0.95,"reason":"A concept."}]})
    monkeypatch.setattr(qwen_question_studio,"_generate_text",wrong)
    with pytest.raises(QwenQuestionStudioInferenceError):
        await classify_competencies([{"position":0,"text":"Explain a concept"}],"Science",[])
    assert len(calls)==2


@pytest.mark.asyncio
async def test_nullable_semantic_marking_does_not_invent_scores(monkeypatch):
    prompts = []
    def insufficient(prompt, **kwargs):
        prompts.append(prompt)
        return json.dumps({"score":2,"correct":True,"insufficient_evidence":True,
            "explanation":"The rubric does not establish the missing requirement.","feedback":"Ask the teacher to clarify the expected reasoning.",
            "demonstrated_concepts":["A relationship"],"partial_concepts":["A step"],"missing_concepts":["An assumption"]})
    service = QwenQuestionStudioService()
    monkeypatch.setattr(service,"_generate_text",insufficient)
    marked = await service.mark_written_answer({"text":"Explain the relationship","marks":2,
        "correct_answer":"Explain two related ideas","marking_rubric":"Credit justified reasoning"},"An equivalent paraphrase.")
    assert marked.score is None and marked.correct is None
    assert marked.missing_concepts==[] and marked.partial_concepts==[]
    assert "semantic meaning" in prompts[0] and "untrusted" in prompts[0]


@pytest.mark.asyncio
async def test_teacher_mapping_review_is_separate_idempotent_and_preserved(client,learning,monkeypatch,db_session):
    l=learning
    assessment,result,_,stages=await submit_assessment(client,l,monkeypatch)
    record=await db_session.get(AssessmentResultRecord,result["id"])
    before=copy.deepcopy((record.questions_json,record.answers_json,record.reviews_json))
    base=f"/api/v1/learnsphere/students/{l.student}/assessments/{assessment['id']}"
    initial=(await client.get(base+"/guidance",headers=l.headers["teacher"])).json()
    assert all(q["competency_mapping"]["status"]=="provisional" for q in initial["questions"])
    body={"expected_version":initial["automation_version"],"request_key":uuid.uuid4().hex,
        "questions":[{"position":0,"label":"AU","reason":"The question requires applying the supplied method."}]}
    confirmed=await client.post(base+"/competencies",headers=l.headers["teacher"],json=body)
    assert confirmed.status_code==200,confirmed.text
    repeat=await client.post(base+"/competencies",headers=l.headers["teacher"],json=body)
    assert repeat.status_code==200
    await evaluate_saved_result(result["id"],True)
    await db_session.refresh(record)
    assert (record.questions_json,record.answers_json,record.reviews_json)==before
    assert len(record.panchapadi_json["competency_reviews"])==1
    assert current_competencies(record)[0]["label"]=="AU"
    assert current_competencies(record)[0]["status"]=="teacher_confirmed"
    assert current_competencies(record)[0]["question_id"]==record.questions_json[0].get("id")
    assert await db_session.scalar(select(func.count()).select_from(LearningAssignment).where(LearningAssignment.student_id==l.student))==2
    assert await db_session.scalar(select(func.count()).select_from(LearningAttempt)
        .join(LearningAssignment,LearningAssignment.id==LearningAttempt.assignment_id)
        .where(LearningAssignment.student_id==l.student))==0
    assert all(a["mapping"]==stages for a in record.panchapadi_json["attempts"] if a["status"]=="complete")
    stale={**body,"request_key":uuid.uuid4().hex}
    assert (await client.post(base+"/competencies",headers=l.headers["teacher"],json=stale)).status_code==409
    changed={**body,"questions":[{**body["questions"][0],"label":"CT"}]}
    assert (await client.post(base+"/competencies",headers=l.headers["teacher"],json=changed)).status_code==409
    for role in ("student","parent","otherteacher","inactive"):
        denied=await client.post(base+"/competencies",headers=l.headers[role],json=stale)
        assert denied.status_code in (403,404)
    assert (await client.post(base+"/competencies",json=stale)).status_code==401
    advice_outcomes=[]
    original_advice=qwen_question_studio.assessment_question_guidance
    async def observe_feedback(question,response,outcome,stage_mapping):
        advice_outcomes.append(copy.deepcopy(outcome))
        return await original_advice(question,response,outcome,stage_mapping)
    monkeypatch.setattr(qwen_question_studio,"assessment_question_guidance",observe_feedback)
    grade_review=review_body(result,stages)
    grade_review["questions"][0]["feedback"]="Teacher clarified the missing relationship."
    reviewed=await client.post(f"/api/v1/assessments/results/{result['id']}/review",
        headers=l.headers["teacher"],json=grade_review)
    assert reviewed.status_code==200,reviewed.text
    current=(await client.get(base+"/guidance",headers=l.headers["teacher"])).json()
    assert current["evaluation_status"]=="teacher_reviewed"
    assert current["performance"]["evaluation"]["teacher_verified"]
    assert current["questions"][0]["competency_mapping"]["label"]=="AU"
    assert any(o.get("feedback")=="Teacher clarified the missing relationship." for o in advice_outcomes)
    parent=(await client.get(base+"/guidance",headers=l.headers["parent"])).json()
    assert "source_references" not in parent["questions"][0]["competency_mapping"]
    assert all(q.get("concept_evidence") is None for q in parent["questions"])


@pytest.mark.asyncio
async def test_failed_classification_stays_unmapped_not_guessed(client,learning,monkeypatch):
    from backend.app.modules.learnsphere import automation
    async def unavailable(*args):
        raise QwenQuestionStudioInferenceError("Unavailable model")
    monkeypatch.setattr(automation,"classify_competencies",unavailable)
    assessment,result,_,_=await submit_assessment(client,learning,monkeypatch)
    data=(await client.get(f"/api/v1/learnsphere/students/{learning.student}/assessments/{assessment['id']}/guidance",
        headers=learning.headers["teacher"])).json()
    assert all(q["competency"]=="Unmapped" and q["competency_mapping"]["label"] is None for q in data["questions"])
    assert data["warnings"]
    assignments=(await client.get("/api/v1/learnsphere/assignments?student_id="+learning.student,headers=learning.headers["teacher"])).json()
    assert assignments==[]
    assert result["answers"]


def test_percentages_exclude_unknown_and_keep_real_zero():
    questions=[{"position":i,"id":str(i),"marks":2} for i in range(3)]
    outcomes=[{"position":0,"score":2,"maximum":2},{"position":1,"score":0,"maximum":2},{"position":2,"score":None,"maximum":2}]
    mapping=[{"position":i,"mappings":[{"stage":"Bodh","reasoning":"Explains a relationship."}]} for i in range(3)]
    score=next(s for s in calculate_stages(questions,outcomes,mapping,verified=True) if s["stage"]=="Bodh")
    assert score["score_pct"]==50 and score["evidence_count"]==2 and score["maximum_marks"]==4
    assert not score["contributions"][2]["eligible"]


@pytest.mark.asyncio
async def test_changed_analysis_invalidates_only_incompatible_advice(client,learning,monkeypatch,db_session):
    from backend.app.services.panchapadi import saved_question_guidance
    _, result, _, _ = await submit_assessment(client,learning,monkeypatch)
    record = await db_session.get(AssessmentResultRecord,result["id"])
    metadata = copy.deepcopy(record.panchapadi_json)
    latest = metadata["attempts"][-1]
    original = record.questions_json[0]["competency"]
    changed = "AU" if original != "AU" else "CT"
    next(m for m in latest["competency_mappings"] if m["position"]==0)["label"] = changed
    record.panchapadi_json = metadata
    assert 0 not in saved_question_guidance(record)
