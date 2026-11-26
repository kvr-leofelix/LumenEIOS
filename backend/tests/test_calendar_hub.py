"""Unified calendar: role-scoped feed from Academic Config, assessments and homework, plus personal items."""
from datetime import datetime

import pytest
import pytest_asyncio

from backend.app.core.security import create_access_token
from backend.app.models.entities import (
    Assessment, ClassSection, ParentStudentLink, School, SchoolMembership, Student,
    Subject, TeacherAssignment, User,
)
from backend.app.models.teacher_planning import SchoolPlanCalendar, TeacherLostPeriod
from backend.app.modules.differentiated_homework.models import HomeworkAssignmentRecord, StudentAccountLink

SID, OTHER = "cal-school", "cal-other"
CFG = {"year": "2026-2027", "start": "2026-04-01", "end": "2027-03-31", "weekdays": [1, 2, 3, 4, 5], "periodsPerDay": 8,
       "periodMinutes": 40, "subjectPeriodsPerDay": {"Mathematics": 2, "Science": 1}, "horizonDays": None,
       "entries": [
           {"id": "h1", "type": "HOLIDAY", "label": "Winter Festival", "start": "2026-12-25", "end": "2026-12-25"},
           {"id": "v1", "type": "VACATION", "label": "Winter Break", "start": "2026-12-28", "end": "2027-01-02"},
           {"id": "x1", "type": "EXAM", "label": "Half-yearly Exams", "start": "2026-12-07", "end": "2026-12-11"},
           {"id": "e1", "type": "EVENT", "label": "Sports Day", "start": "2026-12-15", "end": "2026-12-15"}]}
OTHER_CFG = {**CFG, "entries": [{"id": "o1", "type": "HOLIDAY", "label": "Other School Holiday", "start": "2026-12-20", "end": "2026-12-20"}]}
RANGE = "?start=2026-12-01&end=2027-01-31"


def hdr(uid, role, school):
    return {"Authorization": f"Bearer {create_access_token(uid, school_id=school, role=role)}", "X-School-Id": school}


def user(uid, role, school, **kw):
    return User(id=uid, email=f"{uid}@x.test", name=kw.pop("name", uid), hashed_password="x", role=role, school_id=school)


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="session")
async def seeded():
    from backend.app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await _seed(db)


@pytest_asyncio.fixture
async def world(client):
    return client


async def _seed(db):
    for sid in (SID, OTHER):
        db.add(School(id=sid, name=f"School {sid}", location="x", state="x", infrastructure_tier="standard"))
    db.add_all([SchoolPlanCalendar(school_id=SID, academic_year="2026-2027", version=1, created_by="t", config={**CFG, "entries": []}),
                SchoolPlanCalendar(school_id=SID, academic_year="2026-2027", version=2, created_by="t", config=CFG),
                SchoolPlanCalendar(school_id=OTHER, academic_year="2026-2027", version=1, created_by="t", config=OTHER_CFG)])
    db.add_all([user("c-teacher", "teacher", SID), user("c-principal", "principal", SID), user("c-student", "student", SID),
                user("c-student2", "student", SID), user("c-parent", "parent", SID), user("c-other-teacher", "teacher", OTHER),
                user("c-admin", "admin", SID)])
    db.add(SchoolMembership(user_id="c-principal", school_id=SID, role="principal"))
    db.add(Subject(id="c-sub", name="Mathematics", code="MATH-C", grade=7))
    db.add(Subject(id="c-sub-eng", name="English", code="ENG-C", grade=7))
    for cid, tid in (("c-class-a", "c-teacher"), ("c-class-b", "c-other-teacher")):
        sid = SID if cid == "c-class-a" else OTHER
        db.add(ClassSection(id=cid, school_id=sid, grade=7, section="A" if cid.endswith("a") else "B", name="Class 7-" + cid[-1].upper(),
                            class_teacher_id=tid, class_teacher_name=tid, student_count=1))
    await db.flush()
    for stid, cid, name in (("c-stu1", "c-class-a", "Asha Test"), ("c-stu2", "c-class-b", "Other Pupil")):
        db.add(Student(id=stid, school_id=SID if cid == "c-class-a" else OTHER, class_id=cid, class_name="Class 7", name=name, roll_no=1))
    await db.flush()
    db.add_all([StudentAccountLink(user_id="c-student", student_id="c-stu1", created_by="c-admin"),
                ParentStudentLink(parent_user_id="c-parent", student_id="c-stu1"),
                TeacherAssignment(school_id=SID, teacher_id="c-teacher", class_id="c-class-a", subject_id="c-sub")])
    db.add_all([Assessment(id="c-as1", school_id=SID, class_id="c-class-a", subject_id="c-sub", title="Unit Test 1", date="2026-12-03", status="scheduled"),
                Assessment(id="c-as-draft", school_id=SID, class_id="c-class-a", subject_id="c-sub", title="Secret Draft", date="2026-12-04", status="draft"),
                # Another teacher's subject in c-teacher's homeroom: the published quiz shows, the draft does not.
                Assessment(id="c-as-eng-draft", school_id=SID, class_id="c-class-a", subject_id="c-sub-eng", title="English Draft", date="2026-12-04", status="draft"),
                Assessment(id="c-as-eng-quiz", school_id=SID, class_id="c-class-a", subject_id="c-sub-eng", title="English Quiz", date="2026-12-06", status="scheduled"),
                Assessment(id="c-as-other", school_id=OTHER, class_id="c-class-b", subject_id="c-sub", title="Other Class Test", date="2026-12-05", status="scheduled")])
    # Lost teaching days come from lost periods recorded in the Time-Aware Engine (the dashboards use the same rows).
    lost = dict(school_id=SID, teacher_id="c-teacher", academic_year="2026-2027", grade=7, subject="Mathematics", recorded_by="c-teacher")
    db.add_all([TeacherLostPeriod(**lost, lost_date="2026-12-09", period_number=1, reason_code="Heavy rain"),
                TeacherLostPeriod(**lost, lost_date="2026-12-09", period_number=2, reason_code="Heavy rain"),
                TeacherLostPeriod(**lost, lost_date="2026-12-10", period_number=1, reason_code="Withdrawn storm", status="withdrawn"),
                # Another teacher's loss in another grade: only leadership sees it.
                TeacherLostPeriod(**{**lost, "teacher_id": "c-other-teacher", "grade": 6}, lost_date="2026-12-14", period_number=1,
                                  reason_code="Grade six trip"),
                HomeworkAssignmentRecord(id="c-hw1", draft_id="c-draft-1", student_id="c-stu1", school_id=SID, subject_id="c-sub",
                                         assigned_by="c-teacher", due_at=datetime(2026, 12, 12, 17, 0)),
                HomeworkAssignmentRecord(id="c-hw2", draft_id="c-draft-2", student_id="c-stu2", school_id=OTHER, subject_id="c-sub",
                                         assigned_by="c-other-teacher", due_at=datetime(2026, 12, 13, 17, 0))])
    await db.commit()


