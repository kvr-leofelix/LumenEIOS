import hashlib
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from backend.app.api.dependencies import require_roles, user_school_ids
from backend.app.db.session import get_db
from backend.app.models.entities import ClassSection, School, Subject, utc_now
from backend.app.modules.differentiated_homework.student_access import require_linked_student
from backend.app.services.llm_service import qwen_question_studio, QwenQuestionStudioUnavailable, QwenQuestionStudioInferenceError
from .access import authorized_students, require_student, require_class
from .models import LearningTopic, LearningActivity, LearningAssignment, LearningAttempt, LearningEvidence
from .schemas import TopicCreate, ActivityCreate, AssignmentCreate, AttemptCreate, Review
from . import schemas as output
from backend.app.schemas.panchapadi import Stage, StageHistory, PanchapadiHistory
from backend.app.services.panchapadi import stage_history
from .evidence_service import support, journey, timestamp

router = APIRouter(prefix="/learnsphere", tags=["LearnSphere"])
actor = require_roles("admin", "principal", "teacher", "parent", "student", authenticated=True)
educator = require_roles("admin", "principal", "teacher", authenticated=True)


def topic_out(t):
    return {"id": t.id, "school_id": t.school_id, "class_id": t.class_id,
            "subject_id": t.subject_id, "title": t.title}


def activity_out(a):
    return {key: getattr(a, key) for key in ("id", "topic_id", "kind", "title", "instructions", "rubric", "competency", "stage", "version")}


def attempt_out(a):
    return {"id": a.id, "assignment_id": a.assignment_id, "response": a.response, "hints": a.hints,
            "submitted_at": timestamp(a.submitted_at), "evaluations": a.evaluations, "completed": a.completed, "version": a.version}


async def commit(db):
    try:
        await db.commit()
    except (IntegrityError, StaleDataError):
        await db.rollback()
        raise HTTPException(409, "This record changed or the request was already processed. Reload before retrying.")


async def topic_access(db, user, topic_id):
    topic = await db.get(LearningTopic, topic_id)
    if not topic:
        raise HTTPException(404, "Topic not found.")
    section = await require_class(db, user, topic.class_id)
    if section.school_id != topic.school_id or topic.subject_id not in (section.subject_ids_json or []):
        raise HTTPException(409, "Topic no longer matches the class and subject.")
    return topic


async def assignment_access(db, user, assignment_id):
    a = await db.get(LearningAssignment, assignment_id)
    if not a:
        raise HTTPException(404, "Assignment not found.")
    st = await require_student(db, user, a.student_id)
    if st.school_id != a.school_id or a.snapshot["class_id"] != st.class_id:
        raise HTTPException(404, "Assignment unavailable for the student's current class.")
    return a


async def attempt_access(db, user, attempt_id):
    at = await db.get(LearningAttempt, attempt_id)
    if not at:
        raise HTTPException(404, "Attempt not found.")
    a = await assignment_access(db, user, at.assignment_id)
    return at, a


@router.get("/scope", response_model=output.ScopeOut)
async def scope(db=Depends(get_db), user=Depends(actor)):
    students = await authorized_students(db, user)
    sections = {}
    if user.role in {"teacher", "principal", "admin"}:
        query = select(ClassSection)
        if user.role != "admin":
            query = query.where(ClassSection.school_id.in_(await user_school_ids(db, user)))
        if user.role == "teacher":
            query = query.where(ClassSection.class_teacher_id == user.id)
        sections = {c.id: c for c in (await db.scalars(query)).all()}
    else:
        for st in students:
            sections[st.class_id] = await db.get(ClassSection, st.class_id)
    subjects = {s.id: s.name for s in (await db.scalars(select(Subject))).all()}
    schools = (await db.scalars(select(School).where(School.id.in_({c.school_id for c in sections.values() if c})))).all()
    return {"students": [{"id": s.id, "name": s.name, "class_id": s.class_id, "school_id": s.school_id} for s in students],
            "schools": [{"id": s.id, "name": s.name} for s in schools],
            "classes": [{"id": c.id, "name": c.name, "school_id": c.school_id,
                "subjects": [{"id": i, "name": subjects.get(i, i)} for i in (c.subject_ids_json or [])]} for c in sections.values() if c]}


