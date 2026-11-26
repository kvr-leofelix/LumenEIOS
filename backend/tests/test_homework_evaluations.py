"""Manual grading of submitted homework: teacher evaluation endpoints and the student result.

Teacher (bearer token required; same access as the Phase 3 views):
  GET   /api/v1/homework/assignments/{id}/evaluations
  POST  /api/v1/homework/assignments/{id}/evaluation            (start; idempotent)
  GET   /api/v1/homework/assignments/{id}/evaluation
  PATCH /api/v1/homework/assignments/{id}/evaluation/items
  POST  /api/v1/homework/assignments/{id}/evaluation/finalize
  POST  /api/v1/homework/assignments/{id}/evaluation/release
Student:
  GET   /api/v1/students/me/homework/assignments/{id}/evaluation (released only)
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import backend.app.modules.differentiated_homework.router as homework_router
from backend.app.core.config import settings
from backend.app.core.security import create_access_token
from backend.app.models.entities import ClassSection, ParentStudentLink, Student, Subject, User
from backend.app.modules.differentiated_homework.models import (
    HomeworkAssignmentRecord,
    HomeworkDraftItemRecord,
    HomeworkDraftRecord,
    StudentAccountLink,
)

BASE = "/api/v1/homework/assignments/{}"
QUEUE = BASE + "/evaluations"
EVAL = BASE + "/evaluation"
ITEMS = EVAL + "/items"
FINALIZE = EVAL + "/finalize"
RELEASE = EVAL + "/release"
RESULT = "/api/v1/students/me/homework/assignments/{}/evaluation"
STUDENT_SUB = "/api/v1/students/me/homework/assignments/{}/submission"
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
QUESTIONS = (("mcq", ["A", "B", "C"]), ("short", []), ("descriptive", []), ("practical", []))  # 3 marks each
NOT_FOUND = {"detail": "Assignment not found."}
NO_EVALUATION = {"detail": "Evaluation not found."}
HIDDEN = ("SECRET", "correct_answer", "marking_rubric", "rubric", "competency", "bloom", "Apply", "src-",
          "source_question_id", "draft_item_id", "draft_id", "school_id", "is_ai_generated", "teacher-only")


def uid(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def bearer(user_id, role, school_id="school-1"):
    return {"Authorization": f"Bearer {create_access_token(user_id, school_id=school_id, role=role)}"}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def make_user(role, school_id):
    user_id = uid(f"hev-{role}")
    return User(id=user_id, email=f"{user_id}@test.invalid", name=f"Test {role}", hashed_password="x",
                role=role, school_id=school_id)


def make_student(cls, school_id, name):
    return Student(id=uid("hev-student"), school_id=school_id, class_id=cls.id, class_name=cls.name, name=name,
                   roll_no=1, lu_score=41, cu_score=72, au_score=63, ct_score=54, overall_score=57,
                   baseline_lu=31, baseline_cu=52, baseline_au=43, baseline_ct=34, baseline_overall=40)


FROZEN_KEYS = {1: ("SECRET-ANSWER-1", "SECRET-RUBRIC-1"), 2: ("SECRET-ANSWER-2", None),
               3: (None, "SECRET-RUBRIC-3"), 4: (None, None)}  # distinctive; some deliberately missing


def make_assignment(student, subject_id, created_by):
    items = [
        HomeworkDraftItemRecord(
            position=i, source_question_id=uid("src"), text=f"{student.name} question {i}", type=qtype,
            options_json=list(options), marks=3, competency="LU", competency_rank=1, bloom_level="Apply",
            is_ai_generated=False, correct_answer=FROZEN_KEYS[i][0], marking_rubric=FROZEN_KEYS[i][1],
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
        id=uid("hev-asg"), draft=draft, student_id=student.id, school_id=student.school_id, subject_id=subject_id,
        assigned_by=created_by, assigned_at=NOW - timedelta(days=2), due_at=NOW + timedelta(days=1),
        status="assigned",
    )


@pytest_asyncio.fixture
async def world(db_session, client, monkeypatch):
    """Alice and Cara have submitted (Alice answered questions 1 and 3), Bob is in progress, Dan
    hasn't started. Dan also has an assignment from another teacher in the same school, submitted
    blank. Cara is in another school."""
    subj = Subject(id=uid("hev-subj"), name="Grading Maths", code=uid("HEV"), grade=8)
    cls1 = ClassSection(id=uid("hev-c1"), school_id="school-1", grade=8, section="S", name="GR 1",
                        subject_ids_json=[subj.id])
    cls3 = ClassSection(id=uid("hev-c3"), school_id="school-3", grade=8, section="T", name="GR 3",
                        subject_ids_json=[subj.id])
    alice, bob, dan = (make_student(cls1, "school-1", n) for n in ("Alice", "Bob", "Dan"))
    cara = make_student(cls3, "school-3", "Cara")
    users = {k: make_user("student", s) for k, s in (("u_alice", "school-1"), ("u_bob", "school-1"),
                                                      ("u_dan", "school-1"), ("u_cara", "school-3"))}
    users["u_unlinked"] = make_user("student", "school-1")
    users["u_teacher2"] = make_user("teacher", "school-1")
    users["u_parent"] = make_user("parent", "school-1")

    assignments = {
        "a_alice": make_assignment(alice, subj.id, "user-teacher-1"),
        "a_bob": make_assignment(bob, subj.id, "user-teacher-1"),
        "a_dan": make_assignment(dan, subj.id, "user-teacher-1"),
        "a_teacher2": make_assignment(dan, subj.id, users["u_teacher2"].id),
        "a_cara": make_assignment(cara, subj.id, "user-teacher-3"),
    }
    ids = {"alice": alice.id, "bob": bob.id, "dan": dan.id, "cara": cara.id, "classes": [cls1.id, cls3.id],
           "subject": subj.id, **{k: u.id for k, u in users.items()}, **{k: a.id for k, a in assignments.items()}}
    db_session.add_all([subj, cls1, cls3, alice, bob, dan, cara, *users.values(), *assignments.values(),
                        *(StudentAccountLink(user_id=users[u].id, student_id=s.id, created_by="user-admin")
                          for u, s in (("u_alice", alice), ("u_bob", bob), ("u_dan", dan), ("u_cara", cara))),
                        ParentStudentLink(id=uid("hev-plink"), parent_user_id=users["u_parent"].id,
                                          student_id=alice.id)])
    await db_session.commit()

    monkeypatch.setattr(homework_router, "utc_now", lambda: NOW)

    async def student_put(user, assignment, answers):
        res = await client.put(STUDENT_SUB.format(assignment), headers=bearer(ids[user], "student"),
                               json={"answers": answers})
        assert res.status_code == 201, res.text

    async def student_submit(user, assignment, school="school-1", version=None):
        body = {} if version is None else {"expected_version": version}
        res = await client.post(STUDENT_SUB.format(assignment) + "/submit", headers=bearer(ids[user], "student", school),
                                json=body)
        assert res.status_code == 200, res.text

    await student_put("u_alice", ids["a_alice"], [{"position": 1, "selected_option_index": 2},
                                                  {"position": 3, "answer_text": "Alice's explanation"}])
    await student_submit("u_alice", ids["a_alice"], version=1)
    await student_put("u_bob", ids["a_bob"], [{"position": 2, "answer_text": "Bob's draft"}])
    await student_submit("u_dan", ids["a_teacher2"])
    res = await client.post(STUDENT_SUB.format(ids["a_cara"]) + "/submit",
                            headers=bearer(ids["u_cara"], "student", "school-3"), json={})
    assert res.status_code == 200
    monkeypatch.undo()
    yield ids

    await db_session.rollback()
    for key in ("a_alice", "a_bob", "a_dan", "a_teacher2", "a_cara"):
        await db_session.execute(text("DELETE FROM audit_events WHERE details LIKE :d"), {"d": f"%{ids[key]}%"})
    for student_id in (ids["alice"], ids["bob"], ids["dan"], ids["cara"]):
        p = {"s": student_id}
        for sql in (
            "DELETE FROM homework_evaluation_items WHERE evaluation_id IN "
            "(SELECT id FROM homework_evaluations WHERE student_id = :s)",
            "DELETE FROM homework_evaluations WHERE student_id = :s",
            "DELETE FROM homework_submission_answers WHERE submission_id IN "
            "(SELECT id FROM homework_submissions WHERE student_id = :s)",
            "DELETE FROM homework_submissions WHERE student_id = :s",
            "DELETE FROM homework_assignments WHERE student_id = :s",
            "DELETE FROM homework_draft_items WHERE draft_id IN (SELECT id FROM homework_drafts WHERE student_id = :s)",
            "DELETE FROM homework_drafts WHERE student_id = :s",
            "DELETE FROM student_account_links WHERE student_id = :s",
            "DELETE FROM student_competency_snapshots WHERE student_id = :s",
            "DELETE FROM notifications WHERE user_id = :s",
            "DELETE FROM parent_student_links WHERE student_id = :s",
            "DELETE FROM students WHERE id = :s",
        ):
            await db_session.execute(text(sql), p)
    for key in ("u_alice", "u_bob", "u_dan", "u_cara", "u_unlinked", "u_teacher2", "u_parent"):
        await db_session.execute(text("DELETE FROM audit_events WHERE user_id = :u"), {"u": ids[key]})
        await db_session.execute(text("DELETE FROM student_account_links WHERE user_id = :u"), {"u": ids[key]})
        await db_session.execute(text("DELETE FROM users WHERE id = :u"), {"u": ids[key]})
    for class_id in ids["classes"]:
        await db_session.execute(text("DELETE FROM classes WHERE id = :c"), {"c": class_id})
    await db_session.execute(text("DELETE FROM subjects WHERE id = :j"), {"j": ids["subject"]})
    await db_session.commit()


# --- Helpers --------------------------------------------------------------------------------------


async def start(client, w, key, headers):
    return await client.post(EVAL.format(w[key]), headers=headers)


async def mark(client, w, key, items, version, headers):
    return await client.patch(ITEMS.format(w[key]), headers=headers,
                              json={"expected_version": version, "items": items})


async def transition(client, url, w, key, version, headers):
    return await client.post(url.format(w[key]), headers=headers, json={"expected_version": version})


ALL_MARKED = [{"position": 1, "awarded_marks": 3}, {"position": 2, "awarded_marks": 0},
              {"position": 3, "awarded_marks": 2, "feedback": "Good reasoning; check units."},
              {"position": 4, "awarded_marks": 0, "feedback": "Not attempted."}]


async def marked_and_finalized(client, w, headers, key="a_alice"):
    """Start, mark every question (3 + 0 + 2 + 0 = 5 of 12), finalize. Returns the response."""
    assert (await start(client, w, key, headers)).status_code == 201
    assert (await mark(client, w, key, ALL_MARKED, 1, headers)).status_code == 200
    res = await transition(client, FINALIZE, w, key, 2, headers)
    assert res.status_code == 200, res.text
    return res


async def count(db_session, sql, **params):
    await db_session.rollback()  # fresh read
    return (await db_session.execute(text(sql), params)).scalar()


async def evaluations_for(db_session, assignment_id):
    return await count(db_session, "SELECT COUNT(*) FROM homework_evaluations WHERE assignment_id = :a",
                       a=assignment_id)


async def audits(db_session, action, assignment_id):
    return await count(db_session, "SELECT COUNT(*) FROM audit_events WHERE action = :x AND details LIKE :d",
                       x=action, d=f"%{assignment_id}%")


def race_after_load(monkeypatch, competing):
    """Run `competing` (a whole other request) right after this request reads the evaluation and
    before it writes. Only the first lookup does this."""
    real_load = homework_router._load_evaluation
    state = {"raced": False}

    async def load_then_race(db, submission_id):
        loaded = await real_load(db, submission_id)
        if not state["raced"]:
            state["raced"] = True
            await competing()
        return loaded

    monkeypatch.setattr(homework_router, "_load_evaluation", load_then_race)


# --- Starting an evaluation ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_creates_one_pending_evaluation_with_every_question(client, db_session, world, teacher_token):
    res = await start(client, world, "a_alice", auth(teacher_token))
    assert res.status_code == 201
    body = res.json()
    assert (body["status"], body["version"], body["total_max"], body["total_awarded"]) == ("pending", 1, 12, None)
    assert (body["marked_count"], body["question_count"], body["created_by"]) == (0, 4, "user-teacher-1")
    assert (body["student_id"], body["student_name"], body["is_late"]) == (world["alice"], "Alice", False)
    assert [i["position"] for i in body["items"]] == [1, 2, 3, 4]
    assert [i["answered"] for i in body["items"]] == [True, False, True, False]  # unanswered ones included
    assert all(i["awarded_marks"] is None and i["max_marks"] == 3 for i in body["items"])
    assert body["items"][0]["selected_option_index"] == 2 and body["items"][0]["options"] == ["A", "B", "C"]
    assert body["items"][2]["answer_text"] == "Alice's explanation"
    assert await evaluations_for(db_session, world["a_alice"]) == 1
    assert await audits(db_session, "Homework Evaluation Started", world["a_alice"]) == 1


@pytest.mark.asyncio
async def test_repeated_start_returns_the_same_evaluation(client, db_session, world, teacher_token, principal_token):
    first = await start(client, world, "a_alice", auth(teacher_token))
    again = await start(client, world, "a_alice", auth(teacher_token))
    by_principal = await start(client, world, "a_alice", auth(principal_token))
    assert again.status_code == 200 and by_principal.status_code == 200
    assert again.json() == first.json() == by_principal.json()  # same ID, same version, nothing changed
    assert await evaluations_for(db_session, world["a_alice"]) == 1
    assert await audits(db_session, "Homework Evaluation Started", world["a_alice"]) == 1


@pytest.mark.asyncio
async def test_only_submitted_homework_can_be_evaluated(client, db_session, world, teacher_token):
    for key in ("a_bob", "a_dan"):  # in progress; not started
        res = await start(client, world, key, auth(teacher_token))
        assert res.status_code == 409 and res.json() == {"detail": "Only submitted homework can be evaluated."}
        assert "Bob's draft" not in res.text
        assert await evaluations_for(db_session, world[key]) == 0


@pytest.mark.asyncio
async def test_simultaneous_starts_create_one_evaluation(client, db_session, world, teacher_token, monkeypatch):
    async def competing_start():
        assert (await start(client, world, "a_alice", auth(teacher_token))).status_code == 201

    race_after_load(monkeypatch, competing_start)
    loser = await start(client, world, "a_alice", auth(teacher_token))
    monkeypatch.undo()
    assert loser.status_code == 200  # gets the winner's evaluation, as a repeated request would
    winner = await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token))
    assert loser.json()["id"] == winner.json()["id"]
    assert await evaluations_for(db_session, world["a_alice"]) == 1
    assert await audits(db_session, "Homework Evaluation Started", world["a_alice"]) == 1


@pytest.mark.asyncio
async def test_inconsistent_submission_data_fails_safely(client, db_session, world, teacher_token):
    foreign_item = await count(db_session, "SELECT i.id FROM homework_draft_items i JOIN homework_assignments a "
                                           "ON a.draft_id = i.draft_id WHERE a.id = :a AND i.position = 2",
                               a=world["a_dan"])
    await db_session.execute(text(
        "UPDATE homework_submission_answers SET draft_item_id = :i WHERE id = (SELECT id FROM "
        "homework_submission_answers WHERE submission_id = (SELECT id FROM homework_submissions "
        "WHERE assignment_id = :a) LIMIT 1)"), {"i": foreign_item, "a": world["a_alice"]})
    await db_session.commit()
    res = await start(client, world, "a_alice", auth(teacher_token))
    assert res.status_code == 500
    assert res.json() == {"detail": "This submission can't be processed because of a server-side data problem."}
    assert "Alice" not in res.text and foreign_item not in res.text
    assert await evaluations_for(db_session, world["a_alice"]) == 0


@pytest.mark.asyncio
async def test_tampered_evaluation_items_fail_safely(client, db_session, world, teacher_token):
    await start(client, world, "a_alice", auth(teacher_token))
    await db_session.execute(text(
        "UPDATE homework_evaluation_items SET max_marks = 99 WHERE position = 1 AND evaluation_id = "
        "(SELECT id FROM homework_evaluations WHERE assignment_id = :a)"), {"a": world["a_alice"]})
    await db_session.commit()
    for res in (await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token)),
                await mark(client, world, "a_alice", [{"position": 1, "awarded_marks": 50}], 1, auth(teacher_token))):
        assert res.status_code == 500 and "99" not in res.text


@pytest.mark.asyncio
async def test_get_before_start_is_404_and_creates_nothing(client, db_session, world, teacher_token):
    for key in ("a_alice", "a_bob", "a_dan"):
        res = await client.get(EVAL.format(world[key]), headers=auth(teacher_token))
        assert res.status_code == 404 and res.json() == NO_EVALUATION
    assert await evaluations_for(db_session, world["a_alice"]) == 0


# --- Marking ----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marks_and_feedback_save(client, world, teacher_token):
    await start(client, world, "a_alice", auth(teacher_token))
    res = await mark(client, world, "a_alice", [{"position": 1, "awarded_marks": 3},
                                                {"position": 3, "feedback": "Show your working."}],
                     1, auth(teacher_token))
    assert res.status_code == 200
    body = res.json()
    assert body["version"] == 2 and body["marked_count"] == 1 and body["status"] == "pending"
    q1, q2, q3, _ = body["items"]
    assert (q1["awarded_marks"], q1["marked_by"]) == (3, "user-teacher-1") and q1["marked_at"].startswith("20")
    assert (q2["awarded_marks"], q2["marked_by"]) == (None, None)
    assert (q3["awarded_marks"], q3["feedback"]) == (None, "Show your working.")

    # Change a mark; clear feedback with an empty string; fields left out stay.
    res = await mark(client, world, "a_alice", [{"position": 1, "awarded_marks": 2},
                                                {"position": 3, "feedback": "  "}], 2, auth(teacher_token))
    q1, _, q3, _ = res.json()["items"]
    assert (q1["awarded_marks"], q3["feedback"], res.json()["version"]) == (2, None, 3)


@pytest.mark.asyncio
async def test_zero_marks_for_unanswered_questions(client, world, teacher_token):
    await start(client, world, "a_alice", auth(teacher_token))
    res = await mark(client, world, "a_alice", [{"position": 2, "awarded_marks": 0},
                                                {"position": 4, "awarded_marks": 0}], 1, auth(teacher_token))
    assert res.status_code == 200
    assert [(i["answered"], i["awarded_marks"]) for i in res.json()["items"]][1::2] == [(False, 0), (False, 0)]


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [-1, 1.5, "2", True, None, [3]])
async def test_malformed_marks_are_rejected(client, db_session, world, teacher_token, value):
    await start(client, world, "a_alice", auth(teacher_token))
    res = await mark(client, world, "a_alice", [{"position": 1, "awarded_marks": value}], 1, auth(teacher_token))
    assert res.status_code == 422
    after = (await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token))).json()
    assert after["version"] == 1 and after["items"][0]["awarded_marks"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity", "1e309"])
async def test_nan_and_infinity_are_rejected(client, world, teacher_token, raw):
    await start(client, world, "a_alice", auth(teacher_token))
    content = '{"expected_version": 1, "items": [{"position": 1, "awarded_marks": %s}]}' % raw
    res = await client.patch(ITEMS.format(world["a_alice"]), content=content,
                             headers={**auth(teacher_token), "Content-Type": "application/json"})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_marks_above_the_maximum_and_unknown_questions_reject_the_whole_request(client, world, teacher_token):
    await start(client, world, "a_alice", auth(teacher_token))
    res = await mark(client, world, "a_alice", [{"position": 2, "awarded_marks": 1},  # valid, must not apply
                                                {"position": 1, "awarded_marks": 4},  # max is 3
                                                {"position": 9, "awarded_marks": 0}], 1, auth(teacher_token))
    assert res.status_code == 422
    assert res.json()["detail"] == [
        {"position": 1, "reason": "awarded_marks must be a whole number from 0 to 3"},
        {"position": 9, "reason": "there is no question at this position"},
    ]
    after = (await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token))).json()
    assert after["version"] == 1 and after["marked_count"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"expected_version": 1, "items": [{"position": 1}]},  # nothing to change
    {"expected_version": 1, "items": [{"position": 1, "feedback": None}]},
    {"expected_version": 1, "items": [{"position": 1, "feedback": "x" * 2001}]},
    {"expected_version": 1, "items": [{"position": 1, "awarded_marks": 1}, {"position": 1, "awarded_marks": 2}]},
    {"expected_version": 1, "items": []},
    {"items": [{"position": 1, "awarded_marks": 1}]},  # no version
    {"expected_version": 1, "items": [{"position": 1, "awarded_marks": 1, "status": "marked"}]},
])
async def test_malformed_update_bodies_are_rejected(client, world, teacher_token, body):
    await start(client, world, "a_alice", auth(teacher_token))
    res = await client.patch(ITEMS.format(world["a_alice"]), json=body, headers=auth(teacher_token))
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_feedback_at_the_length_limit_is_accepted(client, world, teacher_token):
    await start(client, world, "a_alice", auth(teacher_token))
    res = await mark(client, world, "a_alice", [{"position": 1, "feedback": "x" * 2000}], 1, auth(teacher_token))
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_stale_version_is_409(client, world, teacher_token):
    await start(client, world, "a_alice", auth(teacher_token))
    await mark(client, world, "a_alice", [{"position": 1, "awarded_marks": 1}], 1, auth(teacher_token))
    res = await mark(client, world, "a_alice", [{"position": 1, "awarded_marks": 3}], 1, auth(teacher_token))
    assert res.status_code == 409
    after = (await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token))).json()
    assert after["items"][0]["awarded_marks"] == 1 and after["version"] == 2


@pytest.mark.asyncio
async def test_concurrent_marking_does_not_overwrite(client, world, teacher_token, principal_token, monkeypatch):
    await start(client, world, "a_alice", auth(teacher_token))

    async def competing_mark():
        res = await mark(client, world, "a_alice", [{"position": 1, "awarded_marks": 3}], 1, auth(principal_token))
        assert res.status_code == 200

    race_after_load(monkeypatch, competing_mark)
    loser = await mark(client, world, "a_alice", [{"position": 1, "awarded_marks": 0},
                                                  {"position": 2, "awarded_marks": 1}], 1, auth(teacher_token))
    monkeypatch.undo()
    assert loser.status_code == 409
    assert loser.json() == {"detail": "This evaluation was changed by another request. Reload it and try again."}
    after = (await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token))).json()
    assert [i["awarded_marks"] for i in after["items"]] == [3, None, None, None]  # nothing of the loser
    assert after["items"][0]["marked_by"] == "user-principal-1"


# --- Finalizing ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unmarked_questions_prevent_finalizing(client, db_session, world, teacher_token):
    await start(client, world, "a_alice", auth(teacher_token))
    await mark(client, world, "a_alice", [{"position": 1, "awarded_marks": 3},
                                          {"position": 3, "feedback": "Feedback alone isn't a mark."}],
               1, auth(teacher_token))
    res = await transition(client, FINALIZE, world, "a_alice", 2, auth(teacher_token))
    assert res.status_code == 409 and res.json()["detail"].endswith("Unmarked: [2, 3, 4].")
    after = (await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token))).json()
    assert (after["status"], after["total_awarded"], after["version"]) == ("pending", None, 2)
    assert await audits(db_session, "Homework Evaluation Finalized", world["a_alice"]) == 0


@pytest.mark.asyncio
async def test_finalize_stores_totals_and_locks(client, db_session, world, teacher_token):
    res = await marked_and_finalized(client, world, auth(teacher_token))
    body = res.json()
    assert (body["status"], body["total_awarded"], body["total_max"], body["version"]) == ("marked", 5, 12, 3)
    assert body["finalized_by"] == "user-teacher-1" and body["finalized_at"] and body["released_at"] is None
    stored = await count(db_session, "SELECT total_awarded FROM homework_evaluations WHERE assignment_id = :a",
                         a=world["a_alice"])
    assert stored == 5
    assert await audits(db_session, "Homework Evaluation Finalized", world["a_alice"]) == 1

    for res in (await mark(client, world, "a_alice", [{"position": 2, "awarded_marks": 3}], 3, auth(teacher_token)),
                await transition(client, FINALIZE, world, "a_alice", 3, auth(teacher_token))):
        assert res.status_code == 409
    after = (await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token))).json()
    assert after == body
    assert await audits(db_session, "Homework Evaluation Finalized", world["a_alice"]) == 1


@pytest.mark.asyncio
async def test_finalize_with_a_stale_version_is_409(client, world, teacher_token):
    await start(client, world, "a_alice", auth(teacher_token))
    await mark(client, world, "a_alice", ALL_MARKED, 1, auth(teacher_token))
    assert (await transition(client, FINALIZE, world, "a_alice", 1, auth(teacher_token))).status_code == 409


@pytest.mark.asyncio
async def test_finalize_racing_a_mark_change(client, world, teacher_token, principal_token, monkeypatch):
    await start(client, world, "a_alice", auth(teacher_token))
    await mark(client, world, "a_alice", ALL_MARKED, 1, auth(teacher_token))

    async def competing_change():
        res = await mark(client, world, "a_alice", [{"position": 2, "awarded_marks": 3}], 2, auth(principal_token))
        assert res.status_code == 200

    race_after_load(monkeypatch, competing_change)
    assert (await transition(client, FINALIZE, world, "a_alice", 2, auth(teacher_token))).status_code == 409
    monkeypatch.undo()
    after = (await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token))).json()
    assert (after["status"], after["items"][1]["awarded_marks"]) == ("pending", 3)


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["finalize", "release"])
async def test_transitions_are_atomic_with_their_audit_event(client, db_session, world, teacher_token, monkeypatch,
                                                             step):
    """If the audit event can't be saved, neither is the state change."""
    await start(client, world, "a_alice", auth(teacher_token))
    await mark(client, world, "a_alice", ALL_MARKED, 1, auth(teacher_token))
    if step == "release":
        await transition(client, FINALIZE, world, "a_alice", 2, auth(teacher_token))
    real_audit = homework_router._audit

    def broken_audit(user, action, details):
        event = real_audit(user, action, details)
        event.user_name = None  # NOT NULL in the database
        return event

    monkeypatch.setattr(homework_router, "_audit", broken_audit)
    failed = await transition(client, FINALIZE if step == "finalize" else RELEASE, world, "a_alice",
                              2 if step == "finalize" else 3, auth(teacher_token))
    assert failed.status_code == 500
    assert failed.json() == {"detail": "Database operation failed."}
    monkeypatch.undo()
    after = (await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token))).json()
    if step == "finalize":
        assert (after["status"], after["total_awarded"], after["finalized_at"]) == ("pending", None, None)
    else:
        assert (after["status"], after["released_at"]) == ("marked", None)


