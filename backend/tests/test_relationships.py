"""Step 3: topic relationships live only in teacher_topic_relationships."""
import copy

import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.app.core.security import create_access_token
from backend.app.models.entities import School, User
from backend.app.models.planning_workspace import PlanningWorkspaceRevision
from backend.app.models.teacher_planning import PlanAuditEvent, TeacherTopicRelationship
from backend.app.seed.teacher_plan_demo import seed_teacher_plan_demo
from backend.app.services.planning_workspace_service import authorize_changes
from backend.app.services.teacher_plan_service import ensure_defaults
from backend.app.services.workspace_import import import_workspace_relationships
from backend.tests.test_planning_workspace import URL, auth, empty_state, save, with_audit


def hdr(uid, role, school):
    return {"Authorization": f"Bearer {create_access_token(uid, school_id=school, role=role)}", "X-School-Id": school}


T2, T3 = ("user-teacher-2", "teacher", "school-1"), ("user-teacher-3", "teacher", "school-3")
T1 = ("user-teacher-1", "teacher", "school-1")
P1, A1 = ("user-principal-1", "principal", "school-1"), ("user-admin", "admin", "school-1")
BASE = "/api/v1/teacher-plans"
M1, M2 = "XW-gegp108-S8.1", "XW-gegp108-S8.2"  # Class VII Mathematics
S1, S2 = "XW-hecu105-S5.4.1", "XW-hecu105-S5.4.2"  # Class VIII Science
EXPL = "Multiplication of fractions is needed before division of fractions."


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="session")
async def seeded():
    from backend.app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        await seed_teacher_plan_demo(s)


def pre(f, t, **kw):
    return {"kind": "PREREQUISITE", "from_key": f, "to_key": t, "explanation": EXPL, "evidence": "8.1 and 8.2 locators", **kw}


async def listing(client, who, teacher, **params):
    r = await client.get(f"{BASE}/{teacher}/relationships", params=params, headers=hdr(*who))
    assert r.status_code == 200, r.text
    return r.json()["items"]


@pytest.mark.asyncio
async def test_crud_audit_and_soft_removal(client):
    url = f"{BASE}/user-teacher-2/relationships"
    r = await client.post(url, json=pre(M1, M2), headers=hdr(*T2))
    assert r.status_code == 201 and r.json()["status"] == "active" and r.json()["origin"] == "teacher"
    rel = r.json()
    assert [i["id"] for i in await listing(client, T2, "user-teacher-2")] == [rel["id"]]
    d = await client.delete(f"{url}/{rel['id']}", params={"reason": "No longer needed"}, headers=hdr(*T2))
    assert d.status_code == 200 and d.json()["status"] == "removed"
    assert await listing(client, T2, "user-teacher-2") == []
    assert [i["status"] for i in await listing(client, T2, "user-teacher-2", include_removed=True)] == ["removed"]  # history kept
    again = await client.post(url, json=pre(M1, M2), headers=hdr(*T2))  # reactivates the same row
    assert again.status_code == 201 and again.json()["id"] == rel["id"]
    ev = (await client.get("/api/v1/plan-logs", params={"category": "topic_relationship", "teacher_id": "user-teacher-2"}, headers=hdr(*P1))).json()["items"]
    summaries = [e["summary"] for e in reversed(ev)]
    assert summaries == [f"prerequisite: {M1} -> {M2} added", f"prerequisite: {M1} -> {M2} removed", f"prerequisite: {M1} -> {M2} added"]
    assert ev[0]["new_value"]["status"] == "active" and ev[1]["previous_value"]["status"] == "active" and ev[1]["reason"] == "No longer needed"
    assert await client.delete(f"{url}/{rel['id']}", headers=hdr(*T2))  # leave it removed for the following tests
    assert await listing(client, T2, "user-teacher-2") == []


@pytest.mark.asyncio
async def test_validation_rules(client):
    url = f"{BASE}/user-teacher-2/relationships"
    bad = [
        (pre(M1, M1), "itself"),
        (pre(M1, M2, explanation="too short"), "20 characters"),
        (pre(M1, M2, evidence=" "), "Evidence"),
        (pre(M1, "XW-nope"), "exist"),
        (pre(M1, M2, kind="MAGIC"), "type"),
        (pre(S1, M1), "later class"),  # Class VIII Science before Class VII Mathematics
        (pre(M1, S1, kind="CROSS_CURRICULAR", shared_periods=2), "which unit teaches"),  # no lead named
        (pre(M1, M2, kind="CROSS_CURRICULAR"), "Mathematics and Science"),
        (pre(M1, S1, kind="CROSS_CURRICULAR", shared_periods=-1), "whole number"),
    ]
    for body, needle in bad:
        r = await client.post(url, json=body, headers=hdr(*T2))
        assert r.status_code == 422, (needle, r.text)
        assert needle in str(r.json()["detail"]), (needle, r.text)
    ok = await client.post(url, json=pre(M1, S1, kind="CROSS_CURRICULAR", shared_periods=2, lead_key=M1), headers=hdr(*T2))
    assert ok.status_code == 201 and ok.json()["lead_key"] == M1 and ok.json()["shared_periods"] == 2
    inverse = await client.post(url, json=pre(S1, M1, kind="CROSS_CURRICULAR", shared_periods=1, lead_key=S1), headers=hdr(*T2))
    assert inverse.status_code == 422 and "already exists" in str(inverse.json()["detail"])  # cross links are symmetric
    await client.delete(f"{url}/{ok.json()['id']}", headers=hdr(*T2))


