"""LumenEIOS demonstration database: two CBSE schools, Classes 6-8, one academic session in progress.

    Shiksha Bharati Education Society (management, "admin")
    ├── Sunrise Public School, Bengaluru (school-1)   principal Dr. Lakshmi Narayanan
    └── Himalayan Vidya Niketan, Mandi    (school-2)   principal Mr. Rajesh Thakur

Each school runs Classes 6, 7 and 8 with sections A and B (20 students each = 120 students per school),
taught Mathematics, Science, English, Social Science and Hindi by seven subject teachers. Every student has
one parent/guardian account.

The 2026-27 session started on 1 April 2026. By mid-November the schools have held:
    Baseline Diagnostic (April) · Class Test 1 (May) · Periodic Test 1 (July) · Written Assignment (August,
    handwritten, scanned) · Half-Yearly Examination (September) · Class Test 2 (October)
and have open, ungraded work for students to submit (Mathematics/Science worksheets, Periodic Test 2).

Marks are generated from a per-student ability model (overall level, competency strengths, subject
strengths, growth across the term and test-day noise), question by question, so totals, competency
scores (LU/CU/AU/CT), snapshots and the support flags all agree with each other.

Login (see docs/LOGIN_CREDENTIALS.md, written by backend/scripts/build_demo_database.py):
    management / principals / teachers: <first>.<last>@<school>.lumeneios.demo or their staff code
    students: admission number (e.g. SPS22041) - password is the date of birth DDMMYYYY
    parents: registered mobile number or parent.<admission no>@... - password Parent@123
Seeding runs only on an empty database.
"""
from __future__ import annotations

import logging
import math
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.security import get_password_hash
from backend.app.models.entities import (
    Announcement, Assessment, AssessmentSubmission, AuditEvent, ClassSection,
    Notification, ParentStudentLink, QuestionBankItem, School, SchoolMembership, Student, Subject,
    TeacherAssignment, User, UserProfile,
)
from backend.app.modules.differentiated_homework.models import StudentAccountLink
from backend.app.seed import school_content
from backend.app.services.competency_update import (
    DIMENSIONS, apply_observation, clamp, dimension_scores_from_questions, refresh_support_flag, snapshot,
)

logger = logging.getLogger(__name__)

DOMAIN = "lumeneios.demo"
SESSION = "2026-2027"
# Kept for older imports (developer tools); the demonstration database uses per-role passwords below.
DEFAULT_PASSWORD = "Teacher@123"
PASSWORDS = {"admin": "Admin@123", "principal": "Principal@123", "teacher": "Teacher@123", "parent": "Parent@123"}
RNG_SEED = 20260401

SCHOOLS = [
    {"id": "school-1", "code": "SPS", "slug": "sps", "name": "Sunrise Public School", "location": "Bengaluru",
     "state": "Karnataka", "tier": "high-tech", "board": "CBSE",
     "principal": ("user-principal-1", "Dr. Lakshmi Narayanan", "lakshmi.narayanan", "F"),
     "description": "CBSE co-educational day school in Whitefield, Bengaluru. Classes 6-8 on LumenEIOS."},
    {"id": "school-2", "code": "HVN", "slug": "hvn", "name": "Himalayan Vidya Niketan", "location": "Mandi",
     "state": "Himachal Pradesh", "tier": "standard", "board": "CBSE",
     "principal": ("user-principal-2", "Mr. Rajesh Thakur", "rajesh.thakur", "M"),
     "description": "CBSE school in Mandi town serving nearby hill villages. Classes 6-8 on LumenEIOS."},
]
ADMIN = ("user-admin", "Ms. Ananya Rao", "ananya.rao", "Director of Academics, Shiksha Bharati Education Society")

SUBJECTS = [
    {"id": "sub-math", "name": "Mathematics", "code": "MATH", "grade": 6, "icon_name": "Calculator"},
    {"id": "sub-sci", "name": "Science", "code": "SCI", "grade": 6, "icon_name": "FlaskConical"},
    {"id": "sub-eng", "name": "English", "code": "ENG", "grade": 6, "icon_name": "BookOpen"},
    {"id": "sub-sst", "name": "Social Science", "code": "SST", "grade": 6, "icon_name": "Globe"},
    {"id": "sub-hin", "name": "Hindi", "code": "HIN", "grade": 6, "icon_name": "Languages"},
]
SUBJECT_IDS = [s["id"] for s in SUBJECTS]
SUBJECT_NAME = {s["id"]: s["name"] for s in SUBJECTS}
GRADES = (6, 7, 8)
SECTIONS = ("A", "B")
STUDENTS_PER_SECTION = 20

ALL_SECTIONS = [(g, s) for g in GRADES for s in SECTIONS]
LOWER = [(6, "A"), (6, "B"), (7, "A")]
UPPER = [(7, "B"), (8, "A"), (8, "B")]

