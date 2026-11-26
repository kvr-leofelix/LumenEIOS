"""Synthetic responses only in conftest's isolated database; never the user database."""
import uuid
import pytest
from sqlalchemy import select, func
from backend.tests.test_learnsphere import learning
from backend.app.models.entities import AssessmentSubmission, Student
from backend.app.modules.learnsphere.models import LearningAssignment, LearningEvidence
from backend.app.modules.learnsphere.assessment_models import AssessmentResultRecord


async def assessment(client, l, written=False):
    q={"subject_id":l.subject,"text":"Which value equals two plus two?","type":"mcq","options":["3","4","5","6"],
       "correct_answer":"4","marking_rubric":"Credit the exact correct option.","marks":2,"competency":"CU","bloom_level":"Apply"}
    question={**q,"id":"learnsphere-test-"+uuid.uuid4().hex}
    questions=[question,{**question,"id":"second-"+uuid.uuid4().hex,"competency":"LU","text":"Interpret the phrase two more than two."}]
    if written:
        questions.append({**question,"id":"written-"+uuid.uuid4().hex,"type":"descriptive","options":[],"competency":"CT","marks":3,"text":"Explain why the competing answer is incorrect.","correct_answer":"Explain addition.","marking_rubric":"Evaluate the reasoning."})
    response=await client.post(f'/api/v1/classes/{l.cls}/assessments',headers=l.headers['teacher'],json={
        "class_id":l.cls,"subject_id":l.subject,"title":"Genuine response test","date":"2026-11-12",
        "total_marks":sum(q['marks'] for q in questions),"competency_focus":["CU","LU","CT"],"questions":questions})
    assert response.status_code==201,response.text
    return response.json()


def answers(written=False):
    response=[{"position":0,"selected_option_index":1},{"position":1,"selected_option_index":0}]
    if written: response.append({"position":2,"answer_text":"Adding two and two gives four; the competing answer miscounts."})
    return {"request_key":uuid.uuid4().hex,"answers":response}


def review(result, topic=None):
    return {"expected_version":result['version'],"feedback":"Reviewed the actual responses against the stored rubric.","questions":[
        {"position":q['position'],"score":q['marks'] if q['position']!=1 else 0,"correct":q['position']!=1,
         "feedback":"Checked the response.","topic_id":topic} for q in result['questions']]}


@pytest.mark.asyncio
async def test_student_submission_identity_server_scoring_and_duplicate_prevention(client,learning,db_session):
    l=learning;a=await assessment(client,l);payload=answers()
    path=f"/api/v1/assessments/{a['id']}/answers"
    r=await client.post(path,headers=l.headers['student'],json=payload)
    assert r.status_code==200,r.text
    result=r.json()
    assert result['student_id']==l.student and result['school_id']==l.school
    assert result['assessment_id']==a['id'] and result['subject_id']==l.subject
    assert result['marks_obtained']==2 and result['total_marks']==4
    assert [o['score'] for o in result['outcomes']]==[2,0]
    assert [o['correct'] for o in result['outcomes']]==[True,False]
    assert result['status']=='automatically_evaluated_unverified'
    assert all('correct_answer' not in q and 'marking_rubric' not in q for q in result['questions'])
    retry=await client.post(path,headers=l.headers['student'],json=payload)
    assert retry.status_code==200 and retry.json()['id']==result['id']
    assert await db_session.scalar(select(func.count()).select_from(AssessmentResultRecord).where(AssessmentResultRecord.assessment_id==a['id']))==1
    assert await db_session.scalar(select(func.count()).select_from(AssessmentSubmission).where(AssessmentSubmission.assessment_id==a['id']))==1
    changed=answers();assert (await client.post(path,headers=l.headers['student'],json=changed)).status_code==409
    payload['marks_obtained']=100
    assert (await client.post(path,headers=l.headers['student'],json=payload)).status_code==422
    support=(await client.get(f'/api/v1/learnsphere/students/{l.student}/support',headers=l.headers['student'])).json()
    assert support['assessment_findings']==[]
    stored=await db_session.get(Student,l.student)
    assert stored.cu_score==70  # automatic/unverified results do not rewrite live scores