@router.get("/students/{student_id}/support", response_model=output.SupportOut)
async def student_support(student_id: str, db=Depends(get_db), user=Depends(actor)):
    await require_student(db, user, student_id)
    return await support(db, student_id)


@router.get("/students/{student_id}/assessments")
async def assessments_for_support(student_id:str,db=Depends(get_db),user=Depends(actor)):
    from backend.app.services.assessment_guidance import student_assessments
    return await student_assessments(db,user,student_id)


@router.get("/students/{student_id}/assessments/{assessment_id}/guidance")
async def assessment_support_guidance(student_id:str,assessment_id:str,db=Depends(get_db),user=Depends(actor)):
    from backend.app.services.assessment_guidance import question_guidance
    return await question_guidance(db,user,student_id,assessment_id)


from .automation import CompetencyReview


@router.post("/students/{student_id}/assessments/{assessment_id}/competencies")
async def confirm_question_competencies(student_id: str, assessment_id: str, body: CompetencyReview,
        background_tasks: BackgroundTasks, db=Depends(get_db), user=Depends(educator)):
    from .automation import review_competencies
    from backend.app.services.panchapadi import evaluate_with_guidance_retry
    from backend.app.services.assessment_guidance import question_guidance
    record = await review_competencies(db, user, student_id, assessment_id, body)
    background_tasks.add_task(evaluate_with_guidance_retry, record.id, True)
    return await question_guidance(db, user, student_id, assessment_id)


@router.get("/students/{student_id}/journey", response_model=output.JourneyOut)
async def student_journey(student_id: str, db=Depends(get_db), user=Depends(actor)):
    await require_student(db, user, student_id)
    return await journey(db, student_id)


@router.get("/students/{student_id}/panchapadi", response_model=PanchapadiHistory)
async def panchapadi_progress(student_id: str, include_provisional:bool=False, db=Depends(get_db), user=Depends(actor)):
    await require_student(db, user, student_id)
    return await stage_history(db, student_id, include_provisional)


@router.get("/students/{student_id}/panchapadi/{stage}", response_model=StageHistory)
async def panchapadi_stage_progress(student_id: str, stage: Stage, include_provisional:bool=False, db=Depends(get_db), user=Depends(actor)):
    await require_student(db, user, student_id)
    history = await stage_history(db, student_id, include_provisional)
    return next(graph for graph in history["graphs"] if graph["stage"] == stage)


@router.get("/summary", response_model=output.SummaryOut)
async def summary(db=Depends(get_db), user=Depends(educator)):
    students = await authorized_students(db, user)
    # Aggregate participation only; no averages of default or unverified scores.
    ids = [s.id for s in students]
    assignments = list((await db.scalars(select(LearningAssignment).where(LearningAssignment.student_id.in_(ids)))).all())
    completed = set((await db.scalars(select(LearningAttempt.assignment_id).where(
        LearningAttempt.assignment_id.in_([a.id for a in assignments]), LearningAttempt.completed == True))).all())
    return {"students": len(students), "assignments": len(assignments), "completed_assignments": len(completed)}


@router.get("/topics", response_model=list[output.TopicOut])
async def topics(class_id: str, db=Depends(get_db), user=Depends(educator)):
    await require_class(db, user, class_id)
    return [topic_out(t) for t in (await db.scalars(select(LearningTopic).where(LearningTopic.class_id == class_id))).all()]


@router.post("/topics", status_code=201, response_model=output.TopicOut)
async def create_topic(body: TopicCreate, db=Depends(get_db), user=Depends(educator)):
    section = await require_class(db, user, body.class_id)
    if body.subject_id not in (section.subject_ids_json or []) or not await db.get(Subject, body.subject_id):
        raise HTTPException(422, "Choose a subject studied by this class.")
    t = LearningTopic(**body.model_dump(), school_id=section.school_id, created_by=user.id)
    db.add(t)
    await commit(db)
    return topic_out(t)