# key, name, gender, subject, sections taught, class-teacher of
TEACHER_ROSTER = {
    "school-1": [
        ("meera", "Mrs. Meera Krishnan", "F", "sub-math", LOWER, (6, "A")),
        ("suresh", "Mr. Suresh Babu", "M", "sub-math", UPPER, (8, "A")),
        ("garima", "Ms. Garima Sharma", "F", "sub-sci", LOWER, (7, "A")),
        ("arvind", "Mr. Arvind Kulkarni", "M", "sub-sci", UPPER, (8, "B")),
        ("priya", "Ms. Priya Menon", "F", "sub-eng", ALL_SECTIONS, (6, "B")),
        ("irfan", "Mr. Mohammed Irfan", "M", "sub-sst", ALL_SECTIONS, (7, "B")),
        ("sunita", "Mrs. Sunita Verma", "F", "sub-hin", ALL_SECTIONS, None),
    ],
    "school-2": [
        ("kamlesh", "Mr. Kamlesh Thakur", "M", "sub-math", LOWER, (6, "A")),
        ("neha", "Ms. Neha Sood", "F", "sub-math", UPPER, (8, "A")),
        ("vikram", "Mr. Vikram Chauhan", "M", "sub-sci", LOWER, (7, "A")),
        ("pooja", "Mrs. Pooja Katoch", "F", "sub-sci", UPPER, (8, "B")),
        ("preeti", "Ms. Preeti Negi", "F", "sub-eng", ALL_SECTIONS, (6, "B")),
        ("rohit", "Mr. Rohit Sharma", "M", "sub-sst", ALL_SECTIONS, (7, "B")),
        ("anjali", "Mrs. Anjali Guleria", "F", "sub-hin", ALL_SECTIONS, None),
    ],
}

# Shape used by syllabus_seed.teaching_assignments (Mathematics/Science teacher plans for Classes 6-8).
TEACHERS = [
    {"key": key, "name": name, "school": school_id, "subject": subject,
     "grades": sorted({g for g, _ in sections}),
     "designation": f"{SUBJECT_NAME[subject]} teacher, Classes {', '.join(f'{g}-{s}' for g, s in sections)}"}
    for school_id, roster in TEACHER_ROSTER.items()
    for key, name, _g, subject, sections, _ct in roster
]

# The one-click demonstration personas on the sign-in page (also the developer role-switch targets).
FEATURED = {"school": "school-1", "teacher": "garima", "student": (7, "A", 1)}
ROOT_PERSONA_EMAILS = {
    "admin": f"ananya.rao@trust.{DOMAIN}",
    "principal": f"lakshmi.narayanan@sps.{DOMAIN}",
    "teacher": f"garima.sharma@sps.{DOMAIN}",
    "student": f"gurleen.kaur@sps.{DOMAIN}",
    "parent": f"harpreet.kaur@sps.{DOMAIN}",
}

NAMES = {
    "school-1": {
        "M": ["Aarav", "Vihaan", "Aditya", "Arjun", "Rohan", "Karthik", "Siddharth", "Pranav", "Varun", "Nikhil",
              "Ishaan", "Harsha", "Rahul", "Abhinav", "Kiran", "Shreyas", "Tejas", "Akash", "Dhruv", "Yash",
              "Agam", "Pranay", "Tanav", "Sai", "Manish", "Darshan", "Gautam", "Rithvik", "Naveen", "Om"],
        "F": ["Ananya", "Diya", "Ishita", "Kavya", "Meghana", "Nandini", "Pooja", "Riya", "Sneha", "Tanvi",
              "Aditi", "Bhavana", "Divya", "Harini", "Keerthana", "Lakshmi", "Navya", "Prerna", "Sanjana", "Shruti",
              "Grishma", "Vaishnavi", "Anika", "Aishwarya", "Deepika", "Sahana", "Spoorthi", "Varsha", "Mahika", "Tara"],
        "surnames": ["Rao", "Reddy", "Iyer", "Nair", "Gowda", "Shetty", "Kulkarni", "Hegde", "Menon", "Pillai",
                     "Sharma", "Patel", "Joshi", "Bhat", "Naidu", "Krishnan", "Kumar", "Das", "Mehta", "Prasad",
                     "Murthy", "Srinivasan", "Desai", "Acharya"],
    },
    "school-2": {
        "M": ["Aryan", "Ayush", "Ansh", "Kartik", "Mohit", "Nitin", "Pankaj", "Rajat", "Sahil", "Tushar",
              "Vikas", "Abhishek", "Deepak", "Himanshu", "Lakshay", "Naman", "Rishabh", "Sourav", "Tanmay", "Yuvraj",
              "Aman", "Harsh", "Kunal", "Manav", "Parth", "Ritik", "Shubham", "Vishal", "Kabir", "Dev"],
        "F": ["Aarti", "Anjali", "Bhumika", "Diksha", "Ekta", "Garima", "Isha", "Jyoti", "Kanika", "Kritika",
              "Mansi", "Neha", "Palak", "Ritika", "Sakshi", "Shivani", "Simran", "Tanya", "Vanshika", "Muskan",
              "Akriti", "Bhavna", "Chhavi", "Ishika", "Komal", "Nikita", "Pallavi", "Radhika", "Srishti", "Yashika"],
        "surnames": ["Thakur", "Sharma", "Katoch", "Guleria", "Rana", "Chauhan", "Verma", "Negi", "Sood", "Kapoor",
                     "Pathania", "Jamwal", "Bhardwaj", "Dogra", "Kaushal", "Mandyal", "Saini", "Walia", "Thakur",
                     "Sharma", "Rana", "Chandel"],
    },
}
FATHER_NAMES = ["Ramesh", "Suresh", "Mahesh", "Rajesh", "Anil", "Sunil", "Vijay", "Sanjay", "Ashok", "Manoj",
                "Prakash", "Rakesh", "Deepak", "Naresh", "Girish", "Venkatesh", "Ravi", "Sandeep", "Ajay", "Pradeep"]
