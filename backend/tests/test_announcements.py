"""Announcements: audience limits, notifications, calendar marking, and no write-through to Academic Config."""
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from backend.app.core.security import create_access_token
from backend.app.models.entities import (
    ClassSection, InstructionalDisruption, Notification, ParentStudentLink, School, Student, Subject, TeacherAssignment, User,
)
from backend.app.models.teacher_planning import SchoolPlanCalendar
from backend.app.modules.differentiated_homework.models import StudentAccountLink

SID, OTHER = "an-school", "an-other"
SOON = (date.today() + timedelta(days=5)).isoformat()


def hdr(uid, role, school=SID):
    return {"Authorization": f"Bearer {create_access_token(uid, school_id=school, role=role)}", "X-School-Id": school}


def mk(uid, role, school=SID):
    return User(id=uid, email=f"{uid}@x.test", name=uid, hashed_password="x", role=role, school_id=school)


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="session")
async def seeded():
    from backend.app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        for sid in (SID, OTHER):
            db.add(School(id=sid, name=sid, location="x", state="x", infrastructure_tier="standard"))
        db.add_all([mk("an-t1", "teacher"), mk("an-t2", "teacher"), mk("an-pr", "principal"), mk("an-s1", "student"),
                    mk("an-s2", "student"), mk("an-p1", "parent"), mk("an-p2", "parent"), mk("an-ot", "teacher", OTHER),
                    mk("an-opr", "principal", OTHER)])
        db.add(Subject(id="an-sub", name="Maths", code="MATH-AN", grade=7))
        for cid, sec, tid in (("an-ca", "A", "an-t1"), ("an-cb", "B", "an-t2")):
            db.add(ClassSection(id=cid, school_id=SID, grade=7, section=sec, name=f"Class 7-{sec}", class_teacher_id=tid,
                                class_teacher_name=tid, student_count=1))
        await db.flush()
        for stid, cid in (("an-st1", "an-ca"), ("an-st2", "an-cb")):
            db.add(Student(id=stid, school_id=SID, class_id=cid, class_name="Class 7", name=stid, roll_no=1))
        await db.flush()
        db.add_all([StudentAccountLink(user_id="an-s1", student_id="an-st1", created_by="x"),
                    StudentAccountLink(user_id="an-s2", student_id="an-st2", created_by="x"),
                    ParentStudentLink(parent_user_id="an-p1", student_id="an-st1"),
                    ParentStudentLink(parent_user_id="an-p2", student_id="an-st2"),
                    TeacherAssignment(school_id=SID, teacher_id="an-t1", class_id="an-ca", subject_id="an-sub")])
        await db.commit()


async def notes(uid):
    from backend.app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        return list((await db.scalars(select(Notification).where(Notification.user_id == uid, Notification.type == "announcement"))).all())


async def titles(client, uid, role, school=SID):
    r = await client.get("/api/v1/announcements", headers=hdr(uid, role, school))
    assert r.status_code == 200, r.text
    return {a["title"] for a in r.json()}


@pytest.mark.asyncio(loop_scope="session")
async def test_principal_broadcast_reaches_chosen_groups_only(client):
    r = await client.post("/api/v1/announcements", headers=hdr("an-pr", "principal"),
                          json={"title": "Staff and parents", "content": "Hello", "audience": ["teacher", "parent"]})
    assert r.status_code == 200, r.text
    assert r.json()["recipients"] == 4  # t1, t2, p1, p2
    assert "Staff and parents" in await titles(client, "an-t1", "teacher")
    assert "Staff and parents" in await titles(client, "an-p2", "parent")
    assert "Staff and parents" not in await titles(client, "an-s1", "student")
    assert "Staff and parents" not in await titles(client, "an-ot", "teacher", OTHER)
    assert len(await notes("an-p1")) == 1 and not await notes("an-s1")


@pytest.mark.asyncio(loop_scope="session")
async def test_teacher_is_limited_to_own_classes(client):
    h = hdr("an-t1", "teacher")
    r = await client.post("/api/v1/announcements", headers=h, json={"title": "Class A note", "content": "x", "audience": ["student", "parent"]})
    assert r.status_code == 200 and r.json()["class_ids"] == ["an-ca"]
    assert "Class A note" in await titles(client, "an-s1", "student")
    assert "Class A note" in await titles(client, "an-p1", "parent")
    assert "Class A note" not in await titles(client, "an-s2", "student")
    assert "Class A note" not in await titles(client, "an-p2", "parent")
    bad = await client.post("/api/v1/announcements", headers=h, json={"title": "No", "content": "x", "audience": ["student"], "class_ids": ["an-cb"]})
    assert bad.status_code == 403
    ok = await client.post("/api/v1/announcements", headers=hdr("an-t2", "teacher"), json={"title": "Staff only", "content": "x", "audience": ["teacher"]})
    assert ok.status_code == 200 and ok.json()["class_ids"] is None
    assert "Staff only" in await titles(client, "an-t1", "teacher")


