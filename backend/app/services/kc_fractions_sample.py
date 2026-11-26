"""Class 6 fractions sample for a walkthrough.

The concepts are school sample data for testing the pipeline. They are not an
official NCERT import and they are not written into the NCERT catalogue.
"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import Assessment, ClassSection, QuestionBankItem, Student, Subject
from backend.app.models.knowledge_components import (
    KnowledgeComponentDetail,
    QuestionBankKcMapping,
    QuestionKcMapping,
)
from backend.app.schemas.evaluation import EvaluationResult
from backend.app.services import kc_graph_service, kc_recommendation_service

SOURCE = "School sample for a Class 6 fractions walkthrough. This is not an official NCERT textbook import."

CONCEPTS = [
    {
        "code": "sample-c6-identify-fraction",
        "name": "Identify a fraction",
        "description": "Name the fraction shown by equal parts of one whole.",
        "subtopic": "Understanding fractions",
        "objective": "Identify the fraction represented by a shaded figure.",
        "difficulty": "foundational",
        "criteria": "The numerator and denominator both match the figure.",
    },
    {
        "code": "sample-c6-equivalent-identify",
        "name": "Identify equivalent fractions",
        "description": "Recognise two fractions that name the same amount.",
        "subtopic": "Equivalent fractions",
        "objective": "Decide whether two fractions are equivalent.",
        "difficulty": "standard",
        "criteria": "The student shows the fractions name the same amount.",
    },
    {
        "code": "sample-c6-equivalent-generate",
        "name": "Generate equivalent fractions",
        "description": "Build an equivalent fraction by multiplying the numerator and denominator by the same number.",
        "subtopic": "Equivalent fractions",
        "objective": "Generate an equivalent fraction with a given denominator.",
        "difficulty": "standard",
        "criteria": "Numerator and denominator are multiplied by the same whole number.",
    },
    {
        "code": "sample-c6-equivalent-compare",
        "name": "Compare equivalent fractions",
        "description": "Compare fractions after rewriting them with a common value.",
        "subtopic": "Equivalent fractions",
        "objective": "Compare two fractions by using equivalent forms.",
        "difficulty": "advanced",
        "criteria": "The comparison follows from a correct equivalent form.",
    },
    {
        "code": "sample-c6-fraction-quantity",
        "name": "Fraction of a quantity",
        "description": "Find a fraction of a whole quantity. This sample concept is intentionally left off the paper.",
        "subtopic": "Fraction of a quantity",
        "objective": "Calculate a unit fraction of a quantity.",
        "difficulty": "standard",
        "criteria": "The quantity is divided into the denominator, then multiplied by the numerator.",
    },
]

EDGES = [
    ("sample-c6-identify-fraction", "sample-c6-equivalent-identify", "PREREQUISITE_OF"),
    ("sample-c6-equivalent-identify", "sample-c6-equivalent-generate", "PREREQUISITE_OF"),
    ("sample-c6-equivalent-identify", "sample-c6-equivalent-compare", "PREREQUISITE_OF"),
    ("sample-c6-equivalent-generate", "sample-c6-equivalent-compare", "RELATED_TO"),
]

QUESTIONS = [
    {
        "bank_id": "sample-c6-q-identify",
        "text": "What fraction of the shape is shaded if 1 of 4 equal parts is shaded?",
        "competency": "LU",
        "bloom_level": "Remember",
        "answer": "1/4",
        "rubric": "Award both marks for 1/4.",
        "links": ["sample-c6-identify-fraction"],
        "weights": [1],
    },
    {
        "bank_id": "sample-c6-q-generate",
        "text": "Find an equivalent fraction of 2/3 with denominator 12.",
        "competency": "CU",
        "bloom_level": "Apply",
        "answer": "8/12",
        "rubric": "Award marks for multiplying the numerator and denominator by 4.",
        "links": ["sample-c6-equivalent-generate", "sample-c6-equivalent-identify"],
        "weights": [0.7, 0.3],
    },
    {
        "bank_id": "sample-c6-q-compare",
        "text": "Explain why 2/3 and 8/12 are equal, then say how 2/3 compares with 1/2.",
        "competency": "AU",
        "bloom_level": "Analyze",
        "answer": "2/3 = 8/12, and 2/3 is greater than 1/2.",
        "rubric": "Credit the equivalent form and the comparison.",
        "links": ["sample-c6-equivalent-compare"],
        "weights": [1],
    },
]

STUDENTS = [
    {"id": "demo-fraction-meera", "name": "Demo Meera", "roll": 31, "profile": "strong", "scores": [92, 90, 85], "awarded": [2, 2, 2]},
    {"id": "demo-fraction-kabir", "name": "Demo Kabir", "roll": 32, "profile": "partial", "scores": [62, 58, 42], "awarded": [1, 1, 1]},
    {"id": "demo-fraction-anika", "name": "Demo Anika", "roll": 33, "profile": "weak", "scores": [30, 22, 15], "awarded": [0, 0, 0]},
]


async def _concept_id(db: AsyncSession, code: str) -> str | None:
    detail = await db.scalar(select(KnowledgeComponentDetail).where(KnowledgeComponentDetail.stable_code == code))
    return None if detail is None else detail.kc_id


async def ensure_fraction_sample(db: AsyncSession, school_id: str, section: ClassSection) -> dict:
    if section.school_id != school_id or "sub-math" not in (section.subject_ids_json or []):
        raise LookupError("subject")
    subject = await db.get(Subject, "sub-math")
    if subject is None:
        raise LookupError("subject")

    ids: dict[str, str] = {}
    for spec in CONCEPTS:
        found = await _concept_id(db, spec["code"])
        if found is None:
            component = await kc_graph_service.create_component(
                db,
                name=spec["name"],
                description=spec["description"],
                subject_id=subject.id,
                topic="Fractions",
            )
            db.add(KnowledgeComponentDetail(
                kc_id=component.id,
                grade_label="6",
                chapter="Fractions",
                subtopic=spec["subtopic"],
                learning_objective=spec["objective"],
                difficulty=spec["difficulty"],
                assessment_criteria=spec["criteria"],
                source_reference=SOURCE,
                stable_code=spec["code"],
            ))
            await db.flush()
            found = component.id
        ids[spec["code"]] = found

    for source, target, relationship in EDGES:
        await kc_graph_service.create_relationship(
            db, source_id=ids[source], target_id=ids[target], relationship=relationship,
        )

    for spec in QUESTIONS:
        item = await db.get(QuestionBankItem, spec["bank_id"])
        if item is None:
            item = QuestionBankItem(
                id=spec["bank_id"],
                school_id=school_id,
                subject_id=subject.id,
                text=spec["text"],
                type="short",
                correct_answer=spec["answer"],
                marking_rubric=spec["rubric"],
                marks=2,
                competency=spec["competency"],
                bloom_level=spec["bloom_level"],
                is_ai_generated=False,
            )
            db.add(item)
            await db.flush()
        await db.execute(
            delete(QuestionBankKcMapping).where(QuestionBankKcMapping.question_bank_item_id == spec["bank_id"])
        )
        for code, weight in zip(spec["links"], spec["weights"]):
            db.add(QuestionBankKcMapping(
                question_bank_item_id=spec["bank_id"],
                kc_id=ids[code],
                relevance=weight,
            ))
    await db.flush()

    for spec in STUDENTS:
        student = await db.get(Student, spec["id"])
        if student is None:
            db.add(Student(
                id=spec["id"],
                school_id=school_id,
                class_id=section.id,
                class_name=section.name,
                name=spec["name"],
                roll_no=spec["roll"],
            ))
    await db.flush()

    assessment_id = f"sample-c6-fractions-{section.id}"
    questions = []
    for spec in QUESTIONS:
        questions.append({
            "id": spec["bank_id"],
            "text": spec["text"],
            "type": "short",
            "correct_answer": spec["answer"],
            "marking_rubric": spec["rubric"],
            "marks": 2,
            "competency": spec["competency"],
            "bloom_level": spec["bloom_level"],
            "kc_mappings": [
                {"kc_id": ids[code], "relevance": weight}
                for code, weight in zip(spec["links"], spec["weights"])
            ],
        })
    assessment = await db.get(Assessment, assessment_id)
    if assessment is None:
        assessment = Assessment(
            id=assessment_id,
            school_id=school_id,
            class_id=section.id,
            subject_id=subject.id,
            title="Class 6 fractions sample",
            date="2026-11-19",
            total_marks=6,
            status="scheduled",
            competency_focus_json=["LU", "CU", "AU"],
            questions_json=questions,
        )
        db.add(assessment)
        await db.flush()
    else:
        assessment.questions_json = questions
    await kc_graph_service.freeze_published_mappings(db, assessment)

    stored = list((await db.scalars(
        select(QuestionKcMapping).where(QuestionKcMapping.assessment_id == assessment.id)
    )).all())
    mappings: dict[str, list[tuple[str, float]]] = {}
    for index in range(1, len(QUESTIONS) + 1):
        mappings[str(index)] = [
            (row.kc_id, float(row.relevance))
            for row in stored
            if row.question_id == str(index)
        ]

    people = []
    for spec in STUDENTS:
        evaluations = []
        for index, question in enumerate(QUESTIONS, start=1):
            awarded = spec["awarded"][index - 1]
            evaluations.append({
                "question_index": index,
                "question_id": str(index),
                "question_text": question["text"],
                "competency": question["competency"],
                "max_marks": 2,
                "awarded_marks": awarded,
                "competency_score": spec["scores"][index - 1],
                "student_answer_extracted": question["answer"] if awarded else "incorrect",
                "status": "attempted",
            })
        result = EvaluationResult.model_validate({
            "question_evaluations": evaluations,
            "scoring_summary": {"total_marks_obtained": sum(spec["awarded"]), "max_possible_marks": 6, "percentage": 0},
        })
        await kc_graph_service.apply_reliable_evaluation(
            db,
            student_id=spec["id"],
            assessment_id=assessment.id,
            source_key=f"{assessment.id}-{spec['id']}",
            result=result,
            mappings=mappings,
        )
        recommendations = await kc_recommendation_service.recommend_questions_for_student(
            db, student_id=spec["id"], subject_id=subject.id, record=False,
        )
        people.append({
            "student_id": spec["id"],
            "student_name": spec["name"],
            "profile": spec["profile"],
            "recommendations": recommendations,
        })

    return {
        "class_id": section.id,
        "class_name": section.name,
        "subject_id": subject.id,
        "subject_name": subject.name,
        "assessment_id": assessment.id,
        "source_reference": SOURCE,
        "students": people,
    }
