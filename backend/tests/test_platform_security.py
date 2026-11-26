"""Platform security: every router, record boundaries, startup and credential failures."""
import hashlib
from datetime import timedelta
import pytest
import pytest_asyncio
from fastapi.routing import APIRoute
from sqlalchemy import delete, select, func
from backend.tests.test_homework_legacy_security import world, auth, uid
from backend.tests.test_assessment_security import assessments
from backend.app.main import app
from backend.app.core.config import Settings, settings
from backend.app.core.security import get_password_hash, verify_password, create_access_token
from backend.app.models.entities import (Document, GradingBatch, GradingBatchItem, CurriculumDay,
    CurriculumProposal, CrossCurricularProposal, InstructionalDisruption, Notification, Announcement,
    AuditEvent, AssessmentSubmission, StudentCompetencySnapshot, User)

pytestmark=pytest.mark.asyncio


@pytest_asyncio.fixture
async def resources(world, db_session, tmp_path):
    school='school-3';class_id=world['classes'][1].id
    file=tmp_path/'private.txt';file.write_text('PRIVATE-OCR-SECRET',encoding='utf-8')
    doc=Document(id=uid(),school_id=school,uploader_id='owner',file_name='private.txt',file_size=18,
                 mime_type='text/plain',storage_path=str(file),extracted_text='PRIVATE-OCR-SECRET')
    batch=GradingBatch(id=uid(),school_id=school,class_id=class_id,subject_id='sub-math',assessment_id='missing',created_by='owner')
    item=GradingBatchItem(id=uid(),batch_id=batch.id,file_name='private.txt',extracted_text='PRIVATE-OCR-SECRET')
    day=CurriculumDay(id=uid(),day_number=1,class_id=class_id,subject_id='sub-math',topic='Private',objective='Private',teaching_process='Private',measurable_outcome='Private')
    proposal=CurriculumProposal(id=uid(),school_id=school,class_id=class_id,original_duration_days=10,
        revised_duration_days=9,days_saved=1,topics_preserved_count=1,topics_reassigned_count=0,topics_integrated_count=0)
    cross=CrossCurricularProposal(id=uid(),school_id=school,class_id=class_id,title='Private',activity='Private')
    disruption=InstructionalDisruption(id=uid(),school_id=school,date='2026-11-10',reason='Private',days_lost=1,recorded_by='Private')
    notification=Notification(id=uid(),user_id=world['users']['parent'].id,title='Private',message='PRIVATE-NOTIFICATION')
    announcement=Announcement(id=uid(),school_id=school,sender_id='owner',sender_name='owner',title='Private',content='PRIVATE-ANNOUNCEMENT',target_role='teacher')
    rows=[doc,batch,item,day,proposal,cross,disruption,notification,announcement]
    db_session.add_all(rows);await db_session.commit()
    cleanup=[(type(row),row.id) for row in reversed(rows)]
    yield dict(doc=doc.id,batch=batch.id,item=item.id,day=day.id,proposal=proposal.id,cross=cross.id,disruption=disruption.id,notification=notification.id)
    await db_session.rollback()
    for model,key in cleanup:await db_session.execute(delete(model).where(model.id==key))
    await db_session.commit()


DEV_BYPASS_PATHS = {'/api/v1/auth/dev/accounts', '/api/v1/auth/dev/login'}


async def test_developer_bypass_is_closed_outside_development(client, monkeypatch, db_session):
    for env, bypass in [('production', True), ('staging', True), ('development', False)]:
        monkeypatch.setattr(settings, 'APP_ENV', env)
        monkeypatch.setattr(settings, 'DEV_LOGIN_BYPASS', bypass)
        assert (await client.get('/api/v1/auth/dev/accounts')).status_code == 404
        assert (await client.post('/api/v1/auth/dev/login', json={'user_id': 'user-admin'})).status_code == 404
    # In development every bypass sign-in is written to the audit trail.
    monkeypatch.setattr(settings, 'APP_ENV', 'development')
    monkeypatch.setattr(settings, 'DEV_LOGIN_BYPASS', True)
    before = await db_session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'Developer bypass login'))
    user_id = (await client.get('/api/v1/auth/dev/accounts')).json()['accounts'][0]['id']
    assert (await client.post('/api/v1/auth/dev/login', json={'user_id': user_id})).status_code == 200
    after = await db_session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'Developer bypass login'))
    assert after == before + 1