# --- Releasing ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_release_before_finalizing_is_rejected(client, world, teacher_token):
    await start(client, world, "a_alice", auth(teacher_token))
    res = await transition(client, RELEASE, world, "a_alice", 1, auth(teacher_token))
    assert res.status_code == 409 and res.json() == {"detail": "Only a finalized evaluation can be released."}


@pytest.mark.asyncio
async def test_release_is_recorded_idempotent_and_final(client, db_session, world, teacher_token, principal_token):
    await marked_and_finalized(client, world, auth(teacher_token))
    first = await transition(client, RELEASE, world, "a_alice", 3, auth(principal_token))
    assert first.status_code == 200
    body = first.json()
    assert (body["status"], body["released_by"], body["version"]) == ("released", "user-principal-1", 4)
    assert body["finalized_by"] == "user-teacher-1" and body["released_at"]

    for version in (4, 3, 99):  # repeated, even with an old version: same result, nothing written
        again = await transition(client, RELEASE, world, "a_alice", version, auth(teacher_token))
        assert again.status_code == 200 and again.json() == body
    assert await audits(db_session, "Homework Results Released", world["a_alice"]) == 1

    for res in (await mark(client, world, "a_alice", [{"position": 2, "awarded_marks": 3}], 4, auth(teacher_token)),
                await transition(client, FINALIZE, world, "a_alice", 4, auth(teacher_token))):
        assert res.status_code == 409
    assert (await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token))).json() == body