@pytest.mark.asyncio
async def test_cycles_are_rejected_but_chains_and_removals_work(client):
    url = f"{BASE}/user-teacher-2/relationships"
    first = await client.post(url, json=pre(M1, M2), headers=hdr(*T2))
    assert first.status_code == 201
    loop = await client.post(url, json=pre(M2, M1), headers=hdr(*T2))
    assert loop.status_code == 422 and "cycle" in str(loop.json()["detail"])
    # after removing the first edge the reverse edge is legal
    await client.delete(f"{url}/{first.json()['id']}", headers=hdr(*T2))
    rev = await client.post(url, json=pre(M2, M1), headers=hdr(*T2))
    assert rev.status_code == 201
    await client.delete(f"{url}/{rev.json()['id']}", headers=hdr(*T2))


@pytest.mark.asyncio
async def test_ownership_roles_and_isolation(client):
    url = f"{BASE}/user-teacher-2/relationships"
    for who in (P1, A1, T1, T3):
        assert (await client.post(url, json=pre(M1, M2), headers=hdr(*who))).status_code == 403
    mine = await client.post(url, json=pre(M1, M2), headers=hdr(*T2))
    rid = mine.json()["id"]
    for who in (P1, A1, T1):
        assert (await client.delete(f"{url}/{rid}", headers=hdr(*who))).status_code == 403
    assert (await client.get(url, headers=hdr(*P1))).status_code == 200  # inspect only
    assert (await client.get(url, headers=hdr(*A1))).status_code == 200
    assert (await client.get(url, headers=hdr(*T1))).status_code == 403  # another teacher
    assert [i["id"] for i in await listing(client, T1, "user-teacher-1") if i["id"] == rid] == []  # teacher 1 unaffected
    other_school = await client.get(f"{BASE}/user-teacher-3/relationships", headers=hdr("user-principal-1", "principal", "school-1"))
    assert other_school.status_code == 404  # school isolation
    # a teacher may only relate topics from their own plans (teacher 3 has none removed; use an unknown owner topic)
    await client.delete(f"{url}/{rid}", headers=hdr(*T2))


@pytest.mark.asyncio
async def test_plan_prerequisites_follow_active_relationships_only(client):
    url = f"{BASE}/user-teacher-2/relationships"
    r = await client.post(url, json=pre(M1, M2), headers=hdr(*T2))
    plan = (await client.get(f"{BASE}/user-teacher-2", params={"grade": 7, "subject": "Mathematics"}, headers=hdr(*T2))).json()
    assert {t["topic_key"]: t["prerequisites"] for t in plan["topics"]}[M2] == [M1]
    await client.delete(f"{url}/{r.json()['id']}", headers=hdr(*T2))
    plan = (await client.get(f"{BASE}/user-teacher-2", params={"grade": 7, "subject": "Mathematics"}, headers=hdr(*T2))).json()
    assert {t["topic_key"]: t["prerequisites"] for t in plan["topics"]}[M2] == []


# ------------------------------------------------------------------ import
def ws_rel(rid, f, t, status="APPROVED", type_="PREREQUISITE", shared=0, lead=None):
    return {"id": rid, "type": type_, "fromNodeId": f, "toNodeId": t, "explanation": EXPL, "evidence": "locators", "sharedPeriods": shared,
            "leadNodeId": lead, "status": status, "proposedBy": {"id": "x", "name": "x", "role": "teacher"}, "proposedAt": "t"}


async def school_with(db, sid, teachers=1):
    db.add(School(id=sid, name=sid, location="x", state="x", infrastructure_tier="standard"))
    users = []
    for i in range(teachers):
        u = User(id=f"{sid}-t{i}", email=f"{sid}-t{i}@x.test", name="T", hashed_password="x", role="teacher", school_id=sid)
        db.add(u)
        users.append(u)
    await db.flush()
    for u in users:
        await ensure_defaults(db, u, sid, u.id, "2026-2027", 7, "Mathematics")
        await ensure_defaults(db, u, sid, u.id, "2026-2027", 8, "Science")
    return users


async def workspace(db, sid, rels):
    s = empty_state()
    s["relationships"] = rels
    db.add(PlanningWorkspaceRevision(school_id=sid, revision=1, action="RELATIONSHIP_REVIEW", summary="legacy", actor_id="x", actor_name="x", actor_role="principal", state=s))
    await db.commit()


