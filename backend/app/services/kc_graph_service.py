"""Question-to-concept mapping and per-student mastery.

Mastery is recalculated from stored attempts. Overall mastery uses equal weights
across dimensions that have evidence, the same rule as calculate_composite_score
when all four are present. A dimension with no reliable attempt stays empty and
is left out of the average.

Recency half-life is 30 days. LUMENEIOS does not define a concept-level decay,
so this weight is an explicit assumption and lives only in this module.
Status bands are also local to concepts: 75 and above is proficient, 50 to 74
is developing, and below 50 needs improvement.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Iterable, Optional

from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import (
    Assessment,
    AssignmentOcrUpload,
    ClassSection,
    QuestionBankItem,
    Student,
    StudentOcrHistory,
    Subject,
    utc_now,
)
from backend.app.models.knowledge_components import (
    KnowledgeComponent,
    KnowledgeComponentRelationship,
    QuestionBankKcMapping,
    QuestionKcMapping,
    StudentKcAttempt,
    StudentKcMastery,
)
from backend.app.schemas.evaluation import EvaluationResult
from backend.app.services.ai_gateway import AIGatewayError, QwenTextProvider, get_ai_provider
from backend.app.services.evaluation_service import repair_json_latex

logger = logging.getLogger(__name__)

DIMENSIONS = ("LU", "CU", "CT", "AU")
HALF_LIFE_DAYS = 30
PROFICIENT_AT = 75
DEVELOPING_AT = 50


class KcComponentLink(BaseModel):
    id: str
    relevance: float = 1


class KcQuestionLink(BaseModel):
    question_id: str
    components: list[KcComponentLink] = Field(default_factory=list)


class KcMappingResponse(BaseModel):
    questions: list[KcQuestionLink] = Field(default_factory=list)


def identity_key(value: str) -> str:
    return " ".join(value.strip().lower().split())


def question_text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def recency_weight(assessed_at: datetime, now: datetime) -> float:
    age_days = max(0.0, (as_utc(now) - as_utc(assessed_at)).total_seconds() / 86400)
    return 0.5 ** (age_days / HALF_LIFE_DAYS)


def learning_status(overall: Optional[float]) -> str:
    if overall is None:
        return "not_assessed"
    if overall >= PROFICIENT_AT:
        return "proficient"
    if overall >= DEVELOPING_AT:
        return "developing"
    return "needs_improvement"


def mastery_from_attempts(attempts: Iterable, now: Optional[datetime] = None) -> dict:
    """Weighted mastery for one component. `attempts` need score, relevance, competency, assessed_at."""
    moment = now or utc_now()
    buckets: dict[str, list[tuple[float, float]]] = {dimension: [] for dimension in DIMENSIONS}
    for attempt in attempts:
        if attempt.competency not in buckets:
            continue
        weight = max(0.0, float(attempt.relevance)) * recency_weight(attempt.assessed_at, moment)
        if weight <= 0:
            continue
        buckets[attempt.competency].append((float(attempt.score), weight))

    scores: dict[str, Optional[float]] = {}
    for dimension, pairs in buckets.items():
        if not pairs:
            scores[dimension] = None
            continue
        total_weight = sum(weight for _, weight in pairs)
        scores[dimension] = round(sum(score * weight for score, weight in pairs) / total_weight, 1)

    present = [score for score in scores.values() if score is not None]
    overall = round(sum(present) / len(present), 1) if present else None
    return {
        "lu": scores["LU"],
        "cu": scores["CU"],
        "ct": scores["CT"],
        "au": scores["AU"],
        "overall": overall,
        "learning_status": learning_status(overall),
    }


def latest_and_previous(attempts: Iterable) -> tuple[dict, dict]:
    ordered: dict[str, list] = {dimension: [] for dimension in DIMENSIONS}
    for attempt in sorted(attempts, key=lambda item: as_utc(item.assessed_at)):
        if attempt.competency in ordered:
            ordered[attempt.competency].append(float(attempt.score))
    latest = {}
    previous = {}
    for dimension, scores in ordered.items():
        latest[dimension] = scores[-1] if scores else None
        previous[dimension] = scores[-2] if len(scores) > 1 else None
    return latest, previous


def recommendations_for(
    name: str,
    scores: dict,
    prerequisites: list[tuple[str, Optional[float]]],
) -> list[str]:
    """Advice from assessed dimensions only. Unassessed prerequisites are omitted."""
    lu, cu, ct, au = scores.get("lu"), scores.get("cu"), scores.get("ct"), scores.get("au")
    notes: list[str] = []
    if lu is not None and cu is not None and lu < DEVELOPING_AT and cu < DEVELOPING_AT:
        notes.append(f"Strengthen foundational understanding of {name} before taking on new problems.")
    elif (
        lu is not None and cu is not None and ct is not None
        and lu >= PROFICIENT_AT and cu >= PROFICIENT_AT and ct < DEVELOPING_AT
    ):
        notes.append(f"Practice reasoning-based exercises on {name}.")
    elif (
        lu is not None and cu is not None and ct is not None and au is not None
        and lu >= PROFICIENT_AT and cu >= PROFICIENT_AT and ct >= PROFICIENT_AT
        and au < DEVELOPING_AT
    ):
        notes.append(f"Practice applying {name} in new situations.")
    for prerequisite_name, overall in prerequisites:
        if overall is not None and overall < DEVELOPING_AT:
            notes.append(f"Revisit {prerequisite_name} before advancing in {name}.")
    return notes


def question_concept_labels(text: str, concept_names: Iterable[str]) -> list[str]:
    """Concept names that appear as whole phrases in a question. The model is not called."""
    folded = text.casefold()
    labels = []
    names = sorted({name.strip() for name in concept_names if name and name.strip()}, key=len, reverse=True)
    for name in names:
        if len(name) < 3:
            continue
        if _phrase_in(folded, name.casefold()):
            labels.append(name)
    return labels


def _phrase_in(text: str, phrase: str) -> bool:
    start = 0
    while True:
        index = text.find(phrase, start)
        if index < 0:
            return False
        before = text[index - 1] if index else " "
        after_at = index + len(phrase)
        after = text[after_at] if after_at < len(text) else " "
        if not before.isalnum() and not after.isalnum():
            return True
        start = index + 1


def _mean(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


async def class_subject_evidence(db: AsyncSession, *, school_id: str, class_id: str, subject_id: str) -> dict:
    """Assessed concepts for one class and subject, drawn from stored evaluation mastery."""
    section = await db.get(ClassSection, class_id)
    if section is None or section.school_id != school_id:
        raise LookupError("class")
    subject = await db.get(Subject, subject_id)
    if subject is None or subject_id not in (section.subject_ids_json or []):
        raise LookupError("subject")

    roster = set((await db.scalars(select(Student.id).where(
        Student.school_id == school_id,
        Student.class_id == class_id,
    ))).all())
    from_papers = set((await db.scalars(
        select(StudentKcAttempt.student_id)
        .join(Assessment, Assessment.id == StudentKcAttempt.assessment_id)
        .where(
            Assessment.school_id == school_id,
            Assessment.class_id == class_id,
            Assessment.subject_id == subject_id,
        )
    )).all())
    student_ids = roster | from_papers
    students = {
        row.id: row
        for row in (await db.scalars(select(Student).where(Student.id.in_(student_ids)))).all()
    } if student_ids else {}
    components = list((await db.scalars(
        select(KnowledgeComponent).where(KnowledgeComponent.subject_id == subject_id)
    )).all())
    mastery_rows = []
    if student_ids and components:
        mastery_rows = list((await db.scalars(select(StudentKcMastery).where(
            StudentKcMastery.student_id.in_(student_ids),
            StudentKcMastery.kc_id.in_([row.id for row in components]),
            StudentKcMastery.learning_status != "not_assessed",
        ))).all())
    grouped: dict[str, list[StudentKcMastery]] = defaultdict(list)
    for row in mastery_rows:
        grouped[row.kc_id].append(row)

    concepts = []
    for component in components:
        rows = [row for row in grouped.get(component.id, []) if row.student_id in students]
        if not rows:
            continue
        dimension_means = {
            "LU": _mean([row.lu_mastery for row in rows if row.lu_mastery is not None]),
            "CU": _mean([row.cu_mastery for row in rows if row.cu_mastery is not None]),
            "CT": _mean([row.ct_mastery for row in rows if row.ct_mastery is not None]),
            "AU": _mean([row.au_mastery for row in rows if row.au_mastery is not None]),
        }
        present = [(name, score) for name, score in dimension_means.items() if score is not None]
        weakest = min(present, key=lambda item: (item[1], item[0]))[0] if present else None
        overalls = [row.overall_mastery for row in rows if row.overall_mastery is not None]
        assessed_at = [row.last_assessed_at for row in rows if row.last_assessed_at is not None]
        people = []
        for row in sorted(rows, key=lambda item: (item.overall_mastery is None, item.overall_mastery or 0)):
            student = students[row.student_id]
            people.append({
                "student_id": student.id,
                "student_name": student.name,
                "learning_status": row.learning_status,
                "overall_mastery": row.overall_mastery,
                "lu": row.lu_mastery,
                "cu": row.cu_mastery,
                "ct": row.ct_mastery,
                "au": row.au_mastery,
                "last_assessed_at": row.last_assessed_at,
            })
        concepts.append({
            "id": component.id,
            "name": component.name,
            "topic": component.topic,
            "student_count": len(rows),
            "proficient_count": sum(row.learning_status == "proficient" for row in rows),
            "developing_count": sum(row.learning_status == "developing" for row in rows),
            "needs_improvement_count": sum(row.learning_status == "needs_improvement" for row in rows),
            "average_mastery": _mean(overalls),
            "weakest_competency": weakest,
            "last_assessed_at": max(assessed_at) if assessed_at else None,
            "students": people,
        })
    concepts.sort(key=lambda item: (-item["needs_improvement_count"], item["average_mastery"] or 0, item["name"]))
    return {
        "class_id": section.id,
        "class_name": section.name,
        "subject_id": subject.id,
        "subject_name": subject.name,
        "concepts": concepts,
    }


def evaluation_is_reliable(result: EvaluationResult) -> bool:
    summary = result.scoring_summary
    if summary.needs_teacher_review or summary.review_reasons:
        return False
    if not result.question_evaluations:
        return False
    for item in result.question_evaluations:
        if item.flag_for_review or item.competency not in DIMENSIONS:
            return False
        if item.status != "unattempted" and not (item.student_answer_extracted or "").strip():
            return False
        if "[unclear]" in (item.student_answer_extracted or "").lower():
            return False
    return True


def _accepted_links(raw: KcMappingResponse, allowed_ids: set[str]) -> dict[str, list[tuple[str, float]]]:
    accepted: dict[str, list[tuple[str, float]]] = {}
    for question in raw.questions:
        best: dict[str, float] = {}
        for component in question.components:
            relevance = min(1.0, float(component.relevance))
            if component.id not in allowed_ids or relevance <= 0:
                continue
            best[component.id] = max(best.get(component.id, 0.0), relevance)
        accepted[question.question_id] = list(best.items())
    return accepted


def _mapping_prompt(subject_name: str, catalogue: list[KnowledgeComponent], questions: list[dict]) -> tuple[str, str]:
    catalogue_payload = [
        {"id": item.id, "name": item.name, "topic": item.topic, "description": item.description}
        for item in catalogue
    ]
    question_payload = [
        {
            "question_id": question["id"],
            "text": question["text"],
            "competency": question["competency"],
            "expected_answer": question.get("correct_answer") or "",
            "marking_rubric": question.get("marking_rubric") or "",
            "student_answer": question.get("student_answer") or "",
        }
        for question in questions
    ]
    system = (
        "You match exam questions to an existing knowledge-component catalogue. "
        "Return only ids from the catalogue. Do not invent components, ids, or relationships. "
        "A question may match several components. relevance is from 0 to 1. "
        "Use an empty components list when nothing in the catalogue fits. "
        "Return JSON only."
    )
    prompt = (
        f"Subject: {subject_name}\n"
        f"Catalogue:\n{json.dumps(catalogue_payload, ensure_ascii=False)}\n"
        f"Questions:\n{json.dumps(question_payload, ensure_ascii=False)}\n"
        'Return {"questions":[{"question_id":"...","components":[{"id":"...","relevance":1}]}]}'
    )
    return system, prompt


async def _catalogue(db: AsyncSession, subject_id: str) -> list[KnowledgeComponent]:
    rows = await db.execute(
        select(KnowledgeComponent)
        .where(KnowledgeComponent.subject_id == subject_id)
        .order_by(KnowledgeComponent.name, KnowledgeComponent.id)
    )
    return list(rows.scalars().all())


async def _stored_mappings(
    db: AsyncSession, assessment_id: str, question_id: str,
) -> list[QuestionKcMapping]:
    rows = await db.execute(
        select(QuestionKcMapping).where(
            QuestionKcMapping.assessment_id == assessment_id,
            QuestionKcMapping.question_id == question_id,
        )
    )
    return list(rows.scalars().all())


def _link_id(raw: object) -> str:
    if isinstance(raw, dict):
        return str(raw.get("kc_id") or raw.get("id") or "").strip()
    return ""


def _link_relevance(raw: object) -> float:
    if not isinstance(raw, dict):
        return 0.0
    try:
        value = float(raw.get("relevance", 1))
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, value))


def published_links(question: dict, allowed_ids: set[str]) -> Optional[list[tuple[str, float]]]:
    """Teacher-confirmed ids stored on the question. None means the paper did not freeze a mapping."""
    raw = question.get("kc_mappings", None)
    if not isinstance(raw, list):
        return None
    best: dict[str, float] = {}
    for item in raw:
        kc_id = _link_id(item)
        relevance = _link_relevance(item)
        if kc_id not in allowed_ids or relevance <= 0:
            continue
        best[kc_id] = max(best.get(kc_id, 0.0), relevance)
    return list(best.items())


async def _write_mappings(
    db: AsyncSession,
    *,
    assessment_id: str,
    question_id: str,
    text: str,
    links: list[tuple[str, float]],
) -> None:
    await db.execute(
        delete(QuestionKcMapping).where(
            QuestionKcMapping.assessment_id == assessment_id,
            QuestionKcMapping.question_id == question_id,
        )
    )
    digest = question_text_hash(text)
    for kc_id, relevance in links:
        db.add(QuestionKcMapping(
            assessment_id=assessment_id,
            question_id=question_id,
            question_text_hash=digest,
            kc_id=kc_id,
            relevance=relevance,
        ))


async def ensure_question_mappings(
    db: AsyncSession,
    *,
    assessment_id: str,
    subject_id: str,
    subject_name: str,
    questions: list[dict],
    ai_provider: str = "gemini",
) -> dict[str, list[tuple[str, float]]]:
    """Use a confirmed mapping when the paper has one. Otherwise reuse or ask the model for catalogue ids only."""
    catalogue = await _catalogue(db, subject_id)
    allowed = {item.id: item for item in catalogue}
    resolved: dict[str, list[tuple[str, float]]] = {}
    pending: list[dict] = []

    for question in questions:
        frozen = published_links(question, set(allowed))
        if frozen is not None:
            await _write_mappings(
                db,
                assessment_id=assessment_id,
                question_id=question["id"],
                text=question["text"],
                links=frozen,
            )
            resolved[question["id"]] = frozen
            continue
        digest = question_text_hash(question["text"])
        stored = await _stored_mappings(db, assessment_id, question["id"])
        if stored and all(row.question_text_hash == digest for row in stored):
            resolved[question["id"]] = [(row.kc_id, float(row.relevance)) for row in stored if row.kc_id in allowed]
            continue
        pending.append(question)
        resolved[question["id"]] = []

    if not pending or not allowed:
        await db.flush()
        return resolved

    system, prompt = _mapping_prompt(subject_name, catalogue, pending)
    text_provider = QwenTextProvider() if ai_provider == "qwen" else get_ai_provider()
    raw = await text_provider.generate_json(system=system, prompt=prompt, schema=KcMappingResponse)
    parsed = KcMappingResponse.model_validate(json.loads(repair_json_latex(raw)))
    accepted = _accepted_links(parsed, set(allowed))
    for question in pending:
        links = accepted.get(question["id"], [])
        await _write_mappings(
            db,
            assessment_id=assessment_id,
            question_id=question["id"],
            text=question["text"],
            links=links,
        )
        resolved[question["id"]] = links
    await db.flush()
    return resolved


async def freeze_published_mappings(db: AsyncSession, assessment: Assessment) -> None:
    """Copy teacher-confirmed ids onto the paper using the same question numbers OCR will use."""
    subject = await db.get(Subject, assessment.subject_id)
    if subject is None:
        return
    allowed = {item.id for item in await _catalogue(db, subject.id)}
    prepared: list[dict] = []
    unknown: list[str] = []
    for index, question in enumerate(assessment.questions_json or [], start=1):
        if not isinstance(question, dict) or not isinstance(question.get("kc_mappings"), list):
            continue
        for item in question["kc_mappings"]:
            kc_id = _link_id(item)
            if kc_id and kc_id not in allowed:
                unknown.append(kc_id)
        prepared.append({
            "id": str(index),
            "text": question.get("text") or "",
            "kc_mappings": question["kc_mappings"],
        })
    if unknown:
        raise ValueError("unknown-kc")
    if not prepared:
        return
    await ensure_question_mappings(
        db,
        assessment_id=assessment.id,
        subject_id=subject.id,
        subject_name=subject.name,
        questions=prepared,
    )


async def remember_bank_mappings(
    db: AsyncSession, *, school_id: str, questions: list[dict],
) -> None:
    """Keep the same confirmed ids on the bank item when that item is what was published."""
    for question in questions:
        if not isinstance(question, dict) or not isinstance(question.get("kc_mappings"), list):
            continue
        item = await db.get(QuestionBankItem, question.get("id"))
        if item is None or item.school_id != school_id or item.subject_id is None:
            continue
        allowed = {row.id for row in await _catalogue(db, item.subject_id)}
        links = published_links(question, allowed) or []
        await db.execute(
            delete(QuestionBankKcMapping).where(QuestionBankKcMapping.question_bank_item_id == item.id)
        )
        for kc_id, relevance in links:
            db.add(QuestionBankKcMapping(
                question_bank_item_id=item.id, kc_id=kc_id, relevance=relevance,
            ))
    await db.flush()


async def suggest_question_mappings(
    db: AsyncSession,
    *,
    subject_id: str,
    subject_name: str,
    questions: list[dict],
    ai_provider: str = "gemini",
) -> dict[str, list[tuple[str, float]]]:
    """Suggest catalogue ids. Nothing is stored until the teacher publishes the paper."""
    catalogue = await _catalogue(db, subject_id)
    allowed = {item.id for item in catalogue}
    if not questions or not allowed:
        return {question["id"]: [] for question in questions}
    system, prompt = _mapping_prompt(subject_name, catalogue, questions)
    text_provider = QwenTextProvider() if ai_provider == "qwen" else get_ai_provider()
    raw = await text_provider.generate_json(system=system, prompt=prompt, schema=KcMappingResponse)
    parsed = KcMappingResponse.model_validate(json.loads(repair_json_latex(raw)))
    accepted = _accepted_links(parsed, allowed)
    return {question["id"]: accepted.get(question["id"], []) for question in questions}


async def find_student_upload(
    db: AsyncSession,
    *,
    school_id: str,
    class_id: str,
    assessment_id: str,
    extracted_text: str,
    history_id: Optional[str],
) -> Optional[StudentOcrHistory]:
    statement = (
        select(StudentOcrHistory)
        .join(Student, Student.id == StudentOcrHistory.student_id)
        .join(AssignmentOcrUpload, AssignmentOcrUpload.history_id == StudentOcrHistory.id)
        .where(
            AssignmentOcrUpload.assessment_id == assessment_id,
            Student.school_id == school_id,
            Student.class_id == class_id,
        )
        .order_by(StudentOcrHistory.created_at.desc(), StudentOcrHistory.id.desc())
    )
    if history_id:
        statement = statement.where(StudentOcrHistory.id == history_id)
    else:
        statement = statement.where(StudentOcrHistory.extracted_text == extracted_text)
    return (await db.execute(statement)).scalars().first()


def _is_correct(status: str, awarded: float, maximum: float) -> bool:
    return status != "unattempted" and maximum > 0 and (awarded / maximum) >= 0.5


async def _recompute_mastery(db: AsyncSession, student_id: str, kc_ids: set[str]) -> None:
    if not kc_ids:
        return
    rows = await db.execute(
        select(StudentKcAttempt).where(
            StudentKcAttempt.student_id == student_id,
            StudentKcAttempt.kc_id.in_(kc_ids),
        )
    )
    grouped: dict[str, list[StudentKcAttempt]] = defaultdict(list)
    for attempt in rows.scalars().all():
        grouped[attempt.kc_id].append(attempt)

    existing_rows = await db.execute(
        select(StudentKcMastery).where(
            StudentKcMastery.student_id == student_id,
            StudentKcMastery.kc_id.in_(kc_ids),
        )
    )
    existing = {row.kc_id: row for row in existing_rows.scalars().all()}
    now = utc_now()

    for kc_id in kc_ids:
        attempts = grouped.get(kc_id, [])
        current = existing.get(kc_id)
        if not attempts:
            if current is not None:
                await db.delete(current)
            continue
        summary = mastery_from_attempts(attempts, now)
        distinct = {(attempt.source_key, attempt.question_id) for attempt in attempts}
        correct = {
            (attempt.source_key, attempt.question_id)
            for attempt in attempts
            if attempt.correct
        }
        if current is None:
            current = StudentKcMastery(student_id=student_id, kc_id=kc_id)
            db.add(current)
        current.lu_mastery = summary["lu"]
        current.cu_mastery = summary["cu"]
        current.ct_mastery = summary["ct"]
        current.au_mastery = summary["au"]
        current.overall_mastery = summary["overall"]
        current.learning_status = summary["learning_status"]
        current.attempt_count = len(distinct)
        current.correct_count = len(correct)
        current.incorrect_count = len(distinct - correct)
        current.last_assessed_at = max(as_utc(attempt.assessed_at) for attempt in attempts)
        current.updated_at = now
    await db.flush()


async def apply_reliable_evaluation(
    db: AsyncSession,
    *,
    student_id: str,
    assessment_id: str,
    source_key: str,
    result: EvaluationResult,
    mappings: dict[str, list[tuple[str, float]]],
    assessed_at: Optional[datetime] = None,
) -> None:
    previous = await db.execute(
        select(StudentKcAttempt.kc_id).where(
            StudentKcAttempt.student_id == student_id,
            StudentKcAttempt.source_key == source_key,
        )
    )
    affected = {kc_id for kc_id in previous.scalars().all()}
    await db.execute(
        delete(StudentKcAttempt).where(
            StudentKcAttempt.student_id == student_id,
            StudentKcAttempt.source_key == source_key,
        )
    )
    assessed_at = assessed_at or utc_now()
    for item in result.question_evaluations:
        for kc_id, relevance in mappings.get(item.question_id, []):
            affected.add(kc_id)
            db.add(StudentKcAttempt(
                student_id=student_id,
                kc_id=kc_id,
                assessment_id=assessment_id,
                question_id=item.question_id,
                source_key=source_key,
                competency=item.competency,
                score=float(item.competency_score),
                relevance=relevance,
                awarded_marks=float(item.awarded_marks),
                max_marks=float(item.max_marks),
                correct=_is_correct(item.status, float(item.awarded_marks), float(item.max_marks)),
                assessed_at=assessed_at,
            ))
    await db.flush()
    await _recompute_mastery(db, student_id, affected)


async def record_teacher_confirmed_marks(
    db: AsyncSession,
    *,
    assessment,
    student_id: str,
    source_key: str,
    marks: dict[int, float],
    assessed_at: Optional[datetime] = None,
) -> int:
    """Teacher-confirmed marks (a published handwritten grade or a reviewed online quiz) update the concept graph.

    Only concept links the paper already has are used (frozen `kc_mappings` on the question, or links stored for
    the same question text); no model is asked. `marks` maps the 1-based question number to the awarded marks.
    The same `source_key` replaces earlier rows, so a corrected grade never counts twice. Returns how many
    questions reached the graph."""
    allowed = {item.id for item in await _catalogue(db, assessment.subject_id)}
    if not allowed:
        return 0
    evaluations, mappings = [], {}
    for index, question in enumerate(assessment.questions_json or [], start=1):
        if not isinstance(question, dict) or index not in marks or question.get("competency") not in DIMENSIONS:
            continue
        maximum = float(question.get("marks") or 0)
        if maximum <= 0 or marks[index] is None:
            continue
        question_id = str(index)
        links = published_links(question, allowed)
        if links is None:
            digest = question_text_hash(question.get("text") or "")
            links = [(row.kc_id, float(row.relevance)) for row in await _stored_mappings(db, assessment.id, question_id)
                     if row.kc_id in allowed and row.question_text_hash == digest]
        if not links:
            continue
        awarded = max(0.0, min(maximum, float(marks[index])))
        mappings[question_id] = links
        evaluations.append(SimpleNamespace(
            question_id=question_id, competency=question["competency"], status="attempted",
            competency_score=round(100 * awarded / maximum, 1), awarded_marks=awarded, max_marks=maximum,
        ))
    if not evaluations:
        return 0
    await apply_reliable_evaluation(
        db, student_id=student_id, assessment_id=assessment.id, source_key=source_key,
        result=SimpleNamespace(question_evaluations=evaluations), mappings=mappings, assessed_at=assessed_at,
    )
    return len(evaluations)


async def record_knowledge_graph(db: AsyncSession, context: dict, result: EvaluationResult) -> None:
    """Map questions, then update mastery only for a linked student and a reliable result."""
    questions = []
    by_id = {item.question_id: item for item in result.question_evaluations}
    for question in context["questions"]:
        item = by_id.get(question["id"])
        questions.append({
            **question,
            "student_answer": item.student_answer_extracted if item else "",
        })
    try:
        mappings = await ensure_question_mappings(
            db,
            assessment_id=context["assessment_id"],
            subject_id=context["subject_id"],
            subject_name=context["subject_name"],
            questions=questions,
            ai_provider=context.get("provider") or "gemini",
        )
    except (AIGatewayError, ValueError, json.JSONDecodeError, KeyError):
        logger.warning("Knowledge-component mapping was skipped for assessment %s.", context["assessment_id"])
        return

    if not evaluation_is_reliable(result):
        return
    history = await find_student_upload(
        db,
        school_id=context["school_id"],
        class_id=context["class_id"],
        assessment_id=context["assessment_id"],
        extracted_text=context["extracted_text"],
        history_id=context.get("history_id"),
    )
    if history is None:
        return
    await apply_reliable_evaluation(
        db,
        student_id=history.student_id,
        assessment_id=context["assessment_id"],
        source_key=history.id,
        result=result,
        mappings=mappings,
    )


async def create_component(
    db: AsyncSession, *, name: str, description: str, subject_id: str, topic: str,
) -> KnowledgeComponent:
    subject = await db.get(Subject, subject_id)
    if subject is None:
        raise LookupError("subject")
    name_key = identity_key(name)
    topic_key = identity_key(topic)
    if not name_key or not topic_key:
        raise ValueError("Name and topic are required.")
    duplicate = await db.execute(
        select(KnowledgeComponent.id).where(
            KnowledgeComponent.subject_id == subject_id,
            KnowledgeComponent.name_key == name_key,
            KnowledgeComponent.topic_key == topic_key,
        )
    )
    if duplicate.scalar() is not None:
        raise ValueError("duplicate")
    component = KnowledgeComponent(
        name=name.strip(),
        name_key=name_key,
        description=description.strip(),
        subject_id=subject.id,
        subject_name=subject.name,
        topic=topic.strip(),
        topic_key=topic_key,
    )
    db.add(component)
    await db.flush()
    return component


def _would_cycle(edges: list[tuple[str, str]], source_id: str, target_id: str) -> bool:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for source, target in edges:
        adjacency[source].append(target)
    adjacency[source_id].append(target_id)
    stack = [target_id]
    seen = set()
    while stack:
        node = stack.pop()
        if node == source_id:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adjacency.get(node, []))
    return False


async def create_relationship(
    db: AsyncSession, *, source_id: str, target_id: str, relationship: str,
) -> KnowledgeComponentRelationship:
    if source_id == target_id:
        raise ValueError("A component cannot relate to itself.")
    source = await db.get(KnowledgeComponent, source_id)
    target = await db.get(KnowledgeComponent, target_id)
    if source is None or target is None:
        raise LookupError("component")
    stored_source, stored_target = source_id, target_id
    if relationship == "RELATED_TO" and stored_source > stored_target:
        stored_source, stored_target = stored_target, stored_source
    if relationship in {"PREREQUISITE_OF", "PART_OF"}:
        rows = await db.execute(
            select(KnowledgeComponentRelationship.source_id, KnowledgeComponentRelationship.target_id).where(
                KnowledgeComponentRelationship.relationship == relationship,
            )
        )
        if _would_cycle(list(rows.all()), stored_source, stored_target):
            raise ValueError("That relationship would create a cycle.")
    existing = await db.execute(
        select(KnowledgeComponentRelationship).where(
            KnowledgeComponentRelationship.source_id == stored_source,
            KnowledgeComponentRelationship.target_id == stored_target,
            KnowledgeComponentRelationship.relationship == relationship,
        )
    )
    found = existing.scalars().first()
    if found is not None:
        return found
    row = KnowledgeComponentRelationship(
        source_id=stored_source, target_id=stored_target, relationship=relationship,
    )
    db.add(row)
    await db.flush()
    return row


async def list_components(db: AsyncSession, subject_id: Optional[str]) -> list[KnowledgeComponent]:
    statement = select(KnowledgeComponent).order_by(KnowledgeComponent.subject_name, KnowledgeComponent.name)
    if subject_id:
        statement = statement.where(KnowledgeComponent.subject_id == subject_id)
    return list((await db.execute(statement)).scalars().all())


async def list_relationships(db: AsyncSession, subject_id: Optional[str]) -> list[KnowledgeComponentRelationship]:
    statement = select(KnowledgeComponentRelationship).order_by(KnowledgeComponentRelationship.relationship)
    if subject_id:
        ids = select(KnowledgeComponent.id).where(KnowledgeComponent.subject_id == subject_id)
        statement = statement.where(
            KnowledgeComponentRelationship.source_id.in_(ids),
            KnowledgeComponentRelationship.target_id.in_(ids),
        )
    return list((await db.execute(statement)).scalars().all())


async def build_student_graph(db: AsyncSession, student_id: str) -> dict:
    mastery_rows = list((await db.execute(
        select(StudentKcMastery).where(StudentKcMastery.student_id == student_id)
    )).scalars().all())
    assessed = {row.kc_id: row for row in mastery_rows}
    edges = list((await db.execute(select(KnowledgeComponentRelationship))).scalars().all())
    catalogue_ids = set((await db.scalars(select(KnowledgeComponent.id))).all())

    # The shared catalogue is visible to every student. Mastery stays on the signed-in student,
    # so another student sees the same concepts in grey until their own work is evaluated.
    visible = set(assessed) | catalogue_ids
    for edge in edges:
        if edge.relationship == "PREREQUISITE_OF" and edge.target_id in assessed:
            visible.add(edge.source_id)
        elif edge.relationship == "PART_OF" and edge.target_id in assessed:
            visible.add(edge.source_id)
        elif edge.relationship == "RELATED_TO" and (edge.source_id in assessed or edge.target_id in assessed):
            visible.add(edge.source_id)
            visible.add(edge.target_id)
    if not visible:
        return {"nodes": [], "edges": [], "insights": []}

    components = {
        row.id: row
        for row in (await db.execute(
            select(KnowledgeComponent).where(KnowledgeComponent.id.in_(visible))
        )).scalars().all()
    }
    attempts = list((await db.execute(
        select(StudentKcAttempt)
        .where(StudentKcAttempt.student_id == student_id, StudentKcAttempt.kc_id.in_(visible))
        .order_by(StudentKcAttempt.assessed_at.desc())
    )).scalars().all())
    history: dict[str, list[StudentKcAttempt]] = defaultdict(list)
    for attempt in attempts:
        history[attempt.kc_id].append(attempt)

    def concept_ref(component_id: str, relationship: str) -> Optional[dict]:
        component = components.get(component_id)
        if component is None:
            return None
        mastery = assessed.get(component_id)
        return {
            "id": component.id,
            "name": component.name,
            "relationship": relationship,
            "overall_mastery": mastery.overall_mastery if mastery else None,
            "learning_status": mastery.learning_status if mastery else "not_assessed",
        }

    nodes = []
    insights: list[str] = []
    for component_id, component in sorted(components.items(), key=lambda pair: pair[1].name):
        mastery = assessed.get(component_id)
        component_attempts = history.get(component_id, [])
        latest, previous = latest_and_previous(component_attempts)
        scores = {
            "lu": mastery.lu_mastery if mastery else None,
            "cu": mastery.cu_mastery if mastery else None,
            "ct": mastery.ct_mastery if mastery else None,
            "au": mastery.au_mastery if mastery else None,
        }
        prerequisites = []
        related = []
        prerequisite_scores: list[tuple[str, Optional[float]]] = []
        for edge in edges:
            if edge.relationship == "PREREQUISITE_OF" and edge.target_id == component_id:
                ref = concept_ref(edge.source_id, edge.relationship)
                if ref is None:
                    continue
                prerequisites.append(ref)
                if edge.source_id in assessed:
                    prerequisite_scores.append((ref["name"], ref["overall_mastery"]))
            elif edge.relationship == "PART_OF" and edge.source_id == component_id:
                ref = concept_ref(edge.target_id, edge.relationship)
                if ref is not None:
                    related.append(ref)
            elif edge.relationship == "RELATED_TO" and component_id in {edge.source_id, edge.target_id}:
                other = edge.target_id if edge.source_id == component_id else edge.source_id
                ref = concept_ref(other, edge.relationship)
                if ref is not None:
                    related.append(ref)
        notes = recommendations_for(component.name, scores, prerequisite_scores) if mastery else []
        for note in notes:
            if note not in insights:
                insights.append(note)
        nodes.append({
            "id": component.id,
            "name": component.name,
            "description": component.description,
            "subject": component.subject_name,
            "topic": component.topic,
            "overall_mastery": mastery.overall_mastery if mastery else None,
            "lu": scores["lu"],
            "cu": scores["cu"],
            "ct": scores["ct"],
            "au": scores["au"],
            "attempt_count": mastery.attempt_count if mastery else 0,
            "correct_count": mastery.correct_count if mastery else 0,
            "incorrect_count": mastery.incorrect_count if mastery else 0,
            "learning_status": mastery.learning_status if mastery else "not_assessed",
            "last_assessed_at": mastery.last_assessed_at if mastery else None,
            "latest": latest,
            "previous": previous,
            "history": [
                {
                    "assessed_at": attempt.assessed_at,
                    "question_id": attempt.question_id,
                    "competency": attempt.competency,
                    "score": attempt.score,
                    "awarded_marks": attempt.awarded_marks,
                    "max_marks": attempt.max_marks,
                    "correct": attempt.correct,
                }
                for attempt in component_attempts
            ],
            "prerequisites": prerequisites,
            "related": related,
            "recommendations": notes,
        })

    visible_edges = [
        {"source_id": edge.source_id, "target_id": edge.target_id, "relationship": edge.relationship}
        for edge in edges
        if edge.source_id in components and edge.target_id in components
    ]
    return {"nodes": nodes, "edges": visible_edges, "insights": insights}


_STATUS_ORDER = {"needs_improvement": 0, "developing": 1, "proficient": 2, "not_assessed": 3}


async def student_subject_analysis(
    db: AsyncSession, *, school_id: str, student_id: str, subject_id: str,
) -> dict:
    """One student's concept results for a subject. Unassessed concepts stay unassessed."""
    student = await db.get(Student, student_id)
    if student is None or student.school_id != school_id:
        raise LookupError("student")
    subject = await db.get(Subject, subject_id)
    if subject is None:
        raise LookupError("subject")
    graph = await build_student_graph(db, student.id)
    concepts = []
    for node in graph["nodes"]:
        if node["subject"] != subject.name:
            continue
        concepts.append({
            "id": node["id"],
            "name": node["name"],
            "topic": node["topic"],
            "learning_status": node["learning_status"],
            "overall_mastery": node["overall_mastery"],
            "attempt_count": node["attempt_count"],
            "correct_count": node["correct_count"],
            "incorrect_count": node["incorrect_count"],
            "recommendations": node["recommendations"],
        })
    concepts.sort(key=lambda item: (
        _STATUS_ORDER.get(item["learning_status"], 9),
        item["overall_mastery"] is None,
        item["overall_mastery"] if item["overall_mastery"] is not None else 0,
        item["name"],
    ))
    assessed = [item for item in concepts if item["learning_status"] != "not_assessed"]
    return {
        "student_id": student.id,
        "student_name": student.name,
        "subject_id": subject.id,
        "subject_name": subject.name,
        "assessed_count": len(assessed),
        "not_assessed_count": len(concepts) - len(assessed),
        "concepts": concepts,
    }
