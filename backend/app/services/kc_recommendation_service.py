"""Question recommendations from stored mastery.

Mastery scores stay in kc_graph_service. This module only chooses the next
question. A class average never changes one student's recommendation.
Students with no assessed row are left out of the class average.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import ClassSection, QuestionBankItem, Student, Subject
from backend.app.models.knowledge_components import (
    KnowledgeComponent,
    QuestionBankKcMapping,
    StudentKcMastery,
    StudentQuestionRecommendation,
)
from backend.app.services.kc_graph_service import (
    DEVELOPING_AT,
    PROFICIENT_AT,
    build_student_graph,
    class_subject_evidence,
)

BAND_WEIGHT = {"weak": 3, "moderate": 2, "strong": 1}
KIND_DIFFICULTY = {
    "foundational": "foundational",
    "practice": "standard",
    "application": "advanced",
    "prerequisite": "foundational",
    "diagnostic": "foundational",
}
KIND_COMPETENCY = {
    "foundational": "LU",
    "practice": "CU",
    "application": "AU",
    "prerequisite": "LU",
    "diagnostic": "LU",
}
KIND_QUESTION_TYPE = {
    "foundational": "short",
    "practice": "short",
    "application": "descriptive",
    "prerequisite": "short",
    "diagnostic": "short",
}


def concept_band(concept: dict) -> str:
    """Class band from assessed students only. A missing average is not zero."""
    average = concept.get("average_mastery")
    count = concept.get("student_count") or 0
    if average is None or count <= 0:
        return "insufficient"
    weak_share = concept["needs_improvement_count"] / count
    if average < DEVELOPING_AT or weak_share >= 0.4:
        return "weak"
    if average >= PROFICIENT_AT and concept["needs_improvement_count"] == 0:
        return "strong"
    return "moderate"


def practice_kind(overall: Optional[float], attempt_count: int) -> str:
    if attempt_count <= 0 or overall is None:
        return "diagnostic"
    if overall < DEVELOPING_AT:
        return "foundational"
    if overall < PROFICIENT_AT:
        return "practice"
    return "application"


def allocate_question_counts(items: list[tuple[str, str]], question_count: int) -> dict[str, int]:
    """Largest-remainder split. `items` are (kc_id, band) for assessed concepts only."""
    ranked = [(kc_id, band) for kc_id, band in items if band in BAND_WEIGHT]
    if question_count <= 0 or not ranked:
        return {}
    weights = [BAND_WEIGHT[band] for _, band in ranked]
    total = sum(weights)
    raw = [question_count * weight / total for weight in weights]
    counts = [int(value) for value in raw]
    leftover = question_count - sum(counts)
    order = sorted(
        range(len(ranked)),
        key=lambda index: (raw[index] - counts[index], weights[index]),
        reverse=True,
    )
    for index in order:
        if leftover <= 0:
            break
        counts[index] += 1
        leftover -= 1
    return {kc_id: count for (kc_id, _), count in zip(ranked, counts) if count}


def _reason(name: str, kind: str, overall: Optional[float], attempts: int) -> str:
    shown = "no assessed score yet" if overall is None else f"{overall}% across {attempts} question{'s' if attempts != 1 else ''}"
    if kind == "prerequisite":
        return f"Revisit {name} first. The latest assessed score is {shown}."
    if kind == "diagnostic":
        return f"{name} does not have enough assessed evidence yet ({shown})."
    if kind == "foundational":
        return f"{name} is still weak ({shown}). Use a simpler example before a harder question."
    if kind == "practice":
        return f"{name} is partial ({shown}). Use a question aimed at the mistake, not a new topic."
    return f"{name} is strong ({shown}). Use a harder application question."


def _outcome(kind: str) -> str:
    if kind == "application":
        return "Use the concept in a new situation."
    if kind == "practice":
        return "Correct the specific step the student is still missing."
    if kind == "diagnostic":
        return "See whether the student understands the concept."
    if kind == "prerequisite":
        return "Restore the earlier concept this one depends on."
    return "Rebuild the concept with a simpler example."


def _targets_from_graph(nodes: list[dict]) -> list[dict]:
    """One target per concept. A weak prerequisite replaces advancing on the later concept."""
    by_id = {node["id"]: node for node in nodes}
    chosen: dict[str, dict] = {}

    def keep(node: dict, kind: str) -> None:
        current = chosen.get(node["id"])
        rank = {"prerequisite": 0, "foundational": 1, "diagnostic": 2, "practice": 3, "application": 4}
        if current is not None and rank[current["kind"]] <= rank[kind]:
            return
        chosen[node["id"]] = {
            "kc_id": node["id"],
            "kc_name": node["name"],
            "kind": kind,
            "overall": node.get("overall_mastery"),
            "attempts": node.get("attempt_count") or 0,
            "learning_status": node.get("learning_status") or "not_assessed",
        }

    for node in nodes:
        if node.get("learning_status") == "not_assessed":
            continue
        blocked = False
        for item in node.get("prerequisites") or []:
            if item.get("overall_mastery") is not None and item["overall_mastery"] < DEVELOPING_AT:
                source = by_id.get(item["id"])
                if source is not None:
                    keep(source, "prerequisite")
                    blocked = True
        own = practice_kind(node.get("overall_mastery"), node.get("attempt_count") or 0)
        if blocked and own == "application":
            continue
        if blocked and own == "practice":
            keep(node, "practice")
            continue
        keep(node, "foundational" if blocked else own)
    order = {"prerequisite": 0, "foundational": 1, "diagnostic": 2, "practice": 3, "application": 4}
    return sorted(chosen.values(), key=lambda item: (order[item["kind"]], item["overall"] if item["overall"] is not None else -1))


async def recommend_questions_for_student(
    db: AsyncSession,
    *,
    student_id: str,
    subject_id: Optional[str] = None,
    limit: int = 5,
    record: bool = True,
) -> list[dict]:
    graph = await build_student_graph(db, student_id)
    nodes = graph["nodes"]
    if subject_id:
        subject = await db.get(Subject, subject_id)
        if subject is None:
            raise LookupError("subject")
        nodes = [node for node in nodes if node["subject"] == subject.name]
    targets = _targets_from_graph(nodes)[:limit]
    if not targets:
        return []

    kc_ids = [item["kc_id"] for item in targets]
    mapping_rows = list((await db.scalars(
        select(QuestionBankKcMapping).where(QuestionBankKcMapping.kc_id.in_(kc_ids))
    )).all())
    item_ids = {row.question_bank_item_id for row in mapping_rows}
    items = {}
    if item_ids:
        items = {
            row.id: row
            for row in (await db.scalars(select(QuestionBankItem).where(QuestionBankItem.id.in_(item_ids)))).all()
        }
    by_kc: dict[str, list[tuple[QuestionBankItem, float]]] = defaultdict(list)
    for row in mapping_rows:
        item = items.get(row.question_bank_item_id)
        if item is not None:
            by_kc[row.kc_id].append((item, float(row.relevance)))

    served = set((await db.scalars(
        select(StudentQuestionRecommendation.question_bank_item_id).where(
            StudentQuestionRecommendation.student_id == student_id,
        )
    )).all())
    used: set[str] = set()
    recommendations = []
    for target in targets:
        kind = target["kind"]
        preferred = KIND_COMPETENCY[kind]
        pool = sorted(
            by_kc.get(target["kc_id"], []),
            key=lambda pair: (pair[0].competency != preferred, pair[0].id),
        )
        chosen = next((item for item, _relevance in pool if item.id not in served and item.id not in used), None)
        question = None
        if chosen is not None:
            used.add(chosen.id)
            question = {
                "id": chosen.id,
                "text": chosen.text,
                "type": chosen.type,
                "competency": chosen.competency,
                "marks": chosen.marks,
                "bloom_level": chosen.bloom_level,
            }
            if record:
                db.add(StudentQuestionRecommendation(
                    student_id=student_id,
                    question_bank_item_id=chosen.id,
                    kc_id=target["kc_id"],
                    kind=kind,
                    reason=_reason(target["kc_name"], kind, target["overall"], target["attempts"]),
                ))
        recommendations.append({
            "kc_id": target["kc_id"],
            "kc_name": target["kc_name"],
            "kind": kind,
            "reason": _reason(target["kc_name"], kind, target["overall"], target["attempts"]),
            "previous_performance": target["learning_status"] if target["overall"] is None else f"{target['overall']}%",
            "attempt_count": target["attempts"],
            "expected_outcome": _outcome(kind),
            "difficulty": KIND_DIFFICULTY[kind],
            "question_type": KIND_QUESTION_TYPE[kind],
            "question": question,
            "needs_generation": question is None,
        })
    if record:
        await db.flush()
    return recommendations


def _spread(concept: dict) -> Optional[float]:
    scores = [
        student["overall_mastery"]
        for student in concept.get("students") or []
        if student.get("overall_mastery") is not None
    ]
    if len(scores) < 2:
        return None
    return round(max(scores) - min(scores), 1)


def _slot_reason(name: str, band: str, concept: dict) -> str:
    average = concept.get("average_mastery")
    shown = "no class average" if average is None else f"class average {average}%"
    spread = _spread(concept)
    vary = f" Scores in the class differ by {spread} points." if spread is not None and spread >= 30 else ""
    if band == "weak":
        return f"{name} needs revision ({shown}). Include a foundational question and one that uses the idea.{vary}"
    if band == "strong":
        return f"{name} is strong for the students who were assessed ({shown}). Include a harder application question.{vary}"
    if band == "insufficient":
        return f"{name} has no class evidence. It is not treated as zero. Include it only if you add it yourself."
    return f"{name} is mixed ({shown}). Include a question that checks the idea, not only the procedure.{vary}"


async def class_test_blueprint(
    db: AsyncSession,
    *,
    school_id: str,
    class_id: str,
    subject_id: str,
    total_marks: int,
    question_count: int,
    duration_minutes: int,
    topic: Optional[str] = None,
    slots: Optional[list[dict]] = None,
) -> dict:
    evidence = await class_subject_evidence(db, school_id=school_id, class_id=class_id, subject_id=subject_id)
    components = list((await db.scalars(
        select(KnowledgeComponent).where(KnowledgeComponent.subject_id == subject_id)
    )).all())
    by_id = {row.id: row for row in components}
    needle = (topic or "").strip().casefold()

    def matches(name: str, component_topic: str) -> bool:
        if not needle:
            return True
        return needle in name.casefold() or needle in component_topic.casefold()

    concepts = []
    seen = set()
    for concept in evidence["concepts"]:
        if not matches(concept["name"], concept["topic"]):
            continue
        band = concept_band(concept)
        concepts.append({**concept, "band": band, "students_without_evidence": 0})
        seen.add(concept["id"])
    for component in components:
        if component.id in seen or not matches(component.name, component.topic):
            continue
        concepts.append({
            "id": component.id,
            "name": component.name,
            "topic": component.topic,
            "student_count": 0,
            "proficient_count": 0,
            "developing_count": 0,
            "needs_improvement_count": 0,
            "average_mastery": None,
            "weakest_competency": None,
            "band": "insufficient",
            "students": [],
        })

    roster = set((await db.scalars(select(Student.id).where(
        Student.school_id == school_id,
        Student.class_id == class_id,
    ))).all())
    assessed_students = {
        student["student_id"]
        for concept in evidence["concepts"]
        for student in concept["students"]
    }
    without_evidence = len(roster - assessed_students)

    selected: list[tuple[str, str, str]] = []
    if slots:
        for slot in slots:
            if not slot.get("include", True):
                continue
            component = by_id.get(slot["kc_id"])
            if component is None:
                raise LookupError("component")
            count = max(0, int(slot.get("question_count") or 0))
            difficulty = slot.get("difficulty") or "standard"
            for _ in range(count):
                selected.append((component.id, component.name, difficulty))
    else:
        counted = allocate_question_counts(
            [(concept["id"], concept["band"]) for concept in concepts if concept["band"] in BAND_WEIGHT],
            question_count,
        )
        for concept in concepts:
            difficulty = {"weak": "foundational", "moderate": "standard", "strong": "advanced"}.get(concept["band"], "standard")
            for _ in range(counted.get(concept["id"], 0)):
                selected.append((concept["id"], concept["name"], difficulty))

    mapping_rows = []
    if selected:
        mapping_rows = list((await db.scalars(
            select(QuestionBankKcMapping).where(
                QuestionBankKcMapping.kc_id.in_({kc_id for kc_id, _, _ in selected})
            )
        )).all())
    item_ids = {row.question_bank_item_id for row in mapping_rows}
    bank = {}
    if item_ids:
        bank = {
            row.id: row
            for row in (await db.scalars(
                select(QuestionBankItem).where(
                    QuestionBankItem.id.in_(item_ids),
                    QuestionBankItem.school_id == school_id,
                )
            )).all()
        }
    pool: dict[str, list[QuestionBankItem]] = defaultdict(list)
    links_for_item: dict[str, list[dict]] = defaultdict(list)
    for row in mapping_rows:
        item = bank.get(row.question_bank_item_id)
        if item is None:
            continue
        pool[row.kc_id].append(item)
        links_for_item[item.id].append({"kc_id": row.kc_id, "relevance": float(row.relevance)})

    concept_by_id = {concept["id"]: concept for concept in concepts}
    marks = _split_marks(total_marks, len(selected))
    used: set[str] = set()
    paper = []
    for index, ((kc_id, name, difficulty), slot_marks) in enumerate(zip(selected, marks), start=1):
        concept = concept_by_id.get(kc_id, {"average_mastery": None, "students": [], "band": "insufficient"})
        preferred = {"foundational": "LU", "standard": "CU", "advanced": "AU"}.get(difficulty, "CU")
        choices = sorted(pool.get(kc_id, []), key=lambda item: (item.competency != preferred, item.id))
        chosen = next((item for item in choices if item.id not in used), None)
        question = None
        if chosen is not None:
            used.add(chosen.id)
            question = {
                "id": chosen.id,
                "text": chosen.text,
                "type": chosen.type,
                "competency": chosen.competency,
                "marks": slot_marks,
                "bloom_level": chosen.bloom_level,
                "correct_answer": chosen.correct_answer,
                "marking_rubric": chosen.marking_rubric,
                "kc_mappings": links_for_item.get(chosen.id) or [{"kc_id": kc_id, "relevance": 1}],
            }
        paper.append({
            "kc_id": kc_id,
            "kc_name": name,
            "band": concept.get("band") or "insufficient",
            "difficulty": difficulty,
            "marks": slot_marks,
            "reason": _slot_reason(name, concept.get("band") or "insufficient", concept),
            "question": question,
        })

    section = await db.get(ClassSection, class_id)
    return {
        "class_id": class_id,
        "class_name": section.name if section is not None else evidence["class_name"],
        "subject_id": subject_id,
        "subject_name": evidence["subject_name"],
        "total_marks": total_marks,
        "question_count": question_count,
        "duration_minutes": duration_minutes,
        "roster_count": len(roster),
        "students_without_evidence": without_evidence,
        "concepts": [
            {
                "id": concept["id"],
                "name": concept["name"],
                "topic": concept["topic"],
                "band": concept["band"],
                "student_count": concept["student_count"],
                "proficient_count": concept["proficient_count"],
                "developing_count": concept["developing_count"],
                "needs_improvement_count": concept["needs_improvement_count"],
                "average_mastery": concept["average_mastery"],
                "reason": _slot_reason(concept["name"], concept["band"], concept),
            }
            for concept in concepts
        ],
        "slots": paper,
    }


def _split_marks(total: int, count: int) -> list[int]:
    if count <= 0:
        return []
    base = max(1, total // count) if total > 0 else 1
    marks = [base] * count
    drift = total - sum(marks)
    index = 0
    while drift > 0 and count:
        marks[index % count] += 1
        drift -= 1
        index += 1
    while drift < 0 and count:
        slot = index % count
        if marks[slot] > 1:
            marks[slot] -= 1
            drift += 1
        index += 1
        if index > count * max(total, 1) + 5:
            break
    return marks