@pytest.mark.asyncio
async def test_written_pending_review_unmapped_evidence_and_no_fake_activities(client,learning,db_session):
    l=learning;a=await assessment(client,l,written=True)
    r=await client.post(f"/api/v1/assessments/{a['id']}/answers",headers=l.headers['student'],json=answers(True))
    assert r.status_code==200,r.text
    result=r.json()
    assert result['status']=='awaiting_teacher_review'
    assert result.get('marks_obtained') is None and result.get('submission_id') is None
    assert result['outcomes'][2].get('score') is None
    reviewed=await client.post(f"/api/v1/assessments/results/{result['id']}/review",headers=l.headers['teacher'],json=review(result))
    assert reviewed.status_code==200,reviewed.text
    result=reviewed.json()
    assert result['marks_obtained']==5 and result['total_marks']==7 and result['status']=='teacher_reviewed'
    assert result['automatic_outcomes'][2].get('score') is None
    support=(await client.get(f'/api/v1/learnsphere/students/{l.student}/support',headers=l.headers['teacher'])).json()
    assert support['findings']==[]  # assessment questions never count as learning activities
    assert len(support['assessment_findings'])==3
    assert all(f['topic_id'] is None and f['assessments']==1 for f in support['assessment_findings'])
    assert all(o['provenance']=='teacher_reviewed' for f in support['assessment_findings'] for o in f['sources'])
    journey=(await client.get(f'/api/v1/learnsphere/students/{l.student}/journey',headers=l.headers['parent'])).json()
    assert len(journey['assessment_observations'])==3
    assert journey['completed_assignments']==0 and journey['participation']==0
    assert all(n==0 for n in journey['stages'].values())
    assert not journey['trends']  # no made-up comparable progress from one assessment
    assert await db_session.scalar(select(func.count()).select_from(LearningAssignment).where(LearningAssignment.student_id==l.student))==2
    assert await db_session.scalar(select(func.count()).select_from(LearningEvidence).where(LearningEvidence.student_id==l.student))==0


@pytest.mark.asyncio
async def test_review_revision_replaces_eligible_outcomes_and_verified_topic(client,learning):
    l=learning;a=await assessment(client,l)
    result=(await client.post(f"/api/v1/assessments/{a['id']}/answers",headers=l.headers['student'],json=answers())).json()
    topic=(await client.post('/api/v1/learnsphere/topics',headers=l.headers['teacher'],json={"class_id":l.cls,"subject_id":l.subject,"title":"Verified addition topic"})).json()
    body=review(result,topic['id']);path=f"/api/v1/assessments/results/{result['id']}/review"
    first=await client.post(path,headers=l.headers['teacher'],json=body)
    assert first.status_code==200,first.text
    assert (await client.post(path,headers=l.headers['teacher'],json=body)).status_code==409
    body=review(first.json(),topic['id']);body['questions'][0]['score']=1
    second=await client.post(path,headers=l.headers['teacher'],json=body)
    assert second.status_code==200,second.text
    assert len(second.json()['reviews'])==2
    assert second.json()['automatic_outcomes'][0]['score']==2
    data=(await client.get(f'/api/v1/learnsphere/students/{l.student}/journey',headers=l.headers['student'])).json()
    assert len(data['assessment_observations'])==2
    assert sum(o['score'] for o in data['assessment_observations'])==1
    assert all(o['topic_id']==topic['id'] for o in data['assessment_observations'])


@pytest.mark.asyncio
@pytest.mark.parametrize('role,status',[('parent',403),('teacher',403),('otherstudent',404),('unlinked',404)])
async def test_unauthorized_submission(client,learning,role,status):
    a=await assessment(client,learning)
    assert (await client.post(f"/api/v1/assessments/{a['id']}/answers",headers=learning.headers[role],json=answers())).status_code==status


@pytest.mark.asyncio
async def test_review_access_and_topic_boundaries(client,learning):
    l=learning;a=await assessment(client,l)
    result=(await client.post(f"/api/v1/assessments/{a['id']}/answers",headers=l.headers['student'],json=answers())).json()
    assert (await client.post(f"/api/v1/assessments/{a['id']}/answers",json=answers())).status_code==401
    for role,code in [('student',403),('parent',403),('otherteacher',404),('inactive',404)]:
        response=await client.post(f"/api/v1/assessments/results/{result['id']}/review",headers=l.headers[role],json=review(result))
        assert response.status_code==code,response.text
    assert (await client.get(f"/api/v1/assessments/results/{result['id']}",headers=l.headers['otherstudent'])).status_code==404
    bad=review(result,'missing-topic')
    assert (await client.post(f"/api/v1/assessments/results/{result['id']}/review",headers=l.headers['teacher'],json=bad)).status_code==422
    bad=review(result);bad['questions'][0]['score']=3
    assert (await client.post(f"/api/v1/assessments/results/{result['id']}/review",headers=l.headers['teacher'],json=bad)).status_code==422
    assert (await client.get('/api/v1/assessments/results-for-review',headers=l.headers['otherteacher'])).json()==[]


