"""Step 4: lost periods and lost days live only in teacher_lost_periods."""
import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.app.core.security import create_access_token
from backend.app.models.entities import School, User
from backend.app.models.planning_workspace import PlanningWorkspaceRevision
from backend.app.models.teacher_planning import PlanAuditEvent, SchoolPlanCalendar, TeacherLostPeriod
from backend.app.seed.teacher_plan_demo import seed_teacher_plan_demo
from backend.app.services.teacher_plan_service import DEFAULT_CALENDAR, ensure_defaults
from backend.app.services.workspace_import import import_workspace_losses
from backend.tests.test_planning_workspace import empty_state


def hdr(uid, role, school):
    return {"Authorization": f"Bearer {create_access_token(uid, school_id=school, role=role)}", "X-School-Id": school}


T1 = ("user-teacher-1", "teacher", "school-1")
T2 = ("user-teacher-2", "teacher", "school-1")
T3 = ("user-teacher-3", "teacher", "school-3")
P1, A1 = ("user-principal-1", "principal", "school-1"), ("user-admin", "admin", "school-1")
SCI = {"grade": 8, "subject": "Science"}  # Science has 1 period/day, Mathematics 2 in the demo calendars
MATH = {"grade": 7, "subject": "Mathematics"}
BASE = "/api/v1/teacher-plans"


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="session")
async def seeded():
    from backend.app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        await seed_teacher_plan_demo(s)


async def overview(client, who, teacher, **kw):
    r = await client.get(f"{BASE}/{teacher}/lost-periods", params={**MATH, "today": "2026-12-31", **kw}, headers=hdr(*who))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_counting_rules_batch_and_distinct_days(client):
    url = f"{BASE}/user-teacher-2/lost-periods"
    r = await client.post(f"{url}/batch", json={**MATH, "entries": [{"date": "2026-09-01", "periods": [1, 2]}, {"date": "2026-09-02", "periods": [2]}],
                                               "reason_code": "Health Drive", "notes": "camp"}, headers=hdr(*T2))
    assert r.status_code == 201, r.text
    batch = r.json()["batch_id"]
    assert len(r.json()["records"]) == 3 and {x["batch_id"] for x in r.json()["records"]} == {batch}
    o = await overview(client, T2, "user-teacher-2")
    assert o["lost_days"] == 2 and o["lost_periods"] == 3  # one date with two periods is one day
    days = [e for e in (await client.get("/api/v1/plan-logs", params={"category": "lost_day", "teacher_id": "user-teacher-2"}, headers=hdr(*P1))).json()["items"] if e["new_value"] == {"date": "2026-09-01"}]
    periods = [e for e in (await client.get("/api/v1/plan-logs", params={"category": "lost_period", "teacher_id": "user-teacher-2"}, headers=hdr(*P1))).json()["items"] if e["new_value"] and e["new_value"].get("date") == "2026-09-01"]
    assert days and periods and days[0]["related_event_id"] == periods[0]["id"]  # the lost-day event points at the lost-period event
    # the same period cannot be recorded twice
    dup = await client.post(url, json={**MATH, "date": "2026-09-01", "periods": [1], "reason_code": "Other"}, headers=hdr(*T2))
    assert dup.status_code == 409
    assert (await overview(client, T2, "user-teacher-2"))["lost_periods"] == 3
    # another teacher (same school/class/subject) is unaffected
    other = await overview(client, ("user-teacher-1", "teacher", "school-1"), "user-teacher-1")
    assert all(rec["date"] not in ("2026-09-01", "2026-09-02") for rec in other["records"])


