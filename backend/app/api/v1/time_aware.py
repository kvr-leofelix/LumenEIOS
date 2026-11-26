from backend.app.api.record_access import check_school, class_record
from backend.app.api.dependencies import require_bearer_token
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user, require_roles
from backend.app.db.session import get_db
from backend.app.models.entities import (
    ClassSection,
    InstructionalDisruption,
    CurriculumDay,
    CurriculumProposal,
    CrossCurricularProposal,
    User,
    AuditEvent,
    Notification,
    utc_now,
)
from backend.app.schemas.time_aware import (
    CalculatePacingRequest,
    PacingMetricsOut,
    CompressionProposalOut,
    TopicSummary,
    ProposalDecisionRequest,
    CrossCurricularProposalOut,
)
from backend.app.services.time_aware_engine import calculate_pacing_metrics

router = APIRouter(tags=["Time-Aware Pedagogical Engine"], dependencies=[Depends(require_bearer_token)])


@router.post("/classes/{class_id}/time-aware/calculate", response_model=PacingMetricsOut)
async def calculate_class_pacing(
    class_id: str,
    req: CalculatePacingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher"))
):
    cls_res = await db.execute(select(ClassSection).filter(ClassSection.id == class_id))
    cls = cls_res.scalars().first()
    if cls is None:
        raise HTTPException(status_code=404, detail="Class not found.")
    await check_school(db, current_user, cls.school_id)
    school_id = cls.school_id

    disruptions_res = await db.execute(select(InstructionalDisruption).filter(InstructionalDisruption.school_id == school_id))
    disruptions = disruptions_res.scalars().all()

    curriculum_res = await db.execute(select(CurriculumDay).filter(CurriculumDay.class_id == class_id))
    curriculum = curriculum_res.scalars().all()

    metrics = calculate_pacing_metrics(req.total_official_days, req.current_day, disruptions, curriculum)
    return PacingMetricsOut(**metrics)


LEGACY_COMPRESSION_RETIRED = (
    "Legacy syllabus compression is retired: it applied a fixed Core/Non-Core ratio to curriculum rows that have no "
    "approved topic-level period requirements. Use the planning workspace (/planning/workspace): approved topic "
    "requirements, lost-period recording and Principal/Admin-approved recovery proposals."
)


@router.post("/classes/{class_id}/time-aware/compression-preview", response_model=CompressionProposalOut)
async def preview_syllabus_compression(
    class_id: str,
    req: CalculatePacingRequest,
    current_user: User = Depends(require_roles("admin", "principal", "teacher"))
):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=LEGACY_COMPRESSION_RETIRED)


@router.post("/curriculum-proposals/{proposal_id}/approve")
async def approve_compression_proposal(
    proposal_id: str,
    req: ProposalDecisionRequest,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher"))
):
    res = await db.execute(select(CurriculumProposal).filter(CurriculumProposal.id == proposal_id))
    proposal = res.scalars().first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    # School scoping first: an educator outside the proposal's school must not learn that it exists (or its state).
    await check_school(db, educator, proposal.school_id)
    # Historical proposals are preserved untouched; approving one would apply the retired fixed-ratio compression.
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=LEGACY_COMPRESSION_RETIRED)


@router.post("/curriculum-proposals/{proposal_id}/reject")
async def reject_compression_proposal(
    proposal_id: str,
    req: ProposalDecisionRequest,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher"))
):
    res = await db.execute(select(CurriculumProposal).filter(CurriculumProposal.id == proposal_id))
    proposal = res.scalars().first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found.")

    await check_school(db, educator, proposal.school_id)
    await class_record(db, educator, proposal.class_id)
    proposal.status = "rejected"
    await db.commit()
    return {"message": "Proposal rejected."}


@router.get("/classes/{class_id}/curriculum/cross-curricular-proposals", response_model=List[CrossCurricularProposalOut])
async def list_cross_curricular_proposals(
    class_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher"))
):
    cls = await class_record(db, current_user, class_id)
    res = await db.execute(select(CrossCurricularProposal).where(CrossCurricularProposal.class_id == class_id, CrossCurricularProposal.school_id == cls.school_id))
    proposals = res.scalars().all()
    return [
        CrossCurricularProposalOut(
            id=p.id,
            title=p.title,
            subject_ids=p.subject_ids_json,
            subject_names=p.subject_names_json,
            target_day_numbers=p.target_day_numbers_json,
            learning_objectives=p.learning_objectives_json,
            activity=p.activity,
            vark_modality=p.vark_modality,
            bloom_level=p.bloom_level,
            estimated_duration_hours=p.estimated_duration_hours,
            time_saved_hours=p.time_saved_hours,
            status=p.status
        ) for p in proposals
    ]


@router.post("/cross-curricular-proposals/{proposal_id}/accept")
async def accept_cross_curricular_proposal(
    proposal_id: str,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher"))
):
    res = await db.execute(select(CrossCurricularProposal).filter(CrossCurricularProposal.id == proposal_id))
    prop = res.scalars().first()
    if not prop:
        raise HTTPException(status_code=404, detail="Proposal not found.")

    await check_school(db, educator, prop.school_id)
    await class_record(db, educator, prop.class_id)
    prop.status = "accepted"

    audit = AuditEvent(
        timestamp=utc_now().strftime("%Y-%m-%d %H:%M"),
        user_id=educator.id,
        user_name=educator.name,
        action="Approved Cross-Curricular Integration",
        details=f"Merged synergy project '{prop.title}', saving {prop.time_saved_hours} hours.",
        category="curriculum"
    )
    db.add(audit)
    await db.commit()
    return {"message": f"Proposal '{prop.title}' accepted.", "hours_saved": prop.time_saved_hours}


@router.post("/cross-curricular-proposals/{proposal_id}/reject")
async def reject_cross_curricular_proposal(
    proposal_id: str,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher"))
):
    res = await db.execute(select(CrossCurricularProposal).filter(CrossCurricularProposal.id == proposal_id))
    prop = res.scalars().first()
    if not prop:
        raise HTTPException(status_code=404, detail="Proposal not found.")

    await check_school(db, educator, prop.school_id)
    await class_record(db, educator, prop.class_id)
    prop.status = "rejected"
    await db.commit()
    return {"message": "Proposal rejected."}