async def test_every_protected_operation_requires_a_real_token(client, monkeypatch, db_session):
    monkeypatch.setattr(settings,'DEMO_MODE',True)
    before=await db_session.scalar(select(func.count()).select_from(AuditEvent))
    import re
    operations=0
    for route_path, methods in app.openapi()['paths'].items():
        if route_path == '/api/v1/auth/login' or not route_path.startswith('/api/v1'): continue
        # The developer sign-in bypass is used before signing in, so it cannot ask for a token; it exists only in
        # development and is covered by test_developer_bypass_is_closed_outside_development below.
        if route_path in DEV_BYPASS_PATHS: continue
        path=re.sub(r'{[^}]+}','missing',route_path)
        for method in set(methods)-{'parameters'}:
            response=await client.request(method.upper(),path,json={} if method.upper() not in {'GET','DELETE'} else None)
            assert response.status_code==401,(method,path,response.status_code,response.text)
            operations+=1
    assert operations>90
    assert before==await db_session.scalar(select(func.count()).select_from(AuditEvent))


@pytest.mark.parametrize('role',['teacher','principal'])
async def test_foreign_school_records_are_unavailable(client,world,resources,role,db_session):
    c=world['classes'][1].id;r=resources
    requests=[('GET',f'/classes/{c}',None),('GET',f'/classes/{c}/students',None),
      ('GET','/schools/school-3',None),('GET','/schools/school-3/classes',None),
      ('GET','/schools/school-3/calendar',None),('GET','/schools/school-3/instructional-availability',None),
      ('POST','/schools/school-3/disruptions',{'date':'2026-11-10','reason':'No','days_lost':1}),
      ('DELETE',f"/disruptions/{r['disruption']}",None),
      ('GET',f"/students/{world['students'][1].id}/competencies",None),
      ('GET',f'/classes/{c}/competency-analytics',None),('GET','/schools/school-3/competency-analytics',None),
      ('GET',f'/curriculum/classes/{c}',None),('GET',f"/curriculum/days/{r['day']}",None),
      ('POST',f"/curriculum/days/{r['day']}/complete",{}),
      ('POST',f'/classes/{c}/time-aware/calculate',{}),('POST',f'/classes/{c}/time-aware/compression-preview',{}),
      ('POST',f"/curriculum-proposals/{r['proposal']}/approve",{'action':'approve'}),
      ('POST',f"/curriculum-proposals/{r['proposal']}/reject",{'action':'reject'}),
      ('GET',f'/classes/{c}/curriculum/cross-curricular-proposals',None),
      ('POST',f"/cross-curricular-proposals/{r['cross']}/accept",{}),
      ('POST',f"/cross-curricular-proposals/{r['cross']}/reject",{}),
      ('GET',f"/documents/{r['doc']}",None),('GET',f"/documents/{r['doc']}/download",None),('DELETE',f"/documents/{r['doc']}",None),
      ('POST','/ocr/process',{'document_id':r['doc']}),
      ('GET',f"/ocr/batches/{r['batch']}",None),('POST',f"/ocr/batches/{r['batch']}/start",{}),
      ('POST',f"/ocr/batches/{r['batch']}/cancel",{}),('DELETE',f"/ocr/batches/{r['batch']}/items/{r['item']}",None),
      ('POST',f"/ocr/batches/{r['batch']}/items/{r['item']}/retry",{}),
      ('PUT',f"/ocr/batches/{r['batch']}/items/{r['item']}",{}),
      ('POST',f"/ocr/batches/{r['batch']}/items/{r['item']}/approve",{}),('POST',f"/ocr/batches/{r['batch']}/approve-all",{})]
    before=await db_session.scalar(select(func.count()).select_from(AuditEvent))
    for method,path,body in requests:
        response=await client.request(method,'/api/v1'+path,json=body,headers=auth(world['users'][role]))
        # Retired endpoints answer 410 Gone to everyone, which reveals nothing about another school's records.
        retired = path.endswith('/time-aware/compression-preview') or (path.startswith('/curriculum-proposals/') and path.endswith(('/approve', '/reject')))
        assert response.status_code==(410 if retired and response.status_code==410 else 404),(method,path,response.status_code,response.text)
        assert 'PRIVATE-OCR-SECRET' not in response.text and 'Private' not in response.text
    assert before==await db_session.scalar(select(func.count()).select_from(AuditEvent))


