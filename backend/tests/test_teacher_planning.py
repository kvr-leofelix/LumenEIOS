"""Teacher-scoped plans: allocation math, ownership, isolation, capacity blocking, lost periods, audit."""
import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.app.core.security import create_access_token
from backend.app.models.teacher_planning import AppendOnlyError, PlanAuditEvent
from backend.app.seed.teacher_plan_demo import seed_teacher_plan_demo
from backend.app.services import annual_allocation as A


def hdr(uid, role, school):
    return {"Authorization": f"Bearer {create_access_token(uid, school_id=school, role=role)}", "X-School-Id": school}


T1, T2, T3 = ("user-teacher-1", "teacher", "school-1"), ("user-teacher-2", "teacher", "school-1"), ("user-teacher-3", "teacher", "school-3")
P1, P3 = ("user-principal-1", "principal", "school-1"), ("demo-plan-principal-3", "principal", "school-3")
MATH = {"grade": 7, "subject": "Mathematics"}
BASE = "/api/v1/teacher-plans"


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="session")
async def seeded():
    from backend.app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        first = await seed_teacher_plan_demo(s)
        second = await seed_teacher_plan_demo(s)
    assert second["plans_created"] == 0  # idempotent
    return first


# ---------------------------------------------------------------- pure allocation math
@pytest.mark.parametrize("p,r", [(0, 0), (1, 1), (10, 1), (11, 2), (180, 18), (181, 19)])
def test_reserve_uses_ceiling(p, r):
    assert A.reserve_periods(p) == r
    assert A.capacity(p)["topic_capacity"] == p - r


@pytest.mark.parametrize("total,n", [(0, 3), (7, 3), (100, 7), (162, 10), (5, 9)])
def test_largest_remainder_sums_exactly_and_is_stable(total, n):
    out = A.largest_remainder(total, [1] * n)
    assert sum(out) == total and max(out) - min(out) <= 1
    assert out == A.largest_remainder(total, [1] * n)
    assert out == sorted(out, reverse=True)  # ties favour earlier syllabus position


def test_split_core_noncore():
    assert A.split_core_noncore(9, "mixed") == {"core": 6, "non_core": 3}
    assert A.split_core_noncore(7, "mixed") == {"core": 5, "non_core": 2}
    assert A.split_core_noncore(5, "core") == {"core": 5, "non_core": 0}
    assert A.split_core_noncore(5, "non_core") == {"core": 0, "non_core": 5}
    for n in range(0, 40):
        s = A.split_core_noncore(n, "mixed")
        assert s["core"] + s["non_core"] == n


def test_topic_allocations_use_custom_weights_stable_order_and_independent_subset():
    topics = [
        {"topic_key": "topic-a", "classification": "core", "weight": 1, "teaching_mode": "SHARED"},
        {"topic_key": "topic-b", "classification": "mixed", "weight": 2, "teaching_mode": "INDEPENDENT"},
    ]
    first = A.topic_allocations(topics, 11)  # P=11, reserve=2, T=9
    again = A.topic_allocations(topics, 11)
    assert first == again
    assert [r["allocation"] for r in first] == [3, 6]
    assert first[0]["core"] == 3 and first[0]["non_core"] == 0
    assert first[1]["core"] == 4 and first[1]["non_core"] == 2  # mixed 2:1
    assert first[1]["independent_periods"] == 1
    assert first[1]["classroom_periods"] == 5
    assert sum(r["allocation"] for r in first) == A.capacity(11)["topic_capacity"]


def test_available_periods_excludes_holidays_events_and_weekends():
    cfg = {"start": "2026-04-01", "end": "2026-04-30", "weekdays": [1, 2, 3, 4, 5],
           "entries": [{"type": "HOLIDAY", "start": "2026-04-03", "end": "2026-04-03"},
                       {"type": "EVENT", "start": "2026-04-06", "end": "2026-04-07"}],
           "subjectPeriodsPerDay": {"Mathematics": 2}}
    # April 2026 has 22 weekdays; minus 1 holiday and 2 event days = 19 days x 2 periods
    assert len(A.instructional_dates(cfg)) == 19
    assert A.available_periods(cfg, "Mathematics") == 38


