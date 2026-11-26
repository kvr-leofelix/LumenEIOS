"""Real API lifecycle from score analysis through released student and parent results."""
import pytest
from sqlalchemy import select, delete, func
from backend.tests.test_homework_legacy_security import world, auth, uid
from backend.app.models.entities import Subject, AssessmentSubmission, StudentCompetencySnapshot
from backend.app.modules.differentiated_homework.models import (
    HomeworkDraftRecord, HomeworkDraftItemRecord, HomeworkAssignmentRecord,
    HomeworkSubmissionRecord, HomeworkSubmissionAnswerRecord, HomeworkEvaluationRecord, HomeworkEvaluationItemRecord,
)


@pytest.mark.asyncio
async def test_complete_homework_lifecycle(client, world, db_session):
    student=world['students'][0]
    sid=student.id
    subject=Subject(id=world['subject'],name='Integration Maths',code=uid(),grade=8)
    world['classes'][0].subject_ids_json=[subject.id]
    db_session.add(subject)
    await db_session.commit()
    teacher=auth(world['users']['teacher']); learner=auth(world['users']['student']); parent=auth(world['users']['parent'])
    initial=(student.lu_score,student.cu_score,student.au_score,student.ct_score,student.baseline_lu,student.baseline_cu)
    counts=[await db_session.scalar(select(func.count()).select_from(m)) for m in [AssessmentSubmission,StudentCompetencySnapshot]]
    async def call(method,path,body=None,headers=teacher,code=200):
        response=await client.request(method,'/api/v1'+path,json=body,headers=headers)
        assert response.status_code == code, response.text
        return response.json()
    try:
        gap=await call('GET',f'/students/{sid}/homework/gap-analysis')
        assert gap['weakest'] == ['LU']
        request={'subject_id':subject.id,'max_questions':1,'include_ai_generated':False}
        preview=await call('POST',f'/students/{sid}/homework/preview',request)
        assert preview['question_count'] == 1
        draft=await call('POST',f'/students/{sid}/homework/drafts',
                         {**request,'expected_question_ids':[q['question_id'] for q in preview['items']]},code=201)
        await call('POST',f"/homework/drafts/{draft['id']}/approve")
        assignment=await call('POST',f"/homework/drafts/{draft['id']}/assign",code=201)
        aid=assignment['id']; base=f'/students/me/homework/assignments/{aid}'
        detail=await call('GET',base,headers=learner)
        assert 'correct_answer' not in str(detail) and 'marking_rubric' not in str(detail)
        submission=await call('PUT',base+'/submission',{'answers':[{'position':1,'selected_option_index':0}]},headers=learner,code=201)
        submission=await call('PUT',base+'/submission',{'expected_version':submission['version'],
                         'answers':[{'position':1,'selected_option_index':1}]},headers=learner)
        await call('POST',base+'/submission/submit',{'expected_version':submission['version']},headers=learner)
        inspected=await call('GET',f'/homework/assignments/{aid}/submissions/{sid}')
        assert inspected['status'] == 'submitted'
        grading=f'/homework/assignments/{aid}/evaluation'
        evaluation=await call('POST',grading,code=201)
        assert evaluation['items'][0]['correct_answer'] == 'SECRET-KEY-school-1'
        evaluation=await call('PATCH',grading+'/items',{'expected_version':evaluation['version'],
            'items':[{'position':1,'awarded_marks':1,'feedback':'Check the units.'}]})
        evaluation=await call('POST',grading+'/finalize',{'expected_version':evaluation['version']})
        parentpath=f'/parents/me/students/{sid}/homework/assignments/{aid}/evaluation'
        await call('GET',base+'/evaluation',headers=learner,code=404)
        await call('GET',parentpath,headers=parent,code=404)
        await call('POST',grading+'/release',{'expected_version':evaluation['version']})
        result=await call('GET',base+'/evaluation',headers=learner)
        assert result == await call('GET',parentpath,headers=parent)
        assert result['total_awarded'] == 1
        assert result['items'][0]['feedback'] == 'Check the units.'
        assert not any(word in str(result) for word in ['SECRET','correct_answer','marking_rubric','marked_by','version'])
        await db_session.refresh(student)
        # Released homework is graded evidence: it may move the live parameters, never the baselines,
        # adds exactly one progress snapshot and creates no assessment submission.
        assert initial[4:] == (student.baseline_lu,student.baseline_cu)
        assert counts[0] == await db_session.scalar(select(func.count()).select_from(AssessmentSubmission))
        assert counts[1] + 1 == await db_session.scalar(select(func.count()).select_from(StudentCompetencySnapshot))
    finally:
        # These rows exist only inside the isolated test DB. Delete dependants first.
        await db_session.rollback()
        drafts=select(HomeworkDraftRecord.id).where(HomeworkDraftRecord.student_id==sid)
        submissions=select(HomeworkSubmissionRecord.id).where(HomeworkSubmissionRecord.student_id==sid)
        evaluations=select(HomeworkEvaluationRecord.id).where(HomeworkEvaluationRecord.student_id==sid)
        await db_session.execute(delete(StudentCompetencySnapshot).where(StudentCompetencySnapshot.student_id==sid))
        await db_session.execute(delete(HomeworkEvaluationItemRecord).where(HomeworkEvaluationItemRecord.evaluation_id.in_(evaluations)))
        await db_session.execute(delete(HomeworkEvaluationRecord).where(HomeworkEvaluationRecord.student_id==sid))
        await db_session.execute(delete(HomeworkSubmissionAnswerRecord).where(HomeworkSubmissionAnswerRecord.submission_id.in_(submissions)))
        await db_session.execute(delete(HomeworkSubmissionRecord).where(HomeworkSubmissionRecord.student_id==sid))
        await db_session.execute(delete(HomeworkAssignmentRecord).where(HomeworkAssignmentRecord.student_id==sid))
        await db_session.execute(delete(HomeworkDraftItemRecord).where(HomeworkDraftItemRecord.draft_id.in_(drafts)))
        await db_session.execute(delete(HomeworkDraftRecord).where(HomeworkDraftRecord.student_id==sid))
        await db_session.execute(delete(Subject).where(Subject.id==world['subject']))
        await db_session.commit()