@pytest.mark.parametrize('role',['student','parent'])
async def test_learners_cannot_read_teacher_resources(client,world,resources,role):
    for path in ['/documents',f"/documents/{resources['doc']}",f"/documents/{resources['doc']}/download",
                 '/ocr/batches',f"/ocr/batches/{resources['batch']}",f"/classes/{world['classes'][0].id}/students"]:
        response=await client.get('/api/v1'+path,headers=auth(world['users'][role]))
        assert response.status_code==403,(path,response.text)
        assert 'PRIVATE-OCR-SECRET' not in response.text
    for path in [f"/students/{world['students'][0].id}/competencies",f"/students/{world['same_id'].id}/competencies"]:
        response=await client.get('/api/v1'+path,headers=auth(world['users'][role]))
        assert response.status_code==(404 if world['same_id'].id in path else 200)


async def test_principal_users_never_default_to_all_schools(client,world):
    response=await client.get('/api/v1/users',headers=auth(world['users']['principal']))
    assert response.status_code==200
    assert all(row['school_id']=='school-1' for row in response.json())
    assert not any('hashed_password' in row for row in response.json())


async def test_notifications_and_announcements_are_private(client,world,resources,db_session):
    headers=auth(world['users']['teacher'])
    response=await client.post(f"/api/v1/notifications/{resources['notification']}/read",headers=headers)
    assert response.status_code==404
    response=await client.get('/api/v1/announcements',headers=headers)
    assert 'PRIVATE-ANNOUNCEMENT' not in response.text
    response=await client.post('/api/v1/announcements',json={'title':'Spoof','content':'Spoof'},headers=auth(world['users']['student']))
    assert response.status_code==403
    response=await client.post(f"/api/v1/notifications/{resources['notification']}/read",headers=auth(world['users']['parent']))
    assert response.status_code==200


async def test_document_storage_cannot_escape_private_root(tmp_path,monkeypatch):
    from backend.app.services.storage_service import storage_service
    root=tmp_path/'uploads';root.mkdir();outside=tmp_path/'private.txt';outside.write_text('SECRET')
    inside=root/'safe.txt';inside.write_text('allowed')
    monkeypatch.setattr(storage_service,'upload_dir',str(root))
    from fastapi import HTTPException
    with pytest.raises(HTTPException):storage_service.get_file_path(str(outside))
    assert storage_service.get_file_path(str(inside))==str(inside.resolve())


async def test_direct_bcrypt_no_sha256_hashing_fallback(monkeypatch):
    import backend.app.core.security as security
    monkeypatch.setattr(settings,'DEMO_MODE',False)
    hashed=get_password_hash('a-test-password')
    assert hashed.startswith('$2b$') and verify_password('a-test-password',hashed)
    assert not verify_password(hashed,hashed)
    assert not verify_password('demo123',get_password_hash('demo123'))
    with pytest.raises(ValueError):get_password_hash('x'*73)
    def broken(*args):raise RuntimeError('hashing unavailable')
    monkeypatch.setattr(security.bcrypt,'hashpw',broken)
    with pytest.raises(RuntimeError):get_password_hash('password')


async def test_expiry_signature_refresh_and_stale_roles(client,world,db_session):
    token=create_access_token(world['users']['teacher'].id,expires_delta=timedelta(seconds=-1))
    response=await client.get('/api/v1/documents',headers={'Authorization':'Bearer '+token})
    assert response.status_code==401
    token=create_access_token(world['users']['teacher'].id)
    parts=token.split('.');parts[-1]='A'+parts[-1][1:]
    assert (await client.get('/api/v1/documents',headers={'Authorization':'Bearer '+'.'.join(parts)})).status_code==401
    headers=auth(world['users']['teacher']);world['users']['teacher'].role='student';await db_session.commit()
    assert (await client.get('/api/v1/documents',headers=headers)).status_code==403