# --- The teacher queue --------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_follows_the_evaluation(client, world, teacher_token):
    async def queue(key="a_alice"):
        res = await client.get(QUEUE.format(world[key]), headers=auth(teacher_token))
        assert res.status_code == 200
        return res.json()

    assert await queue("a_bob") == [] and await queue("a_dan") == []  # not submitted: not listed
    rows = await queue()
    assert rows == [{"student_id": world["alice"], "student_name": "Alice", "submitted_at": rows[0]["submitted_at"],
                     "is_late": False, "evaluation_status": "not_started", "evaluation_id": None,
                     "marked_count": 0, "question_count": 4}]
    started = (await start(client, world, "a_alice", auth(teacher_token))).json()
    await mark(client, world, "a_alice", [{"position": 1, "awarded_marks": 3}], 1, auth(teacher_token))
    assert [(r["evaluation_status"], r["evaluation_id"], r["marked_count"]) for r in await queue()] == [
        ("pending", started["id"], 1)]
    await mark(client, world, "a_alice", ALL_MARKED, 2, auth(teacher_token))
    await transition(client, FINALIZE, world, "a_alice", 3, auth(teacher_token))
    assert (await queue())[0]["evaluation_status"] == "marked"
    await transition(client, RELEASE, world, "a_alice", 4, auth(teacher_token))
    assert (await queue())[0]["evaluation_status"] == "released"


