import copy
import io
import json
import sqlite3
import pytest
from sqlalchemy import select
from backend.tests.test_learnsphere import learning
from backend.app.schemas.panchapadi import STAGES, StageClassification
from backend.app.services.panchapadi import calculate_stages, validate_mapping, evaluate_saved_result
from backend.app.services.llm_service import qwen_question_studio, QwenQuestionStudioUnavailable, QwenQuestionStudioService, QwenQuestionStudioInferenceError
from backend.app.modules.learnsphere.assessment_models import AssessmentResultRecord


def mapping_item(stage, **flags):
    return {"stage": stage, "reasoning": f"The actual question explicitly measures {stage} demand.",
            "prerequisite_test": False, "procedural_practice": False, "independent_extension": False, **flags}


def questions_and_mapping():
    demands = [
        ("Recall the prerequisite fraction method needed before the new lesson.", [mapping_item("Adheeti", prerequisite_test=True)]),
        ("Explain the relationship between the numerator and denominator.", [mapping_item("Bodh")]),
        ("Perform the learned fraction addition method on this calculation.", [mapping_item("Abhyas", procedural_practice=True)]),
        ("Perform the second fraction procedure and explain why it works.", [mapping_item("Abhyas", procedural_practice=True), mapping_item("Bodh")]),
        ("Apply fractions to an unfamiliar household water-use problem.", [mapping_item("Prayog")]),
        ("Develop a new connection, test its limits and justify an independent extension.", [mapping_item("Prasar", independent_extension=True)]),
    ]
    questions = [{"position": i, "id": f"q{i}", "text": text, "type": "mcq", "marks": i+1,
                  "competency": "LU", "bloom_level": "Apply", "options": ["Expected", "Other", "Third", "Fourth"],
                  "correct_answer": "Expected", "marking_rubric": text} for i, (text, _) in enumerate(demands)]
    mapping = [{"position": i, "mappings": mappings} for i, (_, mappings) in enumerate(demands)]
    return questions, mapping


def scored(questions):
    return [{"position": q["position"], "score": q["marks"], "maximum": q["marks"], "competency": q["competency"]} for q in questions]


def test_all_stages_weighted_multistage_and_no_competency_lookup():
    questions, mapping = questions_and_mapping()
    outcomes = scored(questions);outcomes[1]["score"] = 1;outcomes[3]["score"] = 1
    stages = calculate_stages(questions, outcomes, mapping, verified=True)
    assert [s["stage"] for s in stages] == list(STAGES)
    by_stage = {s["stage"]: s for s in stages}
    assert by_stage["Bodh"]["score_pct"] == round(100*2/6, 2)
    assert by_stage["Bodh"]["maximum_marks"] == 6 and by_stage["Bodh"]["evidence_count"] == 2
    assert by_stage["Abhyas"]["score_pct"] == round(100*4/7, 2)
    assert all(by_stage[s]["score_pct"] == 100 for s in ("Adheeti", "Prayog", "Prasar"))
    altered = [{**q, "competency": "CT"} for q in questions]
    assert calculate_stages(altered, outcomes, mapping, verified=True) == stages


def test_insufficient_gates_unknown_marks_and_zero_is_real_only_when_scored():
    questions, mapping = questions_and_mapping();outcomes = scored(questions)
    mapping[0]["mappings"][0]["prerequisite_test"] = False
    mapping[5]["mappings"][0]["independent_extension"] = False
    outcomes[3]["score"] = None  # leaves one Abhyas question: no consistent-practice claim
    outcomes[1]["score"] = 0
    stages = {s["stage"]: s for s in calculate_stages(questions, outcomes, mapping)}
    for name in ("Adheeti", "Abhyas", "Prasar"):
        assert stages[name]["score_pct"] is None and stages[name]["status"] == "Insufficient evidence"
    assert stages["Abhyas"]["evidence_count"] == 1
    assert stages["Bodh"]["score_pct"] == 0  # an actually scored zero, not missing data
    assert stages["Bodh"]["evidence_count"] == 1 and stages["Bodh"]["status"] == "provisional"
    assert not stages["Adheeti"]["contributions"][0]["eligible"]
    outcomes[1]["score"] = None
    assert next(s for s in calculate_stages(questions, outcomes, mapping) if s["stage"] == "Bodh")["score_pct"] is None


def test_incomplete_duplicate_unknown_mappings_are_rejected():
    questions, mapping = questions_and_mapping()
    for invalid in (mapping[:-1], mapping + [mapping[0]], [{**mapping[0], "position": 999}, *mapping[1:]]):
        with pytest.raises(ValueError):validate_mapping(invalid, questions)
    bad = copy.deepcopy(mapping);bad[0]["mappings"][0]["stage"] = "Invented"
    with pytest.raises(ValueError):validate_mapping(bad, questions)


