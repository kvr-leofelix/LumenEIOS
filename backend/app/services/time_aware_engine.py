import uuid
from typing import Dict, List, Any, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.models.entities import (
    CurriculumDay,
    InstructionalDisruption,
    CurriculumProposal,
    AuditEvent,
    utc_now,
)


def calculate_pacing_metrics(
    total_official_days: int,
    current_day: int,
    disruptions: List[InstructionalDisruption],
    curriculum_days: List[CurriculumDay]
) -> Dict[str, Any]:
    """
    Deterministic Time-Aware Pedagogical Engine.
    Calculates actual instructional contact days left, deficit/buffer, and risk status.
    """
    total_lost_days = sum(d.days_lost for d in disruptions)
    gross_remaining_days = max(0, total_official_days - current_day)
    remaining_instructional_days = max(0.0, gross_remaining_days - total_lost_days)

    pending_days = [
        d for d in curriculum_days
        if d.status in ("pending", "in-progress")
    ]
    core_concepts_remaining = sum(1 for d in pending_days if d.classification == "core")
    supplementary_topics_remaining = sum(1 for d in pending_days if d.classification == "supplementary")

    total_periods_needed = core_concepts_remaining + supplementary_topics_remaining
    pacing_buffer = round(remaining_instructional_days - total_periods_needed, 1)

    if pacing_buffer < -3:
        risk_status = "high"
        risk_label = f"High Pacing Risk (Deficit: {abs(pacing_buffer)} days)"
    elif pacing_buffer <= 3:
        risk_status = "medium"
        risk_label = f"Tight Pacing (Buffer: {pacing_buffer} days)"
    else:
        risk_status = "low"
        risk_label = "On Track (Healthy Buffer)"

    return {
        "total_official_days": total_official_days,
        "current_day": current_day,
        "total_lost_days": total_lost_days,
        "remaining_instructional_days": remaining_instructional_days,
        "core_concepts_remaining": core_concepts_remaining,
        "supplementary_topics_remaining": supplementary_topics_remaining,
        "total_periods_needed_original": total_periods_needed,
        "pacing_buffer": pacing_buffer,
        "risk_status": risk_status,
        "risk_label": risk_label,
    }


def generate_compression_proposal(
    curriculum_days: List[CurriculumDay],
    pacing_metrics: Dict[str, Any],
    school_id: str,
    class_id: str
) -> Tuple[CurriculumProposal, List[CurriculumDay], List[CurriculumDay]]:
    """Legacy curriculum rows lack approved topic-period requirements; never invent them."""
    raise ValueError("Legacy compression is retired. Use approved topic requirements in the planning workspace.")
