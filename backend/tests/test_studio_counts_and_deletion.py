import uuid
import pytest
from pydantic import ValidationError
from backend.app.schemas.assessments import GenerateQuestionsRequest
from backend.app.lib.question_distribution import distribute
from backend.app.models.entities import Assessment


@pytest.mark.parametrize("selected,total,expected",[
    (["CT","LU","CU","AU"],10,{"LU":3,"CU":3,"AU":2,"CT":2}),
    (["AU","CT"],5,{"LU":0,"CU":0,"AU":3,"CT":2}),
    (["CU"],1,{"LU":0,"CU":1,"AU":0,"CT":0}),
])
def test_automatic_allocation(selected,total,expected):
    assert distribute(total,selected)==expected
    req=GenerateQuestionsRequest(subject_id="s",mcq_count=min(total,15),theory_count=max(0,total-15),
        total_count=total,selected_competencies=selected)
    assert req.competency_distribution.model_dump()==expected


@pytest.mark.parametrize("changes",[
    {"mcq_count":1.5},{"mcq_count":-1},{"mcq_count":16},{"mcq_count":"3"},{"mcq_count":True},
    {"theory_count":11},{"theory_count":0.5},{"total_count":4},{"selected_competencies":[]},
    {"selected_competencies":["LU","LU"]},
    {"selected_competencies":["LU"],"competency_distribution":{"LU":4,"CU":1}},
])
def test_invalid_counts_rejected(changes):
    with pytest.raises((ValidationError,ValueError)):
        GenerateQuestionsRequest(subject_id="s",**changes)


@pytest.mark.asyncio
async def test_bank_empty_delete_reference_missing_and_school(client,db_session,teacher_token,other_school_teacher_token):
    headers={"Authorization":"Bearer "+teacher_token}
    assert (await client.get("/api/v1/assessments/question-bank?subject_id=absent-"+uuid.uuid4().hex,headers=headers)).json()==[]
    body={"subject_id":"sub-math","text":"Explain why a square has equal sides.","type":"descriptive",
          "correct_answer":"All sides are equal by definition.","marking_rubric":"Explain the definition.","marks":2,"competency":"CU","bloom_level":"Understand"}
    saved=await client.post("/api/v1/assessments/question-bank",headers=headers,json=body)
    assert saved.status_code==201
    qid=saved.json()["id"]
    endpoint="/api/v1/assessments/questions/"+qid
    assert (await client.delete(endpoint)).status_code==401
    assert (await client.delete(endpoint,headers={"Authorization":"Bearer "+other_school_teacher_token})).status_code==404
    db_session.add(Assessment(id="reference-"+uuid.uuid4().hex,school_id="school-1",class_id="class-8a",subject_id="sub-math",
        title="Reference protection",date="2026-01-01",questions_json=[{"id":qid,"text":body["text"]}]))
    await db_session.commit()
    assert (await client.delete(endpoint,headers=headers)).status_code==409
    unused=(await client.post("/api/v1/assessments/question-bank",headers=headers,json=body)).json()["id"]
    assert (await client.delete("/api/v1/assessments/questions/"+unused,headers=headers)).status_code==200
    assert (await client.delete("/api/v1/assessments/questions/"+unused,headers=headers)).status_code==404
