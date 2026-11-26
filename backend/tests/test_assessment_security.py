"""Authorization of formal assessment authoring, results and grade writes."""
import hashlib
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from backend.tests.test_homework_legacy_security import world, auth, uid
from backend.app.models.entities import Assessment, AssessmentSubmission, StudentCompetencySnapshot, Student, AuditEvent
from backend.app.core.config import settings
from backend.app.core.security import verify_password, create_refresh_token

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def assessments(world, db_session):
    rows = [Assessment(id=uid(), school_id=c.school_id, class_id=c.id, subject_id=world['subject'],
            title='Assessment', cycle_number=1, date='2026-11-20', duration_minutes=45, total_marks=10,
            status='scheduled', competency_focus_json=['LU'], questions_json=[{'correct_answer':'FORMAL-SECRET',
            'marking_rubric':'FORMAL-RUBRIC','text':'Question'}]) for c in world['classes']]
    db_session.add_all(rows)
    await db_session.commit()
    ids = [r.id for r in rows]
    student_ids = [s.id for s in world['students']]
    yield ids
    await db_session.rollback()
    await db_session.execute(delete(AssessmentSubmission).where(AssessmentSubmission.assessment_id.in_(ids)))
    await db_session.execute(delete(StudentCompetencySnapshot).where(StudentCompetencySnapshot.student_id.in_(student_ids)))
    await db_session.execute(delete(Assessment).where(Assessment.id.in_(ids)))
    await db_session.commit()


def grade(student):
    return dict(student_id=student, marks_obtained=7,total_marks=10,lu_score=50,cu_score=60,
                au_score=70,ct_score=80,feedback='Teacher feedback')


@pytest.mark.parametrize('role',[None,'student','parent','teacher','principal','admin'])
async def test_assessment_reads_protect_keys_and_records(client, world, assessments, role, monkeypatch):
    monkeypatch.setattr(settings,'DEMO_MODE',True)
    headers=auth(world['users'][role]) if role else {}
    own_class=world['classes'][0].id
    paths=['/api/v1/assessments',f'/api/v1/classes/{own_class}/assessments',
           f'/api/v1/assessments/{assessments[0]}/submissions']
    for path in paths:
        response=await client.get(path,headers=headers)
        assert response.status_code == (401 if role is None else 403 if role in {'student','parent'} else 200)
        if role in {None,'student','parent'}:
            assert 'FORMAL-SECRET' not in response.text
            assert 'FORMAL-RUBRIC' not in response.text
    if role in {'teacher','principal','admin'}:
        rows=(await client.get('/api/v1/assessments',headers=headers)).json()
        assert assessments[0] in [row['id'] for row in rows]
        assert assessments[1] not in [row['id'] for row in rows]
        for path in [f"/api/v1/classes/{world['classes'][1].id}/assessments",
                     f'/api/v1/assessments/{assessments[1]}/submissions']:
            assert (await client.get(path,headers=headers)).status_code == 404


@pytest.mark.parametrize('role',[None,'student','parent','teacher','principal','admin'])
async def test_grade_requires_educator_and_matching_student(client, world, assessments, db_session, role):
    headers=auth(world['users'][role]) if role else {}
    student=world['students'][0]
    fields=['lu_score','cu_score','au_score','ct_score','overall_score','baseline_lu','baseline_cu','baseline_au','baseline_ct','baseline_overall']
    before=[getattr(student,f) for f in fields]
    models=[AssessmentSubmission,StudentCompetencySnapshot,AuditEvent]
    counts=[await db_session.scalar(select(func.count()).select_from(m)) for m in models]
    path=f'/api/v1/assessments/{assessments[0]}/submissions'
    denied_student=world['students'][1].id if role in {'teacher','principal','admin'} else student.id
    response=await client.post(path,json=grade(denied_student),headers=headers)
    assert response.status_code == (401 if role is None else 403 if role in {'student','parent'} else 404)
    await db_session.refresh(student)
    assert before == [getattr(student,f) for f in fields]
    assert counts == [await db_session.scalar(select(func.count()).select_from(m)) for m in models]