async def submit_assessment(client, l, monkeypatch, written=False):
    questions, mapping = questions_and_mapping()
    if written:
        questions[1].update(type="descriptive", options=[])
    async def classify(q, answers, outcomes):
        assert len(answers) == len(q) and all("marks" in item for item in q)
        return StageClassification(questions=mapping)
    monkeypatch.setattr(qwen_question_studio, "classify_panchapadi", classify)
    payload = {"title": "Panchapadi evidence assessment", "subject_id": l.subject, "class_id": l.cls,
               "date": "2026-11-12", "total_marks": 21, "competency_focus": ["LU"], "questions": questions}
    a = await client.post(f"/api/v1/classes/{l.cls}/assessments", headers=l.headers["teacher"], json=payload)
    assert a.status_code == 201, a.text
    answers = [{"position": q["position"], **({"answer_text": "Actual explanation of the relationship."} if q["type"] == "descriptive" else {"selected_option_index": 0})} for q in questions]
    body = {"request_key": a.json()["id"], "answers": answers}
    r = await client.post(f"/api/v1/assessments/{a.json()['id']}/answers", headers=l.headers["student"], json=body)
    assert r.status_code == 200, r.text
    saved = await client.get(f"/api/v1/assessments/results/{r.json()['id']}", headers=l.headers["teacher"])
    assert saved.status_code == 200,saved.text
    return a.json(), saved.json(), body, mapping


def review_body(result, mapping):
    return {"expected_version": result["version"], "feedback": "Verified actual question marks and stage mappings.",
            "confirm_panchapadi": True, "panchapadi_mappings": mapping,
            "questions": [{"position": q["position"], "score": q["marks"], "correct": True, "feedback": "Reviewed response."} for q in result["questions"]]}


@pytest.mark.asyncio
async def test_automatic_submission_provisional_and_verified_graphs(client, learning, monkeypatch):
    l=learning;a,result,body,mapping = await submit_assessment(client,l,monkeypatch,written=True)
    assert result["panchapadi"]["status"] == "complete"
    assert len(result["panchapadi"]["stages"]) == 5 and not result["panchapadi"]["teacher_verified"]
    assert result["version"] == 1  # background metadata does not stale the grade form
    assert (await client.get(f"/api/v1/learnsphere/students/{l.student}/panchapadi",headers=l.headers["student"])).json()["graphs"][0]["points"] == []
    review = await client.post(f"/api/v1/assessments/results/{result['id']}/review",headers=l.headers["teacher"],json=review_body(result,mapping))
    assert review.status_code == 200,review.text
    for stage in STAGES:
        graph = await client.get(f"/api/v1/learnsphere/students/{l.student}/panchapadi/{stage}",headers=l.headers["parent"])
        assert graph.status_code == 200,graph.text
        points=graph.json()["points"]
        assert len(points)==1 and points[0]["score_pct"]==100
        assert points[0]["assessment_id"]==a["id"] and points[0]["assessment_name"]==a["title"]
    journey=(await client.get(f"/api/v1/learnsphere/students/{l.student}/journey",headers=l.headers["student"])).json()
    assert journey["completed_assignments"]==0 and all(n==0 for n in journey["stages"].values())
    assert journey["panchapadi_assessments"][0]["evaluation"]["teacher_verified"] is True
    support=(await client.get(f"/api/v1/learnsphere/students/{l.student}/support",headers=l.headers["teacher"])).json()
    assert support["findings"]==[] and len(support["panchapadi_assessments"][0]["evaluation"]["stages"])==5


@pytest.mark.asyncio
async def test_correction_recalculation_exclusion_and_immutable_review_history(client, learning, monkeypatch):
    l=learning;_,result,_,mapping=await submit_assessment(client,l,monkeypatch)
    path=f"/api/v1/assessments/results/{result['id']}/review"
    first=(await client.post(path,headers=l.headers["teacher"],json=review_body(result,mapping))).json()
    snapshot=copy.deepcopy(first["reviews"][0])
    updated=review_body(first,mapping);updated["questions"][1]["score"]=0
    updated["panchapadi_mappings"][4]["mappings"]=[]  # remove unsuitable Prayog evidence
    second=await client.post(path,headers=l.headers["teacher"],json=updated)
    assert second.status_code==200,second.text
    assert second.json()["reviews"][0]==snapshot and len(second.json()["reviews"])==2
    history=(await client.get(f"/api/v1/learnsphere/students/{l.student}/panchapadi",headers=l.headers["student"])).json()
    by_stage={g["stage"]:g["points"] for g in history["graphs"]}
    assert len(by_stage["Bodh"])==1 and by_stage["Bodh"][0]["score_pct"]==round(100*4/6,2)
    assert by_stage["Prayog"][0]["score_pct"] is None
    assert by_stage["Prayog"][0]["status"]=="Insufficient evidence"
    assert (await client.post(path,headers=l.headers["teacher"],json=updated)).status_code==409


