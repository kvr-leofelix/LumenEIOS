import json
import math
from fastapi import Request
from typing import List, Optional
from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from backend.app.core.config import settings
from backend.app.core.security import decode_token
from backend.app.db.session import get_db
from backend.app.models.entities import User, SchoolMembership

class AccessTokenBearer(HTTPBearer):
    async def __call__(self, request: Request) -> Optional[str]:
        credentials = await super().__call__(request)
        return credentials.credentials if credentials is not None else None


# Keep the existing import name for callers; document the actual JSON-login + JWT contract.
oauth2_scheme = AccessTokenBearer(auto_error=False, scheme_name="BearerAuth", bearerFormat="JWT",
    description="Obtain an access_token with JSON POST /auth/login, then supply it as a bearer token.")


async def require_bearer_token(token: Optional[str] = Depends(oauth2_scheme)) -> None:
    """Opt sensitive routers out of the inherited tokenless demo-admin shortcut."""
    if not token:
        raise HTTPException(status_code=401, detail="Authentication token required.",
                            headers={"WWW-Authenticate": "Bearer"})


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    if not token:
        # Never treat an anonymous request as a user, not even in DEMO_MODE: an "anonymous = admin" shortcut let
        # anyone on the network read and change every school's data without signing in.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token required.")
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")
        if payload.get("demo_root") and not settings.demo_root_enabled:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials.")

    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


async def require_bearer_token(token: Optional[str] = Depends(oauth2_scheme)) -> None:
    """Router-level guard for governed workflows: a real bearer token is mandatory, even when DEMO_MODE is on.

    DEMO_MODE otherwise resolves an anonymous request to the first admin, which would let anyone bypass role checks
    by calling the API directly. Approval, execution and schedule data must never be reachable that way.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_roles(*allowed_roles: str, authenticated: bool = False):
    def role_checker(
        current_user: User = Depends(get_current_user),
        token: Optional[str] = Depends(oauth2_scheme),
    ) -> User:
        # Teammate routes can require a real bearer token even when DEMO_MODE seeds exist.
        if authenticated and not token:
            raise HTTPException(status_code=401, detail="Authentication token required.")
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted for role '{current_user.role}'. Required: {allowed_roles}."
            )
        return current_user
    return role_checker


async def user_school_ids(db: AsyncSession, user: User) -> set[str]:
    """Schools a non-admin user belongs to: their home school plus active memberships."""
    rows = await db.execute(
        select(SchoolMembership.school_id).where(
            SchoolMembership.user_id == user.id, SchoolMembership.is_active == True  # noqa: E712
        )
    )
    return {school_id for school_id in rows.scalars()} | ({user.school_id} if user.school_id else set())


async def require_school_access(db: AsyncSession, user: User, school_id: str) -> None:
    """Admins reach every school; everyone else only the schools they belong to."""
    if user.role == "admin" or school_id in await user_school_ids(db, user):
        return
    # 404, not 403: another school's records must not even be confirmed to exist.
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")


async def require_class_access(db: AsyncSession, user: User, cls) -> None:
    """Staff see every class in their schools. A student sees only their own class and a parent only their linked
    children's classes; any other class is reported as not found, exactly like a missing one."""
    await require_school_access(db, user, cls.school_id)
    if user.role not in ("student", "parent"):
        return
    from backend.app.models.entities import ParentStudentLink, Student
    if user.role == "student":
        from backend.app.modules.differentiated_homework.student_access import resolve_linked_student
        own = await resolve_linked_student(db, user)
        allowed = own is not None and own.class_id == cls.id
    else:
        allowed = (await db.execute(
            select(Student.id).join(ParentStudentLink, ParentStudentLink.student_id == Student.id)
            .filter(ParentStudentLink.parent_user_id == user.id, Student.class_id == cls.id).limit(1)
        )).first() is not None
    if not allowed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found.")


async def get_current_school_context(
    x_school_id: Optional[str] = Header(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> str:
    """
    Resolves the active school context.
    Admins can select any school via X-School-Id.
    Other roles are restricted to their authorized school.
    """
    target = x_school_id or current_user.school_id or "school-1"
    
    if current_user.role == "admin":
        return target
        
    if current_user.school_id == target:
        return target
        
    # Check memberships
    result = await db.execute(
        select(SchoolMembership).filter(
            SchoolMembership.user_id == current_user.id,
            SchoolMembership.school_id == target,
            SchoolMembership.is_active == True
        )
    )
    if result.scalars().first():
        return target

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Unauthorized school context access."
    )



async def reject_non_finite_json(request: Request) -> None:
    """422 for NaN, Infinity or out-of-range numbers in the body, before normal validation.

    Python's JSON parser accepts NaN and Infinity. Strict validation would reject them, but the
    standard 422 response echoes the input back and NaN can't be written as JSON, so the error
    response itself would fail (500). Bodies that aren't valid JSON are left to FastAPI."""
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
    if content_type and content_type != "application/json" and not content_type.endswith("+json"):
        return
    raw = await request.body()
    if not raw:
        return

    class NonFinite(ValueError):
        """Raised only by the hooks below, so it can't be confused with a parse error."""

    def finite(text_value: str) -> float:
        value = float(text_value)
        if not math.isfinite(value):  # e.g. 1e309, which Python turns into inf
            raise NonFinite()
        return value

    def refuse(constant: str):  # NaN, Infinity, -Infinity
        raise NonFinite()

    try:
        json.loads(raw, parse_float=finite, parse_constant=refuse)
    except NonFinite:
        raise HTTPException(status_code=422, detail=[{
            "loc": ["body"], "msg": "Numbers must be finite: NaN and Infinity are not allowed.",
            "type": "value_error",
        }])
    except ValueError:
        pass  # not valid JSON (or too many digits): FastAPI's own body parsing reports it

