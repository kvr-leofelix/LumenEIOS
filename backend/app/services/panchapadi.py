"""Assessment-stage evidence. No activity writes and no competency-to-stage lookup."""
import copy
import asyncio
import hashlib
import json
import logging
import math
import re
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update, func
from backend.app.db.session import AsyncSessionLocal
from backend.app.models.entities import Assessment, Student, Subject, utc_now
from backend.app.modules.learnsphere.assessment_models import AssessmentResultRecord
from backend.app.schemas.panchapadi import STAGES, StageClassification

logger = logging.getLogger(__name__)
GUIDANCE_RETRY_DELAYS = (5, 20)
GUIDANCE_RECOVERY_INTERVAL = 30
# Automatic background attempts per review revision. Beyond this the recovery sweep stops (a model that keeps
# failing would otherwise occupy the GPU and database indefinitely); "Refresh assessment guidance" still works.
GUIDANCE_MAX_AUTOMATIC_ATTEMPTS = 6
EVIDENCE_NEEDED = {
    "Adheeti": "Add an explicit prerequisite/readiness question before the new learning task.",
    "Bodh": "Ask for a conceptual explanation or a relationship and assess the response.",
    "Abhyas": "Assess at least two questions requiring performance of a learned procedure.",
    "Prayog": "Assess an unfamiliar or real-life application problem.",
    "Prasar": "Assess independent extension or a new connection beyond routine application.",
}


def validate_mapping(mapping, questions):
    validated = StageClassification(questions=mapping)
    positions = [q.position for q in validated.questions]
    if len(set(positions)) != len(positions) or set(positions) != {q["position"] for q in questions}:
        raise ValueError("Stage classification must cover each actual question exactly once.")
    return [q.model_dump() for q in validated.questions]


def calculate_stages(questions, outcomes, mapping, verified=False):
    mapping = validate_mapping(mapping, questions)
    by_position = {o["position"]: o for o in outcomes}
    question_by_position = {q["position"]: q for q in questions}
    stages = []
    for stage in STAGES:
        contributions = []
        for item in mapping:
            demand = next((m for m in item["mappings"] if m["stage"] == stage), None)
            if not demand:
                continue
            q = question_by_position[item["position"]]
            outcome = by_position.get(item["position"], {})
            score, maximum = outcome.get("score"), q["marks"]
            exclusion = None
            # Explicitly confirming an Adheeti mapping is the teacher's readiness
            # attestation. Older reviews also stored a default-false checkbox;
            # it must not negate that signed mapping. AI still needs the flag.
            if stage == "Adheeti" and not (demand["prerequisite_test"] or verified):
                exclusion = "No explicit prerequisite/readiness test was confirmed."
            elif stage == "Abhyas" and not demand["procedural_practice"]:
                exclusion = "No procedural practice demand was confirmed."
            elif stage == "Prasar" and not demand["independent_extension"]:
                exclusion = "Routine application is not independent extension."
            elif (type(score) not in (int, float) or not math.isfinite(score)
                  or maximum <= 0 or not 0 <= score <= maximum or outcome.get("maximum") != maximum):
                exclusion = "Actual scored marks are unavailable or inconsistent."
            contributions.append({"position": q["position"], "question_id": q.get("id"),
                "reasoning": demand["reasoning"], "score": score if type(score) in (int, float) and math.isfinite(score) else None,
                "maximum": maximum, "eligible": exclusion is None, "exclusion_reason": exclusion})
        eligible = [c for c in contributions if c["eligible"]]
        minimum = 2 if stage == "Abhyas" else 1
        enough = len(eligible) >= minimum
        earned = sum(c["score"] for c in eligible) if eligible else None
        maximum = sum(c["maximum"] for c in eligible) if eligible else None
        explanation = (f"{len(eligible)} scored question(s); at least {minimum} relevant scored question(s) required. "
                       "Scores describe this assessment's evidence, not overall mastery or long-term improvement.")
        if stage == "Abhyas":
            explanation += " One correct response does not establish consistent practice."
        if not enough:
            explanation += " Additional evidence needed: " + EVIDENCE_NEEDED[stage]
        stages.append({"stage": stage, "score_pct": round(100 * earned / maximum, 2) if enough else None,
            "earned_marks": earned, "maximum_marks": maximum, "evidence_count": len(eligible),
            "status": "verified" if enough and verified else "provisional" if enough else "Insufficient evidence",
            "explanation": explanation, "teacher_verified": verified, "contributions": contributions})
    return stages