async def feed(client, uid, role, school=SID, qs=RANGE):
    r = await client.get("/api/v1/calendar/events" + qs, headers=hdr(uid, role, school))
    assert r.status_code == 200, r.text
    return r.json()


def titles(data):
    return {e["title"] for e in data["events"]}


@pytest.mark.asyncio
async def test_student_sees_school_calendar_class_tests_and_own_homework(world):
    data = await feed(world, "c-student", "student")
    got = titles(data)
    assert {"Winter Festival", "Winter Break", "Half-yearly Exams", "Sports Day", "Unit Test 1", "Teaching disrupted: Heavy rain"} <= got
    assert "Homework due: Mathematics" in got
    assert "Secret Draft" not in got and "Other Class Test" not in got and "Other School Holiday" not in got
    assert "Teaching disrupted: Withdrawn storm" not in got  # a corrected (withdrawn) loss is not a lost day
    assert "Teaching disrupted: Grade six trip" not in got  # another grade's loss is not this student's
    rain = [e for e in data["events"] if e["title"] == "Teaching disrupted: Heavy rain"]
    assert len(rain) == 1 and rain[0]["category"] == "lost" and rain[0]["detail"].startswith("2 periods lost")
    cats = {e["title"]: e["category"] for e in data["events"]}
    assert cats["Winter Festival"] == "holiday" and cats["Winter Break"] == "vacation" and cats["Half-yearly Exams"] == "exam"
    assert cats["Sports Day"] == "event" and cats["Homework due: Mathematics"] == "deadline" and cats["Unit Test 1"] == "exam"
    vacation = next(e for e in data["events"] if e["title"] == "Winter Break")
    assert (vacation["start"], vacation["end"]) == ("2026-12-28", "2027-01-02")


@pytest.mark.asyncio
async def test_latest_academic_config_version_wins(world):
    # version 1 had no entries; version 2 (current) has them
    assert "Winter Festival" in titles(await feed(world, "c-principal", "principal"))


@pytest.mark.asyncio
async def test_meta_reports_session_days_from_academic_config(world):
    meta = (await feed(world, "c-student", "student", qs="?start=2026-04-01&end=2026-04-30"))["meta"]
    assert meta["session_start"] == "2026-04-01" and meta["session_end"] == "2027-03-31"
    assert meta["working_weekdays"] == [1, 2, 3, 4, 5] and meta["year"] == "2026-2027"
    starts = [e for e in (await feed(world, "c-student", "student", qs="?start=2026-04-01&end=2026-04-30"))["events"] if e["category"] == "session"]
    assert [e["title"] for e in starts] == ["Academic session begins"]


