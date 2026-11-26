"""Regression for same-named Class 11-A sections in different schools.

All roster and answer fixtures live exclusively in conftest's isolated test database.
"""
import uuid

import pytest
from sqlalchemy import select

from backend.app.core.security import create_access_token
from backend.app.models.entities import Assessment, ClassSection, School, SchoolMembership, Student, Subject, User
from backend.app.modules.differentiated_homework.models import StudentAccountLink
from backend.tests.test_learnsphere import learning


@pytest.mark.asyncio
async def test_chemistry_assignment_reaches_linked_class11_student_only_in_target_school(client, db_session):
    prefix = uuid.uuid4().hex
    school_a, school_b, chemistry, english = [prefix + x for x in ("school-a", "school-b", "chem", "eng")]
    class_a, class_b = prefix + "class-a", prefix + "class-b"
    teacher_a = User(id=prefix+"teacher-a", name="Test teacher A", email=prefix+"ta@example.test",
                     hashed_password="unused", role="teacher", school_id=school_a)
    teacher_b = User(id=prefix+"teacher-b", name="Test teacher B", email=prefix+"tb@example.test",
                     hashed_password="unused", role="teacher", school_id=school_b)
    login_a = User(id=prefix+"login-a", name="Enrolled chemistry learner", email=prefix+"sa@example.test",
                   hashed_password="unused", role="student", school_id=school_a)
    login_b = User(id=prefix+"login-b", name="Other-school learner", email=prefix+"sb@example.test",
                   hashed_password="unused", role="student", school_id=school_b)
    pupil_a = Student(id=prefix+"pupil-a", name="Enrolled chemistry learner", school_id=school_a,
                      class_id=class_a, class_name="Class 11-A", roll_no=1)
    pupil_b = Student(id=prefix+"pupil-b", name="Other-school learner", school_id=school_b,
                      class_id=class_b, class_name="Class 11-A", roll_no=1)
    db_session.add_all([
        School(id=school_a, name="JNV Bengaluru", location="Test", state="Test", infrastructure_tier="standard"),
        School(id=school_b, name="Dakshana Kottayam", location="Test", state="Test", infrastructure_tier="standard"),
        Subject(id=chemistry, name="Chemistry", code=prefix+"CHEM", grade=11),
        Subject(id=english, name="English", code=prefix+"ENG", grade=11),
        teacher_a, teacher_b, login_a, login_b,
        ClassSection(id=class_a, name="Class 11-A", school_id=school_a, grade=11, section="A",
                     class_teacher_id=teacher_a.id, subject_ids_json=[chemistry]),
        ClassSection(id=class_b, name="Class 11-A", school_id=school_b, grade=11, section="A",
                     class_teacher_id=teacher_b.id, subject_ids_json=[english]),
        pupil_a, pupil_b,
    ])
    await db_session.flush()
    db_session.add_all([
        StudentAccountLink(user_id=login_a.id, student_id=pupil_a.id, created_by=teacher_a.id),
        StudentAccountLink(user_id=login_b.id, student_id=pupil_b.id, created_by=teacher_b.id),
        SchoolMembership(user_id=teacher_a.id, school_id=school_a, role="teacher", is_active=True),
        SchoolMembership(user_id=teacher_b.id, school_id=school_b, role="teacher", is_active=True),
    ])
    await db_session.commit()
    headers = lambda u: {"Authorization": "Bearer " + create_access_token(u.id)}
    cards = "/api/v1/assessments/upload-assignments"
    assert (await client.get(cards, headers=headers(login_a))).json() == []

    targets = (await client.get("/api/v1/assessments/targets", headers=headers(teacher_a))).json()
    assert len(targets) == 1
    assert targets[0]["id"] == class_a and targets[0]["school_id"] == school_a
    assert targets[0]["name"] == "Class 11-A" and targets[0]["school_name"] == "JNV Bengaluru"
    assert targets[0]["subjects"] == [{"id": chemistry, "name": "Chemistry"}]
    question = {"id": prefix+"question", "text": "What is the chemical symbol for oxygen?", "type": "mcq",
                "options": ["O", "H", "N", "C"], "correct_answer": "O", "marking_rubric": "Identify oxygen.",
                "marks": 2, "competency": "CU", "bloom_level": "Remember"}
    body = {"class_id": class_a, "subject_id": chemistry, "title": "Chemistry Assignment", "date": "2026-11-12",
            "total_marks": 2, "competency_focus": ["CU"], "questions": [question]}
    created = await client.post(f"/api/v1/classes/{class_a}/assessments", headers=headers(teacher_a), json=body)
    assert created.status_code == 201, created.text
    assessment_id = created.json()["id"]
    stored = await db_session.scalar(select(Assessment).where(Assessment.id == assessment_id))
    assert (stored.school_id, stored.class_id, stored.subject_id, stored.status) == (school_a, class_a, chemistry, "scheduled")
    visible = (await client.get(cards, headers=headers(login_a))).json()
    assert len(visible) == 1 and visible[0]["id"] == assessment_id
    assert visible[0]["class_name"] == "Class 11-A" and visible[0]["subject_name"] == "Chemistry"
    assert visible[0]["questions"][0]["text"] == question["text"]
    assert "correct_answer" not in visible[0]["questions"][0]

    # This reproduces the reported roster: an identically named class at another
    # school is not the intended audience, even with a valid StudentAccountLink.
    assert (await client.get(cards, headers=headers(login_b))).json() == []
    answers = {"request_key": prefix, "answers": [{"position": 0, "selected_option_index": 0}]}
    assert (await client.post(f"/api/v1/assessments/{assessment_id}/answers", headers=headers(login_b), json=answers)).status_code == 404
    assert (await client.post(f"/api/v1/classes/{class_b}/assessments", headers=headers(teacher_a),
                              json={**body, "class_id": class_b})).status_code == 404
    assert (await client.post(f"/api/v1/classes/{class_b}/assessments", headers=headers(teacher_b),
                              json={**body, "class_id": class_b})).status_code == 422
    answered = await client.post(f"/api/v1/assessments/{assessment_id}/answers", headers=headers(login_a), json=answers)
    assert answered.status_code == 200, answered.text
    assert answered.json()["student_id"] == pupil_a.id and answered.json()["school_id"] == school_a


