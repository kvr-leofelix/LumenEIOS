from starlette.concurrency import run_in_threadpool
from backend.app.api.record_access import school_ids
from backend.app.api.dependencies import require_bearer_token
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user, require_roles
from backend.app.core.security import get_password_hash
from backend.app.db.session import get_db
from backend.app.models.entities import User, School, SchoolMembership, AuditEvent, utc_now
from backend.app.schemas.auth import UserOut, UserCreate, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"], dependencies=[Depends(require_bearer_token)])


@router.get("", response_model=List[UserOut])
async def list_users(
    role: Optional[str] = Query(None),
    school_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "principal"))
):
    query = select(User)
    if current_user.role != "admin":
        query = query.filter(User.school_id.in_(await school_ids(db, current_user)))
    if role and role != "all":
        query = query.filter(User.role == role)
    if school_id:
        query = query.filter(User.school_id == school_id)
    if search:
        query = query.filter(User.name.ilike(f"%{search}%") | User.email.ilike(f"%{search}%"))

    result = await db.execute(query.order_by(User.name))
    return result.scalars().all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    req: UserCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_roles("admin"))
):
    if req.school_id is not None and await db.get(School, req.school_id) is None:
        raise HTTPException(status_code=404, detail="School not found.")
    existing = await db.execute(select(User).filter(User.email == req.email.lower()))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="User email already registered.")

    user = User(
        email=req.email.lower(),
        name=req.name,
        hashed_password=await run_in_threadpool(get_password_hash, req.password),
        role=req.role,
        school_id=req.school_id,
        designation=req.designation,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        duplicate = (await db.execute(select(User.id).where(User.email == req.email.lower()))).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="User could not be created because a record already exists.")
        raise
    await db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    req: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_roles("admin"))
):
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if req.school_id is not None and await db.get(School, req.school_id) is None:
        raise HTTPException(status_code=404, detail="School not found.")
    for field, val in req.model_dump(exclude_unset=True).items():
        setattr(user, field, val)

    await db.commit()
    await db.refresh(user)
    return user

