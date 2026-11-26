"""Planning workspace API: authority, concurrency, append-only history and role enforcement."""
import copy
import uuid

import pytest

from backend.app.core.security import create_access_token
from backend.app.services.planning_workspace_service import authorize_changes

URL = "/api/v1/planning/workspace"


def auth(token, school="school-1"):
    return {"Authorization": f"Bearer {token}", "X-School-Id": school}


def empty_state():
    return {
        "schemaVersion": 2,
        "config": {"year": "2026-2027"},
        "configHistory": [],
        "datasets": [],
        "classifications": {},
        "relationships": [],
        "plans": [],
        "audit": [],
    }


def with_audit(state, action, actor_name="client-claimed"):
    s = copy.deepcopy(state)
    s["audit"].append({"id": uuid.uuid4().hex, "at": "2026-11-10T00:00:00Z", "action": action, "summary": action, "actor": {"id": "x", "name": actor_name, "role": "admin"}})
    return s


def actor(uid, role):
    return {"id": uid, "name": uid, "role": role}


CFG = {"year": "2026-2027", "start": "2026-04-01", "end": "2026-04-30", "weekdays": [1, 2, 3, 4, 5],
       "entries": [{"id": "h", "type": "HOLIDAY", "label": "Holiday", "start": "2026-04-03", "end": "2026-04-03"}],
       "periodsPerDay": 8, "periodMinutes": 40, "subjectPeriodsPerDay": {"Mathematics": 2, "Science": 1}, "horizonDays": None}


def draft_plan(pid):
    return {
        "id": pid, "grade": 7, "subject": "Mathematics", "datasetId": "d", "createdBy": actor("t", "teacher"),
        "createdAt": "2026-11-10", "draft": {"lessons": [{"nodeId": "n1"}]}, "estimates": {"n1": 2},
        "config": {"year": "2026-2027"}, "status": "DRAFT", "versions": [], "execution": [], "evidence": [], "proposals": [],
    }


async def save(client, token, state, expected, action, school="school-1"):
    return await client.put(URL, headers=auth(token, school), json={"expected_revision": expected, "action": action, "summary": action, "state": state})


@pytest.mark.asyncio
async def test_full_workflow_roles_and_history(client, admin_token, principal_token, teacher_token, student_token):
    school = f"school-plan-{uuid.uuid4().hex[:6]}"
    admin_t = create_access_token("user-admin", school_id=school, role="admin")
    # Students have no access.
    assert (await client.get(URL, headers=auth(student_token))).status_code == 403

    # Admin saves configuration (admins may select any school context).
    res = await client.get(URL, headers=auth(admin_t, school))
    assert res.status_code == 200 and res.json()["revision"] == 0 and res.json()["state"] is None
    # (The calendar itself is versioned in school_plan_calendars now; the document still carries the reviewer-set planning date.)
    s1 = with_audit(empty_state(), "PLANNING_DATE")
    s1["asOf"] = "2026-04-01"
    res = await save(client, admin_t, s1, 0, "PLANNING_DATE", school)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["revision"] == 1
    # Server stamps the authenticated actor, ignoring the client-claimed name.
    assert body["state"]["audit"][-1]["actor"]["id"] == "user-admin"

    # Stale write is rejected.
    res = await save(client, admin_t, with_audit(body["state"], "PLANNING_DATE"), 0, "PLANNING_DATE", school)
    assert res.status_code == 409

    # Plans are no longer a workspace responsibility: a draft added to the document is refused for every role.
    s2 = with_audit(body["state"], "PLAN_DRAFT")
    s2["plans"].append(draft_plan("p1"))
    res = await save(client, admin_t, s2, 1, "PLAN_DRAFT", school)
    assert res.status_code == 410 and "POST /api/v1/teacher-plans/{teacher}/plans" in res.text  # the retired action is refused outright
    # ... and the same change smuggled under an action that is still allowed is refused by the field freeze
    s3 = with_audit(body["state"], "PLANNING_DATE")
    s3["plans"].append(draft_plan("p1"))
    res = await save(client, admin_t, s3, 1, "PLANNING_DATE", school)
    assert res.status_code == 403 and "stored per teacher" in res.text


