"""Localhost prototype launcher for the Differentiated Homework demonstration.

Creates (or resumes) an ISOLATED demo directory inside this clone and serves the live
backend against it. It never opens the default ./lumeneios.db, team databases or existing
uploads, and never touches shared/team accounts:

- A new run refuses to start if its database or upload directory already exists.
- It seeds the existing synthetic sample data into the NEW database only, then gives every
  synthetic account a distinct local-only email (…@local-demo.lumeneios.demo) and one random
  per-run password, written to <run-dir>/credentials.txt (git-ignored). These accounts exist
  only in this run's SQLite file.
- It adds an explicit StudentAccountLink for the sample student (admin-created in a real
  system) and a small synthetic question bank, so the teacher→student→parent flow works.
- Backend DEMO_MODE stays false: real bearer tokens, no "demo123" shortcut, no auto-seed.

Run from apps/lumeneios:
    .venv-release\\Scripts\\python.exe -B -m backend.scripts.local_demo            # new run
    .venv-release\\Scripts\\python.exe -B -m backend.scripts.local_demo --resume <run-dir>
"""
import argparse
import asyncio
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path

MARKER = ".lumeneios-local-demo"
DEMO_ROOT = Path(__file__).resolve().parents[2] / ".local-demo"
EMAIL_DOMAIN = "local-demo.lumeneios.demo"
FRONTEND_ORIGINS = '["http://127.0.0.1:3000","http://localhost:3000"]'

# Synthetic Grade 8 maths questions covering all four competencies and several Bloom levels.
# (id suffix, type, options, correct answer, rubric, marks, competency, bloom, text)
QUESTIONS = [
    ("lu-1", "mcq", ["2/3", "3/2", "-2/3", "1"], "3/2", "1m for 3/2.", 1, "LU", "Remember",
     "What is the multiplicative inverse of 2/3?"),
    ("lu-2", "short", [], "l × b × h", "1m for the formula; 1m for naming each dimension.", 2, "LU", "Remember",
     "Write the formula for the volume of a cuboid and name each quantity in it."),
    ("lu-3", "mcq", ["Square", "Rhombus", "Trapezium", "Kite"], "Square",
     "1m for Square.", 1, "LU", "Understand", "Which quadrilateral has four equal sides AND four right angles?"),
    ("cu-1", "short", [], "Because a square satisfies every property of a rectangle.",
     "1m for property comparison; 1m for subset conclusion.", 2, "CU", "Understand",
     "Explain why every square is a rectangle but not every rectangle is a square."),
    ("cu-2", "mcq", ["It doubles", "It becomes 4 times", "It becomes 8 times", "It stays the same"],
     "It becomes 8 times", "1m for 8 times.", 1, "CU", "Understand",
     "If every side of a cube is doubled, what happens to its volume?"),
    ("cu-3", "short", [], "Zero times any number is 0, never 1.", "2m for the reasoning.", 2, "CU", "Understand",
     "Why does zero have no multiplicative inverse?"),
    ("au-1", "practical", [], "Volume = 2 × 1.5 × 1 = 3 m³ = 3000 L.",
     "1m volume; 1m conversion to litres; 1m final answer.", 3, "AU", "Apply",
     "A tank is 2 m long, 1.5 m wide and 1 m deep. How many litres of water can it hold?"),
    ("au-2", "short", [], "Area = 12 × 8 = 96 m²; cost = 96 × 25 = ₹2400.",
     "1m area; 1m cost.", 2, "AU", "Apply",
     "A rectangular floor is 12 m by 8 m. Tiling costs ₹25 per m². Find the total cost."),
    ("au-3", "mcq", ["154 cm²", "44 cm²", "308 cm²", "77 cm²"], "154 cm²", "1m for 154 cm².", 1, "AU", "Apply",
     "Using π = 22/7, what is the area of a circle of radius 7 cm?"),
    ("ct-1", "descriptive", [], "Compare volume per rupee; reasoned recommendation.",
     "2m for computing both volumes; 1m comparison; 1m justified choice.", 4, "CT", "Evaluate",
     "Shop A sells a 10×10×10 cm box of sugar for ₹50; Shop B sells a 20×10×5 cm box for ₹45. "
     "Which is better value? Justify your answer."),
    ("ct-2", "descriptive", [], "Doubling sides makes area 4×, so needs 4× paint, not 2×.",
     "2m for identifying the error; 1m correct factor; 1m explanation.", 4, "CT", "Analyze",
     "Riya says: 'If I double the side of a square wall, I need twice as much paint.' "
     "Is she right? Analyse her reasoning."),
    ("ct-3", "short", [], "Any valid design with V = 1000 cm³ and justification.",
     "1m valid dimensions; 1m justification.", 2, "CT", "Create",
     "Design a box that holds exactly 1 litre. Give its dimensions and explain one advantage of your design."),
]


