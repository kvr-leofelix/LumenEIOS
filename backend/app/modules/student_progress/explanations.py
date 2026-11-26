"""Deterministic progress explanations — no AI, no causation claims."""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import Student
from backend.app.modules.student_progress.evidence import (
    AcademicEvidenceObservation,
    Audience,
    collect_academic_evidence,
    weighted_mean,
)
from backend.app.modules.student_progress.subject_competency import DIMENSIONS
from backend.app.modules.student_progress.timeline import build_subject_timeline

STRENGTH_FLOOR = 75.0
WEAK_CEILING = 55.0
IMPROVE_DELTA = 8.0
DECLINE_DELTA = 8.0
MIN_POINTS_FOR_TREND = 2
INCONSISTENT_RANGE = 25.0


def _finding(
    kind: str,
    summary: str,
    *,
    subject_id: str,
    competency: Optional[str],
    evidence_ids: Sequence[str],
    period_ids: Sequence[str] = (),
) -> dict:
    return {
        "kind": kind,
        "summary": summary,
        "subject_id": subject_id,
        "competency": competency,
        "evidence_ids": list(evidence_ids)[:20],
        "period_ids": list(period_ids),
        "caveat": "Observational pattern from verified scores — not a diagnosis or causal claim.",
    }


async def build_progress_explanations(
    db: AsyncSession,
    student: Student,
    subject_id: str,
    audience: Audience,
) -> dict:
    bundle = await collect_academic_evidence(db, student, audience, subject_id=subject_id)
    obs = bundle.for_subject(subject_id)
    timeline = await build_subject_timeline(db, student, subject_id, audience)
    findings: List[dict] = []

    if not obs:
        findings.append(
            _finding(
                "insufficient_evidence",
                "Not enough verified subject evidence yet to describe strengths or concerns.",
                subject_id=subject_id,
                competency=None,
                evidence_ids=[],
            )
        )
        return {
            "student_id": student.id,
            "subject_id": subject_id,
            "findings": findings,
            "methodology": "progress_explanation.v1.deterministic",
        }

    # Per-competency overall mean + monthly series from term/month checkpoints
    by_dim: Dict[str, List[AcademicEvidenceObservation]] = defaultdict(list)
    for o in obs:
        by_dim[o.competency].append(o)

    for dim in DIMENSIONS:
        rows = by_dim.get(dim, [])
        if not rows:
            findings.append(
                _finding(
                    "insufficient_evidence",
                    f"{dim} has no verified observations for this subject yet.",
                    subject_id=subject_id,
                    competency=dim,
                    evidence_ids=[],
                )
            )
            continue

        mean = weighted_mean(rows)
        eids = [f"{r.source_type}:{r.source_id}:{r.competency}" for r in rows]
        if mean is not None and mean >= STRENGTH_FLOOR:
            findings.append(
                _finding(
                    "consistent_strength",
                    f"{dim} scores are consistently high across verified evidence (mean {mean}).",
                    subject_id=subject_id,
                    competency=dim,
                    evidence_ids=eids,
                )
            )
        elif mean is not None and mean <= WEAK_CEILING:
            findings.append(
                _finding(
                    "persistent_weakness",
                    f"{dim} remains below the practice threshold across verified evidence (mean {mean}).",
                    subject_id=subject_id,
                    competency=dim,
                    evidence_ids=eids,
                )
            )

        scores = [r.normalized_score for r in rows]
        if len(scores) >= 2 and (max(scores) - min(scores)) >= INCONSISTENT_RANGE:
            findings.append(
                _finding(
                    "inconsistent_performance",
                    f"{dim} varies widely across evidence (range {min(scores):.0f}–{max(scores):.0f}).",
                    subject_id=subject_id,
                    competency=dim,
                    evidence_ids=eids,
                )
            )

        # Month-to-month using timeline months with data
        month_scores = []
        for m in timeline["months"]:
            sc = (m.get("scores") or {}).get(dim)
            if sc is not None:
                month_scores.append((m["period_id"], float(sc), m.get("evidence_ids") or []))
        if len(month_scores) >= MIN_POINTS_FOR_TREND:
            first_id, first_val, first_e = month_scores[0]
            last_id, last_val, last_e = month_scores[-1]
            delta = last_val - first_val
            if delta >= IMPROVE_DELTA:
                findings.append(
                    _finding(
                        "recent_improvement",
                        f"{dim} improved from {first_val} ({first_id}) to {last_val} ({last_id}).",
                        subject_id=subject_id,
                        competency=dim,
                        evidence_ids=list(first_e) + list(last_e),
                        period_ids=[first_id, last_id],
                    )
                )
            elif delta <= -DECLINE_DELTA:
                findings.append(
                    _finding(
                        "declining_performance",
                        f"{dim} declined from {first_val} ({first_id}) to {last_val} ({last_id}).",
                        subject_id=subject_id,
                        competency=dim,
                        evidence_ids=list(first_e) + list(last_e),
                        period_ids=[first_id, last_id],
                    )
                )

        if mean is not None and mean <= WEAK_CEILING:
            findings.append(
                _finding(
                    "requires_attention",
                    f"{dim} should be prioritized for teacher-reviewed practice planning.",
                    subject_id=subject_id,
                    competency=dim,
                    evidence_ids=eids,
                )
            )

    return {
        "student_id": student.id,
        "subject_id": subject_id,
        "findings": findings,
        "methodology": "progress_explanation.v1.deterministic",
    }