# --- Authorization ------------------------------------------------------------------------------------


async def every_teacher_call(client, w, key, headers):
    return [
        await client.get(QUEUE.format(w[key]), headers=headers),
        await client.post(EVAL.format(w[key]), headers=headers),
        await client.get(EVAL.format(w[key]), headers=headers),
        await client.patch(ITEMS.format(w[key]), headers=headers,
                           json={"expected_version": 1, "items": [{"position": 1, "awarded_marks": 1}]}),
        await client.post(FINALIZE.format(w[key]), headers=headers, json={"expected_version": 1}),
        await client.post(RELEASE.format(w[key]), headers=headers, json={"expected_version": 1}),
    ]


@pytest.mark.asyncio
async def test_other_teachers_and_schools_get_a_generic_404(client, db_session, world, teacher_token,
                                                            other_school_teacher_token):
    for headers, key, name in ((auth(teacher_token), "a_teacher2", "Dan"),  # another teacher, same school
                               (bearer(world["u_teacher2"], "teacher"), "a_alice", "Alice"),
                               (auth(teacher_token), "a_cara", "Cara"),  # another school
                               (auth(other_school_teacher_token), "a_alice", "Alice")):
        for res in await every_teacher_call(client, world, key, headers):
            assert res.status_code == 404 and res.json() == NOT_FOUND, res.text
            assert name not in res.text and "explanation" not in res.text
    for key in ("a_alice", "a_teacher2", "a_cara"):
        assert await evaluations_for(db_session, world[key]) == 0
    missing = await client.post(EVAL.format("no-such-assignment"), headers=auth(teacher_token))
    assert missing.status_code == 404 and missing.json() == NOT_FOUND


@pytest.mark.asyncio
async def test_principal_and_admin_follow_existing_access(client, world, principal_token, admin_token):
    assert (await start(client, world, "a_teacher2", auth(principal_token))).status_code == 201  # their school
    for res in await every_teacher_call(client, world, "a_cara", auth(principal_token)):  # not their school
        assert res.status_code == 404 and res.json() == NOT_FOUND
    assert (await start(client, world, "a_cara", auth(admin_token))).status_code == 201  # any school
    res = await mark(client, world, "a_cara", [{"position": 1, "awarded_marks": 0}], 1, auth(admin_token))
    assert res.status_code == 200 and res.json()["items"][0]["marked_by"] == "user-admin"


@pytest.mark.asyncio
async def test_students_and_parents_are_refused(client, db_session, world, student_token, parent_token):
    for headers in (auth(student_token), auth(parent_token), bearer(world["u_alice"], "student"),
                    bearer(world["u_parent"], "parent")):
        for res in await every_teacher_call(client, world, "a_alice", headers):
            assert res.status_code == 403 and res.json() == {"detail": "Access denied."}
        assert (await client.post(EVAL.format("no-such-assignment"), headers=headers)).status_code == 403
    assert await evaluations_for(db_session, world["a_alice"]) == 0


@pytest.mark.asyncio
async def test_tokenless_demo_mode_is_refused(client, db_session, world):
    assert settings.DEMO_MODE is True
    for res in await every_teacher_call(client, world, "a_alice", {}):
        assert res.status_code == 401
    previous = settings.DEMO_MODE
    settings.DEMO_MODE = False
    try:
        for res in await every_teacher_call(client, world, "a_alice", {"Authorization": "Bearer not-a-jwt"}):
            assert res.status_code == 401
    finally:
        settings.DEMO_MODE = previous
    assert await evaluations_for(db_session, world["a_alice"]) == 0


# --- Student results ----------------------------------------------------------------------------------


async def student_result(client, w, key="a_alice", user="u_alice", school="school-1"):
    return await client.get(RESULT.format(w[key]), headers=bearer(w[user], "student", school))


@pytest.mark.asyncio
async def test_students_see_nothing_before_release(client, world, teacher_token):
    not_started = await student_result(client, world)
    await start(client, world, "a_alice", auth(teacher_token))
    pending = await student_result(client, world)
    await mark(client, world, "a_alice", ALL_MARKED, 1, auth(teacher_token))
    await transition(client, FINALIZE, world, "a_alice", 2, auth(teacher_token))
    marked = await student_result(client, world)
    for res in (not_started, pending, marked):
        assert res.status_code == 404 and res.json() == NO_EVALUATION
        assert res.content == not_started.content  # indistinguishable, so unreleased marks can't be detected
        assert "5" not in res.text and "Good reasoning" not in res.text


@pytest.mark.asyncio
async def test_released_result_for_the_student(client, world, teacher_token):
    await marked_and_finalized(client, world, auth(teacher_token))
    await transition(client, RELEASE, world, "a_alice", 3, auth(teacher_token))
    res = await student_result(client, world)
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"assignment_id", "released_at", "total_awarded", "total_max", "items"}
    assert (body["assignment_id"], body["total_awarded"], body["total_max"]) == (world["a_alice"], 5, 12)
    assert all(set(i) == {"position", "text", "type", "options", "answer_text", "selected_option_index",
                          "max_marks", "awarded_marks", "feedback"} for i in body["items"])
    q1, q2, q3, q4 = body["items"]
    assert q1 == {"position": 1, "text": "Alice question 1", "type": "mcq", "options": ["A", "B", "C"],
                  "answer_text": None, "selected_option_index": 2, "max_marks": 3, "awarded_marks": 3,
                  "feedback": None}
    assert (q2["answer_text"], q2["awarded_marks"]) == (None, 0)
    assert (q3["answer_text"], q3["awarded_marks"], q3["feedback"]) == ("Alice's explanation", 2,
                                                                        "Good reasoning; check units.")
    assert (q4["awarded_marks"], q4["feedback"]) == (0, "Not attempted.")
    for hidden in HIDDEN + ("version", "marked_by", "marked_at", "finalized", "released_by", "created_by",
                            "user-teacher-1", "status", "evaluation_id", world["alice"], world["u_alice"]):
        assert hidden not in res.text, hidden


@pytest.mark.asyncio
async def test_students_only_see_their_own_results(client, world, teacher_token, admin_token):
    await marked_and_finalized(client, world, auth(teacher_token))
    await transition(client, RELEASE, world, "a_alice", 3, auth(teacher_token))
    for user, school in (("u_bob", "school-1"), ("u_dan", "school-1"), ("u_cara", "school-3")):
        res = await student_result(client, world, user=user, school=school)
        assert res.status_code == 404 and res.json() == NOT_FOUND and "Good reasoning" not in res.text
    unlinked = await student_result(client, world, user="u_unlinked")
    assert unlinked.status_code == 403 and unlinked.json() == {"detail": "This account isn't linked to a student record."}
    for headers in (auth(teacher_token), auth(admin_token), bearer(world["u_parent"], "parent"), {}):
        assert (await client.get(RESULT.format(world["a_alice"]), headers=headers)).status_code == (403 if headers else 401)


# --- Read-only reads, preserved submissions, untouched competency scores -------------------------------


async def snapshot(db_session, w):
    async def rows(sql, **params):
        return [tuple(r) for r in (await db_session.execute(text(sql), params)).all()]

    await db_session.rollback()
    return {
        "evaluations": await rows("SELECT id, status, version, updated_at, total_awarded, released_at "
                                  "FROM homework_evaluations ORDER BY id"),
        "items": await rows("SELECT id, awarded_marks, feedback, marked_at FROM homework_evaluation_items ORDER BY id"),
        "submissions": await rows("SELECT id, status, version, updated_at, submitted_at, is_late "
                                  "FROM homework_submissions ORDER BY id"),
        "answers": await rows("SELECT id, draft_item_id, answer_text, selected_option_index, updated_at "
                              "FROM homework_submission_answers ORDER BY id"),
        "assignments": await rows("SELECT id, status, due_at FROM homework_assignments ORDER BY id"),
        "audit": await rows("SELECT COUNT(*) FROM audit_events"),
    }


