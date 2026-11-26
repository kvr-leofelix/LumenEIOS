import json

import pytest

from backend.app.services.llm_service import (
    build_studio_prompt,
    parse_studio_questions,
    stamp_competency,
)


def test_studio_parser_keeps_requested_types_and_rejects_bad_counts():
    raw = """```json
    {"mcqs":[
      {"type":"mcq","text":"Which is correct?","options":["A","B","C","D"],"correct_answer":"A","marking_rubric":"Choose A","competency":"CU"}
    ],"theory":[
      {"type":"descriptive","text":"Explain the idea.","correct_answer":"Because...","marking_rubric":"Reasoning","competency":"CT"}
    ]}
    ```"""
    questions = parse_studio_questions(raw, mcq_count=1, theory_count=1)

    assert [question["type"] for question in questions] == ["mcq", "descriptive"]
    assert [question["marks"] for question in questions] == [2, 5]
    with pytest.raises(ValueError, match="unexpected number"):
        parse_studio_questions(raw, mcq_count=2, theory_count=1)
    with pytest.raises(ValueError, match="invalid theory"):
        parse_studio_questions(raw.replace('"descriptive"', '"mcq"'), mcq_count=1, theory_count=1)


def test_studio_parser_ignores_unrequested_sections():
    raw = json.dumps({
        "mcqs": [{
            "type": "mcq", "text": "Pick one?",
            "options": ["A", "B", "C", "D"], "correct_answer": "A",
            "marking_rubric": "A", "competency": "CU",
        }],
        "theory": [{
            "type": "short", "text": "Explain.", "correct_answer": "Because",
            "marking_rubric": "Reason", "competency": "CT",
        }],
    })
    questions = parse_studio_questions(raw, mcq_count=1, theory_count=0)
    assert len(questions) == 1 and questions[0]["type"] == "mcq"


def test_studio_parser_trims_extra_questions_and_answer_punctuation():
    raw = json.dumps({"mcqs": [
        {
            "type": "mcq", "text": "Pick one?",
            "options": ["One", "Two", "Three", "Four"],
            "correct_answer": "Two.", "marking_rubric": "Two", "competency": "CU",
        },
        {
            "type": "mcq", "text": "Extra?",
            "options": ["W", "X", "Y", "Z"],
            "correct_answer": "X", "marking_rubric": "X", "competency": "AU",
        },
    ], "theory": []})
    questions = parse_studio_questions(raw, mcq_count=1, theory_count=0)
    assert len(questions) == 1
    assert questions[0]["correct_answer"] == "Two"


def test_studio_parser_repairs_answer_missing_from_options():
    raw = json.dumps({"mcqs": [{
        "type": "mcq", "text": "What do stomach muscles do?",
        "options": [
            "Help contract and relax.",
            "Produce digestive juices.",
            "Absorb nutrients.",
            "Secrete saliva.",
        ],
        "correct_answer": "Help churn the food.",
        "marking_rubric": "Churning mixes food.",
        "competency": "AU",
    }], "theory": []})
    question = parse_studio_questions(raw, mcq_count=1, theory_count=0)[0]
    assert question["correct_answer"] == "Help churn the food."
    assert question["correct_answer"] in question["options"]
    assert len(question["options"]) == 4


def test_studio_parser_normalizes_common_qwen_option_shapes():
    as_dict = json.dumps({"mcqs": [{
        "type": "mcq", "text": "Pick one.",
        "options": {"A": "One", "B": "Two", "C": "Three", "D": "Four"},
        "correct_answer": "B", "marking_rubric": "Two is right", "competency": "CU",
    }], "theory": []})
    questions = parse_studio_questions(as_dict, mcq_count=1, theory_count=0)
    assert questions[0]["options"] == ["One", "Two", "Three", "Four"]
    assert questions[0]["correct_answer"] == "Two"

    as_labeled = json.dumps({"mcqs": [{
        "type": "mcq", "text": "Pick one.",
        "options": "a) Red\nb) Blue\nc) Green\nd) Yellow",
        "correct_answer": "c)", "marking_rubric": "Green", "competency": "LU",
    }], "theory": []})
    questions = parse_studio_questions(as_labeled, mcq_count=1, theory_count=0)
    assert questions[0]["options"] == ["Red", "Blue", "Green", "Yellow"]
    assert questions[0]["correct_answer"] == "Green"

    as_objects = json.dumps({"mcqs": [{
        "type": "mcq", "text": "Pick one.",
        "options": [{"text": "W"}, {"text": "X"}, {"text": "Y"}, {"text": "Z"}],
        "correct_answer": "Y", "marking_rubric": "Y", "competency": "AU",
    }], "theory": []})
    questions = parse_studio_questions(as_objects, mcq_count=1, theory_count=0)
    assert questions[0]["options"] == ["W", "X", "Y", "Z"]
    assert questions[0]["correct_answer"] == "Y"


