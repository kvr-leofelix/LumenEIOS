"""Step 7: one authoritative store per responsibility. The workspace document keeps only datasets and the planning date."""
import copy
import re
from pathlib import Path

import pytest

from backend.app.core.security import create_access_token
from backend.app.services.planning_workspace_service import ACTION_ROLES, MIGRATED_ACTIONS, authorize_changes
from backend.tests.test_planning_workspace import URL, actor, auth, draft_plan, empty_state, save, with_audit

APP = Path(__file__).resolve().parents[1] / "app"
ROLES = ("teacher", "principal", "admin")


def seeded_legacy():
    s = empty_state()
    s["audit"] = [{"id": "a0"}]
    s["config"] = {"year": "2026-2027", "start": "2026-04-01", "end": "2027-03-31"}
    s["configHistory"] = [{"config": s["config"], "savedBy": actor("a", "admin"), "savedAt": "t"}]
    s["classifications"] = {"n1": {"status": "APPROVED", "value": "CORE", "history": []}}
    s["relationships"] = [{"id": "r1", "type": "PREREQUISITE", "status": "APPROVED"}]
    s["coverage"] = {"n1": {"status": "DONE", "source": "MANUAL", "history": [{"status": "DONE"}]}}
    s["plans"] = [draft_plan("p1")]
    return s


MUTATIONS = {
    "config": lambda w: w["config"].update(end="2027-03-30"),
    "configHistory": lambda w: w["configHistory"].append({"config": {}, "savedBy": actor("a", "admin"), "savedAt": "t2"}),
    "classifications": lambda w: w["classifications"]["n1"].update(status="REJECTED"),
    "relationships": lambda w: w["relationships"].clear(),
    "coverage": lambda w: w["coverage"]["n1"].update(status="NOT_DONE"),
    "plans": lambda w: w["plans"].append(draft_plan("p2")),
}


@pytest.mark.parametrize("field", sorted(MUTATIONS))
@pytest.mark.parametrize("role", ROLES)
def test_every_migrated_field_is_frozen_for_every_role(field, role):
    old = seeded_legacy()
    new = with_audit(old, "PLANNING_DATE")
    MUTATIONS[field](new)
    violations = authorize_changes(old, new, role)
    assert any("stored" in v and "no longer accepts" in v for v in violations), (field, role, violations)


@pytest.mark.parametrize("role", ROLES)
def test_unchanged_legacy_history_passes_so_it_stays_readable(role):
    old = seeded_legacy()
    assert authorize_changes(old, with_audit(old, "PLANNING_DATE"), role) == [] or role == "teacher"  # teachers may not change the date, but the freeze never blocks reads
    same = copy.deepcopy(old)
    same["audit"] = old["audit"] + [{"id": "a1"}]
    assert all("no longer accepts" not in v for v in authorize_changes(old, same, role))


@pytest.mark.asyncio
@pytest.mark.parametrize("role,uid,school", [("teacher", "user-teacher-1", "school-1"), ("principal", "user-principal-1", "school-1"), ("admin", "user-admin", "school-1")])
async def test_every_retired_action_is_refused_with_the_replacement_named(client, role, uid, school):
    token = create_access_token(uid, school_id=school, role=role)
    rev = (await client.get(URL, headers=auth(token))).json()["revision"]
    for action, replacement in MIGRATED_ACTIONS.items():
        r = await save(client, token, with_audit(empty_state(), action), rev, action)
        assert r.status_code == 410, (action, role, r.text)
        assert replacement in r.text and "no longer writes the workspace document" in r.text
    assert set(MIGRATED_ACTIONS).isdisjoint(ACTION_ROLES)