def _fail(message):
    print(f"local_demo: {message}", file=sys.stderr)
    sys.exit(2)


def _prepare(run_dir: Path, resume: bool) -> Path:
    run_dir = run_dir.resolve()
    if not run_dir.is_relative_to(DEMO_ROOT.resolve()):
        _fail(f"demo runs must live under {DEMO_ROOT}")
    if resume:
        if not (run_dir / MARKER).is_file():
            _fail(f"{run_dir} is not a local demo directory created by this script")
    else:
        if run_dir.exists():
            _fail(f"{run_dir} already exists; refusing to overwrite it")
        run_dir.mkdir(parents=True)
        (run_dir / MARKER).write_text("Created by backend.scripts.local_demo. Synthetic data only.\n")
    # Settings are read at import time, so configure the environment BEFORE importing the app.
    os.environ.update({
        "APP_ENV": "development",
        "DEBUG": "false",
        "DEMO_MODE": "false",
        "DATABASE_URL": "sqlite+aiosqlite:///" + (run_dir / "local.db").as_posix(),
        "STORAGE_LOCAL_DIR": str(run_dir / "uploads"),
        "SECRET_KEY": secrets.token_hex(32),  # in memory only; sessions end when the server stops
        "BACKEND_CORS_ORIGINS": FRONTEND_ORIGINS,
    })
    return run_dir


# Extra synthetic students so every school-1 class has a roster. The shared seed only creates
# Student rows for Class 8-A and 9-B; 8-B and 7-A had a nominal student_count but nobody
# enrolled, so picking them showed an empty student list. Profiles differ so the gap analysis
# targets different competencies.
# (id suffix, class id, class name, name, roll, LU, CU, AU, CT)
EXTRA_STUDENTS = [
    ("8b-1", "class-8b", "Class 8-B", "Neha Verma", 2, 62, 75, 81, 70),
    ("8b-2", "class-8b", "Class 8-B", "Karan Malhotra", 5, 80, 58, 72, 77),
    ("8b-3", "class-8b", "Class 8-B", "Sana Qureshi", 11, 74, 79, 55, 68),
    ("7a-1", "class-7a", "Class 7-A", "Rahul Saxena", 3, 69, 71, 66, 52),
    ("7a-2", "class-7a", "Class 7-A", "Meera Joshi", 6, 57, 73, 70, 75),
    ("7a-3", "class-7a", "Class 7-A", "Vivaan Reddy", 9, 81, 64, 77, 71),
]

# Second student login, linked to the seeded Student "Ananya Patel" (also linked to the sample
# parent), so the demo has two student accounts and the parent sees two children.
SECOND_STUDENT = ("demo-user-student-2", "ananya.patel", "Ananya Patel", "student-ananya")

SCIENCE_QUESTIONS = [
    ("sci-lu-1", "mcq", ["Friction", "Gravity", "Magnetic force", "Muscular force"], "Gravity", "1m for Gravity.",
     1, "LU", "Remember", "Which of these is a non-contact force that pulls objects towards the Earth?"),
    ("sci-cu-1", "short", [], "Pressure = force / area; a smaller area gives more pressure.",
     "1m for the relation; 1m for applying it.", 2, "CU", "Understand",
     "Why is it easier to cut with a sharp knife than a blunt one? Use the idea of pressure."),
    ("sci-au-1", "practical", [], "P = F/A = 600 N / 0.03 m² = 20,000 Pa.",
     "1m formula; 1m unit conversion; 1m answer.", 3, "AU", "Apply",
     "A box weighing 600 N rests on a face of area 300 cm². Find the pressure it exerts in pascals."),
    ("sci-ct-1", "descriptive", [], "Treads channel water away and keep friction; worn tyres hydroplane.",
     "2m mechanism; 2m justified conclusion.", 4, "CT", "Evaluate",
     "A driver claims tyre treads do not matter on wet roads. Evaluate this claim using what you know about friction."),
]


