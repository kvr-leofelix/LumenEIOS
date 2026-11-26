"""Read-only subject-specific LU/CU/AU/CT aggregation.

See METHODOLOGY.md in this package for the scoring contract.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import (
    Assessment,
    AssessmentSubmission,
    HomeworkRemediation,
    Student,
    Subject,
)
from backend.app.modules.differentiated_homework.models import (
    HomeworkAssignmentRecord,
    HomeworkDraftRecord,
    HomeworkEvaluationRecord,
)
from sqlalchemy.orm import selectinload
from backend.app.modules.student_progress.schemas import (
    Audience,
    CompetencyEvidenceOut,
    OptionalCompetencyScoresOut,
    SubjectCompetencyProfileOut,
)

# Minimum comparable dimension observations required to expose a subject score.
MIN_DIMENSION_EVIDENCE = 1
ACTIVE_ASSESSMENT_STATUSES = ("scheduled", "graded", "closed")
# Legacy HomeworkRemediation statuses
LEARNER_HOMEWORK_STATUSES = {"reviewed"}
EDUCATOR_HOMEWORK_STATUSES = {"assigned", "submitted", "reviewed"}
# Arena Differentiated Homework evaluation statuses
LEARNER_DH_EVAL_STATUSES = {"released"}
EDUCATOR_DH_EVAL_STATUSES = {"marked", "released"}
METHODOLOGY_ID = "subject_competency.v1.mean_of_comparable_0_100"
DIMENSIONS = ("LU", "CU", "AU", "CT")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: Optional[object]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value).isoformat()
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc).isoformat()
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        try:
            year, month, day = int(text[0:4]), int(text[5:7]), int(text[8:10])
            return datetime(year, month, day, tzinfo=timezone.utc).isoformat()
        except ValueError:
            return text
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return _as_utc(parsed).isoformat()
    except ValueError:
        return text


def _mean(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _dedupe_submissions(
    rows: Sequence[Tuple[AssessmentSubmission, Assessment]],
) -> List[Tuple[AssessmentSubmission, Assessment]]:
    """Keep latest submission per (assessment_id, student_id)."""
    by_key: Dict[Tuple[str, str], List[Tuple[AssessmentSubmission, Assessment]]] = {}
    for submission, assessment in rows:
        key = (submission.assessment_id, submission.student_id)
        by_key.setdefault(key, []).append((submission, assessment))

    latest: List[Tuple[AssessmentSubmission, Assessment]] = []
    for group in by_key.values():
        latest.append(
            max(
                group,
                key=lambda pair: (
                    _iso(pair[0].created_at) or _iso(pair[0].submission_date) or "",
                    pair[0].id,
                ),
            )
        )
    return latest


def build_subject_competency_profile(
    *,
    student_id: str,
    subject_id: str,
    subject_name: Optional[str],
    evidence: Sequence[CompetencyEvidenceOut],
) -> SubjectCompetencyProfileOut:
    """Aggregate comparable 0–100 dimension evidence; never fabricate missing values."""
    dim_values: Dict[str, List[float]] = {d: [] for d in DIMENSIONS}
    for item in evidence:
        scores = item.scores
        if scores is None:
            # Single-dimension homework evidence.
            if item.dimension and item.dimension_value is not None:
                dim_values[item.dimension].append(float(item.dimension_value))
            continue
        for dim in DIMENSIONS:
            raw = getattr(scores, dim, None)
            if raw is not None:
                dim_values[dim].append(float(raw))

    dimension_evidence_counts = {d: len(dim_values[d]) for d in DIMENSIONS}
    resolved: Dict[str, Optional[float]] = {}
    for dim in DIMENSIONS:
        if dimension_evidence_counts[dim] >= MIN_DIMENSION_EVIDENCE:
            resolved[dim] = _mean(dim_values[dim])
        else:
            resolved[dim] = None

    available_dims = [d for d in DIMENSIONS if resolved[d] is not None]
    if not evidence:
        status = "unavailable"
    elif len(available_dims) == 4:
        status = "available"
    elif available_dims:
        status = "partial"
    else:
        status = "unavailable"

    overall = _mean([resolved[d] for d in DIMENSIONS if resolved[d] is not None]) if len(available_dims) == 4 else None

    scores_out = None
    if available_dims:
        scores_out = OptionalCompetencyScoresOut(
            LU=resolved["LU"],
            CU=resolved["CU"],
            AU=resolved["AU"],
            CT=resolved["CT"],
            overall=overall,
        )

    return SubjectCompetencyProfileOut(
        student_id=student_id,
        subject_id=subject_id,
        subject_name=subject_name,
        status=status,
        scores=scores_out,
        evidence_count=len(evidence),
        dimension_evidence_counts=dimension_evidence_counts,
        evidence=list(evidence),
        methodology=METHODOLOGY_ID,
    )


async def _subject_name(db: AsyncSession, subject_id: str) -> Optional[str]:
    row = await db.get(Subject, subject_id)
    return row.name if row else None


async def collect_subject_competency_evidence(
    db: AsyncSession,
    student: Student,
    subject_id: str,
    audience: Audience,
) -> List[CompetencyEvidenceOut]:
    """Verified subject-linked competency observations (deduped)."""
    rows = (
        await db.execute(
            select(AssessmentSubmission, Assessment)
            .join(Assessment, Assessment.id == AssessmentSubmission.assessment_id)
            .where(
                AssessmentSubmission.student_id == student.id,
                Assessment.school_id == student.school_id,
                Assessment.subject_id == subject_id,
                Assessment.status.in_(ACTIVE_ASSESSMENT_STATUSES),
            )
        )
    ).all()

    evidence: List[CompetencyEvidenceOut] = []
    for submission, assessment in _dedupe_submissions(rows):
        # Require a complete comparable vector; never invent dimensions.
        if any(
            getattr(submission, f"{d.lower()}_score", None) is None
            for d in ("lu", "cu", "au", "ct")
        ):
            continue
        evidence.append(
            CompetencyEvidenceOut(
                source_type="answer_sheet_ocr" if submission.is_scanned else "assessment_studio",
                source_id=submission.id,
                assessment_id=submission.assessment_id,
                title=assessment.title,
                occurred_at=_iso(submission.submission_date) or _iso(submission.created_at),
                awarded_marks=submission.marks_obtained,
                max_marks=submission.total_marks,
                scores=OptionalCompetencyScoresOut(
                    LU=submission.lu_score,
                    CU=submission.cu_score,
                    AU=submission.au_score,
                    CT=submission.ct_score,
                    overall=submission.overall_score,
                ),
            )
        )

    # Legacy remediation rows (still present in Arena seed / preview APIs).
    statuses = EDUCATOR_HOMEWORK_STATUSES if audience == "educator" else LEARNER_HOMEWORK_STATUSES
    homework = (
        await db.execute(
            select(HomeworkRemediation).where(
                HomeworkRemediation.student_id == student.id,
                HomeworkRemediation.subject_id == subject_id,
                HomeworkRemediation.status.in_(statuses),
                HomeworkRemediation.score.is_not(None),
            )
        )
    ).scalars().all()
    for hw in homework:
        target = (hw.competency_target or "").upper().strip()
        if target not in DIMENSIONS or hw.score is None:
            continue
        evidence.append(
            CompetencyEvidenceOut(
                source_type="differentiated_homework",
                source_id=hw.id,
                assignment_id=hw.id,
                title=hw.title,
                occurred_at=_iso(hw.created_at) or _iso(hw.due_date),
                awarded_marks=hw.score,
                max_marks=100,
                dimension=target,  # type: ignore[arg-type]
                dimension_value=float(hw.score),
            )
        )

    # Arena Differentiated Homework evaluations (primary production path).
    dh_statuses = EDUCATOR_DH_EVAL_STATUSES if audience == "educator" else LEARNER_DH_EVAL_STATUSES
    dh_rows = (
        await db.execute(
            select(HomeworkEvaluationRecord, HomeworkAssignmentRecord)
            .join(
                HomeworkAssignmentRecord,
                HomeworkAssignmentRecord.id == HomeworkEvaluationRecord.assignment_id,
            )
            .options(
                selectinload(HomeworkAssignmentRecord.draft).selectinload(HomeworkDraftRecord.items),
                selectinload(HomeworkEvaluationRecord.items),
            )
            .where(
                HomeworkEvaluationRecord.student_id == student.id,
                HomeworkEvaluationRecord.school_id == student.school_id,
                HomeworkAssignmentRecord.student_id == student.id,
                HomeworkAssignmentRecord.school_id == student.school_id,
                HomeworkAssignmentRecord.subject_id == subject_id,
                HomeworkEvaluationRecord.status.in_(dh_statuses),
            )
        )
    ).all()
    for evaluation, assignment in dh_rows:
        if evaluation.student_id != assignment.student_id:
            continue
        draft_items = {
            item.id: item
            for item in ((assignment.draft.items if assignment.draft is not None else []) or [])
        }
        occurred = _iso(evaluation.released_at or evaluation.finalized_at or evaluation.updated_at)
        title = None
        if assignment.draft is not None:
            title = f"Differentiated homework ({assignment.draft.question_count} questions)"
        emitted_dim = False
        for item in evaluation.items or []:
            if item.awarded_marks is None or item.max_marks is None or item.max_marks <= 0:
                continue
            draft_item = draft_items.get(item.draft_item_id)
            target = ((draft_item.competency if draft_item is not None else "") or "").upper().strip()
            if target not in DIMENSIONS:
                continue
            value = round(100.0 * float(item.awarded_marks) / float(item.max_marks), 1)
            evidence.append(
                CompetencyEvidenceOut(
                    source_type="differentiated_homework",
                    source_id=f"{evaluation.id}:{item.id}",
                    assignment_id=assignment.id,
                    title=title,
                    occurred_at=occurred,
                    awarded_marks=item.awarded_marks,
                    max_marks=item.max_marks,
                    dimension=target,  # type: ignore[arg-type]
                    dimension_value=value,
                )
            )
            emitted_dim = True
        if not emitted_dim and evaluation.total_awarded is not None and evaluation.total_max:
            value = round(100.0 * float(evaluation.total_awarded) / float(evaluation.total_max), 1)
            evidence.append(
                CompetencyEvidenceOut(
                    source_type="differentiated_homework",
                    source_id=evaluation.id,
                    assignment_id=assignment.id,
                    title=title,
                    occurred_at=occurred,
                    awarded_marks=evaluation.total_awarded,
                    max_marks=evaluation.total_max,
                    scores=OptionalCompetencyScoresOut(overall=value),
                )
            )

    evidence.sort(key=lambda e: (e.occurred_at or "", e.source_id), reverse=True)
    return evidence


async def build_subject_competency(
    db: AsyncSession,
    student: Student,
    subject_id: str,
    audience: Audience,
) -> SubjectCompetencyProfileOut:
    evidence = await collect_subject_competency_evidence(db, student, subject_id, audience)
    name = await _subject_name(db, subject_id)
    return build_subject_competency_profile(
        student_id=student.id,
        subject_id=subject_id,
        subject_name=name,
        evidence=evidence,
    )


async def build_all_subject_competencies(
    db: AsyncSession,
    student: Student,
    audience: Audience,
    subject_ids: Optional[Iterable[str]] = None,
) -> List[SubjectCompetencyProfileOut]:
    """Build profiles for requested subjects, or every subject with assessment evidence."""
    if subject_ids is None:
        rows = (
            await db.execute(
                select(Assessment.subject_id)
                .join(AssessmentSubmission, AssessmentSubmission.assessment_id == Assessment.id)
                .where(
                    AssessmentSubmission.student_id == student.id,
                    Assessment.school_id == student.school_id,
                    Assessment.status.in_(ACTIVE_ASSESSMENT_STATUSES),
                )
                .distinct()
            )
        ).scalars().all()
        hw_rows = (
            await db.execute(
                select(HomeworkRemediation.subject_id)
                .where(
                    HomeworkRemediation.student_id == student.id,
                    HomeworkRemediation.score.is_not(None),
                )
                .distinct()
            )
        ).scalars().all()
        dh_rows = (
            await db.execute(
                select(HomeworkAssignmentRecord.subject_id)
                .where(
                    HomeworkAssignmentRecord.student_id == student.id,
                    HomeworkAssignmentRecord.school_id == student.school_id,
                )
                .distinct()
            )
        ).scalars().all()
        subject_ids = sorted({*rows, *hw_rows, *dh_rows})

    profiles: List[SubjectCompetencyProfileOut] = []
    for sid in subject_ids:
        if not sid:
            continue
        profiles.append(await build_subject_competency(db, student, sid, audience))
    profiles.sort(key=lambda p: (p.subject_name or p.subject_id))
    return profiles
