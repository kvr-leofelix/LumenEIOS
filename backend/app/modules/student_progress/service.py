"""Read-only aggregation of verified student performance across LumenEIOS sources.

Rules:
- Never writes marks, competencies, evaluations or AI suggestions.
- Student/parent audience: released Differentiated Homework only.
- Educator audience: marked + released Differentiated Homework.
- Assessment Studio / OCR-approved grades: AssessmentSubmission rows only.
- HumanReview is included only when no matching AssessmentSubmission exists
  (prevents double-counting OCR verify + published submission).
- Multiple submissions/reviews for the same assessment+student keep the latest only.
- Missing marks/percentages stay None — never coerced to zero.
- Trend percentages use awarded/max when both are present (defensible normalization).
- Recommendations are deterministic observations only (no Gemini).
- Rows are school-scoped to the student's school_id.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.entities import (
    Assessment,
    AssessmentSubmission,
    ClassSection,
    HumanReview,
    Student,
    StudentCompetencySnapshot,
    Subject,
)
from backend.app.modules.differentiated_homework.models import (
    HomeworkAssignmentRecord,
    HomeworkDraftRecord,
    HomeworkEvaluationRecord,
)
from backend.app.modules.student_progress import subject_competency
from backend.app.modules.student_progress.schemas import (
    AssessmentHistoryOut,
    Audience,
    CompetencyHistoryOut,
    CompetencyProgressOut,
    CompetencyScoresOut,
    OverallSummaryOut,
    ProgressEventOut,
    RecommendationOut,
    StudentIdentityOut,
    StudentProgressOverviewOut,
    SubjectPerformanceOut,
    SubjectProgressOut,
    SubjectTrendOut,
    TrendPointOut,
)

WEAK_PERCENTAGE = 55.0
LOW_COMPETENCY = 55
MIN_SUBJECT_EVENTS = 2
MIN_TREND_EVENTS = 3
RECENT_LIMIT = 8
# Assessment statuses that may legitimately hold verified submissions.
ACTIVE_ASSESSMENT_STATUSES = ("scheduled", "graded", "closed")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: Optional[object]) -> Optional[str]:
    """Normalize datetimes and YYYY-MM-DD strings to UTC ISO-8601 for stable ordering."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value).isoformat()
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc).isoformat()
    text = str(value).strip()
    if not text:
        return None
    # Date-only strings sort incorrectly against full timestamps unless expanded.
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


def _percentage(awarded: Optional[int], maximum: Optional[int]) -> Optional[float]:
    if awarded is None or maximum is None or maximum <= 0:
        return None
    return round((awarded / maximum) * 100.0, 1)


def _scores(
    lu: Optional[int],
    cu: Optional[int],
    au: Optional[int],
    ct: Optional[int],
    overall: Optional[int] = None,
) -> Optional[CompetencyScoresOut]:
    """Return scores only when all four dimensions are present; never invent zeros."""
    if lu is None or cu is None or au is None or ct is None:
        return None
    return CompetencyScoresOut(
        LU=lu,
        CU=cu,
        AU=au,
        CT=ct,
        overall=overall if overall is not None else round((lu + cu + au + ct) / 4),
    )


def _sort_key(event: ProgressEventOut) -> Tuple[str, str]:
    return (event.occurred_at or "", event.id)


