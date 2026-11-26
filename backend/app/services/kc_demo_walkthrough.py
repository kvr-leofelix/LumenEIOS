"""Sample paper used to demonstrate the knowledge-component workflow.

The sample does not call Gemini or Qwen. It stores a student upload and then
writes the same attempt rows a reliable evaluation would write, so the student
persona shows the resulting colours.
"""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import (
    Assessment,
    AssignmentOcrUpload,
    ClassSection,
    Student,
    StudentOcrHistory,
    Subject,
    User,
)
from backend.app.models.knowledge_components import (
    KnowledgeComponent,
    KnowledgeComponentRelationship,
    QuestionKcMapping,
    StudentKcAttempt,
    StudentKcMastery,
)
from backend.app.modules.differentiated_homework.models import StudentAccountLink
from backend.app.schemas.evaluation import EvaluationResult, QuestionEvaluation, ScoringSummary
from backend.app.services.kc_graph_service import (
    apply_reliable_evaluation,
    build_student_graph,
    create_component,
    create_relationship,
    identity_key,
    question_text_hash,
)

QuestionSpec = dict


def _paper(title: str, concepts: list[dict], questions: list[QuestionSpec], links: list[tuple]) -> dict:
    return {"title": title, "concepts": concepts, "questions": questions, "links": links}


def _q(qid: str, text: str, answer: str, competency: str, score: float, concept: str) -> QuestionSpec:
    awarded = 2 if score >= 75 else 1 if score >= 50 else 0
    return {
        "id": qid,
        "text": text,
        "answer": answer,
        "competency": competency,
        "score": score,
        "awarded": awarded,
        "concept": concept,
    }


CHEMISTRY = _paper(
    "Sample paper: atoms, bonds, and reactions",
    [
        {"name": "Atomic Structure", "topic": "Atoms", "description": "Protons, neutrons, and electron arrangement."},
        {"name": "Electron Configuration", "topic": "Atoms", "description": "How electrons are arranged in shells."},
        {"name": "Periodic Trends", "topic": "Atoms", "description": "How properties change across the periodic table."},
        {"name": "Chemical Bonding", "topic": "Bonds", "description": "How atoms join to form compounds."},
        {"name": "Molecules", "topic": "Bonds", "description": "Groups of atoms held together by bonds."},
        {"name": "Stoichiometry", "topic": "Reactions", "description": "Using a balanced equation to count particles."},
        {"name": "Acids and Bases", "topic": "Reactions", "description": "Substances that donate or accept a proton."},
    ],
    [
        _q("1", "Name the three particles in an atom.", "Protons, neutrons, and electrons.", "LU", 92, "Atomic Structure"),
        _q("2", "Write the electron configuration of sodium.", "2, 8, 1", "CT", 68, "Electron Configuration"),
        _q("3", "State one trend across a period.", "Atomic radius decreases.", "CU", 62, "Periodic Trends"),
        _q("4", "Why do two atoms share electrons?", "To complete their outer shell.", "LU", 38, "Chemical Bonding"),
        _q("5", "Describe a covalent bond.", "A shared pair of electrons.", "CU", 34, "Chemical Bonding"),
        _q("6", "How many moles are in 18 g of water?", "1 mole.", "AU", 88, "Stoichiometry"),
        _q("7", "Name one acid and one base.", "Hydrochloric acid and sodium hydroxide.", "LU", 44, "Acids and Bases"),
    ],
    [
        ("Atomic Structure", "Electron Configuration", "PREREQUISITE_OF"),
        ("Atomic Structure", "Periodic Trends", "PREREQUISITE_OF"),
        ("Atomic Structure", "Chemical Bonding", "PREREQUISITE_OF"),
        ("Chemical Bonding", "Stoichiometry", "PREREQUISITE_OF"),
        ("Stoichiometry", "Acids and Bases", "PREREQUISITE_OF"),
        ("Chemical Bonding", "Molecules", "PART_OF"),
        ("Periodic Trends", "Chemical Bonding", "RELATED_TO"),
    ],
)

