"""Real responses to existing assessments, with explicit scoring/review provenance."""
import copy
import hashlib
import json
import uuid
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from backend.app.models.entities import Assessment, AssessmentSubmission, Student, ClassSection, StudentCompetencySnapshot, utc_now
from backend.app.services.competency_update import apply_observation
from backend.app.modules.learnsphere.access import require_class, require_student
from backend.app.modules.learnsphere.models import LearningTopic
from backend.app.modules.learnsphere.assessment_models import AssessmentResultRecord
from backend.app.modules.differentiated_homework.student_access import require_linked_student

CODES = ("LU", "CU", "AU", "CT")


def normalized_questions(assessment):
    questions = copy.deepcopy(assessment.questions_json or [])
    if not questions:
        raise HTTPException(422, "Assessment has no answerable questions.")
    for i, q in enumerate(questions):
        if q.get("competency") not in CODES or type(q.get("marks")) is not int or q["marks"] <= 0:
            raise HTTPException(422, "Assessment question competency or maximum marks need educator correction.")
        q["position"] = i
        q["options"] = q.get("options") or []
        q["correct_answer"] = q.get("correct_answer") or q.get("correctAnswer")
        q["marking_rubric"] = q.get("marking_rubric") or q.get("markingRubric")
    if sum(q["marks"] for q in questions) != assessment.total_marks:
        raise HTTPException(422, "Assessment maximum marks do not match its question snapshots.")
    return questions


def auto_evaluate(questions, answers):
    outcomes = []
    by_position = {a.position: a for a in answers}
    if set(by_position) != set(range(len(questions))):
        raise HTTPException(422, "Submit exactly one response for every question.")
    for q in questions:
        a = by_position[q["position"]]
        score = correct = None
        if q["type"] == "mcq":
            if a.answer_text is not None or a.selected_option_index is None or a.selected_option_index >= len(q["options"]):
                raise HTTPException(422, "Choose a valid option for each MCQ.")
            # Only score against an unambiguous stored key. Never invent an answer key.
            if q["correct_answer"] in q["options"] and q["options"].count(q["correct_answer"]) == 1:
                correct = q["options"][a.selected_option_index] == q["correct_answer"]
                score = q["marks"] if correct else 0
        elif a.selected_option_index is not None or not a.answer_text:
            raise HTTPException(422, "Provide a written response for each descriptive question.")
        outcomes.append({"position": q["position"], "question_id": q.get("id"), "competency": q["competency"],
            "score": score, "maximum": q["marks"], "correct": correct,
            "provenance": "automatic_key_unverified" if score is not None else "awaiting_teacher_review", "topic_id": None,
            "feedback": ("Response matches the stored key; teacher verification is pending." if correct else "Response differs from the stored key; review the concept and reasoning.") if score is not None else None})
    return outcomes


async def commit(db):
    try:
        await db.commit()
    except (IntegrityError, StaleDataError):
        await db.rollback()
        raise HTTPException(409, "Submission changed or was already saved. Reload the saved result before retrying.")


async def accessible_result(db, user, record_id):
    result = await db.get(AssessmentResultRecord, record_id)
    if not result:
        raise HTTPException(404, "Assessment result unavailable.")
    student = await require_student(db, user, result.student_id)
    assessment = await db.get(Assessment, result.assessment_id)
    if not assessment or student.school_id != result.school_id or assessment.school_id != result.school_id or assessment.class_id != result.class_id or assessment.subject_id != result.subject_id:
        raise HTTPException(404, "Assessment result has inconsistent school or subject relationships.")
    return result, assessment, student