def empty_mapping(questions):
    return [{"position": q["position"], "mappings": []} for q in questions]


def provisional_view(result):
    attempts = (result.panchapadi_json or {}).get("attempts", [])
    if attempts:
        current = attempts[-1]
        mapping = current_mapping(result)
        output = {k: current[k] for k in ("status", "attempt_id", "date", "error") if k in current}
        output.update(mapping=mapping,stages=calculate_stages(result.questions_json,current_outcomes(result),mapping),teacher_verified=False)
        return output
    return {"status": "pending", "mapping": [], "teacher_verified": False,
        "stages": calculate_stages(result.questions_json, result.automatic_json, empty_mapping(result.questions_json))}


def automatic_outcomes(result):
    attempts = (result.panchapadi_json or {}).get("attempts", [])
    return next((a["outcomes"] for a in reversed(attempts) if "outcomes" in a), result.automatic_json)


def current_outcomes(result):
    return result.reviews_json[-1]["outcomes"] if result.reviews_json else automatic_outcomes(result)


def current_mapping(result):
    review=result.reviews_json[-1] if result.reviews_json else {}
    if review.get("panchapadi"):
        return validate_mapping(review["panchapadi"]["mapping"],result.questions_json)
    for attempt in reversed((result.panchapadi_json or {}).get("attempts",[])):
        try:
            return validate_mapping(attempt.get("mapping",[]),result.questions_json)
        except ValueError:
            continue
    return empty_mapping(result.questions_json)


def reviewed_stage_view(result):
    """Recalculate a read projection; never replace an immutable review snapshot."""
    review=result.reviews_json[-1] if result.reviews_json else {}
    if not review.get("panchapadi"):
        return None
    evaluation=copy.deepcopy(review["panchapadi"])
    evaluation["stages"]=calculate_stages(result.questions_json,review["outcomes"],evaluation["mapping"],verified=True)
    return evaluation


def saved_question_guidance(result, outcomes=None, mapping=None, competencies=None):
    """Reuse only identical frozen responses, evaluated marks and stage demands.

    A revision ID alone is not an evidence change. All attempts belong to this
    same immutable result/question/answer snapshot. Changed outcomes or stage
    mappings invalidate the affected question without changing old guidance.
    """
    outcomes=current_outcomes(result) if outcomes is None else outcomes
    mapping=current_mapping(result) if mapping is None else mapping
    expected={o["position"]:o for o in outcomes}
    def stages(items,confirmed=False):
        def demand(s):
            if s["stage"]=="Adheeti":return (s["stage"],bool(s.get("prerequisite_test") or confirmed))
            if s["stage"]=="Abhyas":return (s["stage"],bool(s.get("procedural_practice")))
            if s["stage"]=="Prasar":return (s["stage"],bool(s.get("independent_extension")))
            return (s["stage"],True)
        return {m["position"]:sorted(demand(s) for s in m["mappings"]) for m in items}
    latest=result.reviews_json[-1] if result.reviews_json else {}
    demands=stages(mapping,bool(latest.get("panchapadi")))
    found={}
    from backend.app.modules.learnsphere.automation import current_competencies
    labels = {m["position"]:m["label"] for m in (competencies if competencies is not None else current_competencies(result))}
    original_labels = {q["position"]:q.get("competency") for q in result.questions_json}
    for attempt in reversed((result.panchapadi_json or {}).get("attempts",[])):
        from backend.app.modules.learnsphere.automation import review_revision
        if attempt.get("competency_review_revision_id") != review_revision(result):
            continue
        prior={o["position"]:o for o in attempt.get("outcomes",[])}
        reviewed=next((r for r in result.reviews_json if r["revision_id"]==attempt.get("review_revision_id")),{})
        old_demands=stages(attempt.get("mapping",[]),bool(reviewed.get("panchapadi")))
        for advice in attempt.get("question_guidance",[]):
            position=advice["position"]
            if position in found or position not in prior or position not in expected:
                continue
            if labels.get(position) is not None and advice.get("competency", original_labels.get(position)) != labels[position]:
                continue
            if any(prior[position].get(k)!=expected[position].get(k) for k in ("score","maximum","correct","competency","feedback")):
                continue
            if old_demands.get(position)!=demands.get(position):
                continue
            found[position]=copy.deepcopy(advice)
    return found


