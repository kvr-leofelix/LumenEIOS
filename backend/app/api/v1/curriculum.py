from backend.app.api.record_access import check_school, class_record
from backend.app.api.dependencies import require_bearer_token
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user, require_roles
from backend.app.db.session import get_db
from backend.app.models.entities import CurriculumDay, User, AuditEvent, utc_now
from backend.app.schemas.curriculum import CurriculumDayOut, LessonCompleteRequest

router = APIRouter(prefix="/curriculum", tags=["180-Day Curriculum"], dependencies=[Depends(require_bearer_token)])


@router.get("/classes/{class_id}", response_model=List[CurriculumDayOut])
async def list_class_curriculum(
    class_id: str,
    classification: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None),
    vark: Optional[str] = Query(None),
    limit: int = Query(180, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher"))
):
    await class_record(db, current_user, class_id)
    query = select(CurriculumDay).filter(CurriculumDay.class_id == class_id)
    if classification and classification != "all":
        query = query.filter(CurriculumDay.classification == classification)
    if status_filter and status_filter != "all":
        query = query.filter(CurriculumDay.status == status_filter)
    if vark and vark != "all":
        query = query.filter(CurriculumDay.vark_modality == vark)

    res = await db.execute(query.order_by(CurriculumDay.day_number).limit(limit))
    return res.scalars().all()


@router.get("/days/{day_id}", response_model=CurriculumDayOut)
async def get_curriculum_day(day_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_roles("admin", "principal", "teacher"))):
    res = await db.execute(select(CurriculumDay).filter(CurriculumDay.id == day_id))
    day = res.scalars().first()
    if not day:
        raise HTTPException(status_code=404, detail="Curriculum day lesson not found.")
    await class_record(db, current_user, day.class_id)
    return day


@router.post("/days/{day_id}/complete")
async def complete_curriculum_day(
    day_id: str,
    req: LessonCompleteRequest,
    db: AsyncSession = Depends(get_db),
    educator: User = Depends(require_roles("admin", "principal", "teacher"))
):
    res = await db.execute(select(CurriculumDay).filter(CurriculumDay.id == day_id))
    day = res.scalars().first()
    if not day:
        raise HTTPException(status_code=404, detail="Lesson not found.")

    await class_record(db, educator, day.class_id)
    day.status = "completed"

    audit = AuditEvent(
        timestamp=utc_now().strftime("%Y-%m-%d %H:%M"),
        user_id=educator.id,
        user_name=educator.name,
        action="Completed Curriculum Lesson",
        details=f"Completed Day {day.day_number}: {day.topic}",
        category="curriculum"
    )
    db.add(audit)
    await db.commit()
    return {"message": f"Day {day.day_number} marked as completed."}