MOTHER_NAMES = ["Sunita", "Kavita", "Anita", "Rekha", "Seema", "Meena", "Lata", "Geeta", "Shobha", "Usha",
                "Padma", "Radha", "Savita", "Nirmala", "Shalini", "Pushpa", "Asha", "Veena", "Jaya", "Kamla"]
MODALITIES = ["Visual", "Auditory", "Reading/Writing", "Kinesthetic"]

# Assessment calendar of the session. kind: (title, date, cycle, chapters-by-month, questions, scanned?)
ASSESSMENT_PLAN = [
    ("Baseline Diagnostic Test", "2026-04-15", 1, 5, 8, False),
    ("Class Test 1", "2026-05-20", 1, 5, 8, False),
    ("Periodic Test 1", "2026-07-24", 2, 7, 12, False),
    ("Written Assignment (handwritten)", "2026-08-28", 2, 8, 4, True),
    ("Half-Yearly Examination", "2026-09-25", 3, 9, 16, False),
    ("Class Test 2", "2026-10-30", 3, 10, 8, False),
]
OPEN_WORK = [  # scheduled, not yet graded: students submit these (handwritten upload, OCR, evaluator)
    ("Worksheet: {chapter}", "2026-11-20", 4, 11, 4, ("sub-math", "sub-sci")),
    ("Periodic Test 2", "2026-12-08", 4, 11, 6, tuple(SUBJECT_IDS)),
]
TODAY = date(2026, 11, 16)

# Holidays and examination weeks (Time-Aware Engine capacity). Mandi breaks in winter; Bengaluru in summer.
SCHOOL_CALENDAR = {
    "school-1": [
        {"id": "sum", "type": "HOLIDAY", "label": "Summer vacation", "start": "2026-05-01", "end": "2026-05-31"},
        {"id": "pt1", "type": "EXAM", "label": "Periodic Test 1", "start": "2026-07-20", "end": "2026-07-25"},
        {"id": "hy", "type": "EXAM", "label": "Half-Yearly Examination", "start": "2026-09-21", "end": "2026-10-01"},
        {"id": "dus", "type": "HOLIDAY", "label": "Dasara holidays", "start": "2026-10-17", "end": "2026-10-25"},
        {"id": "dee", "type": "HOLIDAY", "label": "Deepavali", "start": "2026-11-08", "end": "2026-11-10"},
        {"id": "pt2", "type": "EXAM", "label": "Periodic Test 2", "start": "2026-12-08", "end": "2026-12-12"},
        {"id": "ann", "type": "EXAM", "label": "Annual Examination", "start": "2027-02-22", "end": "2027-03-10"},
    ],
    "school-2": [
        {"id": "sum", "type": "HOLIDAY", "label": "Summer break", "start": "2026-06-10", "end": "2026-06-30"},
        {"id": "pt1", "type": "EXAM", "label": "Periodic Test 1", "start": "2026-07-20", "end": "2026-07-25"},
        {"id": "hy", "type": "EXAM", "label": "Half-Yearly Examination", "start": "2026-09-21", "end": "2026-10-01"},
        {"id": "dus", "type": "HOLIDAY", "label": "Dussehra and Diwali", "start": "2026-10-19", "end": "2026-10-23"},
        {"id": "pt2", "type": "EXAM", "label": "Periodic Test 2", "start": "2026-12-08", "end": "2026-12-12"},
        {"id": "win", "type": "HOLIDAY", "label": "Winter vacation", "start": "2026-12-24", "end": "2027-02-10"},
        {"id": "ann", "type": "EXAM", "label": "Annual Examination", "start": "2027-02-22", "end": "2027-03-06"},
    ],
}


def class_id(school_id: str, grade: int, section: str = "A") -> str:
    return f"class-{_school(school_id)['slug']}-{grade}{section.lower()}"


