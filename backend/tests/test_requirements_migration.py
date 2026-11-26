"""Step 2: requirements and classifications live only in teacher_topic_configs."""
import copy

import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.app.core.security import create_access_token
from backend.app.models.entities import School, User
from backend.app.models.planning_workspace import PlanningWorkspaceRevision
from backend.app.models.teacher_planning import PlanAuditEvent, PlanTopic, TeacherPlan, TeacherTopicConfig
from backend.app.seed.teacher_plan_demo import seed_teacher_plan_demo
from backend.app.services.planning_workspace_service import authorize_changes
from backend.app.services.teacher_plan_service import ensure_defaults
from backend.app.services.workspace_import import import_workspace_requirements
from backend.tests.test_planning_workspace import URL, auth, empty_state, save, with_audit


def hdr(uid, role, school):
    return {"Authorization": f"Bearer {create_access_token(uid, school_id=school, role=role)}", "X-School-Id": school}


T1, T2, T3 = ("user-teacher-1", "teacher", "school-1"), ("user-teacher-2", "teacher", "school-1"), ("user-teacher-3", "teacher", "school-3")
P1, A1 = ("user-principal-1", "principal", "school-1"), ("user-admin", "admin", "school-1")
MATH = {"grade": 7, "subject": "Mathematics"}
BASE = "/api/v1/teacher-plans"


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="session")
async def seeded():
    from backend.app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        await seed_teacher_plan_demo(s)


async def plan(client, who, teacher=None):
    r = await client.get(f"{BASE}/{teacher or who[0]}", params=MATH, headers=hdr(*who))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_all_requirements_endpoint_scopes_by_teacher_and_school(client):
    ok = await client.get(f"{BASE}/user-teacher-1/requirements", headers=hdr(*T1))
    assert ok.status_code == 200
    items = ok.json()["items"]
    assert {(i["grade"], i["subject"]) for i in items} == {(7, "Mathematics"), (8, "Science")}
    assert all(i["origin"] in ("demo_default", "teacher", "approved_import") for i in items)
    assert (await client.get(f"{BASE}/user-teacher-1/requirements", headers=hdr(*T2))).status_code == 403  # other teacher
    assert (await client.get(f"{BASE}/user-teacher-1/requirements", headers=hdr(*P1))).status_code == 200  # may inspect
    assert (await client.get(f"{BASE}/user-teacher-1/requirements", headers=hdr(*A1))).status_code == 200
    assert (await client.get(f"{BASE}/user-teacher-1/requirements", headers=hdr(*T3))).status_code == 403
    assert (await client.get(f"{BASE}/user-teacher-3/requirements", headers=hdr("user-principal-1", "principal", "school-1"))).status_code == 404  # other school


