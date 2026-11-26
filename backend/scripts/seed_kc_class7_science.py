"""Demo data: a Class 7 Science concept graph built from the classes' own assessment history.

    python -m backend.scripts.seed_kc_class7_science            # add/refresh the demo data (safe to re-run)

What it does, for Sunrise Public School Classes 7-A and 7-B, Science:
  1. Concepts named after the chapters of the seeded assessments (NCERT "Curiosity" Class 7 chapter titles only,
     no textbook content), with prerequisite links between them.
  2. Every Class 7 Science question (and the matching saved bank questions) is linked to its concepts. The links are stored on the paper as teacher-confirmed
     `kc_mappings`, the same form a teacher confirms in AI Question Studio, so the live grading path reuses them.
  3. Each student's concept history is rebuilt from their recorded results:
       * online quizzes: the teacher-reviewed mark of every question;
       * graded handwritten worksheets: the exact per-question marks (one question per competency);
       * older tests store only LU/CU/AU/CT percentages, so each question takes the student's score for its
         competency in that test. This is a demonstration approximation and is labelled as such in the source key.
  4. Mastery is recomputed with the normal recency weighting.

Ungraded work (for example Gurleen's open worksheet) is left alone, so it can be graded live.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from backend.app.db.session import AsyncSessionLocal  # noqa: E402
from backend.app.models.entities import Assessment, AssessmentSubmission, AssignmentOcrUpload, StudentOcrHistory  # noqa: E402
from backend.app.models.entities import QuestionBankItem  # noqa: E402
from backend.app.models.knowledge_components import (  # noqa: E402
    KnowledgeComponent, KnowledgeComponentRelationship, QuestionBankKcMapping, StudentKcAttempt,
)
from backend.app.modules.learnsphere.assessment_models import AssessmentResultRecord  # noqa: E402
from backend.app.services import kc_graph_service as kc  # noqa: E402

SUBJECT = "sub-sci"
CLASSES = ("class-sps-7a", "class-sps-7b")
CH1 = "The Ever-Evolving World of Science"
CH2 = "Exploring Substances: Acidic, Basic and Neutral"
CH3 = "Electricity: Circuits and their Components"
CH4 = "The World of Metals and Non-metals"
CH5 = "Changes Around Us: Physical and Chemical"

CONCEPTS = [
    ("Scientific method", CH1, "Forming a hypothesis, testing it and sharing methods and results."),
    ("Acid-base indicators", CH2, "Telling acidic, basic and neutral substances apart with litmus and turmeric."),
    ("Neutralisation", CH2, "An acid and a base react; everyday uses such as treating acidic soil."),
    ("Electric circuits", CH3, "Cells, switches and bulbs; why a circuit must be closed for current to flow."),
    ("Series circuits", CH3, "Components in one loop: one fault stops the whole circuit."),
    ("Properties of metals", CH4, "Ductility, conductivity and other properties that decide how metals are used."),
    ("Rusting and its prevention", CH4, "Why iron rusts and how painting or galvanising protects it."),
    ("Physical and chemical changes", CH5, "Whether a new substance is formed, and whether a change can be reversed."),
    ("Signs of a chemical change", CH5, "Colour change, gas, heat or a permanent change show a new substance."),
    ("Crystallisation", CH5, "Getting pure crystals from a solution: a physical change."),
]
LINKS = [
    ("Acid-base indicators", "Neutralisation", "PREREQUISITE_OF"),
    ("Electric circuits", "Series circuits", "PREREQUISITE_OF"),
    ("Physical and chemical changes", "Signs of a chemical change", "PREREQUISITE_OF"),
    ("Physical and chemical changes", "Crystallisation", "PREREQUISITE_OF"),
    ("Physical and chemical changes", "Rusting and its prevention", "PREREQUISITE_OF"),
]
# Question wording -> (concept, relevance). The first matching rule wins.
RULES = [
    ("possible explanation", [("Scientific method", 1.0)]),
    ("hypothesis and a test", [("Scientific method", 1.0)]),
    ("scientific ideas", [("Scientific method", 1.0)]),
    ("share their methods", [("Scientific method", 1.0)]),
    ("litmus", [("Acid-base indicators", 1.0)]),
    ("turmeric", [("Acid-base indicators", 1.0)]),
    ("neutralisation", [("Neutralisation", 1.0)]),
    ("too acidic", [("Neutralisation", 0.7), ("Acid-base indicators", 0.3)]),
    ("series string", [("Series circuits", 0.7), ("Electric circuits", 0.3)]),
    ("in series", [("Electric circuits", 0.6), ("Series circuits", 0.4)]),
    ("opens or closes an electric circuit", [("Electric circuits", 1.0)]),
    ("bulb not glow", [("Electric circuits", 1.0)]),
    ("drawn into wires", [("Properties of metals", 1.0)]),
    ("copper, not iron", [("Properties of metals", 1.0)]),
    ("iron rust but gold", [("Rusting and its prevention", 0.7), ("Properties of metals", 0.3)]),
    ("protect an iron gate", [("Rusting and its prevention", 1.0)]),
    ("cooking an egg", [("Signs of a chemical change", 0.7), ("Physical and chemical changes", 0.3)]),
    ("crystallisation", [("Crystallisation", 0.7), ("Physical and chemical changes", 0.3)]),
    ("chemical change", [("Physical and chemical changes", 1.0)]),
]
HISTORY_KEY = "demo-history:"


def links_for(text: str, ids: dict[str, str]) -> list[dict]:
    low = text.lower()
    for phrase, links in RULES:
        if phrase in low:
            return [{"kc_id": ids[name], "relevance": relevance} for name, relevance in links]
    return []


def day(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value)[:10]).replace(hour=10, tzinfo=timezone.utc)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        # 1. concepts and links (reuse existing rows of the same name and chapter)
        ids: dict[str, str] = {}
        for name, topic, description in CONCEPTS:
            found = await db.scalar(select(KnowledgeComponent).where(
                KnowledgeComponent.subject_id == SUBJECT, KnowledgeComponent.name_key == kc.identity_key(name),
                KnowledgeComponent.topic_key == kc.identity_key(topic)))
            if found is None:
                found = await kc.create_component(db, name=name, description=description, subject_id=SUBJECT, topic=topic)
            ids[name] = found.id
        for source, target, kind in LINKS:
            exists = await db.scalar(select(KnowledgeComponentRelationship.id).where(
                KnowledgeComponentRelationship.source_id == ids[source],
                KnowledgeComponentRelationship.target_id == ids[target]))
            if exists is None:
                await kc.create_relationship(db, source_id=ids[source], target_id=ids[target], relationship=kind)

        # 2. teacher-confirmed concept links on every Class 7 Science paper
        papers = list((await db.scalars(select(Assessment).where(
            Assessment.class_id.in_(CLASSES), Assessment.subject_id == SUBJECT))).all())
        linked = 0
        for paper in papers:
            questions = [dict(q) for q in (paper.questions_json or [])]
            for question in questions:
                found = links_for(question.get("text") or "", ids)
                if found:
                    question["kc_mappings"] = found
                    linked += 1
            paper.questions_json = questions
            flag_modified(paper, "questions_json")
            await kc.freeze_published_mappings(db, paper)
        await db.flush()

        # 2b. the school's saved bank questions get the same concept links, so students are offered practice
        banked = 0
        for item in (await db.scalars(select(QuestionBankItem).where(
                QuestionBankItem.school_id == "school-1", QuestionBankItem.subject_id == SUBJECT))).all():
            for link in links_for(item.text or "", ids):
                exists = await db.scalar(select(QuestionBankKcMapping.id).where(
                    QuestionBankKcMapping.question_bank_item_id == item.id, QuestionBankKcMapping.kc_id == link["kc_id"]))
                if exists is None:
                    db.add(QuestionBankKcMapping(question_bank_item_id=item.id, kc_id=link["kc_id"], relevance=link["relevance"]))
                    banked += 1
        await db.flush()

        # 3. dated concept history from recorded results
        by_paper = {paper.id: paper for paper in papers}
        await db.execute(delete(StudentKcAttempt).where(StudentKcAttempt.assessment_id.in_(by_paper),
                                                        StudentKcAttempt.source_key.like(HISTORY_KEY + "%")))
        students: set[str] = set()
        rows = 0
        uploads = {}  # (assessment, student) -> upload history id: the key the live grading path uses
        for link, history in (await db.execute(select(AssignmentOcrUpload, StudentOcrHistory).join(
                StudentOcrHistory, StudentOcrHistory.id == AssignmentOcrUpload.history_id).where(
                AssignmentOcrUpload.assessment_id.in_(by_paper)))).all():
            uploads[(link.assessment_id, history.student_id)] = history.id
        reviewed = {}  # (assessment, student) -> teacher-reviewed outcomes of an online quiz
        for record in (await db.scalars(select(AssessmentResultRecord).where(
                AssessmentResultRecord.assessment_id.in_(by_paper)))).all():
            if record.reviews_json:
                reviewed[(record.assessment_id, record.student_id)] = record
        for sub in (await db.scalars(select(AssessmentSubmission).where(
                AssessmentSubmission.assessment_id.in_(by_paper)))).all():
            paper = by_paper[sub.assessment_id]
            record = reviewed.get((paper.id, sub.student_id))
            if record is not None:
                # same key as a live teacher review, so a later review replaces these rows
                outcomes = record.reviews_json[-1]["outcomes"]
                marks = {o["position"] + 1: o["score"] for o in outcomes if o.get("score") is not None}
                key, when = f"assessment-result:{record.id}", record.submitted_at
            else:
                by_dimension = {"LU": sub.lu_score, "CU": sub.cu_score, "AU": sub.au_score, "CT": sub.ct_score}
                marks = {index: (by_dimension.get(q.get("competency")) or 0) / 100 * float(q.get("marks") or 0)
                         for index, q in enumerate(paper.questions_json or [], start=1)}
                # graded uploads keep the live key (replacing any earlier rows); older tests get a demo key
                key = uploads.get((paper.id, sub.student_id)) or f"{HISTORY_KEY}{sub.id}"
                when = day(sub.submission_date)
            rows += await kc.record_teacher_confirmed_marks(
                db, assessment=paper, student_id=sub.student_id, source_key=key, marks=marks, assessed_at=when)
            students.add(sub.student_id)
        await db.commit()
        print(f"concepts: {len(ids)} | papers: {len(papers)} | linked questions: {linked} | new bank links: {banked} | "
              f"students with history: {len(students)} | question results recorded: {rows}")


if __name__ == "__main__":
    asyncio.run(main())
