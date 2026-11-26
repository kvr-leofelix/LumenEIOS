"""Coverage has one store: teacher_topic_coverage. The workspace document keeps legacy values readable but is frozen.

Rules that used to be enforced on the workspace (three statuses, two sources, roles, append-only history, stamped actor)
are enforced by the relational API and its audit table; they are tested in the second half of this file.
"""
import copy

import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.app.core.security import create_access_token
from backend.app.models.teacher_planning import TeacherTopicCoverage
from backend.app.seed.teacher_plan_demo import seed_teacher_plan_demo
from backend.app.services.planning_workspace_service import authorize_changes
from backend.tests.test_planning_workspace import URL, auth, empty_state, save, with_audit


def record(status, source="MANUAL"):
    e = {"at": "2026-11-11T10:00:00Z", "by": {"id": "t1", "name": "t1", "role": "teacher"}, "status": status, "source": source}
    return {"status": status, "source": source, "updatedAt": e["at"], "updatedBy": e["by"], "history": [e]}


def base():
    s = empty_state()
    s["audit"] = [{"id": "a0"}]
    return s


def test_documents_without_coverage_still_validate():
    old = base()
    new = with_audit(old, "CONFIG_SAVE")
    assert "coverage" not in new
    assert authorize_changes(old, new, "principal") == []


@pytest.mark.parametrize("role", ["teacher", "admin", "principal"])
def test_workspace_rejects_any_coverage_change_for_every_role(role):
    old = base()
    new = with_audit(old, "COVERAGE_UPDATE")
    new["coverage"] = {"topic-1": record("DONE")}
    assert any("stored per teacher" in m for m in authorize_changes(old, new, role))


def test_legacy_coverage_stays_readable_and_unchanged_documents_pass():
    old = base()
    old["coverage"] = {"topic-1": record("DONE")}
    new = with_audit(old, "CONFIG_SAVE")
    assert authorize_changes(old, new, "principal") == []
    removed = copy.deepcopy(new)
    removed["coverage"] = {}
    assert authorize_changes(old, removed, "principal")  # cannot silently drop it either


@pytest.mark.asyncio
async def test_workspace_http_refuses_coverage_writes(client, teacher_token):
    s = with_audit(base(), "COVERAGE_UPDATE")
    s["coverage"] = {"topic-1": record("IN_PROGRESS")}
    r = await save(client, teacher_token, s, 0, "COVERAGE_UPDATE")
    assert r.status_code == 410 and "teacher-plans" in r.text


# ------------------------------------------------------------ the relational store
def hdr(uid, role, school):
    return {"Authorization": f"Bearer {create_access_token(uid, school_id=school, role=role)}", "X-School-Id": school}


T1 = ("user-teacher-1", "teacher", "school-1")
T2 = ("user-teacher-2", "teacher", "school-1")
P1 = ("user-principal-1", "principal", "school-1")
A1 = ("user-admin", "admin", "school-1")
MATH = {"grade": 7, "subject": "Mathematics"}
URL_COV = "/api/v1/teacher-plans/user-teacher-1/coverage"


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="session")
async def seeded():
    from backend.app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        await seed_teacher_plan_demo(s)


async def first_topic(client):
    r = await client.get("/api/v1/teacher-plans/user-teacher-1", params=MATH, headers=hdr(*T1))
    return r.json()["topics"][1]["topic_key"]


@pytest.mark.asyncio
async def test_only_the_three_statuses_and_two_sources_are_accepted(client):
    k = await first_topic(client)
    ok = {**MATH, "topic_key": k}
    assert (await client.put(URL_COV, json={**ok, "status": "in_progress"}, headers=hdr(*T1))).status_code == 200
    assert (await client.put(URL_COV, json={**ok, "status": "DONE"}, headers=hdr(*T1))).status_code == 422
    assert (await client.put(URL_COV, json={**ok, "status": "done", "source": "ROBOT"}, headers=hdr(*T1))).status_code == 422
    r = await client.put(URL_COV, json={**ok, "status": "done", "source": "EXECUTION"}, headers=hdr(*T1))
    assert r.json()["source"] == "EXECUTION"


@pytest.mark.asyncio
async def test_teacher_sets_coverage_principal_admin_and_other_teacher_cannot(client):
    k = await first_topic(client)
    body = {**MATH, "topic_key": k, "status": "done"}
    for who in (P1, A1, T2):
        assert (await client.put(URL_COV, json=body, headers=hdr(*who))).status_code == 403


