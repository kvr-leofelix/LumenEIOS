"""Answer and review operations on existing Studio assessments."""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select
from backend.app.api.dependencies import require_roles, user_school_ids
from backend.app.db.session import get_db
from backend.app.models.entities import Assessment, ClassSection
from backend.app.modules.learnsphere.access import require_class
from backend.app.modules.learnsphere.assessment_models import AssessmentResultRecord
from backend.app.modules.differentiated_homework.student_access import require_linked_student
from backend.app.schemas.assessment_results import AnswersSubmit, AssessmentReview, ResultOut
from backend.app.services.assessment_results import submit_answers, review_result, accessible_result, result_out
from backend.app.services.panchapadi import evaluate_with_guidance_retry as evaluate_saved_result

router = APIRouter(tags=["Assessments"])
student = require_roles("student", authenticated=True)
educator = require_roles("admin", "principal", "teacher", authenticated=True)
reader = require_roles("student", "parent", "admin", "principal", "teacher", authenticated=True)


@router.post("/assessments/{assessment_id}/answers", response_model=ResultOut, response_model_exclude_none=True)
async def answer_assessment(assessment_id: str, body: AnswersSubmit, background_tasks: BackgroundTasks, db=Depends(get_db), user=Depends(student)):
    result = await submit_answers(db, user, assessment_id, body)
    background_tasks.add_task(evaluate_saved_result, result["id"])
    return result


@router.post("/assessments/results/{result_id}/panchapadi/evaluate", response_model=ResultOut, response_model_exclude_none=True)
async def retry_stages(result_id: str, background_tasks: BackgroundTasks, refresh_guidance:bool=False, db=Depends(get_db), user=Depends(reader)):
    result, assessment, _ = await accessible_result(db, user, result_id)
    if user.role == "parent":
        raise HTTPException(403, "Parents can read stage feedback but cannot request AI evaluation.")
    if refresh_guidance and user.role not in {"admin","principal","teacher"}:
        raise HTTPException(403,"Only an authorized educator can refresh saved guidance.")
    if user.role in {"admin", "principal", "teacher"}:
        await require_class(db, user, result.class_id)
    background_tasks.add_task(evaluate_saved_result, result.id, refresh_guidance)
    return result_out(result, assessment, educator=user.role != "student")


@router.get("/assessments/my-results", response_model=list[ResultOut], response_model_exclude_none=True)
async def my_results(db=Depends(get_db), user=Depends(student)):
    linked = await require_linked_student(db, user)
    rows = (await db.scalars(select(AssessmentResultRecord).where(AssessmentResultRecord.student_id == linked.id))).all()
    output = []
    for r in rows:
        result, assessment, _ = await accessible_result(db, user, r.id)
        output.append(result_out(result, assessment))
    return output


@router.get("/assessments/results-for-review", response_model=list[ResultOut], response_model_exclude_none=True)
async def results_for_review(db=Depends(get_db), user=Depends(educator)):
    query = select(AssessmentResultRecord).join(ClassSection, AssessmentResultRecord.class_id == ClassSection.id)
    if user.role != "admin":
        query = query.where(ClassSection.school_id.in_(await user_school_ids(db, user)))
    if user.role == "teacher":
        query = query.where(ClassSection.class_teacher_id == user.id)
    output = []
    for r in (await db.scalars(query)).all():
        result, assessment, _ = await accessible_result(db, user, r.id)
        output.append(result_out(result, assessment, educator=True))
    return output


@router.get("/assessments/results/{result_id}", response_model=ResultOut, response_model_exclude_none=True)
async def get_result(result_id: str, db=Depends(get_db), user=Depends(reader)):
    result, assessment, _ = await accessible_result(db, user, result_id)
    is_educator = user.role in {"admin", "principal", "teacher"}
    if is_educator:
        await require_class(db, user, result.class_id)
    return result_out(result, assessment, educator=is_educator)


@router.post("/assessments/results/{result_id}/review", response_model=ResultOut, response_model_exclude_none=True)
async def review_assessment(result_id: str, body: AssessmentReview, background_tasks: BackgroundTasks, db=Depends(get_db), user=Depends(educator)):
    result = await review_result(db, user, result_id, body)
    background_tasks.add_task(evaluate_saved_result, result_id)
    return result
