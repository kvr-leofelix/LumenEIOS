"""Update a student's LU / CU / AU / CT parameters from graded work.

Each graded piece of work (exam, class test, scanned assignment, differentiated homework) yields an
observation for the dimensions its questions actually assessed. Only those dimensions move, as an
exponentially weighted moving average, so one bad test nudges rather than overwrites the profile and
an untested dimension never changes. A snapshot row records every change for the progress timeline.
"""
from __future__ import annotations

from typing import Dict, Iterable, Mapping, Optional

from backend.app.models.entities import Student, StudentCompetencySnapshot

DIMENSIONS = ("LU", "CU", "AU", "CT")
COLUMN = {"LU": "lu_score", "CU": "cu_score", "AU": "au_score", "CT": "ct_score"}
# Weight of a new observation: 0.4 moves a parameter 40% of the way towards the new result.
NEW_EVIDENCE_WEIGHT = 0.4
SUPPORT_THRESHOLD = 55
DIMENSION_NAMES = {"LU": "Language Understanding", "CU": "Conceptual Understanding",
                   "AU": "Application", "CT": "Critical Thinking"}


def clamp(value: float) -> int:
    return max(0, min(100, int(round(value))))


def dimension_scores_from_questions(items: Iterable[Mapping]) -> Dict[str, int]:
    """Per-dimension percentage from graded questions: sum(awarded)/sum(max) per competency.

    Each item needs `competency`, `awarded_marks` and `max_marks`. Dimensions with no questions are
    absent (they were not assessed and must not change)."""
    awarded: Dict[str, float] = {}
    maximum: Dict[str, float] = {}
    for item in items:
        dim = str(item.get("competency") or "").upper()
        top = float(item.get("max_marks") or 0)
        if dim not in DIMENSIONS or top <= 0:
            continue
        got = max(0.0, min(top, float(item.get("awarded_marks") or 0)))
        awarded[dim] = awarded.get(dim, 0.0) + got
        maximum[dim] = maximum.get(dim, 0.0) + top
    return {dim: clamp(100 * awarded[dim] / maximum[dim]) for dim in awarded}


def refresh_support_flag(student: Student) -> None:
    student.overall_score = clamp(sum(getattr(student, COLUMN[d]) for d in DIMENSIONS) / 4)
    weakest = min(DIMENSIONS, key=lambda d: getattr(student, COLUMN[d]))
    weakest_value = getattr(student, COLUMN[weakest])
    student.needs_support = student.overall_score < SUPPORT_THRESHOLD or weakest_value < 42
    student.support_area = DIMENSION_NAMES[weakest] if student.needs_support else None


def apply_observation(student: Student, observed: Mapping[str, int], *, weight: float = NEW_EVIDENCE_WEIGHT) -> Dict[str, int]:
    """Fold one graded result (dimension -> 0..100) into the student's live parameters. Returns the new values."""
    for dim, value in observed.items():
        if dim not in DIMENSIONS:
            continue
        current = getattr(student, COLUMN[dim])
        setattr(student, COLUMN[dim], clamp(current + weight * (clamp(value) - current)))
    refresh_support_flag(student)
    return {d: getattr(student, COLUMN[d]) for d in DIMENSIONS} | {"overall": student.overall_score}


def snapshot(student: Student, *, cycle_number: int, subject_id: Optional[str], assessment_id: Optional[str],
             submission_id: Optional[str], notes: str, recorded_at=None) -> StudentCompetencySnapshot:
    row = StudentCompetencySnapshot(
        student_id=student.id, cycle_number=cycle_number,
        lu_score=student.lu_score, cu_score=student.cu_score, au_score=student.au_score, ct_score=student.ct_score,
        overall_score=student.overall_score, notes=notes, subject_id=subject_id,
        source_assessment_id=assessment_id, source_submission_id=submission_id,
    )
    if recorded_at is not None:
        row.recorded_at = recorded_at
    return row
