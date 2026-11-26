"""Populate LearnSphere for the demonstration through the real API (backend + Qwen must be running).

    python -m backend.scripts.demo_learnsphere [--api http://127.0.0.1:8000/api/v1]

Ms. Garima Sharma (class teacher, 7-A Science) authors topics and activities - Teach-Back challenges,
Real-Life Missions and a support intervention - and assigns them. Eight 7-A students respond (answers of
varying quality, all fictional); Qwen evaluates every Teach-Back; the teacher reviews each attempt with
rubric-based scored criteria. Two students make a second, improved attempt so trends appear. Attempt and
review dates are then spread over October-November so the Learning Journey reads like a real term.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))

TEACHER = ("garima.sharma@sps.lumeneios.demo", "Teacher@123")
CLASS, SUBJECT = "class-sps-7a", "sub-sci"
STUDENTS = ["Gurleen Kaur", "Mahika Sharma", "Anika Srinivasan", "Divya Desai", "Pranay Iyer",
            "Nandini Murthy", "Agam Prasad", "Gautam Rao"]

TOPICS = ["Changes Around Us: Physical and Chemical", "Heat Transfer in Nature", "Exploring Substances: Acidic, Basic, and Neutral"]

ACTIVITIES = [
    dict(key="tb_change", topic=0, kind="teach_back", competency="CU", stage="Bodh",
         title="Teach it back: physical vs chemical change",
         instructions="Explain to a Class 5 student how a physical change is different from a chemical change. "
                      "Use one example of each from your kitchen.",
         rubric="States that no new substance forms in a physical change; states that a new substance forms in a "
                "chemical change; gives one correct example of each; mentions that many physical changes can be reversed."),
    dict(key="tb_breeze", topic=1, kind="teach_back", competency="CU", stage="Bodh",
         title="Teach it back: why the sea breeze blows",
         instructions="Explain to a friend why a cool breeze blows from the sea towards the land during the day.",
         rubric="Land heats up faster than water; warm air over the land rises; cooler air from over the sea moves in "
                "to take its place; at night the direction reverses (land breeze)."),
    dict(key="m_kitchen", topic=0, kind="mission", competency="AU", stage="Prayog",
         title="Mission: kitchen change hunt",
         instructions="At home, find three physical changes and three chemical changes. For each one write what "
                      "changed and how you know whether a new substance was formed.",
         rubric="Six changes listed; each correctly classified; each has a reason based on whether a new substance forms."),
    dict(key="m_indicator", topic=2, kind="mission", competency="CT", stage="Prasar",
         title="Mission: make your own indicator",
         instructions="Make an indicator from turmeric or red cabbage. Test four household liquids, record the colour "
                      "change and classify each as acidic, basic or neutral. Explain one result that surprised you.",
         rubric="Four liquids tested; colours recorded; classification consistent with the colours; a reasoned "
                "explanation of one surprising result."),
    dict(key="s_words", topic=0, kind="support", competency="LU", stage="Abhyas",
         title="Word power: changes around us",
         instructions="Write the meaning of each word in your own words and use it in a sentence: reversible, "
                      "substance, crystallisation, rusting, evaporation.",
         rubric="Each of the five words has a correct meaning and a sentence that uses it correctly."),
]

# (student, activity) -> list of (response, observations[(key, score, max)], teacher feedback)
GOOD_TB = "A physical change only changes shape, size or state and no new substance is made, like melting ice or dissolving sugar - you can often get it back. A chemical change makes a new substance, like burning a chapati or curdling milk into paneer, and you cannot get the old substance back."
OK_TB = "In physical change the thing changes its form but it is the same thing, like ice melting into water. In chemical change something new is made, like when we burn paper and it becomes ash."
WEAK_TB = "Physical change is small change and chemical change is big change. Like cutting vegetable is physical. Cooking is chemical."
BREEZE_GOOD = "In the day the land gets hot faster than the sea water. The hot air over the land becomes light and rises up. Cooler air from over the sea comes in to take its place, so we feel the sea breeze. At night land cools faster so the wind blows from land to sea - that is the land breeze."
BREEZE_OK = "The land becomes hot in the day and the air above it goes up. Then air from the sea comes to the land so there is breeze."
BREEZE_WEAK = "Sea has lot of water and wind so the wind comes from the sea to the land in day time."
KITCHEN_GOOD = "Physical: ice cubes melting (still water), sugar dissolving in tea (sugar is still there, tea tastes sweet), chopping onions (only size changed). Chemical: roti getting brown on tawa (new burnt substance), milk turning to curd (new sour substance), iron tawa getting rust (reddish new substance)."
KITCHEN_OK = "Physical: melting butter, boiling water, cutting tomato. Chemical: cooking rice, burning gas, curd."
INDICATOR_GOOD = "Turmeric indicator. Lemon juice: stayed yellow - acidic. Soap water: turned red - basic. Baking soda in water: red - basic. Tap water: yellow - neutral. Surprise: toothpaste turned light red, so it is basic; I think it is made basic to fight acids made by germs in the mouth."
INDICATOR_OK = "Red cabbage. Vinegar pink, soap green, water purple, lemon pink. Vinegar and lemon are acid, soap is base."
WORDS = "Reversible: can be changed back, like ice to water. Substance: the material something is made of. Crystallisation: getting pure crystals from a solution. Rusting: iron becomes brown when air and water touch it. Evaporation: water becomes vapour when heated."

PLAN = {
    "Gurleen Kaur": {"tb_change": [(OK_TB, 6, "Good examples. Add that many physical changes can be reversed."),
                                   (GOOD_TB, 9, "Much clearer now - reversibility and a new substance are both explained.")],
                     "tb_breeze": [(BREEZE_OK, 6, "Right idea. Explain why the land heats up faster, and what happens at night.")],
                     "m_kitchen": [(KITCHEN_OK, 6, "Correct lists. Give a reason for each one next time.")],
                     "m_indicator": [(INDICATOR_OK, 7, "Careful recording. Explain one surprising result.")]},
    "Mahika Sharma": {"tb_change": [(WEAK_TB, 3, "Use the words 'new substance'. Is cutting a vegetable reversible?"),
                                    (OK_TB, 6, "Better - you now explain that something new is made.")],
                      "tb_breeze": [(BREEZE_WEAK, 2, "Think about which heats faster: land or water.")],
                      "m_kitchen": [(KITCHEN_OK, 5, "Good effort. Add your reasons.")],
                      "s_words": [(WORDS, 8, "Well done - your meanings are correct.")]},
    "Anika Srinivasan": {"tb_change": [(WEAK_TB, 3, "Explain what 'new substance' means.")],
                         "tb_breeze": [(BREEZE_OK, 5, "Add why land heats faster and the night-time reversal.")],
                         "m_kitchen": [(KITCHEN_OK, 5, "Add reasons.")],
                         "s_words": [(WORDS, 7, "Good. Check your sentence for 'crystallisation'.")]},
    "Divya Desai": {"tb_change": [(GOOD_TB, 9, "Excellent explanation with clear examples.")],
                    "tb_breeze": [(BREEZE_GOOD, 9, "Complete and clear, including the land breeze.")],
                    "m_kitchen": [(KITCHEN_GOOD, 9, "Every change classified with a reason.")],
                    "m_indicator": [(INDICATOR_GOOD, 9, "Thoughtful explanation of the toothpaste result.")]},
    "Pranay Iyer": {"tb_change": [(GOOD_TB, 9, "Very clear.")],
                    "tb_breeze": [(BREEZE_GOOD, 9, "Complete.")],
                    "m_kitchen": [(KITCHEN_GOOD, 8, "Well reasoned.")],
                    "m_indicator": [(INDICATOR_GOOD, 9, "Excellent investigation.")]},
    "Nandini Murthy": {"tb_change": [(OK_TB, 6, "Add reversibility.")],
                       "tb_breeze": [(BREEZE_OK, 6, "Explain the night-time land breeze.")],
                       "m_kitchen": [(KITCHEN_OK, 6, "Add reasons.")],
                       "m_indicator": [(INDICATOR_OK, 6, "Explain one surprising result.")]},
    "Agam Prasad": {"tb_change": [(GOOD_TB, 10, "Perfect.")],
                    "tb_breeze": [(BREEZE_GOOD, 10, "Perfect.")],
                    "m_kitchen": [(KITCHEN_GOOD, 9, "Excellent.")],
                    "m_indicator": [(INDICATOR_GOOD, 10, "Outstanding.")]},
    "Gautam Rao": {"tb_change": [(GOOD_TB, 9, "Clear.")],
                   "tb_breeze": [(BREEZE_GOOD, 8, "Good.")],
                   "m_kitchen": [(KITCHEN_GOOD, 9, "Good reasons.")]},
}


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def call(self, method, path, body=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(12):
            req = urllib.request.Request(self.base + path, data, headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=900) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                detail = e.read().decode()[:300]
                # SQLite is briefly locked while background Qwen jobs save their results: wait and retry.
                if e.code == 500 and "Database operation failed" in detail and attempt < 11:
                    time.sleep(5)
                    continue
                raise RuntimeError(f"{method} {path} -> {e.code} {detail}") from None

    def login(self, user, password):
        return self.call("POST", "/auth/login", {"email": user, "password": password})["access_token"]


def observations(score10: int):
    """Split an overall /10 judgement into the rubric's criteria (understanding, examples, vocabulary)."""
    a = round(score10 * 0.4)
    b = round(score10 * 0.35)
    return [{"key": "explains-the-idea", "score": min(4, a), "maximum": 4},
            {"key": "correct-examples", "score": min(3, b), "maximum": 3},
            {"key": "scientific-vocabulary", "score": min(3, max(0, score10 - min(4, a) - min(3, b))), "maximum": 3}]