@pytest.mark.asyncio
async def test_batch_is_atomic_and_validates_against_the_calendar(client):
    url = f"{BASE}/user-teacher-2/lost-periods/batch"
    before = (await overview(client, T2, "user-teacher-2"))["lost_periods"]
    bad_entries = [
        [{"date": "2026-09-08", "periods": [1]}, {"date": "2026-09-09", "periods": [3]}],  # period 3 not timetabled (2/day)
        [{"date": "2026-09-08", "periods": [1]}, {"date": "2026-09-06", "periods": [1]}],  # 2026-09-06 is a Sunday
        [{"date": "2026-09-08", "periods": [1]}, {"date": "2026-09-08", "periods": [1]}],  # same period twice
        [{"date": "not-a-date", "periods": [1]}],
        [{"date": "2026-09-08", "periods": []}],
    ]
    for entries in bad_entries:
        r = await client.post(url, json={**MATH, "entries": entries, "reason_code": "Other"}, headers=hdr(*T2))
        assert r.status_code == 422, (entries, r.text)
    assert (await client.post(url, json={**MATH, "entries": [{"date": "2026-09-08", "periods": [1]}], "reason_code": "Bogus"}, headers=hdr(*T2))).status_code == 422
    assert (await client.post(url, json={**MATH, "entries": [{"date": "2026-10-21", "periods": [1]}], "reason_code": "Other"}, headers=hdr(*T2))).status_code == 422  # autumn break
    after = await overview(client, T2, "user-teacher-2")
    assert after["lost_periods"] == before  # nothing from any rejected batch leaked in
    assert not any(r["date"] in ("2026-09-08", "2026-09-09", "2026-09-06") for r in after["records"])


@pytest.mark.asyncio
async def test_holiday_is_not_an_instructional_day(client):
    # school-1 demo calendar has an autumn break 2026-10-19..23
    r = await client.post(f"{BASE}/user-teacher-2/lost-periods", json={**MATH, "date": "2026-10-20", "periods": [1], "reason_code": "Other"}, headers=hdr(*T2))
    assert r.status_code == 422 and "not an instructional day" in r.text


@pytest.mark.asyncio
async def test_withdraw_reactivate_and_audit_history(client):
    url = f"{BASE}/user-teacher-2/lost-periods"
    await client.post(url, json={**MATH, "date": "2026-09-15", "periods": [1, 2], "reason_code": "Local Festival"}, headers=hdr(*T2))
    assert (await client.post(f"{url}/withdraw", json={**MATH, "date": "2026-09-15", "periods": [2], "reason": "no"}, headers=hdr(*T2))).status_code == 422  # reason too short
    w = await client.post(f"{url}/withdraw", json={**MATH, "date": "2026-09-15", "periods": [2], "reason": "Period 2 was taught after all"}, headers=hdr(*T2))
    assert w.status_code == 200 and w.json()["lost_day_remains"] is True
    o = await overview(client, T2, "user-teacher-2")
    day = [r for r in o["records"] if r["date"] == "2026-09-15"]
    assert sorted((r["period"], r["status"]) for r in day) == [(1, "active"), (2, "withdrawn")]  # the row is kept
    again = await client.post(f"{url}/withdraw", json={**MATH, "date": "2026-09-15", "periods": [2], "reason": "Period 2 was taught after all"}, headers=hdr(*T2))
    assert again.status_code == 404  # already withdrawn
    assert (await client.post(url, json={**MATH, "date": "2026-09-15", "periods": [2], "reason_code": "Other"}, headers=hdr(*T2))).status_code == 201  # lost again
    day = [r for r in (await overview(client, T2, "user-teacher-2"))["records"] if r["date"] == "2026-09-15"]
    assert [r["status"] for r in sorted(day, key=lambda r: r["period"])] == ["active", "active"] and len(day) == 2  # same rows, no duplicates
    ev = (await client.get("/api/v1/plan-logs", params={"category": "lost_period", "teacher_id": "user-teacher-2"}, headers=hdr(*P1))).json()["items"]
    withdrawn = [e for e in ev if e["status"] == "withdrawn"]
    assert withdrawn and withdrawn[0]["reason"] == "Period 2 was taught after all" and withdrawn[0]["previous_value"]["status"] == "active"


@pytest.mark.asyncio
async def test_withdraw_whole_day_withdraws_the_lost_day_and_approved_rows_are_immutable(client, db_session):
    url = f"{BASE}/user-teacher-2/lost-periods"
    await client.post(url, json={**SCI, "date": "2026-09-16", "periods": [1], "reason_code": "Other"}, headers=hdr(*T2))
    w = await client.post(f"{url}/withdraw", json={**SCI, "date": "2026-09-16", "periods": [1], "reason": "Recorded by mistake"}, headers=hdr(*T2))
    assert w.json()["lost_day_remains"] is False
    cats = [(e["category"], e["status"]) for e in (await client.get("/api/v1/plan-logs", params={"teacher_id": "user-teacher-2", "subject": "Science"}, headers=hdr(*P1))).json()["items"]]
    assert ("lost_day", "withdrawn") in cats
    # a row linked to an approved schedule version cannot be withdrawn
    await client.post(url, json={**SCI, "date": "2026-09-17", "periods": [1], "reason_code": "Other"}, headers=hdr(*T2))
    row = (await db_session.execute(select(TeacherLostPeriod).filter_by(teacher_id="user-teacher-2", lost_date="2026-09-17"))).scalars().first()
    row.schedule_version = 2
    await db_session.commit()
    r = await client.post(f"{url}/withdraw", json={**SCI, "date": "2026-09-17", "periods": [1], "reason": "Changed my mind"}, headers=hdr(*T2))
    assert r.status_code == 409 and "approved recovery" in r.text