MATHEMATICS = _paper(
    "Sample paper: number sense",
    [
        {"name": "Number line", "topic": "Number sense", "description": "Placing numbers in order on a line."},
        {"name": "Integers", "topic": "Number sense", "description": "Whole numbers and their negatives."},
        {"name": "Expressions", "topic": "Algebra", "description": "A combination of numbers and symbols."},
        {"name": "Equations", "topic": "Algebra", "description": "A statement that two expressions are equal."},
        {"name": "Graphs", "topic": "Algebra", "description": "A picture of how two quantities change together."},
        {"name": "Word problems", "topic": "Application", "description": "Turning a sentence into mathematics."},
        {"name": "Units", "topic": "Application", "description": "The measurement attached to a quantity."},
    ],
    [
        _q("1", "Place -2 and 3 on a number line.", "-2 is left of 0 and 3 is right of 0.", "LU", 90, "Number line"),
        _q("2", "Add -4 and 7.", "3", "CU", 60, "Integers"),
        _q("3", "What is an expression?", "Numbers and symbols without an equals sign.", "LU", 36, "Expressions"),
        _q("4", "Simplify 2x + x.", "3x", "CU", 32, "Expressions"),
        _q("5", "Solve 2x = 8.", "x = 4", "AU", 84, "Equations"),
        _q("6", "The line rises as x increases. What does that mean?", "y increases with x.", "CT", 66, "Graphs"),
        _q("7", "A book costs Rs 40. What is the cost of 3 books?", "Rs 120", "LU", 42, "Word problems"),
    ],
    [
        ("Number line", "Integers", "PREREQUISITE_OF"),
        ("Number line", "Expressions", "PREREQUISITE_OF"),
        ("Expressions", "Equations", "PREREQUISITE_OF"),
        ("Equations", "Graphs", "PREREQUISITE_OF"),
        ("Equations", "Word problems", "PREREQUISITE_OF"),
        ("Expressions", "Units", "PART_OF"),
        ("Integers", "Expressions", "RELATED_TO"),
    ],
)

SCIENCE = _paper(
    "Sample paper: cells and forces",
    [
        {"name": "Cell Structure", "topic": "Life processes", "description": "Parts of a cell and what each part does."},
        {"name": "Photosynthesis", "topic": "Life processes", "description": "How plants make food from light."},
        {"name": "Force and Motion", "topic": "Motion", "description": "How forces change the way objects move."},
        {"name": "Energy", "topic": "Motion", "description": "The capacity to make something move or change."},
        {"name": "Nutrition", "topic": "Life processes", "description": "How organisms obtain food."},
        {"name": "Respiration", "topic": "Life processes", "description": "Releasing energy from food."},
        {"name": "Habitat", "topic": "Environment", "description": "The place an organism lives."},
    ],
    [
        _q("1", "Name the part of a cell that controls it.", "The nucleus.", "LU", 86, "Cell Structure"),
        _q("2", "What gas do plants release in light?", "Oxygen.", "CU", 58, "Photosynthesis"),
        _q("3", "A push makes a trolley speed up. Name the force.", "An applied force.", "CT", 40, "Force and Motion"),
        _q("4", "Give one form of energy.", "Kinetic energy.", "LU", 72, "Energy"),
        _q("5", "Why does a plant need minerals?", "To grow.", "AU", 80, "Nutrition"),
        _q("6", "Where does respiration release energy?", "In the cells.", "LU", 36, "Respiration"),
        _q("7", "Name a desert animal and one adaptation.", "A camel stores water.", "CU", 34, "Respiration"),
    ],
    [
        ("Cell Structure", "Photosynthesis", "PREREQUISITE_OF"),
        ("Cell Structure", "Nutrition", "PREREQUISITE_OF"),
        ("Photosynthesis", "Respiration", "PREREQUISITE_OF"),
        ("Force and Motion", "Energy", "PREREQUISITE_OF"),
        ("Nutrition", "Habitat", "RELATED_TO"),
        ("Photosynthesis", "Energy", "PART_OF"),
        ("Cell Structure", "Force and Motion", "RELATED_TO"),
    ],
)


def paper_for(subject_name: str) -> dict:
    name = subject_name.lower()
    if "chem" in name:
        return CHEMISTRY
    if "math" in name:
        return MATHEMATICS
    if "sci" in name:
        return SCIENCE
    return {
        "title": f"Sample paper: {subject_name}",
        "concepts": CHEMISTRY["concepts"],
        "questions": CHEMISTRY["questions"],
        "links": CHEMISTRY["links"],
    }


def _script(paper: dict) -> str:
    return "\n".join(f"Q{item['id']}. {item['answer']}" for item in paper["questions"])


async def _demo_student(db: AsyncSession, school_id: str) -> tuple[User, Student]:
    user = await db.scalar(select(User).where(User.email == "student@lumeneios.demo", User.role == "student"))
    if user is None:
        user = await db.scalar(select(User).where(User.role == "student", User.school_id == school_id))
    if user is None:
        raise LookupError("student")
    link = await db.scalar(select(StudentAccountLink).where(StudentAccountLink.user_id == user.id))
    student = await db.get(Student, link.student_id) if link is not None else None
    if student is None:
        raise LookupError("link")
    return user, student


async def _class_for_subject(db: AsyncSession, school_id: str, subject_id: str, preferred_class_id: str) -> ClassSection:
    preferred = await db.get(ClassSection, preferred_class_id)
    if preferred is not None and preferred.school_id == school_id and subject_id in (preferred.subject_ids_json or []):
        return preferred
    sections = (await db.scalars(select(ClassSection).where(ClassSection.school_id == school_id))).all()
    for section in sections:
        if subject_id in (section.subject_ids_json or []):
            return section
    raise LookupError("class")