def _school(school_id: str) -> dict:
    return next(s for s in SCHOOLS if s["id"] == school_id)


def staff_email(school_id: Optional[str], handle: str) -> str:
    return f"{handle}@{_school(school_id)['slug'] if school_id else 'trust'}.{DOMAIN}"


def teacher_user_id(key: str) -> str:
    return f"user-teacher-{key}"


def _handle(name: str) -> str:
    parts = [p for p in name.replace(".", "").split() if p not in {"Mr", "Mrs", "Ms", "Dr"}]
    return ".".join(p.lower() for p in parts)


# ---------------------------------------------------------------------------------------------------
# Students (deterministic)
# ---------------------------------------------------------------------------------------------------

def build_students() -> List[dict]:
    rng = random.Random(RNG_SEED)
    students: List[dict] = []
    for school in SCHOOLS:
        pool = NAMES[school["id"]]
        used_names: set = set()
        serial = 0
        for grade, section in ALL_SECTIONS:
            names = []
            while len(names) < STUDENTS_PER_SECTION:
                gender = "F" if len(names) % 2 else "M"
                first = rng.choice(pool[gender])
                last = rng.choice(pool["surnames"])
                full = f"{first} {last}"
                if full in used_names:
                    continue
                used_names.add(full)
                names.append((first, last, gender))
            if school["id"] == FEATURED["school"] and (grade, section) == FEATURED["student"][:2]:
                names[0] = ("Gurleen", "Kaur", "F")
            names.sort(key=lambda n: (n[0], n[1]))
            for roll, (first, last, gender) in enumerate(names, start=1):
                serial += 1
                joined = 2026 - (grade - 6) - rng.choice([0, 0, 0, 1, 2])
                admission = f"{school['code']}{str(joined)[-2:]}{serial:03d}"
                birth_year = 2026 - (grade + 5) - (1 if rng.random() < 0.3 else 0)
                dob = date(birth_year, rng.randint(1, 12), rng.randint(1, 28))
                # Mandi starts a little lower (rural catchment, monsoon closures) but improves faster.
                ability = rng.gauss(66 if school["id"] == "school-1" else 62, 12)
                student = {
                    "id": f"stu-{admission.lower()}",
                    "admission_no": admission,
                    "first": first, "last": last, "name": f"{first} {last}", "gender": gender,
                    "school_id": school["id"], "grade": grade, "section": section, "roll_no": roll,
                    "class_id": class_id(school["id"], grade, section), "dob": dob.isoformat(),
                    "joined": joined,
                    "ability": max(32.0, min(95.0, ability)),
                    "dim": {d: rng.gauss(0, 7) for d in DIMENSIONS},
                    "subj": {s: rng.gauss(0, 8) for s in SUBJECT_IDS},
                    "growth": rng.gauss(4 if school["id"] == "school-1" else 6.5, 5),
                    "attendance": round(min(99.0, max(71.0, rng.gauss(90, 6))), 1),
                    "homework": round(min(100.0, max(45.0, rng.gauss(84, 12))), 1),
                    "modality": rng.choice(MODALITIES),
                    "father": f"{rng.choice(FATHER_NAMES)} {last}",
                    "mother": f"{rng.choice(MOTHER_NAMES)} {last}",
                    "mobile": f"9{rng.randint(100000000, 999999999)}",
                }
                if first == "Gurleen" and last == "Kaur":
                    student.update(father="Harjit Singh", mother="Harpreet Kaur", ability=63.0,
                                   dim={"LU": 8, "CU": 3, "AU": -18, "CT": -4}, growth=6.0)
                student["guardian"] = student["mother"] if rng.random() < 0.55 else student["father"]
                if first == "Gurleen" and last == "Kaur":
                    student["guardian"] = "Harpreet Kaur"
                students.append(student)
    return students


def student_email(s: dict) -> str:
    return f"{s['first'].lower()}.{s['last'].lower()}.{s['admission_no'][-3:]}@{_school(s['school_id'])['slug']}.{DOMAIN}"


def parent_email(s: dict) -> str:
    return f"parent.{s['admission_no'].lower()}@{_school(s['school_id'])['slug']}.{DOMAIN}"


def is_featured_student(s: dict) -> bool:
    return s["name"] == "Gurleen Kaur" and s["school_id"] == FEATURED["school"]