def main(api_base: str) -> None:
    api = Api(api_base)
    db = sqlite3.connect(APP_DIR / "lumeneios.db")
    db.row_factory = sqlite3.Row
    students = {r["name"]: r for r in db.execute(
        "SELECT id, name, admission_no, date_of_birth FROM students WHERE class_id = ?", (CLASS,))}
    teacher = api.login(*TEACHER)

    existing = {t["title"]: t["id"] for t in api.call("GET", f"/learnsphere/topics?class_id={CLASS}&subject_id={SUBJECT}", token=teacher)
                if t.get("class_id") == CLASS}
    topic_ids = []
    for title in TOPICS:
        topic_ids.append(existing.get(title) or api.call("POST", "/learnsphere/topics",
                         {"class_id": CLASS, "subject_id": SUBJECT, "title": title}, teacher)["id"])
    acts = {}
    for a in ACTIVITIES:
        body = {k: a[k] for k in ("kind", "title", "instructions", "rubric", "competency", "stage")}
        acts[a["key"]] = api.call("POST", "/learnsphere/activities", {**body, "topic_id": topic_ids[a["topic"]]}, teacher)["id"]

    # assign each activity to the students who will answer it
    assignment_of = {}
    for key, act_id in acts.items():
        names = [n for n, plan in PLAN.items() if key in plan]
        ids = [students[n]["id"] for n in names]
        out = api.call("POST", f"/learnsphere/activities/{act_id}/assignments",
                       {"student_ids": ids, "request_key": uuid.uuid4().hex}, teacher)
        for sid, aid in zip(ids, out["assignment_ids"]):  # returned in the order the students were given
            assignment_of[(sid, key)] = aid

    attempts = []  # (attempt_id, student, key, attempt_index)
    for name, plan in PLAN.items():
        s = students[name]
        dob = datetime.strptime(s["date_of_birth"], "%Y-%m-%d").strftime("%d%m%Y")
        tok = api.login(s["admission_no"], dob)
        for key, tries in plan.items():
            aid = assignment_of[(s["id"], key)]
            for i, (response, score, feedback) in enumerate(tries):
                at = api.call("POST", f"/learnsphere/assignments/{aid}/attempts",
                              {"response": response, "request_key": uuid.uuid4().hex}, tok)
                if key.startswith("tb_"):
                    for _ in range(2):
                        try:
                            at = api.call("POST", f"/learnsphere/attempts/{at['id']}/evaluate", None, tok)
                            break
                        except RuntimeError as exc:
                            print("  evaluation retry:", str(exc)[:120])
                            time.sleep(2)
                at = api.call("POST", f"/learnsphere/attempts/{at['id']}/review", {
                    "expected_version": at["version"], "feedback": feedback,
                    "outcome": "Meets the rubric" if score >= 8 else "Partly meets the rubric" if score >= 5 else "Needs more practice",
                    "completed": True, "observations": observations(score)}, teacher)
                attempts.append((at["id"], name, key, i))
                print(f"{name:18s} {key:12s} attempt {i + 1}: {score}/10")

    # Spread the term: first attempts in October, second attempts in November.
    base = datetime(2026, 10, 6, 10, 30, tzinfo=timezone.utc)
    order = {k: n for n, k in enumerate(a["key"] for a in ACTIVITIES)}
    cols = {r[1] for r in db.execute("PRAGMA table_info(learning_attempts)")}
    for att_id, name, key, idx in attempts:
        when = base + timedelta(days=order[key] * 7 + (28 if idx else 0), hours=STUDENTS.index(name))
        for col in ("created_at", "submitted_at"):
            if col in cols:
                db.execute(f"UPDATE learning_attempts SET {col} = ? WHERE id = ?", (when.isoformat(), att_id))
    for (sid, key), aid in assignment_of.items():
        db.execute("UPDATE learning_assignments SET assigned_at = ? WHERE id = ?",
                   ((base + timedelta(days=order[key] * 7 - 2)).isoformat(), aid))
    db.commit()
    quizzes = panchapadi(api, db, teacher, students)
    print(f"LearnSphere demo: {len(acts)} activities, {len(attempts)} reviewed attempts, {quizzes} teacher-confirmed quiz results.")