@pytest.mark.asyncio
async def test_parent_sees_child_deadline_labelled_with_the_childs_name(world):
    got = titles(await feed(world, "c-parent", "parent"))
    assert "Homework due: Mathematics (Asha)" in got and "Unit Test 1" in got and "Secret Draft" not in got


@pytest.mark.asyncio
async def test_teacher_sees_own_class_and_assigned_homework_only(world):
    got = titles(await feed(world, "c-teacher", "teacher"))
    assert {"7-A · Unit Test 1", "7-A · Secret Draft", "Homework due: Mathematics"} <= got  # staff see the class name
    assert "Other Class Test" not in got and "Other School Holiday" not in got
    # Their own subject's drafts show; another subject's draft in their homeroom does not, its published quiz does.
    assert "7-A · English Quiz" in got and "7-A · English Draft" not in got
    assert "Teaching disrupted: Heavy rain" in got and "Teaching disrupted: Grade six trip" not in got  # own losses only


@pytest.mark.asyncio
async def test_leadership_calendar_lists_published_assessments_not_drafts(world):
    got = titles(await feed(world, "c-principal", "principal"))
    assert {"7-A · Unit Test 1", "7-A · English Quiz"} <= got
    assert not {"7-A · Secret Draft", "7-A · English Draft"} & got
    assert {"Teaching disrupted: Heavy rain", "Teaching disrupted: Grade six trip"} <= got  # the whole school


@pytest.mark.asyncio
async def test_principal_sees_school_wide_assessments_but_not_other_schools(world):
    got = titles(await feed(world, "c-principal", "principal"))
    assert {"7-A · Unit Test 1", "Winter Festival"} <= got
    assert "Other Class Test" not in got and "Other School Holiday" not in got


@pytest.mark.asyncio
async def test_personal_items_are_private_and_editable(world):
    h = hdr("c-student", "student", SID)
    r = await world.post("/api/v1/calendar/personal", headers=h, json={"title": " Revise fractions ", "kind": "DEADLINE", "start_date": "2026-12-20", "notes": "ch 3"})
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["category"] == "personal" and item["title"] == "Revise fractions" and item["editable"] and item["personal_kind"] == "DEADLINE"
    pid = item["personal_id"]
    assert "Revise fractions" in titles(await feed(world, "c-student", "student"))
    for uid, role in (("c-student2", "student"), ("c-parent", "parent"), ("c-teacher", "teacher"), ("c-principal", "principal")):
        assert "Revise fractions" not in titles(await feed(world, uid, role))
    done = await world.patch(f"/api/v1/calendar/personal/{pid}", headers=h, json={"is_done": True, "title": "Revise ch 3", "end_date": "2026-12-22"})
    assert done.status_code == 200 and done.json()["done"] is True and done.json()["end"] == "2026-12-22"
    assert (await world.patch(f"/api/v1/calendar/personal/{pid}", headers=hdr("c-student2", "student", SID), json={"is_done": False})).status_code == 404
    assert (await world.delete(f"/api/v1/calendar/personal/{pid}", headers=hdr("c-student2", "student", SID))).status_code == 404
    assert (await world.delete(f"/api/v1/calendar/personal/{pid}", headers=h)).status_code == 204
    assert "Revise ch 3" not in titles(await feed(world, "c-student", "student"))


@pytest.mark.asyncio
async def test_personal_validation(world):
    h = hdr("c-teacher", "teacher", SID)
    url = "/api/v1/calendar/personal"
    assert (await world.post(url, headers=h, json={"title": "  ", "start_date": "2026-12-01"})).status_code == 422
    assert (await world.post(url, headers=h, json={"title": "x", "start_date": "not-a-date"})).status_code == 422
    assert (await world.post(url, headers=h, json={"title": "x", "kind": "PARTY", "start_date": "2026-12-01"})).status_code == 422
    assert (await world.post(url, headers=h, json={"title": "x", "start_date": "2026-12-05", "end_date": "2026-12-01"})).status_code == 422


@pytest.mark.asyncio
async def test_range_validation_and_authentication(world):
    h = hdr("c-student", "student", SID)
    assert (await world.get("/api/v1/calendar/events?start=2026-12-10&end=2026-12-01", headers=h)).status_code == 422
    assert (await world.get("/api/v1/calendar/events?start=2026-01-01&end=2028-01-01", headers=h)).status_code == 422
    assert (await world.get("/api/v1/calendar/events" + RANGE)).status_code == 401