def roster_users() -> List[dict]:
    """Every login account (without passwords), in display order. Used by the seed and the credentials sheet."""
    users = [{"id": ADMIN[0], "email": ROOT_PERSONA_EMAILS["admin"], "username": "ADMIN", "name": ADMIN[1],
              "role": "admin", "school_id": "school-1", "designation": ADMIN[3], "password": PASSWORDS["admin"]}]
    for school in SCHOOLS:
        pid, pname, handle, _g = school["principal"]
        users.append({"id": pid, "email": staff_email(school["id"], handle), "username": f"{school['code']}-PRINCIPAL",
                      "name": pname, "role": "principal", "school_id": school["id"],
                      "designation": f"Principal, {school['name']}, {school['location']}", "password": PASSWORDS["principal"]})
    for school_id, roster in TEACHER_ROSTER.items():
        code = _school(school_id)["code"]
        for n, (key, name, _g, subject, sections, ct) in enumerate(roster, start=1):
            users.append({"id": teacher_user_id(key), "email": staff_email(school_id, _handle(name)),
                          "username": f"{code}-T{n:02d}", "name": name, "role": "teacher", "school_id": school_id,
                          "designation": f"{SUBJECT_NAME[subject]} teacher" + (f" · Class teacher {ct[0]}-{ct[1]}" if ct else ""),
                          "password": PASSWORDS["teacher"]})
    for s in build_students():
        featured = is_featured_student(s)
        dob = date.fromisoformat(s["dob"])
        users.append({"id": s["id"], "email": ROOT_PERSONA_EMAILS["student"] if featured else student_email(s),
                      "username": s["admission_no"], "name": s["name"], "role": "student", "school_id": s["school_id"],
                      "designation": f"Student, Class {s['grade']}-{s['section']}, Roll {s['roll_no']}",
                      "password": dob.strftime("%d%m%Y")})
        users.append({"id": f"par-{s['admission_no'].lower()}",
                      "email": ROOT_PERSONA_EMAILS["parent"] if featured else parent_email(s),
                      "username": s["mobile"], "name": s["guardian"], "role": "parent", "school_id": s["school_id"],
                      "designation": f"Parent of {s['name']} ({s['grade']}-{s['section']})", "password": PASSWORDS["parent"]})
    return users


# ---------------------------------------------------------------------------------------------------
# Marks model
# ---------------------------------------------------------------------------------------------------

def _expected_score(s: dict, subject_id: str, dim: str, when: date) -> float:
    progress = max(0.0, min(1.0, (when - date(2026, 4, 1)).days / 230))
    return s["ability"] + s["dim"][dim] + s["subj"][subject_id] + s["growth"] * progress


def _awarded(rng: random.Random, expected: float, marks: int) -> int:
    p = max(0.0, min(1.0, (expected + rng.gauss(0, 8)) / 100))
    # Partial credit on multi-mark questions; MCQs (1 mark) are right or wrong.
    if marks == 1:
        return 1 if rng.random() < p else 0
    return int(round(min(marks, max(0, marks * p + rng.gauss(0, 0.35)))))


def _feedback(pct: int, weakest: Optional[str]) -> str:
    names = {"LU": "reading the question carefully", "CU": "explaining the underlying concept",
             "AU": "applying the method to new problems", "CT": "justifying answers with reasons"}
    tip = f" Focus next on {names[weakest]}." if weakest else ""
    if pct >= 85:
        return "Excellent work - clear and accurate answers." + tip
    if pct >= 70:
        return "Good work. A few steps were missing." + tip
    if pct >= 50:
        return "Satisfactory. Revise the chapter and practise more questions." + tip
    return "Needs improvement. Please meet the teacher for extra practice." + tip


def _question_payload(q: tuple, chapter: str, grade: int) -> dict:
    comp, qtype, text, options, answer, rubric, marks, bloom = q
    return {"text": text, "type": qtype, "options": list(options), "correct_answer": answer, "marking_rubric": rubric,
            "marks": marks, "competency": comp, "bloom_level": bloom, "topic": chapter, "grade": grade}


def _pick_questions(rng: random.Random, grade: int, subject_id: str, by_month: int, count: int,
                    prefer_latest: bool = False) -> List[dict]:
    chapters = school_content.taught_chapters(grade, subject_id, by_month) or school_content.chapters(grade, subject_id)[:1]
    pool = [(c["title"], q) for c in chapters for q in c["questions"]]
    if prefer_latest:
        latest = chapters[-1]["title"]
        pool = [p for p in pool if p[0] == latest] or pool
    picked: List[Tuple[str, tuple]] = []
    # Cover every competency before repeating one.
    by_comp: Dict[str, List[Tuple[str, tuple]]] = {}
    for item in pool:
        by_comp.setdefault(item[1][0], []).append(item)
    for comps in by_comp.values():
        rng.shuffle(comps)
    order = list(DIMENSIONS)
    while len(picked) < min(count, len(pool)):
        for comp in order:
            if by_comp.get(comp) and len(picked) < count:
                picked.append(by_comp[comp].pop())
    return [_question_payload(q, chapter, grade) for chapter, q in picked]


# ---------------------------------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------------------------------

def _hash_all(passwords: List[str]) -> Dict[str, str]:
    unique = sorted(set(passwords))
    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(zip(unique, pool.map(get_password_hash, unique)))


def _dt(day: str, hour: int = 10) -> datetime:
    return datetime.fromisoformat(day).replace(hour=hour, tzinfo=timezone.utc)


