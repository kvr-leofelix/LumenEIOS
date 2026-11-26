"""Authorization for Unified Student Progress — reuses existing school/link rules."""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import Student, User
from backend.app.modules.differentiated_homework.access import can_view_student
from backend.app.modules.differentiated_homework.student_access import require_linked_student
from backend.app.modules.student_progress.schemas import Audience


class ProgressAccessError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def audience_for(user: User) -> Audience:
    if user.role in {"admin", "principal", "teacher"}:
        return "educator"
    return "student_or_parent"


async def require_educator_student(db: AsyncSession, user: User, student_id: str) -> Student:
    """Teachers/principals/admins: school-scoped student access (same as DH can_view_student)."""
    if user.role not in {"admin", "principal", "teacher"}:
        raise ProgressAccessError(status.HTTP_403_FORBIDDEN, "Access denied.")
    student = await db.get(Student, student_id)
    if student is None or not await can_view_student(db, user, student):
        raise ProgressAccessError(status.HTTP_404_NOT_FOUND, "Student not found.")
    return student


async def require_own_student(db: AsyncSession, user: User) -> Student:
    if user.role != "student":
        raise ProgressAccessError(status.HTTP_403_FORBIDDEN, "Access denied.")
    return await require_linked_student(db, user)


async def require_parent_child(db: AsyncSession, user: User, student_id: str) -> Student:
    if user.role != "parent":
        raise ProgressAccessError(status.HTTP_403_FORBIDDEN, "Access denied.")
    student = await db.get(Student, student_id)
    if student is None or not await can_view_student(db, user, student):
        raise ProgressAccessError(status.HTTP_404_NOT_FOUND, "Student not found.")
    return student


def as_http(exc: ProgressAccessError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)
