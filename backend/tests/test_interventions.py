"""AI-assisted learning interventions: auth, state machine, generation, privacy."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from backend.app.models.entities import Assessment, AssessmentSubmission, Student
from backend.app.modules.interventions.schemas import AIInterventionContent
from backend.app.modules.student_progress.schemas import (
    CompetencyEvidenceOut,
    OptionalCompetencyScoresOut,
)
from backend.app.modules.student_progress.subject_competency import (
    build_subject_competency_profile,
)
from backend.app.services import ai_gateway

API = "/api/v1"


def uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def ai_ok_json() -> str:
    return AIInterventionContent(
        learning_objective="Strengthen language understanding for multi-step word problems.",
        recommended_activities=[
            "Guided annotation of question stems",
            "Partner retell of problem conditions",
        ],
        suggested_duration_days=14,
        practice_type="differentiated_homework",
        practice_outline="Assign a short differentiated homework set targeting LU.",
        expected_outcome="LU score improves on the next verified assessment window.",
        reassessment_criteria="Reassess LU via a graded Assessment Studio item or reviewed homework.",
    ).model_dump_json()


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, payload: str = "", *, error: Exception | None = None):
        self.payload = payload or ai_ok_json()
        self.error = error
        self.calls = []

    async def generate_json(self, *, system: str, prompt: str, schema):
        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        if self.error:
            raise self.error
        return self.payload


@pytest_asyncio.fixture
async def intervention_world(db_session):
    student = Student(
        id=uid("iv-stu"),
        school_id="school-1",
        class_id="class-8a",
        class_name="Class 8-A",
        name="Intervention Student",
        roll_no=88,
        gender="Other",
        lu_score=40,
        cu_score=70,
        au_score=70,
        ct_score=70,
        overall_score=62,
        baseline_lu=40,
        baseline_cu=70,
        baseline_au=70,
        baseline_ct=70,
        baseline_overall=62,
    )
    db_session.add(student)
    asm = Assessment(
        id=uid("iv-asm"),
        school_id="school-1",
        class_id="class-8a",
        subject_id="sub-math",
        title="Weak LU probe",
        cycle_number=1,
        date="2026-09-10",
        duration_minutes=40,
        total_marks=100,
        status="graded",
        competency_focus_json=["LU"],
        questions_json=[],
    )
    db_session.add(asm)
    db_session.add(
        AssessmentSubmission(
            id=uid("iv-sub"),
            assessment_id=asm.id,
            student_id=student.id,
            student_name=student.name,
            marks_obtained=42,
            total_marks=100,
            percentage=42,
            lu_score=40,
            cu_score=70,
            au_score=68,
            ct_score=66,
            overall_score=61,
            feedback="Released LU feedback",
            submission_date="2026-09-10",
            is_scanned=False,
            created_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
        )
    )
    # Second weaker LU evidence for inconsistency / weakness patterns
    asm2 = Assessment(
        id=uid("iv-asm2"),
        school_id="school-1",
        class_id="class-8a",
        subject_id="sub-math",
        title="Second LU probe",
        cycle_number=2,
        date="2026-11-05",
        duration_minutes=40,
        total_marks=100,
        status="graded",
        competency_focus_json=["LU"],
        questions_json=[],
    )
    db_session.add(asm2)
    db_session.add(
        AssessmentSubmission(
            id=uid("iv-sub2"),
            assessment_id=asm2.id,
            student_id=student.id,
            student_name=student.name,
            marks_obtained=38,
            total_marks=100,
            percentage=38,
            lu_score=35,
            cu_score=72,
            au_score=70,
            ct_score=68,
            overall_score=61,
            feedback="Released LU feedback 2",
            submission_date="2026-11-05",
            is_scanned=False,
            created_at=datetime(2026, 11, 5, tzinfo=timezone.utc),
        )
    )
    await db_session.commit()
    return {"student_id": student.id, "name": student.name}


@pytest.mark.asyncio
async def test_generate_approve_assign_flow(
    client, teacher_token, intervention_world, monkeypatch
):
    fake = FakeProvider()
    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: fake)
    sid = intervention_world["student_id"]
    headers = {"Authorization": f"Bearer {teacher_token}", "X-School-Id": "school-1"}

    gen = await client.post(
        f"{API}/students/{sid}/interventions/generate",
        headers=headers,
        json={"subject_id": "sub-math", "competency": "LU"},
    )
    assert gen.status_code == 201, gen.text
    body = gen.json()
    assert body["status"] == "pending_review"
    assert body["ai_generated"] is True
    assert body["competency"] == "LU"
    assert body["evidence_refs"]
    assert "proposal_disclaimer" in body
    # Prompt hygiene: student legal name and raw id must not appear
    prompt = fake.calls[0]["prompt"]
    assert intervention_world["name"].lower() not in prompt.lower()
    assert sid.lower() not in prompt.lower()
    assert "learner_" in prompt
    assert "teacher_notes" not in prompt.lower()

    iid = body["id"]
    # Rejected cannot assign
    bad_assign = await client.post(
        f"{API}/students/{sid}/interventions/{iid}/assign",
        headers=headers,
        json={"due_date": "2026-12-01"},
    )
    assert bad_assign.status_code == 409

    approve = await client.post(
        f"{API}/students/{sid}/interventions/{iid}/approve",
        headers=headers,
        json={"review_notes": "Looks good"},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    assign = await client.post(
        f"{API}/students/{sid}/interventions/{iid}/assign",
        headers=headers,
        json={"due_date": "2026-12-01"},
    )
    assert assign.status_code == 200, assign.text
    assigned = assign.json()
    assert assigned["status"] == "assigned"
    assert assigned["assigned_homework_id"]

    # Must create a full Differentiated Homework assignment (not legacy remediation).
    dh = await client.get(
        f"{API}/homework/assignments/{assigned['assigned_homework_id']}",
        headers=headers,
    )
    assert dh.status_code == 200, dh.text
    assert dh.json()["student_id"] == sid
    assert dh.json()["subject_id"] == "sub-math"
    assert dh.json()["question_count"] >= 1

    legacy = await client.get(f"{API}/students/{sid}/homework", headers=headers)
    assert legacy.status_code == 200
    assert all(h["id"] != assigned["assigned_homework_id"] for h in legacy.json())


@pytest.mark.asyncio
async def test_rejected_cannot_be_assigned(
    client, teacher_token, intervention_world, monkeypatch
):
    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: FakeProvider())
    sid = intervention_world["student_id"]
    headers = {"Authorization": f"Bearer {teacher_token}", "X-School-Id": "school-1"}
    gen = await client.post(
        f"{API}/students/{sid}/interventions/generate",
        headers=headers,
        json={"subject_id": "sub-math"},
    )
    iid = gen.json()["id"]
    rej = await client.post(
        f"{API}/students/{sid}/interventions/{iid}/reject",
        headers=headers,
        json={"review_notes": "Not now"},
    )
    assert rej.status_code == 200
    assert rej.json()["status"] == "rejected"
    assign = await client.post(
        f"{API}/students/{sid}/interventions/{iid}/assign",
        headers=headers,
        json={"due_date": "2026-12-01"},
    )
    assert assign.status_code == 409


@pytest.mark.asyncio
async def test_school_isolation_and_student_forbidden(
    client, teacher_token, other_school_teacher_token, student_token, intervention_world, monkeypatch
):
    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: FakeProvider())
    sid = intervention_world["student_id"]
    headers = {"Authorization": f"Bearer {teacher_token}", "X-School-Id": "school-1"}
    gen = await client.post(
        f"{API}/students/{sid}/interventions/generate",
        headers=headers,
        json={"subject_id": "sub-math"},
    )
    assert gen.status_code == 201
    iid = gen.json()["id"]

    foreign = {
        "Authorization": f"Bearer {other_school_teacher_token}",
        "X-School-Id": "school-2",
    }
    listed = await client.get(f"{API}/students/{sid}/interventions", headers=foreign)
    assert listed.status_code in (403, 404)
    got = await client.get(f"{API}/students/{sid}/interventions/{iid}", headers=foreign)
    assert got.status_code in (403, 404)

    student_headers = {
        "Authorization": f"Bearer {student_token}",
        "X-School-Id": "school-1",
    }
    denied = await client.post(
        f"{API}/students/{sid}/interventions/generate",
        headers=student_headers,
        json={"subject_id": "sub-math"},
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_ai_failure_and_malformed_response(
    client, teacher_token, intervention_world, monkeypatch
):
    sid = intervention_world["student_id"]
    headers = {"Authorization": f"Bearer {teacher_token}", "X-School-Id": "school-1"}

    monkeypatch.setattr(
        ai_gateway,
        "get_ai_provider",
        lambda: (_ for _ in ()).throw(ai_gateway.AINotConfigured()),
    )
    # Actually get_ai_provider should raise — wrap:
    def boom():
        raise ai_gateway.AINotConfigured()

    monkeypatch.setattr(ai_gateway, "get_ai_provider", boom)
    r1 = await client.post(
        f"{API}/students/{sid}/interventions/generate",
        headers=headers,
        json={"subject_id": "sub-math"},
    )
    assert r1.status_code == 503

    monkeypatch.setattr(
        ai_gateway,
        "get_ai_provider",
        lambda: FakeProvider(error=ai_gateway.AIProviderTimeout()),
    )
    r2 = await client.post(
        f"{API}/students/{sid}/interventions/generate",
        headers=headers,
        json={"subject_id": "sub-math"},
    )
    assert r2.status_code == 504

    monkeypatch.setattr(
        ai_gateway, "get_ai_provider", lambda: FakeProvider(payload="{not-json")
    )
    r3 = await client.post(
        f"{API}/students/{sid}/interventions/generate",
        headers=headers,
        json={"subject_id": "sub-math"},
    )
    assert r3.status_code == 502


@pytest.mark.asyncio
async def test_missing_evidence_subject(client, teacher_token, intervention_world, monkeypatch):
    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: FakeProvider())
    sid = intervention_world["student_id"]
    headers = {"Authorization": f"Bearer {teacher_token}", "X-School-Id": "school-1"}
    res = await client.post(
        f"{API}/students/{sid}/interventions/generate",
        headers=headers,
        json={"subject_id": "sub-sst"},
    )
    assert res.status_code == 400


def test_ai_text_never_enters_competency_profile():
    """AI proposal fields must not be treated as competency evidence."""
    profile = build_subject_competency_profile(
        student_id="x",
        subject_id="sub-math",
        subject_name="Mathematics",
        evidence=[
            CompetencyEvidenceOut(
                source_type="assessment_studio",
                source_id="sub-1",
                title="Probe",
                occurred_at="2026-09-10T00:00:00+00:00",
                awarded_marks=40,
                max_marks=100,
                scores=OptionalCompetencyScoresOut(
                    LU=40, CU=70, AU=68, CT=66, overall=61
                ),
            )
        ],
    )
    assert profile.scores.LU == 40
    # Ensure methodology remains verified evidence mean — no AI source type exists
    assert profile.methodology.startswith("subject_competency")
    assert all(e.source_type != "ai_intervention" for e in profile.evidence)


@pytest.mark.asyncio
async def test_edit_then_approve(client, teacher_token, intervention_world, monkeypatch):
    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: FakeProvider())
    sid = intervention_world["student_id"]
    headers = {"Authorization": f"Bearer {teacher_token}", "X-School-Id": "school-1"}
    gen = await client.post(
        f"{API}/students/{sid}/interventions/generate",
        headers=headers,
        json={"subject_id": "sub-math"},
    )
    iid = gen.json()["id"]
    edited = await client.patch(
        f"{API}/students/{sid}/interventions/{iid}",
        headers=headers,
        json={
            "learning_objective": "Teacher-edited LU objective with clearer success bar.",
            "recommended_activities": ["Teacher custom activity"],
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["teacher_edited"] is True
    assert "Teacher-edited" in edited.json()["learning_objective"]