@pytest.mark.parametrize('raw',['NaN','Infinity','-Infinity','1e309'])
async def test_non_finite_calendar_input_rejected_without_echo(client,world,raw):
    response=await client.post('/api/v1/schools/school-1/disruptions',headers={**auth(world['users']['teacher']),'Content-Type':'application/json'},
                               content='{"date":"2026-11-10","reason":"PRIVATE-REASON","days_lost":'+raw+'}')
    assert response.status_code==422
    assert 'PRIVATE-REASON' not in response.text


async def test_production_configuration_rejects_insecure_defaults():
    with pytest.raises(ValueError):Settings(_env_file=None,APP_ENV='production')
    secure=dict(APP_ENV='production',DEMO_MODE=False,DEBUG=False,SECRET_KEY='a-secure-test-only-value-with-entropy-123456',
      DATABASE_URL='postgresql+asyncpg://user:password@localhost/test',BACKEND_CORS_ORIGINS=['https://app.example.test'],
      ALLOWED_HOSTS=['api.example.test'],STORAGE_LOCAL_DIR=str(__import__('pathlib').Path(__file__).resolve().parent))
    assert Settings(_env_file=None,**secure).DEMO_MODE is False
    for field,value in [('DEMO_MODE',True),('DEBUG',True),('SECRET_KEY','short'),('ALLOWED_HOSTS',['*']),('BACKEND_CORS_ORIGINS',['*'])]:
        with pytest.raises(ValueError):Settings(_env_file=None,**{**secure,field:value})


async def test_live_mode_refuses_simulated_grade_publication(client,world,monkeypatch,db_session):
    monkeypatch.setattr(settings,'DEMO_MODE',False)
    before=await db_session.scalar(select(func.count()).select_from(AssessmentSubmission))
    response=await client.post('/api/v1/ocr/review/verify',json={},headers=auth(world['users']['teacher']))
    assert response.status_code==409
    assert before==await db_session.scalar(select(func.count()).select_from(AssessmentSubmission))


async def test_readiness_failure_is_503_without_database_error_leak(client,monkeypatch):
    import backend.app.main as main
    def unavailable():raise RuntimeError('SECRET-CONNECTION-STRING')
    monkeypatch.setattr(main,'AsyncSessionLocal',unavailable)
    for path in ['/ready','/health']:
        response=await client.get(path)
        assert response.status_code==503
        assert 'SECRET-CONNECTION-STRING' not in response.text


async def test_upload_mime_cannot_disguise_executable(client,world):
    import io
    response=await client.post('/api/v1/documents/upload',headers=auth(world['users']['teacher']),
        files={'file':('payload.exe',io.BytesIO(b'MZ executable'),'text/plain')})
    assert response.status_code==400


async def test_own_class_and_document_writes_still_work(client,world,db_session):
    import io
    headers=auth(world['users']['teacher'])
    own=world['classes'][0].id
    assert (await client.get(f'/api/v1/classes/{own}/students',headers=headers)).status_code==200
    response=await client.post('/api/v1/documents/upload',headers=headers,
        files={'file':('safe.txt',io.BytesIO(b'Safe curriculum'),'text/plain')})
    assert response.status_code==201
    doc_id=response.json()['id']
    try:
        assert (await client.get(f'/api/v1/documents/{doc_id}',headers=headers)).status_code==200
        downloaded=await client.get(f'/api/v1/documents/{doc_id}/download',headers=headers)
        assert downloaded.status_code==200 and downloaded.content==b'Safe curriculum'
        assert (await client.delete(f'/api/v1/documents/{doc_id}',headers=headers)).status_code==200
    finally:
        await db_session.execute(delete(Document).where(Document.id==doc_id));await db_session.commit()


