"""Read-only academic evidence observations for longitudinal progress.

Projects verified Assessment Studio / OCR-published submissions and reviewed
homework into a uniform observation shape. Does not persist a new table yet —
callers treat this as the evidence ledger contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Literal, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import (
    Assessment,
    AssessmentSubmission,
    HomeworkRemediation,
    HumanReview,
    School,
    Student,
)
from backend.app.modules.differentiated_homework.models import (
    HomeworkAssignmentRecord,
    HomeworkEvaluationRecord,
)
from sqlalchemy.orm import selectinload
from backend.app.modules.student_progress.academic_period import (
    AcademicCalendarConfig,
    coerce_date,
    month_key_for,
    resolve_calendar,
    term_id_for_month,
)
from backend.app.modules.student_progress.subject_competency import (
    ACTIVE_ASSESSMENT_STATUSES,
    DIMENSIONS,
    EDUCATOR_DH_EVAL_STATUSES,
    EDUCATOR_HOMEWORK_STATUSES,
    LEARNER_DH_EVAL_STATUSES,
    LEARNER_HOMEWORK_STATUSES,
    _dedupe_submissions,
)

Audience = Literal["educator", "student_or_parent"]
CompetencyDim = Literal["LU", "CU", "AU", "CT"]
SourceType = Literal["assessment_studio", "answer_sheet_ocr", "differentiated_homework"]
ReliabilityClass = Literal["verified_assessment", "verified_homework"]

LONGITUDINAL_METHODOLOGY = "longitudinal.checkpoint.v1.equal_weight_verified"
RELIABILITY_WEIGHT: Dict[ReliabilityClass, float] = {
    "verified_assessment": 1.0,
    "verified_homework": 1.0,
}


@dataclass
class AcademicEvidenceObservation:
    student_id: str
    subject_id: str
    competency: CompetencyDim
    source_type: SourceType
    source_id: str
    assessment_id: Optional[str]
    awarded_marks: Optional[float]
    max_marks: Optional[float]
    normalized_score: float
    assessed_on: date
    academic_year: str
    month_key: str
    term_id: Optional[str]
    verification_status: str
    release_status: str
    methodology_version: str
    reliability_class: ReliabilityClass
    title: Optional[str] = None
    weight: float = 1.0


@dataclass
class EvidenceBundle:
    calendar: AcademicCalendarConfig
    observations: List[AcademicEvidenceObservation] = field(default_factory=list)

    def for_subject(self, subject_id: str) -> List[AcademicEvidenceObservation]:
        return [o for o in self.observations if o.subject_id == subject_id]


async def _school_calendar(db: AsyncSession, student: Student) -> AcademicCalendarConfig:
    school = await db.get(School, student.school_id)
    label = school.academic_year if school else None
    # Optional future: school.calendar_config_json for term overrides.
    return resolve_calendar(label)


def _dim_scores(submission: AssessmentSubmission) -> Dict[str, Optional[float]]:
    return {
        "LU": submission.lu_score,
        "CU": submission.cu_score,
        "AU": submission.au_score,
        "CT": submission.ct_score,
    }


async def collect_academic_evidence(
    db: AsyncSession,
    student: Student,
    audience: Audience,
    *,
    subject_id: Optional[str] = None,
) -> EvidenceBundle:
    """Build deduplicated verified observations for longitudinal use."""
    calendar = await _school_calendar(db, student)
    observations: List[AcademicEvidenceObservation] = []

    rows = (
        await db.execute(
            select(AssessmentSubmission, Assessment)
            .join(Assessment, Assessment.id == AssessmentSubmission.assessment_id)
            .where(
                AssessmentSubmission.student_id == student.id,
                Assessment.school_id == student.school_id,
                Assessment.status.in_(ACTIVE_ASSESSMENT_STATUSES),
            )
        )
    ).all()
    if subject_id:
        rows = [pair for pair in rows if pair[1].subject_id == subject_id]

    # Matching HumanReview ids (for release/provenance only — scores from submission).
    review_pairs = {
        (r.assessment_id, r.student_id)
        for r in (
            await db.execute(
                select(HumanReview).where(
                    HumanReview.student_id == student.id,
                    HumanReview.status == "approved",
                )
            )
        ).scalars().all()
    }

    for submission, assessment in _dedupe_submissions(rows):
        assessed = coerce_date(submission.submission_date) or coerce_date(submission.created_at)
        if assessed is None:
            continue
        mk = month_key_for(assessed, calendar)
        if mk is None:
            # Outside configured academic year — still keep with synthetic month key
            # so evidence is not silently dropped; timeline filters by year later.
            mk = f"{assessed.year:04d}-{assessed.month:02d}"
        term = term_id_for_month(assessed.month, calendar)
        source_type: SourceType = (
            "answer_sheet_ocr" if submission.is_scanned else "assessment_studio"
        )
        release = "released"  # graded/closed/scheduled submissions are educator-visible;
        # learners already see assessment results via existing progress service.
        if audience == "student_or_parent" and assessment.status == "scheduled":
            # Scheduled without marks should not drive learner longitudinal scores.
            if submission.marks_obtained is None:
                continue
        dims = _dim_scores(submission)
        if any(dims[d] is None for d in DIMENSIONS):
            continue
        for dim in DIMENSIONS:
            score = float(dims[dim])  # type: ignore[arg-type]
            observations.append(
                AcademicEvidenceObservation(
                    student_id=student.id,
                    subject_id=assessment.subject_id,
                    competency=dim,  # type: ignore[arg-type]
                    source_type=source_type,
                    source_id=submission.id,
                    assessment_id=assessment.id,
                    awarded_marks=float(submission.marks_obtained),
                    max_marks=float(submission.total_marks),
                    normalized_score=score,
                    assessed_on=assessed,
                    academic_year=calendar.academic_year,
                    month_key=mk,
                    term_id=term,
                    verification_status="verified",
                    release_status=release,
                    methodology_version=LONGITUDINAL_METHODOLOGY,
                    reliability_class="verified_assessment",
                    title=assessment.title,
                    weight=RELIABILITY_WEIGHT["verified_assessment"],
                )
            )

    hw_statuses = EDUCATOR_HOMEWORK_STATUSES if audience == "educator" else LEARNER_HOMEWORK_STATUSES
    hw_q = select(HomeworkRemediation).where(
        HomeworkRemediation.student_id == student.id,
        HomeworkRemediation.status.in_(hw_statuses),
        HomeworkRemediation.score.is_not(None),
    )
    if subject_id:
        hw_q = hw_q.where(HomeworkRemediation.subject_id == subject_id)
    homework = (await db.execute(hw_q)).scalars().all()
    for hw in homework:
        target = (hw.competency_target or "").upper().strip()
        if target not in DIMENSIONS or hw.score is None:
            continue
        assessed = coerce_date(hw.created_at) or coerce_date(hw.due_date)
        if assessed is None:
            continue
        mk = month_key_for(assessed, calendar) or f"{assessed.year:04d}-{assessed.month:02d}"
        term = term_id_for_month(assessed.month, calendar)
        release = "released" if hw.status == "reviewed" else "educator_only"
        if audience == "student_or_parent" and release != "released":
            continue
        observations.append(
            AcademicEvidenceObservation(
                student_id=student.id,
                subject_id=hw.subject_id,
                competency=target,  # type: ignore[arg-type]
                source_type="differentiated_homework",
                source_id=hw.id,
                assessment_id=None,
                awarded_marks=float(hw.score),
                max_marks=100.0,
                normalized_score=float(hw.score),
                assessed_on=assessed,
                academic_year=calendar.academic_year,
                month_key=mk,
                term_id=term,
                verification_status="verified",
                release_status=release,
                methodology_version=LONGITUDINAL_METHODOLOGY,
                reliability_class="verified_homework",
                title=hw.title,
                weight=RELIABILITY_WEIGHT["verified_homework"],
            )
        )

    dh_statuses = EDUCATOR_DH_EVAL_STATUSES if audience == "educator" else LEARNER_DH_EVAL_STATUSES
    dh_q = (
        select(HomeworkEvaluationRecord, HomeworkAssignmentRecord)
        .join(
            HomeworkAssignmentRecord,
            HomeworkAssignmentRecord.id == HomeworkEvaluationRecord.assignment_id,
        )
        .options(selectinload(HomeworkAssignmentRecord.draft))
        .where(
            HomeworkEvaluationRecord.student_id == student.id,
            HomeworkEvaluationRecord.school_id == student.school_id,
            HomeworkAssignmentRecord.student_id == student.id,
            HomeworkAssignmentRecord.school_id == student.school_id,
            HomeworkEvaluationRecord.status.in_(dh_statuses),
            HomeworkEvaluationRecord.total_awarded.is_not(None),
            HomeworkEvaluationRecord.total_max.is_not(None),
        )
    )
    if subject_id:
        dh_q = dh_q.where(HomeworkAssignmentRecord.subject_id == subject_id)
    for evaluation, assignment in (await db.execute(dh_q)).all():
        if evaluation.student_id != assignment.student_id:
            continue
        if not evaluation.total_max:
            continue
        occurred = evaluation.released_at or evaluation.finalized_at or evaluation.updated_at
        assessed = coerce_date(occurred)
        if assessed is None:
            continue
        mk = month_key_for(assessed, calendar) or f"{assessed.year:04d}-{assessed.month:02d}"
        term = term_id_for_month(assessed.month, calendar)
        release = "released" if evaluation.status == "released" else "educator_only"
        if audience == "student_or_parent" and release != "released":
            continue
        score = round(100.0 * float(evaluation.total_awarded) / float(evaluation.total_max), 1)
        title = None
        if assignment.draft is not None:
            title = f"Differentiated homework ({assignment.draft.question_count} questions)"
        # Overall percentage as equal-weight observation across dimensions when item vectors absent.
        for dim in DIMENSIONS:
            observations.append(
                AcademicEvidenceObservation(
                    student_id=student.id,
                    subject_id=assignment.subject_id,
                    competency=dim,  # type: ignore[arg-type]
                    source_type="differentiated_homework",
                    source_id=f"{evaluation.id}:{dim}",
                    assessment_id=None,
                    awarded_marks=float(evaluation.total_awarded),
                    max_marks=float(evaluation.total_max),
                    normalized_score=score,
                    assessed_on=assessed,
                    academic_year=calendar.academic_year,
                    month_key=mk,
                    term_id=term,
                    verification_status="verified",
                    release_status=release,
                    methodology_version=LONGITUDINAL_METHODOLOGY,
                    reliability_class="verified_homework",
                    title=title,
                    weight=RELIABILITY_WEIGHT["verified_homework"],
                )
            )

    # Explicitly unused: review_pairs documents that orphan reviews are handled
    # by the main progress service; longitudinal scores use submissions only to
    # avoid double-counting OCR + submission (same invariant as subject_competency).
    _ = review_pairs

    observations.sort(key=lambda o: (o.assessed_on, o.source_id, o.competency))
    return EvidenceBundle(calendar=calendar, observations=observations)


def weighted_mean(observations: Sequence[AcademicEvidenceObservation]) -> Optional[float]:
    if not observations:
        return None
    total_w = sum(o.weight for o in observations)
    if total_w <= 0:
        return None
    return round(sum(o.normalized_score * o.weight for o in observations) / total_w, 1)
