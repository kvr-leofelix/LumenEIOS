from backend.app.lib.question_content import option_identity
import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user, require_roles, oauth2_scheme, get_current_school_context
from backend.app.db.session import get_db
from backend.app.core.config import settings
from backend.app.models.entities import (
    Assessment,
    School,
    TeacherAssignment,
    AssignmentOcrUpload,
    ClassSection,
    AssessmentSubmission,
    QuestionBankItem,
    Document,
    Student,
    StudentOcrHistory,
    StudentCompetencySnapshot,
    User,
    AuditEvent,
    Notification,
    utc_now,
)
from backend.app.schemas.assessments import (
    AssessmentCreate,
    AssessmentOut,
    AssignmentTarget,
    UploadAssignment,
    SubmissionCreate,
    SubmissionOut,
    GenerateQuestionsRequest,
    RegenerateQuestionRequest,
    QuestionCreateRequest,
    QuestionUpdateRequest,
)
from backend.app.services import kc_graph_service
from backend.app.services.llm_service import (
    QwenQuestionStudioInferenceError,
    QwenQuestionStudioInputError,
    QwenQuestionStudioUnavailable,
    llm_service,
    qwen_question_studio,
)
from backend.app.models.entities import Subject
from backend.app.services import ai_gateway
from backend.app.core.logging import logger
from backend.app.services.ai_gateway import AIGatewayError, AINotConfigured, AIProviderTimeout
from backend.app.services.ai_question_service import (
    AIGenerationPreview,
    AIQuestionRequest,
    AIQuestionSaveRequest,
    generate_question_preview,
)
from backend.app.services.progress import report_progress, stream_job
from backend.app.services.storage_service import storage_service
from backend.app.services.web_source import WebSourceError, fetch_web_source, normalize_urls
from backend.app.services.assessment_audience import upload_assignments, validate_assignment_target


async def _require_question_bank_login(token: Optional[str] = Depends(oauth2_scheme)) -> None:
    # Keys require a real login, including when global DEMO_MODE is enabled.
    if not token:
        raise HTTPException(status_code=401, detail="Authentication token required.",
                            headers={"WWW-Authenticate": "Bearer"})


# Every assessment route can expose teaching data or change academic records.
router = APIRouter(tags=["Assessments"], dependencies=[Depends(_require_question_bank_login)])


async def _assessment_class(db: AsyncSession, class_id: str, school_id: str) -> ClassSection:
    record = await db.get(ClassSection, class_id)
    if record is None or record.school_id != school_id:
        raise HTTPException(status_code=404, detail="Class not found.")
    return record


async def _scoped_assessment(db: AsyncSession, assessment_id: str, school_id: str) -> Assessment:
    record = (await db.execute(select(Assessment).filter(
        Assessment.id == assessment_id, Assessment.school_id == school_id))).scalars().first()
    if record is None:
        raise HTTPException(status_code=404, detail="Assessment not found.")
    await _assessment_class(db, record.class_id, school_id)
    return record


@router.get("/assessments", response_model=List[AssessmentOut])
async def list_all_assessments(
    class_id: Optional[str] = None,
    school_id: Optional[str] = None,
    subject_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
    active_school: str = Depends(get_current_school_context),
):
    query = select(Assessment).filter(Assessment.school_id == active_school)
    if class_id:
        query = query.filter(Assessment.class_id == class_id)
    if school_id:
        query = query.filter(Assessment.school_id == school_id)
    if subject_id:
        query = query.filter(Assessment.subject_id == subject_id)
    res = await db.execute(query.order_by(Assessment.cycle_number))
    return res.scalars().all()