@pytest.mark.asyncio
async def test_ownership_roles_isolation_and_all_endpoint(client):
    body = {**MATH, "date": "2026-09-22", "periods": [1], "reason_code": "Other"}
    for who in (P1, A1, T1, T3):
        assert (await client.post(f"{BASE}/user-teacher-2/lost-periods", json=body, headers=hdr(*who))).status_code == 403
        assert (await client.post(f"{BASE}/user-teacher-2/lost-periods/batch", json={**MATH, "entries": [{"date": "2026-09-22", "periods": [1]}], "reason_code": "Other"}, headers=hdr(*who))).status_code == 403
        assert (await client.post(f"{BASE}/user-teacher-2/lost-periods/withdraw", json={**MATH, "date": "2026-09-01", "periods": [1], "reason": "not mine"}, headers=hdr(*who))).status_code == 403
    allr = await client.get(f"{BASE}/user-teacher-2/lost-periods/all", headers=hdr(*P1))
    assert allr.status_code == 200 and all(i["recorded_by"] in ("user-teacher-2",) for i in allr.json()["items"])
    assert (await client.get(f"{BASE}/user-teacher-2/lost-periods/all", headers=hdr(*T1))).status_code == 403
    assert (await client.get(f"{BASE}/user-teacher-2/lost-periods/all", headers=hdr("user-principal-1", "principal", "school-3"))).status_code == 403
    # school 3's teacher has independent data
    s3 = await client.get(f"{BASE}/user-teacher-3/lost-periods/all", headers=hdr(*T3))
    assert s3.status_code == 200 and all(i["date"] != "2026-09-01" for i in s3.json()["items"])


@pytest.mark.asyncio
async def test_planning_oversight_counts_come_from_the_same_rows(client):
    o = await overview(client, T2, "user-teacher-2")
    rows = (await client.get("/api/v1/plan-oversight/planning", headers=hdr(*P1))).json()["rows"]
    mine = next(r for r in rows if r["teacher_id"] == "user-teacher-2" and r["subject"] == "Mathematics")
    assert (mine["lost_days"], mine["lost_periods"]) == (o["lost_days"], o["lost_periods"])


# ------------------------------------------------------------------ import
def ws_loss(rid, date, periods, by="x", role="teacher", supersedes=None, reason="Health Drive"):
    return {"id": rid, "date": date, "periodsLost": len(periods or []), "periods": periods, "reason": reason, "note": "n",
            "recordedBy": {"id": by, "name": by, "role": role}, "recordedAt": "2026-09-10T09:00:00Z", "supersedes": supersedes}


async def school_with(db, sid, teachers=1):
    db.add(School(id=sid, name=sid, location="x", state="x", infrastructure_tier="standard"))
    db.add(SchoolPlanCalendar(school_id=sid, academic_year="2026-2027", version=1, created_by="test",
                              config={**DEFAULT_CALENDAR, "subjectPeriodsPerDay": {"Mathematics": 2, "Science": 1}}))
    users = []
    for i in range(teachers):
        u = User(id=f"{sid}-t{i}", email=f"{sid}-t{i}@x.test", name="T", hashed_password="x", role="teacher", school_id=sid)
        db.add(u)
        users.append(u)
    await db.flush()
    for u in users:
        await ensure_defaults(db, u, sid, u.id, "2026-2027", 7, "Mathematics")
    return users


async def workspace(db, sid, plans):
    s = empty_state()
    s["plans"] = plans
    db.add(PlanningWorkspaceRevision(school_id=sid, revision=1, action="LOSS_RECORD", summary="legacy", actor_id="x", actor_name="x", actor_role="teacher", state=s))
    await db.commit()


