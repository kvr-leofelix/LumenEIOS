"""Monthly (Jun–May) and term-wise longitudinal checkpoints."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import Student, Subject
from backend.app.modules.student_progress.academic_period import (
    academic_month_keys,
    DEFAULT_TERM_LABELS,
)
from backend.app.modules.student_progress.evidence import (
    AcademicEvidenceObservation,
    Audience,
    LONGITUDINAL_METHODOLOGY,
    collect_academic_evidence,
    weighted_mean,
)
from backend.app.modules.student_progress.subject_competency import DIMENSIONS

PeriodKind = Literal["month", "term"]


def _checkpoint_from_obs(
    *,
    student_id: str,
    subject_id: str,
    subject_name: Optional[str],
    period_kind: PeriodKind,
    period_id: str,
    period_label: str,
    academic_year: str,
    rows: Sequence[AcademicEvidenceObservation],
) -> dict:
    by_dim: Dict[str, List[AcademicEvidenceObservation]] = {d: [] for d in DIMENSIONS}
    for obs in rows:
        by_dim[obs.competency].append(obs)

    scores: Dict[str, Optional[float]] = {}
    evidence_ids: List[str] = []
    assessment_ids = set()
    for dim in DIMENSIONS:
        scores[dim] = weighted_mean(by_dim[dim])
        for obs in by_dim[dim]:
            evidence_ids.append(f"{obs.source_type}:{obs.source_id}:{obs.competency}")
            if obs.assessment_id:
                assessment_ids.add(obs.assessment_id)

    available = [d for d in DIMENSIONS if scores[d] is not None]
    if not rows:
        status = "unavailable"
    elif len(available) == 4:
        status = "available"
    elif available:
        status = "partial"
    else:
        status = "unavailable"

    overall = None
    if len(available) == 4:
        overall = round(sum(scores[d] for d in DIMENSIONS if scores[d] is not None) / 4, 1)  # type: ignore[misc]

    return {
        "student_id": student_id,
        "subject_id": subject_id,
        "subject_name": subject_name,
        "period_kind": period_kind,
        "period_id": period_id,
        "period_label": period_label,
        "academic_year": academic_year,
        "status": status,
        "scores": {
            "LU": scores["LU"],
            "CU": scores["CU"],
            "AU": scores["AU"],
            "CT": scores["CT"],
            "overall": overall,
        }
        if available
        else None,
        "evidence_count": len({(o.source_type, o.source_id) for o in rows}),
        "assessment_count": len(assessment_ids),
        "coverage": {
            "dimensions_present": len(available),
            "dimensions_total": 4,
        },
        "methodology": LONGITUDINAL_METHODOLOGY,
        "evidence_ids": evidence_ids[:50],
    }


async def build_subject_timeline(
    db: AsyncSession,
    student: Student,
    subject_id: str,
    audience: Audience,
) -> dict:
    bundle = await collect_academic_evidence(db, student, audience, subject_id=subject_id)
    subject = await db.get(Subject, subject_id)
    subject_name = subject.name if subject else None
    calendar = bundle.calendar
    subject_obs = bundle.for_subject(subject_id)

    months = []
    for mk in academic_month_keys(calendar):
        month_num = int(mk[5:7])
        label = f"{mk} ({_month_name(month_num)})"
        rows = [o for o in subject_obs if o.month_key == mk]
        months.append(
            _checkpoint_from_obs(
                student_id=student.id,
                subject_id=subject_id,
                subject_name=subject_name,
                period_kind="month",
                period_id=mk,
                period_label=label,
                academic_year=calendar.academic_year,
                rows=rows,
            )
        )

    terms = []
    for term_id, label in (calendar.term_labels or DEFAULT_TERM_LABELS).items():
        rows = [o for o in subject_obs if o.term_id == term_id]
        terms.append(
            _checkpoint_from_obs(
                student_id=student.id,
                subject_id=subject_id,
                subject_name=subject_name,
                period_kind="term",
                period_id=term_id,
                period_label=label,
                academic_year=calendar.academic_year,
                rows=rows,
            )
        )

    return {
        "student_id": student.id,
        "subject_id": subject_id,
        "subject_name": subject_name,
        "academic_year": calendar.academic_year,
        "methodology": LONGITUDINAL_METHODOLOGY,
        "months": months,
        "terms": terms,
        "observation_count": len(subject_obs),
        "note": (
            "Monthly/term scores are reconstructed from dated verified evidence; "
            "global competency snapshots are not attributed to subjects."
        ),
    }


def _month_name(month: int) -> str:
    names = (
        "",
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )
    return names[month] if 1 <= month <= 12 else str(month)


async def build_period_evidence(
    db: AsyncSession,
    student: Student,
    subject_id: str,
    audience: Audience,
    *,
    period_kind: PeriodKind,
    period_id: str,
) -> dict:
    """Drill-down: observations that produced a month or term checkpoint."""
    bundle = await collect_academic_evidence(db, student, audience, subject_id=subject_id)
    if period_kind == "month":
        rows = [o for o in bundle.for_subject(subject_id) if o.month_key == period_id]
    else:
        rows = [o for o in bundle.for_subject(subject_id) if o.term_id == period_id]

    return {
        "student_id": student.id,
        "subject_id": subject_id,
        "period_kind": period_kind,
        "period_id": period_id,
        "methodology": LONGITUDINAL_METHODOLOGY,
        "observations": [
            {
                "student_id": o.student_id,
                "subject_id": o.subject_id,
                "competency": o.competency,
                "source_type": o.source_type,
                "source_id": o.source_id,
                "assessment_id": o.assessment_id,
                "awarded_marks": o.awarded_marks,
                "max_marks": o.max_marks,
                "normalized_score": o.normalized_score,
                "assessed_on": o.assessed_on.isoformat(),
                "academic_year": o.academic_year,
                "month_key": o.month_key,
                "term_id": o.term_id,
                "verification_status": o.verification_status,
                "release_status": o.release_status,
                "methodology_version": o.methodology_version,
                "reliability_class": o.reliability_class,
                "title": o.title,
                "weight": o.weight,
            }
            for o in rows
        ],
    }