QUIZZES = [  # (id, title, bank topic, date, submitted_at)
    ("asm-sps-7a-sci-quiz-acids", "Online Quiz: Exploring Substances - Science", "Exploring Substances: Acidic, Basic, and Neutral",
     "2026-10-14", datetime(2026, 10, 14, 11, 0, tzinfo=timezone.utc)),
    ("asm-sps-7a-sci-quiz-metals", "Online Quiz: Metals and Non-metals - Science", "The World of Metals and Non-metals",
     "2026-11-11", datetime(2026, 11, 11, 11, 0, tzinfo=timezone.utc)),
]
QUIZ_STUDENTS = {"Gurleen Kaur": (0.55, 0.75), "Mahika Sharma": (0.3, 0.5), "Divya Desai": (0.85, 0.9), "Pranay Iyer": (0.9, 0.95)}
# Teacher-confirmed marks per question (recall /1, explain /2, apply /2, reason /2) in the October and November quizzes.
QUIZ_MARKS = {"Gurleen Kaur": ([1, 1, 1, 0], [1, 2, 1, 1]), "Mahika Sharma": ([0, 1, 0, 0], [1, 1, 1, 0]),
              "Divya Desai": ([1, 2, 1, 1], [1, 2, 2, 1]), "Pranay Iyer": ([1, 2, 2, 1], [1, 2, 2, 2])}


