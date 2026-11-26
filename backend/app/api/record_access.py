"""Small record checks shared by legacy routers; use existing school and account links."""
from fastapi import HTTPException
from sqlalchemy import select

from backend.app.models.entities import ClassSection, Student, SchoolMembership
from backend.app.modules.differentiated_homework.access import has_school_access, can_view_student
from backend.app.modules.differentiated_homework.student_access import resolve_linked_student


async def school_ids(db, user):
    ids = {user.school_id} if user.school_id else set()
    rows = await db.execute(select(SchoolMembership.school_id).where(
        SchoolMembership.user_id == user.id, SchoolMembership.is_active.is_(True)))
    ids.update(rows.scalars().all())
    return ids


async def check_school(db, user, school_id):
    allowed = (await has_school_access(db, user, school_id) if user.role in {'admin','principal','teacher'}
               else user.role in {'student','parent'} and bool(user.school_id) and user.school_id == school_id)
    if not allowed:
        raise HTTPException(status_code=404, detail="Record not found.")


async def school_record(db, user, model, record_id):
    record = await db.get(model, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    await check_school(db, user, record.school_id)
    return record


async def class_record(db, user, class_id):
    return await school_record(db, user, ClassSection, class_id)


async def student_record(db, user, student_id):
    student = await db.get(Student, student_id)
    if user.role == 'student':
        linked = await resolve_linked_student(db, user)
        allowed = student is not None and linked is not None and linked.id == student.id
    else:
        allowed = student is not None and await can_view_student(db, user, student)
    if not allowed:
        raise HTTPException(status_code=404, detail="Record not found.")
    return student
