"""Step 6: calendar versions, recalculation previews and teacher-facing impact. Figures below are worked out by hand."""
import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.app.core.security import create_access_token
from backend.app.models.entities import School, SchoolMembership, User
from backend.app.models.planning_workspace import PlanningWorkspaceRevision
from backend.app.models.teacher_planning import PlanAuditEvent, SchoolPlanCalendar, TeacherTopicConfig
from backend.app.seed.teacher_plan_demo import seed_teacher_plan_demo
from backend.app.services.calendar_service import validate_config
from backend.app.services.teacher_plan_service import ensure_defaults
from backend.app.services.workspace_import import import_workspace_calendar
from backend.tests.test_planning_workspace import empty_state

# Mon 2026-12-14 .. Fri 2027-01-08 = 20 weekdays (no weekends counted)
BASE = {"year": "2026-2027", "start": "2026-12-14", "end": "2027-01-08", "weekdays": [1, 2, 3, 4, 5], "entries": [], "periodsPerDay": 8, "periodMinutes": 40,
        "subjectPeriodsPerDay": {"Mathematics": 2, "Science": 1}, "horizonDays": None}
HOLIDAY = {"id": "h1", "type": "HOLIDAY", "label": "Winter break day", "start": "2026-12-25", "end": "2026-12-25"}  # a Friday
MATH = {"grade": 7, "subject": "Mathematics"}
BASE_URL = "/api/v1/plan-calendar"


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="session")
async def seeded():
    from backend.app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        await seed_teacher_plan_demo(s)


def hdr(uid, role, school):
    return {"Authorization": f"Bearer {create_access_token(uid, school_id=school, role=role)}", "X-School-Id": school}


async def make_school(db, sid, teachers=2):
    db.add(School(id=sid, name=sid, location="x", state="x", infrastructure_tier="standard"))
    db.add(SchoolPlanCalendar(school_id=sid, academic_year="2026-2027", version=1, created_by="test", config=BASE, reason="initial"))
    ts = []
    for i in range(teachers):
        u = User(id=f"{sid}-t{i}", email=f"{sid}-t{i}@x.test", name=f"Teacher {i}", hashed_password="x", role="teacher", school_id=sid)
        db.add(u)
        ts.append(u)
    pr = User(id=f"{sid}-p", email=f"{sid}-p@x.test", name="Principal", hashed_password="x", role="principal", school_id=sid)
    db.add(pr)
    db.add(SchoolMembership(user_id=pr.id, school_id=sid, role="principal"))
    await db.flush()
    for u in ts:
        await ensure_defaults(db, u, sid, u.id, "2026-2027", 7, "Mathematics")
    await db.commit()
    return [u.id for u in ts], pr.id


@pytest_asyncio.fixture
async def cal(client, db_session, request):
    sid = f"school-c{abs(hash(request.node.name)) % 10**7}"
    (t0, t1), pr = await make_school(db_session, sid)

    class C:
        pass
    c = C()
    c.c, c.sid, c.t0, c.t1, c.pr = client, sid, t0, t1, pr
    c.h = lambda who: hdr(who, "principal" if who == pr else "teacher", sid)
    return c


