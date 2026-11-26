"""Unified calendar for every role: read the merged feed, manage your own tasks and deadlines."""
from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import require_roles
from backend.app.db.session import get_db
from backend.app.models.calendar_events import PersonalCalendarEvent
from backend.app.models.entities import User
from backend.app.services.calendar_hub_service import CATEGORIES, collect_events, parse_day, personal_to_event

ROLES = ("admin", "principal", "teacher", "student", "parent")
MAX_PERSONAL = 1000
router = APIRouter(prefix="/calendar", tags=["Calendar"])


def _iso(value: Optional[str]) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("Use a valid date in YYYY-MM-DD format.") from exc


class PersonalIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    kind: Literal["TASK", "DEADLINE"] = "TASK"
    start_date: str
    end_date: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Enter a title.")
        return v

    @field_validator("start_date", "end_date")
    @classmethod
    def _dates(cls, v: Optional[str]) -> Optional[str]:
        return _iso(v)


class PersonalPatch(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=120)
    kind: Optional[Literal["TASK", "DEADLINE"]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=500)
    is_done: Optional[bool] = None

    @field_validator("start_date", "end_date")
    @classmethod
    def _dates(cls, v: Optional[str]) -> Optional[str]:
        return _iso(v)


def _check_span(start: str, end: Optional[str]) -> None:
    if end and end < start:
        raise HTTPException(422, "The end date is before the start date.")


@router.get("/events")
async def list_events(
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    x_school_id: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(*ROLES, authenticated=True)),
):
    lo = start or date.today().replace(day=1)
    hi = end or (lo + timedelta(days=41))
    try:
        data = await collect_events(db, user, x_school_id or user.school_id, lo, hi)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    data["categories"] = list(CATEGORIES)
    return data


@router.post("/personal", status_code=status.HTTP_201_CREATED)
async def add_personal(
    body: PersonalIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(*ROLES, authenticated=True)),
):
    _check_span(body.start_date, body.end_date)
    owned = await db.scalar(select(func.count()).select_from(PersonalCalendarEvent).where(PersonalCalendarEvent.user_id == user.id))
    if (owned or 0) >= MAX_PERSONAL:
        raise HTTPException(422, f"You can keep up to {MAX_PERSONAL} personal items. Delete old ones first.")
    row = PersonalCalendarEvent(user_id=user.id, school_id=user.school_id, title=body.title, kind=body.kind,
                                start_date=body.start_date, end_date=body.end_date, notes=(body.notes or "").strip() or None)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return personal_to_event(row)


async def _own(db: AsyncSession, user: User, item_id: str) -> PersonalCalendarEvent:
    row = await db.get(PersonalCalendarEvent, item_id)
    if not row or row.user_id != user.id:  # someone else's item is indistinguishable from a missing one
        raise HTTPException(404, "Calendar item not found.")
    return row


@router.patch("/personal/{item_id}")
async def update_personal(
    item_id: str,
    body: PersonalPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(*ROLES, authenticated=True)),
):
    row = await _own(db, user, item_id)
    changes = body.model_dump(exclude_unset=True)
    if "title" in changes:
        title = (changes["title"] or "").strip()
        if not title:
            raise HTTPException(422, "Enter a title.")
        row.title = title
    if "kind" in changes and changes["kind"]:
        row.kind = changes["kind"]
    if changes.get("start_date"):
        row.start_date = changes["start_date"]
    if "end_date" in changes:
        row.end_date = changes["end_date"]
    if "notes" in changes:
        row.notes = (changes["notes"] or "").strip() or None
    if "is_done" in changes and changes["is_done"] is not None:
        row.is_done = changes["is_done"]
    _check_span(row.start_date, row.end_date)
    await db.commit()
    await db.refresh(row)
    return personal_to_event(row)


@router.delete("/personal/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_personal(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(*ROLES, authenticated=True)),
):
    row = await _own(db, user, item_id)
    await db.delete(row)
    await db.commit()