@pytest.mark.asyncio
async def test_assistant_gets_the_same_scoped_calendar(world, db_session, monkeypatch):
    import datetime as dt
    from backend.app.services import calendar_hub_service as svc

    class FrozenDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 12, 1)

    monkeypatch.setattr(svc, "date", FrozenDate)
    student = await db_session.get(User, "c-student")
    items = await svc.upcoming_for_assistant(db_session, student, SID, days=30)
    got = {i["title"]: i for i in items}
    assert got["Unit Test 1"]["date"] == "2026-12-03" and got["Unit Test 1"]["type"] == "exam"
    assert got["Winter Break"]["date"] == "2026-12-28 to 2027-01-02" and got["Homework due: Mathematics"]["type"] == "deadline"
    assert "Secret Draft" not in got and "Other Class Test" not in got and "Other School Holiday" not in got
    teacher = await db_session.get(User, "c-teacher")
    assert "7-A · Secret Draft" in {i["title"] for i in await svc.upcoming_for_assistant(db_session, teacher, SID, days=30)}


def test_assistant_highlights_pick_the_next_of_each_kind_and_the_coming_week():
    from datetime import date
    from backend.app.services.calendar_hub_service import assistant_highlights
    items = [
        {"date": "2026-12-03", "type": "exam", "title": "Unit Test 1", "detail": ""},
        {"date": "2026-12-05", "type": "deadline", "title": "Homework due: Mathematics", "detail": ""},
        {"date": "2026-12-12", "type": "deadline", "title": "Homework due: Science", "detail": ""},
        {"date": "2026-12-25", "type": "holiday", "title": "Christmas", "detail": ""},
        {"date": "2026-12-28 to 2027-01-02", "type": "vacation", "title": "Winter Break", "detail": ""},
    ]
    got = assistant_highlights(items, date(2026, 12, 1))
    assert got["next_exam_or_test"] == "Unit Test 1 on 2026-12-03"
    assert got["next_homework_deadline"] == "Homework due: Mathematics on 2026-12-05"
    assert got["next_holiday"] == "Christmas on 2026-12-25" and "next_personal_task" not in got
    assert got["next_vacation"] == "Winter Break on 2026-12-28 to 2027-01-02"
    assert got["next_7_days"] == ["2026-12-03: Unit Test 1 (exam)", "2026-12-05: Homework due: Mathematics (deadline)"]


def test_calendar_questions_are_recognised_and_performance_questions_are_not():
    from backend.app.services.calendar_hub_service import calendar_intent
    assert calendar_intent("When is my next exam?") == "exam"
    assert calendar_intent("Is there a test tomorrow?") == "exam"
    assert calendar_intent("Do I have any homework due this week?") == "deadline"
    assert calendar_intent("When is the next holiday?") == "holiday"
    assert calendar_intent("When is sports day?") == "event"
    assert calendar_intent("What's on this week?") == "week"
    for not_calendar in ("How did I do in the last test?", "What are my marks in the exam?",
                         "Which students need support?", "How do I grade handwritten work?"):
        assert calendar_intent(not_calendar) is None, not_calendar


def test_calendar_answers_name_the_date_and_say_when_nothing_is_scheduled():
    from datetime import date
    from backend.app.services.calendar_hub_service import calendar_answer
    items = [{"date": "2026-11-20", "type": "exam", "title": "Worksheet A", "detail": ""},
             {"date": "2026-11-20", "type": "exam", "title": "Worksheet B", "detail": ""},
             {"date": "2026-11-21", "type": "lost", "title": "Teaching disrupted: Rain", "detail": ""},
             {"date": "2026-11-25", "type": "deadline", "title": "Homework due: Science", "detail": ""},
             {"date": "2026-12-08 to 2026-12-12", "type": "exam", "title": "Periodic Test 2", "detail": ""}]
    today = date(2026, 11, 19)
    exam = calendar_answer("exam", items, today)
    assert "Worksheet A and Worksheet B, on Fri, 20 Nov 2026" in exam and "Periodic Test 2 (Tue, 8 Dec 2026 to Sat, 12 Dec 2026)" in exam
    assert calendar_answer("deadline", items, today) == "Your next homework or deadline: Homework due: Science, on Wed, 25 Nov 2026."
    assert calendar_answer("holiday", items, today).startswith("There is no holiday or vacation on your calendar")
    twice = items + [{"date": "2026-11-25", "type": "deadline", "title": "Homework due: Science", "detail": ""}]
    assert calendar_answer("deadline", twice, today) == "Your next homework or deadline: Homework due: Science (2), on Wed, 25 Nov 2026."
    assert calendar_answer("deadline", items, today, "parent").startswith("Your child's next homework or deadline:")
    week = calendar_answer("week", items, today)
    assert "Worksheet A" in week and "Homework due: Science" in week and "Rain" not in week and "Periodic" not in week
