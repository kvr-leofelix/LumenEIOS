"""Step 5: plans, schedule versions, proposals, execution and evidence live in the relational teacher-plan tables."""
import copy

import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.app.core.security import create_access_token
from backend.app.models.entities import School, SchoolMembership, User
from backend.app.models.teacher_planning import (
    AppendOnlyError, PlanAuditEvent, SchoolPlanCalendar, TeacherLostPeriod, TeacherPlan, TeacherPlanExecution, TeacherPlanVersion,
)
from backend.app.seed.teacher_plan_demo import seed_teacher_plan_demo
from backend.app.services.teacher_plan_service import DEFAULT_CALENDAR, ensure_defaults

A, B = "CH-gegp108-S8.1", "CH-gegp108-S8.2"
CONFIG = {**DEFAULT_CALENDAR, "start": "2026-04-01", "end": "2026-04-30", "weekdays": [1, 2, 3, 4, 5], "entries": [], "horizonDays": 5,
          "subjectPeriodsPerDay": {"Mathematics": 2, "Science": 1}}
# instructional dates: 04-01 (Wed), 04-02, 04-03, 04-06, 04-07


def slot(d, p, k="CORE"):
    return {"date": d, "period": p, "kind": k}


def lesson(node, core, non, slots, independent=0, unscheduled=0):
    return {"nodeId": node, "title": node, "corePeriods": core, "nonCorePeriods": non, "requiredPeriods": core + non, "independentPeriods": independent,
            "unscheduledPeriods": unscheduled, "slots": slots, "classification": "MIXED", "classroomPeriods": len(slots) + unscheduled}


def lessons():
    return [
        lesson(A, 3, 1, [slot("2026-04-01", 1), slot("2026-04-01", 2), slot("2026-04-02", 1), slot("2026-04-02", 2, "NON_CORE")]),
        lesson(B, 2, 0, [slot("2026-04-03", 1), slot("2026-04-03", 2)]),
    ]


def draft_body(pid, ls=None, conflicts=None):
    return {"id": pid, "grade": 7, "subject": "Mathematics", "datasetId": "ds", "datasetLabel": "Dataset", "datasetKind": "VERIFIED", "config": CONFIG,
            "estimates": {A: 4, B: 2}, "draft": {"lessons": ls or lessons(), "metrics": {"requiredPeriods": 6}, "conflicts": conflicts or []}}


def proposal_body(pid, base=1, kind="LOST_PERIODS", lost=None, ls=None):
    ls = ls or [lesson(A, 3, 1, [slot("2026-04-01", 1), slot("2026-04-02", 1), slot("2026-04-02", 2, "NON_CORE"), slot("2026-04-06", 1)]), lessons()[1]]
    return {"id": pid, "baseVersion": base, "trigger": {"kind": kind}, "config": CONFIG, "lessons": ls, "metrics": {"requiredPeriods": 6},
            "conflicts": [], "changes": [{"nodeId": A, "kind": "REQUEUED"}], "explanation": ["Core recovered"], "lostSlots": lost if lost is not None else [{"date": "2026-04-01", "period": 2}]}


def hdr(uid, role, school):
    return {"Authorization": f"Bearer {create_access_token(uid, school_id=school, role=role)}", "X-School-Id": school}


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="session")
async def seeded():
    from backend.app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        await seed_teacher_plan_demo(s)


async def make_school(db, sid, teachers=2):
    db.add(School(id=sid, name=sid, location="x", state="x", infrastructure_tier="standard"))
    db.add(SchoolPlanCalendar(school_id=sid, academic_year="2026-2027", version=1, created_by="test", config={**CONFIG, "horizonDays": None}))
    out = []
    for i in range(teachers):
        u = User(id=f"{sid}-t{i}", email=f"{sid}-t{i}@x.test", name=f"Teacher {i}", hashed_password="x", role="teacher", school_id=sid)
        db.add(u)
        out.append(u)
    pr = User(id=f"{sid}-p", email=f"{sid}-p@x.test", name="Principal", hashed_password="x", role="principal", school_id=sid)
    db.add(pr)
    db.add(SchoolMembership(user_id=pr.id, school_id=sid, role="principal"))
    await db.flush()
    for u in out:
        await ensure_defaults(db, u, sid, u.id, "2026-2027", 7, "Mathematics")
    await db.commit()
    return [u.id for u in out], pr.id


class Ctx:
    def __init__(self, client, sid, t0, t1, pr):
        self.c, self.sid, self.t0, self.t1, self.pr = client, sid, t0, t1, pr

    def h(self, who):
        role = "principal" if who == self.pr else "teacher"
        return hdr(who, role, self.sid)

    async def draft(self, teacher, pid, **kw):
        return await self.c.post(f"/api/v1/teacher-plans/{teacher}/plans", json=draft_body(pid, **kw), headers=self.h(teacher))

    async def approve(self, pid, note=""):
        return await self.c.post(f"/api/v1/plans/{pid}/review", json={"decision": "APPROVED", "note": note}, headers=self.h(self.pr))

    async def plans(self, who, **params):
        r = await self.c.get("/api/v1/plans", params=params, headers=self.h(who))
        assert r.status_code == 200, r.text
        return r.json()["plans"]