@router.get("/activities", response_model=list[output.ActivityOut])
async def activities(class_id: str, db=Depends(get_db), user=Depends(educator)):
    await require_class(db, user, class_id)
    return [activity_out(a) for a in (await db.scalars(select(LearningActivity).join(LearningTopic).where(
        LearningTopic.class_id == class_id))).all()]


@router.post("/activities", status_code=201, response_model=output.ActivityOut)
async def create_activity(body: ActivityCreate, db=Depends(get_db), user=Depends(educator)):
    await topic_access(db, user, body.topic_id)
    a = LearningActivity(**body.model_dump(), created_by=user.id)
    db.add(a)
    await commit(db)
    return activity_out(a)


@router.put("/activities/{activity_id}", response_model=output.ActivityOut)
async def update_activity(activity_id: str, body: ActivityCreate, db=Depends(get_db), user=Depends(educator)):
    a = await db.get(LearningActivity, activity_id)
    if not a:
        raise HTTPException(404, "Activity not found.")
    await topic_access(db, user, a.topic_id)
    await topic_access(db, user, body.topic_id)
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    a.version += 1
    await commit(db)
    return activity_out(a)


@router.post("/activities/{activity_id}/assignments", status_code=201, response_model=output.AssignmentCreated)
async def assign(activity_id: str, body: AssignmentCreate, db=Depends(get_db), user=Depends(educator)):
    activity = await db.get(LearningActivity, activity_id)
    if not activity:
        raise HTTPException(404, "Activity not found.")
    topic = await topic_access(db, user, activity.topic_id)
    result = []
    for student_id in dict.fromkeys(body.student_ids):
        st = await require_student(db, user, student_id)
        if st.school_id != topic.school_id or st.class_id != topic.class_id:
            raise HTTPException(422, "Activity and student must share a school and class.")
        if body.intervention_for:
            previous = await assignment_access(db, user, body.intervention_for)
            if previous.student_id != st.id:
                raise HTTPException(422, "Follow-up must concern the same student.")
        existing = await db.scalar(select(LearningAssignment).where(LearningAssignment.assigned_by == user.id,
            LearningAssignment.request_key == body.request_key, LearningAssignment.student_id == st.id))
        if existing:
            if existing.activity_id != activity.id:
                raise HTTPException(409, "Request key already belongs to another activity.")
            result.append(existing.id)
            continue
        a = LearningAssignment(id=str(uuid.uuid4()), activity_id=activity.id, student_id=st.id, school_id=st.school_id,
            assigned_by=user.id, request_key=body.request_key, due_at=body.due_at, intervention_for=body.intervention_for,
            snapshot={**activity_out(activity), "topic_title": topic.title, "subject_id": topic.subject_id, "class_id": topic.class_id})
        db.add(a)
        result.append(a.id)
    await commit(db)
    return {"assignment_ids": result}


@router.get("/assignments", response_model=list[output.AssignmentOut])
async def assignments(student_id: str, db=Depends(get_db), user=Depends(actor)):
    student = await require_student(db, user, student_id)
    rows = (await db.scalars(select(LearningAssignment).where(LearningAssignment.student_id == student_id)
        .order_by(LearningAssignment.assigned_at.desc()))).all()
    # A transfer must not make the entire list fail because of one old-class assignment.
    rows = [a for a in rows if a.school_id == student.school_id and a.snapshot["class_id"] == student.class_id]
    attempts_by_assignment = {}
    for at in (await db.scalars(select(LearningAttempt).where(
        LearningAttempt.assignment_id.in_([a.id for a in rows])).order_by(LearningAttempt.submitted_at))).all():
        attempts_by_assignment.setdefault(at.assignment_id, []).append(at)
    output = []
    for a in rows:
        attempts = attempts_by_assignment.get(a.id, [])
        snapshot = dict(a.snapshot)
        if user.role in {"student", "parent"} and snapshot.get("assessment_result_id"):
            snapshot["rubric"] = "Teacher-only assessment criteria; explain your own reasoning in the submitted response."
        output.append({"id": a.id, "student_id": a.student_id, "snapshot": snapshot, "assigned_at": timestamp(a.assigned_at),
            "due_at": timestamp(a.due_at) if a.due_at else None, "intervention_for": a.intervention_for, "attempts": [attempt_out(at) for at in attempts]})
    return output


