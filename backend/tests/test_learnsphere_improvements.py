import copy
import io
import json
import sqlite3
import pytest
from sqlalchemy import select
from backend.tests.test_learnsphere import learning
from backend.tests.test_panchapadi import submit_assessment,review_body
from backend.app.modules.learnsphere.models import LearningAssignment,LearningAttempt
from backend.app.modules.learnsphere.assessment_models import AssessmentResultRecord
from backend.app.services.llm_service import qwen_question_studio,QwenQuestionStudioService


@pytest.mark.asyncio
async def test_question_guidance_selected_source_and_automatic_assignments(client,learning,monkeypatch,db_session):
    l=learning;a,first,body,mapping=await submit_assessment(client,l,monkeypatch)
    b,second,_,_=await submit_assessment(client,l,monkeypatch,written=True)
    base=f'/api/v1/learnsphere/students/{l.student}'
    options=(await client.get(base+'/assessments',headers=l.headers['student'])).json()
    assert {o['assessment_id'] for o in options}=={a['id'],b['id']}
    for assessment,result in ((a,first),(b,second)):
        response=await client.get(base+f"/assessments/{assessment['id']}/guidance",headers=l.headers['student'])
        assert response.status_code==200,response.text
        data=response.json()
        assert data['result_id']==result['id'] and data['performance']['assessment_id']==assessment['id']
        assert len(data['questions'])==6 and all(q['guidance'] for q in data['questions'])
        assert all(q['correct_answer'] is None for q in data['questions'])
        assert data['questions'][1]['answer']==('Actual explanation of the relationship.' if assessment==b else 'Expected')
        assert data['evaluation_status']=='provisional'
    assignments=(await client.get('/api/v1/learnsphere/assignments?student_id='+l.student,headers=l.headers['student'])).json()
    assert len(assignments)==4 and all(not a['attempts'] for a in assignments)
    assert {a['snapshot']['generation'] for a in assignments}=={'automatic_provisional'}
    assert {a['snapshot']['topic_id'] for a in assignments}=={None}
    assert {a['snapshot']['assessment_id'] for a in assignments}=={a['id'],b['id']}
    before=copy.deepcopy(assignments)
    for _ in range(2):
        await client.get(base+'/assessments',headers=l.headers['student'])
        await client.get(base+f"/assessments/{a['id']}/guidance",headers=l.headers['student'])
        await client.get(base+'/panchapadi?include_provisional=true',headers=l.headers['student'])
    after=(await client.get('/api/v1/learnsphere/assignments?student_id='+l.student,headers=l.headers['student'])).json()
    assert before==after
    again=await client.post(f"/api/v1/assessments/{a['id']}/answers",headers=l.headers['student'],json=body)
    assert again.status_code==200 and again.json()['id']==first['id']
    assert len((await client.get('/api/v1/learnsphere/assignments?student_id='+l.student,headers=l.headers['student'])).json())==4
    journey=(await client.get(base+'/journey',headers=l.headers['student'])).json()
    assert journey['completed_assignments']==0 and all(v==0 for v in journey['stages'].values())


@pytest.mark.asyncio
@pytest.mark.parametrize('role,allowed',[('teacher',True),('principal',True),('student',True),('parent',True),('otherteacher',False),('otherstudent',False),('inactive',False),('unlinked',False)])
async def test_guidance_access_matrix(client,learning,monkeypatch,role,allowed):
    l=learning;a,_,_,_=await submit_assessment(client,l,monkeypatch)
    for suffix in ('/assessments',f"/assessments/{a['id']}/guidance"):
        response=await client.get(f'/api/v1/learnsphere/students/{l.student}'+suffix,headers=l.headers[role])
        assert (response.status_code==200)==allowed,(role,response.text)
    assert (await client.get(f'/api/v1/learnsphere/students/{l.student}/assessments')).status_code==401