@pytest_asyncio.fixture
async def ctx(client, db_session, request):
    sid = f"school-p{abs(hash(request.node.name)) % 10**7}"
    (t0, t1), pr = await make_school(db_session, sid)
    return Ctx(client, sid, t0, t1, pr)


@pytest.mark.asyncio
async def test_draft_isolation_and_roles(ctx):
    r = await ctx.draft(ctx.t0, "plan-iso-a")
    assert r.status_code == 201, r.text
    assert (await ctx.draft(ctx.t0, "plan-iso-a")).status_code == 409
    # another teacher cannot create into t0's plan space, a principal cannot create a teacher's plan
    assert (await ctx.c.post(f"/api/v1/teacher-plans/{ctx.t0}/plans", json=draft_body("plan-iso-x"), headers=ctx.h(ctx.t1))).status_code == 403
    assert (await ctx.c.post(f"/api/v1/teacher-plans/{ctx.t0}/plans", json=draft_body("plan-iso-y"), headers=ctx.h(ctx.pr))).status_code == 403
    assert (await ctx.draft(ctx.t1, "plan-iso-b")).status_code == 201
    assert [p["id"] for p in await ctx.plans(ctx.t0)] == ["plan-iso-a"]  # each teacher sees only their own
    assert [p["id"] for p in await ctx.plans(ctx.t1)] == ["plan-iso-b"]
    both = await ctx.plans(ctx.pr)
    assert {(p["id"], p["teacherId"]) for p in both} == {("plan-iso-a", ctx.t0), ("plan-iso-b", ctx.t1)}  # reviewer sees both, separately
    assert [p["id"] for p in await ctx.plans(ctx.pr, teacher_id=ctx.t1)] == ["plan-iso-b"]
    # school isolation: a principal of another school cannot see them
    other = await ctx.c.get("/api/v1/plans", headers=hdr("user-principal-1", "principal", ctx.sid))
    assert other.status_code == 403
    mine = (await ctx.c.get("/api/v1/plans", headers=hdr("user-principal-1", "principal", "school-1"))).json()["plans"]
    assert all(p["schoolId"] == "school-1" for p in mine)
    p = (await ctx.plans(ctx.t0))[0]
    assert p["status"] == "DRAFT" and p["versions"] == [] and p["createdBy"]["id"] == ctx.t0  # actor stamped by the server


@pytest.mark.asyncio
async def test_invalid_drafts_are_rejected(ctx):
    bad_date = lessons()
    bad_date[1]["slots"][0]["date"] = "2026-04-04"  # a Saturday
    dup = lessons()
    dup[1]["slots"][0] = slot("2026-04-01", 1)  # same period as topic A
    wrong_total = lessons()
    wrong_total[0]["requiredPeriods"] = 9
    for i, ls in enumerate((bad_date, dup, wrong_total)):
        r = await ctx.draft(ctx.t0, f"plan-bad-{i}", ls=ls)
        assert r.status_code == 422 and r.json()["detail"]["errors"], r.text
    assert (await ctx.c.post(f"/api/v1/teacher-plans/{ctx.t0}/plans", json={**draft_body("plan-bad-x"), "subject": "History"}, headers=ctx.h(ctx.t0))).status_code == 422
    assert await ctx.plans(ctx.t0) == []


