from backend.app.api.dependencies import require_bearer_token
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user, require_roles, get_current_school_context
from backend.app.db.session import get_db
from backend.app.models.entities import Notification, Announcement, User
from backend.app.services import announcement_service as announcements
from backend.app.schemas.common import NotificationOut, AnnouncementCreate, AnnouncementOut

router = APIRouter(tags=["Notifications & Announcements"], dependencies=[Depends(require_bearer_token)])


@router.get("/notifications", response_model=List[NotificationOut])
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    res = await db.execute(
        select(Notification).filter(
            Notification.user_id == current_user.id
        ).order_by(Notification.created_at.desc())
    )
    return res.scalars().all()


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    res = await db.execute(select(Notification).filter(Notification.id == notification_id, Notification.user_id == current_user.id))
    notif = res.scalars().first()
    if notif is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    if notif:
        notif.is_read = True
        await db.commit()
    return {"message": "Notification marked as read."}


@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    res = await db.execute(select(Notification).filter(Notification.user_id == current_user.id))
    for n in res.scalars().all():
        n.is_read = True
    await db.commit()
    return {"message": "All notifications marked as read."}


@router.get("/announcements/options")
async def announcement_options(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context),
):
    """What this sender may address: the three groups, and the classes whose students/parents they can reach."""
    classes = await announcements.sendable_classes(db, current_user, school_id)
    return {"audiences": list(announcements.AUDIENCE_ROLES), "classes": [{"id": c.id, "name": c.name} for c in classes],
            "scope": "classes you teach" if current_user.role == "teacher" else "whole school"}


@router.post("/announcements", response_model=AnnouncementOut)
async def create_announcement(
    req: AnnouncementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
    school_id: str = Depends(get_current_school_context)
):
    audience = req.audience if req.audience is not None else announcements.legacy_audience(req.target_role or "teacher")
    ann, count = await announcements.create_announcement(
        db, current_user, school_id, title=req.title, content=req.content, audience=audience,
        class_ids=req.class_ids, event_start=req.event_start, event_end=req.event_end)
    return announcements.to_out(ann, current_user, await announcements.class_names(db, [ann]), recipients=count)


@router.get("/announcements", response_model=List[AnnouncementOut])
async def list_announcements(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    school_id: str = Depends(get_current_school_context)
):
    scope = None if current_user.role in announcements.LEARNER_ROLES else {school_id}
    rows = await announcements.visible_announcements(db, current_user, scope)
    names = await announcements.class_names(db, rows)
    return [announcements.to_out(a, current_user, names) for a in rows]


@router.delete("/announcements/{announcement_id}", status_code=204)
async def delete_announcement(
    announcement_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal", "teacher")),
):
    await announcements.delete_announcement(db, current_user, announcement_id)
