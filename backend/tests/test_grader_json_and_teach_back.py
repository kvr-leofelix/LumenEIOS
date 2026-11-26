"""Qwen graders: fenced JSON is accepted; Teach-Back feedback does not contradict the rubric."""
from backend.app.modules.learnsphere.schemas import TeachBackFeedback
from backend.app.schemas.assessment_learning import WrittenMark
from backend.app.services.llm_service import json_object_text, sanity_check_teach_back

RUBRIC = "Plants use sunlight, water and carbon dioxide to make glucose (food) and release oxygen; happens in chlorophyll-containing leaves."


def test_fenced_json_is_accepted():
    raw = '```json\n{"score": 2, "correct": true, "explanation": "Both parts.", "feedback": "Well explained."}\n```'
    assert WrittenMark.model_validate_json(json_object_text(raw)).score == 2
    assert json_object_text('Here you go: {"a": 1} thanks') == '{"a": 1}'


def test_true_statements_are_not_misconceptions_and_written_concepts_are_not_missing():
    response = ("Plants make their own food in their green leaves. Chlorophyll traps sunlight and the plant uses water "
                "and carbon dioxide to make glucose, and gives out oxygen.")
    fb = TeachBackFeedback(correctly_understood=[], missing_concepts=["chlorophyll"],
                           misconceptions=["Plants make their own food in their green leaves.", "Plants eat soil to get food."],
                           strengths=[], next_step="Keep going.")
    fb = sanity_check_teach_back(fb, RUBRIC, response)
    assert fb.misconceptions == ["Plants eat soil to get food."]
    assert "Plants make their own food in their green leaves." in fb.correctly_understood
    assert fb.missing_concepts == []


def test_partial_explanation_gets_the_uncovered_rubric_points_as_missing():
    fb = TeachBackFeedback(correctly_understood=["Plants use sunlight to make food"], missing_concepts=[], misconceptions=[],
                           strengths=[], next_step="Add more detail.")
    fb = sanity_check_teach_back(fb, RUBRIC, "Plants use sunlight to make food.")
    text = " ".join(fb.missing_concepts)
    assert "water" in text and "oxygen" in text and "chlorophyll" in text
    assert not any("sunlight" == m for m in fb.missing_concepts)


def test_teach_back_lists_come_from_per_point_judgements_and_cannot_contradict():
    from backend.app.services.llm_service import rubric_points, teach_back_feedback
    rubric = ("Land heats up faster than water; warm air over the land rises; cooler air from over the sea moves in "
              "to take its place; at night the direction reverses (land breeze).")
    response = ("In the day the land gets hot faster than the sea water. The hot air over the land rises. Cooler air "
                "from the sea comes in. At night the wind blows from land to sea.")
    points = rubric_points(rubric)
    assert len(points) == 4
    data = {"covered": [True, True, True, True],
            "misconceptions": ["The student incorrectly stated that the wind blows from land to sea at night.",
                               "Plants eat soil"],
            "strengths": [], "next_step": ""}
    fb = teach_back_feedback(points, data["covered"], data, response, rubric, TeachBackFeedback)
    assert fb.missing_concepts == [] and len(fb.correctly_understood) == 4
    assert fb.misconceptions == []   # restates the rubric / was never written by the student
    assert not set(fb.correctly_understood) & set(fb.missing_concepts)


def test_reply_nested_under_the_schema_title_is_unwrapped():
    from backend.app.services.llm_service import json_payload
    raw = '```json\n{"StageClassification": {"questions": [{"position": 0, "mappings": []}]}}\n```'
    assert json_payload(raw, "StageClassification") == {"questions": [{"position": 0, "mappings": []}]}
    assert json_payload('{"covered": [true]}') == {"covered": [True]}
    assert json_payload('{"answer": {"x": 1}}', "Other") == {"answer": {"x": 1}}  # a real field is never unwrapped


def test_echoed_schema_definitions_become_null():
    from backend.app.schemas.assessment_learning import QuestionGuidance
    from backend.app.services.llm_service import json_payload
    raw = ('```json\n{"expected_concept": {"anyOf": [{"maxLength": 2000, "type": "string"}, {"type": "null"}], '
           '"default": null, "title": "Expected Concept"}, "misunderstanding": {"anyOf": [{"type": "string"}, {"type": "null"}], '
           '"title": "Misunderstanding"}, "explanation": "Acids turn blue litmus red.", "activity": "Test lemon juice with litmus."}\n```')
    guidance = QuestionGuidance.model_validate(json_payload(raw, "QuestionGuidance"))
    assert guidance.expected_concept is None and guidance.misunderstanding is None
    assert guidance.explanation.startswith("Acids")
    # genuine nested values are untouched
    assert json_payload('{"mapping": {"stage": "Bodh", "reasoning": "explains"}}') == {"mapping": {"stage": "Bodh", "reasoning": "explains"}}


def test_mark_allocations_in_one_sentence_are_separate_rubric_points():
    from backend.app.services.llm_service import rubric_points
    assert rubric_points("1 mark for understanding the concept of neutralization, 1 mark for explaining how an antacid "
                         "works to relieve acidity.") == [
        "1 mark for understanding the concept of neutralization",
        "1 mark for explaining how an antacid works to relieve acidity"]
    assert rubric_points("2 marks for the formula and 1 mark for the answer") == ["2 marks for the formula", "1 mark for the answer"]
    assert rubric_points("Explain neutralisation, with an example") == ["Explain neutralisation, with an example"]


import pytest  # noqa: E402


@pytest.mark.asyncio
async def test_teach_back_feedback_survives_a_miscounted_judgement(monkeypatch):
    """Qwen judged two ideas in a one-sentence rubric and the count check failed twice, so the student only ever saw
    'malformed teach-back feedback'. A persistent miscount now uses the judgements in order instead of failing."""
    import json
    from backend.app.services.llm_service import QwenQuestionStudioService
    service = QwenQuestionStudioService()
    calls = []

    def fake_generate(prompt, max_new_tokens, output_schema):
        calls.append(prompt)
        return json.dumps({"covered": [True, True, False], "misconceptions": [], "strengths": ["clear"], "next_step": "Add an example."})
    monkeypatch.setattr(service, "_generate_text", fake_generate)
    monkeypatch.setattr(service, "_statement_is_false", lambda statement, concept: False)
    feedback = await service.evaluate_teach_back(
        "Neutralization", "1 mark for understanding the concept of neutralization, 1 mark for explaining how an antacid works.",
        "An antacid is a base that reacts with stomach acid to form salt and water, which neutralises it.")
    assert len(calls) == 2  # asked once more before accepting the miscount
    assert len(feedback.correctly_understood) == 2 and feedback.missing_concepts == []
