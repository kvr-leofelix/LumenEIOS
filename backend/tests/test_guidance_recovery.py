import copy
from datetime import timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy import select,func
from backend.tests.test_learnsphere import learning
from backend.tests.test_panchapadi import submit_assessment,review_body,questions_and_mapping,scored
from backend.app.db.session import AsyncSessionLocal
from backend.app.models.entities import utc_now
from backend.app.modules.learnsphere.assessment_models import AssessmentResultRecord
from backend.app.modules.learnsphere.models import LearningAssignment,LearningAttempt
from backend.app.services.llm_service import qwen_question_studio
from backend.app.services import panchapadi as worker


@pytest.mark.asyncio
async def test_submission_automatically_retries_only_missing_guidance(client,learning,monkeypatch):
    l=learning;original=qwen_question_studio.assessment_question_guidance;calls={};checkpoints=[]
    async def temporary(question,response,outcome,stages):
        position=question['position'];calls[position]=calls.get(position,0)+1
        async with AsyncSessionLocal() as db:
            record=await db.scalar(select(AssessmentResultRecord).where(AssessmentResultRecord.student_id==l.student))
            current=record.panchapadi_json['attempts'][-1]
            assert current['status']=='running' and current['outcomes']
            checkpoints.append(len(current.get('question_guidance',[])))
        if position==0 and calls[position]<3:raise RuntimeError('Temporary model failure')
        return await original(question,response,outcome,stages)
    monkeypatch.setattr(qwen_question_studio,'assessment_question_guidance',temporary)
    a,result,body,_=await submit_assessment(client,l,monkeypatch)
    assert calls[0]==3 and all(calls[p]==1 for p in range(1,6))
    assert max(checkpoints)>0  # Guidance was saved before the whole model job finished.
    response=await client.get(f"/api/v1/learnsphere/students/{l.student}/assessments/{a['id']}/guidance",headers=l.headers['student'])
    assert response.status_code==200 and all(q['guidance'] for q in response.json()['questions'])
    assert response.json()['guidance_status']=='provisional'
    again=(await client.get(f"/api/v1/assessments/results/{result['id']}",headers=l.headers['teacher'])).json()
    assert again['answers']==body['answers'] and again['reviews']==[] and again['version']==1
    assignments=(await client.get('/api/v1/learnsphere/assignments?student_id='+l.student,headers=l.headers['student'])).json()
    assert len(assignments)==2 and all(not a['attempts'] for a in assignments)
    before=copy.deepcopy(calls)
    await client.get(f"/api/v1/learnsphere/students/{l.student}/assessments/{a['id']}/guidance",headers=l.headers['parent'])
    assert calls==before  # Reads do not start inference or create duplicates.


@pytest.mark.asyncio
async def test_automatic_sweep_recovers_historical_missing_guidance(client,learning,monkeypatch,db_session):
    l=learning;original=qwen_question_studio.assessment_question_guidance
    async def fail(*args):raise RuntimeError('Unavailable')
    monkeypatch.setattr(qwen_question_studio,'assessment_question_guidance',fail)
    a,result,body,mapping=await submit_assessment(client,l,monkeypatch)
    record=await db_session.get(AssessmentResultRecord,result['id'])
    payload=copy.deepcopy(record.panchapadi_json)
    payload['attempts'][-1].update(date=(utc_now()-timedelta(hours=1)).isoformat(),heartbeat_at=(utc_now()-timedelta(hours=1)).isoformat())
    record.panchapadi_json=payload;await db_session.commit()
    old_reviews=copy.deepcopy(record.reviews_json);old_answers=copy.deepcopy(record.answers_json)
    due=worker._retry_due
    monkeypatch.setattr(worker,'_retry_due',lambda r:r.id==record.id and due(r))
    monkeypatch.setattr(qwen_question_studio,'assessment_question_guidance',original)
    assert await worker.recover_missing_guidance_once()==1
    assert await worker.recover_missing_guidance_once()==0
    await db_session.refresh(record)
    assert record.reviews_json==old_reviews and record.answers_json==old_answers
    assert len(worker.saved_question_guidance(record))==6
    assignments=await db_session.scalar(select(func.count()).select_from(LearningAssignment).where(LearningAssignment.student_id==l.student))
    assert assignments==2
    assert await db_session.scalar(select(func.count()).select_from(LearningAttempt).join(LearningAssignment).where(LearningAssignment.student_id==l.student))==0


