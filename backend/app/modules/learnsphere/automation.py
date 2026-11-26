"""LearnSphere-only competency analysis; historical assessment snapshots stay immutable."""
import copy
import hashlib
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

CODES = ("LU", "CU", "AU", "CT")
REVIEW_THRESHOLD = 0.85


class CompetencySuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    position: StrictInt = Field(ge=0)
    label: Literal["LU", "CU", "AU", "CT"] | None
    confidence: float = Field(ge=0, le=1, strict=True)
    reason: str = Field(min_length=1, max_length=2000)


class CompetencyAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    questions: list[CompetencySuggestion] = Field(max_length=100)


class CompetencyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    position: StrictInt = Field(ge=0)
    label: Literal["LU", "CU", "AU", "CT"] | None
    reason: str = Field(min_length=1, max_length=2000)


class CompetencyReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: StrictInt = Field(ge=0)
    request_key: str = Field(min_length=1, max_length=64)
    questions: list[CompetencyDecision] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def distinct(self):
        if len({q.position for q in self.questions}) != len(self.questions):
            raise ValueError("Review each question at most once.")
        return self


def question_fingerprint(question):
    content = {key: question.get(key) for key in
        ("text", "type", "options", "correct_answer", "marking_rubric", "bloom_level", "learning_objective", "topic")}
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def review_revision(result):
    reviews = (result.panchapadi_json or {}).get("competency_reviews", [])
    return reviews[-1]["revision_id"] if reviews else None


def current_competencies(result):
    questions = {q["position"]: q for q in result.questions_json}
    found = {}
    for attempt in reversed((result.panchapadi_json or {}).get("attempts", [])):
        for item in attempt.get("competency_mappings", []):
            position = item["position"]
            if position not in found and position in questions and item.get("question_fingerprint") == question_fingerprint(questions[position]):
                found[position] = copy.deepcopy(item)
    for revision in (result.panchapadi_json or {}).get("competency_reviews", []):
        for item in revision["questions"]:
            position = item["position"]
            if position in questions and item.get("question_fingerprint") == question_fingerprint(questions[position]):
                found[position] = {**copy.deepcopy(item), "confidence": None,
                    "status": "teacher_confirmed" if item["label"] else "teacher_unmapped"}
    return [found.get(position, {"position": position, "label": None, "suggested_label": None,
        "confidence": None, "reason": "Automatic competency analysis is pending; the stored label is not a verified mapping.",
        "status": "pending", "question_fingerprint": question_fingerprint(q)})
        for position, q in questions.items()]


async def classify_competencies(questions, subject, topics):
    from backend.app.services.llm_service import qwen_question_studio, COMPETENCY_DEFINITIONS
    definitions = "\n".join(f"{code}: {COMPETENCY_DEFINITIONS[code]}" for code in CODES)
    instruction = (
        "Analyse the primary LU/CU/AU/CT competency actually required by each question, not the student's success. "
        "Consider wording, learning objective, subject/topic, expected answer, rubric and cognitive action. "
        "Do not copy a previous tag or infer a competency from a Bloom label. "
        "Competencies are NOT Panchapadi stages; never convert stages to competency labels. "
        "Choose exactly one primary competency only when supported; use label=null for ambiguous or insufficient evidence. "
        "Explain the cognitive action without revealing the answer key or a full worked solution. "
        "Confidence is an uncertain model estimate, not teacher verification. Give a short question-specific reason. "
        "Cover every supplied question position exactly once. Do not invent topics, sources, answers or evidence. "
        + definitions
    )
    result = []
    for offset in range(0, len(questions), 4):
        batch = questions[offset:offset + 4]
        expected = {q["position"] for q in batch}
        def validate(parsed):
            if len(parsed.questions) != len(expected) or {q.position for q in parsed.questions} != expected:
                raise ValueError("Competency analysis must cover exactly the actual question positions.")
        content = {"subject": subject, "verified_topics": topics,
            "questions": [{key: q.get(key) for key in
                ("position", "text", "type", "options", "correct_answer", "marking_rubric",
                 "learning_objective", "topic", "bloom_level")} for q in batch]}
        parsed = await qwen_question_studio._assessment_draft(instruction, content, CompetencyAnalysis, validate)
        by_position = {q["position"]: q for q in batch}
        for suggestion in parsed.questions:
            item = suggestion.model_dump()
            item["suggested_label"] = item["label"]
            if item["confidence"] < REVIEW_THRESHOLD:
                item["label"] = None
            item["status"] = "provisional" if item["label"] else "requires_review"
            item["source_references"] = ["project:backend/app/services/llm_service.py:COMPETENCY_DEFINITIONS"]
            item["question_fingerprint"] = question_fingerprint(by_position[item["position"]])
            result.append(item)
    return result


async def review_competencies(db, user, student_id, assessment_id, body):
    from fastapi import HTTPException
    from sqlalchemy import select
    from backend.app.models.entities import utc_now
    from backend.app.modules.learnsphere.assessment_models import AssessmentResultRecord
    from backend.app.services.assessment_results import accessible_result
    from backend.app.modules.learnsphere.access import require_class, require_student
    from backend.app.services.panchapadi import _cas
    import uuid
    await require_student(db, user, student_id)
    record = await db.scalar(select(AssessmentResultRecord).where(
        AssessmentResultRecord.student_id == student_id, AssessmentResultRecord.assessment_id == assessment_id))
    if not record:
        raise HTTPException(404, "Submitted assessment unavailable.")
    record, _, _ = await accessible_result(db, user, record.id)
    await require_class(db, user, record.class_id)
    questions = {q["position"]: q for q in record.questions_json}
    if not {q.position for q in body.questions} <= questions.keys():
        raise HTTPException(422, "Mappings must refer to actual assessment questions.")
    payload = [q.model_dump() for q in body.questions]
    signature = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    revisions = copy.deepcopy((record.panchapadi_json or {}).get("competency_reviews", []))
    previous = next((r for r in revisions if r["request_key"] == body.request_key), None)
    if previous:
        if previous["signature"] != signature:
            raise HTTPException(409, "Request key was already used for a different review.")
        return record
    if len(revisions) != body.expected_version:
        raise HTTPException(409, "Analysis changed. Reload before confirming the competency.")
    new_revision = {"revision_id": uuid.uuid4().hex, "reviewer_id": user.id,
        "date": utc_now().isoformat(), "request_key": body.request_key, "signature": signature,
        "questions": [{**item, "question_id":questions[item["position"]].get("id"),
            "question_fingerprint": question_fingerprint(questions[item["position"]])} for item in payload]}
    for _ in range(2):
        revisions = copy.deepcopy((record.panchapadi_json or {}).get("competency_reviews", []))
        if len(revisions) != body.expected_version:
            raise HTTPException(409, "A teacher mapping changed. Reload before reviewing.")
        if await _cas(db, record.id, record.panchapadi_version or 0, {"competency_reviews": [*revisions, new_revision]}):
            break
        await db.refresh(record)
    else:
        raise HTTPException(409, "Analysis changed. Reload before confirming the competency.")
    await db.refresh(record)
    return record
