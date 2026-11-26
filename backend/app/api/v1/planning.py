"""Authoritative curriculum-planning workspace API (Academic Configuration, syllabus governance, plans,
execution and recovery). One versioned document per school; every write is a new append-only revision."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_school_context, get_current_user, require_bearer_token
from backend.app.db.session import get_db
from backend.app.models.entities import User
from backend.app.models.planning_workspace import PlanningWorkspaceRevision
from backend.app.services.planning_workspace_service import ACTION_ROLES, MIGRATED_ACTIONS, authorize_changes, stamp_audit, validate_shape

router = APIRouter(prefix="/planning", tags=["Curriculum Planning"], dependencies=[Depends(require_bearer_token)])

STAFF = {"admin", "principal", "teacher"}


class WorkspaceOut(BaseModel):
    revision: int
    state: Optional[Dict[str, Any]]
    updated_at: Optional[str]
    updated_by: Optional[str]


class WorkspaceSave(BaseModel):
    expected_revision: int = Field(ge=0)
    action: str
    summary: str = Field(min_length=1, max_length=500)
    state: Dict[str, Any]


class RevisionOut(BaseModel):
    revision: int
    action: str
    summary: str
    actor_name: str
    actor_role: str
    created_at: str


async def _latest(db: AsyncSession, school_id: str) -> Optional[PlanningWorkspaceRevision]:
    res = await db.execute(
        select(PlanningWorkspaceRevision)
        .filter(PlanningWorkspaceRevision.school_id == school_id)
        .order_by(PlanningWorkspaceRevision.revision.desc())
        .limit(1)
    )
    return res.scalars().first()


def _out(row: Optional[PlanningWorkspaceRevision]) -> WorkspaceOut:
    if row is None:
        return WorkspaceOut(revision=0, state=None, updated_at=None, updated_by=None)
    return WorkspaceOut(revision=row.revision, state=row.state, updated_at=row.created_at.isoformat(), updated_by=row.actor_name)


def _require_staff(user: User) -> None:
    if user.role not in STAFF:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Curriculum planning is limited to school staff.")


@router.get("/workspace", response_model=WorkspaceOut)
async def get_workspace(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    school_id: str = Depends(get_current_school_context),
):
    _require_staff(user)
    return _out(await _latest(db, school_id))


@router.put("/workspace", response_model=WorkspaceOut)
async def save_workspace(
    body: WorkspaceSave,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    school_id: str = Depends(get_current_school_context),
):
    _require_staff(user)
    if body.action in MIGRATED_ACTIONS:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=f"'{body.action}' no longer writes the workspace document; use {MIGRATED_ACTIONS[body.action]}.")
    allowed = ACTION_ROLES.get(body.action)
    if allowed is None:
        raise HTTPException(status_code=422, detail=f"Unknown action '{body.action}'.")
    if user.role not in allowed:
        raise HTTPException(status_code=403, detail=f"Role '{user.role}' cannot perform {body.action}.")
    problem = validate_shape(body.state)
    if problem:
        raise HTTPException(status_code=422, detail=problem)

    current = await _latest(db, school_id)
    current_rev = current.revision if current else 0
    if body.expected_revision != current_rev:
        raise HTTPException(status_code=409, detail=f"Workspace changed (now revision {current_rev}). Reload and retry.")

    violations = authorize_changes(current.state if current else None, body.state, user.role)
    if violations:
        raise HTTPException(status_code=403, detail="; ".join(violations))

    state = dict(body.state)
    state["audit"] = [dict(a) for a in state["audit"]]
    stamp_audit(len(current.state["audit"]) if current else 0, state, {"id": user.id, "name": user.name, "role": user.role})

    row = PlanningWorkspaceRevision(
        school_id=school_id,
        revision=current_rev + 1,
        action=body.action,
        summary=body.summary,
        actor_id=user.id,
        actor_name=user.name,
        actor_role=user.role,
        state=state,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Another save completed first. Reload and retry.")
    return _out(row)


@router.get("/workspace/history", response_model=List[RevisionOut])
async def workspace_history(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    school_id: str = Depends(get_current_school_context),
):
    _require_staff(user)
    res = await db.execute(
        select(PlanningWorkspaceRevision)
        .filter(PlanningWorkspaceRevision.school_id == school_id)
        .order_by(PlanningWorkspaceRevision.revision.desc())
        .limit(limit)
    )
    return [
        RevisionOut(revision=r.revision, action=r.action, summary=r.summary, actor_name=r.actor_name, actor_role=r.actor_role, created_at=r.created_at.isoformat())
        for r in res.scalars().all()
    ]