@pytest.mark.asyncio
async def test_teacher_role_enforced_over_http(client, teacher_token, principal_token):
    res = await client.get(URL, headers=auth(principal_token))
    rev = res.json()["revision"]
    base = res.json()["state"] or empty_state()
    # Teachers cannot save the Academic Configuration.
    changed = with_audit(base, "PLANNING_DATE")
    changed["asOf"] = "2026-05-01"
    res = await save(client, teacher_token, changed, rev, "PLANNING_DATE")
    assert res.status_code == 403  # the planning date is a reviewer setting
    assert (await save(client, teacher_token, with_audit(base, "CONFIG_SAVE"), rev, "CONFIG_SAVE")).status_code == 410  # the calendar has its own API
    # Plans go to /api/v1/plans, not the document: a draft smuggled into the workspace is refused, and nothing is stored.
    s = with_audit(base, "PLAN_DRAFT")
    s["plans"].append(draft_plan(f"p-{uuid.uuid4().hex[:6]}"))
    res = await save(client, teacher_token, s, rev, "PLAN_DRAFT")
    assert res.status_code == 410
    hist = await client.get(URL + "/history", headers=auth(teacher_token))
    assert hist.status_code == 200 and all(h["action"] != "PLAN_DRAFT" for h in hist.json())


def approved_plan():
    p = draft_plan("p1")
    p.update(status="APPROVED", versions=[{"version": 1, "config": CFG, "lessons": [{"nodeId": "n1", "date": "2026-04-01"}]}],
             execution=[{"id": "e1", "nodeId": "n1", "status": "HOMEWORK"}],
             proposals=[{"id": "r1", "status": "PENDING", "baseVersion": 1, "lessons": []}])
    s = empty_state()
    s["plans"] = [p]
    s["audit"] = [{"id": "a0"}]
    return s


def test_workspace_plans_are_frozen_for_every_role_and_history_stays_readable():
    """Plans/versions/proposals/execution/evidence live in the relational plan tables (migration step 5)."""
    old = approved_plan()
    ops = {
        "rewrite the original schedule": lambda w: w["plans"][0]["versions"][0]["lessons"][0].update(date="2026-05-01"),
        "erase execution": lambda w: w["plans"][0].update(execution=[]),
        "remove the plan": lambda w: w.update(plans=[]),
        "approve a draft": lambda w: w["plans"][0].update(status="SUPERSEDED"),
        "decide a proposal": lambda w: w["plans"][0]["proposals"][0].update(status="APPROVED"),
        "append a version": lambda w: w["plans"][0]["versions"].append({"version": 2, "proposalId": "r1", "config": CFG, "lessons": []}),
        "add a new plan": lambda w: w["plans"].append(draft_plan("p2")),
        "append execution": lambda w: w["plans"][0]["execution"].append({"id": "e2", "nodeId": "n1", "status": "TAUGHT"}),
    }
    for name, op in ops.items():
        new = with_audit(old, "PLAN_REVIEW")
        op(new)
        for role in ("teacher", "principal", "admin"):
            assert any("stored per teacher" in v for v in authorize_changes(old, new, role)), (name, role)
    untouched = with_audit(old, "CONFIG_SAVE")
    assert all("stored per teacher" not in v for v in authorize_changes(old, untouched, "principal"))


def test_workspace_no_longer_accepts_classification_changes_but_keeps_history_readable():
    """Requirements live in teacher_topic_configs; the workspace cannot hold a conflicting copy (migration step 2)."""
    old = empty_state()
    old["audit"] = [{"id": "a0"}]
    old["classifications"]["n1"] = {"status": "APPROVED", "value": "CORE", "proposedBy": actor("u1", "principal"), "history": [{"action": "APPROVED"}]}
    untouched = with_audit(old, "CONFIG_SAVE")
    for role in ("teacher", "principal", "admin"):
        assert all("stored per teacher" not in v for v in authorize_changes(old, untouched, role))
    for action, mutate in (
        ("CLASSIFICATION_PROPOSE", lambda c: c.update({"n2": {"status": "PROPOSED", "value": "CORE", "proposedBy": actor("u1", "teacher"), "history": [{"action": "PROPOSED"}]}})),
        ("CLASSIFICATION_REVIEW", lambda c: c["n1"].update({"status": "REJECTED"})),
        ("CLASSIFICATION_REVIEW", lambda c: c.pop("n1")),
    ):
        new = with_audit(old, action)
        mutate(new["classifications"])
        for role in ("teacher", "principal", "admin"):
            assert any("stored per teacher" in v for v in authorize_changes(old, new, role)), (action, role)


