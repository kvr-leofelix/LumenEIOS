"""Phase 3 of answer submission: teacher-facing, read-only submission views.

GET /api/v1/homework/assignments/{assignment_id}/submissions
GET /api/v1/homework/assignments/{assignment_id}/submissions/{student_id}

Submissions are created through the real student endpoints (Phase 2), then read here.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event, text

import backend.app.modules.differentiated_homework.router as homework_router
from backend.app.core.config import settings
from backend.app.core.security import create_access_token
from backend.app.db.session import engine
from backend.app.models.entities import ClassSection, ParentStudentLink, Student, Subject, User
from backend.app.modules.differentiated_homework.models import (
    HomeworkAssignmentRecord,
    HomeworkDraftItemRecord,
    HomeworkDraftRecord,
    StudentAccountLink,
)

OVERVIEW = "/api/v1/homework/assignments/{}/submissions"
DETAIL = OVERVIEW + "/{}"
STUDENT_SUB = "/api/v1/students/me/homework/assignments/{}/submission"
DUE = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
BEFORE_DUE = DUE - timedelta(days=1)
QUESTIONS = (("mcq", ["A", "B", "C"]), ("short", []), ("descriptive", []), ("practical", []))
HIDDEN = ("SECRET", "correct_answer", "marking_rubric", "rubric", "marks", "score", "grade", "feedback",
          "competency", "bloom", "Apply", "source_question_id", "src-", "draft_id", "version", "reviewed",
          "assigned_by", "school_id", "is_ai_generated")
ROW_FIELDS = {"student_id", "student_name", "status", "started_at", "updated_at", "submitted_at", "is_late",
              "answered_count", "question_count"}
OVERVIEW_FIELDS = {"assignment_id", "subject_id", "subject_name", "assignment_status", "assigned_at", "due_at",
                   "question_count", "counts", "students"}
COUNT_FIELDS = {"total_students", "not_started", "in_progress", "submitted", "submitted_late"}
QUESTION_FIELDS = {"position", "text", "type", "options", "answered", "answer_text", "selected_option_index"}


def uid(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def bearer(user_id, role, school_id="school-1"):
    return {"Authorization": f"Bearer {create_access_token(user_id, school_id=school_id, role=role)}"}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def make_user(role, school_id):
    user_id = uid(f"tsv-{role}")
    return User(id=user_id, email=f"{user_id}@test.invalid", name=f"Test {role}", hashed_password="x",
                role=role, school_id=school_id)


def make_student(cls, school_id, name):
    return Student(id=uid("tsv-student"), school_id=school_id, class_id=cls.id, class_name=cls.name, name=name,
                   roll_no=1, lu_score=40, cu_score=70, au_score=60, ct_score=50, overall_score=55)


def make_assignment(student, subject_id, created_by, due_at=DUE):
    items = [
        HomeworkDraftItemRecord(
            position=i, source_question_id=uid("src"), text=f"{student.name} question {i}", type=qtype,
            options_json=list(options), marks=3, competency="LU", competency_rank=1, bloom_level="Apply",
            is_ai_generated=False, correct_answer="SECRET-ANSWER", marking_rubric="SECRET-RUBRIC",
        )
        for i, (qtype, options) in enumerate(QUESTIONS, start=1)
    ]
    draft = HomeworkDraftRecord(
        student_id=student.id, school_id=student.school_id, subject_id=subject_id, created_by=created_by,
        status="assigned", requested_questions=4, include_ai_generated=False, question_count=4, total_marks=12,
        shortfall=0, notes_json=["teacher-only"],
        rationale_json={"targeted_competencies": ["LU"], "weakest": ["LU"],
                        "competency_scores": {"LU": 40, "CU": 70, "AU": 60, "CT": 50},
                        "lowest_score": 40, "highest_score": 70, "score_source": "test", "summary": "SECRET-SUMMARY"},
        reviewed_by=created_by, review_note="SECRET-REVIEW", items=items,
    )
    return HomeworkAssignmentRecord(
        id=uid("tsv-asg"), draft=draft, student_id=student.id, school_id=student.school_id, subject_id=subject_id,
        assigned_by=created_by, assigned_at=BEFORE_DUE - timedelta(days=2), due_at=due_at, status="assigned",
    )


@pytest_asyncio.fixture
async def world(db_session, client, monkeypatch):
    """Four students, five assignments, three submission states (created through the student API)."""
    subj = Subject(id=uid("tsv-subj"), name="Teacher View Maths", code=uid("TSV"), grade=8)
    cls1 = ClassSection(id=uid("tsv-c1"), school_id="school-1", grade=8, section="S", name="TV 1",
                        subject_ids_json=[subj.id])
    cls3 = ClassSection(id=uid("tsv-c3"), school_id="school-3", grade=8, section="T", name="TV 3",
                        subject_ids_json=[subj.id])
    alice, bob, dan = (make_student(cls1, "school-1", n) for n in ("Alice", "Bob", "Dan"))
    cara = make_student(cls3, "school-3", "Cara")
    u_alice, u_bob = make_user("student", "school-1"), make_user("student", "school-1")
    u_teacher2, u_parent = make_user("teacher", "school-1"), make_user("parent", "school-1")

    a_alice = make_assignment(alice, subj.id, "user-teacher-1")  # will be in progress
    a_bob = make_assignment(bob, subj.id, "user-teacher-1")  # will be submitted late
    a_dan = make_assignment(dan, subj.id, "user-teacher-1")  # not started
    a_teacher2 = make_assignment(dan, subj.id, u_teacher2.id)  # another teacher, same school
    a_cara = make_assignment(cara, subj.id, "user-teacher-3")  # another school

    ids = {
        "alice": alice.id, "bob": bob.id, "dan": dan.id, "cara": cara.id,
        "u_alice": u_alice.id, "u_bob": u_bob.id, "u_teacher2": u_teacher2.id, "u_parent": u_parent.id,
        "a_alice": a_alice.id, "a_bob": a_bob.id, "a_dan": a_dan.id, "a_teacher2": a_teacher2.id,
        "a_cara": a_cara.id, "classes": [cls1.id, cls3.id], "subject": subj.id,
    }
    db_session.add_all([
        subj, cls1, cls3, alice, bob, dan, cara, u_alice, u_bob, u_teacher2, u_parent,
        a_alice, a_bob, a_dan, a_teacher2, a_cara,
        StudentAccountLink(user_id=u_alice.id, student_id=alice.id, created_by="user-admin"),
        StudentAccountLink(user_id=u_bob.id, student_id=bob.id, created_by="user-admin"),
        ParentStudentLink(id=uid("tsv-plink"), parent_user_id=u_parent.id, student_id=alice.id),
    ])
    await db_session.commit()

    # Alice: in progress (MCQ index 2 and a text answer). Bob: submitted after the due time.
    monkeypatch.setattr(homework_router, "utc_now", lambda: BEFORE_DUE)
    res = await client.put(STUDENT_SUB.format(a_alice.id), headers=bearer(u_alice.id, "student"),
                           json={"answers": [{"position": 1, "selected_option_index": 2},
                                             {"position": 3, "answer_text": "Alice's explanation"}]})
    assert res.status_code == 201
    await client.put(STUDENT_SUB.format(a_bob.id), headers=bearer(u_bob.id, "student"),
                     json={"answers": [{"position": 2, "answer_text": "Bob's short answer"}]})
    monkeypatch.setattr(homework_router, "utc_now", lambda: DUE + timedelta(hours=2))
    res = await client.post(STUDENT_SUB.format(a_bob.id) + "/submit", headers=bearer(u_bob.id, "student"),
                            json={"expected_version": 1})
    assert res.status_code == 200 and res.json()["is_late"] is True
    monkeypatch.undo()
    yield ids

    await db_session.rollback()
    for student_id in (ids["alice"], ids["bob"], ids["dan"], ids["cara"]):
        p = {"s": student_id}
        for sql in (
            "DELETE FROM homework_submission_answers WHERE submission_id IN "
            "(SELECT id FROM homework_submissions WHERE student_id = :s)",
            "DELETE FROM homework_submissions WHERE student_id = :s",
            "DELETE FROM homework_assignments WHERE student_id = :s",
            "DELETE FROM homework_draft_items WHERE draft_id IN (SELECT id FROM homework_drafts WHERE student_id = :s)",
            "DELETE FROM homework_drafts WHERE student_id = :s",
            "DELETE FROM student_account_links WHERE student_id = :s",
            "DELETE FROM parent_student_links WHERE student_id = :s",
            "DELETE FROM students WHERE id = :s",
        ):
            await db_session.execute(text(sql), p)
    for key in ("u_alice", "u_bob", "u_teacher2", "u_parent"):
        await db_session.execute(text("DELETE FROM audit_events WHERE user_id = :u"), {"u": ids[key]})
        await db_session.execute(text("DELETE FROM student_account_links WHERE user_id = :u"), {"u": ids[key]})
        await db_session.execute(text("DELETE FROM users WHERE id = :u"), {"u": ids[key]})
    for class_id in ids["classes"]:
        await db_session.execute(text("DELETE FROM classes WHERE id = :c"), {"c": class_id})
    await db_session.execute(text("DELETE FROM subjects WHERE id = :j"), {"j": ids["subject"]})
    await db_session.commit()


async def both(client, w, assignment_key, student_key, headers):
    """The overview and the detail for one assignment and student."""
    return (await client.get(OVERVIEW.format(w[assignment_key]), headers=headers),
            await client.get(DETAIL.format(w[assignment_key], w[student_key]), headers=headers))


# --- Authorization --------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_teacher_sees_their_own_assignment(client, world, teacher_token):
    overview, detail = await both(client, world, "a_alice", "alice", auth(teacher_token))
    assert overview.status_code == 200 and detail.status_code == 200
    assert overview.json()["students"][0]["student_name"] == "Alice"


NOT_FOUND = {"detail": "Assignment not found."}
SUBMISSION_KEYS = ('"students"', '"questions"', '"counts"', '"answer_text"', '"status"')


def assert_hidden(res, *names):
    """The generic 404, with no submission data and none of the given names."""
    assert res.status_code == 404 and res.json() == NOT_FOUND, res.text
    for leaked in SUBMISSION_KEYS + names:
        assert leaked not in res.text, leaked


@pytest.mark.asyncio
async def test_teacher_cannot_see_another_teachers_assignment_in_the_same_school(client, world, teacher_token):
    for res in await both(client, world, "a_teacher2", "dan", auth(teacher_token)):
        assert_hidden(res, "Dan")
    # ...and the other teacher can't see this teacher's assignments either.
    for res in await both(client, world, "a_alice", "alice", bearer(world["u_teacher2"], "teacher")):
        assert_hidden(res, "Alice", "explanation")
    ok = await both(client, world, "a_teacher2", "dan", bearer(world["u_teacher2"], "teacher"))
    assert [r.status_code for r in ok] == [200, 200]


@pytest.mark.asyncio
async def test_teachers_cannot_cross_schools(client, world, teacher_token, other_school_teacher_token):
    for res in await both(client, world, "a_cara", "cara", auth(teacher_token)):
        assert_hidden(res, "Cara")
    for res in await both(client, world, "a_alice", "alice", auth(other_school_teacher_token)):
        assert_hidden(res, "Alice", "explanation")


@pytest.mark.asyncio
async def test_principal_follows_school_access(client, world, principal_token):
    for key, student in (("a_alice", "alice"), ("a_teacher2", "dan"), ("a_bob", "bob")):
        assert [r.status_code for r in await both(client, world, key, student, auth(principal_token))] == [200, 200]
    for res in await both(client, world, "a_cara", "cara", auth(principal_token)):
        assert_hidden(res, "Cara")


@pytest.mark.asyncio
async def test_inaccessible_and_missing_assignments_look_identical(client, world, teacher_token, principal_token,
                                                                   other_school_teacher_token):
    """Same status, body and headers whether the assignment is missing or just not the caller's,
    so these views don't reveal that another teacher's or school's assignment exists."""
    def fingerprint(res):
        headers = {k: v for k, v in res.headers.items() if k.lower() not in ("date", "server")}
        return res.status_code, res.content, headers

    cases = [
        (auth(teacher_token), "a_teacher2", "dan"),  # another teacher, same school
        (auth(teacher_token), "a_cara", "cara"),  # another school
        (auth(other_school_teacher_token), "a_alice", "alice"),
        (auth(principal_token), "a_cara", "cara"),
    ]
    for headers, key, student in cases:
        hidden_overview, hidden_detail = await both(client, world, key, student, headers)
        missing_overview = await client.get(OVERVIEW.format(uid("no-such")), headers=headers)
        missing_detail = await client.get(DETAIL.format(uid("no-such"), world[student]), headers=headers)
        assert fingerprint(hidden_overview) == fingerprint(missing_overview)
        assert fingerprint(hidden_detail) == fingerprint(missing_detail)
        for res in (hidden_overview, hidden_detail, missing_overview, missing_detail):
            assert fingerprint(res)[:2] == (404, b'{"detail":"Assignment not found."}')