def guidance_missing(result):
    from backend.app.modules.learnsphere.automation import current_competencies
    return (set(saved_question_guidance(result))!={q["position"] for q in result.questions_json}
        or any(m["status"] == "pending" for m in current_competencies(result)))


def drafts_target_gaps(drafts, outcomes):
    if len(drafts)!=3 or {d.get("kind") for d in drafts}!={"support","teach_back","mission"}:
        return False
    gaps = {o["position"] for o in outcomes if o.get("score") is not None and o["score"] < o["maximum"]}
    return not gaps or all(set(d.get("positions", [])) & gaps for d in drafts)


def redact_educational(value, student_name):
    """Account identifiers never enter prompts; redact known name/contact text too."""
    if isinstance(value, dict):
        return {k:redact_educational(v, student_name) for k,v in value.items()}
    if isinstance(value, list):
        return [redact_educational(v, student_name) for v in value]
    if not isinstance(value, str):
        return value
    if student_name:
        value = re.sub(re.escape(student_name), "[student]", value, flags=re.IGNORECASE)
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", value)
    return re.sub(r"(?<!\w)(?:\+?\d[\d ()-]{8,}\d)(?!\w)", "[contact]", value)


async def _cas(db, record_id, version, payload):
    metadata = await db.scalar(select(AssessmentResultRecord.panchapadi_json).where(
        AssessmentResultRecord.id == record_id, func.coalesce(AssessmentResultRecord.panchapadi_version, 0) == version))
    payload = {**copy.deepcopy(metadata or {}), **payload}
    result = await db.execute(update(AssessmentResultRecord).where(AssessmentResultRecord.id == record_id,
        func.coalesce(AssessmentResultRecord.panchapadi_version, 0) == version)
        .values(panchapadi_json=payload, panchapadi_version=version + 1).execution_options(synchronize_session=False))
    if result.rowcount == 1:
        await db.commit()
        return True
    await db.rollback()
    return False


async def _checkpoint(record_id, attempt_id, patch):
    async with AsyncSessionLocal() as db:
        record=await db.get(AssessmentResultRecord,record_id)
        if not record:return False
        payload=copy.deepcopy(record.panchapadi_json or {})
        attempts=payload.get("attempts",[])
        if not attempts or attempts[-1]["attempt_id"]!=attempt_id:return False
        revision=record.reviews_json[-1]["revision_id"] if record.reviews_json else None
        if attempts[-1].get("review_revision_id")!=revision:return False
        from backend.app.modules.learnsphere.automation import review_revision
        if attempts[-1].get("competency_review_revision_id") != review_revision(record):return False
        attempts[-1].update(copy.deepcopy(patch),heartbeat_at=utc_now().isoformat())
        return await _cas(db,record_id,record.panchapadi_version or 0,payload)


def _retry_due(record):
    if not guidance_missing(record):return False
    attempts=(record.panchapadi_json or {}).get("attempts",[])
    if not attempts:return True
    latest=attempts[-1]
    revision=record.reviews_json[-1]["revision_id"] if record.reviews_json else None
    from backend.app.modules.learnsphere.automation import review_revision
    competency_revision = review_revision(record)
    if latest.get("review_revision_id")!=revision or latest.get("competency_review_revision_id") != competency_revision:return True
    # The cap applies to finished attempts; an expired "running" lease (a process stopped mid-job) is always recovered.
    if latest["status"]!="running" and sum(1 for a in attempts if a.get("review_revision_id")==revision and a.get("competency_review_revision_id") == competency_revision)>=GUIDANCE_MAX_AUTOMATIC_ATTEMPTS:return False
    stamp=datetime.fromisoformat(latest.get("heartbeat_at",latest["date"]))
    if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
    delay=1800 if latest["status"]=="running" else min(900,30*2**min(len(attempts)-1,5))
    return stamp<=utc_now()-timedelta(seconds=delay)