async def _ensure_catalogue(db: AsyncSession, subject: Subject, paper: dict) -> dict[str, str]:
    ids: dict[str, str] = {}
    for concept in paper["concepts"]:
        try:
            row = await create_component(
                db,
                name=concept["name"],
                description=concept["description"],
                subject_id=subject.id,
                topic=concept["topic"],
            )
        except ValueError:
            row = await db.scalar(select(KnowledgeComponent).where(
                KnowledgeComponent.subject_id == subject.id,
                KnowledgeComponent.name_key == identity_key(concept["name"]),
                KnowledgeComponent.topic_key == identity_key(concept["topic"]),
            ))
        if row is None:
            raise LookupError("component")
        ids[concept["name"]] = row.id
    for source, target, relationship in paper["links"]:
        try:
            await create_relationship(db, source_id=ids[source], target_id=ids[target], relationship=relationship)
        except ValueError:
            continue
    await _drop_unused_name_collisions(db, subject.id, ids)
    return ids


async def _drop_unused_name_collisions(db: AsyncSession, subject_id: str, kept: dict[str, str]) -> None:
    """A sample concept keeps one row. An older same-name row with no attempts is removed."""
    wanted = {identity_key(name) for name in kept}
    kept_ids = set(kept.values())
    extras = list((await db.scalars(select(KnowledgeComponent).where(
        KnowledgeComponent.subject_id == subject_id,
        KnowledgeComponent.name_key.in_(wanted),
    ))).all())
    for row in extras:
        if row.id in kept_ids:
            continue
        used = await db.scalar(
            select(func.count()).select_from(StudentKcAttempt).where(StudentKcAttempt.kc_id == row.id)
        )
        if used:
            continue
        await db.execute(delete(KnowledgeComponentRelationship).where(
            (KnowledgeComponentRelationship.source_id == row.id)
            | (KnowledgeComponentRelationship.target_id == row.id)
        ))
        await db.execute(delete(QuestionKcMapping).where(QuestionKcMapping.kc_id == row.id))
        await db.execute(delete(StudentKcMastery).where(StudentKcMastery.kc_id == row.id))
        await db.delete(row)
    await db.flush()


def _published_questions(paper: dict) -> list[dict]:
    """Questions the upload evaluator can mark. Each one keeps the sample answer as its key."""
    return [
        {
            "id": item["id"],
            "text": item["text"],
            "type": "short",
            "marks": 2,
            "competency": item["competency"],
            "correct_answer": item["answer"],
            "marking_rubric": f"Award 2 marks when the answer matches: {item['answer']}",
        }
        for item in paper["questions"]
    ]


async def _ensure_paper(
    db: AsyncSession, *, school_id: str, section: ClassSection, subject: Subject, paper: dict, student: Student,
) -> tuple[Assessment, StudentOcrHistory]:
    assessment_id = f"demo-kc-{subject.id}"
    assessment = await db.get(Assessment, assessment_id)
    questions = _published_questions(paper)
    if assessment is None:
        assessment = Assessment(
            id=assessment_id,
            school_id=school_id,
            class_id=section.id,
            subject_id=subject.id,
            title=paper["title"],
            date="2026-11-15",
            duration_minutes=40,
            total_marks=2 * len(questions),
            status="scheduled",
            competency_focus_json=["LU", "CU", "CT", "AU"],
            questions_json=questions,
        )
        db.add(assessment)
        await db.flush()
    else:
        assessment.questions_json = questions
        assessment.total_marks = 2 * len(questions)
    history_id = f"demo-kc-history-{subject.id}"
    history = await db.get(StudentOcrHistory, history_id)
    text = _script(paper)
    if history is None:
        history = StudentOcrHistory(
            id=history_id,
            student_id=student.id,
            file_name="sample-answer.txt",
            extracted_text=text,
            pages_processed=1,
        )
        db.add(history)
        await db.flush()
        db.add(AssignmentOcrUpload(history_id=history.id, assessment_id=assessment.id))
    else:
        history.extracted_text = text
        history.student_id = student.id
        existing = await db.get(AssignmentOcrUpload, history.id)
        if existing is None:
            db.add(AssignmentOcrUpload(history_id=history.id, assessment_id=assessment.id))
    await db.flush()
    return assessment, history


