"""Regression coverage for the educator bank and inherited remediation routes."""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from backend.app.core.config import settings
from backend.app.core.security import create_access_token
from backend.app.models.entities import (
    AssessmentSubmission, AuditEvent, ClassSection, Document, HomeworkRemediation, ParentStudentLink,
    QuestionBankItem, SchoolMembership, Student, StudentCompetencySnapshot, User,
)
from backend.app.modules.differentiated_homework.models import StudentAccountLink

pytestmark = pytest.mark.asyncio
QB = "/api/v1/assessments/question-bank"


def uid():
    return "security-" + uuid.uuid4().hex


def auth(user, school=None):
    headers = {"Authorization": "Bearer " + create_access_token(user.id, role=user.role, school_id=user.school_id)}
    if school:
        headers["X-School-Id"] = school
    return headers


@pytest_asyncio.fixture
async def world(db_session):
    users = {role: User(id=uid(), email=uid()+"@test.invalid", name=role, role=role,
                        school_id="school-1", hashed_password="unused")
             for role in ["admin", "principal", "teacher", "student", "parent", "unknown"]}
    users["unlinked"] = User(id=uid(), email=uid()+"@test.invalid", name="unlinked", role="student",
                             school_id="school-1", hashed_password="unused")
    classes = [ClassSection(id=uid(), school_id=school, grade=8, section="S", name="Security Class")
               for school in ["school-1", "school-3"]]
    students = [Student(id=uid(), school_id=c.school_id, class_id=c.id, class_name=c.name,
                        name="Private Student", roll_no=1, lu_score=41, cu_score=62, au_score=70,
                        ct_score=80, overall_score=63) for c in classes]
    same_id = Student(id=users["unlinked"].id, school_id="school-1", class_id=classes[0].id,
                      class_name="Security Class", name="Same ID", roll_no=2)
    homeworks = [HomeworkRemediation(id=uid(), student_id=s.id, student_name=s.name, class_id=s.class_id,
                 subject_id="sub-math", title="Private task", competency_target="LU", description="Task",
                 due_date="2026-12-01", status="assigned") for s in students]
    subject = uid()
    questions = [QuestionBankItem(id=uid(), school_id=c.school_id, subject_id=subject, text="Question " + c.school_id,
                 type="mcq", options_json=["a", "b"], correct_answer="SECRET-KEY-"+c.school_id,
                 marking_rubric="SECRET-RUBRIC-"+c.school_id, marks=2, competency="LU") for c in classes]
    links = [StudentAccountLink(user_id=users["student"].id, student_id=students[0].id,
                                created_by=users["admin"].id),
             ParentStudentLink(id=uid(), parent_user_id=users["parent"].id, student_id=students[0].id)]
    db_session.add_all([*users.values(), *classes, *students, same_id, *homeworks, *questions, *links])
    await db_session.commit()
    cleanup = [(type(row), row.id) for row in [*links, *homeworks, *questions, *students, same_id, *classes]]
    user_ids = [user.id for user in users.values()]
    yield dict(users=users, classes=classes, students=students, same_id=same_id,
               homeworks=homeworks, questions=questions, subject=subject, links=links)
    await db_session.rollback()
    for model, row_id in cleanup:
        await db_session.execute(delete(model).where(model.id == row_id))
    await db_session.execute(delete(AuditEvent).where(AuditEvent.user_id.in_(user_ids)))
    await db_session.execute(delete(User).where(User.id.in_(user_ids)))
    await db_session.commit()


@pytest.mark.parametrize("role,code", [(None,401),("student",403),("parent",403),("unknown",403),
                                       ("teacher",200),("principal",200),("admin",200)])
async def test_question_bank_role_and_key_boundary(client, world, monkeypatch, role, code):
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    headers = auth(world["users"][role]) if role else {}
    response = await client.get(QB, params={"subject_id":world["subject"]}, headers=headers)
    assert response.status_code == code, response.text
    if code == 200:
        assert [q["id"] for q in response.json()] == [world["questions"][0].id]
        assert response.json()[0]["correct_answer"] == "SECRET-KEY-school-1"
        assert response.json()[0]["marking_rubric"] == "SECRET-RUBRIC-school-1"
    else:
        for secret in ["correct_answer", "marking_rubric", "SECRET", "source_document"]:
            assert secret not in response.text
    assert "SECRET-KEY-school-3" not in response.text


@pytest.mark.parametrize("role", ["teacher","principal","admin"])
async def test_bank_school_context(client, world, role):
    response = await client.get(QB, params={"subject_id":world["subject"]},
                                headers=auth(world["users"][role], "school-3"))
    assert response.status_code == (200 if role == "admin" else 403)
    if role == "admin":
        assert [q["id"] for q in response.json()] == [world["questions"][1].id]
    else:
        assert "SECRET" not in response.text


