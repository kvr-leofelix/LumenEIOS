"""Classroom activity on top of the seeded session, recorded through the real API (in-process).

What a presenter finds when they sign in (Sunrise Public School, Class 7-A Science, Ms. Garima Sharma):
  * Differentiated Homework already assigned to the students who need support - some released with marks
    (their parameters moved), some submitted and waiting to be marked, one freshly assigned to Gurleen Kaur.
  * Handwritten worksheet uploads (OCR already done) waiting in Upload Beta for the evaluator; two already
    graded and published.
  * Syllabus coverage in the teacher plans up to mid-November (Time-Aware Engine).
Run by backend/scripts/build_demo_database.py after the seed.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.core.security import create_access_token
from backend.app.db.session import AsyncSessionLocal
from backend.app.models.entities import (
    Assessment, AssignmentOcrUpload, ClassSection, QuestionBankItem, Student, StudentOcrHistory, User,
)
from backend.app.models.teacher_planning import TeacherTopicCoverage, TeacherTopicConfig
from backend.app.seed.seed_data import TEACHER_ROSTER, teacher_user_id

API = "/api/v1"
FEATURED_TEACHER = "user-teacher-garima"
FEATURED_CLASS = "class-sps-7a"
DUE = (datetime.now(timezone.utc) + timedelta(days=9)).replace(hour=17, minute=0, second=0, microsecond=0).isoformat()


def headers(user: User) -> Dict[str, str]:
    token = create_access_token(user.id, user.school_id, user.role)
    return {"Authorization": f"Bearer {token}", "X-School-Id": user.school_id}


class Api:
    def __init__(self, client: AsyncClient):
        self.client = client

    async def call(self, method: str, path: str, user: User, body=None, ok=(200, 201)):
        r = await self.client.request(method, API + path, json=body, headers=headers(user))
        if r.status_code not in ok:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else None


def answer_for(item: dict, strength: float, rng: random.Random) -> dict:
    """A plausible answer: stronger students are more often right."""
    position = item["position"]
    if item.get("type") == "mcq" and item.get("options"):
        correct = item.get("correct_index")
        if correct is not None and rng.random() < strength:
            return {"position": position, "selected_option_index": correct}
        return {"position": position, "selected_option_index": rng.randrange(len(item["options"]))}
    good = rng.random() < strength
    text = ("I think it is because " if not good else "") + (item.get("model") or "Explained with an example.")
    if not good:
        text = text.split(".")[0] + "."
    return {"position": position, "answer_text": text}


async def homework(api: Api, db, rng: random.Random) -> Dict[str, int]:
    teacher = await db.get(User, FEATURED_TEACHER)
    students = (await db.execute(select(Student).filter_by(class_id=FEATURED_CLASS).order_by(Student.overall_score))).scalars().all()
    featured = next(s for s in students if s.name == "Gurleen Kaur")
    support = [s for s in students if s.id != featured.id][:6]
    counts = {"assigned": 0, "submitted": 0, "released": 0}
    topics_by_round = [["Exploring Substances: Acidic, Basic, and Neutral", "Electricity: Circuits and their Components"],
                       ["The World of Metals and Non-metals", "Changes Around Us: Physical and Chemical"]]

    async def assign(student: Student, topics: List[str]) -> tuple:
        body = {"subject_id": "sub-sci", "max_questions": 4, "include_ai_generated": False, "topics": topics}
        draft = await api.call("POST", f"/students/{student.id}/homework/drafts", teacher, body)
        await api.call("POST", f"/homework/drafts/{draft['id']}/approve", teacher, {"note": "Targets the weakest competencies."})
        assignment = await api.call("POST", f"/homework/drafts/{draft['id']}/assign", teacher, {"due_at": DUE})
        counts["assigned"] += 1
        return assignment["id"], draft

    async def submit(student: Student, assignment_id: str, draft: dict) -> None:
        user = await db.get(User, student.id)
        detail = await api.call("GET", f"/students/me/homework/assignments/{assignment_id}", user)
        source = {item["position"]: item["source_question_id"] for item in draft["items"]}
        strength = max(0.2, min(0.95, student.overall_score / 100))
        answers = []
        for item in detail["items"]:
            bank = await db.get(QuestionBankItem, source.get(item["position"], ""))
            options = item.get("options") or []
            key = bank.correct_answer if bank else None
            info = {"position": item["position"], "type": item["type"], "options": options,
                    "model": key, "correct_index": options.index(key) if key in options else None}
            answers.append(answer_for(info, strength, rng))
        sub = await api.call("PUT", f"/students/me/homework/assignments/{assignment_id}/submission", user, {"answers": answers})
        await api.call("POST", f"/students/me/homework/assignments/{assignment_id}/submission/submit", user,
                       {"expected_version": sub["version"]})
        counts["submitted"] += 1

    async def mark_and_release(student: Student, assignment_id: str) -> None:
        evaluation = await api.call("POST", f"/homework/assignments/{assignment_id}/evaluation", teacher)
        strength = max(0.25, min(0.95, student.overall_score / 100 + 0.05))
        items = []
        for item in evaluation["items"]:
            top = item["max_marks"]
            answered = item.get("answer_text") or item.get("selected_option_index") is not None
            got = min(top, max(0, round(top * (strength + rng.uniform(-0.2, 0.2))))) if answered else 0
            items.append({"position": item["position"], "awarded_marks": got,
                          "feedback": "Well reasoned." if got == top else ("Good attempt - revise the key idea." if got else "Please attempt every question.")})
        evaluation = await api.call("PATCH", f"/homework/assignments/{assignment_id}/evaluation/items", teacher,
                                    {"expected_version": evaluation["version"], "items": items})
        evaluation = await api.call("POST", f"/homework/assignments/{assignment_id}/evaluation/finalize", teacher,
                                    {"expected_version": evaluation["version"]})
        await api.call("POST", f"/homework/assignments/{assignment_id}/evaluation/release", teacher,
                       {"expected_version": evaluation["version"]})
        counts["released"] += 1

    # Round 1 (earlier): everyone in the support group submitted; four were marked and released.
    for i, student in enumerate([featured] + support):
        aid, draft = await assign(student, topics_by_round[0])
        if i < 6:
            await submit(student, aid, draft)
        if i < 4:
            await mark_and_release(student, aid)
    # Round 2 (current): fresh homework for Gurleen and two others, not started yet.
    for student in [featured] + support[:2]:
        await assign(student, topics_by_round[1])
    await db.commit()
    return counts


def ocr_text(questions: List[dict], strength: float, rng: random.Random) -> str:
    """What the OCR step produced from a student's handwritten sheet (Q-numbered answers)."""
    lines = []
    for i, q in enumerate(questions, start=1):
        if rng.random() < 0.06:
            continue  # skipped question
        answer = q.get("correct_answer") or ""
        if q.get("type") == "mcq":
            options = q.get("options") or [answer]
            text = answer if rng.random() < strength else rng.choice(options)
        elif rng.random() < strength:
            text = answer
        else:
            text = answer.split(";")[0].split(",")[0][:60] + " [unclear]" if rng.random() < 0.3 else answer.split(".")[0][:80]
        lines.append(f"Q{i}. {text}")
    return "\n".join(lines)


