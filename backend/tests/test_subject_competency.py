"""Subject-specific competency foundation: separation, aggregation, gaps, dedupe, auth."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.app.models.entities import (
    Assessment,
    AssessmentSubmission,
    HomeworkRemediation,
    Student,
    StudentCompetencySnapshot,
)
from backend.app.modules.student_progress.subject_competency import (
    METHODOLOGY_ID,
    build_subject_competency_profile,
    collect_subject_competency_evidence,
)
from backend.app.modules.student_progress.schemas import CompetencyEvidenceOut, OptionalCompetencyScoresOut

API = "/api/v1"
NOW = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)


def uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@pytest_asyncio.fixture
async def competency_world(db_session):
    """Synthetic isolated evidence for Aarav: Math + Science, with a duplicate Math submission."""
    alice = await db_session.get(Student, "user-student-1")
    assert alice is not None

    math_asm = Assessment(
        id=uid("asm-math"),
        school_id="school-1",
        class_id=alice.class_id,
        subject_id="sub-math",
        title="Math competency probe",
        cycle_number=3,
        date="2026-11-01",
        duration_minutes=40,
        total_marks=20,
        status="graded",
        competency_focus_json=["LU", "CU"],
        questions_json=[],
    )
    sci_subject = "sub-sst"  # isolate from other suites that may write sub-sci evidence
    sci_asm = Assessment(
        id=uid("asm-sci"),
        school_id="school-1",
        class_id=alice.class_id,
        subject_id=sci_subject,
        title="Social Studies competency probe",
        cycle_number=3,
        date="2026-11-02",
        duration_minutes=40,
        total_marks=50,
        status="graded",
        competency_focus_json=["AU", "CT"],
        questions_json=[],
    )
    # Unrelated subject with no submissions → unavailable
    empty_asm = Assessment(
        id=uid("asm-eng"),
        school_id="school-1",
        class_id=alice.class_id,
        subject_id="sub-eng",
        title="English with no grades yet",
        cycle_number=3,
        date="2026-11-03",
        duration_minutes=40,
        total_marks=25,
        status="scheduled",
        competency_focus_json=["LU"],
        questions_json=[],
    )
    db_session.add_all([math_asm, sci_asm, empty_asm])

    older = AssessmentSubmission(
        id=uid("sub-old"),
        assessment_id=math_asm.id,
        student_id=alice.id,
        student_name=alice.name,
        marks_obtained=10,
        total_marks=20,
        percentage=50,
        lu_score=40,
        cu_score=40,
        au_score=40,
        ct_score=40,
        overall_score=40,
        feedback="older duplicate",
        submission_date="2026-11-01",
        is_scanned=False,
        created_at=NOW.replace(day=1),
    )
    newer = AssessmentSubmission(
        id=uid("sub-new"),
        assessment_id=math_asm.id,
        student_id=alice.id,
        student_name=alice.name,
        marks_obtained=16,
        total_marks=20,
        percentage=80,
        lu_score=70,
        cu_score=80,
        au_score=60,
        ct_score=50,
        overall_score=65,
        feedback="latest math",
        submission_date="2026-11-05",
        is_scanned=False,
        created_at=NOW.replace(day=5),
    )
    sci = AssessmentSubmission(
        id=uid("sub-sci"),
        assessment_id=sci_asm.id,
        student_id=alice.id,
        student_name=alice.name,
        marks_obtained=40,
        total_marks=50,
        percentage=80,
        lu_score=90,
        cu_score=85,
        au_score=88,
        ct_score=92,
        overall_score=89,
        feedback="science",
        submission_date="2026-11-06",
        is_scanned=True,
        created_at=NOW.replace(day=6),
    )
    db_session.add_all([older, newer, sci])

    # Global unscoped snapshot must NOT become subject evidence.
    snap = StudentCompetencySnapshot(
        id=uid("snap"),
        student_id=alice.id,
        cycle_number=9,
        recorded_at=NOW,
        lu_score=11,
        cu_score=12,
        au_score=13,
        ct_score=14,
        overall_score=12,
        notes="Global cycle snapshot — unscoped",
        subject_id=None,
    )
    db_session.add(snap)

    # Scored remediation contributes only LU for math.
    hw = HomeworkRemediation(
        id=uid("hw"),
        student_id=alice.id,
        student_name=alice.name,
        class_id=alice.class_id,
        subject_id="sub-math",
        title="LU drill",
        competency_target="LU",
        reason="practice",
        description="drill",
        due_date="2026-11-10",
        status="reviewed",
        score=55,
        created_at=NOW.replace(day=7),
    )
    db_session.add(hw)
    await db_session.commit()

    return {
        "alice": alice.id,
        "math_asm": math_asm.id,
        "sci_asm": sci_asm.id,
        "sci_subject": sci_subject,
        "older": older.id,
        "newer": newer.id,
        "sci": sci.id,
        "snap": snap.id,
        "hw": hw.id,
    }


def test_methodology_mean_does_not_blend_raw_marks():
    """Different max_marks must not distort LU/CU averages (comparable 0–100 only)."""
    evidence = [
        CompetencyEvidenceOut(
            source_type="assessment_studio",
            source_id="a",
            assessment_id="asm-a",
            occurred_at="2026-11-01T00:00:00+00:00",
            awarded_marks=5,
            max_marks=10,
            scores=OptionalCompetencyScoresOut(LU=40, CU=40, AU=40, CT=40, overall=40),
        ),
        CompetencyEvidenceOut(
            source_type="assessment_studio",
            source_id="b",
            assessment_id="asm-b",
            occurred_at="2026-11-02T00:00:00+00:00",
            awarded_marks=90,
            max_marks=100,
            scores=OptionalCompetencyScoresOut(LU=80, CU=80, AU=80, CT=80, overall=80),
        ),
    ]
    profile = build_subject_competency_profile(
        student_id="s1",
        subject_id="sub-math",
        subject_name="Mathematics",
        evidence=evidence,
    )
    assert profile.status == "available"
    assert profile.scores is not None
    assert profile.scores.LU == 60.0  # mean of 40 and 80 — not mark-weighted
    assert profile.evidence_count == 2
    assert profile.methodology == METHODOLOGY_ID


def test_missing_evidence_is_unavailable_not_zero():
    profile = build_subject_competency_profile(
        student_id="s1",
        subject_id="sub-eng",
        subject_name="English",
        evidence=[],
    )
    assert profile.status == "unavailable"
    assert profile.scores is None
    assert profile.evidence_count == 0
    assert profile.dimension_evidence_counts["LU"] == 0


def test_partial_single_dimension_homework_evidence():
    evidence = [
        CompetencyEvidenceOut(
            source_type="differentiated_homework",
            source_id="hw1",
            assignment_id="hw1",
            occurred_at="2026-11-07T00:00:00+00:00",
            awarded_marks=55,
            max_marks=100,
            dimension="LU",
            dimension_value=55,
        )
    ]
    profile = build_subject_competency_profile(
        student_id="s1",
        subject_id="sub-math",
        subject_name="Mathematics",
        evidence=evidence,
    )
    assert profile.status == "partial"
    assert profile.scores is not None
    assert profile.scores.LU == 55
    assert profile.scores.CU is None
    assert profile.scores.overall is None


@pytest.mark.asyncio
async def test_subject_separation_and_duplicate_collapse(client, teacher_token, competency_world, db_session):
    w = competency_world
    headers = {"Authorization": f"Bearer {teacher_token}", "X-School-Id": "school-1"}

    math = await client.get(
        f"{API}/students/{w['alice']}/progress/subjects/sub-math/competencies",
        headers=headers,
    )
    assert math.status_code == 200, math.text
    math_body = math.json()
    assert math_body["subject_id"] == "sub-math"
    assert math_body["status"] in {"available", "partial"}
    assert math_body["scores"]["LU"] is not None
    # Duplicate assessment collapsed: older 40 must not pull the mean alone.
    source_ids = {e["source_id"] for e in math_body["evidence"]}
    assert w["newer"] in source_ids
    assert w["older"] not in source_ids
    assert w["snap"] not in source_ids  # global snapshot excluded
    assert w["sci"] not in source_ids

    sci = await client.get(
        f"{API}/students/{w['alice']}/progress/subjects/{w['sci_subject']}/competencies",
        headers=headers,
    )
    assert sci.status_code == 200
    sci_body = sci.json()
    assert sci_body["subject_id"] == w["sci_subject"]
    assert sci_body["scores"]["LU"] == 90
    assert sci_body["scores"]["CT"] == 92
    assert sci_body["scores"]["LU"] != math_body["scores"]["LU"]

    empty = await client.get(
        f"{API}/students/{w['alice']}/progress/subjects/sub-eng/competencies",
        headers=headers,
    )
    assert empty.status_code == 200
    empty_body = empty.json()
    assert empty_body["status"] == "unavailable"
    assert empty_body["scores"] is None
    assert empty_body["evidence_count"] == 0


@pytest.mark.asyncio
async def test_overview_embeds_subject_competencies_and_preserves_global(
    client, teacher_token, competency_world, db_session
):
    w = competency_world
    headers = {"Authorization": f"Bearer {teacher_token}", "X-School-Id": "school-1"}
    overview = await client.get(f"{API}/students/{w['alice']}/progress", headers=headers)
    assert overview.status_code == 200
    body = overview.json()
    assert "subject_competencies" in body
    by_id = {p["subject_id"]: p for p in body["subject_competencies"]}
    assert "sub-math" in by_id
    assert w["sci_subject"] in by_id
    # Global competencies still come from the live student record.
    assert body["competencies"]["source"] == "students.live_scores"
    # Other tests may legitimately move Aarav's live scores (released homework updates them), so compare
    # with the student's current record rather than the seed value.
    aarav = await db_session.get(Student, w["alice"])
    await db_session.refresh(aarav)
    assert body["competencies"]["current"]["LU"] == aarav.lu_score

    comps = await client.get(
        f"{API}/students/{w['alice']}/progress/competencies",
        headers=headers,
    )
    assert comps.status_code == 200
    hist = comps.json()
    assert hist["current"]["LU"] == aarav.lu_score
    assert any(h["source_id"] == w["snap"] for h in hist["history"])
    assert hist["subject_competencies"]


@pytest.mark.asyncio
async def test_subject_progress_includes_competency_block(
    client, teacher_token, competency_world
):
    w = competency_world
    headers = {"Authorization": f"Bearer {teacher_token}", "X-School-Id": "school-1"}
    res = await client.get(
        f"{API}/students/{w['alice']}/progress/subjects/sub-math",
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["competencies"]["subject_id"] == "sub-math"
    assert body["competencies"]["methodology"] == METHODOLOGY_ID
    assert body["performance"]["competencies"]["evidence_count"] == body["competencies"]["evidence_count"]


@pytest.mark.asyncio
async def test_authorization_boundaries_for_subject_competencies(
    client, teacher_token, student_token, parent_token, other_school_teacher_token, competency_world
):
    w = competency_world
    path = f"{API}/students/{w['alice']}/progress/subjects/sub-math/competencies"

    assert (await client.get(path, headers={"Authorization": f"Bearer {teacher_token}"})).status_code == 200
    assert (
        await client.get(path, headers={"Authorization": f"Bearer {other_school_teacher_token}"})
    ).status_code == 404

    # Student uses /me route, not another student's educator path.
    me = await client.get(
        f"{API}/students/me/progress/subjects/sub-math/competencies",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert me.status_code == 200
    assert me.json()["student_id"] == w["alice"]

    assert (
        await client.get(
            path,
            headers={"Authorization": f"Bearer {student_token}"},
        )
    ).status_code == 403

    parent = await client.get(
        f"{API}/parents/me/students/{w['alice']}/progress/subjects/sub-math/competencies",
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert parent.status_code == 200
    assert parent.json()["student_id"] == w["alice"]

    stranger = await client.get(
        f"{API}/parents/me/students/{w['alice']}/progress/subjects/sub-math/competencies",
        headers={
            "Authorization": f"Bearer {other_school_teacher_token}",
        },
    )
    # Teacher token cannot use parent route.
    assert stranger.status_code == 403


@pytest.mark.asyncio
async def test_collect_evidence_ignores_global_snapshots(db_session, competency_world):
    alice = await db_session.get(Student, competency_world["alice"])
    evidence = await collect_subject_competency_evidence(
        db_session, alice, "sub-math", "educator"
    )
    ids = {e.source_id for e in evidence}
    assert competency_world["snap"] not in ids
    assert competency_world["newer"] in ids
    assert competency_world["older"] not in ids
    assert competency_world["hw"] in ids

    # Ensure historical global snapshot row still exists unchanged.
    snap = await db_session.get(StudentCompetencySnapshot, competency_world["snap"])
    assert snap is not None
    assert snap.subject_id is None
    assert snap.lu_score == 11
