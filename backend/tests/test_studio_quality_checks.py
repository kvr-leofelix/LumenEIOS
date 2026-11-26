"""AI Question Studio: no repeated questions, and MCQ keys are checked against the source."""
from backend.app.services.llm_service import QwenQuestionStudioService, is_near_duplicate

CHEM_WRONG = {"type": "mcq", "text": "What is the result of a chemical change?",
              "options": ["No new substances are formed.", "New substances are formed.", "Only the shape changes.", "Nothing changes."],
              "correct_answer": "No new substances are formed.", "marking_rubric": "", "competency": "CU"}
CHEM_RIGHT = {**CHEM_WRONG, "text": "Which statement describes a chemical change?", "correct_answer": "New substances are formed."}
PHYS = {"type": "mcq", "text": "Which is a physical change?", "options": ["Melting of ice", "Burning of paper", "Rusting of iron", "Cooking an egg"],
        "correct_answer": "Melting of ice", "marking_rubric": "", "competency": "LU"}


def service(batches, verdict_letters):
    svc = QwenQuestionStudioService.__new__(QwenQuestionStudioService)
    calls = {"batch": 0}
    def batch(*args, **kwargs):
        calls["batch"] += 1
        calls.setdefault("facts", []).append(kwargs.get("focus_fact"))
        return [dict(batches.pop(0))]
    svc._generate_question_batch = batch
    svc._generate_text = lambda prompt, **kw: verdict_letters.pop(0)
    return svc, calls


def test_near_duplicates_are_detected():
    assert is_near_duplicate("What is the difference between a physical and a chemical change?",
                             "What is the difference between a physical and chemical change?")
    assert not is_near_duplicate("Which is a physical change?", "How can rusting be prevented?")


def test_wrong_key_is_regenerated():
    svc, calls = service([CHEM_WRONG, CHEM_RIGHT], ["B", "B"])
    out = svc._generate_checked("Science", 1, 0, "Apply", None, "source", 0, [])
    assert out[0]["correct_answer"] == "New substances are formed." and calls["batch"] == 2
    assert "Check the answer key" not in out[0]["marking_rubric"]


SOURCE = ("A physical change alters the shape, size or state of a substance. "
          "A chemical change produces one or more new substances. "
          "Rusting can be prevented by painting, oiling or galvanising iron.")


def test_repeat_is_regenerated_from_a_different_part_of_the_source():
    svc, calls = service([PHYS, CHEM_RIGHT], ["B"])
    svc._used_facts = set()
    out = svc._generate_checked("Science", 1, 0, "Apply", None, SOURCE, 0, [dict(PHYS)])
    assert out[0]["text"] == CHEM_RIGHT["text"]
    assert calls["facts"][0] and calls["facts"][1] and calls["facts"][0] != calls["facts"][1]


def test_disputed_key_after_all_attempts_is_flagged_for_the_teacher():
    svc, _ = service([CHEM_WRONG, {**CHEM_WRONG, "text": "Result of chemical change?"}, {**CHEM_WRONG, "text": "Chemical change gives?"}],
                     ["B", "B", "B"])
    out = svc._generate_checked("Science", 1, 0, "Apply", None, "source", 0, [])
    assert out[0]["marking_rubric"].startswith("Check the answer key")


def test_unclear_check_does_not_block():
    svc, calls = service([PHYS], ["I think it is melting"])
    assert svc._generate_checked("Science", 1, 0, "Apply", None, "source", 0, [])[0]["text"] == PHYS["text"]
    assert calls["batch"] == 1


def test_one_malformed_attempt_does_not_fail_the_paper():
    svc = QwenQuestionStudioService.__new__(QwenQuestionStudioService)
    outputs = [ValueError("Qwen returned an MCQ without four options."), dict(PHYS)]
    def batch(*a, **k):
        item = outputs.pop(0)
        if isinstance(item, Exception):
            raise item
        return [item]
    svc._generate_question_batch = batch
    svc._generate_text = lambda prompt, **kw: "A"
    svc._used_facts = set()
    assert svc._generate_checked("Science", 1, 0, "Apply", None, SOURCE, 0, [])[0]["text"] == PHYS["text"]