def cap(p):
    r = -(-p // 10)
    return {"available_periods": p, "reserved_periods": r, "topic_capacity": p - r}


def test_config_validation_matches_the_planner_rules():
    assert validate_config(BASE) == []
    bad = [
        ({**BASE, "year": "2026-2028"}, "consecutive"),
        ({**BASE, "end": "2026-12-01"}, "after"),
        ({**BASE, "end": "2028-01-08"}, "start in 2026 and end in 2027"),
        ({**BASE, "weekdays": []}, "working weekday"),
        ({**BASE, "weekdays": [1, 9]}, "working weekday"),
        ({**BASE, "periodsPerDay": 0}, "1 to 12"),
        ({**BASE, "periodMinutes": 5}, "10 to 180"),
        ({**BASE, "subjectPeriodsPerDay": {"Mathematics": 5, "Science": 4}}, "exceed"),
        ({**BASE, "subjectPeriodsPerDay": {"Mathematics": -1, "Science": 1}}, "0 or more"),
        ({**BASE, "entries": [{**HOLIDAY, "label": " "}]}, "needs a description"),
        ({**BASE, "entries": [{**HOLIDAY, "start": "2025-01-01", "end": "2025-01-01"}]}, "outside"),
        ({**BASE, "entries": [HOLIDAY, {**HOLIDAY, "id": "h2", "label": "Overlap"}]}, "Conflict"),
        ({**BASE, "entries": [{**HOLIDAY, "type": "PARTY"}]}, "unknown type"),
        ({**BASE, "horizonDays": 0}, "horizon"),
    ]
    for cfg, needle in bad:
        assert any(needle in e for e in validate_config(cfg)), (needle, validate_config(cfg))


@pytest.mark.asyncio
async def test_preview_math_reserve_and_eligible_days(cal):
    # 20 weekdays x 2 Maths periods = 40 -> R = ceil(4.0) = 4 -> T = 36
    r = await cal.c.post(f"{BASE_URL}/preview", json={"config": BASE}, headers=cal.h(cal.pr))
    assert r.status_code == 200
    assert r.json()["capacity_before"]["Mathematics"] == cap(40) == {"available_periods": 40, "reserved_periods": 4, "topic_capacity": 36}
    assert r.json()["unchanged"] is True and r.json()["current_version"] == 1 and r.json()["proposed_version"] == 2
    # one holiday: 19 days x 2 = 38 -> R = ceil(3.8) = 4 -> T = 34 (the reserve rounds UP)
    r = await cal.c.post(f"{BASE_URL}/preview", json={"config": {**BASE, "entries": [HOLIDAY]}}, headers=cal.h(cal.pr))
    assert r.json()["capacity_after"]["Mathematics"] == {"available_periods": 38, "reserved_periods": 4, "topic_capacity": 34}
    # timetable change: 1 Maths period a day -> 20 -> R = 2 -> T = 18; Science untouched at 20 / 2 / 18
    r = await cal.c.post(f"{BASE_URL}/preview", json={"config": {**BASE, "subjectPeriodsPerDay": {"Mathematics": 1, "Science": 1}}}, headers=cal.h(cal.pr))
    assert r.json()["capacity_after"]["Mathematics"] == {"available_periods": 20, "reserved_periods": 2, "topic_capacity": 18}
    assert r.json()["capacity_after"]["Science"] == {"available_periods": 20, "reserved_periods": 2, "topic_capacity": 18}
    # a non-teaching weekday set: only Mon-Wed -> 12 days x 2 = 24 -> R = 3 -> T = 21
    r = await cal.c.post(f"{BASE_URL}/preview", json={"config": {**BASE, "weekdays": [1, 2, 3]}}, headers=cal.h(cal.pr))
    assert r.json()["capacity_after"]["Mathematics"]["topic_capacity"] == 21
    # The display horizon never truncates annual capacity.
    r = await cal.c.post(f"{BASE_URL}/preview", json={"config": {**BASE, "horizonDays": 10}}, headers=cal.h(cal.pr))
    assert r.json()["capacity_after"]["Mathematics"]["available_periods"] == 40


@pytest.mark.asyncio
async def test_preview_shows_recalculated_allocations_without_changing_anything(cal, db_session):
    before = [(c.teacher_id, c.topic_key, c.core_periods, c.non_core_periods, c.version) for c in (await db_session.execute(select(TeacherTopicConfig).filter_by(school_id=cal.sid))).scalars().all()]
    versions_before = len((await db_session.execute(select(SchoolPlanCalendar).filter_by(school_id=cal.sid))).scalars().all())
    r = await cal.c.post(f"{BASE_URL}/preview", json={"config": {**BASE, "subjectPeriodsPerDay": {"Mathematics": 1, "Science": 1}}}, headers=cal.h(cal.pr))
    rows = {(i["teacher_id"], i["subject"]): i for i in r.json()["impact"]}
    row = rows[(cal.t0, "Mathematics")]
    assert row["saved_total"] == 36 and row["capacity_after"]["topic_capacity"] == 18 and row["periods_gained_or_lost"] == -18
    # the remaining allocation is recalculated to FIT the new capacity: 18 over two open topics = 9 + 9 (largest remainder, exact)
    assert row["recalculated_total"] == 18 and row["remaining_after"] == 0 and row["deficit_after"] == 0 and row["needs_teacher_review"] is False
    assert [t["default_after"] for t in row["topics"]] == [9, 9] and sum(t["revised_allocation"] for t in row["topics"]) == 18
    assert [t["default_before"] for t in row["topics"]] == [18, 18] and [t["allocation_change"] for t in row["topics"]] == [-9, -9]
    assert all(t["is_affected"] for t in row["topics"]) and row["topics_changed"] == 2
    assert row["core_requirements_fit"] is True and row["core_shortfall"] == 0 and row["insufficient_capacity"] is False
    assert all(t["original_classroom"] + t["original_independent"] == t["original_allocation"] for t in row["topics"])
    assert all(t["revised_classroom"] + t["revised_independent"] == t["revised_allocation"] for t in row["topics"])
    assert all(t["classification"] in ("core", "non_core", "mixed") for t in row["topics"])  # classifications are preserved
    assert row["approved_schedule"] is None  # no approved plan yet: reported as such, not invented
    assert r.json()["teacher_configurations_changed"] is False and r.json()["will_recalculate_remaining_syllabus"] is True
    after = [(c.teacher_id, c.topic_key, c.core_periods, c.non_core_periods, c.version) for c in (await db_session.execute(select(TeacherTopicConfig).filter_by(school_id=cal.sid))).scalars().all()]
    await db_session.rollback()
    assert sorted(before) == sorted(after)  # a preview writes nothing
    assert len((await db_session.execute(select(SchoolPlanCalendar).filter_by(school_id=cal.sid))).scalars().all()) == versions_before


@pytest.mark.asyncio
async def test_preview_scope_roles_and_validation(cal):
    cfg = {"config": {**BASE, "entries": [HOLIDAY]}}
    mine = await cal.c.post(f"{BASE_URL}/preview", json=cfg, headers=cal.h(cal.t0))
    assert mine.status_code == 200 and {i["teacher_id"] for i in mine.json()["impact"]} == {cal.t0}  # a teacher sees only their own plan
    allr = await cal.c.post(f"{BASE_URL}/preview", json=cfg, headers=cal.h(cal.pr))
    assert {i["teacher_id"] for i in allr.json()["impact"]} == {cal.t0, cal.t1}
    assert (await cal.c.post(f"{BASE_URL}/preview", json={"config": {**BASE, "weekdays": []}}, headers=cal.h(cal.pr))).status_code == 422
    student = {"Authorization": f"Bearer {create_access_token('user-student-1', school_id='school-1', role='student')}", "X-School-Id": "school-1"}
    assert (await cal.c.post(f"{BASE_URL}/preview", json=cfg, headers=student)).status_code == 403


@pytest.mark.asyncio
async def test_save_creates_versions_audits_and_recalculates_the_remaining_syllabus(cal, db_session):
    new = {**BASE, "subjectPeriodsPerDay": {"Mathematics": 1, "Science": 1}}
    assert (await cal.c.put(BASE_URL, json={"config": new, "reason": "Timetable revised"}, headers=cal.h(cal.t0))).status_code == 403  # teachers inspect only
    assert (await cal.c.put(BASE_URL, json={"config": new, "reason": ""}, headers=cal.h(cal.pr))).status_code == 422  # a reason is required
    assert (await cal.c.put(BASE_URL, json={"config": BASE, "reason": "same"}, headers=cal.h(cal.pr))).status_code == 422  # nothing changed
    assert (await cal.c.put(BASE_URL, json={"config": {**BASE, "weekdays": []}, "reason": "bad"}, headers=cal.h(cal.pr))).status_code == 422
    assert (await cal.c.put(BASE_URL, json={"config": new, "reason": "stale", "expected_version": 7}, headers=cal.h(cal.pr))).status_code == 409
    ok = await cal.c.put(BASE_URL, json={"config": new, "reason": "Timetable revised", "expected_version": 1}, headers=cal.h(cal.pr))
    assert ok.status_code == 200 and ok.json()["version"] == 2 and ok.json()["teachers_needing_review"] == 0 and ok.json()["plans_recalculated"] == 2 and ok.json()["topics_changed"] == 4
    h = (await cal.c.get(f"{BASE_URL}/history", headers=cal.h(cal.t1))).json()["versions"]  # teachers may read the history
    assert [v["version"] for v in h] == [1, 2] and h[0]["config"] == BASE and h[1]["config"] == new and h[1]["reason"] == "Timetable revised"
    assert h[0]["capacity"]["Mathematics"]["topic_capacity"] == 36 and h[1]["capacity"]["Mathematics"]["topic_capacity"] == 18
    ev = (await db_session.execute(select(PlanAuditEvent).filter_by(school_id=cal.sid, category="calendar_change"))).scalars().all()
    assert len(ev) == 1 and ev[0].previous_value["capacity"]["Mathematics"]["topic_capacity"] == 36 and ev[0].new_value["capacity"]["Mathematics"]["topic_capacity"] == 18
    assert ev[0].reason == "Timetable revised" and ev[0].actor_id == cal.pr and ev[0].new_value["teachers_needing_review"] == [] and ev[0].new_value["plans_recalculated"] == 2
    # the remaining (untaught) allocation was recalculated automatically to the 18 periods that now fit; classifications are preserved
    plan = (await cal.c.get(f"/api/v1/teacher-plans/{cal.t0}", params=MATH, headers=cal.h(cal.t0))).json()
    assert plan["allocation"]["proposed_total"] == 18 == plan["capacity"]["topic_capacity"] and plan["allocation"]["valid"] is True
    assert [t["core_periods"] + t["non_core_periods"] for t in plan["topics"]] == [9, 9]
    assert plan["summary"]["periods_per_day"] == 1 and plan["summary"]["remaining_capacity"] == 18 and plan["summary"]["unallocated_capacity"] == 0 and plan["summary"]["fits"] is True
    rec = (await db_session.execute(select(PlanAuditEvent).filter_by(school_id=cal.sid, teacher_id=cal.t0, category="calendar_recalculation"))).scalars().all()
    assert len(rec) == 1 and rec[0].previous_value["core"] + rec[0].previous_value["non_core"] == 36 and rec[0].new_value["core"] + rec[0].new_value["non_core"] == 18
    topics = plan["topics"]
    over = {**MATH, "items": [{"topic_key": topics[0]["topic_key"], "core_periods": topics[0]["core_periods"] + 1, "non_core_periods": topics[0]["non_core_periods"]}]}
    assert (await cal.c.put(f"/api/v1/teacher-plans/{cal.t0}/requirements", json=over, headers=cal.h(cal.t0))).status_code == 422
    other = (await cal.c.get(f"/api/v1/teacher-plans/{cal.t1}", params=MATH, headers=cal.h(cal.t1))).json()
    assert other["allocation"]["proposed_total"] == 18 and other["allocation"]["valid"] is True  # every plan in the school is recalculated, each independently


@pytest.mark.asyncio
async def test_teacher_calendar_impact_compares_current_with_previous_version(cal):
    first = (await cal.c.get(f"/api/v1/teacher-plans/{cal.t0}/calendar-impact", params=MATH, headers=cal.h(cal.t0))).json()
    assert first["current_version"] == 1 and first["has_previous"] is False
    await cal.c.put(BASE_URL, json={"config": {**BASE, "entries": [HOLIDAY]}, "reason": "Winter break day"}, headers=cal.h(cal.pr))
    imp = (await cal.c.get(f"/api/v1/teacher-plans/{cal.t0}/calendar-impact", params=MATH, headers=cal.h(cal.t0))).json()
    assert imp["current_version"] == 2 and imp["previous_version"] == 1 and imp["reason"] == "Winter break day"
    row = imp["impact"]
    assert row["capacity_before"]["topic_capacity"] == 36 and row["capacity_after"]["topic_capacity"] == 34
    assert row["saved_total"] == 34 and row["deficit_after"] == 0 and row["needs_teacher_review"] is False  # already recalculated to the 34 that fit
    # another teacher cannot read it, a principal can
    assert (await cal.c.get(f"/api/v1/teacher-plans/{cal.t0}/calendar-impact", params=MATH, headers=cal.h(cal.t1))).status_code == 403
    assert (await cal.c.get(f"/api/v1/teacher-plans/{cal.t0}/calendar-impact", params=MATH, headers=cal.h(cal.pr))).status_code == 200


@pytest.mark.asyncio
async def test_calendar_recalculation_is_deterministic_and_restoration_recovers_capacity(cal, db_session):
    reduced = {**BASE, "entries": [HOLIDAY]}
    a = (await cal.c.post(f"{BASE_URL}/preview", json={"config": reduced}, headers=cal.h(cal.pr))).json()
    b = (await cal.c.post(f"{BASE_URL}/preview", json={"config": reduced}, headers=cal.h(cal.pr))).json()
    assert a["impact"] == b["impact"]
    # Preview is repeatable and never creates calendar/allocation versions.
    assert (await db_session.execute(select(SchoolPlanCalendar).filter_by(school_id=cal.sid))).scalars().all().__len__() == 1
    await cal.c.put(BASE_URL, json={"config": reduced, "reason": "Additional holiday"}, headers=cal.h(cal.pr))
    restored = await cal.c.put(BASE_URL, json={"config": BASE, "reason": "Teaching days restored"}, headers=cal.h(cal.pr))
    assert restored.status_code == 200 and restored.json()["version"] == 3
    impact = (await cal.c.post(f"{BASE_URL}/preview", json={"config": BASE}, headers=cal.h(cal.pr))).json()
    row = next(x for x in impact["impact"] if x["teacher_id"] == cal.t0)
    assert row["capacity_after"]["available_periods"] == 40
    assert [t["revised_allocation"] for t in row["topics"]] == [18, 18]


@pytest.mark.asyncio
async def test_calendars_are_independent_per_school(client, cal):
    other_before = (await client.get(BASE_URL, headers=hdr("user-principal-1", "principal", "school-1"))).json()
    await cal.c.put(BASE_URL, json={"config": {**BASE, "entries": [HOLIDAY]}, "reason": "ours"}, headers=cal.h(cal.pr))
    other_after = (await client.get(BASE_URL, headers=hdr("user-principal-1", "principal", "school-1"))).json()
    assert other_before == other_after
    mine = (await client.get(BASE_URL, headers=cal.h(cal.pr))).json()
    assert mine["version"] == 2 and mine["available_periods"]["Mathematics"] == 38
    # a school the user does not belong to is refused
    assert (await client.get(BASE_URL, headers=hdr("user-principal-1", "principal", cal.sid))).status_code == 403


@pytest.mark.asyncio
async def test_import_workspace_calendar_is_idempotent_and_never_replaces(db_session):
    db_session.add(School(id="school-cimp", name="c", location="x", state="x", infrastructure_tier="standard"))
    st = empty_state()
    st["config"] = BASE
    st["configHistory"] = [{"config": BASE, "savedBy": {"id": "a", "name": "a", "role": "admin"}, "savedAt": "t"}]
    db_session.add(PlanningWorkspaceRevision(school_id="school-cimp", revision=1, action="CONFIG_SAVE", summary="legacy", actor_id="x", actor_name="x", actor_role="admin", state=st))
    await db_session.commit()
    rep = await import_workspace_calendar(db_session, "school-cimp")
    assert rep["imported"] == ["calendar"]
    row = (await db_session.execute(select(SchoolPlanCalendar).filter_by(school_id="school-cimp"))).scalars().one()
    assert row.version == 1 and row.config == BASE and row.created_by == "system-import"
    assert (await import_workspace_calendar(db_session, "school-cimp"))["skipped_existing"] == ["calendar"]
    # never-saved configuration: reported, nothing invented; invalid stored configuration: reported, not forced
    db_session.add(School(id="school-cnone", name="c", location="x", state="x", infrastructure_tier="standard"))
    db_session.add(PlanningWorkspaceRevision(school_id="school-cnone", revision=1, action="SYLLABUS_IMPORT", summary="x", actor_id="x", actor_name="x", actor_role="admin", state=empty_state()))
    bad = empty_state()
    bad["config"] = {**BASE, "weekdays": []}
    bad["configHistory"] = [{"config": bad["config"]}]
    db_session.add(School(id="school-cbad", name="c", location="x", state="x", infrastructure_tier="standard"))
    db_session.add(PlanningWorkspaceRevision(school_id="school-cbad", revision=1, action="CONFIG_SAVE", summary="x", actor_id="x", actor_name="x", actor_role="admin", state=bad))
    await db_session.commit()
    assert (await import_workspace_calendar(db_session, "school-cnone"))["no_configuration"] is True
    assert (await import_workspace_calendar(db_session, "school-cbad"))["invalid"]
    assert (await db_session.execute(select(SchoolPlanCalendar).filter(SchoolPlanCalendar.school_id.in_(["school-cnone", "school-cbad"])))).scalars().all() == []


@pytest.mark.asyncio
async def test_new_planning_endpoints_never_fall_back_to_the_demo_admin(client):
    """DEMO_MODE resolves a tokenless request to an admin elsewhere; none of the teacher-plan surfaces may."""
    probes = [("get", f"{BASE_URL}"), ("get", f"{BASE_URL}/history"), ("post", f"{BASE_URL}/preview"), ("put", f"{BASE_URL}"),
              ("get", "/api/v1/plans"), ("post", "/api/v1/plans/x/review"), ("get", "/api/v1/plan-logs"), ("get", "/api/v1/plan-oversight/planning"),
              ("get", "/api/v1/teacher-plans/user-teacher-1?grade=7&subject=Mathematics"), ("put", "/api/v1/teacher-plans/user-teacher-1/requirements"),
              ("post", "/api/v1/teacher-plans/user-teacher-1/lost-periods"), ("post", "/api/v1/teacher-plans/user-teacher-1/relationships")]
    for method, url in probes:
        r = await getattr(client, method)(url, **({"json": {}} if method in ("post", "put") else {}))
        assert r.status_code == 401, (method, url, r.status_code)


@pytest.mark.asyncio
async def test_teacher_set_classification_and_periods_survive_calendar_changes_both_ways(cal):
    plan = (await cal.c.get(f"/api/v1/teacher-plans/{cal.t0}", params=MATH, headers=cal.h(cal.t0))).json()
    keys = [t["topic_key"] for t in plan["topics"]]
    mixed = {**MATH, "items": [{"topic_key": keys[0], "core_periods": 3, "non_core_periods": 1, "classification": "mixed"}]}
    assert (await cal.c.put(f"/api/v1/teacher-plans/{cal.t0}/requirements", json=mixed, headers=cal.h(cal.t0))).status_code == 200
    def row(p, k):
        return next(t for t in p["topics"] if t["topic_key"] == k)
    for cfg, reason in (({**BASE, "entries": [HOLIDAY]}, "add holiday"), (BASE, "remove holiday"), ({**BASE, "subjectPeriodsPerDay": {"Mathematics": 1, "Science": 1}}, "fewer periods"), (BASE, "restore")):
        assert (await cal.c.put(BASE_URL, json={"config": cfg, "reason": reason}, headers=cal.h(cal.pr))).status_code == 200
        p = (await cal.c.get(f"/api/v1/teacher-plans/{cal.t0}", params=MATH, headers=cal.h(cal.t0))).json()
        r0 = row(p, keys[0])
        assert (r0["classification"], r0["core_periods"], r0["non_core_periods"], r0["origin"]) == ("mixed", 3, 1, "teacher"), (reason, r0)
        # the other topic (an auto-derived default) is what absorbs the change: total = capacity - the teacher's own 4
        assert row(p, keys[1])["core_periods"] + row(p, keys[1])["non_core_periods"] == p["capacity"]["topic_capacity"] - 4, reason
        assert p["allocation"]["valid"] is True