def _mean(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


async def _subject_names(db: AsyncSession, subject_ids: Iterable[str]) -> Dict[str, str]:
    ids = {sid for sid in subject_ids if sid}
    if not ids:
        return {}
    rows = await db.execute(select(Subject.id, Subject.name).where(Subject.id.in_(ids)))
    return {row.id: row.name for row in rows.all()}


async def _load_identity(db: AsyncSession, student: Student) -> StudentIdentityOut:
    section = await db.get(ClassSection, student.class_id)
    subject_ids: List[str] = []
    class_name = student.class_name
    if section is not None and section.school_id == student.school_id:
        class_name = section.name or class_name
        subject_ids = list(section.subject_ids_json or [])
    names = await _subject_names(db, subject_ids)
    return StudentIdentityOut(
        id=student.id,
        name=student.name,
        roll_no=student.roll_no,
        school_id=student.school_id,
        class_id=student.class_id,
        class_name=class_name,
        subject_ids=subject_ids,
        subject_names=[names[sid] for sid in subject_ids if sid in names],
    )


def _homework_statuses(audience: Audience) -> Set[str]:
    if audience == "educator":
        return {"marked", "released"}
    return {"released"}


async def _homework_events(
    db: AsyncSession,
    student: Student,
    audience: Audience,
    names: Dict[str, str],
) -> List[ProgressEventOut]:
    statuses = _homework_statuses(audience)
    rows = (
        await db.execute(
            select(HomeworkEvaluationRecord, HomeworkAssignmentRecord)
            .join(
                HomeworkAssignmentRecord,
                HomeworkAssignmentRecord.id == HomeworkEvaluationRecord.assignment_id,
            )
            .options(
                selectinload(HomeworkAssignmentRecord.draft).raiseload(HomeworkDraftRecord.items),
                selectinload(HomeworkEvaluationRecord.items),
            )
            .where(
                HomeworkEvaluationRecord.student_id == student.id,
                HomeworkEvaluationRecord.school_id == student.school_id,
                HomeworkAssignmentRecord.student_id == student.id,
                HomeworkAssignmentRecord.school_id == student.school_id,
                HomeworkEvaluationRecord.status.in_(statuses),
            )
        )
    ).all()

    events: List[ProgressEventOut] = []
    for evaluation, assignment in rows:
        # Integrity: ignore mismatched evaluation/assignment student ids.
        if evaluation.student_id != assignment.student_id:
            continue
        if evaluation.status == "pending":
            continue
        occurred = evaluation.released_at or evaluation.finalized_at or evaluation.updated_at
        title = None
        if assignment.draft is not None:
            title = f"Differentiated homework ({assignment.draft.question_count} questions)"
        feedback_bits = [
            (item.feedback or "").strip()
            for item in (evaluation.items or [])
            if (item.feedback or "").strip()
        ]
        awarded = evaluation.total_awarded
        maximum = evaluation.total_max
        # Marked/released rows should carry totals; if max is missing/invalid, leave % unavailable.
        events.append(
            ProgressEventOut(
                id=f"differentiated_homework:{evaluation.id}",
                source_type="differentiated_homework",
                source_id=evaluation.id,
                subject_id=assignment.subject_id,
                subject_name=names.get(assignment.subject_id),
                title=title,
                occurred_at=_iso(occurred),
                awarded_marks=awarded,
                max_marks=maximum if maximum is not None and maximum >= 0 else None,
                percentage=_percentage(awarded, maximum),
                evaluation_status=evaluation.status,
                feedback=" · ".join(feedback_bits) if feedback_bits else None,
                assignment_id=assignment.id,
            )
        )
    return events


async def _assessment_events(
    db: AsyncSession,
    student: Student,
    names: Dict[str, str],
) -> Tuple[List[ProgressEventOut], Set[Tuple[str, str]]]:
    """AssessmentSubmission events; latest row wins per (assessment_id, student_id)."""
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

    by_key: Dict[Tuple[str, str], List[Tuple[AssessmentSubmission, Assessment]]] = {}
    for submission, assessment in rows:
        key = (submission.assessment_id, submission.student_id)
        by_key.setdefault(key, []).append((submission, assessment))

    covered: Set[Tuple[str, str]] = set()
    events: List[ProgressEventOut] = []
    for key, group in by_key.items():
        submission, assessment = max(
            group,
            key=lambda pair: (
                _iso(pair[0].created_at) or _iso(pair[0].submission_date) or "",
                pair[0].id,
            ),
        )
        covered.add(key)
        source_type = "answer_sheet_ocr" if submission.is_scanned else "assessment_studio"
        awarded = submission.marks_obtained
        maximum = submission.total_marks
        events.append(
            ProgressEventOut(
                id=f"{source_type}:{submission.id}",
                source_type=source_type,
                source_id=submission.id,
                subject_id=assessment.subject_id,
                subject_name=names.get(assessment.subject_id),
                title=assessment.title,
                occurred_at=_iso(submission.submission_date) or _iso(submission.created_at),
                awarded_marks=awarded,
                max_marks=maximum if maximum is not None and maximum >= 0 else None,
                percentage=_percentage(awarded, maximum),
                evaluation_status="verified",
                is_scanned=submission.is_scanned,
                competency_scores=_scores(
                    submission.lu_score,
                    submission.cu_score,
                    submission.au_score,
                    submission.ct_score,
                    submission.overall_score,
                ),
                feedback=(submission.feedback or "").strip() or None,
                assessment_id=submission.assessment_id,
            )
        )
    return events, covered


async def _orphan_ocr_events(
    db: AsyncSession,
    student: Student,
    covered: Set[Tuple[str, str]],
    names: Dict[str, str],
    audience: Audience,
) -> List[ProgressEventOut]:
    """HumanReview rows with no matching AssessmentSubmission (dedupe per assessment)."""
    reviews = (
        await db.execute(select(HumanReview).where(HumanReview.student_id == student.id))
    ).scalars().all()
    if not reviews:
        return []

    assessment_ids = {r.assessment_id for r in reviews}
    assessments = {}
    if assessment_ids:
        rows = await db.execute(
            select(Assessment).where(
                Assessment.id.in_(assessment_ids),
                Assessment.school_id == student.school_id,
                Assessment.status.in_(ACTIVE_ASSESSMENT_STATUSES),
            )
        )
        assessments = {a.id: a for a in rows.scalars().all()}

    by_key: Dict[Tuple[str, str], List[HumanReview]] = {}
    for review in reviews:
        if (review.assessment_id, review.student_id) in covered:
            continue
        status = (review.status or "").lower()
        if status in {"rejected", "pending", "draft"}:
            continue
        if review.assessment_id not in assessments:
            continue
        by_key.setdefault((review.assessment_id, review.student_id), []).append(review)

    events: List[ProgressEventOut] = []
    for (_assessment_id, _student_id), group in by_key.items():
        review = max(
            group,
            key=lambda row: (_iso(row.reviewed_at) or "", row.id),
        )
        assessment = assessments[review.assessment_id]
        notes = (review.teacher_notes or "").strip() or None
        awarded = review.verified_marks
        maximum = review.total_marks
        events.append(
            ProgressEventOut(
                id=f"answer_sheet_ocr:{review.id}",
                source_type="answer_sheet_ocr",
                source_id=review.id,
                subject_id=assessment.subject_id,
                subject_name=names.get(assessment.subject_id),
                title=assessment.title,
                occurred_at=_iso(review.reviewed_at),
                awarded_marks=awarded,
                max_marks=maximum if maximum is not None and maximum >= 0 else None,
                percentage=_percentage(awarded, maximum),
                evaluation_status=review.status or "approved",
                is_scanned=True,
                feedback=notes if audience == "educator" else None,
                assessment_id=review.assessment_id,
            )
        )
    return events


async def _competency_history_events(
    db: AsyncSession,
    student_id: str,
) -> List[ProgressEventOut]:
    snapshots = (
        await db.execute(
            select(StudentCompetencySnapshot)
            .where(StudentCompetencySnapshot.student_id == student_id)
            .order_by(StudentCompetencySnapshot.recorded_at.asc(), StudentCompetencySnapshot.id.asc())
        )
    ).scalars().all()
    events: List[ProgressEventOut] = []
    for snap in snapshots:
        scores = _scores(snap.lu_score, snap.cu_score, snap.au_score, snap.ct_score, snap.overall_score)
        if scores is None:
            continue
        events.append(
            ProgressEventOut(
                id=f"competency_snapshot:{snap.id}",
                source_type="competency_snapshot",
                source_id=snap.id,
                subject_id=getattr(snap, "subject_id", None),
                title=snap.notes or f"Competency snapshot (cycle {snap.cycle_number})",
                occurred_at=_iso(snap.recorded_at),
                competency_scores=scores,
                evaluation_status="recorded",
                assessment_id=getattr(snap, "source_assessment_id", None),
            )
        )
    return events


async def collect_performance_events(
    db: AsyncSession,
    student: Student,
    audience: Audience,
) -> List[ProgressEventOut]:
    """Verified score-bearing academic events (excludes competency-only snapshots)."""
    # Collect subject ids from the same filtered sources used for events (one round-trip each).
    homework_subject_ids = (
        await db.execute(
            select(HomeworkAssignmentRecord.subject_id).where(
                HomeworkAssignmentRecord.student_id == student.id,
                HomeworkAssignmentRecord.school_id == student.school_id,
            )
        )
    ).scalars().all()
    assessment_subject_ids = (
        await db.execute(
            select(Assessment.subject_id)
            .join(AssessmentSubmission, AssessmentSubmission.assessment_id == Assessment.id)
            .where(
                AssessmentSubmission.student_id == student.id,
                Assessment.school_id == student.school_id,
            )
        )
    ).scalars().all()
    names = await _subject_names(db, list(homework_subject_ids) + list(assessment_subject_ids))

    homework = await _homework_events(db, student, audience, names)
    assessments, covered = await _assessment_events(db, student, names)
    orphans = await _orphan_ocr_events(db, student, covered, names, audience)

    events = homework + assessments + orphans
    events.sort(key=_sort_key, reverse=True)
    return events


def build_subject_performance(events: Sequence[ProgressEventOut]) -> List[SubjectPerformanceOut]:
    by_subject: Dict[str, List[ProgressEventOut]] = {}
    for event in events:
        if not event.subject_id:
            continue
        by_subject.setdefault(event.subject_id, []).append(event)

    subjects: List[SubjectPerformanceOut] = []
    for subject_id, rows in by_subject.items():
        ordered = sorted(rows, key=_sort_key)
        percentages = [e.percentage for e in ordered if e.percentage is not None]
        comparable_count = len(percentages)
        latest = next((e for e in reversed(ordered) if e.percentage is not None), None)
        subjects.append(
            SubjectPerformanceOut(
                subject_id=subject_id,
                subject_name=rows[0].subject_name,
                event_count=len(rows),
                comparable_event_count=comparable_count,
                average_percentage=_mean(percentages) if percentages else None,
                latest_percentage=latest.percentage if latest else None,
                latest_occurred_at=latest.occurred_at if latest else None,
            )
        )
    subjects.sort(key=lambda s: (s.subject_name or s.subject_id))
    return subjects


def build_trends(events: Sequence[ProgressEventOut]) -> Tuple[List[TrendPointOut], List[SubjectTrendOut]]:
    """Chronological comparable percentages only (awarded÷max). Insufficient points stay empty."""
    points: List[TrendPointOut] = []
    for event in sorted(events, key=_sort_key):
        if event.percentage is None or not event.occurred_at:
            continue
        if event.max_marks is None or event.max_marks <= 0 or event.awarded_marks is None:
            continue
        points.append(
            TrendPointOut(
                occurred_at=event.occurred_at,
                percentage=event.percentage,
                subject_id=event.subject_id,
                subject_name=event.subject_name,
                source_type=event.source_type,
                source_id=event.source_id,
                title=event.title,
            )
        )

    by_subject: Dict[str, List[TrendPointOut]] = {}
    for point in points:
        if point.subject_id:
            by_subject.setdefault(point.subject_id, []).append(point)

    subject_trends = [
        SubjectTrendOut(
            subject_id=subject_id,
            subject_name=rows[0].subject_name,
            points=rows,
        )
        for subject_id, rows in sorted(by_subject.items(), key=lambda item: item[0])
    ]
    return points, subject_trends


def _competency_progress(student: Student, history: Sequence[ProgressEventOut]) -> CompetencyProgressOut:
    # Live LU/CU/AU/CT columns are required on Student; read them as recorded (never invent).
    current = _scores(
        student.lu_score, student.cu_score, student.au_score, student.ct_score, student.overall_score
    )
    baseline = _scores(
        student.baseline_lu,
        student.baseline_cu,
        student.baseline_au,
        student.baseline_ct,
        student.baseline_overall,
    )
    assert current is not None and baseline is not None
    return CompetencyProgressOut(
        current=current,
        baseline=baseline,
        source="students.live_scores",
        history=list(history),
    )


async def _missing_assessment_recommendations(
    db: AsyncSession,
    student: Student,
) -> List[RecommendationOut]:
    assessments = (
        await db.execute(
            select(Assessment).where(
                Assessment.class_id == student.class_id,
                Assessment.school_id == student.school_id,
                Assessment.status.in_(ACTIVE_ASSESSMENT_STATUSES),
            )
        )
    ).scalars().all()
    if not assessments:
        return []

    submitted_ids = set(
        (
            await db.execute(
                select(AssessmentSubmission.assessment_id).where(
                    AssessmentSubmission.student_id == student.id
                )
            )
        ).scalars().all()
    )
    missing = [a for a in assessments if a.id not in submitted_ids]
    if not missing:
        return []
    evidence = [f"{a.title} ({a.date})" for a in missing[:5]]
    return [
        RecommendationOut(
            kind="missing_assessment",
            summary=f"{len(missing)} class assessment(s) have no verified submission for this student.",
            evidence=evidence,
        )
    ]


async def _incomplete_homework_recommendations(
    db: AsyncSession,
    student: Student,
    audience: Audience,
) -> List[RecommendationOut]:
    assignments = (
        await db.execute(
            select(HomeworkAssignmentRecord).where(
                HomeworkAssignmentRecord.student_id == student.id,
                HomeworkAssignmentRecord.school_id == student.school_id,
            )
        )
    ).scalars().all()
    if not assignments:
        return []

    evaluation_by_assignment = {
        row.assignment_id: row
        for row in (
            await db.execute(
                select(HomeworkEvaluationRecord).where(
                    HomeworkEvaluationRecord.student_id == student.id,
                    HomeworkEvaluationRecord.school_id == student.school_id,
                )
            )
        ).scalars().all()
    }
    required = _homework_statuses(audience)
    incomplete = []
    for assignment in assignments:
        evaluation = evaluation_by_assignment.get(assignment.id)
        if evaluation is None or evaluation.status not in required:
            # Pending/draft/not_started are incomplete for this audience; never treat as scored.
            status = evaluation.status if evaluation is not None else "not_started"
            if status == "pending" or evaluation is None or status not in required:
                incomplete.append(f"Assignment {assignment.id} ({status})")
    if not incomplete:
        return []
    return [
        RecommendationOut(
            kind="incomplete_homework",
            summary=f"{len(incomplete)} differentiated homework assignment(s) lack a verified result for this view.",
            evidence=incomplete[:5],
        )
    ]


def build_recommendations(
    student: Student,
    events: Sequence[ProgressEventOut],
    subjects: Sequence[SubjectPerformanceOut],
    trends: Sequence[TrendPointOut],
    extra: Optional[Sequence[RecommendationOut]] = None,
) -> List[RecommendationOut]:
    out: List[RecommendationOut] = []

    for subject in subjects:
        comparable = getattr(subject, "comparable_event_count", None)
        if comparable is None:
            comparable = subject.event_count
        if comparable < MIN_SUBJECT_EVENTS or subject.average_percentage is None:
            continue
        if subject.average_percentage < WEAK_PERCENTAGE:
            out.append(
                RecommendationOut(
                    kind="weak_subject",
                    summary=(
                        f"Repeated weak performance in "
                        f"{subject.subject_name or subject.subject_id} "
                        f"(average {subject.average_percentage}%)."
                    ),
                    evidence=[
                        f"{comparable} comparable percentage results; average {subject.average_percentage}%"
                    ],
                    subject_id=subject.subject_id,
                )
            )

    # Live competency flags only when dimensions are present (never invent).
    current = _scores(student.lu_score, student.cu_score, student.au_score, student.ct_score, student.overall_score)
    if current is not None:
        for dim, score in (("LU", current.LU), ("CU", current.CU), ("AU", current.AU), ("CT", current.CT)):
            if score < LOW_COMPETENCY:
                out.append(
                    RecommendationOut(
                        kind="low_competency",
                        summary=f"Competency {dim} is currently low at {score}%.",
                        evidence=[f"Live {dim} score={score} (source students.live_scores)"],
                        competency=dim,
                    )
                )

    # Trends require enough comparable points; never infer from a single result.
    if len(trends) >= MIN_TREND_EVENTS:
        mid = len(trends) // 2
        earlier = _mean([p.percentage for p in trends[:mid]])
        later = _mean([p.percentage for p in trends[mid:]])
        if earlier is not None and later is not None:
            delta = round(later - earlier, 1)
            if delta >= 8:
                out.append(
                    RecommendationOut(
                        kind="improving_trend",
                        summary=f"Performance improved across recent verified results (+{delta} percentage points).",
                        evidence=[
                            f"Earlier average {earlier}% over {mid} results",
                            f"Later average {later}% over {len(trends) - mid} results",
                        ],
                    )
                )
            elif delta <= -8:
                out.append(
                    RecommendationOut(
                        kind="declining_trend",
                        summary=f"Performance declined across recent verified results ({delta} percentage points).",
                        evidence=[
                            f"Earlier average {earlier}% over {mid} results",
                            f"Later average {later}% over {len(trends) - mid} results",
                        ],
                    )
                )

    if extra:
        out.extend(extra)
    return out


async def build_overview(
    db: AsyncSession,
    student: Student,
    audience: Audience,
) -> StudentProgressOverviewOut:
    identity = await _load_identity(db, student)
    events = await collect_performance_events(db, student, audience)
    competency_history = await _competency_history_events(db, student.id)
    subjects = build_subject_performance(events)
    subject_competencies = await subject_competency.build_all_subject_competencies(
        db, student, audience
    )
    by_subject_comp = {p.subject_id: p for p in subject_competencies}
    subjects = [
        s.model_copy(update={"competencies": by_subject_comp.get(s.subject_id)})
        for s in subjects
    ]
    known_ids = {s.subject_id for s in subjects}
    for profile in subject_competencies:
        if profile.subject_id in known_ids:
            continue
        subjects.append(
            SubjectPerformanceOut(
                subject_id=profile.subject_id,
                subject_name=profile.subject_name,
                event_count=0,
                comparable_event_count=0,
                average_percentage=None,
                latest_percentage=None,
                latest_occurred_at=None,
                competencies=profile,
            )
        )
    subjects.sort(key=lambda s: (s.subject_name or s.subject_id))
    trends, subject_trends = build_trends(events)
    percentages = [e.percentage for e in events if e.percentage is not None]
    extra = []
    extra.extend(await _missing_assessment_recommendations(db, student))
    extra.extend(await _incomplete_homework_recommendations(db, student, audience))
    recommendations = build_recommendations(student, events, subjects, trends, extra)

    latest = events[0].occurred_at if events else None
    return StudentProgressOverviewOut(
        student=identity,
        audience=audience,
        overall=OverallSummaryOut(
            verified_event_count=len(events),
            average_percentage=_mean(percentages),
            latest_activity_at=latest,
        ),
        subjects=subjects,
        competencies=_competency_progress(student, competency_history),
        subject_competencies=subject_competencies,
        recent_activity=events[:RECENT_LIMIT],
        trends=trends,
        subject_trends=subject_trends,
        recommendations=recommendations,
        generated_at=_iso(utc_now()) or "",
    )


async def build_history(
    db: AsyncSession,
    student: Student,
    audience: Audience,
    subject_id: Optional[str] = None,
) -> AssessmentHistoryOut:
    events = await collect_performance_events(db, student, audience)
    if subject_id:
        events = [e for e in events if e.subject_id == subject_id]
    return AssessmentHistoryOut(
        student_id=student.id,
        audience=audience,
        events=events,
        generated_at=_iso(utc_now()) or "",
    )


async def build_competency_history(
    db: AsyncSession,
    student: Student,
    audience: Audience = "educator",
) -> CompetencyHistoryOut:
    history = await _competency_history_events(db, student.id)
    current = _scores(
        student.lu_score, student.cu_score, student.au_score, student.ct_score, student.overall_score
    )
    baseline = _scores(
        student.baseline_lu,
        student.baseline_cu,
        student.baseline_au,
        student.baseline_ct,
        student.baseline_overall,
    )
    assert current is not None and baseline is not None
    subject_competencies = await subject_competency.build_all_subject_competencies(
        db, student, audience
    )
    return CompetencyHistoryOut(
        student_id=student.id,
        current=current,
        baseline=baseline,
        source="students.live_scores",
        history=history,
        generated_at=_iso(utc_now()) or "",
        subject_competencies=subject_competencies,
    )


async def build_subject_progress(
    db: AsyncSession,
    student: Student,
    audience: Audience,
    subject_id: str,
) -> SubjectProgressOut:
    history = await build_history(db, student, audience, subject_id=subject_id)
    events = history.events
    subjects = build_subject_performance(events)
    competencies = await subject_competency.build_subject_competency(
        db, student, subject_id, audience
    )
    performance = subjects[0] if subjects else SubjectPerformanceOut(
        subject_id=subject_id,
        subject_name=competencies.subject_name,
        event_count=0,
        comparable_event_count=0,
        average_percentage=None,
        latest_percentage=None,
        latest_occurred_at=None,
        competencies=competencies,
    )
    if subjects:
        performance = performance.model_copy(update={"competencies": competencies})
    if performance.subject_name is None:
        names = await _subject_names(db, [subject_id])
        performance = performance.model_copy(update={"subject_name": names.get(subject_id)})

    trends, _ = build_trends(events)
    recommendations = [
        r
        for r in build_recommendations(student, events, subjects, trends)
        if r.subject_id == subject_id or r.kind in {"improving_trend", "declining_trend"}
    ]
    return SubjectProgressOut(
        student_id=student.id,
        subject_id=subject_id,
        subject_name=performance.subject_name,
        performance=performance,
        competencies=competencies,
        events=events,
        trend=trends,
        recommendations=recommendations,
        generated_at=_iso(utc_now()) or "",
    )