@pytest.mark.asyncio
async def test_reads_change_nothing(client, db_session, world, teacher_token):
    await start(client, world, "a_alice", auth(teacher_token))
    before = await snapshot(db_session, world)
    for key in ("a_alice", "a_bob", "a_dan"):
        await client.get(QUEUE.format(world[key]), headers=auth(teacher_token))
        await client.get(EVAL.format(world[key]), headers=auth(teacher_token))
        await student_result(client, world, key=key)
    assert await snapshot(db_session, world) == before


@pytest.mark.asyncio
async def test_grading_never_changes_the_submission_or_competency_scores(client, db_session, world, teacher_token):
    """Marking and finalizing never touch scores. Releasing the result is graded evidence: it moves only that
    student's parameters, adds exactly one progress snapshot and never changes submissions or answers."""
    async def scores():
        await db_session.rollback()
        students = {r[0]: tuple(r[1:]) for r in (await db_session.execute(text(
            "SELECT id, lu_score, cu_score, au_score, ct_score, overall_score, baseline_lu, baseline_cu, "
            "baseline_au, baseline_ct, baseline_overall FROM students ORDER BY id"))).all()}
        snapshots = (await db_session.execute(text("SELECT COUNT(*) FROM student_competency_snapshots"))).scalar()
        assessment_subs = (await db_session.execute(text("SELECT COUNT(*) FROM assessment_submissions"))).scalar()
        return students, snapshots, assessment_subs

    before_scores = await scores()
    before = await snapshot(db_session, world)
    await marked_and_finalized(client, world, auth(teacher_token))
    assert await scores() == before_scores  # marking/finalizing alone changes nothing
    await transition(client, RELEASE, world, "a_alice", 3, auth(teacher_token))
    after = await snapshot(db_session, world)
    assert (after["submissions"], after["answers"], after["assignments"]) == (
        before["submissions"], before["answers"], before["assignments"])
    students, snapshots, assessment_subs = await scores()
    changed = {sid for sid in students if students[sid] != before_scores[0][sid]}
    assert changed <= {world["alice"]}  # only the student whose homework was released
    assert all(students[sid][5:] == before_scores[0][sid][5:] for sid in students)  # baselines never move
    assert snapshots == before_scores[1] + 1 and assessment_subs == before_scores[2]


# --- API schema -----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_openapi_has_no_hidden_fields(client):
    spec = (await client.get("/api/v1/openapi.json")).json()
    paths, schemas = spec["paths"], spec["components"]["schemas"]
    base = "/api/v1/homework/assignments/{assignment_id}"
    assert set(paths[base + "/evaluation"]) == {"get", "post"} and set(paths[base + "/evaluation/items"]) == {"patch"}
    assert set(paths[base + "/evaluations"]) == {"get"}
    assert set(paths["/api/v1/students/me/homework/assignments/{assignment_id}/evaluation"]) == {"get"}
    fields = " ".join(str(schemas[n]["properties"]) for n in (
        "TeacherEvaluationOut", "TeacherEvaluationItemOut", "TeacherEvaluationQueueItemOut",
        "StudentResultOut", "StudentResultItemOut"))
    for hidden in ("competency", "bloom", "source_question_id", "draft_item_id", "percentage", "grade", "score"):
        assert hidden not in fields, hidden
    # Answer keys and rubrics: only in the teacher's per-question evaluation schema.
    assert {"correct_answer", "marking_rubric"} <= set(schemas["TeacherEvaluationItemOut"]["properties"])
    for name in ("TeacherEvaluationOut", "TeacherEvaluationQueueItemOut", "StudentResultOut", "StudentResultItemOut"):
        for hidden in ("correct_answer", "marking_rubric", "rubric"):
            assert hidden not in str(schemas[name]["properties"]), (name, hidden)
    student = str(schemas["StudentResultOut"]["properties"]) + str(schemas["StudentResultItemOut"]["properties"])
    for teacher_only in ("version", "marked_by", "finalized", "released_by", "created_by", "student_id", "status"):
        assert teacher_only not in student, teacher_only


# --- Hardening review --------------------------------------------------------------------------------


async def eval_sql(db_session, sql, w, key="a_alice"):
    """Run SQL against the assignment's evaluation (`:a` is the assignment ID) and commit."""
    await db_session.rollback()
    await db_session.execute(text(sql), {"a": w[key]})
    await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    '{"expected_version": 1, "items": [{"position": 1, "awarded_marks": ' + "9" * 5000 + '}]}',
    '{"expected_version": 1, "items": [{"position": 100000000000000000000000000000, "awarded_marks": 1}]}',
    '{"expected_version": 100000000000000000000000000000, "items": [{"position": 1, "awarded_marks": 1}]}',
    '{"expected_version": 1, "items": [{"position": 1, "awarded_marks": 99999999999999999999}]}',
    'not json at all',
    '{"expected_version": 1, "items": [{"position": 1, "awarded_marks": 1}',
])
async def test_huge_numbers_and_broken_json_never_crash(client, world, teacher_token, body):
    await start(client, world, "a_alice", auth(teacher_token))
    res = await client.patch(ITEMS.format(world["a_alice"]), content=body,
                             headers={**auth(teacher_token), "Content-Type": "application/json"})
    assert res.status_code in (400, 409, 422), (res.status_code, res.text[:200])
    after = (await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token))).json()
    assert after["version"] == 1 and after["marked_count"] == 0


@pytest.mark.asyncio
async def test_the_words_nan_and_infinity_in_feedback_are_fine(client, world, teacher_token):
    await start(client, world, "a_alice", auth(teacher_token))
    res = await mark(client, world, "a_alice", [{"position": 1, "feedback": "NaN, Infinity and -Infinity"}],
                     1, auth(teacher_token))
    assert res.status_code == 200 and res.json()["items"][0]["feedback"] == "NaN, Infinity and -Infinity"


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [FINALIZE, RELEASE])
async def test_nan_in_transition_bodies_is_a_clean_422(client, world, teacher_token, url):
    await start(client, world, "a_alice", auth(teacher_token))
    res = await client.post(url.format(world["a_alice"]), content='{"expected_version": NaN}',
                            headers={**auth(teacher_token), "Content-Type": "application/json"})
    assert res.status_code == 422 and res.json()["detail"][0]["loc"] == ["body"]


@pytest.mark.asyncio
async def test_two_simultaneous_finalizes(client, db_session, world, teacher_token, principal_token, monkeypatch):
    await start(client, world, "a_alice", auth(teacher_token))
    await mark(client, world, "a_alice", ALL_MARKED, 1, auth(teacher_token))

    async def competing_finalize():
        assert (await transition(client, FINALIZE, world, "a_alice", 2, auth(principal_token))).status_code == 200

    race_after_load(monkeypatch, competing_finalize)
    loser = await transition(client, FINALIZE, world, "a_alice", 2, auth(teacher_token))
    monkeypatch.undo()
    assert loser.status_code == 409
    after = (await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token))).json()
    assert (after["status"], after["finalized_by"], after["total_awarded"]) == ("marked", "user-principal-1", 5)
    assert await audits(db_session, "Homework Evaluation Finalized", world["a_alice"]) == 1


@pytest.mark.asyncio
async def test_two_simultaneous_releases_both_succeed_with_one_audit_event(client, db_session, world, teacher_token,
                                                                           principal_token, monkeypatch):
    """Release is idempotent, so a release that loses a race to another release has still got
    what it asked for: 200 with the released evaluation, not a conflict, and one audit event."""
    await marked_and_finalized(client, world, auth(teacher_token))

    async def competing_release():
        assert (await transition(client, RELEASE, world, "a_alice", 3, auth(principal_token))).status_code == 200

    race_after_load(monkeypatch, competing_release)
    loser = await transition(client, RELEASE, world, "a_alice", 3, auth(teacher_token))
    monkeypatch.undo()
    assert loser.status_code == 200, loser.text
    assert (loser.json()["status"], loser.json()["released_by"]) == ("released", "user-principal-1")
    assert await audits(db_session, "Homework Results Released", world["a_alice"]) == 1


@pytest.mark.asyncio
async def test_release_racing_a_change_that_is_not_a_release_is_409(client, world, teacher_token, monkeypatch):
    """Only another *release* makes a lost release race succeed. Here the evaluation is changed
    behind the request's back (simulated with a version bump) and stays unreleased."""
    await marked_and_finalized(client, world, auth(teacher_token))
    from backend.app.db.session import AsyncSessionLocal

    async def competing_bump():
        async with AsyncSessionLocal() as other:
            await other.execute(text("UPDATE homework_evaluations SET version = version + 1 WHERE assignment_id = :a"),
                                {"a": world["a_alice"]})
            await other.commit()

    race_after_load(monkeypatch, competing_bump)
    res = await transition(client, RELEASE, world, "a_alice", 3, auth(teacher_token))
    monkeypatch.undo()
    assert res.status_code == 409
    after = (await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token))).json()
    assert after["status"] == "marked"


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", [
    "UPDATE homework_evaluations SET total_awarded = 11 WHERE assignment_id = :a",  # totals don't add up
    "UPDATE homework_evaluation_items SET awarded_marks = NULL WHERE position = 2 AND evaluation_id = "
    "(SELECT id FROM homework_evaluations WHERE assignment_id = :a)",  # finalized but a question unmarked
    "UPDATE homework_evaluations SET school_id = 'school-3' WHERE assignment_id = :a",
    "UPDATE homework_evaluations SET student_id = 'someone-else' WHERE assignment_id = :a",
    "UPDATE homework_submissions SET status = 'in_progress', submitted_at = NULL, is_late = 0 "
    "WHERE assignment_id = :a",  # an evaluation for homework that isn't submitted
])
async def test_tampered_evaluations_fail_closed_everywhere(client, db_session, world, teacher_token, tamper):
    await marked_and_finalized(client, world, auth(teacher_token))
    await transition(client, RELEASE, world, "a_alice", 3, auth(teacher_token))
    await eval_sql(db_session, tamper, world)
    responses = [
        await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token)),
        await client.get(QUEUE.format(world["a_alice"]), headers=auth(teacher_token)),
        await client.post(EVAL.format(world["a_alice"]), headers=auth(teacher_token)),
        await transition(client, RELEASE, world, "a_alice", 4, auth(teacher_token)),
        await student_result(client, world),
    ]
    for res in responses:
        if "in_progress" in tamper and res.request.url.path.endswith("/evaluations"):
            assert res.status_code == 200 and res.json() == []  # not submitted: not listed at all
            continue
        assert res.status_code == 500, (res.request.url.path, res.status_code, res.text[:200])
        assert res.json() == {"detail": "This submission can't be processed because of a server-side data problem."}


