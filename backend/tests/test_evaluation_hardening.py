"""Deterministic checks applied to every scan-evaluator result (MCQ key match, blanks, copied template text)."""
from backend.app.schemas.evaluation import EvaluationResult
from backend.app.services.evaluation_service import harden_evaluation, mcq_choice_is_key, split_numbered_answers

QUESTIONS = [
    {"id": "1", "max_marks": 1, "competency": "LU", "options": ["burning of paper", "melting of ice", "tearing of paper", "dissolving sugar"],
     "correct_answer": "burning of paper"},
    {"id": "2", "max_marks": 2, "competency": "CU", "options": [], "correct_answer": "No new substance forms in a physical change."},
    {"id": "3", "max_marks": 2, "competency": "AU", "options": [], "correct_answer": "Chemical."},
]


def model_output(**overrides):
    items = [
        {"question_index": 1, "question_id": "1", "question_text": "q1", "competency": "LU", "max_marks": 1,
         "awarded_marks": 1, "competency_score": 100, "feedback": "Correct volume and liter conversion; final calculation step for time was omitted."},
        {"question_index": 2, "question_id": "2", "question_text": "q2", "competency": "CU", "max_marks": 2,
         "awarded_marks": 2, "competency_score": 100, "feedback": "Clear explanation."},
        {"question_index": 3, "question_id": "3", "question_text": "q3", "competency": "AU", "max_marks": 2,
         "awarded_marks": 2, "competency_score": 100, "feedback": "Good."},
    ]
    return EvaluationResult.model_validate({
        "question_evaluations": items,
        "scoring_summary": {"total_marks_obtained": 5, "max_possible_marks": 5, "percentage": 100,
                            "overall_feedback": "Strong conceptual and formula grasp. Needs focus on complete multi-step problem execution."},
        **overrides,
    })


def test_split_numbered_answers_handles_common_labels_and_continuations():
    text = "Q1. dissolving sugar\nQ2. In a physical change no new\nsubstance forms\nAns 3: chemical"
    assert split_numbered_answers(text) == {1: "dissolving sugar", 2: "In a physical change no new substance forms", 3: "chemical"}


def test_wrong_mcq_choice_gets_zero_whatever_the_model_said():
    result = harden_evaluation(model_output(), QUESTIONS, "Q1. dissolving sugar\nQ2. no new substance\nQ3. chemical")
    q1 = result.question_evaluations[0]
    assert q1.awarded_marks == 0 and "burning of paper" in q1.feedback
    assert result.scoring_summary.total_marks_obtained == 4
    assert result.scoring_summary.competency_scores.LU == 0


def test_right_mcq_choice_and_option_letter_are_recognised():
    assert mcq_choice_is_key("burning of paper", QUESTIONS[0]["options"], "burning of paper") is True
    assert mcq_choice_is_key("(a)", QUESTIONS[0]["options"], "burning of paper") is True
    assert mcq_choice_is_key("b", QUESTIONS[0]["options"], "burning of paper") is False
    assert mcq_choice_is_key("I think something", QUESTIONS[0]["options"], "burning of paper") is None


def test_blank_answers_are_unattempted_and_template_text_is_removed():
    result = harden_evaluation(model_output(), QUESTIONS, "Q1. burning of paper\nQ2. no new substance forms")
    q3 = result.question_evaluations[2]
    assert q3.status == "unattempted" and q3.awarded_marks == 0
    assert result.scoring_summary.overall_feedback == ""
    assert all("liter conversion" not in i.feedback for i in result.question_evaluations)
    assert result.scoring_summary.total_marks_obtained == 3


def test_praise_is_replaced_when_the_key_check_lowers_a_generous_mark():
    questions = [*QUESTIONS[:2], {"id": "3", "max_marks": 2, "competency": "AU", "options": [],
                                  "correct_answer": "Chemical: the egg white changes permanently and cannot be reversed."}]
    result = harden_evaluation(model_output(), questions, "Q1. burning of paper\nQ2. no new substance forms\nQ3. Chemical")
    q3 = result.question_evaluations[2]
    assert q3.awarded_marks < 2 and q3.flag_for_review
    assert q3.feedback.startswith("Partly correct") and "cannot be reversed" in q3.feedback