@pytest.mark.parametrize('role',['teacher','principal','admin'])
async def test_authorized_grade_keeps_existing_academic_rules(client, world, assessments, db_session, role):
    student=world['students'][0]
    before_baseline=(student.baseline_lu,student.baseline_cu,student.baseline_au,student.baseline_ct)
    response=await client.post(f'/api/v1/assessments/{assessments[0]}/submissions',
                               json=grade(student.id),headers=auth(world['users'][role]))
    assert response.status_code == 200, response.text
    assert response.json()['percentage'] == 70
    assert response.json()['scores'] == {'LU':50,'CU':60,'AU':70,'CT':80,'overall':65}
    await db_session.refresh(student)
    assert student.lu_score == 50
    assert before_baseline == (student.baseline_lu,student.baseline_cu,student.baseline_au,student.baseline_ct)


@pytest.mark.parametrize('role',[None,'student','parent','teacher','principal','admin'])
async def test_assessment_creation_scope(client, world, assessments, role):
    headers=auth(world['users'][role]) if role else {}
    body=dict(subject_id=world['subject'],title='Test',date='2026-12-01',questions=[],competency_focus=['LU'])
    response=await client.post(f"/api/v1/classes/{world['classes'][1].id}/assessments",json=body,headers=headers)
    assert response.status_code == (401 if role is None else 403 if role in {'student','parent'} else 404)


async def test_admin_explicit_school_and_class_mismatch(client, world, assessments):
    response=await client.get('/api/v1/assessments',headers=auth(world['users']['admin'],'school-3'))
    assert [r['id'] for r in response.json()] == [assessments[1]]
    body=dict(subject_id=world['subject'],title='Test',date='2026-12-01',questions=[],competency_focus=['LU'],class_id='wrong')
    response=await client.post(f"/api/v1/classes/{world['classes'][0].id}/assessments",json=body,
                               headers=auth(world['users']['teacher']))
    assert response.status_code == 422


async def test_refresh_token_cannot_authorize_api(client, world):
    response=await client.get('/api/v1/assessments/question-bank',headers={
        'Authorization':'Bearer '+create_refresh_token(world['users']['admin'].id)})
    assert response.status_code == 401


async def test_production_password_does_not_accept_stored_hash(monkeypatch):
    monkeypatch.setattr(settings,'DEMO_MODE',False)
    password='test-legacy-password'
    stored=hashlib.sha256(password.encode()).hexdigest()
    assert verify_password(password,stored)
    assert not verify_password(stored,stored)
    assert not verify_password('plaintext-stored','plaintext-stored')
    assert not verify_password('demo123',stored)


@pytest.mark.parametrize('demo',[False,True])
async def test_startup_seeds_only_in_explicit_demo_mode(monkeypatch,demo):
    import backend.app.main as main
    called=[]
    async def init(): pass
    async def seed(session): called.append('seed')
    monkeypatch.setattr(settings,'DEMO_MODE',demo)
    monkeypatch.setattr(main,'init_db',init)
    monkeypatch.setattr(main,'seed_database_if_empty',seed)
    async with main.lifespan(main.app): pass
    assert called == (['seed'] if demo else [])


@pytest.mark.parametrize('demo',[False,True])
async def test_empty_live_bank_has_no_bundled_demo_answer(monkeypatch, demo):
    from backend.app.api.v1.assessments import get_question_bank
    class EmptyResult:
        def scalars(self): return self
        def all(self): return []
    class EmptyDatabase:
        async def execute(self, query): return EmptyResult()
    monkeypatch.setattr(settings,'DEMO_MODE',demo)
    rows=await get_question_bank(subject_id='sub-math',db=EmptyDatabase(),educator=None,school_id='school-1')
    assert rows == []  # Empty banks stay empty in both modes; do not invent a saved item.