@pytest.mark.asyncio
async def test_audit_events_never_contain_answers_or_feedback(client, db_session, world, teacher_token):
    await marked_and_finalized(client, world, auth(teacher_token))
    await transition(client, RELEASE, world, "a_alice", 3, auth(teacher_token))
    await db_session.rollback()
    details = [r[0] for r in (await db_session.execute(text(
        "SELECT details FROM audit_events WHERE details LIKE :d"), {"d": f"%{world['a_alice']}%"})).all()]
    assert len(details) == 4  # the student's submit, then start, finalize, release
    for detail in details:
        for secret in ("Alice's explanation", "Good reasoning", "Not attempted", "SECRET", "Alice"):
            assert secret not in detail, detail


@pytest.mark.asyncio
async def test_an_evaluated_submission_cannot_be_deleted_through_the_orm(client, db_session, world, teacher_token):
    """No endpoint deletes submissions, but scripts using the ORM could. With SQLite foreign keys
    off, that would orphan the evaluation, so it's refused (like assigned drafts)."""
    from sqlalchemy import select

    from backend.app.modules.differentiated_homework.models import (
        EvaluatedSubmissionDeletionError,
        HomeworkSubmissionRecord,
    )

    await start(client, world, "a_alice", auth(teacher_token))
    await db_session.rollback()
    submission = (await db_session.execute(select(HomeworkSubmissionRecord).filter(
        HomeworkSubmissionRecord.assignment_id == world["a_alice"]))).scalars().one()
    await db_session.delete(submission)
    with pytest.raises(EvaluatedSubmissionDeletionError):
        await db_session.commit()
    await db_session.rollback()
    assert await count(db_session, "SELECT COUNT(*) FROM homework_submissions WHERE assignment_id = :a",
                       a=world["a_alice"]) == 1
    assert await evaluations_for(db_session, world["a_alice"]) == 1


@pytest.mark.asyncio
async def test_deleting_an_evaluation_removes_its_items(client, db_session, world, teacher_token):
    from sqlalchemy import select

    from backend.app.modules.differentiated_homework.models import HomeworkEvaluationRecord

    evaluation_id = (await start(client, world, "a_alice", auth(teacher_token))).json()["id"]
    await db_session.rollback()
    evaluation = (await db_session.execute(select(HomeworkEvaluationRecord).filter(
        HomeworkEvaluationRecord.id == evaluation_id))).scalars().one()
    await db_session.delete(evaluation)
    await db_session.commit()
    assert await count(db_session, "SELECT COUNT(*) FROM homework_evaluation_items WHERE evaluation_id = :e",
                       e=evaluation_id) == 0


EVALUATION_INSERT = (
    "INSERT INTO homework_evaluations (id, submission_id, assignment_id, student_id, school_id, status, total_max, "
    "total_awarded, created_by, created_at, updated_at, finalized_by, finalized_at, released_by, released_at, "
    "version) VALUES (:id, :s, 'a', 'st', 'sch', :status, :tmax, :tawarded, 't', '2026-11-09', '2026-11-09', "
    ":fby, :fat, :rby, :rat, 1)"
)
ITEM_INSERT = (
    "INSERT INTO homework_evaluation_items (id, evaluation_id, draft_item_id, position, max_marks, awarded_marks, "
    "feedback, marked_by, marked_at, created_at) VALUES (:id, :e, :item, :pos, :max, :awarded, NULL, :mby, :mat, "
    "'2026-11-09')"
)
DONE = {"fby": "t", "fat": "2026-11-09"}
NOT_DONE = {"fby": None, "fat": None}
UNRELEASED = {"rby": None, "rat": None}
RELEASED = {"rby": "t", "rat": "2026-11-09"}


@pytest.mark.asyncio
@pytest.mark.parametrize("values, constraint", [
    ({"status": "graded", "tmax": 12, "tawarded": None, **NOT_DONE, **UNRELEASED}, "ck_homework_evaluations_status"),
    ({"status": "pending", "tmax": 12, "tawarded": None, **DONE, **UNRELEASED}, "ck_homework_evaluations_finalized"),
    ({"status": "marked", "tmax": 12, "tawarded": 5, **NOT_DONE, **UNRELEASED}, "ck_homework_evaluations_finalized"),
    ({"status": "marked", "tmax": 12, "tawarded": 5, "fby": None, "fat": "2026-11-09", **UNRELEASED},
     "ck_homework_evaluations_finalized_by"),
    ({"status": "marked", "tmax": 12, "tawarded": 5, **DONE, **RELEASED}, "ck_homework_evaluations_released"),
    ({"status": "released", "tmax": 12, "tawarded": 5, **DONE, **UNRELEASED}, "ck_homework_evaluations_released"),
    ({"status": "released", "tmax": 12, "tawarded": 5, **DONE, "rby": None, "rat": "2026-11-09"},
     "ck_homework_evaluations_released_by"),
    ({"status": "marked", "tmax": 12, "tawarded": None, **DONE, **UNRELEASED}, "ck_homework_evaluations_total_set"),
    ({"status": "pending", "tmax": 12, "tawarded": 3, **NOT_DONE, **UNRELEASED}, "ck_homework_evaluations_total_set"),
    ({"status": "marked", "tmax": 12, "tawarded": 13, **DONE, **UNRELEASED}, "ck_homework_evaluations_totals"),
    ({"status": "marked", "tmax": 12, "tawarded": -1, **DONE, **UNRELEASED}, "ck_homework_evaluations_totals"),
    ({"status": "pending", "tmax": -1, "tawarded": None, **NOT_DONE, **UNRELEASED}, "ck_homework_evaluations_totals"),
])
async def test_evaluation_check_constraints(db_session, values, constraint):
    with pytest.raises(IntegrityError, match=constraint):
        await db_session.execute(text(EVALUATION_INSERT), {"id": uid("raw"), "s": uid("raw-sub"), **values})
    await db_session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("values, constraint", [
    ({"pos": 0, "max": 3, "awarded": None, "mby": None, "mat": None}, "ck_homework_evaluation_items_position"),
    ({"pos": 1, "max": -1, "awarded": None, "mby": None, "mat": None}, "ck_homework_evaluation_items_max"),
    ({"pos": 1, "max": 3, "awarded": 4, "mby": "t", "mat": "2026-11-09"}, "ck_homework_evaluation_items_awarded"),
    ({"pos": 1, "max": 3, "awarded": -1, "mby": "t", "mat": "2026-11-09"}, "ck_homework_evaluation_items_awarded"),
    ({"pos": 1, "max": 3, "awarded": 2, "mby": "t", "mat": None}, "ck_homework_evaluation_items_marked_by"),
])
async def test_item_check_constraints(db_session, values, constraint):
    with pytest.raises(IntegrityError, match=constraint):
        await db_session.execute(text(ITEM_INSERT), {"id": uid("raw"), "e": uid("raw-eval"), "item": uid("raw-item"),
                                                     **values})
    await db_session.rollback()


@pytest.mark.asyncio
async def test_unique_rules(db_session):
    submission, evaluation = uid("raw-sub"), uid("raw-eval")
    base = {"status": "pending", "tmax": 6, "tawarded": None, **NOT_DONE, **UNRELEASED}
    try:
        await db_session.execute(text(EVALUATION_INSERT), {"id": evaluation, "s": submission, **base})
        await db_session.commit()
        with pytest.raises(IntegrityError, match="homework_evaluations.submission_id"):
            await db_session.execute(text(EVALUATION_INSERT), {"id": uid("raw"), "s": submission, **base})
        await db_session.rollback()

        item = {"e": evaluation, "max": 3, "awarded": None, "mby": None, "mat": None}
        await db_session.execute(text(ITEM_INSERT), {"id": uid("raw"), "item": "q1", "pos": 1, **item})
        await db_session.commit()
        with pytest.raises(IntegrityError, match="homework_evaluation_items.evaluation_id"):  # same question
            await db_session.execute(text(ITEM_INSERT), {"id": uid("raw"), "item": "q1", "pos": 2, **item})
        await db_session.rollback()
        with pytest.raises(IntegrityError, match="homework_evaluation_items.evaluation_id"):  # same position
            await db_session.execute(text(ITEM_INSERT), {"id": uid("raw"), "item": "q2", "pos": 1, **item})
        await db_session.rollback()
    finally:
        await db_session.execute(text("DELETE FROM homework_evaluation_items WHERE evaluation_id = :e"),
                                 {"e": evaluation})
        await db_session.execute(text("DELETE FROM homework_evaluations WHERE id = :e"), {"e": evaluation})
        await db_session.commit()