async def test_bootstrap_does_not_overwrite_accounts(db_session,monkeypatch):
    from backend.scripts.provision_admin import provision_admin
    monkeypatch.setattr(settings,'DEMO_MODE',False)
    email=uid()+'@example.com'
    user=await provision_admin(db_session,email,'Test admin','safely-provisioned-password')
    key=user.id;original=user.hashed_password
    try:
        with pytest.raises(ValueError):await provision_admin(db_session,email,'Replacement','replacement-password')
        await db_session.refresh(user)
        assert user.hashed_password==original and user.name=='Test admin'
    finally:
        await db_session.execute(delete(User).where(User.id==key));await db_session.commit()


@pytest.mark.parametrize('value',[None,'Infinity','3.5'])
async def test_invalid_ocr_awards_are_422_not_500(client,world,resources,value):
    response=await client.put(f"/api/v1/ocr/batches/{resources['batch']}/items/{resources['item']}",
      json={'question_evaluations':[{'awarded_marks':value}]},headers=auth(world['users']['admin']))
    assert response.status_code==422


async def test_concurrent_demo_grade_approval_publishes_once(client,world,assessments,db_session):
    import asyncio
    student=world['students'][0]
    batch=GradingBatch(id=uid(),school_id=student.school_id,class_id=student.class_id,subject_id=world['subject'],
        assessment_id=assessments[0],created_by=world['users']['teacher'].id,status='completed')
    item=GradingBatchItem(id=uid(),batch_id=batch.id,file_name='approved.txt',student_id=student.id,
        student_name=student.name,max_marks=10,marks_obtained=7,percentage=70,status='completed')
    db_session.add_all([batch,item]);await db_session.commit()
    bid,iid=batch.id,item.id
    path=f'/api/v1/ocr/batches/{bid}/items/{iid}/approve';headers=auth(world['users']['teacher'])
    try:
        responses=await asyncio.gather(client.post(path,headers=headers),client.post(path,headers=headers))
        assert all(response.status_code==200 for response in responses),[response.text for response in responses]
        assert responses[0].json()['submission_id']==responses[1].json()['submission_id']
        count=await db_session.scalar(select(func.count()).select_from(AssessmentSubmission).where(AssessmentSubmission.assessment_id==assessments[0]))
        assert count==1
    finally:
        await db_session.rollback()
        await db_session.execute(delete(GradingBatchItem).where(GradingBatchItem.id==iid))
        await db_session.execute(delete(GradingBatch).where(GradingBatch.id==bid));await db_session.commit()


async def test_inconsistent_legacy_batch_fails_closed_even_for_admin(client,world,resources):
    response=await client.get(f"/api/v1/ocr/batches/{resources['batch']}",headers=auth(world['users']['admin']))
    assert response.status_code==404 and 'PRIVATE-OCR-SECRET' not in response.text


async def test_used_document_deletion_is_guarded(client,world,resources,db_session):
    from backend.app.models.entities import OCRRun
    record=OCRRun(id=uid(),document_id=resources['doc'],provider='simulated',model_version='test',confidence_score=1)
    db_session.add(record);await db_session.commit();key=record.id
    try:
        response=await client.delete(f"/api/v1/documents/{resources['doc']}",headers=auth(world['users']['admin'],'school-3'))
        assert response.status_code==409
    finally:
        await db_session.execute(delete(OCRRun).where(OCRRun.id==key));await db_session.commit()


async def test_production_rejects_untrusted_host_before_database_io(tmp_path):
    import subprocess,sys,os
    env={**os.environ,'APP_ENV':'production','DEBUG':'false','DEMO_MODE':'false',
      'SECRET_KEY':'test-only-not-production-secret-unique-value-12345',
      'DATABASE_URL':'postgresql+asyncpg://test:test@127.0.0.1:1/test',
      'ALLOWED_HOSTS':'["api.example.test"]','BACKEND_CORS_ORIGINS':'["https://app.example.test"]',
      'STORAGE_LOCAL_DIR':str(tmp_path/'private')}
    script="""import asyncio
from httpx import AsyncClient,ASGITransport
from backend.app.main import app
async def check():
 async with AsyncClient(transport=ASGITransport(app=app),base_url='https://attacker.example') as client:
  response=await client.get('/health')
  assert response.status_code==400,response.status_code
asyncio.run(check())
"""
    completed=subprocess.run([sys.executable,'-B','-c',script],env=env,capture_output=True,text=True)
    assert completed.returncode==0,completed.stderr