@pytest.mark.asyncio
async def test_import_preserves_data_reports_gaps_and_is_idempotent(db_session):
    users = await school_with(db_session, "school-l1")
    t = users[0].id
    await workspace(db_session, "school-l1", [{"id": "p", "grade": 7, "subject": "Mathematics", "losses": [
        ws_loss("a", "2026-09-01", [1, 2], by=t),
        ws_loss("b", "2026-09-02", [1], by=t),
        ws_loss("b2", "2026-09-02", [], by=t, supersedes="b"),      # withdraws b -> b itself is superseded history
        ws_loss("c", "2026-09-03", None, by=t),                      # legacy: no explicit periods
        ws_loss("d", "2026-09-06", [1], by=t),                       # a Sunday: not an instructional day
        ws_loss("e", "2026-09-04", [9], by=t),                       # period not timetabled
    ]}])
    rep = await import_workspace_losses(db_session, "school-l1")
    assert rep["imported"] == ["a"] and rep["superseded_ignored"] == 2
    assert [i["record"] for i in rep["incomplete"]] == ["c"] and {i["record"] for i in rep["invalid"]} == {"d", "e"}
    rows = (await db_session.execute(select(TeacherLostPeriod).filter_by(school_id="school-l1"))).scalars().all()
    assert sorted((r.lost_date, r.period_number, r.reason_code, r.notes, r.recorded_by, r.topic_keys) for r in rows) == [
        ("2026-09-01", 1, "Health Drive", "n", t, []), ("2026-09-01", 2, "Health Drive", "n", t, [])]  # nothing invented
    assert rows[0].created_at.year == 2026 and rows[0].created_at.month == 9  # original timestamp kept
    ev = (await db_session.execute(select(PlanAuditEvent).filter_by(school_id="school-l1", category="lost_period"))).scalars().all()
    assert len(ev) == 1 and "Imported once" in ev[0].reason
    again = await import_workspace_losses(db_session, "school-l1")
    assert again["imported"] == [] and again["skipped_existing"] == ["a"]
    assert len((await db_session.execute(select(TeacherLostPeriod).filter_by(school_id="school-l1"))).scalars().all()) == 2


@pytest.mark.asyncio
async def test_import_never_guesses_owner(db_session):
    await school_with(db_session, "school-l2", teachers=2)
    await workspace(db_session, "school-l2", [{"id": "p", "grade": 7, "subject": "Mathematics", "losses": [
        ws_loss("a", "2026-09-01", [1], by="school-l2-principal", role="principal"),   # recorder holds no plan, two holders
        ws_loss("b", "2026-09-02", [1], by="school-l2-t1", role="teacher"),            # recorder is one of the holders: unambiguous
    ]}])
    rep = await import_workspace_losses(db_session, "school-l2")
    assert rep["imported"] == ["b"] and rep["ambiguous"][0]["record"] == "a" and len(rep["ambiguous"][0]["teachers"]) == 2
    rows = (await db_session.execute(select(TeacherLostPeriod).filter_by(school_id="school-l2"))).scalars().all()
    assert [(r.teacher_id, r.lost_date) for r in rows] == [("school-l2-t1", "2026-09-02")]


@pytest.mark.asyncio
async def test_dashboard_lost_days_match_the_recorded_lost_periods(client):
    """The principal/management dashboards read lost days from /workspace; they must count exactly the dates with an
    active lost period (the Time-Aware Engine's rule), not a separate disruption register."""
    from backend.app.db.session import AsyncSessionLocal
    url = f"{BASE}/user-teacher-2/lost-periods/batch"
    r = await client.post(url, json={**MATH, "entries": [{"date": "2026-11-24", "periods": [1, 2]}], "reason_code": "Election Duties"},
                          headers=hdr(*T2))
    assert r.status_code == 201, r.text
    async with AsyncSessionLocal() as s:
        dates = set((await s.execute(select(TeacherLostPeriod.lost_date).filter_by(school_id="school-1", status="active"))).scalars().all())
    ws = await client.get("/api/v1/workspace", headers=hdr(*P1))
    assert ws.status_code == 200, ws.text
    lost = [d for d in ws.json()["disruptions"] if d["schoolId"] == "school-1"]
    assert {d["date"] for d in lost} == dates and all(d["daysLost"] == 1 for d in lost)
    day = next(d for d in lost if d["date"] == "2026-11-24")
    assert day["reason"] == "Election Duties" and day["notes"].startswith("2 periods lost")
