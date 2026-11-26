"""Only explicit teacher-reviewed observations qualify. Legacy scores remain unverified."""
from collections import defaultdict
from datetime import timezone
from sqlalchemy import select
from backend.app.core.config import settings
from backend.app.models.entities import AssessmentSubmission, Assessment, GradingBatchItem
from backend.app.modules.differentiated_homework.models import HomeworkSubmissionRecord
from .models import LearningEvidence, LearningAssignment, LearningAttempt
from .assessment_models import AssessmentResultRecord
from backend.app.services.assessment_results import assessment_evidence
from backend.app.services.panchapadi import assessment_stage_views


def timestamp(value):
    """SQLite returns naive datetimes; persisted application timestamps are UTC."""
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()


def eligible(evidence, attempt):
    reviews = [r for r in attempt.evaluations if r["kind"] == "teacher"]
    latest = reviews[-1] if reviews else None
    return bool(evidence.provenance == "confirmed" and attempt.completed and latest
                and evidence.observation_key.startswith(latest["revision_id"] + ":")
                and evidence.score is not None and evidence.maximum is not None
                and evidence.maximum > 0 and 0 <= evidence.score <= evidence.maximum)


async def evidence_rows(db, student_id):
    return (await db.execute(select(LearningEvidence, LearningAttempt, LearningAssignment)
        .join(LearningAttempt, LearningEvidence.attempt_id == LearningAttempt.id)
        .join(LearningAssignment, LearningEvidence.assignment_id == LearningAssignment.id)
        .where(LearningEvidence.student_id == student_id,
               LearningAssignment.student_id == student_id,
               LearningAttempt.assignment_id == LearningAssignment.id)
        .order_by(LearningEvidence.recorded_at, LearningEvidence.id))).all()


async def support(db, student_id):
    groups = defaultdict(list)
    for e, attempt, assignment in await evidence_rows(db, student_id):
        if eligible(e, attempt) and assignment.snapshot.get("topic_id"):
            s = assignment.snapshot
            groups[(s["subject_id"], s["topic_id"], e.competency)].append((e, attempt, assignment))
    # Include assigned topics even when no eligible scores exist.
    assignments = list((await db.scalars(select(LearningAssignment).where(
        LearningAssignment.student_id == student_id))).all())
    for a in assignments:
        if a.snapshot.get("topic_id"):
            groups.setdefault((a.snapshot["subject_id"], a.snapshot["topic_id"], a.snapshot["competency"]), [])
    findings = []
    for (subject, topic, competency), rows in groups.items():
        rows = rows[-settings.LEARNSPHERE_RECENT_OBSERVATIONS:]
        n = len(rows)
        activities = len({a.activity_id for _, _, a in rows})
        enough = n >= settings.LEARNSPHERE_MIN_OBSERVATIONS and activities >= settings.LEARNSPHERE_MIN_ACTIVITIES
        score = round(100 * sum(e.score for e, _, _ in rows) / sum(e.maximum for e, _, _ in rows), 1) if rows else None
        gap = enough and score < settings.LEARNSPHERE_SUPPORT_THRESHOLD
        name = next(a.snapshot["topic_title"] for a in assignments if a.snapshot["topic_id"] == topic)
        findings.append({"subject_id": subject, "topic_id": topic, "topic": name, "competency": competency,
            "observations": n, "activities": activities, "score_pct": score,
            "status": "More practice data needed" if not enough else "Practice suggested" if gap else "Progress supported by evidence",
            "reason": f"{n} teacher-confirmed observations across {activities} activities." + (f" Weighted score {score}%." if score is not None else ""),
            "rule": f"At least {settings.LEARNSPHERE_MIN_OBSERVATIONS} observations across {settings.LEARNSPHERE_MIN_ACTIVITIES} activities; recent weighted score below {settings.LEARNSPHERE_SUPPORT_THRESHOLD}% suggests practice.",
            "suggestion": {"LU": "Explain key terms and restate the instructions.", "CU": "Explain the concept with an example and a concept map.", "AU": "Apply the concept to a practical mission.", "CT": "Compare explanations and justify a conclusion."}[competency] if gap else "Collect further comparable practice evidence." if not enough else "Continue with a follow-up activity.",
            "sources": [{"id": e.id, "assignment_id": a.id, "attempt_id": at.id, "score": e.score,
                "maximum": e.maximum, "correct": e.correct, "hints": at.hints,
                "recorded_at": timestamp(e.recorded_at), "source": e.source} for e, at, a in rows]})
    assessment_groups = defaultdict(list)
    for observation in await assessment_evidence(db, student_id):
        assessment_groups[(observation["subject_id"], observation["topic_id"], observation["competency"])].append(observation)
    assessment_findings = []
    for (subject, topic, competency), observations in assessment_groups.items():
        assessment_findings.append({"subject_id": subject, "topic_id": topic, "topic": observations[0]["topic"],
            "competency": competency, "observations": len(observations),
            "assessments": len({o["assessment_id"] for o in observations}),
            "score_pct": round(100 * sum(o["score"] for o in observations) / sum(o["maximum"] for o in observations), 1),
            "status": "Teacher-reviewed assessment evidence",
            "suggestion": "Review the incorrect or partially credited responses with your teacher." if any(o["score"] < o["maximum"] for o in observations) else "Continue collecting comparable learning evidence.",
            "reason": "Assessment questions are scored observations, not learning activities. The three-observations/across-two-activities rule is unchanged.",
            "sources": observations})
    return {"student_id": student_id, "findings": findings, "assessment_findings": assessment_findings,
            "panchapadi_assessments": await assessment_stage_views(db, student_id),
            "empty_message": "More practice data needed" if not findings else None}