def confirm_review(api: "Api", teacher: str, rid: str, marks: list) -> None:
    """Teacher review: confirmed marks per question plus the confirmed Panchapadi stage mapping."""
    r = api.call("GET", f"/assessments/results/{rid}", token=teacher)
    questions = [{"position": q["position"], "score": min(q["marks"], marks[q["position"]]), "verify_key": q["type"] == "mcq",
                  "feedback": "Correct." if marks[q["position"]] >= q["marks"] else "Partly correct - compare with the model answer."}
                 for q in r["questions"]]
    api.call("POST", f"/assessments/results/{rid}/review", {
        "expected_version": r["version"], "feedback": "Reviewed and confirmed by the class teacher.", "questions": questions,
        "confirm_panchapadi": True, "panchapadi_mappings": teacher_stage_mapping(r["questions"])}, teacher)


def teacher_stage_mapping(questions: list) -> list:
    """The class teacher's Panchapadi mapping for a 4-question quiz (recall, explain, apply, reason)."""
    def m(stage, why, **flags):
        return {"stage": stage, "reasoning": why, **flags}
    by_comp = {
        "LU": [m("Adheeti", "Recalls a prerequisite fact needed for the chapter.", prerequisite_test=True),
               m("Abhyas", "Routine recognition practised in class.", procedural_practice=True)],
        "CU": [m("Bodh", "Asks the student to explain the concept in their own words.")],
        "AU": [m("Prayog", "Applies the idea to an everyday situation."),
               m("Abhyas", "Uses the learned test procedure.", procedural_practice=True)],
        "CT": [m("Prasar", "Extends the idea to a new problem and justifies a choice.", independent_extension=True),
               m("Prayog", "Applies the concept to a real-life decision.")],
    }
    return [{"position": q["position"], "mappings": by_comp.get(q["competency"], [])} for q in questions]