async def evaluate_with_guidance_retry(record_id, refresh_guidance=False):
    """Existing background hook, with bounded transient retries and saved progress."""
    for number in range(len(GUIDANCE_RETRY_DELAYS)+1):
        try:
            await evaluate_saved_result(record_id,refresh_guidance if number==0 else False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Assessment guidance retry deferred (%s)",type(exc).__name__)
            return  # The recovery sweep will pick up an expired running lease.
        async with AsyncSessionLocal() as db:
            record=await db.get(AssessmentResultRecord,record_id)
            if not record or not guidance_missing(record):return
            attempts=(record.panchapadi_json or {}).get("attempts",[])
            if attempts and attempts[-1]["status"]=="running":return
        if number<len(GUIDANCE_RETRY_DELAYS):
            await asyncio.sleep(GUIDANCE_RETRY_DELAYS[number])


async def recover_missing_guidance_once():
    """Backfill only genuine saved results; never launch inference from a GET."""
    async with AsyncSessionLocal() as db:
        rows=(await db.scalars(select(AssessmentResultRecord).join(Assessment,
            Assessment.id==AssessmentResultRecord.assessment_id).join(Student,
            Student.id==AssessmentResultRecord.student_id).where(
                Assessment.school_id==AssessmentResultRecord.school_id,
                Assessment.class_id==AssessmentResultRecord.class_id,
                Assessment.subject_id==AssessmentResultRecord.subject_id,
                Student.school_id==AssessmentResultRecord.school_id)
            .order_by(AssessmentResultRecord.submitted_at,AssessmentResultRecord.id))).all()
        ids=[]
        for record in rows:
            try:
                if _retry_due(record):ids.append(record.id)
            except (ValueError,KeyError,TypeError):
                logger.warning("Malformed historical guidance metadata skipped; original result retained.")
    for record_id in ids:
        await evaluate_with_guidance_retry(record_id)
    return len(ids)


async def run_guidance_recovery():
    while True:
        try:
            await recover_missing_guidance_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Guidance recovery deferred (%s)",type(exc).__name__)
        await asyncio.sleep(GUIDANCE_RECOVERY_INTERVAL)


async def evaluate_saved_result(record_id, refresh_guidance=False):
    """Post-response worker: responses are committed first; no transaction spans inference."""
    from backend.app.services.llm_service import qwen_question_studio
    from backend.app.modules.learnsphere.automation import current_competencies, classify_competencies, review_revision
    async with AsyncSessionLocal() as db:
        record = await db.get(AssessmentResultRecord, record_id)
        if not record:
            return
        questions, answers = copy.deepcopy(record.questions_json), copy.deepcopy(record.answers_json)
        review = copy.deepcopy(record.reviews_json[-1]) if record.reviews_json else None
        outcomes = copy.deepcopy(current_outcomes(record))
        student = await db.get(Student, record.student_id)
        subject = await db.get(Subject, record.subject_id)
        from backend.app.modules.learnsphere.models import LearningTopic
        verified_topics = []
        for topic_id in {o.get("topic_id") for o in outcomes if o.get("topic_id")}:
            topic = await db.get(LearningTopic, topic_id)
            if topic and (topic.school_id,topic.class_id,topic.subject_id)==(record.school_id,record.class_id,record.subject_id):
                verified_topics.append(topic.title)
        safe_questions = redact_educational([{k:q.get(k) for k in ("position","text","type","options","marks","correct_answer","marking_rubric","competency","bloom_level","learning_objective","topic")} for q in questions], student.name if student else "")
        safe_answers = redact_educational(answers, student.name if student else "")
        base_outcomes=review["outcomes"] if review else record.automatic_json
        competencies = current_competencies(record)
        competency_revision = review_revision(record)
        teacher_mappings = {m["position"]: copy.deepcopy(m) for m in competencies if m["status"].startswith("teacher_")}
        fingerprint = hashlib.sha256(json.dumps([3, questions, answers, base_outcomes, review, competency_revision], sort_keys=True).encode()).hexdigest()
        attempts = copy.deepcopy((record.panchapadi_json or {}).get("attempts", []))
        reusable = None
        if attempts:
            current = attempts[-1]
            if not refresh_guidance and current.get("fingerprint") == fingerprint and current["status"] == "complete" and current.get("guidance_status") == "complete" and len(current.get("question_guidance",[]))==len(questions) and current.get("automatic_assignments") and not current.get("evaluation_warnings") and drafts_target_gaps(current.get("learning_drafts", []), current.get("outcomes", outcomes)):
                return
            if current.get("fingerprint") == fingerprint and current["status"] == "running" and datetime.fromisoformat(current.get("heartbeat_at",current["date"])) > utc_now() - timedelta(minutes=30):
                return
            if current.get("fingerprint") == fingerprint and current["status"] == "complete":
                reusable = copy.deepcopy(current)
                outcomes = copy.deepcopy(current.get("outcomes", outcomes))
        attempt_id = uuid.uuid4().hex
        current = {"attempt_id": attempt_id, "fingerprint": fingerprint, "date": utc_now().isoformat(),
            "competency_review_revision_id": competency_revision, "competency_mappings": competencies,
            "heartbeat_at":utc_now().isoformat(),
            "review_revision_id":review["revision_id"] if review else None,
            "status": "running", "mapping": reusable["mapping"] if reusable else [],
            "stages": calculate_stages(questions, outcomes, reusable["mapping"] if reusable else empty_mapping(questions))}
        attempts.append(current)
        if not await _cas(db, record_id, record.panchapadi_version or 0, {"attempts": attempts}):
            return
    errors = []
    if any(m["status"] == "pending" for m in competencies) or (refresh_guidance and len(teacher_mappings) < len(questions)):
        try:
            competencies = await classify_competencies(safe_questions, subject.name if subject else None, verified_topics)
        except Exception as exc:
            logger.warning("Competency analysis unavailable (%s)", type(exc).__name__)
            errors.append("Automatic competency mapping is unavailable; unmapped questions need teacher review.")
    from backend.app.modules.learnsphere.automation import question_fingerprint
    original_questions = {q["position"]: q for q in questions}
    for item in competencies:
        item["question_fingerprint"] = question_fingerprint(original_questions[item["position"]])
        item["question_id"] = original_questions[item["position"]].get("id")
    competencies = [teacher_mappings.get(m["position"], m) for m in competencies]
    effective = {m["position"]: m["label"] for m in competencies}
    for question in safe_questions:
        question["competency"] = effective.get(question["position"]) or "unmapped"
    if not await _checkpoint(record_id, attempt_id, {"competency_mappings": competencies}):return
    if not review:
        for question, safe_question in zip(questions, safe_questions):
            if question["type"] == "mcq":
                continue
            outcome = next(o for o in outcomes if o["position"] == question["position"])
            if outcome.get("provenance") == "ai_written_unverified" and outcome.get("score") is not None:
                continue
            answer = next(a for a in safe_answers if a["position"] == question["position"])
            if not question.get("marking_rubric") or not question.get("correct_answer"):
                outcome["feedback"] = "A question-specific expected answer and rubric are needed for automatic written marking."
                continue
            try:
                mark = await qwen_question_studio.mark_written_answer(safe_question, answer.get("answer_text"))
                outcome.update(score=mark.score, correct=mark.correct, feedback=mark.feedback,
                    explanation=mark.explanation, provenance="ai_written_unverified")
                outcome["concept_evidence"] = {"demonstrated":mark.demonstrated_concepts,
                    "partial":mark.partial_concepts, "missing":mark.missing_concepts,
                    "status":"provisional", "reason":mark.explanation}
            except Exception as exc:
                logger.warning("Written evaluation unavailable (%s)", type(exc).__name__)
                errors.append("Written marking unavailable for Q"+str(question["position"]+1)+"; teacher review is available.")
    try:
        safe_outcomes = [{k:o.get(k) for k in ("position","score","maximum","correct","provenance")} for o in outcomes]
        if review and review.get("panchapadi"):
            mapping=validate_mapping(review["panchapadi"]["mapping"],questions)
        elif reusable:
            mapping = validate_mapping(reusable["mapping"], questions)
        else:
            classification = await qwen_question_studio.classify_panchapadi(safe_questions, safe_answers, safe_outcomes)
            mapping = validate_mapping(classification.model_dump()["questions"], questions)
        completion = {"status": "complete", "mapping": mapping, "stages": calculate_stages(questions, outcomes, mapping)}
    except Exception as exc:
        # Keep submitted work and confirmed reviews intact even if inference is unavailable.
        logger.warning("Panchapadi evaluation did not complete (%s)", type(exc).__name__)
        completion = {"status": "failed", "error": "Automatic stage evaluation unavailable or invalid. Your answers are saved; retry or ask the teacher to map stages.",
            "mapping": [], "stages": calculate_stages(questions, outcomes, empty_mapping(questions))}
    completion["outcomes"] = outcomes
    completion["competency_mappings"] = competencies
    completion["review_revision_id"] = review["revision_id"] if review else None
    if not await _checkpoint(record_id,attempt_id,{**completion,"status":"running"}):return
    question_guidance=[]
    old_guidance={} if refresh_guidance else saved_question_guidance(record,outcomes,completion["mapping"],competencies)
    for question,safe_question in zip(questions,safe_questions):
        position=question["position"]
        outcome=next(o for o in outcomes if o["position"]==position)
        response=next(a for a in safe_answers if a["position"]==position)
        stages=next((m["mappings"] for m in completion["mapping"] if m["position"]==position),[])
        if position in old_guidance:
            question_guidance.append(old_guidance[position])
            if not await _checkpoint(record_id,attempt_id,{"question_guidance":question_guidance}):return
            continue
        try:
            advice=await qwen_question_studio.assessment_question_guidance(safe_question,response,
                {**{k:outcome.get(k) for k in ("score","maximum","correct","provenance")},
                 "competency":effective.get(position),
                 "feedback":redact_educational(outcome.get("feedback"), student.name if student else "")},stages)
            question_guidance.append({"position":position,**advice.model_dump(),"status":"provisional",
                "competency":effective.get(position)})
        except Exception as exc:
            logger.warning("Question guidance unavailable (%s)",type(exc).__name__)
            errors.append("Question-wise guidance is temporarily unavailable for Q"+str(position+1)+"; automatic recovery will retry it.")
        if not await _checkpoint(record_id,attempt_id,{"question_guidance":question_guidance}):return
    completion["question_guidance"]=question_guidance
    try:
        # Prioritise actual incorrect/partial answers, then enrichment; bound context
        # without silently truncating any selected response.
        gaps = [o for o in outcomes if o.get("score") is not None and o["score"] < o["maximum"]]
        selected = sorted(gaps or outcomes, key=lambda o: (o.get("score") is None, (o.get("score") or 0)/o["maximum"], o["position"]))[:3]
        positions = {o["position"] for o in selected}
        evidence = {"subject": subject.name if subject else None, "verified_topics": verified_topics,
                    "required_gap_positions": [o["position"] for o in selected if o.get("score") is not None and o["score"] < o["maximum"]],
                    "questions": [q for q in safe_questions if q["position"] in positions],
                    "answers": [a for a in safe_answers if a["position"] in positions],
                    "outcomes": [{k:o.get(k) for k in ("position","score","maximum","correct","provenance")} for o in selected],
                    "stage_mapping": [m for m in completion["mapping"] if m["position"] in positions],
                    "stages": [{k:s[k] for k in ("stage","score_pct","evidence_count","status")} for s in completion["stages"]]}
        generated = await qwen_question_studio.generate_assessment_learning(evidence)
        drafts = [d.model_dump() for d in generated.drafts]
        if {d["kind"] for d in drafts} != {"support","teach_back","mission"} or any(not set(d["positions"]) <= positions or len(set(d["positions"]))!=len(d["positions"]) for d in drafts):
            raise ValueError("Draft references must use the actual supplied evidence, one draft per kind.")
        if not drafts_target_gaps(drafts, selected):
            raise ValueError("Each personalised draft must address at least one actual gap when gaps were demonstrated.")
        completion["learning_drafts"] = drafts
        completion["guidance_status"] = "complete"
    except Exception as exc:
        logger.warning("Assessment learning drafts unavailable (%s)", type(exc).__name__)
        completion["learning_drafts"] = []
        completion["guidance_status"] = "failed"
        errors.append("Personalised draft generation unavailable; retry or author teacher content.")
    completion["evaluation_warnings"] = errors
    async with AsyncSessionLocal() as db:
        record = await db.get(AssessmentResultRecord, record_id)
        if not record:
            return
        attempts = copy.deepcopy((record.panchapadi_json or {}).get("attempts", []))
        if not attempts or attempts[-1]["attempt_id"] != attempt_id:
            return
        latest_review_id = record.reviews_json[-1]["revision_id"] if record.reviews_json else None
        if latest_review_id != (review["revision_id"] if review else None) or review_revision(record) != competency_revision:
            completion.update(status="superseded", learning_drafts=[])
        elif completion.get("guidance_status")=="complete":
            from backend.app.services.assessment_learning import assign_automatic_learning
            completion["automatic_assignments"]=await assign_automatic_learning(db,record,completion)
            if len(completion["automatic_assignments"])<2:
                completion["evaluation_warnings"].append(
                    "Automatic activities need a reliable competency mapping for their source questions; review the unmapped competencies."
                    if any(m["label"] is None for m in competencies) else
                    "Automatic activity assignment needs a valid current enrollment and authorized class teacher. Saved guidance remains available.")
        attempts[-1].update(completion, date=utc_now().isoformat(),heartbeat_at=utc_now().isoformat())
        await _cas(db, record_id, record.panchapadi_version or 0, {"attempts": attempts})


async def assessment_stage_views(db, student_id):
    from backend.app.services.assessment_results import assessment_evidence
    eligible = {o["result_id"] for o in await assessment_evidence(db, student_id)}
    rows = (await db.execute(select(AssessmentResultRecord, Assessment).join(Assessment,
        Assessment.id == AssessmentResultRecord.assessment_id).where(AssessmentResultRecord.student_id == student_id,
            Assessment.school_id == AssessmentResultRecord.school_id,
            Assessment.class_id == AssessmentResultRecord.class_id,
            Assessment.subject_id == AssessmentResultRecord.subject_id)
        .order_by(AssessmentResultRecord.submitted_at, AssessmentResultRecord.id))).all()
    output = []
    for record, assessment in rows:
        latest = record.reviews_json[-1] if record.reviews_json else None
        verified = reviewed_stage_view(record) if latest and record.id in eligible else None
        evaluation = copy.deepcopy(verified) if verified else provisional_view(record)
        assessed_at = record.submitted_at
        if assessed_at.tzinfo is None:
            assessed_at = assessed_at.replace(tzinfo=timezone.utc)
        output.append({"result_id": record.id, "assessment_id": assessment.id, "assessment_name": assessment.title,
            "subject_id": record.subject_id, "assessed_at": assessed_at.isoformat(), "evaluation": student_evaluation(evaluation),
            "learning_plan": [{k:v for k,v in item.items() if k != "rubric"} for item in (latest or {}).get("learning_plan", []) if item.get("decision")=="approved"]})
    return output


def student_evaluation(evaluation):
    """AI reasoning may quote keys; student progress contains scores and references only."""
    output = copy.deepcopy(evaluation)
    output["mapping"] = []
    for stage in output["stages"]:
        for contribution in stage["contributions"]:
            contribution["reasoning"] = "Evidence from this assessment question for " + stage["stage"] + "."
    return output


async def stage_history(db, student_id, include_provisional=False):
    from backend.app.services.assessment_results import assessment_evidence
    eligible = {o["result_id"] for o in await assessment_evidence(db, student_id)}
    views = await assessment_stage_views(db, student_id)
    graphs = []
    for stage in STAGES:
        points = []
        for view in views:
            if view["result_id"] not in eligible and not include_provisional:
                continue
            evaluation = view["evaluation"]
            score = next(s for s in evaluation["stages"] if s["stage"] == stage)
            verified = evaluation.get("teacher_verified", False)
            points.append({k: view[k] for k in ("result_id", "assessment_id", "assessment_name", "subject_id", "assessed_at")}
                | {"score_pct": score["score_pct"] if verified or include_provisional else None,
                   "earned_marks": score["earned_marks"] if verified or include_provisional else None,
                   "maximum_marks": score["maximum_marks"] if verified or include_provisional else None,
                   "evidence_count": score["evidence_count"] if verified or include_provisional else 0,
                   "status": score["status"] if verified or include_provisional else "Insufficient evidence",
                   "teacher_verified":verified,
                   "explanation": score["explanation"] if verified or include_provisional else "Stage mappings have not been confirmed for the latest assessment review.",
                   "review_revision_id": evaluation.get("review_revision_id") if verified else None})
        graphs.append({"stage": stage, "points": points})
    return {"student_id": student_id, "graphs": graphs}