@router.post("/assignments/{assignment_id}/attempts", status_code=201, response_model=output.AttemptOut)
async def submit(assignment_id: str, body: AttemptCreate, db=Depends(get_db), user=Depends(actor)):
    if user.role != "student":
        raise HTTPException(403, "Only the linked student can submit a response.")
    a = await assignment_access(db, user, assignment_id)
    st = await require_linked_student(db, user)
    if a.student_id != st.id:
        raise HTTPException(404, "Assignment not found.")
    existing = await db.scalar(select(LearningAttempt).where(LearningAttempt.assignment_id == a.id,
        LearningAttempt.request_key == body.request_key))
    if existing:
        if existing.response != body.response or existing.hints != body.hints:
            raise HTTPException(409, "This request key already identifies a different response.")
        return attempt_out(existing)
    at = LearningAttempt(assignment_id=a.id, **body.model_dump())
    db.add(at)
    await commit(db)
    return attempt_out(at)


@router.post("/attempts/{attempt_id}/evaluate", response_model=output.AttemptOut)
async def evaluate(attempt_id: str, db=Depends(get_db), user=Depends(actor)):
    at, assignment = await attempt_access(db, user, attempt_id)
    if user.role == "parent":
        raise HTTPException(403, "Parents can view feedback but cannot request evaluation.")
    if assignment.snapshot["kind"] != "teach_back":
        raise HTTPException(422, "AI evaluation is available only for teach-back activities.")
    # Repeated successful evaluations return the persisted revision; failures remain retryable.
    if any(r["kind"] == "ai" and r.get("feedback") for r in at.evaluations):
        return attempt_out(at)
    try:
        feedback = await qwen_question_studio.evaluate_teach_back(assignment.snapshot["instructions"],
            assignment.snapshot["rubric"], at.response)
        revision = {"kind": "ai", "date": utc_now().isoformat(), "feedback": feedback.model_dump()}
    except (QwenQuestionStudioUnavailable, QwenQuestionStudioInferenceError, ValueError) as exc:
        revision = {"kind": "ai_failure", "date": utc_now().isoformat(), "error": str(exc)}
        at.evaluations = [*at.evaluations, revision]
        await commit(db)
        raise HTTPException(503 if isinstance(exc, QwenQuestionStudioUnavailable) else 502,
                            "Your response is saved. AI evaluation failed: " + str(exc))
    at.evaluations = [*at.evaluations, revision]
    await commit(db)
    return attempt_out(at)


@router.post("/attempts/{attempt_id}/review", response_model=output.AttemptOut)
async def review(attempt_id: str, body: Review, db=Depends(get_db), user=Depends(educator)):
    at, assignment = await attempt_access(db, user, attempt_id)
    if at.version != body.expected_version:
        raise HTTPException(409, "Attempt changed. Reload before reviewing.")
    revision_id = uuid.uuid4().hex
    at.evaluations = [*at.evaluations, {"kind": "teacher", "revision_id": revision_id,
        "date": utc_now().isoformat(), "feedback": body.feedback, "outcome": body.outcome,
        "reviewer_id": user.id, "completed": body.completed}]
    at.completed = body.completed
    basis = hashlib.sha256(json.dumps({k: assignment.snapshot[k] for k in
        ("rubric", "competency", "instructions")}, sort_keys=True).encode()).hexdigest()
    for observation in body.observations:
        db.add(LearningEvidence(student_id=assignment.student_id, assignment_id=assignment.id, attempt_id=at.id,
            source="teacher_review", observation_key=revision_id + ":" + observation.key[:60],
            competency=assignment.snapshot["competency"], score=observation.score, maximum=observation.maximum,
            correct=observation.correct, provenance="confirmed", scoring_basis=basis))
    await commit(db)
    return attempt_out(at)