def panchapadi(api: Api, db: sqlite3.Connection, teacher: str, students: dict) -> int:
    """Two online quizzes answered by six students; Qwen classifies each question into Panchapadi stages in the
    background, then the teacher confirms marks and stage mappings so the Learning Journey has verified points."""
    import random
    rng = random.Random(7)
    template = db.execute("SELECT * FROM assessments WHERE id = 'asm-sps-7a-sci-open1'").fetchone()
    reviewed = 0
    for qi, (aid, title, topic, day, when) in enumerate(QUIZZES):
        bank = db.execute("SELECT * FROM question_bank_items WHERE school_id='school-1' AND subject_id='sub-sci' AND grade=7 "
                          "AND topic=? ORDER BY CASE competency WHEN 'LU' THEN 0 WHEN 'CU' THEN 1 WHEN 'AU' THEN 2 ELSE 3 END", (topic,)).fetchall()
        questions = [{"id": q["id"], "text": q["text"], "type": q["type"], "options": json.loads(q["options_json"] or "[]"),
                      "correct_answer": q["correct_answer"], "marking_rubric": q["marking_rubric"], "marks": q["marks"],
                      "competency": q["competency"], "bloom_level": q["bloom_level"], "topic": topic, "grade": 7} for q in bank]
        db.execute("DELETE FROM assessments WHERE id = ?", (aid,))
        db.execute("INSERT INTO assessments (id, school_id, class_id, subject_id, title, cycle_number, date, duration_minutes, total_marks, "
                   "status, competency_focus_json, questions_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (aid, "school-1", CLASS, SUBJECT, title, template["cycle_number"], day, 30, sum(q["marks"] for q in questions),
                    "scheduled", template["competency_focus_json"], json.dumps(questions), when.isoformat()))
        db.commit()
        for name, quality in QUIZ_STUDENTS.items():
            s = students[name]
            tok = api.login(s["admission_no"], datetime.strptime(s["date_of_birth"], "%Y-%m-%d").strftime("%d%m%Y"))
            good = quality[qi]
            marks = QUIZ_MARKS[name][qi]
            answers = []  # written to match the mark the teacher will confirm
            for pos, q in enumerate(questions):
                if q["type"] == "mcq":
                    right = q["options"].index(q["correct_answer"]) if q["correct_answer"] in q["options"] else 0
                    pick = right if marks[pos] >= q["marks"] else (right + 1) % max(1, len(q["options"]))
                    answers.append({"position": pos, "selected_option_index": pick})
                else:
                    key = (q["correct_answer"] or "").strip()
                    if marks[pos] >= q["marks"]:
                        text = key
                    elif marks[pos] > 0:
                        text = re.split(r"[;,.]", key)[0].strip() or key[: len(key) // 2]
                    else:
                        text = "I do not remember."
                    answers.append({"position": pos, "answer_text": text})
            res = api.call("POST", f"/assessments/{aid}/answers", {"request_key": uuid.uuid4().hex, "answers": answers}, tok)
            rid = res["id"]
            # Let the background Qwen work for this sheet (stage suggestion, written marking, guidance) finish first:
            # on SQLite it holds the write lock while it runs, so a review sent meanwhile fails.
            for _ in range(24):  # the stage suggestion; slower optional guidance is not waited for
                r = api.call("GET", f"/assessments/results/{rid}", token=teacher)
                if r["panchapadi"]["status"] in ("complete", "failed"):
                    break
                time.sleep(5)
            time.sleep(3)
            r = api.call("GET", f"/assessments/results/{rid}", token=teacher)
            # Qwen suggests stages; the teacher confirms the mapping (teacher_stage_mapping), which is the documented
            # path whenever the automatic classification is unavailable or needs correcting.
            questions_review = []
            for q, auto in zip(r["questions"], r["automatic_outcomes"]):
                score = min(q["marks"], QUIZ_MARKS[name][qi][q["position"]])  # the teacher's confirmed mark
                questions_review.append({"position": q["position"], "score": int(score), "verify_key": q["type"] == "mcq",
                                         "feedback": "Correct." if score >= q["marks"] else "Partly correct - compare with the model answer."})
            body = {"expected_version": r["version"], "feedback": "Reviewed and confirmed by the class teacher.",
                    "questions": questions_review}
            body.update(confirm_panchapadi=True, panchapadi_mappings=teacher_stage_mapping(r["questions"]))
            api.call("POST", f"/assessments/results/{rid}/review", body, teacher)
            db.execute("UPDATE learning_assessment_results SET submitted_at = ? WHERE id = ?", (when.isoformat(), rid))
            db.commit()  # never hold a write transaction open while the API is writing
            reviewed += 1
            print(f"  {title[:40]:40s} result {rid[:8]} confirmed")
        db.execute("UPDATE assessments SET status = 'graded' WHERE id = ?", (aid,))
        db.commit()
    return reviewed


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000/api/v1")
    ap.add_argument("--quizzes-only", action="store_true", help="only (re)create the Panchapadi quizzes")
    args = ap.parse_args()
    if args.quizzes_only:
        api = Api(args.api)
        con = sqlite3.connect(APP_DIR / "lumeneios.db")
        con.row_factory = sqlite3.Row
        studs = {r["name"]: r for r in con.execute(
            "SELECT id, name, admission_no, date_of_birth FROM students WHERE class_id = ?", (CLASS,))}
        print(panchapadi(api, con, api.login(*TEACHER), studs), "quiz results confirmed")
    else:
        main(args.api)