@pytest.mark.asyncio
async def test_the_two_remaining_workspace_writes_still_work_and_history_is_unchanged(client):
    school = "school-1"  # principal and teacher belong to it; revisions are read, not assumed
    tok = {r: create_access_token(u, school_id=school, role=r) for r, u in (("admin", "user-admin"), ("principal", "user-principal-1"), ("teacher", "user-teacher-1"))}
    cur = (await client.get(URL, headers=auth(tok["admin"], school))).json()
    base = cur["state"] or empty_state()
    rev = cur["revision"]
    s1 = with_audit(base, "PLANNING_DATE")
    s1["asOf"] = "2026-06-01"
    # teachers cannot change the planning date; a principal and an admin can
    assert (await save(client, tok["teacher"], copy.deepcopy(s1), rev, "PLANNING_DATE", school)).status_code == 403
    ok = await save(client, tok["principal"], copy.deepcopy(s1), rev, "PLANNING_DATE", school)
    assert ok.status_code == 200 and ok.json()["state"]["asOf"] == "2026-06-01"
    s2 = with_audit(ok.json()["state"], "PLANNING_DATE")
    s2["asOf"] = "2026-06-02"
    second = await save(client, tok["admin"], copy.deepcopy(s2), rev + 1, "PLANNING_DATE", school)
    assert second.status_code == 200
    # only an admin imports syllabus datasets (built on the state the server returned, whose audit entries it stamped)
    stored = second.json()["state"]
    s3 = with_audit(stored, "SYLLABUS_IMPORT")
    s3["datasets"] = list(stored.get("datasets") or []) + [{"id": "d-single-store"}]
    assert (await save(client, tok["principal"], copy.deepcopy(s3), rev + 2, "SYLLABUS_IMPORT", school)).status_code == 403
    assert (await save(client, tok["admin"], copy.deepcopy(s3), rev + 2, "SYLLABUS_IMPORT", school)).status_code == 200
    final = (await client.get(URL, headers=auth(tok["admin"], school))).json()["state"]
    for f in ("coverage", "classifications", "relationships", "plans", "configHistory"):
        assert final.get(f) == base.get(f), f  # nothing migrated ever entered the document (absent in a fresh document, unchanged otherwise)
    hist = (await client.get(URL + "/history", headers=auth(tok["admin"], school))).json()
    assert [h["action"] for h in hist][:3] == ["SYLLABUS_IMPORT", "PLANNING_DATE", "PLANNING_DATE"]  # revisions are append-only history


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_only_the_workspace_endpoint_and_the_one_time_import_touch_workspace_revisions():
    """No relational service reads or writes the legacy document. Allowed: the model, its endpoint, the import, the demo-seed guard."""
    allowed = {"models/planning_workspace.py", "db/base.py", "api/v1/planning.py", "services/workspace_import.py", "seed/teacher_plan_demo.py", "services/syllabus_seed.py"}
    offenders = []
    for f in APP.rglob("*.py"):
        rel = f.relative_to(APP).as_posix()
        if "PlanningWorkspaceRevision" in _read(f) and rel not in allowed:
            offenders.append(rel)
    assert offenders == []


def test_relational_services_do_not_import_the_workspace_service():
    relational = ["teacher_plan_service", "plan_service", "lost_period_service", "relationship_service", "calendar_service", "annual_allocation", "workspace_import"]
    for name in relational:
        text = _read(APP / "services" / f"{name}.py")
        assert not re.search(r"^\s*(from|import)\s+backend\.app\.services\.planning_workspace_service", text, re.M), name
    assert "planning_workspace_service" not in _read(APP / "api/v1/teacher_planning.py") + _read(APP / "api/v1/plans.py")
    importing = re.compile(r"^\s*(from|import)\s+backend\.app\.services\.planning_workspace_service", re.M)
    users = [f.relative_to(APP).as_posix() for f in APP.rglob("*.py") if importing.search(_read(f)) and f.name != "planning_workspace_service.py"]
    assert users == ["api/v1/planning.py"]


def test_the_importer_is_the_only_reader_of_migrated_workspace_fields():
    """`state['plans'|'classifications'|...]` appears only in the import (and the field freeze itself)."""
    pattern = re.compile(r"""state\.get\(["'](plans|classifications|relationships|coverage|configHistory)["']\)|state\[["'](plans|classifications|relationships|coverage|configHistory)["']\]""")
    readers = sorted(f.relative_to(APP).as_posix() for f in APP.rglob("*.py") if pattern.search(_read(f)))
    assert readers == ["services/planning_workspace_service.py", "services/workspace_import.py"]