async def test_database_errors_never_echo_or_log_parameters(client,world,caplog):
    from backend.app.api.dependencies import get_current_user
    from backend.app.db.session import get_db
    from sqlalchemy.exc import IntegrityError
    class BrokenDatabase:
        async def execute(self,*args,**kwargs):
            raise IntegrityError('PRIVATE-SQL',{'correct_answer':'PRIVATE-KEY','password':'PRIVATE-PASSWORD'},Exception('PRIVATE-CAUSE'))
    app.dependency_overrides[get_current_user]=lambda:world['users']['teacher']
    app.dependency_overrides[get_db]=lambda:BrokenDatabase()
    try:
        response=await client.get('/api/v1/documents',headers=auth(world['users']['teacher']))
        assert response.status_code==500
        for secret in ['PRIVATE-SQL','PRIVATE-KEY','PRIVATE-PASSWORD','PRIVATE-CAUSE']:
            assert secret not in response.text and secret not in caplog.text
    finally:
        app.dependency_overrides.pop(get_current_user,None);app.dependency_overrides.pop(get_db,None)


@pytest.mark.parametrize('path,body',[('/ocr/process',{'document_id':'missing'}),('/ocr/batches/missing/start',{}),('/ocr/batches/missing/items/missing/retry',{})])
async def test_live_mode_cannot_present_simulated_ocr_as_real(client,world,monkeypatch,path,body):
    monkeypatch.setattr(settings,'DEMO_MODE',False)
    response=await client.post('/api/v1'+path,json=body,headers=auth(world['users']['teacher']))
    assert response.status_code==409


async def test_account_and_class_mutations_validate_record_relationships(client,world):
    headers=auth(world['users']['admin'])
    path='/api/v1/users/'+world['users']['student'].id
    for body,code in [({'role':None},422),({'role':'unsupported'},422),({'name':None},422),({'school_id':'missing'},404)]:
        response=await client.patch(path,json=body,headers=headers)
        assert response.status_code==code
    body={'teacher_id':world['users']['teacher'].id,'teacher_name':'Untrusted name'}
    own=await client.post(f"/api/v1/classes/{world['classes'][0].id}/assignments",json=body,
                          headers=auth(world['users']['principal']))
    assert own.status_code==200 and own.json()['class_teacher_name']==world['users']['teacher'].name
    foreign=await client.post(f"/api/v1/classes/{world['classes'][1].id}/assignments",json=body,
                              headers=auth(world['users']['principal']))
    assert foreign.status_code==404


async def test_storage_errors_do_not_expose_private_paths(monkeypatch):
    import io
    import backend.app.services.storage_service as storage_module
    from starlette.datastructures import UploadFile,Headers
    def broken(*args,**kwargs):raise PermissionError('PRIVATE-DISK-PATH')
    monkeypatch.setattr(storage_module.aiofiles,'open',broken)
    result=await storage_module.storage_service.save_upload_detailed(UploadFile(
        filename='safe.txt',file=io.BytesIO(b'Safe'),headers=Headers({'content-type':'text/plain'})))
    assert result['valid'] is False and 'PRIVATE-DISK-PATH' not in result['error']


async def test_retired_legacy_proposal_approval_sends_no_cross_school_notifications(client,world,resources,db_session):
    # Legacy fixed-ratio compression approval is retired (HTTP 410); it must neither apply changes nor notify anyone.
    recipient=User(id=uid(),email=uid()+'@example.com',name='School principal',role='principal',school_id='school-3',hashed_password='unused')
    db_session.add(recipient);await db_session.commit();recipient_id=recipient.id
    before=set((await db_session.execute(select(Notification.id))).scalars().all())
    world['users']['teacher'].school_id='school-3';await db_session.commit()
    try:
        response=await client.post(f"/api/v1/curriculum-proposals/{resources['proposal']}/approve",json={'action':'approve'},
                                   headers=auth(world['users']['teacher']))
        assert response.status_code==410,response.text
        rows=list((await db_session.execute(select(Notification).where(Notification.id.not_in(before)))).scalars())
        assert rows==[]
    finally:
        await db_session.execute(delete(User).where(User.id==recipient_id));await db_session.commit()