@pytest.mark.asyncio
async def test_import_is_unambiguous_validated_idempotent_and_never_overwrites(client, db_session):
    users = await school_with(db_session, "school-q1")
    await workspace(db_session, "school-q1", [
        ws_rel("r1", "CH-gegp108-S8.1", "CH-gegp108-S8.2"),
        ws_rel("r2", "CH-gegp108-S8.2", "CH-gegp108-S8.1"),  # would close a cycle -> invalid, reported
        ws_rel("r3", "CH-gegp108-S8.1", "CH-hecu105-S5.4.1", type_="CROSS_CURRICULAR", shared=2, lead="CH-gegp108-S8.1"),
        ws_rel("r4", "CH-gegp108-S8.1", "CH-hecu105-S5.4.2", status="PROPOSED"),  # never approved
        ws_rel("r5", "CH-nope-S1", "CH-gegp108-S8.1"),
    ])
    rep = await import_workspace_relationships(db_session, "school-q1")
    assert rep["imported"] == ["r1", "r3"] and rep["skipped_not_approved"] == ["r4"] and rep["unknown_topic"] == ["r5"]
    assert [i["relationship"] for i in rep["invalid"]] == ["r2"] and any("cycle" in e for e in rep["invalid"][0]["errors"])
    rows = (await db_session.execute(select(TeacherTopicRelationship).filter_by(school_id="school-q1"))).scalars().all()
    assert {r.kind for r in rows} == {"PREREQUISITE", "CROSS_CURRICULAR"} and all(r.origin == "approved_import" for r in rows)
    ev = (await db_session.execute(select(PlanAuditEvent).filter_by(school_id="school-q1", category="topic_relationship"))).scalars().all()
    assert len(ev) == 2
    again = await import_workspace_relationships(db_session, "school-q1")
    assert again["imported"] == [] and again["skipped_existing"] == ["r1", "r3"] and [i["relationship"] for i in again["invalid"]] == ["r2"]
    assert len((await db_session.execute(select(TeacherTopicRelationship).filter_by(school_id="school-q1"))).scalars().all()) == 2
    # a link the teacher removed is a teacher decision: import must not bring it back
    tok = {"Authorization": f"Bearer {create_access_token(users[0].id, school_id='school-q1', role='teacher')}", "X-School-Id": "school-q1"}
    rid = next(r.id for r in rows if r.kind == "PREREQUISITE")
    assert (await client.delete(f"{BASE}/{users[0].id}/relationships/{rid}", headers=tok)).status_code == 200
    await import_workspace_relationships(db_session, "school-q1")
    gone = (await client.get(f"{BASE}/{users[0].id}/relationships", headers=tok)).json()["items"]
    assert not any(i["from_key"] == M1 and i["to_key"] == M2 for i in gone)  # the removed pair stays removed
    # (r2, the reverse pair, no longer closes a cycle once r1 is gone, so it may now import: a different link, still validated)


@pytest.mark.asyncio
async def test_import_never_guesses_between_two_teachers(db_session):
    await school_with(db_session, "school-q2", teachers=2)
    await workspace(db_session, "school-q2", [ws_rel("r1", "CH-gegp108-S8.1", "CH-gegp108-S8.2")])
    rep = await import_workspace_relationships(db_session, "school-q2")
    assert rep["imported"] == [] and len(rep["ambiguous"][0]["teachers"]) == 2
    assert (await db_session.execute(select(TeacherTopicRelationship).filter_by(school_id="school-q2"))).scalars().all() == []


@pytest.mark.asyncio
async def test_workspace_cannot_write_relationships_any_more(client, teacher_token, principal_token, admin_token):
    rev = (await client.get(URL, headers=auth(teacher_token))).json()["revision"]
    s = with_audit(empty_state(), "RELATIONSHIP_PROPOSE")
    s["audit"] = [{"id": "a0"}] + s["audit"]
    s["relationships"] = [ws_rel("rx", "CH-gegp108-S8.1", "CH-gegp108-S8.2", status="PROPOSED")]
    for tok in (teacher_token, principal_token, admin_token):
        r = await save(client, tok, copy.deepcopy(s), rev, "RELATIONSHIP_PROPOSE")
        assert r.status_code == 410 and "relationships" in r.text
        smuggled = await save(client, tok, copy.deepcopy(s), rev, "PLANNING_DATE")
        assert smuggled.status_code == 403 and ("stored per teacher" in smuggled.text or "cannot perform PLANNING_DATE" in smuggled.text)  # a reviewer is stopped by the field freeze, a teacher by the role check
    # historical values are still readable and unchanged documents still pass
    old = empty_state()
    old["audit"] = [{"id": "a0"}]
    old["relationships"] = [ws_rel("rx", "a", "b")]
    assert all("stored per teacher" not in v for v in authorize_changes(old, with_audit(old, "CONFIG_SAVE"), "principal"))
    removed = with_audit(old, "CONFIG_SAVE")
    removed["relationships"] = []
    assert any("stored per teacher" in v for v in authorize_changes(old, removed, "principal"))
