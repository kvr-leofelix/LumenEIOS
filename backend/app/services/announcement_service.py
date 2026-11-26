"""Announcements: a role-limited broadcast that can optionally be marked on the calendar.

Who may reach whom
  * principal / admin -> teachers, students, parents of their school (whole school, or chosen classes for students/parents)
  * teacher           -> other teachers of their school, and the students / parents of the classes they teach

An announcement only ever *reads* the academic calendar; it never writes to Academic Config, working days or lost days.
The audience is enforced here, on the server, for the list, the notifications and the calendar feed alike.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import user_school_ids
from backend.app.models.entities import (
    Announcement, ClassSection, Notification, ParentStudentLink, SchoolMembership, Student, TeacherAssignment, User,
)
from backend.app.modules.differentiated_homework.models import StudentAccountLink

AUDIENCE_ROLES = ("teacher", "student", "parent")
STAFF_SENDERS = ("admin", "principal", "teacher")
LEARNER_ROLES = ("student", "parent")
PREVIEW_CHARS = 180


def legacy_audience(target_role: Optional[str]) -> List[str]:
    """Rows written before broadcasts only had one target role (``all`` meant everyone)."""
    if not target_role or target_role == "all":
        return list(AUDIENCE_ROLES)
    return [target_role]


def audience_of(ann: Announcement) -> List[str]:
    return list(ann.audience_json) if ann.audience_json else legacy_audience(ann.target_role)


async def sendable_classes(db: AsyncSession, user: User, school_id: str) -> List[ClassSection]:
    """Classes whose students and parents this sender may address."""
    query = select(ClassSection).where(ClassSection.school_id == school_id)
    if user.role == "teacher":
        taught = select(TeacherAssignment.class_id).where(TeacherAssignment.teacher_id == user.id)
        query = query.where(or_(ClassSection.class_teacher_id == user.id, ClassSection.id.in_(taught)))
    rows = (await db.scalars(query.order_by(ClassSection.grade, ClassSection.section))).all()
    return list(rows)


async def _staff_ids(db: AsyncSession, school_id: str, role: str) -> Set[str]:
    home = select(User.id).where(User.role == role, User.school_id == school_id)
    member = select(User.id).join(SchoolMembership, SchoolMembership.user_id == User.id).where(
        User.role == role, SchoolMembership.school_id == school_id, SchoolMembership.is_active == True)  # noqa: E712
    return set((await db.scalars(home)).all()) | set((await db.scalars(member)).all())


async def resolve_recipients(db: AsyncSession, school_id: str, audience: Iterable[str], class_ids: Optional[List[str]]) -> Set[str]:
    """User ids that should receive a notification. Students/parents are matched through their linked records."""
    audience = set(audience)
    out: Set[str] = set()
    if "teacher" in audience:
        out |= await _staff_ids(db, school_id, "teacher")
    if audience & set(LEARNER_ROLES):
        pupils = select(Student.id).where(Student.school_id == school_id)
        if class_ids is not None:
            pupils = pupils.where(Student.class_id.in_(class_ids))
        if "student" in audience:
            out |= set((await db.scalars(select(StudentAccountLink.user_id).where(StudentAccountLink.student_id.in_(pupils)))).all())
        if "parent" in audience:
            out |= set((await db.scalars(select(ParentStudentLink.parent_user_id).where(ParentStudentLink.student_id.in_(pupils)))).all())
    return out


def normalise_event(start: Optional[str], end: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not start:
        if end:
            raise HTTPException(422, "Add a start date for the event, or clear the end date.")
        return None, None
    try:
        first = date.fromisoformat(start)
        last = date.fromisoformat(end) if end else None
    except ValueError:
        raise HTTPException(422, "Use a valid date in YYYY-MM-DD format.")
    if first < date.today() - timedelta(days=1):
        raise HTTPException(422, "The event date is in the past. Pick today or a later date.")
    if last and last < first:
        raise HTTPException(422, "The event ends before it starts.")
    return first.isoformat(), (last.isoformat() if last and last != first else None)


async def create_announcement(db: AsyncSession, user: User, school_id: str, *, title: str, content: str,
                              audience: List[str], class_ids: Optional[List[str]],
                              event_start: Optional[str], event_end: Optional[str]) -> tuple[Announcement, int]:
    if user.role not in STAFF_SENDERS:
        raise HTTPException(403, "Only staff can post announcements.")
    audience = [r for r in AUDIENCE_ROLES if r in set(audience)]
    if not audience:
        raise HTTPException(422, "Choose at least one group to send this to.")
    reaches_learners = bool(set(audience) & set(LEARNER_ROLES))
    chosen: Optional[List[str]] = None
    if reaches_learners:
        reachable = {c.id for c in await sendable_classes(db, user, school_id)}
        if class_ids:
            if not set(class_ids) <= reachable:
                raise HTTPException(403, "You can only address students and parents of classes you teach.")
            chosen = sorted(set(class_ids))
        elif user.role == "teacher":
            if not reachable:
                raise HTTPException(422, "You have no classes assigned, so there are no students or parents to reach.")
            chosen = sorted(reachable)  # a teacher's "all" means all of *their* classes, never the whole school
    start, end = normalise_event(event_start, event_end)
    ann = Announcement(
        school_id=school_id, sender_id=user.id, sender_name=user.name, sender_role=user.role, title=title, content=content,
        target_role="all" if len(audience) == len(AUDIENCE_ROLES) else audience[0],
        audience_json=audience, class_ids_json=chosen, event_start=start, event_end=end,
    )
    db.add(ann)
    await db.flush()
    recipients = await resolve_recipients(db, school_id, audience, chosen)
    recipients.discard(user.id)
    when = f" · {start}" + (f" to {end}" if end else "") if start else ""
    preview = content if len(content) <= PREVIEW_CHARS else content[:PREVIEW_CHARS].rstrip() + "…"
    for uid in sorted(recipients):
        db.add(Notification(user_id=uid, title=title, message=f"{user.name}: {preview}{when}", type="announcement",
                            link=f"/announcements?id={ann.id}"))
    await db.commit()
    await db.refresh(ann)
    return ann, len(recipients)


async def _viewer_context(db: AsyncSession, user: User) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {"pupils": []}
    if user.role == "student":
        row = (await db.execute(select(Student).join(StudentAccountLink, StudentAccountLink.student_id == Student.id)
                                .where(StudentAccountLink.user_id == user.id))).scalars().first()
        ctx["pupils"] = [row] if row else []
    elif user.role == "parent":
        ctx["pupils"] = list((await db.scalars(select(Student).where(Student.id.in_(
            select(ParentStudentLink.student_id).where(ParentStudentLink.parent_user_id == user.id))))).all())
    return ctx


def _reaches(ann: Announcement, user: User, ctx: Dict[str, Any]) -> bool:
    if ann.sender_id == user.id or user.role in ("admin", "principal"):
        return True  # senders and the school's leadership can always see what was broadcast
    if user.role not in audience_of(ann):
        return False
    if user.role == "teacher":
        return True
    classes = ann.class_ids_json
    return any(p.school_id == ann.school_id and (classes is None or p.class_id in classes) for p in ctx["pupils"])


async def visible_announcements(db: AsyncSession, user: User, school_ids: Optional[Set[str]] = None,
                                *, only_events: bool = False) -> List[Announcement]:
    ctx = await _viewer_context(db, user)
    if school_ids is None:
        if user.role in LEARNER_ROLES:
            school_ids = {p.school_id for p in ctx["pupils"]}
        else:
            school_ids = await user_school_ids(db, user)
    if not school_ids:
        return []
    query = select(Announcement).where(Announcement.school_id.in_(school_ids))
    if only_events:
        query = query.where(Announcement.event_start.is_not(None))
    rows = (await db.scalars(query.order_by(Announcement.created_at.desc()))).all()
    return [a for a in rows if _reaches(a, user, ctx)]


async def class_names(db: AsyncSession, ann_list: List[Announcement]) -> Dict[str, str]:
    ids = {c for a in ann_list for c in (a.class_ids_json or [])}
    if not ids:
        return {}
    return {c.id: c.name for c in (await db.scalars(select(ClassSection).where(ClassSection.id.in_(ids)))).all()}


def to_out(ann: Announcement, user: User, names: Dict[str, str], recipients: Optional[int] = None) -> Dict[str, Any]:
    out = {
        "id": ann.id, "school_id": ann.school_id, "sender_id": ann.sender_id, "sender_name": ann.sender_name,
        "sender_role": ann.sender_role, "title": ann.title, "content": ann.content, "target_role": ann.target_role,
        "audience": audience_of(ann), "class_ids": ann.class_ids_json, "class_names": [names.get(c, c) for c in (ann.class_ids_json or [])],
        "event_start": ann.event_start, "event_end": ann.event_end, "created_at": ann.created_at,
        "can_delete": ann.sender_id == user.id or user.role in ("admin", "principal"),
    }
    if recipients is not None:
        out["recipients"] = recipients
    return out


def calendar_event(ann: Announcement) -> Dict[str, Any]:
    end = ann.event_end or ann.event_start
    return {"id": f"ann:{ann.id}", "category": "announcement", "title": ann.title, "start": ann.event_start, "end": end,
            "source": "announcement", "detail": ann.content[:240], "editable": False, "announcement_id": ann.id,
            "sender_name": ann.sender_name}


async def delete_announcement(db: AsyncSession, user: User, ann_id: str) -> None:
    ann = await db.get(Announcement, ann_id)
    ctx = await _viewer_context(db, user)
    if not ann or not _reaches(ann, user, ctx):
        raise HTTPException(404, "Announcement not found.")
    if ann.sender_id != user.id and user.role not in ("admin", "principal"):
        raise HTTPException(403, "Only the sender or the principal can remove an announcement.")
    if user.role == "principal" and user.id != ann.sender_id and ann.school_id not in await user_school_ids(db, user):
        raise HTTPException(404, "Announcement not found.")
    for note in (await db.scalars(select(Notification).where(Notification.link == f"/announcements?id={ann.id}"))).all():
        await db.delete(note)
    await db.delete(ann)
    await db.commit()