@pytest.mark.asyncio(loop_scope="session")
async def test_learners_cannot_send(client):
    r = await client.post("/api/v1/announcements", headers=hdr("an-s1", "student"), json={"title": "x", "content": "x", "audience": ["teacher"]})
    assert r.status_code == 403
    r = await client.post("/api/v1/announcements", headers=hdr("an-pr", "principal"), json={"title": "x", "content": "x", "audience": []})
    assert r.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
async def test_event_shows_on_calendar_for_audience_and_leaves_academic_config_alone(client):
    from backend.app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        before = (await db.scalar(select(func.count()).select_from(SchoolPlanCalendar)),
                  await db.scalar(select(func.count()).select_from(InstructionalDisruption)))
    r = await client.post("/api/v1/announcements", headers=hdr("an-pr", "principal"),
                          json={"title": "Annual Day", "content": "Please attend", "audience": ["student", "parent"],
                                "event_start": SOON})
    assert r.status_code == 200 and r.json()["event_start"] == SOON
    rng = f"?start={SOON}&end={SOON}"
    for uid, role in (("an-s1", "student"), ("an-p2", "parent"), ("an-pr", "principal")):
        events = (await client.get(f"/api/v1/calendar/events{rng}", headers=hdr(uid, role))).json()["events"]
        assert any(e["category"] == "announcement" and e["title"] == "Annual Day" for e in events), uid
    events = (await client.get(f"/api/v1/calendar/events{rng}", headers=hdr("an-t1", "teacher"))).json()["events"]
    assert not any(e["title"] == "Annual Day" for e in events)
    async with AsyncSessionLocal() as db:
        after = (await db.scalar(select(func.count()).select_from(SchoolPlanCalendar)),
                 await db.scalar(select(func.count()).select_from(InstructionalDisruption)))
    assert before == after


@pytest.mark.asyncio(loop_scope="session")
async def test_event_date_validation(client):
    h = hdr("an-pr", "principal")
    past = (date.today() - timedelta(days=10)).isoformat()
    base = {"title": "E", "content": "x", "audience": ["teacher"]}
    assert (await client.post("/api/v1/announcements", headers=h, json={**base, "event_start": past})).status_code == 422
    assert (await client.post("/api/v1/announcements", headers=h, json={**base, "event_start": SOON, "event_end": past})).status_code == 422
    assert (await client.post("/api/v1/announcements", headers=h, json={**base, "event_end": SOON})).status_code == 422


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_removes_event_and_notifications(client):
    r = await client.post("/api/v1/announcements", headers=hdr("an-t1", "teacher"),
                          json={"title": "Field trip", "content": "x", "audience": ["student"], "event_start": SOON})
    ann_id = r.json()["id"]
    assert [n for n in await notes("an-s1") if n.title == "Field trip"]
    assert (await client.delete(f"/api/v1/announcements/{ann_id}", headers=hdr("an-t2", "teacher"))).status_code == 404
    assert (await client.delete(f"/api/v1/announcements/{ann_id}", headers=hdr("an-opr", "principal", OTHER))).status_code == 404
    assert (await client.delete(f"/api/v1/announcements/{ann_id}", headers=hdr("an-t1", "teacher"))).status_code == 204
    assert "Field trip" not in await titles(client, "an-s1", "student")
    assert not [n for n in await notes("an-s1") if n.title == "Field trip"]


@pytest.mark.asyncio(loop_scope="session")
async def test_options_for_teacher_and_principal(client):
    t = (await client.get("/api/v1/announcements/options", headers=hdr("an-t1", "teacher"))).json()
    assert [c["id"] for c in t["classes"]] == ["an-ca"]
    p = (await client.get("/api/v1/announcements/options", headers=hdr("an-pr", "principal"))).json()
    assert {c["id"] for c in p["classes"]} == {"an-ca", "an-cb"}
