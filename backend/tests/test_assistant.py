import json

import pytest

from backend.app.api.v1 import assistant

URL = "/api/v1/assistant/chat"


def test_parse_model_answer_accepts_object_or_plain_text():
    parsed = assistant.parse_model_answer('Sure.\n{"answer":"Open Curriculum","page":"Curriculum"}')
    assert parsed.answer == "Open Curriculum"
    assert parsed.page == "Curriculum"

    # Qwen sometimes returns a bare page list instead of the required object.
    fallback = assistant.parse_model_answer(
        '["Dashboard", "My classes", "Assessment studio"]'
    )
    assert fallback.page is None
    assert "Dashboard" in fallback.answer


@pytest.mark.asyncio
async def test_assistant_scopes_parent_records_and_navigation(client, parent_token, monkeypatch):
    captured = {}

    def answer(messages, max_new_tokens):
        captured["messages"] = messages
        return '{"answer":"Progress overview","page":"Reports"}'

    monkeypatch.setattr(assistant.qwen_model, "generate", answer)
    response = await client.request(
        "POST", URL, json={"message": "How is my child doing?"},
        headers={"Authorization": f"Bearer {parent_token}"},
    )
    assert response.status_code == 200
    assert response.json()["links"] == []
    prompt = captured["messages"][0]["content"][0]["text"]
    marker = "Authorized data: "
    payload = json.loads(prompt[prompt.index(marker) + len(marker):].split("\n", 1)[0])
    assert payload["pages"] == ["Child progress", "Unified progress", "Homework results", "Calendar"]
    assert set(payload["records"]["calendar"]) == {"today", "highlights", "upcoming"}  # role-scoped calendar items
    assert payload["records"]["student_count"] == 2
    assert payload["records"]["classes"] == []
    # The assistant can read the same role-scoped calendar as the Calendar page (read-only).
    assert "today" in payload["records"]["calendar"]
    assert isinstance(payload["records"]["calendar"]["upcoming"], list)
    assert "next_7_days" in payload["records"]["calendar"]["highlights"]
    assert any("Calendar:" in step for step in payload["how_to"])


@pytest.mark.asyncio
async def test_assistant_denies_unauthenticated_requests_and_unassigned_schools(client, teacher_token):
    assert (await client.post(URL, json={"message": "Show scores"})).status_code == 401
    assert (await client.post(URL, json={"message": "Show scores"}, headers={
        "Authorization": f"Bearer {teacher_token}", "X-School-Id": "unassigned-school",
    })).status_code == 404  # another school is reported as not found


@pytest.mark.asyncio
async def test_teacher_context_excludes_other_teachers_classes(db_session):
    from sqlalchemy import select
    from backend.app.models.entities import TeacherAssignment, User

    # Teacher 1 has an explicit Mathematics allocation in class 8-B, in addition to
    # being the class teacher for 8-A and 9-B. Set it up here so this test is order independent.
    allocation = await db_session.scalar(select(TeacherAssignment.id).where(
        TeacherAssignment.teacher_id == "user-teacher-1",
        TeacherAssignment.class_id == "class-8b",
        TeacherAssignment.subject_id == "sub-math",
    ))
    if allocation is None:
        db_session.add(TeacherAssignment(
            teacher_id="user-teacher-1", school_id="school-1", class_id="class-8b", subject_id="sub-math",
        ))
        await db_session.commit()

    teacher = await db_session.get(User, "user-teacher-1")
    context = await assistant.assistant_context(db_session, teacher, "school-1")
    assert context["classes"]
    other_teacher = await db_session.get(User, "user-teacher-2")
    other = await assistant.assistant_context(db_session, other_teacher, "school-1")
    assert other["classes"]
    # Class 8-B is deliberately shared: teacher 1 has an explicit Mathematics allocation there.
    # Each teacher must still exclude the other teacher's unallocated class sections.
    assert {item["name"] for item in context["classes"]} == {"Class 8-A", "Class 8-B", "Class 9-B"}
    assert {item["name"] for item in other["classes"]} == {"Class 7-A", "Class 8-B"}


@pytest.mark.asyncio
async def test_student_and_admin_receive_scoped_context(db_session):
    from backend.app.models.entities import User
    from backend.app.modules.differentiated_homework.student_access import resolve_linked_student

    user = await db_session.get(User, "user-student-1")
    student = await resolve_linked_student(db_session, user)
    assert student is not None
    context = await assistant.assistant_context(db_session, user, "unassigned-school")
    assert [record["name"] for record in context["students"]] == [student.name]
    assert context["classes"] == []

    admin = await db_session.get(User, "user-admin")
    context = await assistant.assistant_context(db_session, admin, None)
    assert context["schools"]
    assert all(set(school) == {"name", "student_count", "average_overall"} for school in context["schools"])


@pytest.mark.asyncio
async def test_calendar_questions_are_answered_from_the_calendar_without_the_model(client, parent_token, monkeypatch):
    def model_must_not_run(messages, max_new_tokens):
        raise AssertionError("a calendar question must not reach the model")
    monkeypatch.setattr(assistant.qwen_model, "generate", model_must_not_run)
    response = await client.request("POST", URL, json={"message": "When is the next holiday?"},
                                    headers={"Authorization": f"Bearer {parent_token}"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["links"] == [{"label": "Calendar", "path": "/calendar"}]
    assert "holiday" in body["answer"].lower()