@pytest.mark.asyncio
async def test_approval_builds_version_one_server_side_and_is_audited(ctx, db_session):
    await ctx.draft(ctx.t0, "plan-ap")
    # a teacher cannot approve; a reviewer must give a reason to reject; blocked drafts cannot be approved
    assert (await ctx.c.post("/api/v1/plans/plan-ap/review", json={"decision": "APPROVED"}, headers=ctx.h(ctx.t0))).status_code == 403
    assert (await ctx.c.post("/api/v1/plans/plan-ap/review", json={"decision": "REJECTED", "note": "no"}, headers=ctx.h(ctx.pr))).status_code == 422
    await ctx.draft(ctx.t1, "plan-blocked", conflicts=[{"code": "REQUIREMENT_MISSING", "severity": "error", "message": "x", "nodeIds": []}])
    blocked = await ctx.approve("plan-blocked")
    assert blocked.status_code == 422 and "requirements" in str(blocked.json()["detail"])
    ok = await ctx.approve("plan-ap", "Looks right")
    assert ok.status_code == 200 and ok.json()["version"] == 1
    again = await ctx.approve("plan-ap")
    assert again.status_code == 409  # only drafts can be decided
    plan = (await ctx.plans(ctx.t0))[0]
    assert plan["status"] == "APPROVED" and plan["review"]["decision"] == "APPROVED" and plan["review"]["by"]["id"] == ctx.pr
    v1 = plan["versions"][0]
    assert v1["version"] == 1 and v1["lessons"] == lessons() and v1["proposalId"] is None and v1["approvedBy"]["role"] == "principal"
    ev = (await ctx.c.get("/api/v1/plan-logs", params={"teacher_id": ctx.t0}, headers=ctx.h(ctx.pr))).json()["items"]
    cats = {e["category"]: e for e in ev}
    assert {"plan_draft", "plan_approval", "schedule_version"} <= set(cats)
    assert cats["plan_approval"]["schedule_version"] == 1 and cats["plan_approval"]["previous_value"]["status"] == "DRAFT" and cats["plan_approval"]["reason"] == "Looks right"
    assert cats["schedule_version"]["related_event_id"] == cats["plan_approval"]["id"]
    # versions are append-only at the model level
    row = (await db_session.execute(select(TeacherPlanVersion).filter_by(plan_id="plan-ap"))).scalars().first()
    row.reason = "tampered"
    with pytest.raises(AppendOnlyError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_rejected_draft_changes_nothing_and_new_approval_supersedes_the_old_plan(ctx):
    await ctx.draft(ctx.t0, "plan-r1")
    rej = await ctx.c.post("/api/v1/plans/plan-r1/review", json={"decision": "REJECTED", "note": "Please rework the order"}, headers=ctx.h(ctx.pr))
    assert rej.status_code == 200
    p = (await ctx.plans(ctx.t0))[0]
    assert p["status"] == "REJECTED" and p["versions"] == [] and p["review"]["note"] == "Please rework the order"
    await ctx.draft(ctx.t0, "plan-r2")
    await ctx.approve("plan-r2")
    await ctx.draft(ctx.t0, "plan-r3")
    await ctx.approve("plan-r3")
    by_id = {x["id"]: x for x in await ctx.plans(ctx.t0)}
    assert by_id["plan-r2"]["status"] == "SUPERSEDED" and by_id["plan-r2"]["supersededBy"] == "plan-r3"
    assert by_id["plan-r2"]["versions"][0]["lessons"] == lessons()  # history preserved
    assert by_id["plan-r3"]["status"] == "APPROVED" and by_id["plan-r1"]["status"] == "REJECTED"


async def approved(ctx, teacher, pid):
    await ctx.draft(teacher, pid)
    r = await ctx.approve(pid)
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_scheduled_is_not_taught_and_homework_is_not_classroom_teaching(ctx):
    await approved(ctx, ctx.t0, "plan-ex")
    ov = lambda: ctx.c.get("/api/v1/plan-oversight/planning", headers=ctx.h(ctx.pr))
    row = next(r for r in (await ov()).json()["rows"] if r["teacher_id"] == ctx.t0 and r["subject"] == "Mathematics")
    assert (row["required_periods"], row["scheduled_periods"], row["taught_periods"], row["outstanding_core_periods"]) == (row["required_periods"], 6, 0, 5)
    assert row["approval_status"] == "APPROVED" and row["schedule_version"] == 1 and row["pending_proposals"] == 0
    ex = f"/api/v1/plans/plan-ex/execution"
    ev = lambda i, node, date, status, **kw: {"id": i, "nodeId": node, "date": date, "status": status, "periodsTaught": kw.get("n", 0), "note": kw.get("note", ""), "supersedes": kw.get("sup")}
    # owner only, instructional days only, units of the schedule only
    assert (await ctx.c.post(ex, json=ev("e0", A, "2026-04-01", "TAUGHT"), headers=ctx.h(ctx.t1))).status_code == 403
    assert (await ctx.c.post(ex, json=ev("e0", A, "2026-04-01", "TAUGHT"), headers=ctx.h(ctx.pr))).status_code == 403
    assert (await ctx.c.post(ex, json=ev("e0", A, "2026-04-04", "TAUGHT"), headers=ctx.h(ctx.t0))).status_code == 422
    assert (await ctx.c.post(ex, json=ev("e0", "CH-nope", "2026-04-01", "TAUGHT"), headers=ctx.h(ctx.t0))).status_code == 422
    assert (await ctx.c.post(ex, json=ev("e0", A, "2026-04-01", "MAGIC"), headers=ctx.h(ctx.t0))).status_code == 422
    # homework for B: assigned, not taught
    assert (await ctx.c.post(ex, json=ev("e1", B, "2026-04-03", "HOMEWORK"), headers=ctx.h(ctx.t0))).status_code == 201
    row = next(r for r in (await ov()).json()["rows"] if r["teacher_id"] == ctx.t0 and r["subject"] == "Mathematics")
    assert row["taught_periods"] == 0 and row["scheduled_periods"] == 6
    # evidence needs a taught unit
    evd = {"id": "ev1", "nodeId": A, "kind": "ASSESSMENT", "reference": "Quiz 1", "result": "80%"}
    assert (await ctx.c.post("/api/v1/plans/plan-ex/evidence", json=evd, headers=ctx.h(ctx.t0))).status_code == 422
    # A is taught: its 4 classroom periods count, B's Core is still outstanding
    assert (await ctx.c.post(ex, json=ev("e2", A, "2026-04-02", "TAUGHT"), headers=ctx.h(ctx.t0))).status_code == 201
    row = next(r for r in (await ov()).json()["rows"] if r["teacher_id"] == ctx.t0 and r["subject"] == "Mathematics")
    assert (row["taught_periods"], row["outstanding_core_periods"]) == (4, 2)
    assert (await ctx.c.post("/api/v1/plans/plan-ex/evidence", json=evd, headers=ctx.h(ctx.t0))).status_code == 201
    assert (await ctx.c.post("/api/v1/plans/plan-ex/evidence", json=evd, headers=ctx.h(ctx.t0))).status_code == 409  # same id
    # a correction must supersede a current record of the same unit
    assert (await ctx.c.post(ex, json=ev("e3", B, "2026-04-03", "PARTIAL", n=1, sup="e2"), headers=ctx.h(ctx.t0))).status_code == 422
    assert (await ctx.c.post(ex, json=ev("e4", B, "2026-04-03", "PARTIAL", n=1, sup="e1"), headers=ctx.h(ctx.t0))).status_code == 201
    assert (await ctx.c.post(ex, json=ev("e5", B, "2026-04-03", "TAUGHT", sup="e1"), headers=ctx.h(ctx.t0))).status_code == 422  # e1 already superseded
    row = next(r for r in (await ov()).json()["rows"] if r["teacher_id"] == ctx.t0 and r["subject"] == "Mathematics")
    assert row["taught_periods"] == 5
    # the other teacher's row is untouched and has no approved schedule: figures are null, not zero
    other = next(r for r in (await ov()).json()["rows"] if r["teacher_id"] == ctx.t1 and r["subject"] == "Mathematics")
    assert other["scheduled_periods"] is None and other["taught_periods"] is None and other["schedule_version"] is None and other["approval_status"] == "NO_PLAN"
    cats = [e["category"] for e in (await ctx.c.get("/api/v1/plan-logs", params={"category": "teaching_execution", "teacher_id": ctx.t0}, headers=ctx.h(ctx.pr))).json()["items"]]
    assert len(cats) >= 4


@pytest.mark.asyncio
async def test_proposal_lifecycle_approval_creates_version_and_freezes_lost_periods(ctx, db_session):
    await approved(ctx, ctx.t0, "plan-pr")
    lost = await ctx.c.post(f"/api/v1/teacher-plans/{ctx.t0}/lost-periods", json={"grade": 7, "subject": "Mathematics", "date": "2026-04-01", "periods": [2], "reason_code": "Health Drive"}, headers=ctx.h(ctx.t0))
    assert lost.status_code == 201, lost.text
    url = "/api/v1/plans/plan-pr/proposals"
    # who may propose; invalid / stale proposals are refused
    assert (await ctx.c.post(url, json=proposal_body("pr-x"), headers=ctx.h(ctx.t1))).status_code == 403
    assert (await ctx.c.post(url, json=proposal_body("pr-x", base=7), headers=ctx.h(ctx.t0))).status_code == 409
    broken = proposal_body("pr-x")
    broken["lessons"][1]["slots"][0] = slot("2026-04-01", 1)
    assert (await ctx.c.post(url, json=broken, headers=ctx.h(ctx.t0))).status_code == 422
    reduced = proposal_body("pr-x")
    reduced["lessons"][0]["corePeriods"] = 2
    reduced["lessons"][0]["requiredPeriods"] = 3
    assert (await ctx.c.post(url, json=reduced, headers=ctx.h(ctx.t0))).status_code == 422  # approved Core may not be reduced
    p1 = await ctx.c.post(url, json=proposal_body("pr-1"), headers=ctx.h(ctx.t0))
    assert p1.status_code == 201 and p1.json()["status"] == "PENDING"
    plan = (await ctx.plans(ctx.t0))[0]
    assert len(plan["versions"]) == 1  # generating a proposal does not change the approved schedule
    p2 = await ctx.c.post(url, json=proposal_body("pr-2"), headers=ctx.h(ctx.t0))
    assert p2.status_code == 201
    by = {x["id"]: x for x in (await ctx.plans(ctx.t0))[0]["proposals"]}
    assert (by["pr-1"]["status"], by["pr-2"]["status"]) == ("SUPERSEDED", "PENDING")  # older pending proposal kept as superseded
    # a teacher cannot decide; rejection needs a reason and leaves the schedule alone
    assert (await ctx.c.post(f"{url}/pr-2/review", json={"decision": "APPROVED"}, headers=ctx.h(ctx.t0))).status_code == 403
    assert (await ctx.c.post(f"{url}/pr-2/review", json={"decision": "REJECTED", "note": "x"}, headers=ctx.h(ctx.pr))).status_code == 422
    assert (await ctx.c.post(f"{url}/pr-1/review", json={"decision": "APPROVED"}, headers=ctx.h(ctx.pr))).status_code == 409  # superseded
    p3 = await ctx.c.post(url, json=proposal_body("pr-3"), headers=ctx.h(ctx.t0))
    rej = await ctx.c.post(f"{url}/pr-3/review", json={"decision": "REJECTED", "note": "Use the Saturday class"}, headers=ctx.h(ctx.pr))
    assert p3.status_code == 201 and rej.status_code == 200
    plan = (await ctx.plans(ctx.t0))[0]
    assert len(plan["versions"]) == 1 and {x["id"]: x["status"] for x in plan["proposals"]}["pr-3"] == "REJECTED"
    assert next(x for x in plan["proposals"] if x["id"] == "pr-3")["review"]["note"] == "Use the Saturday class"
    # approve a fresh one: exactly one new version, built from the stored proposal; version 1 is untouched
    await ctx.c.post(url, json=proposal_body("pr-4"), headers=ctx.h(ctx.t0))
    ov = (await ctx.c.get("/api/v1/plan-oversight/planning", headers=ctx.h(ctx.pr))).json()["rows"]
    assert next(r for r in ov if r["teacher_id"] == ctx.t0)["pending_proposals"] == 1
    # the lost period can still be withdrawn while nothing absorbed it
    ok = await ctx.c.post(f"{url}/pr-4/review", json={"decision": "APPROVED", "note": "Approved"}, headers=ctx.h(ctx.pr))
    assert ok.status_code == 200 and ok.json()["version"] == 2
    plan = (await ctx.plans(ctx.t0))[0]
    assert [v["version"] for v in plan["versions"]] == [1, 2]
    assert plan["versions"][0]["lessons"] == lessons() and plan["versions"][1]["proposalId"] == "pr-4" and plan["versions"][1]["lostSlots"] == [{"date": "2026-04-01", "period": 2}]
    assert (await ctx.c.post(f"{url}/pr-4/review", json={"decision": "APPROVED"}, headers=ctx.h(ctx.pr))).status_code == 409
    # the approved recovery froze the lost period it absorbed
    row = (await db_session.execute(select(TeacherLostPeriod).filter_by(teacher_id=ctx.t0, lost_date="2026-04-01"))).scalars().first()
    await db_session.refresh(row)
    assert row.schedule_version == 2
    w = await ctx.c.post(f"/api/v1/teacher-plans/{ctx.t0}/lost-periods/withdraw", json={"grade": 7, "subject": "Mathematics", "date": "2026-04-01", "periods": [2], "reason": "Changed my mind"}, headers=ctx.h(ctx.t0))
    assert w.status_code == 409 and "approved recovery" in w.text
    # a proposal built on version 1 is now stale
    stale = await ctx.c.post(url, json=proposal_body("pr-5", base=1), headers=ctx.h(ctx.t0))
    assert stale.status_code == 409
    # the audit trail carries the whole story with versions and proposal ids
    items = (await ctx.c.get("/api/v1/plan-logs", params={"teacher_id": ctx.t0, "limit": 200}, headers=ctx.h(ctx.pr))).json()["items"]
    cats = [e["category"] for e in items]
    for c in ("recovery_proposal", "recovery_rejection", "recovery_approval", "schedule_version"):
        assert c in cats, c
    appr = next(e for e in items if e["category"] == "recovery_approval")
    assert appr["schedule_version"] == 2 and appr["related_proposal_id"] == "pr-4" and appr["previous_value"]["version"] == 1
    # contextual history: filtering by proposal id and by version returns the same events as the central log
    by_prop = (await ctx.c.get("/api/v1/plan-logs", params={"proposal_id": "pr-4"}, headers=ctx.h(ctx.pr))).json()["items"]
    assert {e["id"] for e in by_prop} <= {e["id"] for e in items} and {"recovery_proposal", "recovery_approval", "schedule_version"} <= {e["category"] for e in by_prop}
    by_ver = (await ctx.c.get("/api/v1/plan-logs", params={"schedule_version": 2, "teacher_id": ctx.t0}, headers=ctx.h(ctx.pr))).json()["items"]
    assert by_ver and all(e["schedule_version"] == 2 for e in by_ver)


@pytest.mark.asyncio
async def test_supersede_pending_and_non_owner_cannot(ctx):
    await approved(ctx, ctx.t0, "plan-sp")
    await ctx.c.post("/api/v1/plans/plan-sp/proposals", json=proposal_body("sp-1"), headers=ctx.h(ctx.t0))
    assert (await ctx.c.post("/api/v1/plans/plan-sp/proposals/supersede", json={"reason": "x"}, headers=ctx.h(ctx.t1))).status_code == 403
    r = await ctx.c.post("/api/v1/plans/plan-sp/proposals/supersede", json={"reason": "Nothing remains to change"}, headers=ctx.h(ctx.t0))
    assert r.status_code == 200 and r.json()["superseded"] == ["sp-1"]
    assert (await ctx.plans(ctx.t0))[0]["proposals"][0]["status"] == "SUPERSEDED"
    assert (await ctx.c.get("/api/v1/plans/plan-sp", headers=ctx.h(ctx.t0))).status_code in (404, 405)


@pytest.mark.asyncio
async def test_plans_in_one_school_never_leak_into_another(client, ctx, db_session):
    await ctx.draft(ctx.t0, "plan-leak")
    r = await client.post("/api/v1/plans/plan-leak/review", json={"decision": "APPROVED"}, headers=hdr("user-principal-1", "principal", "school-1"))
    assert r.status_code == 404  # school-1's principal cannot even see another school's plan
    assert (await client.post("/api/v1/plans/plan-leak/execution", json={"id": "x"}, headers=hdr("user-teacher-1", "teacher", "school-1"))).status_code == 404
    assert (await db_session.execute(select(TeacherPlan).filter_by(id="plan-leak"))).scalars().first().status == "DRAFT"


@pytest.mark.asyncio
async def test_execution_rows_are_append_only(ctx, db_session):
    await approved(ctx, ctx.t0, "plan-ao")
    await ctx.c.post("/api/v1/plans/plan-ao/execution", json={"id": "ao1", "nodeId": A, "date": "2026-04-01", "status": "PARTIAL", "periodsTaught": 1}, headers=ctx.h(ctx.t0))
    row = (await db_session.execute(select(TeacherPlanExecution).filter_by(id="ao1"))).scalars().first()
    row.status = "TAUGHT"
    with pytest.raises(AppendOnlyError):
        await db_session.flush()
    await db_session.rollback()
    row = (await db_session.execute(select(TeacherPlanExecution).filter_by(id="ao1"))).scalars().first()
    await db_session.delete(row)
    with pytest.raises(AppendOnlyError):
        await db_session.flush()
    await db_session.rollback()


# ------------------------------------------------------------------ import
def ws_plan(pid, status="APPROVED", by=None, versions=True, proposals=None, execution=None, ls=None):
    ls = ls or lessons()
    ver = {"version": 1, "lessons": ls, "metrics": {}, "conflicts": [], "config": CONFIG, "approvedBy": {"id": "pr", "name": "P", "role": "principal"},
           "approvedAt": "2026-04-01T00:00:00Z", "reason": "Initial schedule approved", "proposalId": None}
    return {"id": pid, "grade": 7, "subject": "Mathematics", "datasetId": "ds", "datasetLabel": "D", "datasetKind": "VERIFIED", "createdBy": by or {"id": "x", "name": "x", "role": "teacher"},
            "createdAt": "2026-03-30T00:00:00Z", "config": CONFIG, "estimates": {}, "status": status, "draft": {"lessons": ls, "metrics": {}, "conflicts": []},
            "versions": [ver] if versions else [], "review": {"by": {"id": "pr", "name": "P", "role": "principal"}, "at": "t", "note": "", "decision": status} if status != "DRAFT" else None,
            "execution": execution or [], "evidence": [], "proposals": proposals or [], "losses": []}


async def workspace(db, sid, plans):
    from backend.app.models.planning_workspace import PlanningWorkspaceRevision
    from backend.tests.test_planning_workspace import empty_state
    st = empty_state()
    st["plans"] = plans
    db.add(PlanningWorkspaceRevision(school_id=sid, revision=1, action="PLAN_REVIEW", summary="legacy", actor_id="x", actor_name="x", actor_role="principal", state=st))
    await db.commit()


@pytest.mark.asyncio
async def test_import_copies_history_untouched_and_is_idempotent(ctx, db_session):
    from backend.app.services.workspace_import import import_workspace_plans
    prop = {"id": "pp1", "status": "REJECTED", "baseVersion": 1, "trigger": {"kind": "LOST_PERIODS"}, "createdBy": {"id": "x", "name": "x", "role": "teacher"}, "createdAt": "t",
            "lessons": lessons(), "config": CONFIG, "metrics": {}, "conflicts": [], "changes": [], "explanation": ["e"], "review": {"by": {"id": "pr", "name": "P", "role": "principal"}, "at": "t", "note": "Use the Saturday class"}}
    exe = {"id": "ex1", "nodeId": A, "date": "2026-04-01", "status": "PARTIAL", "periodsTaught": 1, "note": "n", "recordedBy": {"id": ctx.t0, "name": "T", "role": "teacher"}, "recordedAt": "2026-04-01T09:00:00Z", "supersedes": None, "scheduleVersion": 1}
    await workspace(db_session, ctx.sid, [
        ws_plan("w-old", status="SUPERSEDED", by={"id": ctx.t0, "name": "T", "role": "teacher"}),
        ws_plan("w-cur", by={"id": ctx.t0, "name": "T", "role": "teacher"}, proposals=[prop], execution=[exe]),
        ws_plan("w-draft", status="DRAFT", by={"id": ctx.t1, "name": "T", "role": "teacher"}, versions=False),
        ws_plan("w-bad", by={"id": ctx.t1, "name": "T", "role": "teacher"}, ls=[lesson(A, 3, 1, [slot("2026-04-04", 1)])]),   # Saturday: invalid
        ws_plan("w-twin", by={"id": ctx.t0, "name": "T", "role": "teacher"}),                                                 # second APPROVED for the same owner
        ws_plan("w-amb", by={"id": "someone-else", "name": "?", "role": "admin"}),                                            # two holders, recorder holds no plan
    ])
    rep = await import_workspace_plans(db_session, ctx.sid)
    assert rep["imported"] == ["w-old", "w-cur", "w-draft"] and [i["plan"] for i in rep["invalid"]] == ["w-bad"]
    assert [c["plan"] for c in rep["conflicts"]] == ["w-twin"] and rep["ambiguous"][0]["plan"] == "w-amb" and len(rep["ambiguous"][0]["teachers"]) == 2
    cur = next(p for p in await ctx.plans(ctx.t0) if p["id"] == "w-cur")
    assert cur["status"] == "APPROVED" and cur["versions"][0]["approvedBy"]["role"] == "principal" and cur["versions"][0]["lessons"] == lessons()
    assert cur["proposals"][0]["status"] == "REJECTED" and cur["proposals"][0]["review"]["note"] == "Use the Saturday class"  # nothing re-approved
    assert cur["execution"][0]["recordedAt"] == "2026-04-01T09:00:00Z" and cur["execution"][0]["status"] == "PARTIAL"
    assert {p["id"] for p in await ctx.plans(ctx.t1)} == {"w-draft"}  # each teacher only their own
    ev = (await db_session.execute(select(PlanAuditEvent).filter_by(school_id=ctx.sid, category="schedule_change"))).scalars().all()
    assert len(ev) == 3 and all("nothing was re-approved" in e.reason for e in ev)
    again = await import_workspace_plans(db_session, ctx.sid)
    assert again["imported"] == [] and set(again["skipped_existing"]) == {"w-old", "w-cur", "w-draft"}


@pytest.mark.asyncio
async def test_structural_schedule_checks_apply_to_every_proposal(ctx):
    """Ported from the workspace-document tests: the server validates every persisted schedule, whoever generated it."""
    await approved(ctx, ctx.t0, "plan-st")
    url = "/api/v1/plans/plan-st/proposals"

    def bad(pid, ls, config=CONFIG):
        body = proposal_body(pid, ls=ls)
        body["config"] = config
        return body

    holiday_cfg = {**CONFIG, "entries": [{"id": "h", "type": "HOLIDAY", "label": "H", "start": "2026-04-06", "end": "2026-04-06"}]}
    cases = [
        ("a weekend date", bad("st1", [lesson(A, 3, 1, [slot("2026-04-04", 1)] * 1), lessons()[1]]), "not a teaching date"),
        ("outside the calendar", bad("st2", [lesson(A, 3, 1, [slot("2026-05-01", 1)]), lessons()[1]]), "not a teaching date"),
        ("a holiday", bad("st3", [lesson(A, 3, 1, [slot("2026-04-06", 1)]), lessons()[1]], holiday_cfg), "not a teaching date"),
        ("a period beyond the subject's periods", bad("st4", [lesson(A, 3, 1, [slot("2026-04-01", 3)]), lessons()[1]]), "outside the subject"),
        ("a double-allocated period", bad("st5", [lesson(A, 3, 1, [slot("2026-04-01", 1)]), lesson(B, 2, 0, [slot("2026-04-01", 1)])]), "allocated to both"),
        ("requirement arithmetic", bad("st6", [lesson(A, 3, 1, [], unscheduled=0) | {"requiredPeriods": 9}, lessons()[1]]), "does not equal"),
        ("a silently dropped topic", bad("st7", [lessons()[0]]), "silently dropped"),
        ("reduced approved Core", bad("st8", [lesson(A, 1, 1, []), lessons()[1]]), "Core requirement"),
    ]
    for name, body, needle in cases:
        r = await ctx.c.post(url, json=body, headers=ctx.h(ctx.t0))
        assert r.status_code == 422 and needle in str(r.json()["detail"]), (name, r.text)
    assert (await ctx.plans(ctx.t0))[0]["proposals"] == []  # none of them was stored
    ok = await ctx.c.post(url, json=proposal_body("st-ok"), headers=ctx.h(ctx.t0))
    assert ok.status_code == 201


@pytest.mark.asyncio
async def test_import_links_lost_periods_already_absorbed_by_an_approved_version(ctx, db_session):
    from backend.app.services.workspace_import import import_workspace_plans
    r = await ctx.c.post(f"/api/v1/teacher-plans/{ctx.t0}/lost-periods", json={"grade": 7, "subject": "Mathematics", "date": "2026-04-01", "periods": [2], "reason_code": "Health Drive"}, headers=ctx.h(ctx.t0))
    assert r.status_code == 201
    plan = ws_plan("w-lost", by={"id": ctx.t0, "name": "T", "role": "teacher"})
    plan["versions"].append({**plan["versions"][0], "version": 2, "proposalId": "pp", "lostSlots": [{"date": "2026-04-01", "period": 2}]})
    await workspace(db_session, ctx.sid, [plan])
    assert (await import_workspace_plans(db_session, ctx.sid))["imported"] == ["w-lost"]
    row = (await db_session.execute(select(TeacherLostPeriod).filter_by(teacher_id=ctx.t0, lost_date="2026-04-01"))).scalars().first()
    await db_session.refresh(row)
    assert row.schedule_version == 2  # first version whose lostSlots contain it
    w = await ctx.c.post(f"/api/v1/teacher-plans/{ctx.t0}/lost-periods/withdraw", json={"grade": 7, "subject": "Mathematics", "date": "2026-04-01", "periods": [2], "reason": "Changed my mind"}, headers=ctx.h(ctx.t0))
    assert w.status_code == 409


@pytest.mark.asyncio
async def test_a_loss_is_validated_against_the_approved_schedule_not_the_changed_timetable(ctx):
    """Approved schedules keep the calendar they were approved against, so the school's later timetable change cannot hide a real period."""
    await approved(ctx, ctx.t0, "plan-lv")
    # The school later drops to 1 Maths period a day (calendar version 2); the approved schedule still has period 2 slots.
    cfg = {**DEFAULT_CALENDAR, "subjectPeriodsPerDay": {"Mathematics": 1, "Science": 1}}  # a full valid academic year, 1 Maths period a day
    assert (await ctx.c.put("/api/v1/plan-calendar", json={"config": cfg, "reason": "Timetable revised"}, headers=ctx.h(ctx.pr))).status_code == 200
    url = f"/api/v1/teacher-plans/{ctx.t0}/lost-periods"
    body = {"grade": 7, "subject": "Mathematics", "reason_code": "Health Drive"}
    ok = await ctx.c.post(url, json={**body, "date": "2026-04-02", "periods": [2]}, headers=ctx.h(ctx.t0))
    assert ok.status_code == 201, ok.text  # period 2 exists in the approved schedule even though the new timetable has one a day
    # a period that is not in the approved schedule is refused (04-06 has no slot), and so is a date outside it
    nope = await ctx.c.post(url, json={**body, "date": "2026-04-06", "periods": [1]}, headers=ctx.h(ctx.t0))
    assert nope.status_code == 422 and "not a classroom period of the approved schedule" in nope.text
    # a topic recorded as taught cannot lose a period
    assert (await ctx.c.post("/api/v1/plans/plan-lv/execution", json={"id": "lv-e1", "nodeId": B, "date": "2026-04-03", "status": "TAUGHT"}, headers=ctx.h(ctx.t0))).status_code == 201
    taught = await ctx.c.post(url, json={**body, "date": "2026-04-03", "periods": [1]}, headers=ctx.h(ctx.t0))
    assert taught.status_code == 422 and "recorded as taught" in taught.text
    # the other teacher (no approved plan) is still validated against the school's current timetable
    other = await ctx.c.post(f"/api/v1/teacher-plans/{ctx.t1}/lost-periods", json={**body, "date": "2026-04-02", "periods": [2]}, headers=ctx.h(ctx.t1))
    assert other.status_code == 422 and "timetabled" in other.text


@pytest.mark.asyncio
async def test_import_records_a_historical_loss_an_approved_recovery_already_absorbed(ctx, db_session):
    """Live recording refuses an absorbed period; the import must still be able to bring that history in, linked to its version."""
    from backend.app.services.workspace_import import import_workspace_losses, import_workspace_plans
    plan = ws_plan("w-hist", by={"id": ctx.t0, "name": "T", "role": "teacher"})
    plan["versions"].append({**plan["versions"][0], "version": 2, "proposalId": "pp", "lostSlots": [{"date": "2026-04-01", "period": 2}],
                             "lessons": [lesson(A, 3, 1, [slot("2026-04-01", 1), slot("2026-04-02", 1), slot("2026-04-02", 2, "NON_CORE"), slot("2026-04-06", 1)]), lessons()[1]]})
    plan["losses"] = [{"id": "l1", "date": "2026-04-01", "periodsLost": 1, "periods": [2], "reason": "Health Drive", "note": "n", "recordedBy": {"id": ctx.t0, "name": "T", "role": "teacher"},
                       "recordedAt": "2026-04-01T09:00:00Z", "supersedes": None}]
    await workspace(db_session, ctx.sid, [plan])
    assert (await import_workspace_plans(db_session, ctx.sid))["imported"] == ["w-hist"]
    rep = await import_workspace_losses(db_session, ctx.sid)
    assert rep["imported"] == ["l1"] and rep["invalid"] == []
    row = (await db_session.execute(select(TeacherLostPeriod).filter_by(teacher_id=ctx.t0, lost_date="2026-04-01"))).scalars().first()
    assert (row.period_number, row.reason_code, row.schedule_version) == (2, "Health Drive", 2)  # linked to the version that absorbed it
    live = await ctx.c.post(f"/api/v1/teacher-plans/{ctx.t0}/lost-periods", json={"grade": 7, "subject": "Mathematics", "date": "2026-04-01", "periods": [2], "reason_code": "Other"}, headers=ctx.h(ctx.t0))
    assert live.status_code == 409  # still refused when a teacher tries to record it live