@pytest.mark.asyncio
async def test_legacy_or_modified_totals_not_promoted(client,learning,db_session):
    l=learning;a=await assessment(client,l)
    result=(await client.post(f"/api/v1/assessments/{a['id']}/answers",headers=l.headers['student'],json=answers())).json()
    reviewed=(await client.post(f"/api/v1/assessments/results/{result['id']}/review",headers=l.headers['teacher'],json=review(result))).json()
    sub=await db_session.get(AssessmentSubmission,reviewed['submission_id']);sub.marks_obtained=0
    await db_session.commit()
    data=(await client.get(f'/api/v1/learnsphere/students/{l.student}/support',headers=l.headers['teacher'])).json()
    assert data['assessment_findings']==[]


def test_postgresql_additive_migration_offline():
    import io
    from alembic.config import Config
    from alembic import command
    buffer=io.StringIO();config=Config('backend/alembic.ini',output_buffer=buffer)
    config.set_main_option('sqlalchemy.url','postgresql://')
    command.upgrade(config,'0002_assessment_results',sql=True)
    sql=buffer.getvalue()
    assert 'CREATE TABLE learning_assessment_results' in sql
    assert 'UNIQUE (assessment_id, student_id)' in sql
    assert 'ALTER TABLE' not in sql and 'DROP TABLE' not in sql


@pytest.mark.asyncio
async def test_publication_with_foreign_key_enforcement(client,learning,db_session):
    from sqlalchemy import text
    from backend.app.schemas.assessment_results import AnswersSubmit, AssessmentReview
    from backend.app.services.assessment_results import submit_answers, review_result
    l=learning;a=await assessment(client,l,written=True)
    await db_session.execute(text('PRAGMA foreign_keys=ON'))
    assert (await db_session.execute(text('PRAGMA foreign_keys'))).scalar()==1
    try:
        result=await submit_answers(db_session,l.users['student'],a['id'],AnswersSubmit(**answers(True)))
        await db_session.execute(text('PRAGMA foreign_keys=ON'))
        reviewed=await review_result(db_session,l.users['teacher'],result['id'],AssessmentReview(**review(result)))
        assert reviewed['submission_id'] and reviewed['marks_obtained']==5
    finally:
        await db_session.rollback()
        # commit() releases connections back to the pool. Toggling a later acquired
        # connection does not reset the one that had FK enforcement enabled.
        # Close this session and dispose idle test connections so later legacy
        # tests retain their own default connection configuration.
        await db_session.close()
        from backend.app.db.session import engine
        await engine.dispose()


@pytest.mark.asyncio
async def test_teacher_review_nudges_live_parameters_once_instead_of_overwriting(client,learning,db_session):
    l=learning;a=await assessment(client,l)
    before=await db_session.get(Student,l.student)
    start={c:getattr(before,c) for c in ('lu_score','cu_score','au_score','ct_score')}
    result=(await client.post(f"/api/v1/assessments/{a['id']}/answers",headers=l.headers['student'],json=answers())).json()
    path=f"/api/v1/assessments/results/{result['id']}/review"
    first=await client.post(path,headers=l.headers['teacher'],json=review(result))  # CU 2/2 = 100, LU 0/2 = 0
    assert first.status_code==200,first.text
    weight=round(0.1+0.3*4/25,3)
    db_session.expire_all()
    after=await db_session.get(Student,l.student)
    assert after.cu_score==round(start['cu_score']+weight*(100-start['cu_score']))
    assert after.lu_score==round(start['lu_score']+weight*(0-start['lu_score']))
    assert after.cu_score<100 and after.lu_score>0  # one quiz never replaces the whole profile
    assert (after.au_score,after.ct_score)==(start['au_score'],start['ct_score'])  # untested dimensions stay
    moved={c:getattr(after,c) for c in ('lu_score','cu_score')}
    body=review(first.json());body['questions'][0]['score']=1
    assert (await client.post(path,headers=l.headers['teacher'],json=body)).status_code==200
    db_session.expire_all()
    again=await db_session.get(Student,l.student)
    assert {c:getattr(again,c) for c in ('lu_score','cu_score')}==moved  # a corrected review does not move them twice
