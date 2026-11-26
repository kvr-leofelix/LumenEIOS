"""Catalogue maintenance for teachers, and the signed-in student's own graph."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import require_roles
from backend.app.db.session import get_db
from backend.app.models.entities import ClassSection, Student, Subject, User
from backend.app.modules.differentiated_homework.student_access import require_linked_student
from backend.app.schemas.knowledge_components import (
    ClassBlueprintOut,
    ClassBlueprintRequest,
    ClassEvidenceOut,
    DemoWalkthroughOut,
    FractionSampleOut,
    KnowledgeComponentCreate,
    StudentConceptAnalysisOut,
    KnowledgeComponentOut,
    KnowledgeGraphOut,
    QuestionMapOut,
    QuestionMapRequest,
    RelationshipCreate,
    RelationshipOut,
    StudentRecommendationOut,
)
from backend.app.services import kc_demo_walkthrough, kc_fractions_sample, kc_graph_service, kc_recommendation_service
from backend.app.services.ai_gateway import AIGatewayError

router = APIRouter(tags=["Knowledge Components"])


@router.get("/knowledge-components", response_model=list[KnowledgeComponentOut])
async def list_knowledge_components(
    subject_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "principal", "teacher", authenticated=True)),
):
    return await kc_graph_service.list_components(db, subject_id)


@router.post("/knowledge-components", response_model=KnowledgeComponentOut, status_code=201)
async def create_knowledge_component(
    body: KnowledgeComponentCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "principal", "teacher", authenticated=True)),
):
    try:
        return await kc_graph_service.create_component(
            db,
            name=body.name,
            description=body.description,
            subject_id=body.subject_id,
            topic=body.topic,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Subject not found.") from None
    except ValueError as exc:
        if str(exc) == "duplicate":
            raise HTTPException(status_code=409, detail="That concept already exists for this subject and topic.") from None
        raise HTTPException(status_code=422, detail="Name and topic are required.") from None


@router.get("/knowledge-components/relationships", response_model=list[RelationshipOut])
async def list_knowledge_relationships(
    subject_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "principal", "teacher", authenticated=True)),
):
    return await kc_graph_service.list_relationships(db, subject_id)


@router.post("/knowledge-components/relationships", response_model=RelationshipOut, status_code=201)
async def create_knowledge_relationship(
    body: RelationshipCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "principal", "teacher", authenticated=True)),
):
    try:
        return await kc_graph_service.create_relationship(
            db,
            source_id=body.source_id,
            target_id=body.target_id,
            relationship=body.relationship,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Knowledge component not found.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/knowledge-components/class-evidence", response_model=ClassEvidenceOut)
async def class_knowledge_evidence(
    class_id: str = Query(min_length=1),
    subject_id: str = Query(min_length=1),
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_roles("admin", "principal", "teacher", authenticated=True)),
):
    try:
        return await kc_graph_service.class_subject_evidence(
            db, school_id=teacher.school_id, class_id=class_id, subject_id=subject_id,
        )
    except LookupError as exc:
        if str(exc) == "subject":
            raise HTTPException(status_code=422, detail="The selected class does not study this subject.") from None
        raise HTTPException(status_code=404, detail="Choose a class in your school.") from None


@router.get("/knowledge-components/demo-walkthrough", response_model=DemoWalkthroughOut)
async def preview_demo_walkthrough(
    subject_id: str = Query(min_length=1),
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_roles("admin", "principal", "teacher", authenticated=True)),
):
    try:
        return await _retry_once_if_raced(db, lambda: kc_demo_walkthrough.prepare_demo(db, teacher, subject_id))
    except LookupError as exc:
        raise _demo_error(exc) from None


@router.post("/knowledge-components/demo-walkthrough", response_model=DemoWalkthroughOut)
async def run_demo_walkthrough(
    subject_id: str = Query(min_length=1),
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_roles("admin", "principal", "teacher", authenticated=True)),
):
    try:
        return await _retry_once_if_raced(db, lambda: kc_demo_walkthrough.evaluate_demo(db, teacher, subject_id))
    except LookupError as exc:
        raise _demo_error(exc) from None


async def _retry_once_if_raced(db: AsyncSession, run):
    """The walkthrough creates its sample rows on first use. Two requests for the same subject at once (for example
    React's development double render) can both try to insert them; the loser retries once and finds the rows."""
    try:
        return await run()
    except (IntegrityError, OperationalError):
        await db.rollback()
        return await run()


def _demo_error(exc: LookupError) -> HTTPException:
    reason = str(exc)
    if reason == "subject":
        return HTTPException(status_code=404, detail="Subject not found.")
    if reason == "class":
        return HTTPException(status_code=404, detail="No class in this school studies that subject.")
    return HTTPException(status_code=404, detail="The student persona has no linked student record.")


@router.post("/knowledge-components/map-questions", response_model=QuestionMapOut)
async def map_questions_to_components(
    body: QuestionMapRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("admin", "principal", "teacher", authenticated=True)),
):
    subject = await db.get(Subject, body.subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found.")
    try:
        suggested = await kc_graph_service.suggest_question_mappings(
            db,
            subject_id=subject.id,
            subject_name=subject.name,
            questions=[question.model_dump() for question in body.questions],
            ai_provider=body.provider,
        )
    except AIGatewayError as exc:
        raise HTTPException(status_code=502, detail=exc.public_message) from exc
    catalogue = {
        row.id: row.name
        for row in await kc_graph_service.list_components(db, subject.id)
    }
    return {
        "questions": [
            {
                "question_id": question_id,
                "components": [
                    {"id": kc_id, "name": catalogue.get(kc_id, kc_id), "relevance": relevance}
                    for kc_id, relevance in links
                ],
            }
            for question_id, links in suggested.items()
        ]
    }


@router.post("/knowledge-components/class-blueprint", response_model=ClassBlueprintOut)
async def class_question_blueprint(
    body: ClassBlueprintRequest,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_roles("admin", "principal", "teacher", authenticated=True)),
):
    try:
        return await kc_recommendation_service.class_test_blueprint(
            db,
            school_id=teacher.school_id,
            class_id=body.class_id,
            subject_id=body.subject_id,
            total_marks=body.total_marks,
            question_count=body.question_count,
            duration_minutes=body.duration_minutes,
            topic=body.topic,
            slots=[slot.model_dump() for slot in body.slots],
        )
    except LookupError as exc:
        reason = str(exc)
        if reason == "subject":
            raise HTTPException(status_code=422, detail="The selected class does not study this subject.") from None
        if reason == "component":
            raise HTTPException(status_code=422, detail="Choose a concept from this subject.") from None
        raise HTTPException(status_code=404, detail="Choose a class in your school.") from None