async def worksheet_uploads(api: Api, db, rng: random.Random) -> Dict[str, int]:
    teacher = await db.get(User, FEATURED_TEACHER)
    sheet = (await db.execute(select(Assessment).filter(
        Assessment.class_id == FEATURED_CLASS, Assessment.subject_id == "sub-sci", Assessment.status == "scheduled",
        Assessment.title.like("Worksheet%")))).scalars().first()
    students = (await db.execute(select(Student).filter_by(class_id=FEATURED_CLASS).order_by(Student.roll_no))).scalars().all()
    uploaders = [s for s in students if s.name != "Gurleen Kaur"][:9]
    histories = []
    for n, student in enumerate(uploaders):
        strength = max(0.25, min(0.95, student.overall_score / 100))
        history = StudentOcrHistory(student_id=student.id, file_name=f"{student.name.split()[0].lower()}_worksheet_p1.jpg",
                                    extracted_text=ocr_text(sheet.questions_json, strength, rng), pages_processed=1)
        history.created_at = datetime.now(timezone.utc) - timedelta(hours=30 - n * 3)
        db.add(history)
        await db.flush()
        db.add(AssignmentOcrUpload(history_id=history.id, assessment_id=sheet.id))
        histories.append((student, history))
    await db.commit()
    # Two were already evaluated and published by the teacher.
    for student, history in histories[:2]:
        items = []
        for i, q in enumerate(sheet.questions_json, start=1):
            top = q["marks"]
            items.append({"question_index": i, "awarded_marks": min(top, max(0, round(top * min(1, student.overall_score / 90)))),
                          "feedback": None})
        await api.call("POST", f"/assessments/{sheet.id}/grade", teacher,
                       {"student_id": student.id, "history_id": history.id, "items": items,
                        "overall_feedback": "Neat work. Show each step of your reasoning.", "evaluated_by": "teacher"})
    return {"uploads": len(histories), "graded": 2}


async def syllabus_coverage(db) -> Dict[str, int]:
    """Mark topics taught so far in every Mathematics/Science teacher plan (in teaching order)."""
    progress = {"school-1": 0.56, "school-2": 0.48}  # Mandi lost days to monsoon closures
    configs = (await db.execute(select(TeacherTopicConfig))).scalars().all()
    plans: Dict[tuple, List[TeacherTopicConfig]] = {}
    for c in configs:
        plans.setdefault((c.school_id, c.teacher_id, c.academic_year, c.grade, c.subject), []).append(c)
    rows = (await db.execute(select(TeacherTopicCoverage))).scalars().all()
    coverage = {(r.school_id, r.teacher_id, r.academic_year, r.grade, r.subject, r.topic_key): r for r in rows}
    from backend.app.models.teacher_planning import PlanTopic
    order = {t.topic_key: t.sort_order for t in (await db.execute(select(PlanTopic))).scalars().all()}
    marked = 0
    for key, cfgs in plans.items():
        cfgs.sort(key=lambda c: order.get(c.topic_key, 0))
        done = int(len(cfgs) * progress.get(key[0], 0.5))
        for i, cfg in enumerate(cfgs):
            row = coverage.get(key + (cfg.topic_key,))
            if row is None:
                continue
            status = "done" if i < done else ("in_progress" if i < done + 2 else "not_done")
            if row.status != status:
                row.status, row.source, row.updated_by = status, "MANUAL", key[1]
                marked += 1
    await db.commit()
    return {"plans": len(plans), "topics_updated": marked}


async def run_scenario() -> Dict[str, Dict[str, int]]:
    from backend.app.main import app

    rng = random.Random(7)
    out = {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://scenario") as client:
        api = Api(client)
        async with AsyncSessionLocal() as db:
            out["coverage"] = await syllabus_coverage(db)
        async with AsyncSessionLocal() as db:
            out["homework"] = await homework(api, db, rng)
        async with AsyncSessionLocal() as db:
            out["worksheets"] = await worksheet_uploads(api, db, rng)
    for name, result in out.items():
        print(f"   {name}: {result}")
    return out