@pytest.mark.asyncio
async def test_admin_sees_every_school(client, world, admin_token):
    for key, student in (("a_alice", "alice"), ("a_teacher2", "dan"), ("a_cara", "cara")):
        assert [r.status_code for r in await both(client, world, key, student, auth(admin_token))] == [200, 200]


@pytest.mark.asyncio
async def test_students_and_parents_are_refused(client, world, student_token, parent_token):
    for headers in (auth(student_token), auth(parent_token), bearer(world["u_alice"], "student"),
                    bearer(world["u_parent"], "parent")):  # the last two are linked to Alice
        for res in await both(client, world, "a_alice", "alice", headers):
            assert res.status_code == 403 and res.json() == {"detail": "Access denied."}
            assert "explanation" not in res.text and "Alice" not in res.text
        # Role is checked before any lookup: a missing assignment is also just 403.
        assert (await client.get(OVERVIEW.format("no-such-assignment"), headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_demo_mode_cannot_stand_in_for_a_login(client, world):
    assert settings.DEMO_MODE is True  # shared login code would treat "no token" as admin
    for res in await both(client, world, "a_alice", "alice", {}):
        assert res.status_code == 401 and "Alice" not in res.text
    for res in await both(client, world, "a_alice", "alice", {"Authorization": "Bearer not-a-jwt"}):
        assert res.status_code == 401
    previous = settings.DEMO_MODE
    settings.DEMO_MODE = False
    try:
        for res in await both(client, world, "a_alice", "alice", {}):
            assert res.status_code == 401
    finally:
        settings.DEMO_MODE = previous


@pytest.mark.asyncio
async def test_missing_assignment_is_404_for_educators(client, world, teacher_token):
    assert (await client.get(OVERVIEW.format("no-such-assignment"), headers=auth(teacher_token))).status_code == 404
    res = await client.get(DETAIL.format("no-such-assignment", world["alice"]), headers=auth(teacher_token))
    assert res.status_code == 404 and res.json() == {"detail": "Assignment not found."}


@pytest.mark.asyncio
async def test_stale_or_missing_student_records_dont_leak_or_bypass(client, db_session, world, teacher_token,
                                                                     other_school_teacher_token):
    """Teacher access never uses StudentAccountLink. Removing Alice's link changes nothing here;
    deleting her Student record leaves an anonymous roster entry, and access rules still hold."""
    before = (await client.get(OVERVIEW.format(world["a_alice"]), headers=auth(teacher_token))).json()
    await db_session.execute(text("DELETE FROM student_account_links WHERE user_id = :u"), {"u": world["u_alice"]})
    await db_session.commit()
    assert (await client.get(OVERVIEW.format(world["a_alice"]), headers=auth(teacher_token))).json() == before

    await db_session.execute(text("DELETE FROM students WHERE id = :s"), {"s": world["alice"]})
    await db_session.commit()
    overview, detail = await both(client, world, "a_alice", "alice", auth(teacher_token))
    assert overview.status_code == 200 and overview.json()["students"][0]["student_name"] is None
    assert overview.json()["students"][0]["status"] == "in_progress"
    assert detail.status_code == 200 and detail.json()["student_name"] is None
    for res in await both(client, world, "a_alice", "alice", auth(other_school_teacher_token)):
        assert_hidden(res)


# --- Overview and list -------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overview_in_each_state(client, world, teacher_token):
    expected = {
        "a_alice": ("alice", "Alice", "in_progress", {"not_started": 0, "in_progress": 1, "submitted": 0,
                                                       "submitted_late": 0}, None, 2),
        "a_bob": ("bob", "Bob", "submitted", {"not_started": 0, "in_progress": 0, "submitted": 1,
                                               "submitted_late": 1}, True, 1),
        "a_dan": ("dan", "Dan", "not_started", {"not_started": 1, "in_progress": 0, "submitted": 0,
                                                 "submitted_late": 0}, None, 0),
    }
    for key, (student, name, state, counts, late, answered) in expected.items():
        res = await client.get(OVERVIEW.format(world[key]), headers=auth(teacher_token))
        assert res.status_code == 200
        body = res.json()
        assert set(body) == OVERVIEW_FIELDS and set(body["counts"]) == COUNT_FIELDS
        assert body["counts"] == {"total_students": 1, **counts}
        assert body["assignment_id"] == world[key] and body["subject_name"] == "Teacher View Maths"
        assert body["assignment_status"] == "assigned" and body["question_count"] == 4
        assert body["due_at"].startswith("2026-11-20T12:00:00")
        assert len(body["students"]) == 1  # the assignment's student, once
        row = body["students"][0]
        assert set(row) == ROW_FIELDS
        assert (row["student_id"], row["student_name"], row["status"]) == (world[student], name, state)
        assert (row["is_late"], row["answered_count"], row["question_count"]) == (late, answered, 4)


@pytest.mark.asyncio
async def test_not_started_student_is_listed_with_empty_times(client, world, teacher_token):
    row = (await client.get(OVERVIEW.format(world["a_dan"]), headers=auth(teacher_token))).json()["students"][0]
    assert row == {"student_id": world["dan"], "student_name": "Dan", "status": "not_started", "started_at": None,
                   "updated_at": None, "submitted_at": None, "is_late": None, "answered_count": 0,
                   "question_count": 4}


@pytest.mark.asyncio
async def test_in_progress_past_the_due_time_is_not_labelled_late(client, db_session, world, teacher_token):
    """Alice's due time has passed in real time terms for this check; she hasn't submitted."""
    await db_session.execute(text("UPDATE homework_assignments SET due_at = '2020-01-01 00:00:00' WHERE id = :a"),
                             {"a": world["a_alice"]})
    await db_session.commit()
    body = (await client.get(OVERVIEW.format(world["a_alice"]), headers=auth(teacher_token))).json()
    assert body["students"][0]["is_late"] is None and body["counts"]["submitted_late"] == 0


@pytest.mark.asyncio
async def test_no_data_crosses_assignments(client, world, teacher_token):
    """Dan's assignments don't show Alice's or Bob's submissions, and vice versa."""
    dan = await client.get(OVERVIEW.format(world["a_dan"]), headers=auth(teacher_token))
    for other in ("Alice", "Bob", world["alice"], world["bob"], "explanation", "short answer"):
        assert other not in dan.text
    alice = await client.get(DETAIL.format(world["a_alice"], world["alice"]), headers=auth(teacher_token))
    assert "Bob" not in alice.text and world["bob"] not in alice.text and "Dan" not in alice.text


@pytest.mark.asyncio
async def test_queries_dont_grow_with_answers(client, world, teacher_token):
    """A fixed number of statements per request, whatever the number of answers (no N+1)."""
    def count_for(url):
        statements = []

        def record(conn, cursor, statement, params, context, executemany):
            statements.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", record)
        return statements, record

    results = {}
    for label, url in (("none", DETAIL.format(world["a_dan"], world["dan"])),
                       ("two answers", DETAIL.format(world["a_alice"], world["alice"])),
                       ("submitted", DETAIL.format(world["a_bob"], world["bob"])),
                       ("overview", OVERVIEW.format(world["a_alice"]))):
        statements, record = count_for(url)
        try:
            assert (await client.get(url, headers=auth(teacher_token))).status_code == 200
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", record)
        results[label] = len(statements)
    assert results["two answers"] == results["submitted"] and results["none"] <= results["two answers"]
    assert max(results.values()) <= 12, results


# --- Detail ----------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_progress_detail_maps_answers_to_questions(client, world, teacher_token):
    res = await client.get(DETAIL.format(world["a_alice"], world["alice"]), headers=auth(teacher_token))
    body = res.json()
    assert (body["status"], body["is_late"], body["answered_count"], body["question_count"]) == (
        "in_progress", None, 2, 4)
    assert body["started_at"].startswith("2026-11-19T12:00:00") and body["submitted_at"] is None
    assert [q["position"] for q in body["questions"]] == [1, 2, 3, 4]
    assert all(set(q) == QUESTION_FIELDS for q in body["questions"])
    q1, q2, q3, q4 = body["questions"]
    assert q1 == {"position": 1, "text": "Alice question 1", "type": "mcq", "options": ["A", "B", "C"],
                  "answered": True, "answer_text": None, "selected_option_index": 2}
    assert (q2["answered"], q2["answer_text"], q2["selected_option_index"]) == (False, None, None)
    assert (q3["answered"], q3["answer_text"], q3["type"]) == (True, "Alice's explanation", "descriptive")
    assert q4["answered"] is False and q4["type"] == "practical"


@pytest.mark.asyncio
async def test_submitted_detail(client, world, teacher_token):
    body = (await client.get(DETAIL.format(world["a_bob"], world["bob"]), headers=auth(teacher_token))).json()
    assert (body["status"], body["is_late"], body["answered_count"]) == ("submitted", True, 1)
    assert body["submitted_at"].startswith("2026-11-20T14:00:00")
    assert body["questions"][1]["answer_text"] == "Bob's short answer"


@pytest.mark.asyncio
async def test_not_started_detail_is_explicit(client, world, teacher_token):
    res = await client.get(DETAIL.format(world["a_dan"], world["dan"]), headers=auth(teacher_token))
    assert res.status_code == 200
    body = res.json()
    assert (body["status"], body["started_at"], body["is_late"], body["answered_count"]) == ("not_started", None,
                                                                                              None, 0)
    assert len(body["questions"]) == 4 and not any(q["answered"] for q in body["questions"])


@pytest.mark.asyncio
async def test_student_id_must_belong_to_the_assignment(client, world, teacher_token, admin_token):
    for headers in (auth(teacher_token), auth(admin_token)):
        for student in ("bob", "dan", "cara"):  # other students, same school or not
            res = await client.get(DETAIL.format(world["a_alice"], world[student]), headers=headers)
            assert res.status_code == 404 and res.json() == {"detail": "Student not found on this assignment."}
            assert "Alice" not in res.text
        res = await client.get(DETAIL.format(world["a_alice"], "no-such-student"), headers=headers)
        assert res.status_code == 404
    # Alice's ID with another assignment (Bob's): no access to Alice's data that way.
    res = await client.get(DETAIL.format(world["a_bob"], world["alice"]), headers=auth(teacher_token))
    assert res.status_code == 404 and "explanation" not in res.text


@pytest.mark.asyncio
async def test_inconsistent_stored_data_is_a_500_without_details(client, db_session, world, teacher_token):
    foreign_item = (await db_session.execute(text(
        "SELECT i.id FROM homework_draft_items i JOIN homework_assignments a ON a.draft_id = i.draft_id "
        "WHERE a.id = :a AND i.position = 1"), {"a": world["a_dan"]})).scalar()
    await db_session.execute(text(  # one of Alice's two answers now points at Dan's question
        "UPDATE homework_submission_answers SET draft_item_id = :i WHERE id = (SELECT id FROM "
        "homework_submission_answers WHERE submission_id = (SELECT id FROM homework_submissions "
        "WHERE assignment_id = :a) LIMIT 1)"), {"i": foreign_item, "a": world["a_alice"]})
    await db_session.commit()
    for res in await both(client, world, "a_alice", "alice", auth(teacher_token)):
        assert res.status_code == 500
        assert res.json() == {"detail": "This submission can't be processed because of a server-side data problem."}
        assert foreign_item not in res.text


# --- Read-only guarantee ------------------------------------------------------------------------------------


async def snapshot(db_session, w):
    async def rows(sql):
        return [tuple(r) for r in (await db_session.execute(text(sql))).all()]

    await db_session.rollback()  # start a fresh read
    return {
        "submissions": await rows("SELECT id, assignment_id, status, version, updated_at, submitted_at, is_late "
                                  "FROM homework_submissions ORDER BY id"),
        "answers": await rows("SELECT id, submission_id, draft_item_id, answer_text, selected_option_index, "
                              "updated_at FROM homework_submission_answers ORDER BY id"),
        "assignments": await rows("SELECT id, status, due_at FROM homework_assignments ORDER BY id"),
        "audit": await rows("SELECT COUNT(*) FROM audit_events"),
    }


@pytest.mark.asyncio
async def test_views_change_nothing(client, db_session, world, teacher_token, principal_token, admin_token):
    before = await snapshot(db_session, world)
    for headers in (auth(teacher_token), auth(principal_token), auth(admin_token)):
        for key, student in (("a_alice", "alice"), ("a_bob", "bob"), ("a_dan", "dan")):
            await both(client, world, key, student, headers)
        await client.get(DETAIL.format(world["a_alice"], world["bob"]), headers=headers)  # a refused lookup
    after = await snapshot(db_session, world)
    assert after == before  # no submission created for Dan, no version, answer, status or audit change


@pytest.mark.asyncio
async def test_only_get_is_allowed(client, world, teacher_token):
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        for url in (OVERVIEW.format(world["a_alice"]), DETAIL.format(world["a_alice"], world["alice"])):
            assert (await client.request(method, url, headers=auth(teacher_token))).status_code == 405


# --- Information leakage -----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_hidden_data_in_any_response(client, world, teacher_token, admin_token):
    for headers in (auth(teacher_token), auth(admin_token)):
        for key, student in (("a_alice", "alice"), ("a_bob", "bob"), ("a_dan", "dan")):
            for res in await both(client, world, key, student, headers):
                for hidden in HIDDEN + ("teacher-only", "user-teacher-1"):
                    assert hidden not in res.text, (hidden, res.text)


@pytest.mark.asyncio
async def test_openapi_schemas(client):
    spec = (await client.get("/api/v1/openapi.json")).json()
    paths, schemas = spec["paths"], spec["components"]["schemas"]
    overview_path = "/api/v1/homework/assignments/{assignment_id}/submissions"
    assert set(paths[overview_path]) == {"get"} and set(paths[overview_path + "/{student_id}"]) == {"get"}
    assert set(schemas["TeacherAssignmentSubmissionsOut"]["properties"]) == OVERVIEW_FIELDS
    assert set(schemas["TeacherSubmissionCountsOut"]["properties"]) == COUNT_FIELDS
    assert set(schemas["TeacherStudentSubmissionOut"]["properties"]) == ROW_FIELDS
    assert set(schemas["TeacherSubmissionDetailOut"]["properties"]) == ROW_FIELDS | {"assignment_id", "questions"}
    assert set(schemas["TeacherQuestionAnswerOut"]["properties"]) == QUESTION_FIELDS
    fields = " ".join(str(schemas[n]["properties"]) for n in schemas if n.startswith("Teacher") and "Submission" in n
                      or n == "TeacherQuestionAnswerOut")
    for hidden in ("correct_answer", "marking_rubric", "marks", "score", "grade", "feedback", "competency",
                   "bloom", "source_question_id", "version", "school_id"):
        assert hidden not in fields
    # The student-facing schema is unchanged by this phase.
    assert set(schemas["HomeworkSubmissionOut"]["properties"]) == {
        "id", "assignment_id", "status", "version", "is_late", "started_at", "updated_at", "submitted_at",
        "answered_count", "question_count", "answers"}