async def ensure_classic_demo_student_link(session: AsyncSession) -> None:
    """Kept for startup compatibility. The demonstration roster creates every StudentAccountLink itself."""
    return None


async def seed_database_if_empty(session: AsyncSession) -> None:
    if (await session.execute(select(School.id).limit(1))).first():
        logger.info("Database already seeded.")
        return
    logger.info("Empty database: building the demonstration schools (this takes about a minute)...")
    rng = random.Random(RNG_SEED + 1)
    students = build_students()
    users = roster_users()
    hashes = _hash_all([u["password"] for u in users])

    # Schools, subjects
    for school in SCHOOLS:
        pid, pname, _h, _g = school["principal"]
        session.add(School(
            id=school["id"], name=school["name"], location=school["location"], state=school["state"],
            infrastructure_tier=school["tier"], academic_year=SESSION, principal_id=pid, principal_name=pname,
            student_count=sum(1 for s in students if s["school_id"] == school["id"]),
            teacher_count=len(TEACHER_ROSTER[school["id"]]), class_count=len(ALL_SECTIONS),
            pacing_risk="medium" if school["id"] == "school-2" else "low", description=school["description"],
            official_working_days=220,
        ))
    for subject in SUBJECTS:
        session.add(Subject(**subject))
    from backend.app.models.teacher_planning import SchoolPlanCalendar
    for school in SCHOOLS:
        session.add(SchoolPlanCalendar(
            school_id=school["id"], academic_year=SESSION, version=1, created_by=school["principal"][0],
            reason="Academic calendar 2026-27 approved by the principal",
            config={"year": SESSION, "start": "2026-04-01", "end": "2027-03-31", "weekdays": [1, 2, 3, 4, 5, 6],
                    "periodsPerDay": 8, "periodMinutes": 40, "horizonDays": None,
                    "subjectPeriodsPerDay": {"Mathematics": 2, "Science": 2},
                    "entries": SCHOOL_CALENDAR[school["id"]]},
        ))
    await session.flush()

    # Accounts
    for u in users:
        session.add(User(id=u["id"], email=u["email"], username=u["username"], name=u["name"], role=u["role"],
                         school_id=u["school_id"], designation=u["designation"], hashed_password=hashes[u["password"]]))
    await session.flush()
    for u in users:
        session.add(SchoolMembership(id=f"mem-{u['id']}-{u['school_id']}", user_id=u["id"],
                                     school_id=u["school_id"], role=u["role"]))
    session.add(SchoolMembership(id="mem-user-admin-school-2", user_id=ADMIN[0], school_id="school-2", role="admin"))

    # Classes and teacher allocation
    teacher_names = {teacher_user_id(k): n for r in TEACHER_ROSTER.values() for k, n, *_ in r}
    for school in SCHOOLS:
        class_teacher = {ct: teacher_user_id(k) for k, _n, _g, _s, _sec, ct in TEACHER_ROSTER[school["id"]] if ct}
        for grade, section in ALL_SECTIONS:
            ct_id = class_teacher.get((grade, section))
            session.add(ClassSection(
                id=class_id(school["id"], grade, section), school_id=school["id"], grade=grade, section=section,
                name=f"Class {grade}-{section}", class_teacher_id=ct_id, class_teacher_name=teacher_names.get(ct_id),
                student_count=STUDENTS_PER_SECTION, subject_ids_json=list(SUBJECT_IDS),
            ))
    await session.flush()
    teacher_of: Dict[Tuple[str, int, str, str], str] = {}
    for school_id, roster in TEACHER_ROSTER.items():
        for key, _n, _g, subject, sections, _ct in roster:
            for grade, section in sections:
                session.add(TeacherAssignment(teacher_id=teacher_user_id(key), school_id=school_id,
                                              class_id=class_id(school_id, grade, section), subject_id=subject))
                teacher_of[(school_id, grade, section, subject)] = teacher_user_id(key)

    # Students, parents, links, profiles
    for s in students:
        session.add(Student(
            id=s["id"], school_id=s["school_id"], class_id=s["class_id"], class_name=f"Class {s['grade']}-{s['section']}",
            name=s["name"], roll_no=s["roll_no"], admission_no=s["admission_no"], date_of_birth=s["dob"],
            gender=s["gender"], attendance_pct=s["attendance"], learning_modality=s["modality"],
            parent_id=f"par-{s['admission_no'].lower()}", homework_completion_rate=s["homework"],
            lu_score=60, cu_score=60, au_score=60, ct_score=60, overall_score=60,
            baseline_lu=60, baseline_cu=60, baseline_au=60, baseline_ct=60, baseline_overall=60,
        ))
    await session.flush()
    for s in students:
        pid = f"par-{s['admission_no'].lower()}"
        session.add(ParentStudentLink(id=f"psl-{s['admission_no'].lower()}", parent_user_id=pid, student_id=s["id"]))
        session.add(StudentAccountLink(user_id=s["id"], student_id=s["id"], created_by=ADMIN[0]))
        session.add(UserProfile(user_id=pid, phone=s["mobile"], address=f"{_school(s['school_id'])['location']}"))
        session.add(UserProfile(user_id=s["id"], date_of_birth=date.fromisoformat(s["dob"])))

    # Question bank (teacher-written, topic and grade tagged)
    for school in SCHOOLS:
        for grade in GRADES:
            for subject_id in SUBJECT_IDS:
                author = teacher_of.get((school["id"], grade, "A", subject_id))
                for chapter in school_content.chapters(grade, subject_id):
                    for q in chapter["questions"]:
                        p = _question_payload(q, chapter["title"], grade)
                        session.add(QuestionBankItem(
                            school_id=school["id"], subject_id=subject_id, text=p["text"], type=p["type"],
                            options_json=p["options"], correct_answer=p["correct_answer"],
                            marking_rubric=p["marking_rubric"], marks=p["marks"], competency=p["competency"],
                            bloom_level=p["bloom_level"], topic=chapter["title"], grade=grade,
                            source_document_ids_json=[], source_document_names_json=[
                                f"NCERT {school_content.SUBJECT_BOOKS[subject_id]} (Class {grade})"],
                            is_ai_generated=False, created_by=author,
                        ))
    await session.flush()

    # Graded history: assessments, submissions, competency evolution
    by_class: Dict[str, List[dict]] = {}
    for s in students:
        by_class.setdefault(s["class_id"], []).append(s)
    student_rows = {row.id: row for row in (await session.execute(select(Student))).scalars().all()}
    events: List[Tuple[date, int, str, dict, List[dict], Assessment]] = []
    for school in SCHOOLS:
        for grade, section in ALL_SECTIONS:
            cid = class_id(school["id"], grade, section)
            for subject_id in SUBJECT_IDS:
                for n, (title, day, cycle, by_month, count, scanned) in enumerate(ASSESSMENT_PLAN):
                    if scanned and subject_id not in ("sub-math", "sub-sci"):
                        continue
                    qrng = random.Random(f"{school['id']}-{grade}-{subject_id}-{n}")  # same paper for both sections
                    questions = _pick_questions(qrng, grade, subject_id, by_month, count, prefer_latest=scanned)
                    for i, q in enumerate(questions, start=1):
                        q["id"] = f"q{i}"
                    a = Assessment(
                        id=f"asm-{cid[6:]}-{subject_id[4:]}-{n + 1}", school_id=school["id"], class_id=cid,
                        subject_id=subject_id, title=f"{title} - {SUBJECT_NAME[subject_id]}", cycle_number=cycle,
                        date=day, duration_minutes=30 if count <= 4 else (60 if count <= 6 else 120),
                        total_marks=sum(q["marks"] for q in questions), status="graded",
                        competency_focus_json=sorted({q["competency"] for q in questions}), questions_json=questions,
                    )
                    session.add(a)
                    events.append((date.fromisoformat(day), n, subject_id, {"scanned": scanned, "title": title}, questions, a))
    await session.flush()

    events.sort(key=lambda e: (e[0], e[1], e[2], e[5].class_id))
    rounds: Dict[Tuple[date, int], list] = {}
    for event in events:
        rounds.setdefault((event[0], event[1]), []).append(event)
    column = {"LU": "lu_score", "CU": "cu_score", "AU": "au_score", "CT": "ct_score"}
    baseline_column = {"LU": "baseline_lu", "CU": "baseline_cu", "AU": "baseline_au", "CT": "baseline_ct"}
    for (when, n), round_events in rounds.items():
        baseline: Dict[str, Dict[str, List[int]]] = {}
        touched: Dict[str, Assessment] = {}
        title = round_events[0][3]["title"]
        for _when, _n, subject_id, meta, questions, assessment in round_events:
            for s in by_class[assessment.class_id]:
                row = student_rows[s["id"]]
                graded = []
                for q in questions:
                    got = _awarded(rng, _expected_score(s, subject_id, q["competency"], when), q["marks"])
                    graded.append({"competency": q["competency"], "awarded_marks": got, "max_marks": q["marks"]})
                obtained = sum(g["awarded_marks"] for g in graded)
                total = assessment.total_marks
                pct = round(100 * obtained / total) if total else 0
                dims = dimension_scores_from_questions(graded)
                weakest = min(dims, key=dims.get) if dims else None
                if n == 0:  # Baseline diagnostic: averaged across subjects, applied after the round.
                    bucket = baseline.setdefault(s["id"], {d: [] for d in DIMENSIONS})
                    for d, v in dims.items():
                        bucket[d].append(v)
                else:
                    # Same evidence weighting as live grading: bigger papers move the parameters more.
                    apply_observation(row, dims, weight=round(0.1 + 0.3 * min(1.0, total / 25), 3))
                sub = AssessmentSubmission(
                    assessment_id=assessment.id, student_id=s["id"], student_name=s["name"], marks_obtained=obtained,
                    total_marks=total, percentage=pct,
                    lu_score=dims.get("LU", row.lu_score), cu_score=dims.get("CU", row.cu_score),
                    au_score=dims.get("AU", row.au_score), ct_score=dims.get("CT", row.ct_score),
                    overall_score=clamp(sum(dims.values()) / len(dims)) if dims else pct,
                    feedback=_feedback(pct, weakest), submission_date=when.isoformat(), is_scanned=meta["scanned"],
                )
                sub.created_at = _dt(when.isoformat(), 15)
                session.add(sub)
                touched[s["id"]] = assessment
        for student_id, bucket in baseline.items():
            row = student_rows[student_id]
            for d in DIMENSIONS:
                value = clamp(sum(bucket[d]) / len(bucket[d])) if bucket[d] else 60
                setattr(row, column[d], value)
                setattr(row, baseline_column[d], value)
            refresh_support_flag(row)
            row.baseline_overall = row.overall_score
        # One timeline snapshot per student per assessment round.
        for student_id, assessment in touched.items():
            session.add(snapshot(student_rows[student_id], cycle_number=assessment.cycle_number, subject_id=None,
                                 assessment_id=None, submission_id=None,
                                 notes=f"After {title} ({when.strftime('%d %b %Y')})",
                                 recorded_at=_dt(when.isoformat(), 17)))
        await session.flush()

    # Open work students can submit now (handwritten upload -> OCR -> evaluator)
    for school in SCHOOLS:
        for grade, section in ALL_SECTIONS:
            cid = class_id(school["id"], grade, section)
            for n, (title, day, cycle, by_month, count, subjects) in enumerate(OPEN_WORK):
                for subject_id in subjects:
                    qrng = random.Random(f"open-{school['id']}-{grade}-{subject_id}-{n}")
                    questions = _pick_questions(qrng, grade, subject_id, by_month, count, prefer_latest=(n == 0))
                    for i, q in enumerate(questions, start=1):
                        q["id"] = f"q{i}"
                    chapter = questions[0]["topic"] if questions else "Revision"
                    session.add(Assessment(
                        id=f"asm-{cid[6:]}-{subject_id[4:]}-open{n + 1}", school_id=school["id"], class_id=cid,
                        subject_id=subject_id, title=f"{title.format(chapter=chapter)} - {SUBJECT_NAME[subject_id]}",
                        cycle_number=cycle, date=day, duration_minutes=40 if n == 0 else 60,
                        # Worksheets are open for uploads now; Periodic Test 2 is announced but not open yet.
                        total_marks=sum(q["marks"] for q in questions), status="scheduled" if n == 0 else "draft",
                        competency_focus_json=sorted({q["competency"] for q in questions}), questions_json=questions,
                    ))

    # Announcements and notifications. Lost teaching days are not seeded: they come only from lost periods that
    # teachers record in the Time-Aware Engine, so the dashboards and the engine always show the same count.
    for school in SCHOOLS:
        pid, pname, _h, _g = school["principal"]
        for title, content, role in [
            ("Half-Yearly results published", "Half-Yearly Examination results for Classes 6-8 are available on LumenEIOS. Parent-teacher meeting on Saturday, 17 October.", "all"),
            ("Periodic Test 2 schedule", "Periodic Test 2 for Classes 6-8 begins on 8 December 2026. The syllabus is the chapters completed after the Half-Yearly Examination.", "all"),
            ("Submit worksheets by 20 November", "Mathematics and Science worksheets must be uploaded (photo or PDF of your handwritten answers) through Upload by 20 November.", "student"),
        ]:
            session.add(Announcement(school_id=school["id"], sender_id=pid, sender_name=pname, title=title,
                                     content=content, target_role=role))
    for s in students:
        row = student_rows[s["id"]]
        pid = f"par-{s['admission_no'].lower()}"
        session.add(Notification(user_id=pid, title="Half-Yearly results available",
                                 message=f"{s['name']}'s Half-Yearly Examination results and competency report are ready."))
        if row.needs_support:
            session.add(Notification(user_id=pid, title="Extra support suggested",
                                     message=f"{s['name']} would benefit from extra practice in {row.support_area}. Differentiated homework will be assigned."))
    for school_id, roster in TEACHER_ROSTER.items():
        for key, *_ in roster:
            session.add(Notification(user_id=teacher_user_id(key), title="Worksheets awaiting evaluation",
                                     message="Students are uploading handwritten worksheets. Review the OCR text and evaluate them in Upload."))

    session.add(AuditEvent(timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), user_id=ADMIN[0],
                           user_name="System", action="Demonstration database created",
                           details=f"{len(SCHOOLS)} schools, {len(students)} students, {len(users)} accounts.",
                           category="user"))
    await session.commit()
    logger.info("Seeded %d schools, %d students, %d accounts, %d graded assessments.",
                len(SCHOOLS), len(students), len(users), len(events))