async def _seed(run_dir: Path) -> None:
    from sqlalchemy import func, select

    from backend.app.api.v1.router import api_router  # noqa: F401 (registers all models)
    from backend.app.core.security import get_password_hash
    from backend.app.db.session import AsyncSessionLocal, engine, init_db
    from backend.app.models.entities import ClassSection, QuestionBankItem, SchoolMembership, Student, User
    from backend.app.modules.differentiated_homework.models import StudentAccountLink
    from backend.app.seed.seed_data import seed_database_if_empty

    await init_db()
    password = secrets.token_urlsafe(12)
    async with AsyncSessionLocal() as session:
        if (await session.execute(select(User.id))).first() is not None:
            _fail("the new demo database is unexpectedly not empty")
        await seed_database_if_empty(session)

        for suffix, class_id, class_name, name, roll, lu, cu, au, ct in EXTRA_STUDENTS:
            overall = round((lu + cu + au + ct) / 4)
            session.add(Student(
                id=f"demo-student-{suffix}", school_id="school-1", class_id=class_id, class_name=class_name,
                name=name, roll_no=roll, lu_score=lu, cu_score=cu, au_score=au, ct_score=ct, overall_score=overall,
                baseline_lu=lu - 8, baseline_cu=cu - 8, baseline_au=au - 8, baseline_ct=ct - 8,
                baseline_overall=overall - 8,
            ))

        # Second student login + explicit identity links (admin-only actions in a real deployment).
        user_id, local_part, name, student_id = SECOND_STUDENT
        session.add(User(id=user_id, email=f"{local_part}@{EMAIL_DOMAIN}", name=name, hashed_password="unset",
                         role="student", school_id="school-1", designation="Student, Grade 8 Section A"))
        session.add(SchoolMembership(id="demo-mem-stud-2", user_id=user_id, school_id="school-1", role="student"))
        await session.flush()
        session.add_all([
            StudentAccountLink(user_id="user-student-1", student_id="user-student-1", created_by="user-admin"),
            StudentAccountLink(user_id=user_id, student_id=student_id, created_by="user-admin"),
        ])

        for subject_id, questions in (("sub-math", QUESTIONS), ("sub-sci", SCIENCE_QUESTIONS)):
            for suffix, qtype, options, answer, rubric, marks, comp, bloom, text in questions:
                session.add(QuestionBankItem(
                    id=f"demo-qb-{suffix}", school_id="school-1", subject_id=subject_id, text=text, type=qtype,
                    options_json=options, correct_answer=answer, marking_rubric=rubric, marks=marks,
                    competency=comp, bloom_level=bloom, is_ai_generated=False, created_by="user-teacher-1",
                ))
        await session.flush()

        # The shared seed stores a nominal student_count (e.g. 32); store the real roster size.
        counts = dict((await session.execute(
            select(Student.class_id, func.count(Student.id)).group_by(Student.class_id))).all())
        for cls in (await session.execute(select(ClassSection))).scalars():
            cls.student_count = counts.get(cls.id, 0)

        hashed = get_password_hash(password)
        for user in (await session.execute(select(User))).scalars():
            user.email = f"{user.email.split('@', 1)[0]}@{EMAIL_DOMAIN}"
            user.hashed_password = hashed
        await session.commit()
        summary = await _verify(session)
    await engine.dispose()

    lines = ["LumenEIOS local demo accounts (synthetic data, this run's database only)",
             f"Password for every account: {password}", ""] + summary
    (run_dir / "credentials.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _verify(session) -> list:
    """Fail loudly if relationships the homework demo depends on are missing; describe the
    accounts for credentials.txt."""
    from sqlalchemy import func, select

    from backend.app.models.entities import ClassSection, ParentStudentLink, QuestionBankItem, SchoolMembership, Student, User
    from backend.app.modules.differentiated_homework.models import StudentAccountLink

    problems, out = [], []
    users = {u.id: u for u in (await session.execute(select(User).order_by(User.role, User.email))).scalars()}
    students = {s.id: s for s in (await session.execute(select(Student))).scalars()}

    teacher = users.get("user-teacher-1")
    classes = (await session.execute(select(ClassSection).filter(ClassSection.school_id == "school-1")
                                     .order_by(ClassSection.name))).scalars().all()
    member = (await session.execute(select(SchoolMembership.id).filter(
        SchoolMembership.user_id == "user-teacher-1", SchoolMembership.school_id == "school-1"))).first()
    if teacher is None or (teacher.school_id != "school-1" and member is None):
        problems.append("teacher account missing or without access to school-1")
    for cls in classes:
        if cls.student_count < 1:
            problems.append(f"{cls.name} has no students")
        if "sub-math" not in (cls.subject_ids_json or []):
            problems.append(f"{cls.name} does not list sub-math")

    student_logins = []
    for link in (await session.execute(select(StudentAccountLink))).scalars():
        user, student = users.get(link.user_id), students.get(link.student_id)
        if user is None or student is None or user.role != "student" or user.school_id != student.school_id:
            problems.append(f"student link {link.user_id} -> {link.student_id} is invalid")
        else:
            student_logins.append((user, student))
    if len(student_logins) < 2:
        problems.append("fewer than two working student logins")

    parent_children = {}
    for link in (await session.execute(select(ParentStudentLink))).scalars():
        if link.student_id not in students:
            problems.append(f"parent link to missing student {link.student_id}")
        else:
            parent_children.setdefault(link.parent_user_id, []).append(students[link.student_id])
    if not parent_children:
        problems.append("no parent is linked to a student")

    bank = dict((await session.execute(
        select(QuestionBankItem.competency, func.count(QuestionBankItem.id))
        .filter(QuestionBankItem.school_id == "school-1", QuestionBankItem.subject_id == "sub-math")
        .group_by(QuestionBankItem.competency))).all())
    for comp in ("LU", "CU", "AU", "CT"):
        if bank.get(comp, 0) < 2:
            problems.append(f"sub-math bank has fewer than 2 {comp} questions")

    if problems:
        _fail("demo seed verification failed: " + "; ".join(problems))

    out.append("HOMEWORK DEMO ACCOUNTS")
    out.append(f"  Teacher  {teacher.email:<44} {teacher.name}")
    out.append("           school-1 classes: " + ", ".join(f"{c.name} ({c.student_count} students)" for c in classes))
    out.append("           question bank: sub-math (LU/CU/AU/CT), sub-sci")
    for user, student in student_logins:
        out.append(f"  Student  {user.email:<44} {student.name}, {student.class_name}, roll {student.roll_no}")
    for parent_id, kids in parent_children.items():
        parent = users.get(parent_id)
        if parent is not None:
            out.append(f"  Parent   {parent.email:<44} {parent.name} -> linked to " + ", ".join(k.name for k in kids))
    out += ["",
            "Demo path: teacher -> 1. Create homework -> Class 8-A -> Aarav Patel (or Ananya Patel) -> sub-math -> Preview.",
            "Any rostered student can receive homework; only the two students above can sign in to answer it.",
            "", "ALL ACCOUNTS"]
    out += [f"  {u.role:<10} {u.email:<45} {u.name} ({u.school_id})" for u in users.values()]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--resume", type=Path, help="restart an existing demo run directory")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-serve", action="store_true", help="create and verify a new run, then exit")
    args = parser.parse_args()

    if args.resume:
        run_dir = _prepare(args.resume, resume=True)
    else:
        run_dir = _prepare(DEMO_ROOT / datetime.now().strftime("run-%Y%m%d-%H%M%S"), resume=False)
        asyncio.run(_seed(run_dir))

    print(f"\nDemo run directory: {run_dir}")
    print(f"Accounts and password: {run_dir / 'credentials.txt'}")
    print("Key accounts: teacher@, student@, ananya.patel@, parent@ - all @" + EMAIL_DOMAIN)
    print(f"Restart later with: --resume \"{run_dir}\"\n")
    if args.no_serve:
        return
    # Import settings only after env is prepared so GEMINI_* overrides apply; model default
    # lives solely in Settings.GEMINI_MODEL (override with the GEMINI_MODEL env var).
    import uvicorn
    from backend.app.core.config import settings
    from backend.app.main import app
    if settings.GEMINI_API_KEY.get_secret_value().strip():  # never print the key itself
        print(f"AI question generation: enabled, model {settings.GEMINI_MODEL}\n")
    else:
        print("AI question generation: disabled (set GEMINI_API_KEY to enable)\n")
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