@pytest.mark.parametrize("active", [True, False])
async def test_bank_membership(client, world, db_session, active):
    membership = SchoolMembership(id=uid(), user_id=world["users"]["teacher"].id,
                                  school_id="school-3", role="teacher", is_active=active)
    db_session.add(membership)
    await db_session.commit()
    try:
        response = await client.get(QB, params={"subject_id":world["subject"]},
                                    headers=auth(world["users"]["teacher"], "school-3"))
        assert response.status_code == (200 if active else 403)
    finally:
        await db_session.delete(membership)
        await db_session.commit()


@pytest.mark.parametrize("role", [None,"student","parent","teacher","principal","admin"])
async def test_empty_bank_does_not_bypass_roles(client, world, role):
    response = await client.get(QB, params={"subject_id":uid()},
                                headers=auth(world["users"][role]) if role else {})
    assert response.status_code == (401 if role is None else 403 if role in {"student","parent"} else 200)
    assert "correct_answer" not in response.text
    assert "marking_rubric" not in response.text


@pytest.mark.parametrize("method,suffix,body", [("put","",{}),("post","/regenerate",{"subject_id":"sub-math"}),("delete","",None)])
@pytest.mark.parametrize("role", [None,"student","parent","teacher","principal"])
async def test_bank_mutations_cannot_bypass_key_scope(client, world, role, method, suffix, body):
    response = await client.request(method, "/api/v1/assessments/questions/" + world["questions"][1].id + suffix,
                                    json=body, headers=auth(world["users"][role]) if role else {})
    expected = 401 if role is None else 403 if role in {"student","parent"} else 404
    assert response.status_code == expected, response.text
    assert "SECRET" not in response.text


@pytest.mark.parametrize("role", [None,"student","parent","teacher","principal","admin"])
async def test_legacy_student_reads(client, world, role):
    headers = auth(world["users"][role]) if role else {}
    for suffix in ["homework","remediation/recommendation"]:
        own = await client.get(f"/api/v1/students/{world['students'][0].id}/{suffix}", headers=headers)
        assert own.status_code == (401 if role is None else 200), own.text
        other = await client.get(f"/api/v1/students/{world['students'][1].id}/{suffix}", headers=headers)
        assert other.status_code == (401 if role is None else 200 if role == "admin" else 404)
        missing = await client.get(f"/api/v1/students/missing/{suffix}", headers=headers)
        assert missing.status_code == (401 if role is None else 404)


async def test_no_same_id_or_stale_student_identity(client, world, db_session):
    for student_id in [world["same_id"].id, world["students"][0].id]:
        response = await client.get(f"/api/v1/students/{student_id}/homework", headers=auth(world["users"]["unlinked"]))
        assert response.status_code == 404
    world["users"]["student"].school_id = "school-3"
    await db_session.commit()
    response = await client.get(f"/api/v1/students/{world['students'][0].id}/homework",
                                headers=auth(world["users"]["student"]))
    assert response.status_code == 404


@pytest.mark.parametrize("role", [None,"student","parent","teacher","principal","admin"])
async def test_class_roster_is_educator_scoped(client, world, role):
    headers = auth(world["users"][role]) if role else {}
    for index, c in enumerate(world["classes"]):
        response = await client.get(f"/api/v1/classes/{c.id}/homework", headers=headers)
        expected = 401 if role is None else 403 if role in {"student","parent"} else 404 if index and role != "admin" else 200
        assert response.status_code == expected


def create_body(world):
    return dict(student_id=world["students"][0].id, class_id=world["classes"][0].id,
                subject_id="sub-math", title="Task", competency_target="LU", description="Task", due_date="2026-12-01")


@pytest.mark.parametrize("role", [None,"student","parent","teacher","principal","admin"])
async def test_legacy_creation_permissions(client, world, db_session, role):
    response = await client.post(f"/api/v1/classes/{world['classes'][0].id}/homework", json=create_body(world),
                                 headers=auth(world["users"][role]) if role else {})
    assert response.status_code == (401 if role is None else 403 if role in {"student","parent"} else 201)
    if response.status_code == 201:
        created = await db_session.get(HomeworkRemediation, response.json()["id"])
        assert created.score is None
        await db_session.delete(created)
        await db_session.commit()


async def test_legacy_creation_rejects_class_and_school_mismatch(client, world):
    body = create_body(world)
    path = f"/api/v1/classes/{world['classes'][0].id}/homework"
    for change, code in [({"class_id":"wrong"},422), ({"student_id":world["students"][1].id},404),
                         ({"student_id":"missing"},404)]:
        response = await client.post(path, json={**body, **change}, headers=auth(world["users"]["teacher"]))
        assert response.status_code == code
    body["student_id"] = world["students"][1].id
    response = await client.post(path, json=body, headers=auth(world["users"]["admin"]))
    assert response.status_code == 422


