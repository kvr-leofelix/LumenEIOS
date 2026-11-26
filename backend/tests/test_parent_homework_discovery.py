"""Parent discovery: a parent lists linked children and their assignments (read-only).

  GET /api/v1/parents/me/students
  GET /api/v1/parents/me/students/{student_id}/homework/assignments

Reuses the synthetic `world` fixture from test_homework_evaluations: the parent is linked to
Alice only; Alice has submitted, Bob is in progress, Dan hasn't started.
"""
import pytest

from backend.tests.test_homework_evaluations import (  # noqa: F401 (fixture import)
    HIDDEN,
    RELEASE,
    as_parent,
    auth,
    bearer,
    marked_and_finalized,
    transition,
    world,
)

CHILDREN = "/api/v1/parents/me/students"
CHILD_ASSIGNMENTS = CHILDREN + "/{}/homework/assignments"


@pytest.mark.asyncio
async def test_parent_lists_only_linked_children(client, world):
    res = await client.get(CHILDREN, headers=as_parent(world))
    assert res.status_code == 200
    assert [c["id"] for c in res.json()] == [world["alice"]]
    assert set(res.json()[0]) == {"id", "name", "class_name", "school_id"}


@pytest.mark.asyncio
async def test_child_assignments_show_progress_and_release_without_content(client, world, teacher_token):
    res = await client.get(CHILD_ASSIGNMENTS.format(world["alice"]), headers=as_parent(world))
    assert res.status_code == 200
    rows = res.json()
    assert [r["id"] for r in rows] == [world["a_alice"]]
    assert rows[0]["submission_status"] == "submitted" and rows[0]["result_released"] is False
    for hidden in HIDDEN + ("items", "awarded", "feedback", "answer"):
        assert hidden not in res.text, hidden

    await marked_and_finalized(client, world, auth(teacher_token))
    assert (await transition(client, RELEASE, world, "a_alice", 3, auth(teacher_token))).status_code == 200
    rows = (await client.get(CHILD_ASSIGNMENTS.format(world["alice"]), headers=as_parent(world))).json()
    assert rows[0]["result_released"] is True


@pytest.mark.asyncio
async def test_unlinked_or_missing_child_gives_the_same_404(client, world):
    unlinked = await client.get(CHILD_ASSIGNMENTS.format(world["bob"]), headers=as_parent(world))
    missing = await client.get(CHILD_ASSIGNMENTS.format("no-such-student"), headers=as_parent(world))
    assert unlinked.status_code == missing.status_code == 404
    assert unlinked.json() == missing.json()


@pytest.mark.asyncio
async def test_non_parents_are_refused(client, world, teacher_token):
    for headers in (auth(teacher_token), bearer(world["u_alice"], "student")):
        assert (await client.get(CHILDREN, headers=headers)).status_code == 403
        assert (await client.get(CHILD_ASSIGNMENTS.format(world["alice"]), headers=headers)).status_code == 403
    assert (await client.get(CHILDREN)).status_code == 401


@pytest.mark.asyncio
async def test_students_own_list_reports_the_same_progress_and_release(client, world, teacher_token):
    """The student's list must say a result is released once the parent's does (it used to stay 'submitted')."""
    own = "/api/v1/students/me/homework/assignments"
    as_alice = bearer(world["u_alice"], "student")
    rows = (await client.get(own, headers=as_alice)).json()
    assert [(r["id"], r["submission_status"], r["result_released"]) for r in rows] == [(world["a_alice"], "submitted", False)]
    for hidden in HIDDEN + ("items", "awarded", "feedback", "answer"):
        assert hidden not in str(rows), hidden

    await marked_and_finalized(client, world, auth(teacher_token))
    assert (await transition(client, RELEASE, world, "a_alice", 3, auth(teacher_token))).status_code == 200
    student_rows = (await client.get(own, headers=as_alice)).json()
    parent_rows = (await client.get(CHILD_ASSIGNMENTS.format(world["alice"]), headers=as_parent(world))).json()
    assert student_rows == parent_rows
    assert student_rows[0]["result_released"] is True


@pytest.mark.asyncio
async def test_students_and_parents_only_see_their_own_class(client, db_session, world, teacher_token):
    """Class details and class-average analytics: own (or linked child's) class only, any other class is 'not found'."""
    from backend.app.models.entities import ClassSection
    from backend.tests.test_homework_evaluations import uid
    other = ClassSection(id=uid("hev-other"), school_id="school-1", grade=8, section="Z", name="GR other",
                         student_count=0, subject_ids_json=[])
    db_session.add(other)
    await db_session.commit()
    own = world["classes"][0]
    try:
        for headers in (bearer(world["u_alice"], "student"), as_parent(world)):
            for path in ("/api/v1/classes/{}", "/api/v1/classes/{}/competency-analytics"):
                assert (await client.get(path.format(own), headers=headers)).status_code == 200
                hidden = await client.get(path.format(other.id), headers=headers)
                missing = await client.get(path.format("no-such-class"), headers=headers)
                assert hidden.status_code == missing.status_code == 404
        # staff of the school still see every class
        assert (await client.get(f"/api/v1/classes/{other.id}", headers=auth(teacher_token))).status_code == 200
    finally:
        await db_session.delete(other)
        await db_session.commit()