def test_studio_parser_repairs_malformed_qwen_json():
    trailing = """Here is the question:
    {"mcqs":[{"type":"mcq","text":"Which is half?","options":["1","2","3","4"],"correct_answer":"1","marking_rubric":"Half of two.","competency":"CU",}],"theory":[],}
    Hope that helps."""
    assert parse_studio_questions(trailing, mcq_count=1, theory_count=0)[0]["text"] == "Which is half?"

    latex = json.dumps({"mcqs": [{
        "type": "mcq", "text": "placeholder",
        "options": ["1", "2", "3", "4"], "correct_answer": "1",
        "marking_rubric": "half", "competency": "CU",
    }], "theory": []}).replace("placeholder", r"What is \frac{1}{2}?")
    assert r"\frac{1}{2}" in parse_studio_questions(latex, mcq_count=1, theory_count=0)[0]["text"]

    broken_line = (
        '{"mcqs":[{"type":"mcq","text":"Line one\nLine two","options":["A","B","C","D"],'
        '"correct_answer":"A","marking_rubric":"A","competency":"LU"}]'
    )
    assert "Line one" in parse_studio_questions(broken_line, mcq_count=1, theory_count=0)[0]["text"]

    bare = json.dumps({
        "type": "short", "text": "Why?", "correct_answer": "Because.",
        "marking_rubric": "Reason", "competency": "CT",
    })
    assert parse_studio_questions(bare, mcq_count=0, theory_count=1)[0]["type"] == "short"

    with pytest.raises(ValueError, match="invalid question JSON"):
        parse_studio_questions("no json here", mcq_count=1, theory_count=0)


def test_studio_prompt_assigns_each_competency_and_the_recommended_answer():
    prompt = build_studio_prompt("Science", 2, 2, "Analyze", "friction", "chapter context")
    for phrase in (
        "LU: Language Understanding",
        "CU: Conceptual Understanding",
        "AU: Application",
        "CT: Critical Thinking",
        "recommended answer",
    ):
        assert phrase in prompt
    assert prompt.index("MCQ 1 must test LU") < prompt.index("MCQ 2 must test CU")
    assert "Theory 1 must test AU" in prompt
    assert "Theory 2 must test CT" in prompt


def test_stamp_keeps_the_mcq_option_and_labels_the_theory_answer():
    mcq = {"type": "mcq", "competency": "LU", "correct_answer": "A", "marking_rubric": "Choose A"}
    stamp_competency(mcq)
    assert mcq["correct_answer"] == "A"
    assert mcq["marking_rubric"].startswith("LU: Language Understanding")

    theory = {"type": "descriptive", "competency": "CT", "correct_answer": "Because", "marking_rubric": "Reason"}
    stamp_competency(theory)
    assert "Recommended answer focus — CT" in theory["correct_answer"]
    assert theory["marking_rubric"].startswith("CT: Critical Thinking")


@pytest.mark.asyncio
async def test_studio_progress_stream_reports_completion():
    from backend.app.services.progress import report_progress, stream_job

    async def work():
        report_progress("write", "Wrote question 1 of 1", 1, 1)
        return {"generated_count": 1}

    response = stream_job(work)
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    streamed = [
        json.loads(line[6:])
        for line in "".join(chunks).split("\n")
        if line.startswith("data: ")
    ]
    assert streamed[0]["kind"] == "progress"
    assert streamed[0]["done"] == 1 and streamed[0]["total"] == 1
    assert streamed[1] == {"kind": "complete", "result": {"generated_count": 1}}