def result_out(result, assessment, educator=False):
    from backend.app.services.panchapadi import provisional_view, automatic_outcomes, student_evaluation
    questions = [{k: q.get(k) for k in ("position", "id", "text", "type", "options", "marks", "competency")} for q in result.questions_json]
    if educator:
        for q, original in zip(questions, result.questions_json):
            q.update(correct_answer=original.get("correct_answer"), marking_rubric=original.get("marking_rubric"))
    automatic = automatic_outcomes(result)
    outcomes = result.reviews_json[-1]["outcomes"] if result.reviews_json else automatic
    reviews = copy.deepcopy(result.reviews_json)
    evaluation = provisional_view(result)
    attempts = (result.panchapadi_json or {}).get("attempts", [])
    latest = attempts[-1] if attempts else {}
    if not educator:
        automatic = [{k:v for k,v in o.items() if k not in {"feedback","explanation"}} for o in automatic]
        outcomes = [{k:v for k,v in o.items() if k!="explanation" and (k!="feedback" or result.reviews_json)} for o in outcomes]
        evaluation = student_evaluation(evaluation)
        for revision in reviews:
            for o in revision["outcomes"]:
                o.pop("explanation", None)
            if revision.get("panchapadi"):
                revision["panchapadi"] = student_evaluation(revision["panchapadi"])
            # Teacher drafts/assessment keys must not reach students or parents.
            revision.pop("learning_plan", None)
    complete = all(o["score"] is not None for o in outcomes)
    return {"id": result.id, "assessment_id": result.assessment_id, "assessment_title": assessment.title,
        "student_id": result.student_id, "school_id": result.school_id, "subject_id": result.subject_id, "class_id": result.class_id,
        "submission_id": result.submission_id, "version": result.version,
        "status": "teacher_reviewed" if result.reviews_json else "automatically_evaluated_unverified" if complete else "awaiting_teacher_review",
        "questions": questions, "answers": result.answers_json, "automatic_outcomes": automatic,
        "reviews": reviews, "outcomes": outcomes,
        "marks_obtained": sum(o["score"] for o in outcomes) if complete else None,
        "total_marks": sum(q["marks"] for q in result.questions_json), "panchapadi": evaluation,
        "learning_drafts": latest.get("learning_drafts", []) if educator else [],
        "evaluation_warnings": latest.get("evaluation_warnings", []), "guidance_status": latest.get("guidance_status")}


async def publish(db, result, assessment, student, outcomes, verified):
    """Reuse assessment_submissions. Unknown competency dimensions stay out of evidence."""
    if any(o["score"] is None for o in outcomes):
        return
    marks = sum(o["score"] for o in outcomes)
    maximum = sum(o["maximum"] for o in outcomes)
    scores = {}
    for c in CODES:
        items = [o for o in outcomes if o["competency"] == c]
        if items:
            scores[c] = round(100 * sum(o["score"] for o in items) / sum(o["maximum"] for o in items))
    submission = await db.get(AssessmentSubmission, result.submission_id) if result.submission_id else None
    if submission is None:
        submission = AssessmentSubmission(id=str(uuid.uuid4()), assessment_id=assessment.id, student_id=student.id,
            student_name=student.name, submission_date=utc_now().strftime("%Y-%m-%d"), is_scanned=False)
        db.add(submission)
        result.submission = submission
    submission.marks_obtained, submission.total_marks = marks, maximum
    submission.percentage = round(100 * marks / maximum)
    # Legacy non-null score columns cannot represent an unassessed dimension. They
    # remain compatibility placeholders; the adapter exclusively reads question outcomes.
    for c in CODES:
        setattr(submission, c.lower()+"_score", scores.get(c, 0))
    submission.overall_score = round(sum(scores.values()) / len(scores))
    submission.feedback = result.reviews_json[-1]["feedback"] if verified else "Automatically scored against stored MCQ keys; not teacher verified."
    if verified and len(result.reviews_json) == 1:
        # Like every other graded work, the first teacher-verified result nudges the live parameters
        # (weighted by how much evidence it carries) instead of overwriting them. Later review
        # revisions correct the marks only; the parameters already moved once for this work.
        apply_observation(student, scores, weight=round(0.1 + 0.3 * min(1.0, maximum / 25), 3))
    try:
        # The submission relationship orders parent/child writes for PostgreSQL
        # and SQLite connections that enable foreign-key enforcement.
        await db.flush()
    except (IntegrityError, StaleDataError):
        await db.rollback()
        raise HTTPException(409, "Result changed or was already submitted. Reload before retrying.")