@pytest.mark.parametrize("role", [None,"student","parent","teacher","principal","admin"])
async def test_legacy_submit_only_linked_owner_no_grading(client, world, db_session, role):
    student = world["students"][0]
    fields = ["lu_score", "cu_score", "au_score", "ct_score", "overall_score", "baseline_lu",
              "baseline_cu", "baseline_au", "baseline_ct", "baseline_overall", "needs_support"]
    before = [getattr(student, f) for f in fields]
    models = [AssessmentSubmission,StudentCompetencySnapshot]
    counts = [await db_session.scalar(select(func.count()).select_from(m)) for m in models]
    headers = auth(world["users"][role]) if role else {}
    own = "/api/v1/homework/"+world["homeworks"][0].id+"/submissions"
    response = await client.post(own, headers=headers)
    assert response.status_code == (401 if role is None else 200 if role == "student" else 403)
    if role == "student":
        assert response.json()["score"] is None
        assert (await client.post(own, headers=headers)).status_code == 200
        other = await client.post("/api/v1/homework/"+world["homeworks"][1].id+"/submissions", headers=headers)
        assert other.status_code == 404
    await db_session.refresh(student)
    assert before == [getattr(student, f) for f in fields]
    assert counts == [await db_session.scalar(select(func.count()).select_from(m)) for m in models]
    await db_session.refresh(world["homeworks"][0])
    assert world["homeworks"][0].status == ("submitted" if role == "student" else "assigned")
    assert world["homeworks"][0].score is None


async def test_repeat_submit_preserves_review(client, world, db_session):
    hw = world["homeworks"][0]
    hw.status, hw.score = "reviewed", 7
    await db_session.commit()
    response = await client.post("/api/v1/homework/"+hw.id+"/submissions", headers=auth(world["users"]["student"]))
    assert response.status_code == 200
    await db_session.refresh(hw)
    assert (hw.status, hw.score) == ("reviewed", 7)


@pytest.mark.parametrize("role", ["student", "parent"])
async def test_other_student_in_same_school_is_private(client, world, role):
    for suffix in ["homework", "remediation/recommendation"]:
        response = await client.get(f"/api/v1/students/{world['same_id'].id}/{suffix}",
                                    headers=auth(world["users"][role]))
        assert response.status_code == 404


async def test_revoked_parent_link_and_inconsistent_homework(client, world, db_session):
    parent_link = world["links"][1]
    await db_session.execute(delete(ParentStudentLink).where(ParentStudentLink.id == parent_link.id))
    hw = world["homeworks"][0]
    hw.class_id = world["classes"][1].id
    await db_session.commit()
    path = f"/api/v1/students/{world['students'][0].id}/homework"
    assert (await client.get(path, headers=auth(world["users"]["parent"]))).status_code == 404
    assert (await client.get(path, headers=auth(world["users"]["student"]))).json() == []
    assert (await client.post("/api/v1/homework/"+hw.id+"/submissions",
                              headers=auth(world["users"]["student"]))).status_code == 404
    listing = await client.get(f"/api/v1/classes/{world['classes'][1].id}/homework",
                               headers=auth(world["users"]["admin"]))
    assert len(listing.json()) == 1  # only the correctly mapped second student
    assert listing.json()[0]["id"] == world["homeworks"][1].id


@pytest.mark.parametrize("role", [None, "student", "parent", "teacher", "principal", "admin"])
async def test_generation_source_access(client, world, db_session, role):
    doc_id = uid()
    doc = Document(id=doc_id, school_id="school-3", uploader_id="unused", file_name="private.txt",
                   file_size=1, mime_type="text/plain", storage_path="unused", extracted_text="SECRET-DOC")
    db_session.add(doc)
    await db_session.commit()
    try:
        response = await client.post("/api/v1/assessments/generate-questions",
            json={"subject_id":world["subject"], "source_document_ids":[doc_id]},
            headers=auth(world["users"][role]) if role else {})
        expected = 401 if role is None else 403 if role in {"student", "parent"} else 404
        assert response.status_code == expected
        assert "SECRET-DOC" not in response.text
    finally:
        await db_session.execute(delete(Document).where(Document.id == doc_id))
        await db_session.commit()


async def test_generation_uses_admin_selected_school(client, world, db_session):
    response = await client.post("/api/v1/assessments/generate-questions",
        json={"subject_id":world["subject"], "mcq_count":1, "theory_count":0, "save_to_bank":True},
        headers=auth(world["users"]["admin"], "school-3"))
    assert response.status_code == 200
    question_id = response.json()["questions"][0]["id"]
    try:
        assert (await db_session.get(QuestionBankItem, question_id)).school_id == "school-3"
    finally:
        await db_session.execute(delete(QuestionBankItem).where(QuestionBankItem.id == question_id))
        await db_session.commit()


async def test_invalid_token_never_gets_demo_keys(client):
    response = await client.get(QB, headers={"Authorization":"Bearer invalid"})
    assert response.status_code == 401
    assert "correct_answer" not in response.text
    assert "marking_rubric" not in response.text
