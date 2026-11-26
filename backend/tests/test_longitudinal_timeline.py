"""Longitudinal evidence ledger, monthly/term checkpoints, deterministic explanations."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from backend.app.models.entities import (
    Assessment,
    AssessmentSubmission,
    HomeworkRemediation,
    Student,
    StudentCompetencySnapshot,
)
from backend.app.modules.student_progress.academic_period import (
    academic_month_keys,
    resolve_calendar,
)
from backend.app.modules.student_progress.evidence import LONGITUDINAL_METHODOLOGY

API = "/api/v1"


def uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@pytest_asyncio.fixture
async def long_world(db_session):
    """Isolated student with Math evidence in two months + global snapshot bait."""
    student = Student(
        id=uid("long-stu"),
        school_id="school-1",
        class_id="class-8a",
        class_name="Class 8-A",
        name="Longitudinal Test Student",
        roll_no=77,
        gender="Other",
        lu_score=10,
        cu_score=10,
        au_score=10,
        ct_score=10,
        overall_score=10,
        baseline_lu=10,
        baseline_cu=10,
        baseline_au=10,
        baseline_ct=10,
        baseline_overall=10,
    )
    db_session.add(student)

    # Global snapshot must NOT appear in subject month scores
    db_session.add(
        StudentCompetencySnapshot(
            id=uid("long-snap"),
            student_id=student.id,
            cycle_number=1,
            recorded_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            lu_score=1,
            cu_score=1,
            au_score=1,
            ct_score=1,
            overall_score=1,
            notes="GLOBAL-BAIT",
            subject_id=None,
        )
    )

    jun = Assessment(
        id=uid("asm-jun"),
        school_id="school-1",
        class_id="class-8a",
        subject_id="sub-math",
        title="June Math Probe",
        cycle_number=1,
        date="2026-06-15",
        duration_minutes=40,
        total_marks=100,
        status="graded",
        competency_focus_json=["LU"],
        questions_json=[],
    )
    nov = Assessment(
        id=uid("asm-nov"),
        school_id="school-1",
        class_id="class-8a",
        subject_id="sub-math",
        title="November Math Probe",
        cycle_number=2,
        date="2026-11-10",
        duration_minutes=40,
        total_marks=100,
        status="graded",
        competency_focus_json=["LU"],
        questions_json=[],
    )
    db_session.add_all([jun, nov])

    db_session.add(
        AssessmentSubmission(
            id=uid("sub-jun"),
            assessment_id=jun.id,
            student_id=student.id,
            student_name=student.name,
            marks_obtained=60,
            total_marks=100,
            percentage=60,
            lu_score=50,
            cu_score=55,
            au_score=45,
            ct_score=40,
            overall_score=47,
            feedback="June released",
            submission_date="2026-06-15",
            is_scanned=False,
            created_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
        )
    )
    db_session.add(
        AssessmentSubmission(
            id=uid("sub-nov"),
            assessment_id=nov.id,
            student_id=student.id,
            student_name=student.name,
            marks_obtained=85,
            total_marks=100,
            percentage=85,
            lu_score=80,
            cu_score=78,
            au_score=70,
            ct_score=72,
            overall_score=75,
            feedback="November released",
            submission_date="2026-11-10",
            is_scanned=False,
            created_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
        )
    )
    # Reviewed homework in November for LU only
    db_session.add(
        HomeworkRemediation(
            id=uid("hw-nov"),
            student_id=student.id,
            student_name=student.name,
            class_id="class-8a",
            subject_id="sub-math",
            title="Nov LU practice",
            competency_target="LU",
            reason="practice",
            description="reviewed",
            due_date="2026-11-20",
            status="reviewed",
            score=90,
            created_at=datetime(2026, 11, 12, tzinfo=timezone.utc),
        )
    )
    # Unreleased homework — learners must not see in longitudinal evidence
    db_session.add(
        HomeworkRemediation(
            id=uid("hw-secret"),
            student_id=student.id,
            student_name=student.name,
            class_id="class-8a",
            subject_id="sub-math",
            title="SECRET-LONG-UNRELEASED",
            competency_target="CU",
            reason="draft",
            description="hidden",
            due_date="2026-11-25",
            status="assigned",
            score=None,
            created_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
        )
    )
    await db_session.commit()
    return {"student_id": student.id, "jun": jun.id, "nov": nov.id}


def test_academic_year_has_twelve_months():
    cal = resolve_calendar("2026-2027")
    keys = academic_month_keys(cal)
    assert len(keys) == 12
    assert keys[0] == "2026-06"
    assert keys[-1] == "2027-05"


@pytest.mark.asyncio
async def test_timeline_reconstructs_months_without_global_snapshot(
    client, teacher_token, long_world
):
    sid = long_world["student_id"]
    headers = {"Authorization": f"Bearer {teacher_token}", "X-School-Id": "school-1"}
    res = await client.get(
        f"{API}/students/{sid}/progress/subjects/sub-math/timeline",
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["methodology"] == LONGITUDINAL_METHODOLOGY
    assert len(body["months"]) == 12
    by_id = {m["period_id"]: m for m in body["months"]}
    jun = by_id["2026-06"]
    nov = by_id["2026-11"]
    empty = by_id["2026-08"]
    assert jun["status"] == "available"
    assert jun["scores"]["LU"] == 50
    assert nov["status"] == "available"
    # Nov LU = mean(80 assessment, 90 homework) = 85
    assert nov["scores"]["LU"] == 85.0
    assert empty["status"] == "unavailable"
    assert empty["scores"] is None
    assert "GLOBAL-BAIT" not in res.text
    # Term T1 includes June
    terms = {t["period_id"]: t for t in body["terms"]}
    assert terms["T1"]["scores"]["LU"] == 50
    assert terms["T2"]["scores"]["LU"] == 85.0


@pytest.mark.asyncio
async def test_student_me_timeline_not_captured_by_educator_route(client, student_token):
    """Regression: /students/me/.../timeline must not match /students/{student_id}/..."""
    headers = {"Authorization": f"Bearer {student_token}", "X-School-Id": "school-1"}
    res = await client.get(f"{API}/students/me/progress/subjects/sub-math/timeline", headers=headers)
    assert res.status_code == 200, res.text
    assert len(res.json().get("months") or []) == 12
    expl = await client.get(
        f"{API}/students/me/progress/subjects/sub-math/explanations", headers=headers
    )
    assert expl.status_code == 200, expl.text


@pytest.mark.asyncio
async def test_period_drilldown_and_explanations(client, teacher_token, long_world):
    sid = long_world["student_id"]
    headers = {"Authorization": f"Bearer {teacher_token}", "X-School-Id": "school-1"}
    drill = await client.get(
        f"{API}/students/{sid}/progress/subjects/sub-math/timeline/month/2026-11",
        headers=headers,
    )
    assert drill.status_code == 200
    obs = drill.json()["observations"]
    assert any(o["normalized_score"] == 80 and o["competency"] == "LU" for o in obs)
    assert any(o["source_type"] == "differentiated_homework" for o in obs)
    assert "SECRET-LONG-UNRELEASED" not in drill.text

    expl = await client.get(
        f"{API}/students/{sid}/progress/subjects/sub-math/explanations",
        headers=headers,
    )
    assert expl.status_code == 200
    kinds = {f["kind"] for f in expl.json()["findings"]}
    assert "recent_improvement" in kinds or "consistent_strength" in kinds or "requires_attention" in kinds
    for f in expl.json()["findings"]:
        assert "caveat" in f
        assert f["evidence_ids"] or f["kind"] == "insufficient_evidence"
