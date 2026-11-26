from backend.app.api.dependencies import require_bearer_token
from backend.app.api.dependencies import reject_non_finite_json as _reject_non_finite_json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.app.api.dependencies import get_current_user, require_roles
from backend.app.db.session import get_db
from backend.app.models.entities import HomeworkRemediation, Student, User, AuditEvent, utc_now
from backend.app.schemas.competencies import HomeworkOut
from backend.app.services.competency_service import generate_differentiated_recommendation
import logging

from pydantic import ValidationError

from backend.app.modules.differentiated_homework.access import can_view_student, role_may_view_students
from backend.app.modules.differentiated_homework.competency_adapter import load_competency_profile
from backend.app.modules.differentiated_homework.gap_analyzer import analyze_gaps
from backend.app.modules.differentiated_homework.schemas import GapAnalysis
from backend.app.models.entities import ClassSection, Subject
from backend.app.modules.differentiated_homework.access import role_may_generate_homework
from backend.app.modules.differentiated_homework.homework_assembler import AssemblyError, assemble_homework_draft
from backend.app.modules.differentiated_homework.question_bank_adapter import load_candidate_questions
from backend.app.modules.differentiated_homework.question_selector import select_questions
from backend.app.modules.differentiated_homework.schemas import (
    HomeworkDraft,
    HomeworkPreviewRequest,
    SelectionRequest,
)
from fastapi import Query
from backend.app.models.entities import SchoolMembership
from backend.app.modules.differentiated_homework.access import can_access_draft
from backend.app.modules.differentiated_homework.draft_service import (
    InvalidEdit,
    InvalidTransition,
    StaleQuestion,
    apply_review,
    build_draft_record,
    remove_item,
    renumber_and_recount,
    stage_renumber,
    to_out,
    to_summary,
)
from sqlalchemy.orm.exc import StaleDataError
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from backend.app.modules.differentiated_homework.access import can_access_assignment
from backend.app.modules.differentiated_homework.draft_service import (
    build_assignment,
    to_assignment_out,
    to_assignment_summary,
)
from backend.app.modules.differentiated_homework.models import HomeworkAssignmentRecord, StudentAccountLink
from fastapi import Request, Response
from backend.app.modules.differentiated_homework.draft_service import as_utc
from backend.app.modules.differentiated_homework.schemas import (
    StudentAccountLinkCreate,
    StudentAccountLinkListItemOut,
    StudentAccountLinkOut,
    StudentAssignmentOut,
)
from backend.app.modules.differentiated_homework.student_access import (
    resolve_linked_student,
    subject_names,
    to_student_detail,
    to_student_summary,
)
from backend.app.modules.differentiated_homework.models import HomeworkSubmissionRecord
from backend.app.modules.differentiated_homework.schemas import (
    AnswerProblemOut,
    SubmissionAnswersUpdate,
    SubmissionFinalizeRequest,
    HomeworkSubmissionOut,
)
from backend.app.modules.differentiated_homework.submission_service import (
    InvalidAnswers,
    NotSubmittable,
    SubmissionLocked,
    SubmissionMismatch,
    VersionConflict,
    empty_submission_out,
    finalize_submission,
    save_answers,
    to_submission_out,
)
from backend.app.api.dependencies import oauth2_scheme
from backend.app.modules.differentiated_homework.schemas import (
    TeacherAssignmentSubmissionsOut,
    TeacherSubmissionDetailOut,
)
from backend.app.modules.differentiated_homework.teacher_submissions import (
    assignment_overview,
    student_row,
    submission_detail,
)
from backend.app.modules.differentiated_homework.models import HomeworkEvaluationRecord
from backend.app.modules.differentiated_homework.schemas import (
    AIEvaluationRerunRequest,
    AIEvaluationSuggestRequest,
    AIEvaluationSuggestionsOut,
    EvaluationMarksUpdate,
    EvaluationTransitionRequest,
    StudentResultOut,
    TeacherEvaluationOut,
    TeacherEvaluationQueueItemOut,
)
from backend.app.modules.differentiated_homework.evaluation_service import (
    EvaluationError,
    InvalidMarks,
    apply_marks,
    build_evaluation,
    check_evaluation,
    finalize_evaluation,
    release_evaluation,
    to_queue_item,
    to_student_result,
    to_teacher_evaluation,
)
from backend.app.modules.differentiated_homework.ai_evaluation_service import (
    InvalidSuggestionRequest,
    SuggestionConflict,
    SuggestionUnavailable,
    build_suggestions,
    persist_suggestions,
    to_suggestions_out,
)
from backend.app.services.ai_gateway import AIGatewayError, AINotConfigured, AIProviderTimeout
from backend.app.modules.differentiated_homework.schemas import (
    AssignmentOut,
    AssignmentStatus,
    AssignmentSummaryOut,
    AssignRequest,
)
from backend.app.modules.differentiated_homework.models import HomeworkDraftRecord
from backend.app.modules.differentiated_homework.question_bank_adapter import load_question_snapshots
from backend.app.modules.differentiated_homework.schemas import (
    DraftReviewRequest,
    DraftStatus,
    HomeworkDraftSaveRequest,
    SavedDraftOut,
    SavedDraftSummaryOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Homework & Remediation"], dependencies=[Depends(require_bearer_token)])


class HomeworkCreate(BaseModel):
    student_id: str
    class_id: str
    subject_id: str = "sub-math"
    title: str
    competency_target: str
    reason: Optional[str] = None
    description: str
    due_date: str


async def _require_legacy_login(token: Optional[str] = Depends(oauth2_scheme)) -> None:
    if not token:
        raise HTTPException(status_code=401, detail="Authentication token required.",
                            headers={"WWW-Authenticate": "Bearer"})


async def _legacy_student(db: AsyncSession, user: User, student_id: str) -> Student:
    """Explicit account/parent links or educator school access; no ID/email shortcut."""
    if user.role not in {"admin", "principal", "teacher", "parent", "student"}:
        raise HTTPException(status_code=403, detail="Access denied.")
    student = await db.get(Student, student_id)
    if user.role == "student":
        linked = await resolve_linked_student(db, user)
        allowed = student is not None and linked is not None and linked.id == student.id
    else:
        allowed = student is not None and await can_view_student(db, user, student)
    if not allowed:
        raise HTTPException(status_code=404, detail="Student not found.")
    return student


async def _legacy_class(db: AsyncSession, user: User, class_id: str) -> ClassSection:
    from backend.app.modules.differentiated_homework.access import has_school_access
    if not role_may_generate_homework(user):
        raise HTTPException(status_code=403, detail="Access denied.")
    record = await db.get(ClassSection, class_id)
    if record is None or not await has_school_access(db, user, record.school_id):
        raise HTTPException(status_code=404, detail="Class not found.")
    return record


@router.get("/classes/{class_id}/homework", response_model=List[HomeworkOut],
            dependencies=[Depends(_require_legacy_login)])
async def list_class_homework(class_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    record = await _legacy_class(db, current_user, class_id)
    res = await db.execute(select(HomeworkRemediation).join(Student, Student.id == HomeworkRemediation.student_id)
                           .filter(HomeworkRemediation.class_id == record.id, Student.class_id == record.id,
                                   Student.school_id == record.school_id))
    return res.scalars().all()


@router.post("/classes/{class_id}/homework", response_model=HomeworkOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(_require_legacy_login)])
async def assign_homework(
    class_id: str,
    req: HomeworkCreate,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher"))
):
    record = await _legacy_class(db, educator, class_id)
    st = await _legacy_student(db, educator, req.student_id)
    if req.class_id != class_id or st.class_id != class_id or st.school_id != record.school_id:
        raise HTTPException(status_code=422, detail="Student and request must belong to the target class.")
    hw = HomeworkRemediation(
        student_id=st.id, student_name=st.name, class_id=class_id, subject_id=req.subject_id,
        title=req.title, competency_target=req.competency_target, reason=req.reason,
        description=req.description, due_date=req.due_date, status="assigned"
    )
    db.add(hw)
    db.add(_audit(educator, "Assigned Differentiated Remediation",
                  f"Assigned {req.competency_target} task '{req.title}' to {st.name}"))
    await db.commit()
    await db.refresh(hw)
    return hw


@router.get("/students/{student_id}/homework", response_model=List[HomeworkOut],
            dependencies=[Depends(_require_legacy_login)])
async def list_student_homework(student_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    student = await _legacy_student(db, current_user, student_id)
    res = await db.execute(select(HomeworkRemediation).filter(
        HomeworkRemediation.student_id == student.id, HomeworkRemediation.class_id == student.class_id))
    return res.scalars().all()


@router.post("/homework/{homework_id}/submissions", dependencies=[Depends(_require_legacy_login)])
async def submit_homework(homework_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Access denied.")
    linked = await resolve_linked_student(db, current_user)
    hw = (await db.execute(select(HomeworkRemediation).filter(
        HomeworkRemediation.id == homework_id,
        HomeworkRemediation.student_id == linked.id,
        HomeworkRemediation.class_id == linked.class_id,
    ))).scalars().first() if linked is not None else None
    if hw is None:
        raise HTTPException(status_code=404, detail="Homework not found.")
    if hw.status == "assigned":
        hw.status = "submitted"
        await db.commit()
    elif hw.status not in {"submitted", "reviewed"}:
        raise HTTPException(status_code=409, detail="Homework cannot be submitted in its current state.")
    # Completion only: preserve any historical score without inventing a grade or overwriting review.
    return {"message": "Homework submitted successfully.", "score": hw.score}


@router.get("/students/{student_id}/remediation/recommendation", dependencies=[Depends(_require_legacy_login)])
async def get_student_remediation_recommendation(
    student_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    student = await _legacy_student(db, current_user, student_id)
    return generate_differentiated_recommendation(student)


@router.get("/students/{student_id}/homework/gap-analysis", response_model=GapAnalysis)
async def get_student_gap_analysis(
    student_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Read-only: rank the student's LU, CU, AU and CT scores and report the weakest.

    Access rules are in access.py. Scores come from the temporary competency adapter and
    are unverified, so the result is a relative comparison, not a diagnosis.
    """
    # Roles that can never view student analysis are refused before any lookup, so they
    # can't use this endpoint to find out which student IDs exist.
    if not role_may_view_students(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    result = await db.execute(select(Student).filter(Student.id == student_id))
    student = result.scalars().first()
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")

    if not await can_view_student(db, current_user, student):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    try:
        profile = await load_competency_profile(db, student_id)
    except ValidationError:
        # Stored data is out of range or malformed. Don't return or log the values.
        logger.warning("Invalid stored competency scores for a student; gap analysis refused.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="This student's competency data is invalid. Contact an administrator.",
        )
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")

    return analyze_gaps(profile)


INVALID_DATA = "This student's data is invalid. Contact an administrator."


@router.post("/students/{student_id}/homework/preview", response_model=HomeworkDraft)
async def preview_student_homework(
    student_id: str,
    body: HomeworkPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Build an unsaved homework draft for one student. Nothing is written to the database.

    Runs the existing pipeline: competency adapter, Gap Analyzer, question bank adapter,
    Question Selector, Homework Assembler. The school comes from the student's record.
    """
    return await _generate_draft(db, current_user, student_id, body)


async def _generate_draft(
    db: AsyncSession, current_user: User, student_id: str, body: HomeworkPreviewRequest
) -> HomeworkDraft:
    """Shared by preview and save: checks access and inputs, then runs the pipeline. No writes."""
    if not role_may_generate_homework(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    student = (await db.execute(select(Student).filter(Student.id == student_id))).scalars().first()
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")
    if not await can_view_student(db, current_user, student):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    # The subject must exist and be offered by the student's own class (agreed rule).
    subject = (await db.execute(select(Subject.id).filter(Subject.id == body.subject_id))).first()
    if subject is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    student_class = (
        await db.execute(select(ClassSection).filter(ClassSection.id == student.class_id))
    ).scalars().first()
    if (
        student_class is None
        or student_class.school_id != student.school_id
        or not isinstance(student_class.subject_ids_json, list)
    ):
        logger.warning("Student class record missing or inconsistent; homework preview refused.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=INVALID_DATA)
    if body.subject_id not in student_class.subject_ids_json:
        raise HTTPException(
            status_code=422,  # plain number: the named constant differs between Starlette versions
            detail="This subject isn't offered in the student's class.",
        )

    try:
        profile = await load_competency_profile(db, student_id)
    except ValidationError:
        logger.warning("Invalid stored competency scores for a student; homework preview refused.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="This student's competency data is invalid. Contact an administrator.",
        )
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")

    analysis = analyze_gaps(profile)
    selection_request = SelectionRequest(
        school_id=student.school_id,
        subject_id=body.subject_id,
        max_questions=body.max_questions,
        max_total_marks=body.max_total_marks,
        include_ai_generated=body.include_ai_generated,
    )
    loaded = await load_candidate_questions(db, student.school_id, body.subject_id, body.topics,
                                            grade=student_class.grade)
    selection = select_questions(analysis, loaded.candidates, selection_request)

    try:
        draft = assemble_homework_draft(analysis, selection, selection_request)
    except AssemblyError:
        # The pipeline produced inconsistent data; this is a server fault, not a client error.
        logger.exception("Homework assembly failed on pipeline output.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Homework preview failed.")

    if loaded.malformed_question_ids:
        note = f"{len(loaded.malformed_question_ids)} question bank row(s) couldn't be read and were skipped."
        draft = draft.model_copy(update={"notes": [*draft.notes, note]})
    if body.topics:
        note = f"Limited to topic(s): {', '.join(body.topics)}."
        if draft.shortfall:
            note += " Tag more bank questions with these topics, or widen the topic choice, to fill the gap."
        draft = draft.model_copy(update={"notes": [note, *draft.notes]})
    return draft


# --- Saved homework drafts ------------------------------------------------------------


def _audit(user: User, action: str, details: str) -> AuditEvent:
    return AuditEvent(
        timestamp=utc_now().strftime("%Y-%m-%d %H:%M"),
        user_id=user.id,
        user_name=user.name,
        action=action,
        details=details,
        category="curriculum",
    )


async def _accessible_school_ids(db: AsyncSession, user: User) -> set:
    ids = {user.school_id} if user.school_id else set()
    rows = await db.execute(
        select(SchoolMembership.school_id).filter(
            SchoolMembership.user_id == user.id,
            SchoolMembership.is_active == True,  # noqa: E712 (SQL comparison)
        )
    )
    ids.update(r.school_id for r in rows.all())
    return ids


async def _load_draft_for(db: AsyncSession, user: User, draft_id: str) -> HomeworkDraftRecord:
    if not role_may_generate_homework(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    record = (
        await db.execute(select(HomeworkDraftRecord).filter(HomeworkDraftRecord.id == draft_id))
    ).scalars().first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found.")
    if not await can_access_draft(db, user, record):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    return record


@router.post("/students/{student_id}/homework/drafts", response_model=SavedDraftOut, status_code=201)
async def save_homework_draft(
    student_id: str,
    body: HomeworkDraftSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Explicitly save a homework draft. The server regenerates it with the same pipeline as
    the preview, so a client can't post altered questions. Saved with status 'draft'."""
    draft = await _generate_draft(db, current_user, student_id, body)

    question_ids = [item.question_id for item in draft.items]
    if body.expected_question_ids is not None and body.expected_question_ids != question_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The selected questions have changed since the preview. Preview again before saving.",
        )
    if not question_ids:
        raise HTTPException(status_code=422, detail="There are no questions to save.")

    snapshots = await load_question_snapshots(db, question_ids, draft.school_id, draft.subject_id)
    try:
        record = build_draft_record(draft, snapshots, body, created_by=current_user.id)
    except StaleQuestion:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A selected question changed while saving. Preview again before saving.",
        )

    db.add(record)
    db.add(_audit(current_user, "Saved Homework Draft",
                  f"Saved homework draft for student {draft.student_id} ({draft.question_count} questions)."))
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return to_out(record)


async def _with_display_names(db: AsyncSession, rows: list) -> list:
    """Attach student and subject names so teacher lists never show raw ids."""
    if not rows:
        return rows
    student_ids = {r.student_id for r in rows}
    found = await db.execute(select(Student.id, Student.name).filter(Student.id.in_(student_ids)))
    students = {r.id: r.name for r in found.all()}
    subjects = await subject_names(db, {r.subject_id for r in rows})
    return [r.model_copy(update={"student_name": students.get(r.student_id), "subject_name": subjects.get(r.subject_id)})
            for r in rows]


@router.get("/homework/drafts", response_model=List[SavedDraftSummaryOut])
async def list_homework_drafts(
    draft_status: Optional[DraftStatus] = Query(default=None, alias="status"),
    student_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Drafts the user may see: admin all, principal their schools, teacher their own."""
    if not role_may_generate_homework(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    query = select(HomeworkDraftRecord)
    if current_user.role != "admin":
        schools = await _accessible_school_ids(db, current_user)
        query = query.filter(HomeworkDraftRecord.school_id.in_(schools))
        if current_user.role == "teacher":
            query = query.filter(HomeworkDraftRecord.created_by == current_user.id)
    if draft_status:
        query = query.filter(HomeworkDraftRecord.status == draft_status)
    if student_id:
        query = query.filter(HomeworkDraftRecord.student_id == student_id)

    rows = await db.execute(query.order_by(HomeworkDraftRecord.created_at.desc(), HomeworkDraftRecord.id))
    return await _with_display_names(db, [to_summary(r) for r in rows.scalars().all()])


@router.get("/homework/drafts/{draft_id}", response_model=SavedDraftOut)
async def get_homework_draft(
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return to_out(await _load_draft_for(db, current_user, draft_id))


CHANGED_ELSEWHERE = "This draft was changed by another request. Reload it and try again."


async def _commit_or_conflict(db: AsyncSession) -> None:
    """Commit; if another request changed the draft first (version mismatch), roll back and 409."""
    try:
        await db.commit()
    except StaleDataError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=CHANGED_ELSEWHERE)


async def _review(db: AsyncSession, user: User, draft_id: str, action: str, note) -> SavedDraftOut:
    record = await _load_draft_for(db, user, draft_id)
    try:
        apply_review(record, action, user.id, note)
    except InvalidTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    db.add(_audit(user, f"Homework Draft {action.capitalize()}", f"{action} draft {record.id}."))
    await _commit_or_conflict(db)
    return to_out(record)


@router.post("/homework/drafts/{draft_id}/approve", response_model=SavedDraftOut)
async def approve_homework_draft(
    draft_id: str,
    body: Optional[DraftReviewRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _review(db, current_user, draft_id, "approve", body.note if body else None)


@router.post("/homework/drafts/{draft_id}/reject", response_model=SavedDraftOut)
async def reject_homework_draft(
    draft_id: str,
    body: Optional[DraftReviewRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _review(db, current_user, draft_id, "reject", body.note if body else None)


@router.post("/homework/drafts/{draft_id}/reopen", response_model=SavedDraftOut)
async def reopen_homework_draft(
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Move a rejected draft back to 'draft' so it can be edited."""
    return await _review(db, current_user, draft_id, "reopen", None)


@router.delete("/homework/drafts/{draft_id}/items/{position}", response_model=SavedDraftOut)
async def remove_homework_draft_item(
    draft_id: str,
    position: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove one question from a draft in 'draft' status; positions and totals are updated."""
    record = await _load_draft_for(db, current_user, draft_id)
    try:
        removed = remove_item(record, position)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No question at that position.")
    except InvalidEdit as exc:
        code = status.HTTP_409_CONFLICT if record.status != "draft" else 422
        raise HTTPException(status_code=code, detail=str(exc))

    try:
        await db.flush()  # delete the removed item first
        stage_renumber(record)
        await db.flush()  # temporary positions, so final numbering can't collide
    except StaleDataError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=CHANGED_ELSEWHERE)
    renumber_and_recount(record, removed)
    db.add(_audit(current_user, "Homework Draft Edited",
                  f"Removed question {removed.source_question_id} from draft {record.id}."))
    await _commit_or_conflict(db)
    return to_out(record)


# --- Homework assignments ---------------------------------------------------------------


@router.post("/homework/drafts/{draft_id}/assign", response_model=AssignmentOut, status_code=201)
async def assign_homework_draft(
    draft_id: str,
    body: Optional[AssignRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Issue an approved draft to its student. Creates the assignment and marks the draft
    'assigned' in one transaction. Student, school and teacher come from the server."""
    record = await _load_draft_for(db, current_user, draft_id)

    existing = (await db.execute(
        select(HomeworkAssignmentRecord.id).filter(HomeworkAssignmentRecord.draft_id == record.id)
    )).first()
    if existing is not None or record.status == "assigned":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This draft has already been assigned.")

    due_at = body.due_at if body else None
    if due_at is not None and due_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="The due date must be in the future.")

    try:
        apply_review(record, "assign", current_user.id, None)
    except InvalidTransition:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only approved drafts can be assigned; this one is {record.status}.",
        )

    assignment = build_assignment(record, current_user.id, due_at)
    db.add(assignment)
    db.add(_audit(current_user, "Homework Assigned",
                  f"Assigned draft {record.id} to student {record.student_id}."))
    try:
        await db.commit()
    except StaleDataError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=CHANGED_ELSEWHERE)
    except IntegrityError:
        await db.rollback()
        # Only a duplicate (another request assigned this draft first, hitting the unique
        # draft_id) is a 409. Any other integrity failure is a server fault: re-raise it.
        duplicate = (await db.execute(
            select(HomeworkAssignmentRecord.id).filter(HomeworkAssignmentRecord.draft_id == draft_id)
        )).first()
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This draft has already been assigned.")
        raise
    return to_assignment_out(assignment)


@router.get("/homework/assignments", response_model=List[AssignmentSummaryOut])
async def list_homework_assignments(
    student_id: Optional[str] = None,
    subject_id: Optional[str] = None,
    assignment_status: Optional[AssignmentStatus] = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Assignments the user may see, filtered in the database query."""
    if not role_may_generate_homework(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    query = (
        select(HomeworkAssignmentRecord)
        .join(HomeworkDraftRecord, HomeworkAssignmentRecord.draft_id == HomeworkDraftRecord.id)
        # Summaries need draft totals but not the questions: skip loading items (and fail loudly
        # if anything tries to read them).
        .options(selectinload(HomeworkAssignmentRecord.draft).raiseload(HomeworkDraftRecord.items))
    )
    if current_user.role != "admin":
        schools = await _accessible_school_ids(db, current_user)
        query = query.filter(HomeworkAssignmentRecord.school_id.in_(schools))
        if current_user.role == "teacher":
            query = query.filter(HomeworkDraftRecord.created_by == current_user.id)
    if student_id:
        query = query.filter(HomeworkAssignmentRecord.student_id == student_id)
    if subject_id:
        query = query.filter(HomeworkAssignmentRecord.subject_id == subject_id)
    if assignment_status:
        query = query.filter(HomeworkAssignmentRecord.status == assignment_status)

    rows = await db.execute(
        query.order_by(HomeworkAssignmentRecord.assigned_at.desc(), HomeworkAssignmentRecord.id)
    )
    return await _with_display_names(db, [to_assignment_summary(a) for a in rows.scalars().all()])


@router.get("/homework/assignments/{assignment_id}", response_model=AssignmentOut)
async def get_homework_assignment(
    assignment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not role_may_generate_homework(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    assignment = (await db.execute(
        select(HomeworkAssignmentRecord).filter(HomeworkAssignmentRecord.id == assignment_id)
    )).scalars().first()
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found.")
    if not await can_access_assignment(db, current_user, assignment):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    return to_assignment_out(assignment)


# --- Student account links (admin only) ---------------------------------------------------


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")


@router.post("/student-account-links", response_model=StudentAccountLinkOut, status_code=201)
async def create_student_account_link(
    body: StudentAccountLinkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Link a student login to a Student record, one to one. Admin only; nothing is inferred."""
    _require_admin(current_user)

    account = (await db.execute(select(User).filter(User.id == body.user_id))).scalars().first()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if account.role != "student":
        raise HTTPException(status_code=422, detail="Only accounts with the 'student' role can be linked.")
    student = (await db.execute(select(Student).filter(Student.id == body.student_id))).scalars().first()
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")
    if not account.school_id or account.school_id != student.school_id:
        raise HTTPException(status_code=422, detail="The account and the student belong to different schools.")

    existing = (await db.execute(
        select(StudentAccountLink.id).filter(
            (StudentAccountLink.user_id == body.user_id) | (StudentAccountLink.student_id == body.student_id)
        )
    )).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="This account or this student is already linked.")

    link = StudentAccountLink(user_id=account.id, student_id=student.id, created_by=current_user.id)
    db.add(link)
    db.add(_audit(current_user, "Student Account Linked", f"Linked account {account.id} to student {student.id}."))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        clash = (await db.execute(
            select(StudentAccountLink.id).filter(
                (StudentAccountLink.user_id == body.user_id) | (StudentAccountLink.student_id == body.student_id)
            )
        )).first()
        if clash is not None:  # another request linked one of them first
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="This account or this student is already linked.")
        raise
    return StudentAccountLinkOut(id=link.id, user_id=link.user_id, student_id=link.student_id,
                                 created_by=link.created_by, created_at=as_utc(link.created_at))


@router.get("/student-account-links", response_model=List[StudentAccountLinkListItemOut])
async def list_student_account_links(
    user_id: Optional[str] = Query(default=None, min_length=1),
    student_id: Optional[str] = Query(default=None, min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List links, newest first, optionally filtered. Admin only. Each link says whether its
    User and Student still exist, so stale links can be found and removed with DELETE."""
    _require_admin(current_user)
    query = (
        select(StudentAccountLink, User.id.is_not(None), Student.id.is_not(None))
        .outerjoin(User, User.id == StudentAccountLink.user_id)
        .outerjoin(Student, Student.id == StudentAccountLink.student_id)
    )
    if user_id is not None:
        query = query.filter(StudentAccountLink.user_id == user_id)
    if student_id is not None:
        query = query.filter(StudentAccountLink.student_id == student_id)
    rows = (await db.execute(
        query.order_by(StudentAccountLink.created_at.desc(), StudentAccountLink.id)
    )).all()
    return [
        StudentAccountLinkListItemOut(
            id=link.id, user_id=link.user_id, student_id=link.student_id, created_by=link.created_by,
            created_at=as_utc(link.created_at), user_exists=bool(user_ok), student_exists=bool(student_ok),
            is_stale=not (user_ok and student_ok),
        )
        for link, user_ok, student_ok in rows
    ]


@router.delete("/student-account-links/{link_id}", status_code=204)
async def delete_student_account_link(
    link_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a link, for example after a mistake. The student account loses homework access."""
    _require_admin(current_user)
    link = (await db.execute(select(StudentAccountLink).filter(StudentAccountLink.id == link_id))).scalars().first()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found.")
    await db.delete(link)
    db.add(_audit(current_user, "Student Account Unlinked",
                  f"Unlinked account {link.user_id} from student {link.student_id}."))
    await db.commit()
    return Response(status_code=204)


# --- Student-facing homework ----------------------------------------------------------------

NOT_LINKED = "This account isn't linked to a student record."


async def _current_student(db: AsyncSession, user: User) -> Student:
    """The Student linked to this login. Fails closed: wrong role, no link, or a school
    mismatch all give 403. The student is never taken from the request."""
    if user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    student = await resolve_linked_student(db, user)
    if student is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=NOT_LINKED)
    return student


from backend.app.modules.differentiated_homework.schemas import ParentAssignmentSummaryOut  # noqa: E402


async def _summaries_with_progress(db: AsyncSession, assignments) -> List[ParentAssignmentSummaryOut]:
    """Assignment summaries plus the submission status and whether a teacher released the result.
    Shared by the student's own list and a parent's view of a linked child, so both say the same."""
    if not assignments:
        return []
    ids = [a.id for a in assignments]
    submissions = {s.assignment_id: s for s in (await db.execute(
        select(HomeworkSubmissionRecord).filter(HomeworkSubmissionRecord.assignment_id.in_(ids))
    )).scalars().all()}
    released = set((await db.execute(
        select(HomeworkEvaluationRecord.assignment_id).filter(
            HomeworkEvaluationRecord.assignment_id.in_(ids),
            HomeworkEvaluationRecord.status == "released",
        )
    )).scalars().all())
    names = await subject_names(db, (a.subject_id for a in assignments))
    out = []
    for a in assignments:
        submission = submissions.get(a.id)
        out.append(ParentAssignmentSummaryOut(
            **to_student_summary(a, names).model_dump(),
            submission_status=submission.status if submission is not None else "not_started",
            result_released=a.id in released,
        ))
    return out


@router.get("/students/me/homework/assignments", response_model=List[ParentAssignmentSummaryOut])
async def list_my_homework_assignments(
    assignment_status: Optional[AssignmentStatus] = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The logged-in student's own assignments, newest first, with their submission status and
    whether the result has been released (the same flags a linked parent sees)."""
    student = await _current_student(db, current_user)
    query = (
        select(HomeworkAssignmentRecord)
        .filter(HomeworkAssignmentRecord.student_id == student.id)
        .options(selectinload(HomeworkAssignmentRecord.draft).raiseload(HomeworkDraftRecord.items))
    )
    if assignment_status:
        query = query.filter(HomeworkAssignmentRecord.status == assignment_status)
    rows = (await db.execute(
        query.order_by(HomeworkAssignmentRecord.assigned_at.desc(), HomeworkAssignmentRecord.id)
    )).scalars().all()
    return await _summaries_with_progress(db, rows)


@router.get("/students/me/homework/assignments/{assignment_id}", response_model=StudentAssignmentOut)
async def get_my_homework_assignment(
    assignment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """One of the student's own assignments, with questions. Anyone else's assignment returns
    404, the same as a missing one, so a student can't tell whether another assignment exists."""
    student = await _current_student(db, current_user)
    assignment = (await db.execute(
        select(HomeworkAssignmentRecord).filter(
            HomeworkAssignmentRecord.id == assignment_id,
            HomeworkAssignmentRecord.student_id == student.id,
        )
    )).scalars().first()
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found.")
    names = await subject_names(db, [assignment.subject_id])
    return to_student_detail(assignment, names)


# --- Student answer submissions -----------------------------------------------------------------

SUBMISSION_PATH = "/students/me/homework/assignments/{assignment_id}/submission"
SUBMISSION_CHANGED = "This submission was changed by another request. Reload it and try again."
SUBMISSION_STARTED = "A submission was started by another request. Reload it and try again."
SUBMISSION_FAULT = "This submission can't be processed because of a server-side data problem."


async def _my_assignment(db: AsyncSession, user: User, assignment_id: str) -> HomeworkAssignmentRecord:
    """The logged-in student's own assignment. Loaded by its ID and the linked student's ID,
    so another student's assignment gives 404, the same as a missing one."""
    student = await _current_student(db, user)
    assignment = (await db.execute(
        select(HomeworkAssignmentRecord).filter(
            HomeworkAssignmentRecord.id == assignment_id,
            HomeworkAssignmentRecord.student_id == student.id,
        )
    )).scalars().first()
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found.")
    return assignment


async def _load_submission(db: AsyncSession, assignment_id: str) -> Optional[HomeworkSubmissionRecord]:
    """The assignment's submission, if any. Only ever called with an assignment already
    checked to belong to the student."""
    return (await db.execute(
        select(HomeworkSubmissionRecord).filter(HomeworkSubmissionRecord.assignment_id == assignment_id)
    )).scalars().first()


def _submission_error(exc: Exception) -> HTTPException:
    """Map a submission-service error to HTTP. Order matters: SubmissionMismatch is a
    NotSubmittable, but it's a server-side fault (500), not a client conflict."""
    if isinstance(exc, SubmissionMismatch):
        logger.error("Inconsistent homework submission data: %s", exc)
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=SUBMISSION_FAULT)
    if isinstance(exc, InvalidAnswers):
        return HTTPException(status_code=422, detail=[
            AnswerProblemOut(position=p.position, reason=p.reason).model_dump() for p in exc.problems
        ])
    if isinstance(exc, (SubmissionLocked, VersionConflict, NotSubmittable)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    raise exc


# How the "one submission per assignment" violation appears in the driver's message: the
# constraint name on PostgreSQL, the column on SQLite (which doesn't report constraint names).
DUPLICATE_SUBMISSION_MARKERS = ("uq_homework_submissions_assignment", "homework_submissions.assignment_id")


def _is_duplicate_submission(exc: IntegrityError) -> bool:
    message = str(getattr(exc, "orig", exc))
    return any(marker in message for marker in DUPLICATE_SUBMISSION_MARKERS)


async def _commit_submission(db: AsyncSession, assignment_id: str, created: bool) -> None:
    """One commit for the whole request (answers, lock and audit together). On failure the
    transaction is rolled back, so nothing is half-written.
    - StaleDataError: another request changed the submission since it was read -> 409.
    - IntegrityError: 409 only when this request created the submission, the error is the
      unique assignment_id rule, and another request's submission now exists. Any other
      integrity error is a real fault and is re-raised (500)."""
    try:
        await db.commit()
    except StaleDataError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=SUBMISSION_CHANGED)
    except IntegrityError as exc:
        await db.rollback()
        if created and _is_duplicate_submission(exc):
            winner = (await db.execute(
                select(HomeworkSubmissionRecord.id).filter(HomeworkSubmissionRecord.assignment_id == assignment_id)
            )).first()
            if winner is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=SUBMISSION_STARTED)
        raise


def _render(submission: HomeworkSubmissionRecord, assignment: HomeworkAssignmentRecord) -> HomeworkSubmissionOut:
    try:
        return to_submission_out(submission, assignment)
    except SubmissionMismatch as exc:
        raise _submission_error(exc)


def _check_stored_submission(submission: Optional[HomeworkSubmissionRecord],
                             assignment: HomeworkAssignmentRecord) -> None:
    """Before changing anything: refuse (500) if the stored submission is inconsistent, so a
    request on corrupted data writes nothing instead of committing and then failing."""
    if submission is not None:
        _render(submission, assignment)




@router.get(SUBMISSION_PATH, response_model=HomeworkSubmissionOut)
async def get_my_submission(
    assignment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The student's answers to their own assignment. Before the first save this returns the
    not_started state and creates nothing."""
    assignment = await _my_assignment(db, current_user, assignment_id)
    submission = await _load_submission(db, assignment.id)
    if submission is None:
        return empty_submission_out(assignment)
    return _render(submission, assignment)


@router.put(SUBMISSION_PATH, response_model=HomeworkSubmissionOut,
            dependencies=[Depends(_reject_non_finite_json)],
            responses={201: {"model": HomeworkSubmissionOut, "description": "First save: submission created"}})
async def save_my_answers(
    assignment_id: str,
    body: SubmissionAnswersUpdate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save some answers (a partial update). 201 when this creates the submission, 200 after.
    Allowed after the due time; lateness is decided only at final submit."""
    assignment = await _my_assignment(db, current_user, assignment_id)
    existing = await _load_submission(db, assignment.id)
    _check_stored_submission(existing, assignment)
    try:
        submission = save_answers(assignment, existing, body, utc_now())
    except Exception as exc:
        raise _submission_error(exc)
    created = existing is None
    if created:
        db.add(submission)
    await _commit_submission(db, assignment.id, created)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return _render(submission, assignment)


@router.post(f"{SUBMISSION_PATH}/submit", response_model=HomeworkSubmissionOut,
             dependencies=[Depends(_reject_non_finite_json)])
async def submit_my_answers(
    assignment_id: str,
    body: SubmissionFinalizeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Final submit: locks the answers for good. Blank and partial submissions are allowed.
    Late only when strictly after the due time. The audit event is saved in the same
    transaction as the lock."""
    assignment = await _my_assignment(db, current_user, assignment_id)
    existing = await _load_submission(db, assignment.id)
    _check_stored_submission(existing, assignment)
    try:
        submission = finalize_submission(assignment, existing, body, utc_now())
    except Exception as exc:
        raise _submission_error(exc)
    created = existing is None
    if created:
        db.add(submission)
    db.add(_audit(current_user, "Homework Submitted",
                  f"Submitted assignment {assignment.id}{' (late)' if submission.is_late else ''}."))
    await _commit_submission(db, assignment.id, created)
    return _render(submission, assignment)


# --- Teacher-facing, read-only submission views ---------------------------------------------------
# Same access rules as GET /homework/assignments/{assignment_id}: admin all; principal their
# schools; teacher only assignments of drafts they created, in a school they can access.
# Students and parents are refused. Read-only: nothing is created, changed or audited.


async def _require_bearer_token(token: Optional[str] = Depends(oauth2_scheme)) -> None:
    """These views show students' answers, so a real login is required. In DEMO_MODE the shared
    login code treats a request with no token as an admin; here that gives 401 instead."""
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication token required.",
                            headers={"WWW-Authenticate": "Bearer"})


async def _teacher_assignment(db: AsyncSession, user: User, assignment_id: str) -> HomeworkAssignmentRecord:
    """Role check first (no lookup for other roles: 403). Then a missing assignment and one the
    caller can't access give the same 404, so these views don't reveal whether another teacher's
    or school's assignment exists. (The older assignment endpoints keep their 404/403.)"""
    if not role_may_generate_homework(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    assignment = (await db.execute(
        select(HomeworkAssignmentRecord).filter(HomeworkAssignmentRecord.id == assignment_id)
    )).scalars().first()
    if assignment is None or not await can_access_assignment(db, user, assignment):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found.")
    return assignment


async def _roster_entry(db: AsyncSession, assignment: HomeworkAssignmentRecord):
    """The assignment's one student (from the assignment, the authoritative roster) and their
    submission, if any. Two fixed queries; the answers load with the submission."""
    student = await db.get(Student, assignment.student_id)
    submission = await _load_submission(db, assignment.id)
    return student, submission


@router.get("/homework/assignments/{assignment_id}/submissions", response_model=TeacherAssignmentSubmissionsOut,
            dependencies=[Depends(_require_bearer_token)])
async def get_assignment_submissions(
    assignment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Progress on one assignment: counts by state, and each assigned student's status. A
    student with no submission appears as not_started."""
    assignment = await _teacher_assignment(db, current_user, assignment_id)
    student, submission = await _roster_entry(db, assignment)
    try:
        rows = [student_row(assignment, student, submission)]
    except SubmissionMismatch as exc:
        raise _submission_error(exc)
    names = await subject_names(db, [assignment.subject_id])
    return assignment_overview(assignment, names.get(assignment.subject_id), rows)


@router.get("/homework/assignments/{assignment_id}/submissions/{student_id}",
            response_model=TeacherSubmissionDetailOut, dependencies=[Depends(_require_bearer_token)])
async def get_student_submission(
    assignment_id: str,
    student_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """One assigned student's answers next to the frozen questions. not_started if they haven't
    saved anything. A student who isn't on this assignment gives 404."""
    assignment = await _teacher_assignment(db, current_user, assignment_id)
    if student_id != assignment.student_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found on this assignment.")
    student, submission = await _roster_entry(db, assignment)
    try:
        return submission_detail(assignment, student, submission)
    except SubmissionMismatch as exc:
        raise _submission_error(exc)


# --- Homework evaluations: manual grading (teacher) and released results (student) -----------------
# Teacher endpoints: same access as the Phase 3 views (_teacher_assignment: role check -> 403;
# missing or inaccessible assignment -> the same 404) and a real bearer token is required.
# Grading never changes the submission, its answers or any competency score.

EVALUATION_PATH = "/homework/assignments/{assignment_id}/evaluation"
EVALUATION_NOT_FOUND = "Evaluation not found."
EVALUATION_CHANGED = "This evaluation was changed by another request. Reload it and try again."
DUPLICATE_EVALUATION_MARKERS = ("uq_homework_evaluations_submission", "homework_evaluations.submission_id")


async def _reload_grading_context(db: AsyncSession, assignment_id: str):
    """After a rollback the session's objects are expired; reload them with fresh queries (access
    was already checked for this request)."""
    assignment = (await db.execute(
        select(HomeworkAssignmentRecord).filter(HomeworkAssignmentRecord.id == assignment_id)
        .execution_options(populate_existing=True)
    )).scalars().one()
    student = (await db.execute(
        select(Student).filter(Student.id == assignment.student_id).execution_options(populate_existing=True)
    )).scalars().first()
    submission = (await db.execute(
        select(HomeworkSubmissionRecord).filter(HomeworkSubmissionRecord.assignment_id == assignment_id)
        .execution_options(populate_existing=True)
    )).scalars().first()
    return assignment, student, submission


async def _load_evaluation(db: AsyncSession, submission_id: str) -> Optional[HomeworkEvaluationRecord]:
    return (await db.execute(
        select(HomeworkEvaluationRecord).filter(HomeworkEvaluationRecord.submission_id == submission_id)
    )).scalars().first()


def _evaluation_error(exc: Exception) -> HTTPException:
    """Map an evaluation-service error to HTTP. Inconsistent data is a 500 (via the submission
    mapping, which logs it); invalid marks are 422 with one entry per question; state and
    version problems are 409."""
    if isinstance(exc, SubmissionMismatch):  # includes EvaluationMismatch
        return _submission_error(exc)
    if isinstance(exc, InvalidMarks):
        return HTTPException(status_code=422, detail=[
            AnswerProblemOut(position=p.position, reason=p.reason).model_dump() for p in exc.problems
        ])
    if isinstance(exc, EvaluationError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    raise exc


async def _grading_context(db: AsyncSession, user: User, assignment_id: str):
    """The accessible assignment, its student and its submission (any of the last two may be None)."""
    assignment = await _teacher_assignment(db, user, assignment_id)
    student, submission = await _roster_entry(db, assignment)
    return assignment, student, submission


async def _existing_evaluation(db: AsyncSession, assignment, submission) -> HomeworkEvaluationRecord:
    """The assignment's evaluation, checked for consistency before anything uses it."""
    evaluation = await _load_evaluation(db, submission.id) if submission is not None else None
    if evaluation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=EVALUATION_NOT_FOUND)
    try:
        check_evaluation(evaluation, assignment, submission)
    except SubmissionMismatch as exc:
        raise _evaluation_error(exc)
    return evaluation


async def _commit_evaluation(db: AsyncSession) -> None:
    """One commit per request. Version conflicts -> 409; anything else rolls back and re-raises."""
    try:
        await db.commit()
    except StaleDataError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=EVALUATION_CHANGED)
    except IntegrityError:
        await db.rollback()
        raise


def _render_evaluation(evaluation, assignment, submission, student) -> TeacherEvaluationOut:
    try:
        return to_teacher_evaluation(evaluation, assignment, submission, student)
    except SubmissionMismatch as exc:
        raise _evaluation_error(exc)


@router.get("/homework/assignments/{assignment_id}/evaluations", response_model=List[TeacherEvaluationQueueItemOut],
            dependencies=[Depends(_require_bearer_token)])
async def list_assignment_evaluations(
    assignment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submitted homework for this assignment and where its evaluation stands (not_started,
    pending, marked, released). Homework that isn't submitted yet isn't listed. Read-only."""
    assignment, student, submission = await _grading_context(db, current_user, assignment_id)
    if submission is None or submission.status != "submitted":
        return []
    evaluation = await _load_evaluation(db, submission.id)
    try:
        return [to_queue_item(assignment, submission, student, evaluation)]
    except SubmissionMismatch as exc:
        raise _evaluation_error(exc)


@router.post(EVALUATION_PATH, response_model=TeacherEvaluationOut, dependencies=[Depends(_require_bearer_token)],
             responses={201: {"model": TeacherEvaluationOut, "description": "Evaluation created"}})
async def start_evaluation(
    assignment_id: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start marking a submitted homework: 201 with a new pending evaluation (one unmarked item per
    question), or 200 with the existing one. Never creates a second evaluation and never assigns
    marks. 409 if the homework isn't submitted."""
    assignment, student, submission = await _grading_context(db, current_user, assignment_id)
    existing = await _load_evaluation(db, submission.id) if submission is not None else None
    if existing is not None:
        try:
            check_evaluation(existing, assignment, submission)
        except SubmissionMismatch as exc:
            raise _evaluation_error(exc)
        response.status_code = status.HTTP_200_OK
        return _render_evaluation(existing, assignment, submission, student)

    try:
        evaluation = build_evaluation(assignment, submission, current_user.id, utc_now())
    except Exception as exc:
        raise _evaluation_error(exc)
    db.add(evaluation)
    db.add(_audit(current_user, "Homework Evaluation Started", f"Started evaluation of assignment {assignment.id}."))
    assignment_key, submission_key = assignment.id, submission.id  # plain values survive a rollback
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        # Another request started it first (unique submission_id): return that one, as for a
        # repeated request. Any other integrity failure is a real fault.
        if any(marker in str(getattr(exc, "orig", exc)) for marker in DUPLICATE_EVALUATION_MARKERS):
            assignment, student, submission = await _reload_grading_context(db, assignment_key)
            winner = await _load_evaluation(db, submission_key)
            if winner is not None:
                try:
                    check_evaluation(winner, assignment, submission)
                except SubmissionMismatch as mismatch:
                    raise _evaluation_error(mismatch)
                response.status_code = status.HTTP_200_OK
                return _render_evaluation(winner, assignment, submission, student)
        raise
    response.status_code = status.HTTP_201_CREATED
    return _render_evaluation(evaluation, assignment, submission, student)


@router.get(EVALUATION_PATH, response_model=TeacherEvaluationOut, dependencies=[Depends(_require_bearer_token)])
async def get_evaluation(
    assignment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The evaluation with every question, the student's answer, marks and feedback. Read-only;
    404 if marking hasn't been started."""
    assignment, student, submission = await _grading_context(db, current_user, assignment_id)
    evaluation = await _existing_evaluation(db, assignment, submission)
    return _render_evaluation(evaluation, assignment, submission, student)


@router.patch(f"{EVALUATION_PATH}/items", response_model=TeacherEvaluationOut,
              dependencies=[Depends(_require_bearer_token), Depends(_reject_non_finite_json)])
async def mark_evaluation_items(
    assignment_id: str,
    body: EvaluationMarksUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set marks and/or feedback on one or more questions of a pending evaluation. All or
    nothing; 422 lists every invalid entry; 409 on a stale version or a finalized evaluation."""
    assignment, student, submission = await _grading_context(db, current_user, assignment_id)
    evaluation = await _existing_evaluation(db, assignment, submission)
    try:
        apply_marks(evaluation, body, current_user.id, utc_now())
    except Exception as exc:
        raise _evaluation_error(exc)
    await _commit_evaluation(db)
    return _render_evaluation(evaluation, assignment, submission, student)


@router.post(f"{EVALUATION_PATH}/finalize", response_model=TeacherEvaluationOut,
             dependencies=[Depends(_require_bearer_token), Depends(_reject_non_finite_json)])
async def finalize_homework_evaluation(
    assignment_id: str,
    body: EvaluationTransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """pending -> marked, once every question has a mark. Stores the totals; the evaluation is
    read-only afterwards. The audit event is saved in the same transaction."""
    assignment, student, submission = await _grading_context(db, current_user, assignment_id)
    evaluation = await _existing_evaluation(db, assignment, submission)
    try:
        finalize_evaluation(evaluation, body, current_user.id, utc_now())
    except Exception as exc:
        raise _evaluation_error(exc)
    db.add(_audit(current_user, "Homework Evaluation Finalized",
                  f"Finalized evaluation of assignment {assignment.id}: "
                  f"{evaluation.total_awarded}/{evaluation.total_max}."))
    await _commit_evaluation(db)
    return _render_evaluation(evaluation, assignment, submission, student)


async def _record_progress_from_release(db: AsyncSession, assignment, evaluation) -> None:
    """Released homework is graded evidence: move the student's LU/CU/AU/CT parameters for the competencies
    it assessed, keep a timeline snapshot and tell the student and their parents."""
    from backend.app.models.entities import Notification, ParentStudentLink, Student as StudentRow
    from backend.app.services.competency_update import apply_observation, dimension_scores_from_questions, snapshot

    competency = {item.id: item.competency for item in assignment.draft.items}
    graded = [{"competency": competency.get(item.draft_item_id), "awarded_marks": item.awarded_marks or 0,
               "max_marks": item.max_marks} for item in evaluation.items]
    dims = dimension_scores_from_questions(graded)
    record = await db.get(StudentRow, assignment.student_id)
    if record is None or not dims:
        return
    apply_observation(record, dims, weight=0.25)  # homework counts, but less than a supervised test
    awarded = sum(item.awarded_marks or 0 for item in evaluation.items)
    total = sum(item.max_marks for item in evaluation.items)
    db.add(snapshot(record, cycle_number=4, subject_id=assignment.subject_id, assessment_id=None, submission_id=None,
                    notes=f"Differentiated homework released ({awarded}/{total})"))
    message = f"{record.name}'s differentiated homework has been marked: {awarded}/{total}."
    db.add(Notification(user_id=assignment.student_id, title="Homework results released", message=message,
                        type="success", link="/student/homework"))
    for parent_id in (await db.execute(select(ParentStudentLink.parent_user_id).filter_by(
            student_id=assignment.student_id))).scalars().all():
        db.add(Notification(user_id=parent_id, title="Homework results released", message=message,
                            type="info", link="/parent/homework"))


@router.post(f"{EVALUATION_PATH}/release", response_model=TeacherEvaluationOut,
             dependencies=[Depends(_require_bearer_token), Depends(_reject_non_finite_json)])
async def release_homework_evaluation(
    assignment_id: str,
    body: EvaluationTransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """marked -> released: the student can now see the results. Idempotent: releasing again
    returns the evaluation unchanged, with no new audit event. 409 if not finalized."""
    assignment, student, submission = await _grading_context(db, current_user, assignment_id)
    evaluation = await _existing_evaluation(db, assignment, submission)
    try:
        released_now = release_evaluation(evaluation, body, current_user.id, utc_now())
    except Exception as exc:
        raise _evaluation_error(exc)
    if released_now:
        db.add(_audit(current_user, "Homework Results Released",
                      f"Released results of assignment {assignment.id}."))
        await _record_progress_from_release(db, assignment, evaluation)
        assignment_key = assignment.id  # plain value survives a rollback
        try:
            await db.commit()
        except StaleDataError:
            await db.rollback()
            # Lost a race. If the other request released it, this request has what it asked
            # for: return the released evaluation (idempotent), without a second audit event.
            # Any other concurrent change is a real conflict.
            assignment, student, submission = await _reload_grading_context(db, assignment_key)
            winner = (await db.execute(
                select(HomeworkEvaluationRecord).filter(HomeworkEvaluationRecord.submission_id == submission.id)
                .execution_options(populate_existing=True)
            )).scalars().first() if submission is not None else None
            if winner is None or winner.status != "released":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=EVALUATION_CHANGED)
            try:
                check_evaluation(winner, assignment, submission)
            except SubmissionMismatch as exc:
                raise _evaluation_error(exc)
            return _render_evaluation(winner, assignment, submission, student)
        except IntegrityError:
            await db.rollback()
            raise
    return _render_evaluation(evaluation, assignment, submission, student)


# --- AI-assisted evaluation suggestions (teacher-only) -----------------------------------------
# Suggestions never write awarded_marks, never finalize/release, never change submission answers,
# never bump evaluation.version, and never update competency scores. Teacher-only; keys and
# explanations stay off student/parent result endpoints.


def _ai_suggestion_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SuggestionConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, SuggestionUnavailable):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, InvalidSuggestionRequest):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, AIGatewayError):
        code = 503 if isinstance(exc, AINotConfigured) else 504 if isinstance(exc, AIProviderTimeout) else 502
        return HTTPException(status_code=code, detail=exc.public_message)
    return _evaluation_error(exc)


async def _run_ai_suggestions(
    *,
    db: AsyncSession,
    current_user: User,
    assignment_id: str,
    positions: Optional[List[int]],
    replace: bool,
    model: str = "gemini",
) -> AIEvaluationSuggestionsOut:
    assignment, student, submission = await _grading_context(db, current_user, assignment_id)
    evaluation = await _existing_evaluation(db, assignment, submission)
    version_before = evaluation.version
    try:
        from backend.app.services.ai_gateway import QwenTextProvider
        built = await build_suggestions(
            provider=QwenTextProvider() if model == "qwen" else None,
            evaluation=evaluation,
            assignment=assignment,
            submission=submission,
            positions=positions,
            replace=replace,
            teacher_id=current_user.id,
            now=utc_now(),
        )
        persist_suggestions(evaluation, built, current_user.id, utc_now())
    except Exception as exc:
        raise _ai_suggestion_http_error(exc)
    await _commit_evaluation(db)
    # Suggestions must not advance optimistic locking on the evaluation itself.
    if evaluation.version != version_before:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI suggestions must not change the evaluation version.",
        )
    try:
        return to_suggestions_out(evaluation, assignment, submission)
    except Exception as exc:
        raise _ai_suggestion_http_error(exc)


@router.post(
    "/homework/assignments/{assignment_id}/evaluation/ai-suggestions",
    response_model=AIEvaluationSuggestionsOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_bearer_token)],
)
async def generate_ai_evaluation_suggestions(
    assignment_id: str,
    body: AIEvaluationSuggestRequest = AIEvaluationSuggestRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate AI/deterministic mark suggestions for a pending evaluation.

    Does not apply marks. Fails with 409 if suggestions already exist unless replace=true.
    MCQs with a usable frozen key are scored without calling an AI model; open-ended answers use
    the chosen model (`provider`: the local Qwen model or Gemini)."""
    return await _run_ai_suggestions(
        db=db,
        current_user=current_user,
        assignment_id=assignment_id,
        positions=body.positions,
        replace=body.replace,
        model=body.provider,
    )


@router.get(
    "/homework/assignments/{assignment_id}/evaluation/ai-suggestions",
    response_model=AIEvaluationSuggestionsOut,
    dependencies=[Depends(_require_bearer_token)],
)
async def get_ai_evaluation_suggestions(
    assignment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the latest stored suggestions for this evaluation. Teacher-only."""
    assignment, student, submission = await _grading_context(db, current_user, assignment_id)
    evaluation = await _existing_evaluation(db, assignment, submission)
    try:
        return to_suggestions_out(evaluation, assignment, submission)
    except Exception as exc:
        raise _ai_suggestion_http_error(exc)


@router.post(
    "/homework/assignments/{assignment_id}/evaluation/ai-suggestions/rerun",
    response_model=AIEvaluationSuggestionsOut,
    dependencies=[Depends(_require_bearer_token)],
)
async def rerun_ai_evaluation_suggestions(
    assignment_id: str,
    body: AIEvaluationRerunRequest = AIEvaluationRerunRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Replace stored suggestions for the given positions (default: all). Pending evaluations only."""
    return await _run_ai_suggestions(
        db=db,
        current_user=current_user,
        assignment_id=assignment_id,
        positions=body.positions,
        replace=True,
        model=body.provider,
    )


@router.get("/students/me/homework/assignments/{assignment_id}/evaluation", response_model=StudentResultOut)
async def get_my_homework_result(
    assignment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The student's own released results. Identity via StudentAccountLink only. 404 for another
    student's assignment ("Assignment not found.") and for results not released yet, or not
    started ("Evaluation not found."), so unreleased marks can't be detected."""
    assignment = await _my_assignment(db, current_user, assignment_id)
    submission = await _load_submission(db, assignment.id)
    evaluation = await _load_evaluation(db, submission.id) if submission is not None else None
    if evaluation is None or evaluation.status != "released":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=EVALUATION_NOT_FOUND)
    try:
        return to_student_result(evaluation, assignment, submission)
    except SubmissionMismatch as exc:
        raise _evaluation_error(exc)


# --- Parent access to released results ---------------------------------------------------------
# A parent sees exactly what their linked child sees (StudentResultOut, built by the same
# to_student_result): released results only, never answer keys, rubrics or teacher details.
# The link is the existing ParentStudentLink, checked through the existing can_view_student.
# There is no "verified" flag on ParentStudentLink; a link row is the authorization, as in the
# gap-analysis endpoint. No new mapping, and never matching IDs or emails.

PARENT_RESULT_NOT_FOUND = "Result not found."


@router.get("/parents/me/students/{student_id}/homework/assignments/{assignment_id}/evaluation",
            response_model=StudentResultOut)
async def get_child_homework_result(
    student_id: str,
    assignment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A linked child's released homework result. Read-only; parents only (other roles 403).

    Every other case gives the same 404 "Result not found.": no link to this student, the
    student no longer exists, the assignment is missing or belongs to another student, or the
    result isn't released (not started, pending or marked). So a parent can't learn whether
    another student, assignment or unreleased evaluation exists."""
    if current_user.role != "parent":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    not_found = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PARENT_RESULT_NOT_FOUND)

    student = await db.get(Student, student_id)
    if student is None or not await can_view_student(db, current_user, student):
        raise not_found
    assignment = (await db.execute(
        select(HomeworkAssignmentRecord).filter(
            HomeworkAssignmentRecord.id == assignment_id,
            HomeworkAssignmentRecord.student_id == student.id,
        )
    )).scalars().first()
    if assignment is None:
        raise not_found
    submission = await _load_submission(db, assignment.id)
    evaluation = await _load_evaluation(db, submission.id) if submission is not None else None
    if evaluation is None or evaluation.status != "released":
        raise not_found
    try:
        return to_student_result(evaluation, assignment, submission)
    except SubmissionMismatch as exc:
        raise _evaluation_error(exc)



# --- Parent discovery (read-only) --------------------------------------------------------
# Lets a parent find their linked children and those children's assignments so they can open
# a released result without typing IDs. Authorization is the existing ParentStudentLink row
# (the same rule as the result endpoint above). An unlinked or missing student gives the same
# generic 404, so a parent can't probe for other students.

from backend.app.models.entities import ParentStudentLink  # noqa: E402
from backend.app.modules.differentiated_homework.schemas import ParentChildOut  # noqa: E402

PARENT_STUDENT_NOT_FOUND = "Student not found."


def _require_parent(user: User) -> None:
    if user.role != "parent":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")


@router.get("/parents/me/students", response_model=List[ParentChildOut])
async def list_my_children(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Students linked to the logged-in parent, by name. Parents only."""
    _require_parent(current_user)
    rows = (await db.execute(
        select(Student)
        .join(ParentStudentLink, ParentStudentLink.student_id == Student.id)
        .filter(ParentStudentLink.parent_user_id == current_user.id)
        .order_by(Student.name, Student.id)
    )).scalars().all()
    return [ParentChildOut(id=s.id, name=s.name, class_name=s.class_name, school_id=s.school_id) for s in rows]


@router.get("/parents/me/students/{student_id}/homework/assignments",
            response_model=List[ParentAssignmentSummaryOut])
async def list_child_homework_assignments(
    student_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A linked child's assignments, newest first, with submission status and whether a
    teacher has released the result. Read-only; marks are only available via the result
    endpoint, and only once released."""
    _require_parent(current_user)
    student = await db.get(Student, student_id)
    if student is None or not await can_view_student(db, current_user, student):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PARENT_STUDENT_NOT_FOUND)
    assignments = (await db.execute(
        select(HomeworkAssignmentRecord)
        .filter(HomeworkAssignmentRecord.student_id == student.id)
        .options(selectinload(HomeworkAssignmentRecord.draft).raiseload(HomeworkDraftRecord.items))
        .order_by(HomeworkAssignmentRecord.assigned_at.desc(), HomeworkAssignmentRecord.id)
    )).scalars().all()
    return await _summaries_with_progress(db, assignments)