ANIKA_TEXT = ("Q1. dissolving sugar\n"
              "Q2. In a physical change no new substance forms and it is often reversible; a chemical change forms new\nsubstances.\n"
              "Q3. Chemical: the egg white changes permanently from clear liqui [unclear]\n"
              "Q4. Physical: the same substance separates as crystals; no new substance forms.")
WORKSHEET = [
    {"id": "1", "max_marks": 1, "competency": "LU", "options": ["burning of paper", "melting of ice", "tearing of paper", "dissolving sugar"],
     "correct_answer": "burning of paper"},
    {"id": "2", "max_marks": 2, "competency": "CU", "options": [],
     "correct_answer": "In a physical change no new substance forms and it is often reversible; a chemical change forms new substances."},
    {"id": "3", "max_marks": 2, "competency": "AU", "options": [],
     "correct_answer": "Chemical: the egg white changes permanently from clear liquid to white solid; it cannot be reversed."},
    {"id": "4", "max_marks": 2, "competency": "CT", "options": [],
     "correct_answer": "Physical: the same substance separates as crystals; no new substance forms."},
]


def test_answers_the_model_says_are_missing_are_marked_from_the_key():
    """Regression: Qwen reported Q2-Q4 'not attempted' although the transcript had (correct) answers."""
    missed = lambda n, m: {"question_index": n, "question_id": str(n), "question_text": f"q{n}", "competency": "CU",
                           "max_marks": m, "awarded_marks": 0, "competency_score": 0, "status": "unattempted",
                           "feedback": "The student did not attempt this question."}
    raw = EvaluationResult.model_validate({
        "question_evaluations": [missed(1, 1), missed(2, 2), missed(3, 2), missed(4, 2)],
        "scoring_summary": {"total_marks_obtained": 0, "max_possible_marks": 7, "percentage": 0,
                            "overall_feedback": "The student did not attempt any questions."},
    })
    result = harden_evaluation(raw, WORKSHEET, ANIKA_TEXT)
    q1, q2, q3, q4 = result.question_evaluations
    assert q1.awarded_marks == 0                       # wrong MCQ option stays wrong
    assert q2.awarded_marks == 2 and q4.awarded_marks == 2
    assert 1 <= q3.awarded_marks < 2                   # partly legible answer: partial credit, flagged
    assert all(q.status == "attempted" and "did not attempt" not in q.feedback for q in (q2, q3, q4))
    assert q3.flag_for_review and "answer key" in q3.flag_reason
    assert "did not attempt" not in result.scoring_summary.overall_feedback
    assert result.scoring_summary.total_marks_obtained >= 5


def test_prompt_lists_each_answer_next_to_its_question():
    from backend.app.services.evaluation_service import build_evaluation_messages
    _system, user = build_evaluation_messages("Science", "Worksheet", "7", WORKSHEET, ANIKA_TEXT)
    assert 'Q2 (question_id 2): "In a physical change' in user
    assert 'Q4 (question_id 4): "Physical: the same substance' in user
    _system, user = build_evaluation_messages("Science", "Worksheet", "7", WORKSHEET, "Q1. burning of paper")
    assert "Q3 (question_id 3): [no answer written]" in user


def test_overall_comment_claiming_everything_correct_is_rebuilt_when_marks_were_lost():
    item = lambda n, m, a: {"question_index": n, "question_id": str(n), "question_text": f"q{n}", "competency": "CU",
                            "max_marks": m, "awarded_marks": a, "competency_score": 100 * a / m, "feedback": "ok"}
    raw = EvaluationResult.model_validate({
        "question_evaluations": [item(1, 1, 1), item(2, 2, 2), item(3, 2, 1), item(4, 2, 1)],
        "scoring_summary": {"total_marks_obtained": 5, "max_possible_marks": 7, "percentage": 71,
                            "overall_feedback": "Strong understanding. Each question was answered correctly with clear explanations."},
    })
    result = harden_evaluation(raw, WORKSHEET, ANIKA_TEXT.replace("dissolving sugar", "burning of paper"))
    fb = result.scoring_summary.overall_feedback
    assert "answered correctly" not in fb and "Revise Q" in fb