async def submit_answers(db, user, assessment_id, body):
    student = await require_linked_student(db, user)
    assessment = await db.get(Assessment, assessment_id)
    section = await db.get(ClassSection, student.class_id)
    if not assessment or assessment.class_id != student.class_id or assessment.school_id != student.school_id or not section or section.school_id != student.school_id or assessment.subject_id not in (section.subject_ids_json or []):
        raise HTTPException(404, "Assessment unavailable for your class and subject.")
    existing = await db.scalar(select(AssessmentResultRecord).where(AssessmentResultRecord.assessment_id == assessment.id,
        AssessmentResultRecord.student_id == student.id))
    answers = [a.model_dump() for a in sorted(body.answers, key=lambda a: a.position)]
    if existing:
        if existing.request_key != body.request_key or existing.answers_json != answers:
            raise HTTPException(409, "This assessment was already submitted. Its responses are locked.")
        return result_out(existing, assessment)
    if assessment.status != "scheduled":
        raise HTTPException(409, "Assessment is not open for submission.")
    questions = normalized_questions(assessment)
    automatic = auto_evaluate(questions, body.answers)
    prior_results = (await db.scalars(select(AssessmentResultRecord).where(
        AssessmentResultRecord.assessment_id==assessment.id,
        AssessmentResultRecord.school_id==assessment.school_id,
        AssessmentResultRecord.class_id==assessment.class_id,
        AssessmentResultRecord.subject_id==assessment.subject_id))).all()
    for question, outcome in zip(questions, automatic):
        if question["type"] != "mcq" or outcome["score"] is None:
            continue
        for previous in prior_results:
            if not previous.reviews_json:
                continue
            same = next((q for q in previous.questions_json if q["position"]==question["position"]),None)
            if not same or any(same.get(k)!=question.get(k) for k in ("text","options","correct_answer","marks")):
                continue
            reviewed_key = next((o for o in previous.reviews_json[-1]["outcomes"] if o["position"]==question["position"]),{})
            if reviewed_key.get("key_verified"):
                outcome.update(provenance="deterministic_verified_key", key_verified=True,
                    feedback="Automatically marked against a teacher-verified key; this result awaits teacher confirmation.")
                break
    result = AssessmentResultRecord(assessment_id=assessment.id, student_id=student.id, school_id=student.school_id,
        class_id=student.class_id, subject_id=assessment.subject_id, request_key=body.request_key,
        questions_json=questions, answers_json=answers, automatic_json=automatic, reviews_json=[])
    db.add(result)
    await publish(db, result, assessment, student, automatic, verified=False)
    await commit(db)
    return result_out(result, assessment)