@pytest.mark.asyncio
async def test_science_teacher_cannot_assign_chemistry_to_another_teachers_class(client, db_session, learning):
    """Arvind/Garima allocation case: same school is not teaching authorization."""
    l = learning
    chemistry_class = await db_session.get(ClassSection, l.cls)
    chemistry_class.grade = 11
    chemistry_class.name = "Class 11-A"
    chemistry_subject = await db_session.get(Subject, l.subject)
    chemistry_subject.name, chemistry_subject.grade = "Chemistry", 11
    science_class = await db_session.get(ClassSection, l.cls2)
    science_class.grade, science_class.name = 6, "Class 6-A"
    science_id = uuid.uuid4().hex
    db_session.add(Subject(id=science_id, name="Science", code=science_id, grade=6))
    science_class.subject_ids_json = [science_id]
    await db_session.commit()
    chemistry_teacher, science_teacher = l.headers["teacher"], l.headers["otherteacher"]
    path = "/api/v1/assessments/targets"
    science_targets = (await client.get(path, headers=science_teacher)).json()
    assert l.cls not in {c["id"] for c in science_targets}
    assert l.cls2 in {c["id"] for c in science_targets}
    assert science_targets[0]["subjects"] == [{"id": science_id, "name": "Science"}]
    chemistry_targets = (await client.get(path, headers=chemistry_teacher)).json()
    assert {c["id"] for c in chemistry_targets} == {l.cls}
    assert chemistry_targets[0]["subjects"] == [{"id": l.subject, "name": "Chemistry"}]
    body = {"class_id": l.cls, "subject_id": l.subject, "title": "Chemistry Assignment",
            "date": "2026-11-12", "total_marks": 1, "competency_focus": ["CU"], "questions": [{
                "text": "What is oxygen's symbol?", "type": "mcq", "options": ["O", "H", "N", "C"],
                "correct_answer": "O", "marks": 1, "competency": "CU", "bloom_level": "Remember"}]}
    endpoint = f"/api/v1/classes/{l.cls}/assessments"
    denied = await client.post(endpoint, headers=science_teacher, json=body)
    assert denied.status_code == 404
    assert not (await db_session.scalars(select(Assessment).where(Assessment.class_id == l.cls))).all()
    created = await client.post(endpoint, headers=chemistry_teacher, json=body)
    assert created.status_code == 201, created.text
    assert created.json()["class_id"] == l.cls and created.json()["subject_id"] == l.subject
    assert created.json()["school_id"] == l.school and created.json()["status"] == "scheduled"
    # Principals retain existing school-authorized creation permissions.
    principal_targets = (await client.get(path, headers=l.headers["principal"])).json()
    assert {c["id"] for c in principal_targets} == {l.cls, l.cls2}
