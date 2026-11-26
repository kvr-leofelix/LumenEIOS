from fastapi import APIRouter, Depends
from backend.app.api.dependencies import reject_non_finite_json
from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.schools import router as schools_router
from backend.app.api.v1.users import router as users_router
from backend.app.api.v1.teachers import router as teachers_router
from backend.app.api.v1.classes import router as classes_router
from backend.app.api.v1.calendar import router as calendar_router
from backend.app.api.v1.calendar_hub import router as calendar_hub_router
from backend.app.api.v1.assessments import router as assessments_router
from backend.app.api.v1.scan_grading import router as scan_grading_router
from backend.app.api.v1.workspace import router as workspace_router
from backend.app.api.v1.assessment_results import router as assessment_results_router
from backend.app.api.v1.competencies import router as competencies_router
from backend.app.modules.differentiated_homework.router import router as homework_router
from backend.app.modules.student_progress.router import router as student_progress_router
from backend.app.modules.interventions.router import router as interventions_router
from backend.app.api.v1.curriculum import router as curriculum_router
from backend.app.api.v1.time_aware import router as time_aware_router
from backend.app.api.v1.documents import router as documents_router
from backend.app.api.v1.ocr import router as ocr_router
from backend.app.api.v1.model_registry import router as model_registry_router
from backend.app.api.v1.notifications import router as notifications_router
from backend.app.api.v1.reports import router as reports_router
from backend.app.api.v1.audit import router as audit_router
from backend.app.api.v1.admin import router as admin_router
from backend.app.api.v1.onboarding import router as onboarding_router
from backend.app.api.v1.assistant import router as assistant_router
from backend.app.api.v1.developer import router as developer_router
from backend.app.api.v1.ncert import router as ncert_router
from backend.app.api.v1.planning import router as planning_router
from backend.app.api.v1.teacher_planning import router as teacher_plan_router, oversight as plan_oversight_router, logs as plan_logs_router, calendar_router as plan_calendar_router

from backend.app.api.v1.plans import router as plans_router
from backend.app.api.v1.knowledge_graph import router as knowledge_graph_router

api_router = APIRouter(dependencies=[Depends(reject_non_finite_json)])
from backend.app.modules.learnsphere.router import router as learnsphere_router
api_router.include_router(learnsphere_router)

api_router.include_router(auth_router)
api_router.include_router(schools_router)
api_router.include_router(users_router)
api_router.include_router(teachers_router)
api_router.include_router(classes_router)
api_router.include_router(calendar_router)
api_router.include_router(calendar_hub_router)
api_router.include_router(scan_grading_router)
api_router.include_router(workspace_router)
api_router.include_router(assessments_router)
api_router.include_router(assessment_results_router)
api_router.include_router(competencies_router)
api_router.include_router(homework_router)
api_router.include_router(student_progress_router)
api_router.include_router(interventions_router)
api_router.include_router(curriculum_router)
api_router.include_router(time_aware_router)
api_router.include_router(documents_router)
api_router.include_router(ocr_router)
api_router.include_router(model_registry_router)
api_router.include_router(notifications_router)
api_router.include_router(reports_router)
api_router.include_router(audit_router)
api_router.include_router(admin_router)
api_router.include_router(onboarding_router)
api_router.include_router(assistant_router)
api_router.include_router(developer_router)
api_router.include_router(ncert_router)
api_router.include_router(planning_router)
api_router.include_router(teacher_plan_router)
api_router.include_router(plan_oversight_router)
api_router.include_router(plan_logs_router)
api_router.include_router(plan_calendar_router)
api_router.include_router(plans_router)
api_router.include_router(knowledge_graph_router)