def test_validate_requirements_blocks_over_capacity_and_bad_values():
    ok = A.validate_requirements([{"topic_key": "a", "core_periods": 3, "non_core_periods": 2}], 5)
    assert ok["valid"] and ok["remaining"] == 0
    bad = A.validate_requirements([{"topic_key": "a", "core_periods": 4, "non_core_periods": 2}], 5)
    assert not bad["valid"] and bad["deficit"] == 1
    assert not A.validate_requirements([{"topic_key": "a", "core_periods": -1, "non_core_periods": 2}], 5)["valid"]


def test_lost_day_counting_groups_periods_by_date():
    s = A.lost_summary([{"date": "2026-06-01", "period": 1}, {"date": "2026-06-01", "period": 2}, {"date": "2026-06-02", "period": 1}])
    assert s == {"lost_days": 2, "lost_periods": 3}


def test_demo_classification_deterministic_and_pure():
    assert A.demo_classification("XW-x") == A.demo_classification("XW-x")
    assert {A.demo_classification(f"k{i}") for i in range(60)} == {"core", "mixed", "non_core"}


# ---------------------------------------------------------------- API behaviour
async def plan(client, who, teacher, grade=7, subject="Mathematics"):
    r = await client.get(f"{BASE}/{teacher}", params={"grade": grade, "subject": subject}, headers=hdr(*who))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_defaults_use_full_topic_capacity_and_match_across_schools(client):
    a, b = await plan(client, T1, T1[0]), await plan(client, T3, T3[0])
    for p in (a, b):
        assert p["allocation"]["valid"]
        assert p["allocation"]["proposed_total"] == p["capacity"]["topic_capacity"]  # sum == T exactly
        assert p["capacity"]["reserved_periods"] == -(-p["capacity"]["available_periods"] // 10)
    # same hypothetical classification pattern in every school
    assert [(t["topic_key"], t["classification"]) for t in a["topics"]] == [(t["topic_key"], t["classification"]) for t in b["topics"]]
    assert a["capacity"] != b["capacity"]  # independent calendars give different capacity


@pytest.mark.asyncio
async def test_teacher_edit_is_independent_and_audited(client):
    before2 = await plan(client, T2, T2[0])
    t = (await plan(client, T1, T1[0]))["topics"][0]
    body = {**MATH, "reason": "More practice needed",
            "items": [{"topic_key": t["topic_key"], "core_periods": t["core_periods"] - 1,
                       "non_core_periods": t["non_core_periods"], "classification": t["classification"]}]}
    r = await client.put(f"{BASE}/user-teacher-1/requirements", json=body, headers=hdr(*T1))
    assert r.status_code == 200 and r.json()["changed"] == [t["topic_key"]]
    after1 = await plan(client, T1, T1[0])
    assert after1["topics"][0]["core_periods"] == t["core_periods"] - 1
    assert after1["topics"][0]["origin"] == "teacher" and after1["topics"][0]["version"] == 2
    assert await plan(client, T2, T2[0]) == before2  # teacher B unchanged
    logs = (await client.get("/api/v1/plan-logs", params={"topic_key": t["topic_key"], "teacher_id": "user-teacher-1"}, headers=hdr(*P1))).json()
    ev = [e for e in logs["items"] if e["reason"] == "More practice needed"][0]
    assert ev["previous_value"]["core_periods"] == t["core_periods"] and ev["new_value"]["core_periods"] == t["core_periods"] - 1


@pytest.mark.asyncio
async def test_over_capacity_save_is_blocked_and_not_persisted(client):
    p = await plan(client, T1, T1[0])
    t = p["topics"][0]
    body = {**MATH, "items": [{"topic_key": t["topic_key"], "core_periods": t["core_periods"] + 50, "non_core_periods": t["non_core_periods"]}]}
    r = await client.put(f"{BASE}/user-teacher-1/requirements", json=body, headers=hdr(*T1))
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["deficit"] > 0 and d["topic_capacity"] == p["capacity"]["topic_capacity"] and d["proposed_total"] > d["topic_capacity"]
    assert (await plan(client, T1, T1[0]))["topics"][0]["core_periods"] == t["core_periods"]


@pytest.mark.asyncio
async def test_core_topic_cannot_carry_noncore_periods(client):
    p = await plan(client, T2, T2[0])
    core = next((t for t in p["topics"] if t["classification"] == "core"), None)
    if core is None:
        pytest.skip("no core topic in this combination")
    body = {**MATH, "items": [{"topic_key": core["topic_key"], "core_periods": core["core_periods"] - 1, "non_core_periods": 1}]}
    assert (await client.put(f"{BASE}/user-teacher-2/requirements", json=body, headers=hdr(*T2))).status_code == 422


@pytest.mark.asyncio
async def test_ownership_and_oversight_roles(client):
    t = (await plan(client, T1, T1[0]))["topics"][0]
    body = {**MATH, "items": [{"topic_key": t["topic_key"], "core_periods": t["core_periods"], "non_core_periods": t["non_core_periods"]}]}
    assert (await client.put(f"{BASE}/user-teacher-1/requirements", json=body, headers=hdr(*T2))).status_code == 403
    assert (await client.put(f"{BASE}/user-teacher-1/requirements", json=body, headers=hdr(*P1))).status_code == 403
    cov = {**MATH, "topic_key": t["topic_key"], "status": "done"}
    assert (await client.put(f"{BASE}/user-teacher-1/coverage", json=cov, headers=hdr(*P1))).status_code == 403
    assert (await client.get(f"{BASE}/user-teacher-1", params=MATH, headers=hdr(*T2))).status_code == 403
    assert (await client.get("/api/v1/plan-oversight/planning", headers=hdr(*T1))).status_code == 403


@pytest.mark.asyncio
async def test_coverage_is_per_teacher_and_percent_counts_only_done(client):
    p1 = await plan(client, T1, T1[0])
    k = p1["topics"][0]["topic_key"]
    base = {**MATH, "topic_key": k}
    assert (await client.put(f"{BASE}/user-teacher-1/coverage", json={**base, "status": "done"}, headers=hdr(*T1))).status_code == 200
    assert (await client.put(f"{BASE}/user-teacher-1/coverage", json={**base, "status": "bogus"}, headers=hdr(*T1))).status_code == 422
    a, b = await plan(client, T1, T1[0]), await plan(client, T2, T2[0])
    assert a["topics"][0]["coverage"] == "done" and b["topics"][0]["coverage"] == "not_done"
    assert a["coverage"]["done"] == 1 and a["coverage"]["percent"] == round(100 / a["coverage"]["eligible"], 1)
    assert b["coverage"]["done"] == 0
    await client.put(f"{BASE}/user-teacher-1/coverage", json={**base, "status": "in_progress"}, headers=hdr(*T1))
    assert (await plan(client, T1, T1[0]))["coverage"]["done"] == 0
    rows = (await client.get("/api/v1/plan-oversight/curriculum", headers=hdr(*P1))).json()["rows"]
    mine = [r for r in rows if r["grade"] == 7 and r["subject"] == "Mathematics"]
    assert {r["teacher_id"] for r in mine} == {"user-teacher-1", "user-teacher-2"}  # listed separately, not merged


@pytest.mark.asyncio
async def test_lost_periods_same_date_is_one_day_and_duplicates_rejected(client):
    base = {**MATH, "date": "2026-06-01", "reason_code": "school_event", "notes": "Sports day"}
    url = f"{BASE}/user-teacher-1/lost-periods"
    r = await client.post(url, json={**base, "periods": [1, 2]}, headers=hdr(*T1))
    assert r.status_code == 201, r.text
    assert (await client.post(url, json={**base, "periods": [2]}, headers=hdr(*T1))).status_code == 409
    assert (await client.post(url, json={**base, "date": "2026-06-02", "periods": [1]}, headers=hdr(*T1))).status_code == 201
    o = (await client.get(url, params={**MATH, "today": "2026-06-30"}, headers=hdr(*T1))).json()
    assert o["lost_days"] == 2 and o["lost_periods"] == 3
    assert o["completed_days"] > 0 and o["remaining_days"] > 0
    other = (await client.get(f"{BASE}/user-teacher-2/lost-periods", params=MATH, headers=hdr(*T2))).json()
    assert all(r["date"] not in ("2026-06-01", "2026-06-02") for r in other["records"])  # teacher 1's losses are not teacher 2's
    assert (await client.post(url, json={**base, "date": "2026-06-03", "periods": [1, 2, 3]}, headers=hdr(*T1))).status_code == 422
    assert (await client.post(url, json={**base, "date": "2030-01-01", "periods": [1]}, headers=hdr(*T1))).status_code == 422
    assert (await client.post(url, json={**base, "date": "2026-06-04", "periods": [1], "reason_code": "x"}, headers=hdr(*T1))).status_code == 422
    cats = [e["category"] for e in (await client.get("/api/v1/plan-logs", params={"teacher_id": "user-teacher-1"}, headers=hdr(*P1))).json()["items"]]
    assert cats.count("lost_day") == 2 and cats.count("lost_period") == 2


@pytest.mark.asyncio
async def test_school_isolation(client):
    assert (await client.get(f"{BASE}/user-teacher-1", params=MATH, headers=hdr(*P3))).status_code == 404
    rows = (await client.get("/api/v1/plan-oversight/planning", headers=hdr(*P3))).json()["rows"]
    assert rows and all(r["teacher_id"] in ("user-teacher-3", "demo-plan-teacher-3b") for r in rows)
    logs = (await client.get("/api/v1/plan-logs", headers=hdr(*P3))).json()["items"]
    assert logs and all(e["school_id"] == "school-3" for e in logs)
    assert (await client.get("/api/v1/plan-logs", headers=hdr("demo-plan-principal-3", "principal", "school-1"))).status_code == 403


@pytest.mark.asyncio
async def test_teacher_sees_only_own_logs_and_filters_work(client):
    mine = (await client.get("/api/v1/plan-logs", headers=hdr(*T2))).json()["items"]
    assert mine and all(e["teacher_id"] == "user-teacher-2" for e in mine)
    f = (await client.get("/api/v1/plan-logs", params={"category": "lost_period"}, headers=hdr(*P1))).json()
    assert f["total"] >= 1 and all(e["category"] == "lost_period" for e in f["items"])


@pytest.mark.asyncio
async def test_calendar_change_versions_and_recalculates_untaught_allocations_preserving_classification(client):
    before = await plan(client, T1, T1[0])
    cal = (await client.get("/api/v1/plan-calendar", headers=hdr(*P1))).json()
    cfg = {**cal["config"], "subjectPeriodsPerDay": {"Mathematics": 1, "Science": 1}}
    pv = await client.post("/api/v1/plan-calendar/preview", json={"config": cfg, "reason": "x"}, headers=hdr(*P1))
    assert pv.status_code == 200 and pv.json()["teacher_configurations_changed"] is False
    assert (await client.put("/api/v1/plan-calendar", json={"config": cfg, "reason": "x"}, headers=hdr(*T1))).status_code == 403
    put = await client.put("/api/v1/plan-calendar", json={"config": cfg, "reason": "Timetable revised"}, headers=hdr(*P1))
    assert put.json()["version"] == cal["version"] + 1
    after = await plan(client, T1, T1[0])
    assert after["capacity"]["topic_capacity"] < before["capacity"]["topic_capacity"]
    assert after["allocation"]["valid"] is True and after["allocation"]["proposed_total"] == after["capacity"]["topic_capacity"]  # recalculated to fit
    assert [t["classification"] for t in after["topics"]] == [t["classification"] for t in before["topics"]]  # classifications preserved
    await client.put("/api/v1/plan-calendar", json={"config": cal["config"], "reason": "restore"}, headers=hdr(*P1))


@pytest.mark.asyncio
async def test_audit_events_are_append_only(db_session):
    ev = (await db_session.execute(select(PlanAuditEvent).limit(1))).scalars().first()
    ev.summary = "tampered"
    with pytest.raises(AppendOnlyError):
        await db_session.flush()
    await db_session.rollback()
    ev = (await db_session.execute(select(PlanAuditEvent).limit(1))).scalars().first()
    await db_session.delete(ev)
    with pytest.raises(AppendOnlyError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_relationships_are_teacher_specific(client):
    p = await plan(client, T1, T1[0])
    a, b = p["topics"][0]["topic_key"], p["topics"][1]["topic_key"]
    url = f"{BASE}/user-teacher-1/relationships"
    body = {"kind": "PREREQUISITE", "from_key": a, "to_key": b, "explanation": "Multiplication of fractions is needed before division.", "evidence": "8.1 and 8.2 locators"}
    assert (await client.post(url, json=body, headers=hdr(*T1))).status_code == 201
    assert (await client.post(url, json=body, headers=hdr(*T1))).status_code == 422  # duplicate
    assert (await client.post(url, json={**body, "to_key": a}, headers=hdr(*T1))).status_code == 422  # self link
    assert (await plan(client, T1, T1[0]))["topics"][1]["prerequisites"] == [a]
    assert (await plan(client, T2, T2[0]))["topics"][1]["prerequisites"] == []