def _result(paper: dict) -> tuple[EvaluationResult, dict[str, str]]:
    questions = [
        QuestionEvaluation(
            question_index=index,
            question_id=item["id"],
            question_text=item["text"],
            competency=item["competency"],
            max_marks=2,
            awarded_marks=item["awarded"],
            competency_score=item["score"],
            student_answer_extracted=item["answer"],
            status="attempted",
            feedback="Sample marking for the demonstration.",
        )
        for index, item in enumerate(paper["questions"], start=1)
    ]
    result = EvaluationResult(
        question_evaluations=questions,
        scoring_summary=ScoringSummary(total_marks_obtained=0, max_possible_marks=1, percentage=0),
    )
    concepts = {item["id"]: item["concept"] for item in paper["questions"]}
    return result, concepts


async def _store_mappings(db: AsyncSession, assessment_id: str, paper: dict, ids: dict[str, str]) -> dict[str, list[tuple[str, float]]]:
    mappings: dict[str, list[tuple[str, float]]] = {}
    for item in paper["questions"]:
        kc_id = ids[item["concept"]]
        mappings[item["id"]] = [(kc_id, 1.0)]
        existing = await db.scalar(select(QuestionKcMapping).where(
            QuestionKcMapping.assessment_id == assessment_id,
            QuestionKcMapping.question_id == item["id"],
            QuestionKcMapping.kc_id == kc_id,
        ))
        if existing is None:
            db.add(QuestionKcMapping(
                assessment_id=assessment_id,
                question_id=item["id"],
                question_text_hash=question_text_hash(item["text"]),
                kc_id=kc_id,
                relevance=1.0,
            ))
    await db.flush()
    return mappings


def _view(graph: dict, subject_name: str) -> dict:
    nodes = [node for node in graph["nodes"] if node["subject"] == subject_name]
    ids = {node["id"] for node in nodes}
    names = {node["name"] for node in nodes}
    return {
        "nodes": nodes,
        "edges": [
            edge for edge in graph["edges"]
            if edge["source_id"] in ids and edge["target_id"] in ids
        ],
        "insights": [note for note in graph["insights"] if any(name in note for name in names)],
    }


async def prepare_demo(db: AsyncSession, teacher: User, subject_id: str) -> dict:
    subject = await db.get(Subject, subject_id)
    if subject is None:
        raise LookupError("subject")
    user, student = await _demo_student(db, teacher.school_id)
    section = await _class_for_subject(db, teacher.school_id, subject.id, student.class_id)
    paper = paper_for(subject.name)
    await _ensure_catalogue(db, subject, paper)
    assessment, history = await _ensure_paper(
        db, school_id=teacher.school_id, section=section, subject=subject, paper=paper, student=student,
    )
    graph = _view(await build_student_graph(db, student.id), subject.name)
    marked = await db.scalar(select(func.count()).select_from(StudentKcAttempt).where(
        StudentKcAttempt.student_id == student.id,
        StudentKcAttempt.source_key == history.id,
    ))
    payload = _payload(user, student, section, subject, assessment, history, graph, evaluated=bool(marked))
    if marked:
        result, _concepts = _result(paper)
        payload["total_marks_obtained"] = result.scoring_summary.total_marks_obtained
        payload["max_possible_marks"] = result.scoring_summary.max_possible_marks
        payload["percentage"] = result.scoring_summary.percentage
    return payload


async def evaluate_demo(db: AsyncSession, teacher: User, subject_id: str) -> dict:
    prepared = await prepare_demo(db, teacher, subject_id)
    subject = await db.get(Subject, subject_id)
    user, student = await _demo_student(db, teacher.school_id)
    paper = paper_for(subject.name)
    ids = await _ensure_catalogue(db, subject, paper)
    result, _concepts = _result(paper)
    mappings = await _store_mappings(db, prepared["assessment_id"], paper, ids)
    history_id = f"demo-kc-history-{subject.id}"
    await apply_reliable_evaluation(
        db,
        student_id=student.id,
        assessment_id=prepared["assessment_id"],
        source_key=history_id,
        result=result,
        mappings=mappings,
    )
    graph = _view(await build_student_graph(db, student.id), subject.name)
    payload = _payload(
        user, student,
        await db.get(ClassSection, (await db.get(Assessment, prepared["assessment_id"])).class_id),
        subject,
        await db.get(Assessment, prepared["assessment_id"]),
        await db.get(StudentOcrHistory, history_id),
        graph,
        evaluated=True,
    )
    payload["total_marks_obtained"] = result.scoring_summary.total_marks_obtained
    payload["max_possible_marks"] = result.scoring_summary.max_possible_marks
    payload["percentage"] = result.scoring_summary.percentage
    return payload


def _payload(user, student, section, subject, assessment, history, graph, *, evaluated: bool) -> dict:
    return {
        "student_name": student.name,
        "student_email": user.email,
        "subject_name": subject.name,
        "assessment_id": assessment.id,
        "title": assessment.title,
        "class_name": section.name,
        "extracted_text": history.extracted_text,
        "evaluated": evaluated,
        "total_marks_obtained": None,
        "max_possible_marks": None,
        "percentage": None,
        "graph": graph,
    }