def test_evaluation_tables_compile_for_postgresql():
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable

    from backend.app.db.session import Base

    dialect = postgresql.dialect()
    evaluations = str(CreateTable(Base.metadata.tables["homework_evaluations"]).compile(dialect=dialect))
    items = str(CreateTable(Base.metadata.tables["homework_evaluation_items"]).compile(dialect=dialect))
    assert "UNIQUE (submission_id)" in evaluations
    assert "(status = 'pending') = (finalized_at IS NULL)" in evaluations
    assert "total_awarded <= total_max" in evaluations
    assert "UNIQUE (evaluation_id, draft_item_id)" in items and "UNIQUE (evaluation_id, position)" in items
    assert "awarded_marks <= max_marks" in items and "ON DELETE CASCADE" in items


# --- Teacher-only answer keys and rubrics ---------------------------------------------------------------

KEY_VALUES = ("SECRET-ANSWER-1", "SECRET-ANSWER-2", "SECRET-RUBRIC-1", "SECRET-RUBRIC-3")


def keys_of(evaluation_json):
    return {i["position"]: (i["correct_answer"], i["marking_rubric"]) for i in evaluation_json["items"]}


def assert_no_keys(res):
    for secret in KEY_VALUES + ("SECRET", "correct_answer", "marking_rubric"):
        assert secret not in res.text, (res.request.method, res.request.url.path, secret)


@pytest.mark.asyncio
async def test_every_teacher_grading_response_carries_the_frozen_keys(client, world, teacher_token):
    expected = {p: keys for p, keys in FROZEN_KEYS.items()}  # missing values come back as null
    responses = [await start(client, world, "a_alice", auth(teacher_token)),
                 await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token)),
                 await mark(client, world, "a_alice", ALL_MARKED, 1, auth(teacher_token)),
                 await transition(client, FINALIZE, world, "a_alice", 2, auth(teacher_token)),
                 await transition(client, RELEASE, world, "a_alice", 3, auth(teacher_token)),
                 await transition(client, RELEASE, world, "a_alice", 4, auth(teacher_token)),  # idempotent repeat
                 await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token))]
    for res in responses:
        assert res.status_code in (200, 201), res.text
        assert keys_of(res.json()) == expected
    assert keys_of(responses[0].json())[4] == (None, None)  # absent, not invented


@pytest.mark.asyncio
async def test_principal_and_admin_see_the_keys_too(client, world, principal_token, admin_token):
    assert keys_of((await start(client, world, "a_alice", auth(principal_token))).json())[1] == FROZEN_KEYS[1]
    assert keys_of((await start(client, world, "a_cara", auth(admin_token))).json())[2] == FROZEN_KEYS[2]


@pytest.mark.asyncio
async def test_keys_come_from_the_frozen_snapshot_not_the_question_bank(client, db_session, world, teacher_token):
    """The homework's question 1 came from a bank question; the bank's answer and rubric change
    afterwards. Grading still shows the values frozen when the homework was created, and the
    frozen snapshot itself is never modified."""
    from backend.app.models.entities import QuestionBankItem

    await db_session.rollback()
    source_id = (await db_session.execute(text(
        "SELECT i.source_question_id FROM homework_draft_items i JOIN homework_assignments a ON a.draft_id = "
        "i.draft_id WHERE a.id = :a AND i.position = 1"), {"a": world["a_alice"]})).scalar()
    db_session.add(QuestionBankItem(id=source_id, school_id="school-1", subject_id=world["subject"], text="Bank Q",
                                    type="mcq", options_json=["A", "B", "C"], correct_answer="BANK-ANSWER-ORIGINAL",
                                    marking_rubric="BANK-RUBRIC-ORIGINAL", marks=3, competency="LU"))
    await db_session.commit()
    try:
        await db_session.execute(text("UPDATE question_bank_items SET correct_answer = 'BANK-ANSWER-CHANGED', "
                                      "marking_rubric = 'BANK-RUBRIC-CHANGED' WHERE id = :q"), {"q": source_id})
        await db_session.commit()
        res = await start(client, world, "a_alice", auth(teacher_token))
        assert keys_of(res.json())[1] == ("SECRET-ANSWER-1", "SECRET-RUBRIC-1")
        assert "BANK-" not in res.text
        frozen = (await db_session.execute(text(
            "SELECT correct_answer, marking_rubric FROM homework_draft_items WHERE source_question_id = :q"),
            {"q": source_id})).one()
        assert tuple(frozen) == ("SECRET-ANSWER-1", "SECRET-RUBRIC-1")  # snapshot untouched
    finally:
        await db_session.execute(text("DELETE FROM question_bank_items WHERE id = :q"), {"q": source_id})
        await db_session.commit()


@pytest.mark.asyncio
async def test_student_responses_never_contain_keys(client, world, teacher_token):
    alice = bearer(world["u_alice"], "student")
    bob = bearer(world["u_bob"], "student")
    student_base = "/api/v1/students/me/homework/assignments"
    # 1. assignment detail and listing; 2. submission retrieval (submitted and in progress)
    responses = [
        await client.get(f"{student_base}/{world['a_alice']}", headers=alice),
        await client.get(student_base, headers=alice),
        await client.get(STUDENT_SUB.format(world["a_alice"]), headers=alice),
        await client.get(STUDENT_SUB.format(world["a_bob"]), headers=bob),
        await client.put(STUDENT_SUB.format(world["a_bob"]), headers=bob,
                         json={"expected_version": 1, "answers": [{"position": 1, "selected_option_index": 0}]}),
    ]
    # 3. the final-submit response
    responses.append(await client.post(STUDENT_SUB.format(world["a_bob"]) + "/submit", headers=bob,
                                       json={"expected_version": 2}))
    # 5. unreleased results: not started, pending, marked
    responses.append(await student_result(client, world))
    await start(client, world, "a_alice", auth(teacher_token))
    responses.append(await student_result(client, world))
    await mark(client, world, "a_alice", ALL_MARKED, 1, auth(teacher_token))
    await transition(client, FINALIZE, world, "a_alice", 2, auth(teacher_token))
    responses.append(await student_result(client, world))
    # 4. the released result
    await transition(client, RELEASE, world, "a_alice", 3, auth(teacher_token))
    released = await student_result(client, world)
    assert released.status_code == 200
    responses.append(released)
    # another student asking for Alice's result
    responses.append(await student_result(client, world, user="u_bob"))
    for res in responses:
        assert res.status_code in (200, 201, 404), (res.request.url.path, res.status_code)
        assert_no_keys(res)


@pytest.mark.asyncio
async def test_parents_and_unauthorized_callers_never_see_keys(client, world, teacher_token,
                                                               other_school_teacher_token, student_token, parent_token):
    await start(client, world, "a_alice", auth(teacher_token))
    callers = [bearer(world["u_teacher2"], "teacher"), auth(other_school_teacher_token), auth(student_token),
               auth(parent_token), bearer(world["u_parent"], "parent"), bearer(world["u_alice"], "student"), {}]
    for headers in callers:
        for res in await every_teacher_call(client, world, "a_alice", headers):
            assert res.status_code in (401, 403, 404), res.status_code
            assert_no_keys(res)
    # The linked parent's existing endpoint for Alice (gap analysis) has no question content.
    parent_view = await client.get(f"/api/v1/students/{world['alice']}/homework/gap-analysis",
                                   headers=bearer(world["u_parent"], "parent"))
    assert parent_view.status_code == 200
    assert_no_keys(parent_view)


@pytest.mark.asyncio
async def test_other_teacher_views_stay_key_free(client, world, teacher_token):
    """Keys are only in the grading evaluation. The queue and the Phase 3 submission views don't
    need them and don't have them."""
    await start(client, world, "a_alice", auth(teacher_token))
    views = [await client.get(QUEUE.format(world["a_alice"]), headers=auth(teacher_token)),
             await client.get(f"/api/v1/homework/assignments/{world['a_alice']}/submissions", headers=auth(teacher_token)),
             await client.get(f"/api/v1/homework/assignments/{world['a_alice']}/submissions/{world['alice']}",
                              headers=auth(teacher_token)),
             await client.get(f"/api/v1/homework/assignments/{world['a_alice']}", headers=auth(teacher_token))]
    for res in views:
        assert res.status_code == 200
        assert_no_keys(res)


@pytest.mark.asyncio
async def test_keys_never_reach_audit_errors_or_logs(client, db_session, world, teacher_token, caplog):
    await start(client, world, "a_alice", auth(teacher_token))
    errors = [
        await mark(client, world, "a_alice", [{"position": 1, "awarded_marks": 4}], 1, auth(teacher_token)),  # 422
        await mark(client, world, "a_alice", [{"position": 1, "awarded_marks": 1}], 9, auth(teacher_token)),  # 409
        await transition(client, FINALIZE, world, "a_alice", 1, auth(teacher_token)),  # 409 incomplete
        await transition(client, RELEASE, world, "a_alice", 1, auth(teacher_token)),  # 409 not finalized
    ]
    await mark(client, world, "a_alice", ALL_MARKED, 1, auth(teacher_token))
    await transition(client, FINALIZE, world, "a_alice", 2, auth(teacher_token))
    await transition(client, RELEASE, world, "a_alice", 3, auth(teacher_token))
    await eval_sql(db_session, "UPDATE homework_evaluations SET total_awarded = 11 WHERE assignment_id = :a", world)
    with caplog.at_level("DEBUG"):
        errors.append(await client.get(EVAL.format(world["a_alice"]), headers=auth(teacher_token)))  # 500
        errors.append(await student_result(client, world))  # 500
    assert [r.status_code for r in errors] == [422, 409, 409, 409, 500, 500]
    for res in errors:
        assert_no_keys(res)
    for record in caplog.records:
        for secret in KEY_VALUES:
            assert secret not in record.getMessage(), record.getMessage()
    await db_session.rollback()
    details = [r[0] for r in (await db_session.execute(text(
        "SELECT details FROM audit_events WHERE details LIKE :d"), {"d": f"%{world['a_alice']}%"})).all()]
    assert details and not any(s in d for d in details for s in KEY_VALUES + ("SECRET",))