async def review_result(db, user, record_id, body):
    result, assessment, student = await accessible_result(db, user, record_id)
    await require_class(db, user, result.class_id)
    if result.version != body.expected_version:
        raise HTTPException(409, "Result changed. Reload before reviewing.")
    by_position = {r.position: r for r in body.questions}
    if len(by_position) != len(body.questions) or set(by_position) != set(range(len(result.questions_json))):
        raise HTTPException(422, "Review each question exactly once.")
    outcomes = []
    for q in result.questions_json:
        reviewed = by_position[q["position"]]
        if reviewed.verify_key and (q["type"]!="mcq" or q.get("correct_answer") not in q["options"] or q["options"].count(q["correct_answer"])!=1):
            raise HTTPException(422, "Only an unambiguous stored MCQ key can be verified.")
        if reviewed.score > q["marks"]:
            raise HTTPException(422, "Question score exceeds its original maximum.")
        if reviewed.topic_id:
            topic = await db.get(LearningTopic, reviewed.topic_id)
            if not topic or topic.class_id != result.class_id or topic.school_id != result.school_id or topic.subject_id != result.subject_id:
                raise HTTPException(422, "Choose a verified topic for the assessment's class and subject, or leave it unmapped.")
        outcomes.append({"position": q["position"], "question_id": q.get("id"), "competency": q["competency"],
            "score": reviewed.score, "maximum": q["marks"], "correct": reviewed.correct,
            "feedback": reviewed.feedback, "topic_id": reviewed.topic_id, "provenance": "teacher_reviewed",
            "explanation": reviewed.explanation, "key_verified": reviewed.verify_key})
    revision_id, date = uuid.uuid4().hex, utc_now().isoformat()
    revision = {"revision_id": revision_id, "reviewer_id": user.id,
        "date": date, "feedback": body.feedback, "outcomes": outcomes}
    if body.learning_plan is not None:
        from backend.app.services.assessment_learning import approve_learning_plan
        revision["learning_plan"] = await approve_learning_plan(db, user, result, body.learning_plan, outcomes)
    if body.confirm_panchapadi:
        from backend.app.services.panchapadi import validate_mapping, calculate_stages
        if body.panchapadi_mappings is None:
            raise HTTPException(422, "Explicit stage mappings are required to confirm Panchapadi evaluations.")
        try:
            mapping = validate_mapping([m.model_dump() for m in body.panchapadi_mappings], result.questions_json)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        revision["panchapadi"] = {"status": "teacher_verified", "date": date,
            "teacher_verified": True, "review_revision_id": revision_id, "mapping": mapping,
            "stages": calculate_stages(result.questions_json, outcomes, mapping, verified=True)}
    result.reviews_json = [*result.reviews_json, revision]
    await publish(db, result, assessment, student, outcomes, verified=True)
    # The teacher-reviewed marks also reach the concept graph (only through the paper's confirmed concept links).
    from backend.app.services.kc_graph_service import record_teacher_confirmed_marks
    await record_teacher_confirmed_marks(
        db, assessment=assessment, student_id=student.id, source_key=f"assessment-result:{result.id}",
        marks={o["position"] + 1: o["score"] for o in outcomes if o["score"] is not None},
        assessed_at=result.submitted_at,
    )
    await commit(db)
    return result_out(result, assessment, educator=True)


async def assessment_evidence(db, student_id):
    """Read current reviewed source observations; no duplicate materialized activity rows."""
    rows = (await db.execute(select(AssessmentResultRecord, Assessment, AssessmentSubmission)
        .join(Assessment, Assessment.id == AssessmentResultRecord.assessment_id)
        .join(AssessmentSubmission, AssessmentSubmission.id == AssessmentResultRecord.submission_id)
        .join(Student, Student.id == AssessmentResultRecord.student_id)
        .where(AssessmentResultRecord.student_id == student_id, AssessmentSubmission.student_id == student_id,
            AssessmentSubmission.assessment_id == Assessment.id, Student.school_id == AssessmentResultRecord.school_id,
            Assessment.school_id == AssessmentResultRecord.school_id, Assessment.class_id == AssessmentResultRecord.class_id,
            Assessment.subject_id == AssessmentResultRecord.subject_id))).all()
    observations = []
    for result, assessment, submission in rows:
        if not result.reviews_json:
            continue
        review = result.reviews_json[-1]
        outcomes = review["outcomes"]
        if sum(o["score"] for o in outcomes) != submission.marks_obtained or sum(o["maximum"] for o in outcomes) != submission.total_marks:
            continue  # A legacy writer changed the total; do not certify stale reviews.
        for o in outcomes:
            if o["provenance"] != "teacher_reviewed" or not 0 <= o["score"] <= o["maximum"] or o["maximum"] <= 0:
                continue
            topic = await db.get(LearningTopic, o["topic_id"]) if o.get("topic_id") else None
            if topic and (topic.school_id != result.school_id or topic.class_id != result.class_id or topic.subject_id != result.subject_id):
                topic = None
            q = result.questions_json[o["position"]]
            observations.append({"id": f"{result.id}:{o['position']}", "result_id": result.id,
                "submission_id": submission.id, "assessment_id": assessment.id, "assessment_title": assessment.title,
                "subject_id": result.subject_id, "topic_id": topic.id if topic else None, "topic": topic.title if topic else None,
                "competency": o["competency"], "score": o["score"], "maximum": o["maximum"], "correct": o["correct"],
                "source": "assessment_teacher_review", "recorded_at": review["date"], "provenance": "teacher_reviewed",
                "scoring_basis": hashlib.sha256(json.dumps(q, sort_keys=True).encode()).hexdigest()})
    return observations