@pytest.mark.asyncio
async def test_cached_retries_failure_history_and_saved_answers(client, learning, monkeypatch, db_session):
    l=learning;a,result,body,mapping=await submit_assessment(client,l,monkeypatch)
    async def must_not_run(*args):raise AssertionError("Cached evaluation reran")
    monkeypatch.setattr(qwen_question_studio,"classify_panchapadi",must_not_run)
    await evaluate_saved_result(result["id"])
    duplicate=await client.post(f"/api/v1/assessments/{a['id']}/answers",headers=l.headers["student"],json=body)
    assert duplicate.status_code==200
    stored=await db_session.get(AssessmentResultRecord,result["id"])
    assert len(stored.panchapadi_json["attempts"])==1
    # Rehearse a failed evaluation on a new submission, then a retry.
    _,other,_,mapping=await submit_assessment(client,l,monkeypatch)
    stored=await db_session.get(AssessmentResultRecord,other["id"])
    stored.panchapadi_json=None;stored.panchapadi_version=None
    await db_session.commit()
    async def unavailable(*args):raise QwenQuestionStudioUnavailable("Unavailable")
    monkeypatch.setattr(qwen_question_studio,"classify_panchapadi",unavailable)
    await evaluate_saved_result(other["id"])
    async def valid(*args):return StageClassification(questions=mapping)
    monkeypatch.setattr(qwen_question_studio,"classify_panchapadi",valid)
    retry=await client.post(f"/api/v1/assessments/results/{other['id']}/panchapadi/evaluate",headers=l.headers["student"])
    assert retry.status_code==200
    db_session.expire_all();saved=await db_session.get(AssessmentResultRecord,other["id"])
    assert [a["status"] for a in saved.panchapadi_json["attempts"]]==["failed","complete"]
    assert len(saved.answers_json)==6


@pytest.mark.asyncio
@pytest.mark.parametrize("role,allowed",[("teacher",True),("principal",True),("parent",True),("student",True),("otherteacher",False),("otherstudent",False),("inactive",False),("unlinked",False)])
async def test_all_graph_authorization(client,learning,role,allowed):
    for stage in STAGES:
        r=await client.get(f"/api/v1/learnsphere/students/{learning.student}/panchapadi/{stage}",headers=learning.headers[role])
        assert (r.status_code==200)==allowed,(role,r.text)
    assert (await client.get(f"/api/v1/learnsphere/students/{learning.student}/panchapadi")).status_code==401


def test_existing_ollama_transport_and_bounded_corrective_retry(monkeypatch):
    import asyncio
    q,mapping=questions_and_mapping();service=QwenQuestionStudioService();calls=[]
    def generate(prompt,**kwargs):
        calls.append((prompt,kwargs));return 'not JSON' if len(calls)==1 else json.dumps({"questions":mapping})
    monkeypatch.setattr(service,"_generate_text",generate)
    result=asyncio.run(service.classify_panchapadi(q,[],scored(q)))
    assert len(calls)==2 and len(result.questions)==6
    assert "Never map LU/CU/AU/CT" in calls[0][0] and "untrusted" in calls[0][0]
    assert "output_schema" in calls[0][1]
    monkeypatch.setattr(service,"_generate_text",lambda *a,**kw:'{}')
    with pytest.raises(QwenQuestionStudioInferenceError):asyncio.run(service.classify_panchapadi(q,[],scored(q)))


