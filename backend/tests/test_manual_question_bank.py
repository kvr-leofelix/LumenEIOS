"""Teacher-written question-bank items and the MCQ answer-key guarantees used by Differentiated Homework."""
import pytest

from backend.app.services.llm_service import coerce_mcq_answer_and_options, normalize_mcq_answer

BANK = "/api/v1/assessments/question-bank"


def headers(token):
    return {"Authorization": f"Bearer {token}", "X-School-Id": "school-1"}


def mcq(**overrides):
    body = {
        "subject_id": "sub-math", "type": "mcq", "text": r"Solve \( 2x + 3 = 7 \).",
        "options": [r"\( x = 1 \)", r"\( x = 2 \)", r"\( x = 3 \)", r"\( x = 4 \)"],
        "correct_answer": r"\( x = 2 \)", "marking_rubric": "Subtract 3, divide by 2.",
        "marks": 2, "competency": "AU", "bloom_level": "Apply",
    }
    return {**body, **overrides}


@pytest.mark.asyncio
async def test_teacher_writes_edits_and_deletes_a_question(client, teacher_token):
    created = await client.post(BANK, headers=headers(teacher_token), json=mcq())
    assert created.status_code == 201, created.text
    question = created.json()
    assert question["is_ai_generated"] is False
    assert question["correct_answer"] == r"\( x = 2 \)"
    try:
        listed = await client.get(f"{BANK}?subject_id=sub-math", headers=headers(teacher_token))
        assert any(row["id"] == question["id"] for row in listed.json())

        edited = await client.put(
            f"/api/v1/assessments/questions/{question['id']}", headers=headers(teacher_token),
            json={"options": ["1", "2", "3"], "correct_answer": "3"},
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["options"] == ["1", "2", "3"]
        assert edited.json()["correct_answer"] == "3"

        # An edit that leaves the key pointing at no option is refused.
        orphan = await client.put(
            f"/api/v1/assessments/questions/{question['id']}", headers=headers(teacher_token),
            json={"options": ["5", "6", "7"]},
        )
        assert orphan.status_code == 422
    finally:
        deleted = await client.delete(f"/api/v1/assessments/questions/{question['id']}", headers=headers(teacher_token))
        assert deleted.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", [
    {"correct_answer": "x = 9"},                       # key matches no option
    {"options": ["same", "Same", "other"], "correct_answer": "same"},  # duplicate options
    {"options": ["only one"], "correct_answer": "only one"},
    {"text": "   "},
    {"marks": 0},
    {"competency": "XX"},
    {"bloom_level": "Memorise"},
    {"type": "essay"},
])
async def test_invalid_questions_are_rejected(client, teacher_token, overrides):
    response = await client.post(BANK, headers=headers(teacher_token), json=mcq(**overrides))
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_written_questions_need_no_options(client, teacher_token):
    response = await client.post(BANK, headers=headers(teacher_token), json=mcq(
        type="short", options=["ignored"], correct_answer="x = 2", text="Explain how to solve 2x + 3 = 7.",
    ))
    assert response.status_code == 201, response.text
    assert response.json()["options"] == []
    await client.delete(f"/api/v1/assessments/questions/{response.json()['id']}", headers=headers(teacher_token))


@pytest.mark.asyncio
async def test_learners_cannot_write_to_the_bank(client, student_token):
    response = await client.post(BANK, headers=headers(student_token), json=mcq())
    assert response.status_code == 403


def test_short_answer_key_does_not_match_a_longer_option():
    # "2" used to be keyed to the first option containing it ("12"), marking the wrong option correct.
    options = ["12", "2x", "20", "2"]
    assert normalize_mcq_answer("2", options) == "2"
    assert normalize_mcq_answer("x", ["12", "2x", "20", "2"]) == "2x"
    ambiguous = ["x = 12", "x = 21", "y = 3", "y = 4"]
    assert normalize_mcq_answer("x =", ambiguous) == "x ="  # ambiguous: left for the repair step


def test_latex_options_keep_exactly_one_key():
    options = [r"\( \frac{1}{2} \)", r"\( \frac{1}{3} \)", r"\( \frac{2}{3} \)", r"\( \frac{3}{4} \)"]
    answer, repaired = coerce_mcq_answer_and_options(r"\( \frac{2}{3} \)", options)
    assert answer == options[2] and repaired == options
    assert sum(option == answer for option in repaired) == 1
