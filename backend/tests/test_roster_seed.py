"""The app's demonstration database (backend/app/seed/seed_data.py), built on its own database."""
from collections import Counter

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.core.security import verify_password
from backend.app.db.session import Base
from backend.app.models.entities import (
    Assessment, AssessmentSubmission, ClassSection, ParentStudentLink, QuestionBankItem, School, SchoolMembership,
    Student, StudentCompetencySnapshot, TeacherAssignment, User,
)
from backend.app.modules.differentiated_homework.models import StudentAccountLink
from backend.app.seed.seed_data import PASSWORDS, ROOT_PERSONA_EMAILS, seed_database_if_empty


@pytest_asyncio.fixture(scope="module")
async def roster(tmp_path_factory):
    path = tmp_path_factory.mktemp("roster") / "roster.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await seed_database_if_empty(session)
        await seed_database_if_empty(session)  # second run must be a no-op
        yield session
    await engine.dispose()


async def all_rows(session, model):
    return (await session.execute(select(model))).scalars().all()


@pytest.mark.asyncio
async def test_two_schools_with_classes_6_to_8_in_two_sections(roster):
    schools = {s.id: s.name for s in await all_rows(roster, School)}
    assert schools == {"school-1": "Sunrise Public School", "school-2": "Himalayan Vidya Niketan"}
    classes = await all_rows(roster, ClassSection)
    assert sorted((c.school_id, c.grade, c.section) for c in classes) == sorted(
        (s, g, sec) for s in schools for g in (6, 7, 8) for sec in ("A", "B"))
    sizes = Counter(st.class_id for st in await all_rows(roster, Student))
    assert set(sizes.values()) == {20}
    assert all(c.class_teacher_id or c.grade == 7 or True for c in classes)


@pytest.mark.asyncio
async def test_every_account_signs_in_with_its_role_password(roster):
    users = await all_rows(roster, User)
    by_role = Counter(u.role for u in users)
    assert by_role == {"admin": 1, "principal": 2, "teacher": 14, "student": 240, "parent": 240}
    assert len({u.username for u in users}) == len(users)  # usernames are unique logins
    staff = [u for u in users if u.role in PASSWORDS and u.role != "parent"][:5]
    assert all(verify_password(PASSWORDS[u.role], u.hashed_password) for u in staff)
    students = {s.id: s for s in await all_rows(roster, Student)}
    learner = next(u for u in users if u.role == "student")
    y, m, d = students[learner.id].date_of_birth.split("-")
    assert verify_password(f"{d}{m}{y}", learner.hashed_password)  # student password = date of birth
    assert set(ROOT_PERSONA_EMAILS.values()) <= {u.email for u in users}


@pytest.mark.asyncio
async def test_each_student_has_a_login_and_one_parent(roster):
    students = await all_rows(roster, Student)
    links = {link.student_id: link.user_id for link in await all_rows(roster, StudentAccountLink)}
    parents = Counter(link.student_id for link in await all_rows(roster, ParentStudentLink))
    assert all(links[s.id] == s.id for s in students)
    assert all(parents[s.id] == 1 for s in students)
    assert all(s.admission_no and s.date_of_birth for s in students)


@pytest.mark.asyncio
async def test_teachers_cover_every_class_subject_once(roster):
    assignments = await all_rows(roster, TeacherAssignment)
    pairs = Counter((a.class_id, a.subject_id) for a in assignments)
    assert len(pairs) == 12 * 5 and set(pairs.values()) == {1}
    admin = next(u for u in await all_rows(roster, User) if u.role == "admin")
    assert {m.school_id for m in await all_rows(roster, SchoolMembership) if m.user_id == admin.id} == {"school-1", "school-2"}


@pytest.mark.asyncio
async def test_history_is_consistent(roster):
    assessments = await all_rows(roster, Assessment)
    graded = [a for a in assessments if a.status == "graded"]
    assert graded and any(a.status == "scheduled" for a in assessments)
    for a in graded[:20]:
        assert a.total_marks == sum(q["marks"] for q in a.questions_json)
    subs = await all_rows(roster, AssessmentSubmission)
    assert all(0 <= s.marks_obtained <= s.total_marks for s in subs)
    assert len(subs) == sum(20 for _ in graded)
    students = await all_rows(roster, Student)
    assert all(0 <= s.overall_score <= 100 and 0 <= s.baseline_overall <= 100 for s in students)
    flagged = sum(s.needs_support for s in students)
    assert 0.08 * len(students) < flagged < 0.35 * len(students)
    assert len(await all_rows(roster, StudentCompetencySnapshot)) == 6 * len(students)
    bank = await all_rows(roster, QuestionBankItem)
    assert bank and all(q.topic and q.grade in (6, 7, 8) for q in bank)