def test_additive_migration_preserves_existing_result_and_review(tmp_path):
    from sqlalchemy import create_engine
    from alembic.config import Config
    from alembic import command
    from backend.scripts.migrate_learnsphere import upgrade,column_inventory,fingerprint
    path=tmp_path/'preservation.db';engine=create_engine('sqlite:///'+path.as_posix())
    with engine.begin() as c:
        config=Config('backend/alembic.ini');config.attributes['connection']=c
        command.upgrade(config,'0002_assessment_results')
    engine.dispose()
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO learning_assessment_results (id,assessment_id,student_id,school_id,class_id,subject_id,request_key,questions_json,answers_json,automatic_json,reviews_json,submitted_at,version) VALUES ('r','a','s','sc','c','sub','key','[]','[]','[]','[{\"revision_id\":\"historic-review\"}]','2026-11-12',1)")
        c.commit();columns=column_inventory(c);before=fingerprint(c)
    upgrade(path,expected=before,expected_columns=columns)
    with sqlite3.connect(path) as c:
        after=fingerprint(c,columns)
        assert all(after[k]==v for k,v in before.items() if k!='alembic_version')
        assert c.execute('SELECT panchapadi_json,panchapadi_version FROM learning_assessment_results').fetchone()==(None,None)
        assert json.loads(c.execute('SELECT reviews_json FROM learning_assessment_results').fetchone()[0])[0]['revision_id']=='historic-review'
    out=io.StringIO();config=Config('backend/alembic.ini',output_buffer=out);config.set_main_option('sqlalchemy.url','postgresql://')
    command.upgrade(config,'0002_assessment_results:head',sql=True)
    sql=out.getvalue();assert sql.count('ADD COLUMN')==2 and 'DROP TABLE' not in sql and 'UPDATE learning_assessment_results' not in sql


@pytest.mark.asyncio
async def test_chronological_graphs_include_null_gap_not_zero(client,learning,monkeypatch,db_session):
    from datetime import datetime,timezone
    l=learning
    for day in (3,1,2):
        _,result,_,mapping=await submit_assessment(client,l,monkeypatch)
        body=review_body(result,mapping)
        if day==2:
            for item in body['panchapadi_mappings']:
                item['mappings']=[m for m in item['mappings'] if m['stage']!='Bodh']
        if day==3:
            body['questions'][1]['score']=0
            body['questions'][3]['score']=1
        response=await client.post(f"/api/v1/assessments/results/{result['id']}/review",headers=l.headers['teacher'],json=body)
        assert response.status_code==200,response.text
        record=await db_session.get(AssessmentResultRecord,result['id'])
        record.submitted_at=datetime(2026,11,day,tzinfo=timezone.utc)
        await db_session.commit()
    points=(await client.get(f'/api/v1/learnsphere/students/{l.student}/panchapadi/Bodh',headers=l.headers['student'])).json()['points']
    assert [p['assessed_at'][8:10] for p in points]==['01','02','03']
    assert [p['score_pct'] for p in points]==[100,None,round(100/6,2)]


@pytest.mark.asyncio
async def test_late_ai_result_does_not_change_confirmed_review(client,learning,monkeypatch,db_session):
    l=learning;_,result,_,mapping=await submit_assessment(client,l,monkeypatch)
    reviewed=await client.post(f"/api/v1/assessments/results/{result['id']}/review",headers=l.headers['teacher'],json=review_body(result,mapping))
    assert reviewed.status_code==200
    original=copy.deepcopy(reviewed.json()['reviews'])
    record=await db_session.get(AssessmentResultRecord,result['id'])
    record.panchapadi_json=None;record.panchapadi_version=None
    await db_session.commit()
    async def different(*args):return StageClassification(questions=[{'position':q['position'],'mappings':[]} for q in result['questions']])
    monkeypatch.setattr(qwen_question_studio,'classify_panchapadi',different)
    await evaluate_saved_result(result['id'])
    response=(await client.get(f"/api/v1/assessments/results/{result['id']}",headers=l.headers['teacher'])).json()
    assert response['reviews']==original
    points=(await client.get(f'/api/v1/learnsphere/students/{l.student}/panchapadi/Bodh',headers=l.headers['student'])).json()['points']
    assert points[0]['score_pct']==100


def test_mapping_batches_do_not_truncate_actual_answers(monkeypatch):
    import asyncio
    service=QwenQuestionStudioService();questions,_=questions_and_mapping()
    extra={**questions[0],'position':6,'id':'q6'};questions=[*questions,extra]
    calls=[]
    def generate(prompt,**kwargs):
        batch=json.loads(prompt.split('Return only the structured JSON.\n')[1])
        calls.append(batch)
        return json.dumps({'questions':[{'position':r['question']['position'],'mappings':[]} for r in batch]})
    monkeypatch.setattr(service,'_generate_text',generate)
    answers=[{'position':q['position'],'answer_text':'Complete actual response.'} for q in questions]
    result=asyncio.run(service.classify_panchapadi(questions,answers,scored(questions)))
    assert len(calls)==2 and len(result.questions)==7
    assert all(r['response']['answer_text']=='Complete actual response.' for batch in calls for r in batch)
    assert all('source_document_names' not in r['question'] for batch in calls for r in batch)