@pytest.mark.asyncio
async def test_review_preference_refresh_and_provisional_graphs(client,learning,monkeypatch):
    l=learning;a,result,_,mapping=await submit_assessment(client,l,monkeypatch)
    path=f'/api/v1/learnsphere/students/{l.student}'
    history=(await client.get(path+'/panchapadi?include_provisional=true',headers=l.headers['parent'])).json()
    assert len(history['graphs'])==5 and all(len(g['points'])==1 for g in history['graphs'])
    assert all(not g['points'][0]['teacher_verified'] for g in history['graphs'])
    body=review_body(result,mapping);body['questions'][0].update(score=0,correct=False)
    reviewed=await client.post(f"/api/v1/assessments/results/{result['id']}/review",headers=l.headers['teacher'],json=body)
    assert reviewed.status_code==200,reviewed.text
    selected=(await client.get(path+f"/assessments/{a['id']}/guidance",headers=l.headers['parent'])).json()
    assert selected['questions'][0]['score']==0 and selected['questions'][0]['status']=='Incorrect'
    assert selected['questions'][0]['guidance']['misunderstanding']
    assert selected['evaluation_status']=='teacher_reviewed' and selected['guidance_status']=='provisional'
    original=qwen_question_studio.assessment_question_guidance;calls=[]
    async def track(*args):calls.append(args);return await original(*args)
    monkeypatch.setattr(qwen_question_studio,'assessment_question_guidance',track)
    url=f"/api/v1/assessments/results/{result['id']}/panchapadi/evaluate?refresh_guidance=true"
    for role in ('parent','student','otherteacher'):
        assert (await client.post(url,headers=l.headers[role])).status_code in (403,404)
    refresh=await client.post(url,headers=l.headers['teacher'])
    assert refresh.status_code==200 and len(calls)==6
    current=(await client.get(f"/api/v1/assessments/results/{result['id']}",headers=l.headers['teacher'])).json()
    assert current['answers']==result['answers'] and current['reviews']==reviewed.json()['reviews']
    assert len((await client.get('/api/v1/learnsphere/assignments?student_id='+l.student,headers=l.headers['student'])).json())==2
    graphs=(await client.get(path+'/panchapadi?include_provisional=true',headers=l.headers['student'])).json()['graphs']
    assert all(g['points'][0]['teacher_verified'] for g in graphs)


@pytest.mark.asyncio
async def test_missing_guidance_and_unknown_scores_do_not_invent_weakness(client,learning,monkeypatch):
    async def unavailable(*args):raise ValueError('Unavailable')
    monkeypatch.setattr(qwen_question_studio,'assessment_question_guidance',unavailable)
    l=learning;a,result,_,_=await submit_assessment(client,l,monkeypatch,written=True)
    data=(await client.get(f"/api/v1/learnsphere/students/{l.student}/assessments/{a['id']}/guidance",headers=l.headers['student'])).json()
    assert data['questions'][1]['score'] is None and data['questions'][1]['status']=='Unassessed'
    assert data['questions'][1]['guidance'] is None and data['questions'][1]['missing_information']
    assert data['warnings']


@pytest.mark.asyncio
async def test_guidance_model_cannot_assert_unknown_weakness_or_invent_expected_concept(monkeypatch):
    service=QwenQuestionStudioService()
    monkeypatch.setattr(service,'_generate_text',lambda *a,**k:json.dumps({'expected_concept':'Invented answer',
        'misunderstanding':'Invented weakness','explanation':'A clarification exercise.','activity':'Explain your reasoning.','practice_question':'Why?'}))
    guidance=await service.assessment_question_guidance({'text':'Explain the idea.','marks':2},'Actual response',{'score':None,'maximum':2},[])
    assert guidance.expected_concept is None and guidance.misunderstanding is None


def test_nullable_activity_migration_retains_checks_and_rows(tmp_path):
    from sqlalchemy import create_engine,inspect
    from alembic.config import Config
    from alembic import command
    from backend.scripts.migrate_learnsphere import upgrade,fingerprint,column_inventory
    path=tmp_path/'activities.db';engine=create_engine('sqlite:///'+path.as_posix())
    with engine.begin() as c:
        config=Config('backend/alembic.ini');config.attributes['connection']=c;command.upgrade(config,'0003_panchapadi')
    engine.dispose()
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO learning_activities (id,topic_id,kind,title,instructions,rubric,competency,stage,version,created_by,created_at) VALUES ('keep','real-topic','mission','Original','Actual instructions','Original rubric','CU','Prayog',1,'teacher','2026-11-13')")
        db.commit();before=fingerprint(db);cols=column_inventory(db)
    upgrade(path,expected=before,expected_columns=cols)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT topic_id,title FROM learning_activities WHERE id='keep'").fetchone()==('real-topic','Original')
        assert len(db.execute('PRAGMA table_info(learning_activities)').fetchall())==11
        with pytest.raises(sqlite3.IntegrityError):db.execute("UPDATE learning_activities SET kind='invalid' WHERE id='keep'")
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    out=io.StringIO();config=Config('backend/alembic.ini',output_buffer=out);config.set_main_option('sqlalchemy.url','postgresql://')
    command.upgrade(config,'0003_panchapadi:0004_unmapped_activities',sql=True)
    assert 'DROP NOT NULL' in out.getvalue() and 'DROP TABLE' not in out.getvalue()
