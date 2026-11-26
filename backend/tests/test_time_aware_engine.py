import pytest
from backend.app.models.entities import (
    CurriculumDay,
    InstructionalDisruption,
)
from backend.app.services.time_aware_engine import (
    calculate_pacing_metrics,
    generate_compression_proposal,
)


def test_calculate_pacing_metrics_healthy_buffer():
    # 220 official days, current day 50, 2 lost days, 100 pending periods (70 core + 30 supp)
    disruptions = [InstructionalDisruption(days_lost=2.0)]
    curriculum_days = [
        CurriculumDay(classification="core", status="pending") for _ in range(70)
    ] + [
        CurriculumDay(classification="supplementary", status="pending") for _ in range(30)
    ]

    metrics = calculate_pacing_metrics(
        total_official_days=220,
        current_day=50,
        disruptions=disruptions,
        curriculum_days=curriculum_days,
    )

    # Remaining = (220 - 50) - 2 = 168
    assert metrics["remaining_instructional_days"] == 168.0
    assert metrics["total_periods_needed_original"] == 100
    assert metrics["pacing_buffer"] == 68.0
    assert metrics["risk_status"] == "low"


def test_calculate_pacing_metrics_deficit():
    # 220 official days, current day 140, 16 lost days, 70 pending periods
    # Remaining = (220 - 140) - 16 = 64 days. Needed = 70. Buffer = -6 (high risk)
    disruptions = [InstructionalDisruption(days_lost=16.0)]
    curriculum_days = [
        CurriculumDay(classification="core", status="pending") for _ in range(50)
    ] + [
        CurriculumDay(classification="supplementary", status="pending") for _ in range(20)
    ]

    metrics = calculate_pacing_metrics(
        total_official_days=220,
        current_day=140,
        disruptions=disruptions,
        curriculum_days=curriculum_days,
    )

    assert metrics["remaining_instructional_days"] == 64.0
    assert metrics["total_periods_needed_original"] == 70
    assert metrics["pacing_buffer"] == -6.0
    assert metrics["risk_status"] == "high"


def test_legacy_compression_refuses_to_invent_requirements():
    # Legacy curriculum rows carry no approved topic-level Core/Non-Core period counts, so no fixed-ratio
    # compression may be generated from them.
    rows = [CurriculumDay(id="core-1", classification="core", status="pending")]
    with pytest.raises(ValueError, match="retired"):
        generate_compression_proposal(curriculum_days=rows, pacing_metrics={}, school_id="school-1", class_id="class-8a")
