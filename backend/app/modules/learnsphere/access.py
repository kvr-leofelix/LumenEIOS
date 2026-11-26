"""Fail-closed record access, shared by selectors and individual endpoints."""
from fastapi import HTTPException
from sqlalchemy import select
from backend.app.api.dependencies import user_school_ids
from backend.app.models.entities import ClassSection, Student, ParentStudentLink
from backend.app.modules.differentiated_homework.student_access import require_linked_student


async def student_query(db, user):
    query = select(Student).join(ClassSection, Student.class_id == ClassSection.id).where(
        Student.school_id == ClassSection.school_id)
    if user.role == "admin":
        pass
    elif user.role in {"principal", "teacher"}:
        query = query.where(Student.school_id.in_(await user_school_ids(db, user)))
        if user.role == "teacher":
            query = query.where(ClassSection.class_teacher_id == user.id)
    elif user.role == "parent":
        query = query.where(Student.id.in_(select(ParentStudentLink.student_id).where(
            ParentStudentLink.parent_user_id == user.id)))
    elif user.role == "student":
        student = await require_linked_student(db, user)
        query = query.where(Student.id == student.id)
    else:
        raise HTTPException(403, "This role cannot access LearnSphere.")
    return query


async def authorized_students(db, user):
    return list((await db.scalars((await student_query(db, user)).order_by(Student.name))).all())


async def require_student(db, user, student_id):
    student = await db.scalar((await student_query(db, user)).where(Student.id == student_id))
    if student is None:
        raise HTTPException(404, "Student unavailable in your authorized scope.")
    return student


async def require_class(db, user, class_id):
    section = await db.get(ClassSection, class_id)
    if user.role not in {"admin", "principal", "teacher"}:
        raise HTTPException(403, "An educator account is required.")
    if not section or (user.role != "admin" and section.school_id not in await user_school_ids(db, user)):
        raise HTTPException(404, "Class unavailable in your authorized scope.")
    if user.role == "teacher" and section.class_teacher_id != user.id:
        raise HTTPException(404, "Class unavailable in your authorized scope.")
    return section