@router.post("/knowledge-components/sample-fractions", response_model=FractionSampleOut)
async def load_fraction_sample(
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_roles("admin", "principal", "teacher", authenticated=True)),
):
    sections = list((await db.scalars(
        select(ClassSection).where(ClassSection.school_id == teacher.school_id, ClassSection.grade == 6)
    )).all())
    section = next((row for row in sections if "sub-math" in (row.subject_ids_json or [])), None)
    if section is None:
        raise HTTPException(status_code=404, detail="No Class 6 in this school studies Mathematics.")
    try:
        return await kc_fractions_sample.ensure_fraction_sample(db, teacher.school_id, section)
    except LookupError:
        raise HTTPException(status_code=404, detail="Mathematics is not available for that class.") from None


@router.get("/knowledge-components/student-analysis", response_model=StudentConceptAnalysisOut)
async def student_concept_analysis(
    student_id: str = Query(min_length=1),
    subject_id: str = Query(min_length=1),
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_roles("admin", "principal", "teacher", authenticated=True)),
):
    try:
        return await kc_graph_service.student_subject_analysis(
            db, school_id=teacher.school_id, student_id=student_id, subject_id=subject_id,
        )
    except LookupError as exc:
        if str(exc) == "subject":
            raise HTTPException(status_code=404, detail="Subject not found.") from None
        raise HTTPException(status_code=404, detail="Student not found in your school.") from None


@router.get(
    "/knowledge-components/student-recommendations",
    response_model=list[StudentRecommendationOut],
)
async def student_question_recommendations(
    student_id: str = Query(min_length=1),
    subject_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_roles("admin", "principal", "teacher", authenticated=True)),
):
    student = await db.get(Student, student_id)
    if student is None or student.school_id != teacher.school_id:
        raise HTTPException(status_code=404, detail="Student not found in your school.")
    try:
        return await kc_recommendation_service.recommend_questions_for_student(
            db, student_id=student.id, subject_id=subject_id, record=False,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Subject not found.") from None


@router.get("/students/me/question-recommendations", response_model=list[StudentRecommendationOut])
async def my_question_recommendations(
    subject_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("student", authenticated=True)),
):
    student = await require_linked_student(db, current_user)
    try:
        return await kc_recommendation_service.recommend_questions_for_student(
            db, student_id=student.id, subject_id=subject_id, record=True,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Subject not found.") from None


@router.get("/students/me/knowledge-graph", response_model=KnowledgeGraphOut)
async def my_knowledge_graph(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("student", authenticated=True)),
):
    student = await require_linked_student(db, current_user)
    return await kc_graph_service.build_student_graph(db, student.id)