@pytest.mark.asyncio
async def test_every_change_is_one_stamped_audit_event_and_history_is_append_only(client):
    k = await first_topic(client)
    body = {**MATH, "topic_key": k}
    await client.put(URL_COV, json={**body, "status": "not_done"}, headers=hdr(*T1))
    await client.put(URL_COV, json={**body, "status": "in_progress"}, headers=hdr(*T1))
    await client.put(URL_COV, json={**body, "status": "in_progress"}, headers=hdr(*T1))  # no change: no event
    await client.put(URL_COV, json={**body, "status": "done"}, headers=hdr(*T1))
    items = (await client.get("/api/v1/plan-logs", params={"category": "coverage_status", "topic_key": k, "teacher_id": "user-teacher-1"}, headers=hdr(*P1))).json()["items"]
    chain = [(e["previous_value"]["status"], e["new_value"]["status"]) for e in reversed(items)]
    assert chain[-2:] == [("not_done", "in_progress"), ("in_progress", "done")]
    assert all(e["actor_id"] == "user-teacher-1" and e["actor_role"] == "teacher" for e in items)  # stamped by the server


@pytest.mark.asyncio
async def test_coverage_persists_in_the_relational_row(client, db_session):
    k = await first_topic(client)
    await client.put(URL_COV, json={**MATH, "topic_key": k, "status": "in_progress"}, headers=hdr(*T1))
    row = (await db_session.execute(select(TeacherTopicCoverage).filter_by(teacher_id="user-teacher-1", topic_key=k))).scalars().first()
    await db_session.refresh(row)
    assert row.status == "in_progress" and row.source == "MANUAL"
    other = (await db_session.execute(select(TeacherTopicCoverage).filter_by(teacher_id="user-teacher-2", topic_key=k))).scalars().first()
    assert other.status == "not_done"


@pytest.mark.asyncio
async def test_workspace_import_is_idempotent_unambiguous_and_never_overwrites(client, db_session):
    from backend.app.services.workspace_import import import_workspace_coverage
    school = "school-3"  # two teachers share Class VII Mathematics here -> ambiguous; Class VIII Science too
    ws = empty_state()
    ws["coverage"] = {"CH-gegp108-S8.1": record("DONE")}
    from backend.app.models.planning_workspace import PlanningWorkspaceRevision
    db_session.add(PlanningWorkspaceRevision(school_id=school, revision=1, action="COVERAGE_UPDATE", summary="legacy", actor_id="x", actor_name="x", actor_role="teacher", state=ws))
    await db_session.commit()
    rep = await import_workspace_coverage(db_session, school)
    assert rep["imported"] == [] and rep["ambiguous"][0]["topic"] == "XW-gegp108-S8.1" and len(rep["ambiguous"][0]["teachers"]) == 2
    assert (await import_workspace_coverage(db_session, school)) == rep


@pytest.mark.asyncio
async def test_workspace_import_happy_path_then_rerun_is_a_noop(client, db_session):
    from backend.app.models.entities import School, User
    from backend.app.models.planning_workspace import PlanningWorkspaceRevision
    from backend.app.services.teacher_plan_service import ensure_defaults
    from backend.app.services.workspace_import import import_workspace_coverage
    db_session.add(School(id="school-imp", name="Import School", location="x", state="x", infrastructure_tier="standard"))
    t = User(id="imp-teacher", email="imp@x.test", name="Imp", hashed_password="x", role="teacher", school_id="school-imp")
    db_session.add(t)
    await db_session.flush()
    assert await ensure_defaults(db_session, t, "school-imp", "imp-teacher", "2026-2027", 7, "Mathematics")
    ws = empty_state()
    ws["coverage"] = {"CH-gegp108-S8.1": record("DONE"), "CH-nope-S1": record("DONE")}
    db_session.add(PlanningWorkspaceRevision(school_id="school-imp", revision=1, action="COVERAGE_UPDATE", summary="legacy", actor_id="x", actor_name="x", actor_role="teacher", state=ws))
    await db_session.commit()
    rep = await import_workspace_coverage(db_session, "school-imp")
    assert rep["imported"] == ["XW-gegp108-S8.1"] and rep["unknown_topic"] == ["CH-nope-S1"]
    row = (await db_session.execute(select(TeacherTopicCoverage).filter_by(teacher_id="imp-teacher", topic_key="XW-gegp108-S8.1"))).scalars().first()
    assert row.status == "done"
    again = await import_workspace_coverage(db_session, "school-imp")
    assert again["imported"] == [] and again["skipped_existing"] == ["XW-gegp108-S8.1"]