async def test_retired_legacy_proposal_approval_is_school_scoped(client,world,resources):
    # A foreign-school educator must not learn that a legacy proposal exists (no 410 / no 404-vs-410 oracle).
    foreign=await client.post(f"/api/v1/curriculum-proposals/{resources['proposal']}/approve",json={'action':'approve'},
                              headers=auth(world['users']['teacher']))
    assert foreign.status_code in (403,404),foreign.text
    missing=await client.post(f"/api/v1/curriculum-proposals/{uid()}/approve",json={'action':'approve'},
                              headers=auth(world['users']['teacher']))
    assert missing.status_code==404


async def test_notifications_are_owner_scoped(client,world,resources,db_session):
    teacher=auth(world['users']['teacher']);parent=auth(world['users']['parent'])
    mine=await client.get('/api/v1/notifications',headers=teacher)
    assert mine.status_code==200 and 'PRIVATE-NOTIFICATION' not in mine.text
    assert (await client.post(f"/api/v1/notifications/{resources['notification']}/read",headers=teacher)).status_code==404
    assert (await client.post('/api/v1/notifications/read-all',headers=teacher)).status_code==200
    row=await db_session.get(Notification,resources['notification']);await db_session.refresh(row)
    assert row.is_read is False
    own=await client.get('/api/v1/notifications',headers=parent)
    assert 'PRIVATE-NOTIFICATION' in own.text


async def test_non_duplicate_account_integrity_fault_is_redacted_500(client,world,monkeypatch,db_session):
    import backend.app.api.v1.users as users
    monkeypatch.setattr(users,'get_password_hash',lambda password:None)
    email=uid()+'@example.com'
    response=await client.post('/api/v1/users',headers=auth(world['users']['admin']),
      json={'email':email,'name':'Fault','role':'teacher','password':'PRIVATE-TEST-PASSWORD'})
    assert response.status_code==500 and response.json()=={'detail':'Database operation failed.'}
    assert 'PRIVATE-TEST-PASSWORD' not in response.text
    assert not (await db_session.execute(select(User.id).where(User.email==email))).first()


async def test_background_failure_logs_and_response_state_are_redacted(resources,db_session,monkeypatch,caplog):
    import asyncio
    import backend.app.services.batch_grading_service as service
    class BrokenProvider:
        async def extract_document(self,*args,**kwargs):raise RuntimeError('PRIVATE-OCR-ERROR-CONTENT')
    monkeypatch.setattr(service,'get_ocr_provider',lambda name:BrokenProvider())
    await service.process_single_batch_item(resources['batch'],resources['item'],asyncio.Semaphore(1),fast_mode=True)
    row=(await db_session.execute(select(GradingBatchItem.status,GradingBatchItem.error_message).where(GradingBatchItem.id==resources['item']))).one()
    assert row.status=='failed'
    assert 'PRIVATE-OCR-ERROR-CONTENT' not in row.error_message and 'PRIVATE-OCR-ERROR-CONTENT' not in caplog.text


async def test_openapi_describes_json_login_and_http_bearer():
    spec=app.openapi()
    assert spec['components']['securitySchemes']['BearerAuth']['type']=='http'
    assert spec['components']['securitySchemes']['BearerAuth']['scheme']=='bearer'
    assert 'application/json' in spec['paths']['/api/v1/auth/login']['post']['requestBody']['content']


async def test_browser_fixture_server_cannot_target_original_project(monkeypatch,tmp_path):
    from backend.tests.browser_server import isolated_paths
    monkeypatch.setenv('LUMENEIOS_E2E_DIR',str(tmp_path/'not-browser-fixtures'))
    with pytest.raises(RuntimeError):isolated_paths()