def test_audit_entry_required_and_shape_validated():
    old = empty_state()
    same = copy.deepcopy(old)
    same["plans"].append(draft_plan("p9"))
    assert any("audit entry" in v for v in authorize_changes(old, same, "teacher"))


@pytest.mark.asyncio
async def test_unknown_action_and_bad_shape_rejected(client, admin_token):
    school = f"school-plan-{uuid.uuid4().hex[:6]}"
    res = await save(client, admin_token, with_audit(empty_state(), "X"), 0, "DROP_EVERYTHING", school)
    assert res.status_code == 422
    bad = with_audit(empty_state(), "PLANNING_DATE")
    bad["schemaVersion"] = 1
    res = await save(client, admin_token, bad, 0, "PLANNING_DATE", school)
    assert res.status_code == 422


def test_lost_period_records_are_frozen_in_the_workspace_and_history_stays_append_only():
    """Lost periods live in teacher_lost_periods (migration step 4). The document keeps history readable but accepts no change."""
    old = approved_plan()
    old["plans"][0]["losses"] = [{"id": "l1", "date": "2026-04-01", "periodsLost": 2, "reason": "Election Duties", "supersedes": None}]
    appended = with_audit(old, "LOSS_RECORD")
    appended["plans"][0]["losses"].append({"id": "l2", "date": "2026-04-01", "periodsLost": 1, "reason": "Election Duties", "supersedes": "l1"})
    for role in ("teacher", "admin", "principal"):
        assert any("stored per teacher" in v for v in authorize_changes(old, appended, role)), role
    # Editing or deleting an existing record is refused too.
    edited = with_audit(old, "LOSS_RECORD")
    edited["plans"][0]["losses"][0]["periodsLost"] = 0
    assert any("stored per teacher" in v for v in authorize_changes(old, edited, "admin"))
    erased = with_audit(old, "LOSS_RECORD")
    erased["plans"][0]["losses"] = []
    assert any("stored per teacher" in v for v in authorize_changes(old, erased, "teacher"))
    # An unrelated change leaves the historical losses untouched and is not blocked by this rule.
    untouched = with_audit(old, "CONFIG_SAVE")
    assert all("stored per teacher" not in v for v in authorize_changes(old, untouched, "principal"))


@pytest.mark.asyncio
async def test_loss_record_action_accepted_for_teacher(client, teacher_token):
    res = await client.get(URL, headers=auth(teacher_token))
    rev = res.json()["revision"]
    base = res.json()["state"] or empty_state()
    res = await save(client, teacher_token, with_audit(base, "LOSS_RECORD"), rev, "LOSS_RECORD")
    assert res.status_code == 410 and "lost-periods" in res.text  # lost periods are not a workspace write any more


@pytest.mark.asyncio
async def test_planning_never_falls_back_to_demo_admin_without_a_token(client):
    """DEMO_MODE resolves anonymous requests to an admin elsewhere; planning must always demand a real token."""
    assert (await client.get(URL)).status_code == 401
    assert (await client.get(URL + "/history")).status_code == 401
    body = {"expected_revision": 0, "action": "CONFIG_SAVE", "summary": "anon", "state": empty_state()}
    assert (await client.put(URL, json=body)).status_code == 401


def test_workspace_calendar_is_frozen_for_every_role_and_history_stays_readable():
    """The academic calendar lives in school_plan_calendars (migration step 6)."""
    old = empty_state()
    old["audit"] = [{"id": "a0"}]
    old["config"] = {"year": "2026-2027", "start": "2026-04-01", "end": "2027-03-31"}
    old["configHistory"] = [{"config": old["config"], "savedBy": actor("a", "admin"), "savedAt": "t"}]
    changed = with_audit(old, "CONFIG_SAVE")
    changed["config"] = {**old["config"], "end": "2027-03-30"}
    appended = with_audit(old, "CONFIG_SAVE")
    appended["configHistory"].append({"config": changed["config"], "savedBy": actor("a", "admin"), "savedAt": "t2"})
    for role in ("teacher", "principal", "admin"):
        for new in (changed, appended):
            assert any("stored as versions" in v for v in authorize_changes(old, new, role)), role
    untouched = with_audit(old, "CONFIG_SAVE")
    untouched["asOf"] = "2026-05-01"
    assert all("stored as versions" not in v for v in authorize_changes(old, untouched, "principal"))