async def journey(db, student_id):
    assignments = list((await db.scalars(select(LearningAssignment).where(
        LearningAssignment.student_id == student_id).order_by(LearningAssignment.assigned_at))).all())
    attempts = list((await db.scalars(select(LearningAttempt).join(LearningAssignment).where(
        LearningAssignment.student_id == student_id).order_by(LearningAttempt.submitted_at))).all())
    timeline = [{"kind": "assigned", "date": timestamp(a.assigned_at), "title": a.snapshot["title"],
        "stage": a.snapshot["stage"], "assignment_id": a.id, "topic": a.snapshot["topic_title"],
        "subject_id": a.snapshot["subject_id"], "competency": a.snapshot["competency"],
        "intervention_for": a.intervention_for, "detail": "Activity assigned"} for a in assignments]
    by_id = {a.id: a for a in assignments}
    for at in attempts:
        a = by_id[at.assignment_id]
        timeline.append({"kind": "submitted", "date": timestamp(at.submitted_at), "title": a.snapshot["title"],
            "stage": a.snapshot["stage"], "topic": a.snapshot["topic_title"], "subject_id": a.snapshot["subject_id"],
            "competency": a.snapshot["competency"], "assignment_id": a.id,
            "detail": "Response submitted; completion and understanding require review."})
        for revision in at.evaluations:
            timeline.append({"kind": revision["kind"], "date": revision["date"], "title": a.snapshot["title"],
                "stage": a.snapshot["stage"], "topic": a.snapshot["topic_title"], "subject_id": a.snapshot["subject_id"],
                "competency": a.snapshot["competency"], "assignment_id": a.id,
                "detail": revision.get("outcome", "AI feedback available; not a teacher-verified score.")})
    legacy = (await db.execute(select(AssessmentSubmission, Assessment).join(Assessment,
        AssessmentSubmission.assessment_id == Assessment.id).where(AssessmentSubmission.student_id == student_id))).all()
    simulated_ids = set((await db.scalars(select(GradingBatchItem.submission_id).where(
        GradingBatchItem.submission_id.in_([sub.id for sub, _ in legacy])))).all())
    result_records = (await db.execute(select(AssessmentResultRecord, Assessment).join(Assessment,
        Assessment.id == AssessmentResultRecord.assessment_id).where(AssessmentResultRecord.student_id == student_id))).all()
    linked_submissions = {r.submission_id for r, _ in result_records if r.submission_id}
    for result, assessment in result_records:
        timeline.append({"kind": "assessment_submitted", "date": timestamp(result.submitted_at), "title": assessment.title,
            "subject_id": result.subject_id, "stage": None, "topic": None, "competency": None,
            "detail": "Genuine assessment responses saved. Automatic scores are unverified until teacher review."})
    for sub, assessment in legacy:
        if sub.id in linked_submissions:
            continue
        simulated = sub.id in simulated_ids
        timeline.append({"kind": "simulated" if simulated else "legacy_uncertain", "date": timestamp(sub.created_at), "title": assessment.title,
            "subject_id": assessment.subject_id, "stage": None, "topic": None, "competency": None,
            "detail": "Simulated batch grading record; excluded from scored trends." if simulated else "Historical assessment record; provenance unverified, excluded from scored trends."})
    homework = list((await db.scalars(select(HomeworkSubmissionRecord).where(
        HomeworkSubmissionRecord.student_id == student_id))).all())
    for sub in homework:
        timeline.append({"kind": "submitted", "date": timestamp(sub.updated_at), "title": "Differentiated homework",
            "stage": None, "topic": None, "subject_id": None, "competency": None,
            "detail": f"{sub.status}; no verified learning score is available."})
    grouped = defaultdict(list)
    for e, at, a in await evidence_rows(db, student_id):
        if eligible(e, at) and a.snapshot.get("topic_id"):
            s = a.snapshot
            grouped[(s["subject_id"], s["topic_id"], e.competency, e.scoring_basis)].append((e, a))
    trends = []
    for (subject, topic, competency, basis), rows in grouped.items():
        # Multiple observations from one attempt are one point, not repeated progress.
        points = {}
        for e, a in rows:
            p = points.setdefault(e.attempt_id, {"date": timestamp(e.recorded_at), "score": 0, "maximum": 0, "activity_id": a.activity_id})
            p["score"] += e.score
            p["maximum"] += e.maximum
        ordered = sorted(points.values(), key=lambda p: p["date"])
        percentages = [{"date": p["date"], "score_pct": round(100*p["score"]/p["maximum"], 1)} for p in ordered]
        trends.append({"subject_id": subject, "topic_id": topic, "topic": rows[0][1].snapshot["topic_title"], "competency": competency,
            "scoring_basis": basis, "points": percentages,
            "change": round(percentages[-1]["score_pct"]-percentages[0]["score_pct"], 1) if len(percentages) >= 2 else None})
    assessment_observations = await assessment_evidence(db, student_id)
    for observation in assessment_observations:
        timeline.append({"kind": "assessment_teacher_review", "date": observation["recorded_at"],
            "title": observation["assessment_title"], "subject_id": observation["subject_id"],
            "stage": None, "topic": observation["topic"], "competency": observation["competency"],
            "detail": f"Teacher-reviewed assessment question: {observation['score']}/{observation['maximum']}. " +
                ("Topic unmapped; no topic was inferred." if observation["topic_id"] is None else "Teacher-verified topic mapping.")})
    return {"student_id": student_id, "timeline": sorted(timeline, key=lambda x: x["date"], reverse=True),
        "panchapadi_assessments": await assessment_stage_views(db, student_id),
        "assessment_observations": assessment_observations,
        "trends": trends, "participation": len(attempts), "completed_assignments": len({a.assignment_id for a in attempts if a.completed}),
        "verified_observations": sum(len(v) for v in grouped.values()),
        "stages": {s: len({a.assignment_id for a in attempts if a.completed and by_id[a.assignment_id].snapshot["stage"] == s})
                   for s in ("Adheeti", "Bodh", "Abhyas", "Prayog", "Prasar")}}