@pytest.mark.asyncio
async def test_legacy_adheeti_display_and_identical_review_guidance_reuse(client,learning,monkeypatch,db_session):
    l=learning;a,result,body,mapping=await submit_assessment(client,l,monkeypatch)
    mapping[0]['mappings'][0]['prerequisite_test']=False
    reviewed=await client.post(f"/api/v1/assessments/results/{result['id']}/review",headers=l.headers['teacher'],json=review_body(result,mapping))
    assert reviewed.status_code==200,reviewed.text
    record=await db_session.get(AssessmentResultRecord,result['id'])
    reviews=copy.deepcopy(record.reviews_json)
    # Reproduce the old signed snapshot with a redundant false checkbox and a
    # stale insufficient-evidence total. This is isolated synthetic data only.
    adheeti=reviews[-1]['panchapadi']['stages'][0]
    adheeti.update(score_pct=None,earned_marks=None,maximum_marks=None,evidence_count=0,status='Insufficient evidence')
    adheeti['contributions'][0].update(eligible=False,exclusion_reason='No prerequisite checkbox')
    record.reviews_json=reviews
    payload=copy.deepcopy(record.panchapadi_json)
    # A newer interrupted attempt must not hide saved guidance with identical
    # questions, locked answers, confirmed marks and mapped stage names.
    payload['attempts'].append({'attempt_id':'interrupted','status':'running','date':utc_now().isoformat(),
        'review_revision_id':reviews[-1]['revision_id'],'mapping':[],'stages':[]})
    record.panchapadi_json=payload;await db_session.commit()
    raw_reviews=copy.deepcopy(record.reviews_json);raw_answers=copy.deepcopy(record.answers_json);version=record.version
    response=await client.get(f"/api/v1/learnsphere/students/{l.student}/assessments/{a['id']}/guidance",headers=l.headers['student'])
    assert response.status_code==200,response.text
    output=response.json();stage=output['performance']['evaluation']['stages'][0]
    assert stage['stage']=='Adheeti' and stage['score_pct']==100 and stage['evidence_count']==1
    assert stage['earned_marks']==1 and stage['maximum_marks']==1 and stage['status']=='verified'
    assert stage['contributions'][0]['position']==0 and stage['contributions'][0]['eligible']
    assert all(q['guidance'] for q in output['questions'])
    assert output['guidance_status']=='provisional'  # AI advice is not teacher confirmation.
    graphs=(await client.get(f'/api/v1/learnsphere/students/{l.student}/panchapadi',headers=l.headers['student'])).json()
    assert graphs['graphs'][0]['points'][0]['score_pct']==100
    await db_session.refresh(record)
    assert record.reviews_json==raw_reviews and record.answers_json==raw_answers and record.version==version
    assert record.reviews_json[-1]['panchapadi']['stages'][0]['score_pct'] is None
    assert not worker.guidance_missing(record)
    changed=copy.deepcopy(record.reviews_json)
    changed[-1]['outcomes'][0]['score']=0
    changed[-1]['panchapadi']['mapping'][2]['mappings'][0]['procedural_practice']=False
    record.reviews_json=changed
    assert 0 not in worker.saved_question_guidance(record)  # Changed marks invalidate only affected advice.
    assert 2 not in worker.saved_question_guidance(record)  # Changed demand gates also invalidate advice.


def test_confirmed_adheeti_is_independent_and_ai_needs_prerequisite_evidence():
    questions,mapping=questions_and_mapping();outcomes=scored(questions)
    mapping[0]['mappings'][0]['prerequisite_test']=False
    ai=worker.calculate_stages(questions,outcomes,mapping)
    verified=worker.calculate_stages(questions,outcomes,mapping,verified=True)
    assert ai[0]['score_pct'] is None and verified[0]['score_pct']==100 and verified[0]['evidence_count']==1
    assert [s['score_pct'] for s in ai[1:]]==[s['score_pct'] for s in verified[1:]]
    outcomes[0]['score']=0
    assert worker.calculate_stages(questions,outcomes,mapping,verified=True)[0]['score_pct']==0
    outcomes[0]['score']=None
    assert worker.calculate_stages(questions,outcomes,mapping,verified=True)[0]['score_pct'] is None
    outcomes[0]['score']=1;mapping[0]['mappings']=[]
    assert worker.calculate_stages(questions,outcomes,mapping,verified=True)[0]['evidence_count']==0


def test_recovery_respects_running_lease_and_backoff():
    questions,mapping=questions_and_mapping();outcomes=scored(questions)
    record=SimpleNamespace(questions_json=questions,automatic_json=outcomes,reviews_json=[],panchapadi_json={})
    assert worker._retry_due(record)
    attempt={'status':'running','date':utc_now().isoformat(),'heartbeat_at':utc_now().isoformat(),'review_revision_id':None,'mapping':mapping,'outcomes':outcomes}
    record.panchapadi_json={'attempts':[attempt]}
    assert not worker._retry_due(record)
    attempt['heartbeat_at']=(utc_now()-timedelta(minutes=31)).isoformat()
    assert worker._retry_due(record)
    attempt.update(status='failed',heartbeat_at=utc_now().isoformat())
    assert not worker._retry_due(record)
    attempt['heartbeat_at']=(utc_now()-timedelta(minutes=2)).isoformat()
    assert worker._retry_due(record)


def test_recovery_stops_after_the_automatic_attempt_limit():
    questions,mapping=questions_and_mapping();outcomes=scored(questions)
    old=(utc_now()-timedelta(hours=2)).isoformat()
    failed=lambda:{'status':'failed','date':old,'heartbeat_at':old,'review_revision_id':None,'mapping':mapping,'outcomes':outcomes}
    record=SimpleNamespace(questions_json=questions,automatic_json=outcomes,reviews_json=[],
                           panchapadi_json={'attempts':[failed() for _ in range(worker.GUIDANCE_MAX_AUTOMATIC_ATTEMPTS-1)]})
    assert worker._retry_due(record)
    record.panchapadi_json['attempts'].append(failed())
    assert not worker._retry_due(record)  # a persistently failing model no longer loops forever
    # ...but a job stopped mid-run (expired running lease) is still recovered once
    record.panchapadi_json['attempts'][-1]['status']='running'
    assert worker._retry_due(record)