# --- Parent access to released results -------------------------------------------------------------

PARENT_RESULT = "/api/v1/parents/me/students/{}/homework/assignments/{}/evaluation"
RESULT_NOT_FOUND = {"detail": "Result not found."}


def as_parent(w, user="u_parent"):
    return bearer(w[user], "parent")


async def parent_result(client, w, student="alice", assignment="a_alice", headers=None):
    headers = as_parent(w) if headers is None else headers  # {} means "no token", not "default"
    return await client.get(PARENT_RESULT.format(w[student], w[assignment]), headers=headers)


async def release_alice(client, w, teacher_token):
    await marked_and_finalized(client, w, auth(teacher_token))
    assert (await transition(client, RELEASE, w, "a_alice", 3, auth(teacher_token))).status_code == 200


def assert_parent_safe(res):
    assert_no_keys(res)
    for hidden in ("version", "marked_by", "marked_at", "finalized", "released_by", "created_by", "user-teacher-1",
                   "evaluation_id", '"id"', "draft_item_id", "student_id", "school_id"):
        assert hidden not in res.text, (hidden, res.text[:200])


@pytest.mark.asyncio
async def test_linked_parent_sees_exactly_the_students_released_result(client, world, teacher_token):
    await release_alice(client, world, teacher_token)
    parent = await parent_result(client, world)
    student = await student_result(client, world)
    assert parent.status_code == 200 and student.status_code == 200
    assert parent.json() == student.json()  # the same content, built by the same serializer
    assert (parent.json()["total_awarded"], parent.json()["total_max"]) == (5, 12)
    assert parent.json()["items"][2]["feedback"] == "Good reasoning; check units."
    assert_parent_safe(parent)


@pytest.mark.asyncio
async def test_unavailable_results_all_look_the_same(client, db_session, world, teacher_token):
    """Not started, pending, marked, a missing assignment, an assignment of another student, and
    an unlinked student all give the same 404, so nothing about them can be inferred."""
    responses = [await parent_result(client, world)]  # not started
    await start(client, world, "a_alice", auth(teacher_token))
    responses.append(await parent_result(client, world))  # pending
    await mark(client, world, "a_alice", ALL_MARKED, 1, auth(teacher_token))
    await transition(client, FINALIZE, world, "a_alice", 2, auth(teacher_token))
    responses.append(await parent_result(client, world))  # marked, not released
    responses.append(await client.get(PARENT_RESULT.format(world["alice"], "no-such-assignment"),
                                      headers=as_parent(world)))
    responses.append(await parent_result(client, world, assignment="a_bob"))  # Bob's assignment under Alice's ID
    responses.append(await parent_result(client, world, student="bob", assignment="a_bob"))  # not linked to Bob
    responses.append(await client.get(PARENT_RESULT.format("no-such-student", world["a_alice"]),
                                      headers=as_parent(world)))
    for res in responses:
        assert res.status_code == 404 and res.json() == RESULT_NOT_FOUND
        assert res.content == responses[0].content
        assert_parent_safe(res)
        assert "Good reasoning" not in res.text and "Bob" not in res.text


@pytest.mark.asyncio
async def test_a_parent_without_a_link_gets_nothing(client, world, teacher_token, parent_token):
    await release_alice(client, world, teacher_token)
    # The seeded parent (user-parent-1) has no link to Alice.
    res = await parent_result(client, world, headers=auth(parent_token))
    assert res.status_code == 404 and res.json() == RESULT_NOT_FOUND and "Good reasoning" not in res.text


@pytest.mark.asyncio
async def test_stale_links_fail_closed(client, db_session, world, teacher_token):
    await release_alice(client, world, teacher_token)
    assert (await parent_result(client, world)).status_code == 200

    # The account is no longer a parent: refused by role.
    await db_session.execute(text("UPDATE users SET role = 'teacher' WHERE id = :u"), {"u": world["u_parent"]})
    await db_session.commit()
    res = await parent_result(client, world)
    assert res.status_code == 403 and "Good reasoning" not in res.text
    await db_session.execute(text("UPDATE users SET role = 'parent' WHERE id = :u"), {"u": world["u_parent"]})
    await db_session.commit()

    # The link is removed: nothing.
    await db_session.execute(text("DELETE FROM parent_student_links WHERE parent_user_id = :u"),
                             {"u": world["u_parent"]})
    await db_session.commit()
    res = await parent_result(client, world)
    assert res.status_code == 404 and res.json() == RESULT_NOT_FOUND


@pytest.mark.asyncio
async def test_link_to_a_deleted_student_fails_closed(client, db_session, world, teacher_token):
    """SQLite foreign keys are off, so the link outlives the deleted Student: a stale link."""
    await release_alice(client, world, teacher_token)
    await db_session.execute(text("DELETE FROM students WHERE id = :s"), {"s": world["alice"]})
    await db_session.commit()
    res = await parent_result(client, world)
    assert res.status_code == 404 and res.json() == RESULT_NOT_FOUND and "Good reasoning" not in res.text


@pytest.mark.asyncio
async def test_parent_with_two_children_gets_only_the_requested_childs_result(client, db_session, world,
                                                                               teacher_token):
    await db_session.execute(text("INSERT INTO parent_student_links (id, parent_user_id, student_id, created_at) "
                                  "VALUES (:i, :p, :s, '2026-11-10')"),
                             {"i": uid("hev-plink"), "p": world["u_parent"], "s": world["dan"]})
    await db_session.commit()
    await release_alice(client, world, teacher_token)
    teacher2 = bearer(world["u_teacher2"], "teacher")
    await start(client, world, "a_teacher2", teacher2)
    await mark(client, world, "a_teacher2", [{"position": p, "awarded_marks": 1} for p in (1, 2, 3, 4)], 1, teacher2)
    await transition(client, FINALIZE, world, "a_teacher2", 2, teacher2)
    await transition(client, RELEASE, world, "a_teacher2", 3, teacher2)

    alice = await parent_result(client, world)
    dan = await parent_result(client, world, student="dan", assignment="a_teacher2")
    assert (alice.status_code, dan.status_code) == (200, 200)
    assert alice.json()["assignment_id"] == world["a_alice"] and alice.json()["total_awarded"] == 5
    assert dan.json()["assignment_id"] == world["a_teacher2"] and dan.json()["total_awarded"] == 4
    assert "Dan question" in dan.text and "Alice" not in dan.text
    # Mixing one child's ID with the other child's assignment gives nothing.
    for student, assignment in (("alice", "a_teacher2"), ("dan", "a_alice"), ("dan", "a_dan")):
        res = await parent_result(client, world, student=student, assignment=assignment)
        assert res.status_code == 404 and res.json() == RESULT_NOT_FOUND
    for res in (alice, dan):
        assert_parent_safe(res)


@pytest.mark.asyncio
async def test_only_parents_use_the_parent_endpoint(client, world, teacher_token, principal_token, admin_token,
                                                    student_token):
    await release_alice(client, world, teacher_token)
    for headers in (auth(teacher_token), auth(principal_token), auth(admin_token), auth(student_token),
                    bearer(world["u_alice"], "student"), {}):  # {} = no token: DEMO_MODE's admin
        res = await parent_result(client, world, headers=headers)
        assert res.status_code == (403 if headers else 401)
        assert "Good reasoning" not in res.text


@pytest.mark.asyncio
async def test_parents_cannot_change_anything(client, db_session, world, teacher_token):
    """Parents get 403 on the student submission endpoints and the teacher grading endpoints, and
    reading results writes nothing."""
    await start(client, world, "a_alice", auth(teacher_token))
    await mark(client, world, "a_alice", ALL_MARKED, 1, auth(teacher_token))
    before = await snapshot(db_session, world)
    parent = as_parent(world)
    writes = [
        await client.put(STUDENT_SUB.format(world["a_alice"]), headers=parent,
                         json={"answers": [{"position": 2, "answer_text": "parent edit"}]}),
        await client.post(STUDENT_SUB.format(world["a_alice"]) + "/submit", headers=parent, json={}),
        *await every_teacher_call(client, world, "a_alice", parent),
    ]
    for res in writes:
        assert res.status_code == 403, (res.request.method, res.request.url.path, res.status_code)
        assert_no_keys(res)
    await parent_result(client, world)
    assert await snapshot(db_session, world) == before


@pytest.mark.asyncio
async def test_parent_endpoint_in_openapi(client):
    spec = (await client.get("/api/v1/openapi.json")).json()
    path = "/api/v1/parents/me/students/{student_id}/homework/assignments/{assignment_id}/evaluation"
    assert set(spec["paths"][path]) == {"get"}
    ok = spec["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ok.endswith("/StudentResultOut")  # the same schema as the student's result