@router.get("/classes/{class_id}/assessments", response_model=List[AssessmentOut])
async def list_class_assessments(
    class_id: str,
    subject_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    await _assessment_class(db, class_id, school_id)
    query = select(Assessment).filter(Assessment.class_id == class_id, Assessment.school_id == school_id)
    if subject_id:
        query = query.filter(Assessment.subject_id == subject_id)
    res = await db.execute(query.order_by(Assessment.cycle_number))
    return res.scalars().all()




@router.get("/assessments/targets", response_model=List[AssignmentTarget])
async def get_assignment_targets(
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    school = await db.get(School, school_id)
    query = select(ClassSection).where(ClassSection.school_id == school_id)
    taught = None
    if educator.role == "teacher":
        taught = {(row.class_id, row.subject_id) for row in (await db.scalars(select(TeacherAssignment).where(
            TeacherAssignment.teacher_id == educator.id, TeacherAssignment.school_id == school_id))).all()}
        query = query.where(or_(ClassSection.class_teacher_id == educator.id,
                               ClassSection.id.in_([class_id for class_id, _ in taught])))
    sections = (await db.scalars(query.order_by(ClassSection.name, ClassSection.id))).all()
    subject_ids = {subject_id for section in sections for subject_id in section.subject_ids_json}
    subjects = {
        subject.id: subject.name
        for subject in (await db.scalars(select(Subject).where(Subject.id.in_(subject_ids)))).all()
    } if subject_ids else {}
    return [
        {
            "id": section.id,
            "name": section.name,
            "school_id": section.school_id,
            "school_name": school.name if school else section.school_id,
            "subjects": [
                {"id": subject_id, "name": subjects[subject_id]}
                for subject_id in section.subject_ids_json if subject_id in subjects and (taught is None or section.class_teacher_id == educator.id or (section.id, subject_id) in taught)
            ],
        }
        for section in sections
    ]


@router.get("/assessments/upload-assignments", response_model=List[UploadAssignment])
async def list_upload_assignments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("teacher", "student")),
):
    student, rows = await upload_assignments(db, current_user)
    uploaded = set()
    if student and rows:
        uploaded = set((await db.scalars(
            select(AssignmentOcrUpload.assessment_id)
            .join(StudentOcrHistory, StudentOcrHistory.id == AssignmentOcrUpload.history_id)
            .where(
                StudentOcrHistory.student_id == student.id,
                AssignmentOcrUpload.assessment_id.in_([assessment.id for assessment, _, _ in rows]),
            )
            .distinct()
        )).all())
    return [
        UploadAssignment(
            id=assessment.id, title=assessment.title, date=assessment.date,
            class_name=section.name, subject_name=subject.name, total_marks=assessment.total_marks,
            uploaded=assessment.id in uploaded, questions=assessment.questions_json,
        )
        for assessment, section, subject in rows
    ]


def _question_payload(question) -> dict:
    payload = question.model_dump()
    if payload.get("kc_mappings") is None:
        payload.pop("kc_mappings", None)
    if payload.get("difficulty") is None:
        payload.pop("difficulty", None)
    return payload