@pytest.mark.asyncio
async def test_defaults_keep_the_allocation_rules_and_stay_demo_defaults(client):
    p = await plan(client, T2)
    cap = p["capacity"]
    assert cap["reserved_periods"] == -(-cap["available_periods"] // 10)
    assert sum(t["core_periods"] + t["non_core_periods"] for t in p["topics"]) == cap["topic_capacity"]
    for t in p["topics"]:
        alloc = t["core_periods"] + t["non_core_periods"]
        if t["classification"] == "mixed":
            assert t["core_periods"] == -(-alloc * 2 // 3)  # 2:1 split with Core rounded up
        assert t["origin"] == "demo_default"  # never presented as approved
        assert t["teaching_mode"] in ("SHARED", "INDEPENDENT")
        assert 0 <= t["independent_periods"] <= t["non_core_periods"]
        assert t["classroom_periods"] + t["independent_periods"] == alloc
    # This two-topic demo slice need not contain all three deterministic classes; the larger suite below
    # checks distribution across a full 18-topic syllabus.


@pytest.mark.asyncio
async def test_defaults_fill_partial_topic_sets_deterministically_without_overwriting_decisions(db_session):
    sid = "school-default-fill"
    users = await new_school(db_session, sid)
    teacher = users[0]
    db_session.add(TeacherPlan(id="default-history-plan", school_id=sid, teacher_id=teacher.id, academic_year="2026-2027",
        grade=6, subject="Science", status="APPROVED", dataset_id="fixture", dataset_label="fixture", dataset_kind="DRAFT",
        config={}, estimates={}, draft={"lessons": []}, created_by={"id": teacher.id, "name": teacher.name, "role": "teacher"}, review={"decision": "APPROVED"}))
    keys = [f"defaults-{i:02d}" for i in range(18)]
    for i, key in enumerate(keys):
        db_session.add(PlanTopic(topic_key=key, grade=6, subject="Science", chapter_number="1", chapter_title="Fixture",
                                 section_label=f"Topic {i}", sort_order=i + 1, source_ref=f"ncert-batch:test-{key}"))
    await db_session.flush()
    custom = TeacherTopicConfig(school_id=sid, teacher_id=teacher.id, academic_year="2026-2027", grade=6, subject="Science",
        topic_key=keys[0], classification="mixed", core_periods=2, non_core_periods=1, independent_periods=1,
        teaching_mode="INDEPENDENT", origin="teacher", version=7, updated_by=teacher.id)
    imported = TeacherTopicConfig(school_id=sid, teacher_id=teacher.id, academic_year="2026-2027", grade=6, subject="Science",
        topic_key=keys[1], classification="core", core_periods=2, non_core_periods=0, independent_periods=0,
        teaching_mode="SHARED", origin="approved_import", version=3, updated_by=teacher.id)
    db_session.add_all([custom, imported])
    await db_session.commit()
    assert await ensure_defaults(db_session, teacher, sid, teacher.id, "2026-2027", 6, "Science") is True
    await db_session.flush()
    rows = (await db_session.execute(select(TeacherTopicConfig).filter_by(school_id=sid, teacher_id=teacher.id,
        academic_year="2026-2027", grade=6, subject="Science").order_by(TeacherTopicConfig.topic_key))).scalars().all()
    first = {r.topic_key: r for r in rows}
    assert len(first) == 18
    assert (first[keys[0]].origin, first[keys[0]].version, first[keys[0]].core_periods, first[keys[0]].independent_periods) == ("teacher", 7, 2, 1)
    assert (first[keys[1]].origin, first[keys[1]].version, first[keys[1]].classification) == ("approved_import", 3, "core")
    assert {first[k].classification for k in keys} >= {"core", "non_core", "mixed"}
    assert {first[k].teaching_mode for k in keys} == {"SHARED", "INDEPENDENT"}
    p = await plan_for(db_session, sid, teacher.id)
    assert sum(t.core_periods + t.non_core_periods for t in rows) == p["topic_capacity"]
    snapshot = [(r.topic_key, r.core_periods, r.non_core_periods, r.independent_periods, r.origin, r.version) for r in rows]
    assert await ensure_defaults(db_session, teacher, sid, teacher.id, "2026-2027", 6, "Science") is False
    await db_session.commit()
    again = (await db_session.execute(select(TeacherTopicConfig).filter_by(school_id=sid, teacher_id=teacher.id,
        academic_year="2026-2027", grade=6, subject="Science").order_by(TeacherTopicConfig.topic_key))).scalars().all()
    assert snapshot == [(r.topic_key, r.core_periods, r.non_core_periods, r.independent_periods, r.origin, r.version) for r in again]
    approved = (await db_session.execute(select(TeacherPlan).filter_by(id="default-history-plan"))).scalars().one()
    assert approved.review == {"decision": "APPROVED"}


async def plan_for(db, sid, teacher_id):
    from backend.app.services.teacher_plan_service import build_plan
    result = await build_plan(db, sid, teacher_id, "2026-2027", 6, "Science")
    return result["capacity"]


@pytest.mark.asyncio
async def test_multi_item_over_capacity_save_writes_nothing(client, db_session):
    p = await plan(client, T1)
    a, b = p["topics"][0], p["topics"][1]
    body = {**MATH, "items": [
        {"topic_key": a["topic_key"], "core_periods": a["core_periods"] - 1, "non_core_periods": a["non_core_periods"]},  # valid on its own
        {"topic_key": b["topic_key"], "core_periods": b["core_periods"] + 500, "non_core_periods": b["non_core_periods"]},  # breaks capacity
    ]}
    events_before = len((await db_session.execute(select(PlanAuditEvent).filter_by(teacher_id="user-teacher-1", category="period_requirement"))).scalars().all())
    r = await client.put(f"{BASE}/user-teacher-1/requirements", json=body, headers=hdr(*T1))
    assert r.status_code == 422 and r.json()["detail"]["deficit"] > 0
    after = await plan(client, T1)
    assert [(t["core_periods"], t["non_core_periods"], t["version"]) for t in after["topics"]] == [(t["core_periods"], t["non_core_periods"], t["version"]) for t in p["topics"]]
    events_after = len((await db_session.execute(select(PlanAuditEvent).filter_by(teacher_id="user-teacher-1", category="period_requirement"))).scalars().all())
    assert events_after == events_before


@pytest.mark.asyncio
async def test_classification_change_is_audited_as_classification_and_teacher_specific(client):
    p = await plan(client, T2)
    t = next(x for x in p["topics"] if x["classification"] == "mixed")
    total = t["core_periods"] + t["non_core_periods"]
    body = {**MATH, "reason": "All Core this year", "items": [{"topic_key": t["topic_key"], "core_periods": total, "non_core_periods": 0, "classification": "core"}]}
    assert (await client.put(f"{BASE}/user-teacher-2/requirements", json=body, headers=hdr(*T2))).status_code == 200
    mine = await plan(client, T2)
    other = await plan(client, T1)
    got = next(x for x in mine["topics"] if x["topic_key"] == t["topic_key"])
    assert got["classification"] == "core" and got["origin"] == "teacher"
    assert next(x for x in other["topics"] if x["topic_key"] == t["topic_key"])["classification"] == "mixed"  # teacher 1 untouched
    logs = (await client.get("/api/v1/plan-logs", params={"category": "topic_classification", "teacher_id": "user-teacher-2"}, headers=hdr(*P1))).json()["items"]
    assert logs and logs[0]["previous_value"]["classification"] == "mixed" and logs[0]["new_value"]["classification"] == "core"
    # school isolation: school-3 teacher with the same topic is unaffected
    s3 = await plan(client, T3)
    assert next(x for x in s3["topics"] if x["topic_key"] == t["topic_key"])["classification"] == t["classification"]


def approved(core, non, status="APPROVED"):
    return {"status": status, "value": "MIXED", "corePeriods": core, "nonCorePeriods": non, "criteria": [], "rationale": "r", "evidence": "e",
            "proposedBy": {"id": "x", "name": "x", "role": "teacher"}, "proposedAt": "t", "history": []}


async def new_school(db, sid, teachers=1):
    db.add(School(id=sid, name=sid, location="x", state="x", infrastructure_tier="standard"))
    users = []
    for i in range(teachers):
        u = User(id=f"{sid}-t{i}", email=f"{sid}-t{i}@x.test", name="T", hashed_password="x", role="teacher", school_id=sid)
        db.add(u)
        users.append(u)
    await db.flush()
    for u in users:
        await ensure_defaults(db, u, sid, u.id, "2026-2027", 7, "Mathematics")
    return users


async def workspace(db, sid, classifications):
    s = empty_state()
    s["classifications"] = classifications
    db.add(PlanningWorkspaceRevision(school_id=sid, revision=1, action="CLASSIFICATION_REVIEW", summary="legacy", actor_id="x", actor_name="x", actor_role="principal", state=s))
    await db.commit()


@pytest.mark.asyncio
async def test_import_applies_only_unambiguous_approved_counts_and_is_idempotent(db_session):
    await new_school(db_session, "school-r1")
    await workspace(db_session, "school-r1", {
        "CH-gegp108-S8.1": approved(4, 2),
        "CH-gegp108-S8.2": approved(3, 3, status="PROPOSED"),  # never approved -> never imported
        "CH-unknown-S1": approved(1, 1),
    })
    rep = await import_workspace_requirements(db_session, "school-r1")
    assert rep["imported"] == ["XW-gegp108-S8.1"] and rep["skipped_not_approved"] == ["CH-gegp108-S8.2"] and rep["unknown_topic"] == ["CH-unknown-S1"]
    row = (await db_session.execute(select(TeacherTopicConfig).filter_by(school_id="school-r1", topic_key="XW-gegp108-S8.1"))).scalars().first()
    assert (row.core_periods, row.non_core_periods, row.origin) == (4, 2, "approved_import")
    other = (await db_session.execute(select(TeacherTopicConfig).filter_by(school_id="school-r1", topic_key="XW-gegp108-S8.2"))).scalars().first()
    assert other.origin == "demo_default"
    again = await import_workspace_requirements(db_session, "school-r1")
    assert again["imported"] == [] and again["skipped_existing"] == ["XW-gegp108-S8.1"]
    ev = (await db_session.execute(select(PlanAuditEvent).filter_by(school_id="school-r1", category="period_requirement"))).scalars().all()
    assert any("imported approved" in e.summary for e in ev)


@pytest.mark.asyncio
async def test_import_never_guesses_between_teachers_and_respects_capacity(db_session):
    await new_school(db_session, "school-r2", teachers=2)
    await new_school(db_session, "school-r3")
    await workspace(db_session, "school-r2", {"CH-gegp108-S8.1": approved(4, 2)})
    rep = await import_workspace_requirements(db_session, "school-r2")
    assert rep["imported"] == [] and len(rep["ambiguous"][0]["teachers"]) == 2
    await workspace(db_session, "school-r3", {"CH-gegp108-S8.1": approved(5000, 0)})
    assert (await import_workspace_requirements(db_session, "school-r3"))["over_capacity"] == ["XW-gegp108-S8.1"]


@pytest.mark.asyncio
async def test_import_never_overwrites_a_teacher_edit(client, db_session):
    users = await new_school(db_session, "school-r4")
    await db_session.commit()
    tok = {"Authorization": f"Bearer {create_access_token(users[0].id, school_id='school-r4', role='teacher')}", "X-School-Id": "school-r4"}
    p = (await client.get(f"{BASE}/{users[0].id}", params=MATH, headers=tok)).json()
    t = p["topics"][0]
    r = await client.put(f"{BASE}/{users[0].id}/requirements", json={**MATH, "items": [{"topic_key": t["topic_key"], "core_periods": t["core_periods"] - 1, "non_core_periods": t["non_core_periods"]}]}, headers=tok)
    assert r.status_code == 200
    await workspace(db_session, "school-r4", {"CH-" + t["topic_key"][3:]: approved(1, 1)})
    rep = await import_workspace_requirements(db_session, "school-r4")
    assert rep["imported"] == [] and rep["skipped_existing"] == [t["topic_key"]]
    after = (await client.get(f"{BASE}/{users[0].id}", params=MATH, headers=tok)).json()["topics"][0]
    assert after["core_periods"] == t["core_periods"] - 1 and after["origin"] == "teacher"


@pytest.mark.asyncio
async def test_workspace_http_cannot_create_a_conflicting_requirement(client, teacher_token, principal_token, admin_token):
    """The old document path is frozen: whatever it is sent, the relational values are the only ones that exist."""
    before = await plan(client, T1)
    rev = (await client.get(URL, headers=auth(teacher_token))).json()["revision"]
    s = with_audit(empty_state(), "CLASSIFICATION_PROPOSE")
    s["audit"] = [{"id": "a0"}] + s["audit"]
    s["classifications"] = {"CH-gegp108-S8.1": approved(1, 1)}
    for tok in (teacher_token, principal_token, admin_token):
        r = await save(client, tok, copy.deepcopy(s), rev, "CLASSIFICATION_PROPOSE", school="school-1")
        assert r.status_code == 410 and "requirements" in r.text
        smuggled = await save(client, tok, copy.deepcopy(s), rev, "PLANNING_DATE")
        assert smuggled.status_code == 403 and ("stored per teacher" in smuggled.text or "cannot perform PLANNING_DATE" in smuggled.text)  # a reviewer is stopped by the field freeze, a teacher by the role check
    assert await plan(client, T1) == before
