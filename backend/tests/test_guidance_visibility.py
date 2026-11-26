import copy
import json
import pytest
from backend.tests.test_learnsphere import learning
from backend.tests.test_panchapadi import submit_assessment
from backend.app.services.llm_service import qwen_question_studio
from backend.app.schemas.assessment_learning import QuestionGuidance
from backend.app.modules.learnsphere.assessment_models import AssessmentResultRecord
from backend.app.services.assessment_guidance import TEACHER_MAGNET_ACTIVITY,MAGNET_PRACTICE_QUESTION,guidance_for_role


@pytest.mark.asyncio
async def test_all_four_roles_visibility_wording_and_original_records(client,learning,monkeypatch,db_session):
    l=learning;original=qwen_question_studio.assessment_question_guidance
    async def guidance(question,*args):
        if question['position'] in (0,1):
            return QuestionGuidance(expected_concept='The supplied concept.',explanation='An existing explanation.',
                activity=TEACHER_MAGNET_ACTIVITY,practice_question=MAGNET_PRACTICE_QUESTION)
        return await original(question,*args)
    monkeypatch.setattr(qwen_question_studio,'assessment_question_guidance',guidance)
    a,result,_,_=await submit_assessment(client,l,monkeypatch)
    record=await db_session.get(AssessmentResultRecord,result['id'])
    before=copy.deepcopy([record.questions_json,record.answers_json,record.automatic_json,record.reviews_json,record.panchapadi_json])
    path=f"/api/v1/learnsphere/students/{l.student}/assessments/{a['id']}/guidance"
    for role in ('teacher','principal','parent','student'):
        response=await client.get(path,headers=l.headers[role]);assert response.status_code==200,response.text
        payload=response.json();item=payload['questions'][0]['guidance']
        assert item['practice_question']==MAGNET_PRACTICE_QUESTION and item['practice_for_student']
        assert item['explanation']=='An existing explanation.'
        assert item['activity_for_student']
        assert payload['questions'][1]['guidance']['practice_question'] is None
        assert sum(q['guidance'].get('practice_question')==MAGNET_PRACTICE_QUESTION for q in payload['questions'])==1
        if role in ('teacher','principal'):
            assert item['activity']==TEACHER_MAGNET_ACTIVITY
            assert sum(q['guidance'].get('activity')==TEACHER_MAGNET_ACTIVITY for q in payload['questions'])==1
        else:
            assert item['activity'] is None
            assert TEACHER_MAGNET_ACTIVITY not in json.dumps(payload)
    for role in ('otherteacher','otherstudent','unlinked'):
        assert (await client.get(path,headers=l.headers[role])).status_code==404
    assert (await client.get(path)).status_code==401
    await db_session.refresh(record)
    assert [record.questions_json,record.answers_json,record.automatic_json,record.reviews_json,record.panchapadi_json]==before


def test_other_learning_support_content_is_unchanged():
    advice={'activity':'Group objects and explain your reasoning.','practice_question':'How would you compare two examples?',
        'explanation':'Actual existing feedback.','status':'provisional'}
    for role in ('teacher','principal','parent','student'):
        assert guidance_for_role(advice,role)==advice


@pytest.mark.parametrize('role',['parent','student','admin'])
def test_older_teacher_tip_wording_is_also_not_exposed(role):
    activity='Create a simple experiment where students can observe the attraction of different materials to a magnet. Materials like iron, steel, and certain alloys should be used. Discuss the results and relate them to the concept of magnetic materials.'
    original={'activity':activity,'practice_question':MAGNET_PRACTICE_QUESTION}
    public=guidance_for_role(original,role)
    assert public['activity'] is None and public['practice_question']==MAGNET_PRACTICE_QUESTION
    assert original['activity']==activity