@router.post("/classes/{class_id}/assessments", response_model=AssessmentOut, status_code=status.HTTP_201_CREATED)
async def create_assessment(
    class_id: str,
    req: AssessmentCreate,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    if "class_id" in req.model_fields_set and req.class_id != class_id:
        raise HTTPException(status_code=422, detail="Request class must match the target class.")
    section = await validate_assignment_target(db, school_id, class_id, req.subject_id)
    if educator.role == "teacher" and section.class_teacher_id != educator.id:
        allocation = await db.scalar(select(TeacherAssignment.id).where(
            TeacherAssignment.teacher_id == educator.id, TeacherAssignment.school_id == school_id,
            TeacherAssignment.class_id == class_id, TeacherAssignment.subject_id == req.subject_id))
        if allocation is None:
            raise HTTPException(404, "Class and subject unavailable in your teaching scope.")
    asm = Assessment(
        school_id=section.school_id,
        class_id=class_id,
        subject_id=req.subject_id,
        title=req.title,
        cycle_number=req.cycle_number,
        date=req.date,
        duration_minutes=req.duration_minutes,
        total_marks=req.total_marks,
        status="scheduled",
        competency_focus_json=req.competency_focus,
        questions_json=[_question_payload(q) for q in req.questions]
    )
    db.add(asm)
    await db.flush()
    try:
        await kc_graph_service.freeze_published_mappings(db, asm)
        await kc_graph_service.remember_bank_mappings(
            db, school_id=section.school_id, questions=asm.questions_json,
        )
    except ValueError as exc:
        if str(exc) == "unknown-kc":
            raise HTTPException(
                status_code=422,
                detail="A question names a knowledge component that is not in this subject.",
            ) from None
        raise

    audit = AuditEvent(
        timestamp=utc_now().strftime("%Y-%m-%d %H:%M"),
        user_id=educator.id,
        user_name=educator.name,
        action="Created Assessment Cycle",
        details=f"Created assessment: '{asm.title}' (Cycle {asm.cycle_number})",
        category="assessment"
    )
    db.add(audit)
    await db.commit()
    await db.refresh(asm)
    return asm


def _serialize_qb_item(item: QuestionBankItem) -> Dict[str, Any]:
    return {
        "id": item.id,
        "subject_id": item.subject_id,
        "text": item.text,
        "type": item.type,
        "options": item.options_json or [],
        "correct_answer": item.correct_answer,
        "marking_rubric": item.marking_rubric or item.correct_answer,
        "marks": item.marks,
        "competency": item.competency,
        "bloom_level": item.bloom_level,
        "topic": item.topic,
        "grade": item.grade,
        "source_document_ids": item.source_document_ids_json or [],
        "source_document_names": item.source_document_names_json or [],
        "is_ai_generated": item.is_ai_generated,
    }


@router.get("/assessments/question-bank", dependencies=[Depends(_require_question_bank_login)])
async def get_question_bank(
    subject_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    """Educators only, in the authorized X-School-Id context. Includes teaching keys/rubrics.

    A real bearer token is required. Student/parent question delivery uses assigned homework,
    not this authoring bank.
    """
    query = select(QuestionBankItem).filter(QuestionBankItem.school_id == school_id)
    if subject_id:
        query = query.filter(QuestionBankItem.subject_id == subject_id)
    res = await db.execute(query.order_by(QuestionBankItem.created_at.desc()))
    items = list(res.scalars().all())
    if items:
        return [_serialize_qb_item(it) for it in items]

    return []


def _clean_topic(value: Optional[str]) -> Optional[str]:
    """Normalise a free-text topic: trimmed, single-spaced, at most 255 chars; blank -> None."""
    if not value:
        return None
    cleaned = " ".join(str(value).split())[:255]
    return cleaned or None


@router.get("/assessments/question-bank/topics", dependencies=[Depends(_require_question_bank_login)])
async def list_bank_topics(
    subject_id: str = Query(..., min_length=1),
    grade: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    """Topics used in this school's bank for a subject, with question counts per competency.
    Untagged questions are reported separately so teachers can see what still needs a topic."""
    rows = (await db.execute(
        select(QuestionBankItem.topic, QuestionBankItem.competency).filter(
            QuestionBankItem.school_id == school_id, QuestionBankItem.subject_id == subject_id,
            *([or_(QuestionBankItem.grade == grade, QuestionBankItem.grade.is_(None))] if grade is not None else []))
    )).all()
    topics: Dict[str, Dict[str, Any]] = {}
    untagged = 0
    for topic, competency in rows:
        name = _clean_topic(topic)
        if not name:
            untagged += 1
            continue
        entry = topics.setdefault(name.casefold(), {"topic": name, "count": 0, "by_competency": {}})
        entry["count"] += 1
        entry["by_competency"][competency] = entry["by_competency"].get(competency, 0) + 1
    return {
        "subject_id": subject_id,
        "topics": sorted(topics.values(), key=lambda t: t["topic"].casefold()),
        "untagged": untagged,
    }


QUESTION_TYPES = {"mcq", "short", "descriptive", "practical"}
BLOOM_LEVELS = {"Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"}
COMPETENCIES = {"LU", "CU", "AU", "CT"}


def _validate_bank_question(
    *, text: str, qtype: str, options: List[str], correct_answer: str, marks: int, competency: str, bloom: str
) -> List[str]:
    """Shared checks for teacher-authored and edited bank questions. Returns cleaned options."""
    if not (text or "").strip():
        raise HTTPException(status_code=422, detail="Question text is required.")
    if qtype not in QUESTION_TYPES:
        raise HTTPException(status_code=422, detail="Type must be mcq, short, descriptive or practical.")
    if competency not in COMPETENCIES:
        raise HTTPException(status_code=422, detail="Competency must be LU, CU, AU or CT.")
    if bloom not in BLOOM_LEVELS:
        raise HTTPException(status_code=422, detail="Invalid Bloom's Taxonomy level.")
    if not isinstance(marks, int) or not 1 <= marks <= 100:
        raise HTTPException(status_code=422, detail="Marks must be a whole number from 1 to 100.")
    if qtype != "mcq":
        return []
    cleaned = [option.strip() for option in options if isinstance(option, str) and option.strip()]
    if not 2 <= len(cleaned) <= 6:
        raise HTTPException(status_code=422, detail="A multiple-choice question needs 2 to 6 options.")
    if len({option_identity(option) for option in cleaned}) != len(cleaned):
        raise HTTPException(status_code=422, detail="Multiple-choice options must be different from each other.")
    if (correct_answer or "").strip() not in cleaned:
        raise HTTPException(status_code=422, detail="Mark exactly one option as the correct answer.")
    return cleaned


@router.post(
    "/assessments/question-bank",
    dependencies=[Depends(_require_question_bank_login)],
    status_code=status.HTTP_201_CREATED,
)
async def create_bank_question(
    req: QuestionCreateRequest,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    """A teacher writes a question directly into the school's bank. No AI is called."""
    if await db.get(Subject, req.subject_id) is None:
        raise HTTPException(status_code=404, detail="Subject not found.")
    options = _validate_bank_question(
        text=req.text, qtype=req.type, options=req.options, correct_answer=req.correct_answer,
        marks=req.marks, competency=req.competency, bloom=req.bloom_level,
    )
    item = QuestionBankItem(
        school_id=school_id,
        subject_id=req.subject_id,
        text=req.text.strip(),
        type=req.type,
        options_json=options,
        correct_answer=req.correct_answer.strip(),
        marking_rubric=req.marking_rubric.strip(),
        marks=req.marks,
        competency=req.competency,
        bloom_level=req.bloom_level,
        topic=_clean_topic(req.topic),
        grade=req.grade,
        source_document_ids_json=[],
        source_document_names_json=[],
        is_ai_generated=False,
        created_by=educator.id,
    )
    db.add(item)
    db.add(AuditEvent(
        timestamp=utc_now().strftime("%Y-%m-%d %H:%M"),
        user_id=educator.id,
        user_name=educator.name,
        action="Created Question",
        details=f"Teacher wrote a {req.type} question for subject {req.subject_id}.",
        category="assessment",
    ))
    await db.commit()
    await db.refresh(item)
    return _serialize_qb_item(item)


@router.post(
    "/assessments/question-bank/template",
    dependencies=[Depends(_require_question_bank_login)],
    status_code=status.HTTP_201_CREATED,
)
async def create_template_question(
    subject_id: str = Query(..., min_length=1),
    bloom_level: str = Query("Understand"),
    competency: str = Query("CU"),
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    """Deterministic question-bank authoring helper. Does not call Gemini or any AI provider.

    Teachers use this to seed the central bank, then edit the text/key/rubric before assembly.
    """
    subject = await db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found.")
    allowed_bloom = {"Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"}
    if bloom_level not in allowed_bloom:
        raise HTTPException(status_code=422, detail="Invalid Bloom's Taxonomy level.")
    if competency not in {"LU", "CU", "AU", "CT"}:
        raise HTTPException(status_code=422, detail="Invalid competency.")

    item = QuestionBankItem(
        school_id=school_id,
        subject_id=subject_id,
        text=(
            f"Template {competency} question for {subject.name}: "
            f"explain one key idea at Bloom level {bloom_level}."
        ),
        type="mcq",
        options_json=["Option A", "Option B", "Option C", "Option D"],
        correct_answer="Option A",
        marking_rubric="1 mark for selecting the correct option.",
        marks=1,
        competency=competency,
        bloom_level=bloom_level,
        source_document_ids_json=[],
        source_document_names_json=[],
        is_ai_generated=False,
        created_by=educator.id,
    )
    db.add(item)
    db.add(
        AuditEvent(
            timestamp=utc_now().strftime("%Y-%m-%d %H:%M"),
            user_id=educator.id,
            user_name=educator.name,
            action="Created Template Question",
            details=f"Added non-AI template question for subject {subject_id}.",
            category="assessment",
        )
    )
    await db.commit()
    await db.refresh(item)
    return {"generated_count": 1, "subject_id": subject_id, "questions": [_serialize_qb_item(item)]}


@router.post("/assessments/generate-questions", dependencies=[Depends(_require_question_bank_login)])
async def generate_questions_ai(
    req: GenerateQuestionsRequest,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    """
    Generates MCQ and Theory questions grounded in one or multiple source documents.
    Saves generated items to the Question Bank and retains source document references.
    """
    if req.mcq_count < 0 or req.theory_count < 0 or (req.mcq_count + req.theory_count) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please request at least 1 MCQ or 1 Theory question.",
        )

    source_docs_data: List[Dict[str, Any]] = []
    if req.source_document_ids:
        doc_res = await db.execute(
            select(Document).filter(Document.id.in_(req.source_document_ids), Document.school_id == school_id)
        )
        docs = list(doc_res.scalars().all())
        if {doc.id for doc in docs} != set(req.source_document_ids):
            raise HTTPException(status_code=404, detail="Source document not found.")
        for doc in docs:
            source_docs_data.append(
                {
                    "id": doc.id,
                    "file_name": doc.file_name,
                    "extracted_text": doc.extracted_text or "",
                }
            )

    generated_items = await llm_service.generate_questions_from_sources(
        subject_id=req.subject_id,
        mcq_count=req.mcq_count,
        theory_count=req.theory_count,
        bloom_level=req.bloom_level,
        source_documents=source_docs_data,
        focus_topic=req.focus_topic,
    )

    saved_out = []
    for g in generated_items:
        qb_item = QuestionBankItem(
            id=g["id"],
            school_id=school_id,
            subject_id=req.subject_id,
            text=g["text"],
            type=g["type"],
            options_json=g.get("options", []),
            correct_answer=g.get("correct_answer"),
            marking_rubric=g.get("marking_rubric"),
            marks=g.get("marks", 2),
            competency=g.get("competency", "CU"),
            bloom_level=g.get("bloom_level", req.bloom_level),
            topic=_clean_topic(req.bank_topic or req.focus_topic),
            source_document_ids_json=g.get("source_document_ids", []),
            source_document_names_json=g.get("source_document_names", []),
            is_ai_generated=True,
            created_by=educator.id,
        )
        if req.save_to_bank:
            db.add(qb_item)
        saved_out.append(_serialize_qb_item(qb_item))

    audit = AuditEvent(
        timestamp=utc_now().strftime("%Y-%m-%d %H:%M"),
        user_id=educator.id,
        user_name=educator.name,
        action="AI Generated Competency Questions",
        details=(
            f"Generated {req.mcq_count} MCQs and {req.theory_count} Theory items "
            f"(Bloom: {req.bloom_level}) from {len(source_docs_data) or 1} source document(s)."
        ),
        category="assessment",
    )
    db.add(audit)
    await db.commit()

    return {
        "generated_count": len(saved_out),
        "subject_id": req.subject_id,
        "bloom_level": req.bloom_level,
        "source_documents": source_docs_data,
        "questions": saved_out,
    }


@router.post("/assessments/generate-questions-beta", dependencies=[Depends(_require_question_bank_login)])
async def generate_questions_beta(
    req: GenerateQuestionsRequest,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    """Teammate AI Question Studio Beta — shared Qwen model grounded on one chapter PDF."""
    if (
        not 0 <= req.mcq_count <= 15
        or not 0 <= req.theory_count <= 10
        or req.mcq_count + req.theory_count == 0
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request 1–15 MCQs and 0–10 theory questions, with at least one question.",
        )
    if req.bloom_level not in {"Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Bloom's Taxonomy level.")

    document_ids = list(dict.fromkeys(req.source_document_ids))
    if len(document_ids) > 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use one chapter PDF per generation.")
    try:
        source_urls = normalize_urls(req.source_urls)
    except WebSourceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not document_ids and not source_urls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload a chapter PDF or paste a learning-resource link to generate questions.",
        )

    document = None
    if document_ids:
        doc_result = await db.execute(
            select(Document).filter(Document.id == document_ids[0], Document.school_id == school_id)
        )
        document = doc_result.scalars().first()
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Uploaded PDF not found.")
        if document.mime_type != "application/pdf" or not document.file_name.lower().endswith(".pdf"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF source documents are supported.")

    web_sources = []
    for index, url in enumerate(source_urls, start=1):
        report_progress("links", f"Reading link {index} of {len(source_urls)}", index - 1, len(source_urls))
        try:
            web_sources.append(await fetch_web_source(url))
        except WebSourceError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        report_progress("links", f"Read link {index} of {len(source_urls)}", index, len(source_urls))
    source_names = ([document.file_name] if document else []) + [source.url for source in web_sources]

    try:
        pdf_path = storage_service.get_file_path(document.storage_path) if document else None
        generated_items = await qwen_question_studio.generate_questions(
            pdf_path=pdf_path,
            subject_id=req.subject_id,
            subject_name=req.subject_name or req.subject_id,
            source_document_id=document.id if document else None,
            source_document_name=document.file_name if document else None,
            mcq_count=req.mcq_count,
            theory_count=req.theory_count,
            bloom_level=req.bloom_level,
            focus_topic=req.focus_topic,
            web_sources=web_sources,
            **({"competency_distribution": req.competency_distribution.model_dump()} if req.competency_distribution is not None else {}),
        )
    except QwenQuestionStudioInputError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except QwenQuestionStudioUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (QwenQuestionStudioInferenceError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc) or "Qwen returned invalid question data.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("AI Question Studio Beta generation failed.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Question generation failed. Check backend logs.",
        ) from exc

    saved_out = []
    for item in generated_items:
        qb_item = QuestionBankItem(
            id=item["id"],
            school_id=school_id,
            subject_id=req.subject_id,
            text=item["text"],
            type=item["type"],
            options_json=item["options"],
            correct_answer=item["correct_answer"],
            marking_rubric=item["marking_rubric"],
            marks=item["marks"],
            competency=item["competency"],
            bloom_level=req.bloom_level,
            topic=_clean_topic(req.bank_topic or req.focus_topic),
            source_document_ids_json=[document.id] if document else [],
            source_document_names_json=source_names,
            is_ai_generated=True,
            created_by=educator.id,
        )
        if req.save_to_bank:
            db.add(qb_item)
        saved_out.append(_serialize_qb_item(qb_item))

    db.add(
        AuditEvent(
            timestamp=utc_now().strftime("%Y-%m-%d %H:%M"),
            user_id=educator.id,
            user_name=educator.name,
            action="AI Question Studio Generated Questions",
            details=(
                f"Generated {req.mcq_count} MCQs and {req.theory_count} Theory items "
                f"(Bloom: {req.bloom_level}) from {', '.join(source_names)} using "
                f"{settings.QWEN_VL_MODEL_ID}."
            ),
            category="assessment",
        )
    )
    await db.commit()
    report_progress("save", f"Saved {len(saved_out)} questions", len(saved_out), len(saved_out))
    return {
        "generated_count": len(saved_out),
        "subject_id": req.subject_id,
        "bloom_level": req.bloom_level,
        "source_documents_used": source_names,
        "model": settings.QWEN_VL_MODEL_ID,
        "questions": saved_out,
    }


@router.post("/assessments/generate-questions/stream", dependencies=[Depends(_require_question_bank_login)])
async def stream_generate_questions_ai(
    req: GenerateQuestionsRequest,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    return stream_job(lambda: generate_questions_ai(req, db, educator, school_id))


@router.post("/assessments/generate-questions-beta/stream", dependencies=[Depends(_require_question_bank_login)])
async def stream_generate_questions_beta(
    req: GenerateQuestionsRequest,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    return stream_job(lambda: generate_questions_beta(req, db, educator, school_id))


@router.post("/assessments/questions/{question_id}/regenerate", dependencies=[Depends(_require_question_bank_login)])
async def regenerate_question_endpoint(
    question_id: str,
    req: RegenerateQuestionRequest,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    existing_res = await db.execute(select(QuestionBankItem).filter(
        QuestionBankItem.id == question_id, QuestionBankItem.school_id == school_id))
    existing = existing_res.scalars().first()
    if existing is None:
        raise HTTPException(status_code=404, detail="Question not found in bank.")
    new_q = await llm_service.regenerate_single_question(
        subject_id=req.subject_id or existing.subject_id,
        question_type=req.question_type or existing.type,
        bloom_level=req.bloom_level or existing.bloom_level,
        competency=req.competency or existing.competency,
        source_document_ids=req.source_document_ids or (existing.source_document_ids_json or []),
        source_document_names=req.source_document_names or (existing.source_document_names_json or []),
        current_text=req.current_text or existing.text,
    )

    existing.text = new_q["text"]
    existing.options_json = new_q.get("options", [])
    existing.correct_answer = new_q.get("correct_answer")
    existing.marking_rubric = new_q.get("marking_rubric")
    existing.marks = new_q.get("marks", existing.marks)
    existing.bloom_level = new_q.get("bloom_level", existing.bloom_level)
    await db.commit()
    await db.refresh(existing)
    return _serialize_qb_item(existing)


@router.put("/assessments/questions/{question_id}", dependencies=[Depends(_require_question_bank_login)])
async def update_question_endpoint(
    question_id: str,
    req: QuestionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    res = await db.execute(select(QuestionBankItem).filter(
        QuestionBankItem.id == question_id, QuestionBankItem.school_id == school_id))
    item = res.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Question not found in bank.")

    # Validate the question as it will look after the edit, so an MCQ can never end up with an
    # answer key that matches no option (or several).
    merged_type = req.type if req.type is not None else item.type
    merged_options = req.options if req.options is not None else (item.options_json or [])
    merged_answer = req.correct_answer if req.correct_answer is not None else (item.correct_answer or "")
    cleaned = _validate_bank_question(
        text=req.text if req.text is not None else item.text,
        qtype=merged_type,
        options=merged_options,
        correct_answer=merged_answer,
        marks=req.marks if req.marks is not None else item.marks,
        competency=req.competency if req.competency is not None else item.competency,
        bloom=req.bloom_level if req.bloom_level is not None else item.bloom_level,
    )
    if req.type is not None or req.options is not None:
        req.options = cleaned

    if req.text is not None:
        item.text = req.text
    if req.type is not None:
        item.type = req.type
    if req.options is not None:
        item.options_json = req.options
    if req.correct_answer is not None:
        item.correct_answer = req.correct_answer
    if req.marking_rubric is not None:
        item.marking_rubric = req.marking_rubric
    if req.marks is not None:
        item.marks = req.marks
    if req.competency is not None:
        item.competency = req.competency
    if req.bloom_level is not None:
        item.bloom_level = req.bloom_level
    if req.topic is not None:
        item.topic = _clean_topic(req.topic)
    if req.grade is not None:
        item.grade = req.grade or None

    await db.commit()
    await db.refresh(item)
    return _serialize_qb_item(item)


@router.delete("/assessments/questions/{question_id}", dependencies=[Depends(_require_question_bank_login)])
async def delete_question_endpoint(
    question_id: str,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    res = await db.execute(select(QuestionBankItem).filter(
        QuestionBankItem.id == question_id, QuestionBankItem.school_id == school_id))
    item = res.scalars().first()
    if item is None:
        raise HTTPException(404, "Question not found in your school.")
    # Frozen assessment references live in JSON and are not protected by foreign keys.
    snapshots = (await db.scalars(select(Assessment.questions_json))).all()
    if any(isinstance(q, dict) and (q.get("id") == question_id or q.get("source_question_id") == question_id)
           for snapshot in snapshots for q in (snapshot or [])):
        raise HTTPException(409, "This question is used in an assessment and cannot be deleted.")
    await db.delete(item)
    await db.commit()
    return {"status": "deleted", "id": question_id}


# --- AI question generation (local Qwen or Gemini): preview, then explicit educator approval ---
# Generation never writes to the bank. Approved (optionally edited) questions are saved through
# the save endpoint below as ordinary QuestionBankItem rows flagged is_ai_generated=True, so the
# existing bank, homework selection and frozen draft snapshots work unchanged.


@router.post("/assessments/ai/generate-questions", response_model=AIGenerationPreview)
async def ai_generate_questions_preview(
    req: AIQuestionRequest,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    """Educators only. Returns NEW AI-generated questions for review; nothing is saved.

    Every question in the response is produced by the AI provider during this request. The
    existing bank is read only to reject duplicates; its questions are never returned, sent to the
    provider or modified, and there is no template fallback: failures are reported as errors."""
    subject = await db.get(Subject, req.subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found.")
    existing_texts = list((await db.execute(select(QuestionBankItem.text).filter(
        QuestionBankItem.school_id == school_id, QuestionBankItem.subject_id == req.subject_id))).scalars().all())

    def audit(action: str, details: str) -> None:
        db.add(AuditEvent(timestamp=utc_now().strftime("%Y-%m-%d %H:%M"), user_id=educator.id,
                          user_name=educator.name, action=action, details=details, category="assessment"))

    scope = (f"{req.subject_id}, grade {req.grade}, {req.competency}/{req.bloom_level}/{req.question_type}, "
             f"requested {req.count}, model {req.provider}")
    try:
        provider = ai_gateway.QwenTextProvider() if req.provider == "qwen" else ai_gateway.get_ai_provider()
        preview = await generate_question_preview(provider, req, subject.name, existing_texts)
    except AIGatewayError as exc:
        code = 503 if isinstance(exc, AINotConfigured) else 504 if isinstance(exc, AIProviderTimeout) else 502
        logger.warning("AI question preview failed: %s (%s).", type(exc).__name__, scope)
        audit("AI Question Preview Failed", f"{type(exc).__name__} for {scope}; nothing returned or saved.")
        await db.commit()
        raise HTTPException(status_code=code, detail=exc.public_message)
    logger.info("AI question preview: provider=%s model=%s attempts=%d received=%d generated=%d "
                "bank_duplicates=%d repeats=%d invalid=%d (%s).", preview.provider, preview.model, preview.attempts,
                preview.received, preview.generated, preview.rejected_duplicates, preview.rejected_repeats,
                preview.rejected_invalid, scope)
    audit("AI Question Preview",
          f"{preview.provider}/{preview.model} generated {preview.generated} new question(s) for {scope} in "
          f"{preview.attempts} request(s); rejected {preview.rejected_duplicates} bank duplicate(s), "
          f"{preview.rejected_repeats} repeat(s), {preview.rejected_invalid} invalid; not saved.")
    await db.commit()
    return preview


@router.post("/assessments/ai/questions", status_code=status.HTTP_201_CREATED)
async def ai_save_approved_questions(
    req: AIQuestionSaveRequest,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    """Educators only. Saves questions the educator reviewed and approved into the school's
    question bank, flagged as AI-generated. The same validation as generation applies."""
    if await db.get(Subject, req.subject_id) is None:
        raise HTTPException(status_code=404, detail="Subject not found.")
    items = []
    for q in req.questions:
        rubric = q.marking_rubric + (f"\nExplanation: {q.explanation}" if q.explanation else "")
        items.append(QuestionBankItem(
            id=str(uuid.uuid4()), school_id=school_id, subject_id=req.subject_id, text=q.text, type=q.question_type,
            options_json=list(q.options), correct_answer=q.correct_answer, marking_rubric=rubric,
            marks=q.marks, competency=q.competency, bloom_level=q.bloom_level,
            source_document_ids_json=[], source_document_names_json=[],
            is_ai_generated=True, created_by=educator.id, topic=_clean_topic(q.topic or req.topic),
        ))
    db.add_all(items)
    db.add(AuditEvent(
        timestamp=utc_now().strftime("%Y-%m-%d %H:%M"), user_id=educator.id, user_name=educator.name,
        action="AI Questions Approved",
        details=f"Approved and saved {len(items)} AI-generated question(s) for {req.subject_id}"
                + (f" ({req.model})." if req.model else "."),
        category="assessment",
    ))
    out = {"saved_count": len(items), "questions": [_serialize_qb_item(i) for i in items]}
    await db.commit()
    return out



@router.post("/assessments/{assessment_id}/submissions", response_model=SubmissionOut)
async def submit_assessment_grade(
    assessment_id: str,
    req: SubmissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    asm = await _scoped_assessment(db, assessment_id, school_id)

    st_res = await db.execute(select(Student).filter(Student.id == req.student_id))
    student = st_res.scalars().first()
    if not student or student.school_id != school_id or student.class_id != asm.class_id:
        raise HTTPException(status_code=404, detail="Student not found.")

    percentage = round((req.marks_obtained / max(1, req.total_marks)) * 100)
    overall_comp = round((req.lu_score + req.cu_score + req.au_score + req.ct_score) / 4)

    sub = AssessmentSubmission(
        assessment_id=assessment_id,
        student_id=student.id,
        student_name=student.name,
        marks_obtained=req.marks_obtained,
        total_marks=req.total_marks,
        percentage=percentage,
        lu_score=req.lu_score,
        cu_score=req.cu_score,
        au_score=req.au_score,
        ct_score=req.ct_score,
        overall_score=overall_comp,
        feedback=req.feedback,
        submission_date=utc_now().strftime("%Y-%m-%d"),
        is_scanned=req.is_scanned
    )
    db.add(sub)

    # Recalibrate student's live competencies
    student.lu_score = req.lu_score
    student.cu_score = req.cu_score
    student.au_score = req.au_score
    student.ct_score = req.ct_score
    student.overall_score = overall_comp
    student.needs_support = percentage < 65

    # Record historical snapshot
    snapshot = StudentCompetencySnapshot(
        student_id=student.id,
        cycle_number=asm.cycle_number,
        lu_score=req.lu_score,
        cu_score=req.cu_score,
        au_score=req.au_score,
        ct_score=req.ct_score,
        overall_score=overall_comp,
        notes=f"Graded submission for assessment: {asm.title}",
        subject_id=asm.subject_id,
        source_assessment_id=asm.id,
        source_submission_id=sub.id,
    )
    db.add(snapshot)

    audit = AuditEvent(
        timestamp=utc_now().strftime("%Y-%m-%d %H:%M"),
        user_id=current_user.id,
        user_name=current_user.name,
        action="Graded Assessment Submission",
        details=f"Recorded {percentage}% for {student.name} in '{asm.title}'. Recalibrated baseline.",
        category="assessment"
    )
    db.add(audit)
    await db.commit()
    await db.refresh(sub)

    return SubmissionOut(
        id=sub.id,
        assessment_id=sub.assessment_id,
        student_id=sub.student_id,
        student_name=sub.student_name,
        marks_obtained=sub.marks_obtained,
        total_marks=sub.total_marks,
        percentage=sub.percentage,
        scores={
            "LU": sub.lu_score,
            "CU": sub.cu_score,
            "AU": sub.au_score,
            "CT": sub.ct_score,
            "overall": sub.overall_score
        },
        feedback=sub.feedback,
        submission_date=sub.submission_date,
        is_scanned=sub.is_scanned
    )


@router.get("/assessments/{assessment_id}/submissions", response_model=List[SubmissionOut])
async def list_assessment_submissions(
    assessment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    asm = await _scoped_assessment(db, assessment_id, school_id)
    query = select(AssessmentSubmission).join(Student, Student.id == AssessmentSubmission.student_id).filter(
        AssessmentSubmission.assessment_id == assessment_id,
        Student.school_id == school_id, Student.class_id == asm.class_id)

    res = await db.execute(query)
    subs = res.scalars().all()
    return [
        SubmissionOut(
            id=s.id,
            assessment_id=s.assessment_id,
            student_id=s.student_id,
            student_name=s.student_name,
            marks_obtained=s.marks_obtained,
            total_marks=s.total_marks,
            percentage=s.percentage,
            scores={"LU": s.lu_score, "CU": s.cu_score, "AU": s.au_score, "CT": s.ct_score, "overall": s.overall_score},
            feedback=s.feedback,
            submission_date=s.submission_date,
            is_scanned=s.is_scanned
        ) for s in subs
    ]
