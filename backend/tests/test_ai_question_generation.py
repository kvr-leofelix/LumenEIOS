"""AI (Gemini) question generation. Gemini is always mocked: no network calls are made.

  POST /api/v1/assessments/ai/generate-questions   preview only, never saves
  POST /api/v1/assessments/ai/questions            educator-approved save into the bank

Several tests guard against the preview ever returning existing question-bank or template
questions instead of newly generated ones.
"""
import asyncio
import json
import types as pytypes

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import select, text

from backend.app.core.config import settings
from backend.app.models.entities import QuestionBankItem
from backend.app.services import ai_gateway
from backend.app.services.ai_question_service import (
    AIGeneratedQuestion,
    AIQuestionRequest,
    build_prompt,
    is_near_duplicate,
    validate_generated,
)
from backend.app.services.llm_service import llm_service

GENERATE = "/api/v1/assessments/ai/generate-questions"
SAVE = "/api/v1/assessments/ai/questions"
MARKER = "AI-TEST-QUESTION"
REQUEST = {"subject_id": "sub-math", "grade": 8, "topic": "Mensuration", "competency": "AU", "bloom_level": "Apply",
           "question_type": "mcq", "marks": 2, "count": 2, "language": "English", "instructions": "Use rupees."}
# Distinct synthetic stems, so the near-duplicate check treats them as different questions.
STEMS = [
    "a rectangular garden is 4 m by 3 m; how much fencing tape covers its area?",
    "a cricket pitch roller has radius 0.5 m; what area does one full turn flatten?",
    "a school water bottle holds 750 ml; how many fill a 6 litre cooler?",
    "rice sacks of 25 kg each are stacked in a godown; what is the load of 18 sacks?",
    "a classroom notice board is 120 cm by 90 cm; what paper area covers it?",
    "a rangoli square has side 60 cm; what is the length of its border?",
    "tiles of 30 cm side pave a 3 m verandah; how many tiles are needed per row?",
    "a cuboid lunch box is 20 by 12 by 6 cm; what is its capacity?",
    "a circular well has diameter 2.8 m; what is the area of its opening?",
    "a bus covers 45 km in 50 minutes; what is its speed in km per hour?",
]


def mcq(i, **overrides):
    q = {"text": f"{MARKER} {STEMS[i % len(STEMS)]}", "question_type": "mcq",
         "options": ["7 m²", "12 m²", "14 m²", "24 m²"], "correct_answer": "12 m²",
         "marking_rubric": "2m for 12 m².", "marks": 2, "competency": "AU", "bloom_level": "Apply",
         "explanation": "Area = l × b."}
    q.update(overrides)
    return q


class FakeProvider:
    """Returns the queued payloads in order (the last one repeats); records every prompt."""
    name, model = "gemini", "fake-model"

    def __init__(self, *payloads, error=None):
        self.payloads, self.error, self.calls = list(payloads), error, []

    async def generate_json(self, *, system, prompt, schema):
        self.calls.append(system + "\n" + prompt)
        if self.error:
            raise self.error
        payload = self.payloads[min(len(self.calls), len(self.payloads)) - 1]
        return payload if isinstance(payload, str) else json.dumps(payload)


def use(monkeypatch, fake):
    monkeypatch.setattr(ai_gateway, "get_ai_provider", lambda: fake)
    return fake


@pytest.fixture
def provider(monkeypatch):
    return use(monkeypatch, FakeProvider({"questions": [mcq(0), mcq(1)]}))


@pytest.fixture
def no_template_fallback(monkeypatch):
    """Fail loudly if the AI preview ever reaches the deterministic/template generator."""
    async def forbidden(*args, **kwargs):
        raise AssertionError("AI preview must never use the template generator")
    monkeypatch.setattr(llm_service, "generate_questions_from_sources", forbidden)
    monkeypatch.setattr(llm_service, "regenerate_single_question", forbidden)


@pytest_asyncio.fixture
async def cleanup(db_session):
    yield
    await db_session.execute(text("DELETE FROM question_bank_items WHERE text LIKE :m"), {"m": f"%{MARKER}%"})
    await db_session.commit()


async def bank_snapshot(db_session, subject="sub-math"):
    rows = await db_session.execute(select(QuestionBankItem.id, QuestionBankItem.text, QuestionBankItem.correct_answer,
                                           QuestionBankItem.marking_rubric).filter(
        QuestionBankItem.school_id == "school-1", QuestionBankItem.subject_id == subject).order_by(QuestionBankItem.id))
    return [tuple(r) for r in rows.all()]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# --- validation -------------------------------------------------------------------------

def test_mcq_validation_maps_letters_and_rejects_bad_options():
    assert AIGeneratedQuestion.model_validate(mcq(1, correct_answer="B")).correct_answer == "12 m²"
    for bad in (mcq(1, correct_answer="15 m²"), mcq(1, options=["a", "b", "c"]), mcq(1, options=["a", "a", "b", "c"]),
                mcq(1, competency="XX"), mcq(1, bloom_level="Memorise"), mcq(1, marks=0),
                mcq(1, question_type="short"), mcq(1, text="")):
        with pytest.raises(ValueError):
            AIGeneratedQuestion.model_validate(bad)


def test_response_validation_keeps_only_matching_new_questions():
    req = AIQuestionRequest(**REQUEST)
    existing = ["What is the AREA of a rectangular garden 4 m by 3 m?"]
    raw = json.dumps({"questions": [mcq(1), mcq(2, competency="CT"), mcq(3, correct_answer="nope"), mcq(1), {"text": "x"},
                                    mcq(4, text="what is the area of a rectangular garden, 4 m by 3 m")]})
    valid, rejected = validate_generated(raw, req, existing)
    assert [q.text for q in valid] == [mcq(1)["text"]]
    assert sorted(kind for kind, _ in rejected) == ["bank_duplicate", "invalid", "invalid", "mismatch", "repeat"]
    with pytest.raises(ai_gateway.AIInvalidResponse):
        validate_generated("not json {", req)


def test_near_duplicate_detection():
    assert is_near_duplicate("Find the volume of a cuboid 4 m x 3 m x 2 m.", ["find the VOLUME of a cuboid, 4 m × 3 m × 2 m"])
    assert is_near_duplicate("Find the volume of a cuboid of 4 m by 3 m by 2 m", ["Find the volume of a cuboid 4 m by 3 m by 2 m."])
    assert not is_near_duplicate("Find the volume of a cylinder of radius 7 cm and height 10 cm.",
                                 ["Find the volume of a cuboid 4 m by 3 m by 2 m."])


def test_prompt_asks_for_original_questions_and_contains_only_teaching_parameters():
    prompt = build_prompt(AIQuestionRequest(**REQUEST), "Mathematics")
    for expected in ("brand-new, original", "Grade 8 Mathematics", "Mensuration", "AU", "Apply", "exactly 2 mark",
                     "English", "Use rupees."):
        assert expected in prompt
    for private in ("student", "school-1", "user-", "@"):
        assert private not in prompt.lower()
    assert "rejected" in build_prompt(AIQuestionRequest(**REQUEST), "Mathematics", 1, retry=True)


# --- Gemini provider (SDK mocked) ------------------------------------------------------------

def test_provider_requires_key_and_uses_configured_model(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", SecretStr(""))
    with pytest.raises(ai_gateway.AINotConfigured):
        ai_gateway.get_ai_provider()
    monkeypatch.setattr(settings, "GEMINI_API_KEY", SecretStr("test-key-not-real"))
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-test-model")
    provider = ai_gateway.get_ai_provider()  # builds a client; makes no request
    assert provider.model == "gemini-test-model"
    assert "test-key-not-real" not in repr(settings)


@pytest.mark.asyncio
async def test_provider_requests_json_and_maps_failures():
    seen = {}

    async def ok(model, contents, config):
        seen.update(model=model, mime=config.response_mime_type, schema=config.response_json_schema)
        return pytypes.SimpleNamespace(text='{"questions": []}')

    async def slow(model, contents, config):
        await asyncio.sleep(5)

    async def boom(model, contents, config):
        raise RuntimeError("secret detail")

    def client(fn):
        return pytypes.SimpleNamespace(aio=pytypes.SimpleNamespace(models=pytypes.SimpleNamespace(generate_content=fn)))

    from backend.app.services.ai_question_service import _WireResponse
    p = ai_gateway.GeminiProvider("k", "m1", 0.05, client=client(ok))
    assert await p.generate_json(system="s", prompt="p", schema=_WireResponse) == '{"questions": []}'
    assert seen["model"] == "m1"
    assert seen["mime"] == "application/json"
    assert "questions" in seen["schema"]["properties"]
    with pytest.raises(ai_gateway.AIProviderTimeout):
        await ai_gateway.GeminiProvider("k", "m1", 0.05, client=client(slow)).generate_json(system="s", prompt="p", schema=_WireResponse)
    with pytest.raises(ai_gateway.AIProviderError) as info:
        await ai_gateway.GeminiProvider("k", "m1", 0.05, client=client(boom)).generate_json(system="s", prompt="p", schema=_WireResponse)
    assert "secret detail" not in str(info.value)


@pytest.mark.asyncio
async def test_provider_retries_only_transient_api_errors(monkeypatch):
    from google.genai import errors
    from backend.app.services.ai_question_service import _WireResponse

    monkeypatch.setattr(ai_gateway.GeminiProvider, "RETRY_DELAYS", (0.0, 0.0))
    calls = {"n": 0}

    def provider(codes):
        async def fn(model, contents, config):
            i = calls["n"]; calls["n"] += 1
            if i < len(codes):
                raise errors.APIError(codes[i], {"error": {"message": "secret detail", "status": "X"}})
            return pytypes.SimpleNamespace(text='{"questions": []}')
        return ai_gateway.GeminiProvider("k", "m1", 5, client=pytypes.SimpleNamespace(
            aio=pytypes.SimpleNamespace(models=pytypes.SimpleNamespace(generate_content=fn))))

    # one 503 then success -> succeeds on the 2nd attempt
    assert await provider([503]).generate_json(system="s", prompt="p", schema=_WireResponse) == '{"questions": []}'
    assert calls["n"] == 2
    # persistent 503 -> gives up after 3 attempts with a clear overload error
    calls["n"] = 0
    with pytest.raises(ai_gateway.AIProviderBusy) as info:
        await provider([503, 503, 503, 503]).generate_json(system="s", prompt="p", schema=_WireResponse)
    assert calls["n"] == 3 and "secret detail" not in str(info.value)
    # a non-transient error (400) is not retried
    calls["n"] = 0
    with pytest.raises(ai_gateway.AIProviderError):
        await provider([400, 400]).generate_json(system="s", prompt="p", schema=_WireResponse)
    assert calls["n"] == 1


# --- preview endpoint: new questions only, never the bank --------------------------------------

@pytest.mark.asyncio
async def test_seven_question_preview_comes_only_from_the_provider(client, db_session, teacher_token, monkeypatch,
                                                                    no_template_fallback):
    before = await bank_snapshot(db_session)
    bank_texts = [t for _, t, _, _ in before]
    assert bank_texts, "the test database should have sub-math bank questions"
    fake = use(monkeypatch, FakeProvider({"questions": [mcq(i) for i in range(7)]}))
    res = await client.post(GENERATE, json=dict(REQUEST, count=7), headers=auth(teacher_token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(fake.calls) == 1  # the provider was really invoked
    assert body["source"] == "ai_generated" and (body["requested"], body["generated"]) == (7, 7)
    assert [q["text"] for q in body["questions"]] == [mcq(i)["text"] for i in range(7)]  # exactly the provider's output
    assert not any(is_near_duplicate(q["text"], bank_texts) for q in body["questions"])
    assert body["checked_against"] == len(bank_texts)
    assert await bank_snapshot(db_session) == before  # preview saved and modified nothing
    for bank_text in bank_texts:
        assert bank_text not in fake.calls[0]  # bank questions are never sent as examples


@pytest.mark.asyncio
async def test_bank_duplicates_are_rejected_and_replaced_by_the_provider(client, db_session, teacher_token,
                                                                       monkeypatch, no_template_fallback):
    bank_text = (await bank_snapshot(db_session))[0][1]
    near_copy = mcq(0, text=bank_text.upper().replace("?", "") + " ")  # same question, different case/punctuation
    fake = use(monkeypatch, FakeProvider({"questions": [near_copy, mcq(1)]}, {"questions": [mcq(2)]}))
    res = await client.post(GENERATE, json=REQUEST, headers=auth(teacher_token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(fake.calls) == 2 and "rejected" in fake.calls[1] and bank_text not in fake.calls[1]
    assert [q["text"] for q in body["questions"]] == [mcq(1)["text"], mcq(2)["text"]]
    assert (body["generated"], body["attempts"], body["rejected_duplicates"]) == (2, 2, 1)
    assert any("replaced with new ones" in w for w in body["warnings"])


@pytest.mark.asyncio
async def test_shortfall_is_reported_and_never_filled_from_the_bank(client, db_session, teacher_token, monkeypatch,
                                                                  no_template_fallback):
    bank_text = (await bank_snapshot(db_session))[0][1]
    dup = mcq(0, text=bank_text)
    fake = use(monkeypatch, FakeProvider({"questions": [mcq(1), dup, dup]}, {"questions": [dup, dup]}))
    before = await bank_snapshot(db_session)
    res = await client.post(GENERATE, json=dict(REQUEST, count=3), headers=auth(teacher_token))
    body = res.json()
    assert res.status_code == 200 and len(fake.calls) == 3  # first request + 2 replacement requests
    assert [q["text"] for q in body["questions"]] == [mcq(1)["text"]]
    assert (body["requested"], body["generated"], body["rejected_duplicates"]) == (3, 1, 6)
    assert any("1 of 3 requested" in w and "duplicated existing question-bank" in w for w in body["warnings"])
    assert await bank_snapshot(db_session) == before


@pytest.mark.asyncio
async def test_only_duplicates_or_provider_failure_gives_an_error_not_bank_questions(
        client, db_session, teacher_token, monkeypatch, no_template_fallback):
    bank_text = (await bank_snapshot(db_session))[0][1]
    use(monkeypatch, FakeProvider({"questions": [mcq(0, text=bank_text)]}))
    res = await client.post(GENERATE, json=REQUEST, headers=auth(teacher_token))
    assert res.status_code == 502 and "already exist" in res.json()["detail"] and "questions" not in res.json()
    for error, code in ((ai_gateway.AINotConfigured(), 503), (ai_gateway.AIProviderTimeout(), 504),
                        (ai_gateway.AIProviderError(), 502)):
        use(monkeypatch, FakeProvider(error=error))
        res = await client.post(GENERATE, json=REQUEST, headers=auth(teacher_token))
        assert res.status_code == code and res.json() == {"detail": error.public_message}
    use(monkeypatch, FakeProvider("{not json"))
    assert (await client.post(GENERATE, json=REQUEST, headers=auth(teacher_token))).status_code == 502
    assert (await client.post(GENERATE, json=dict(REQUEST, count=50, competency="ZZ"),
                              headers=auth(teacher_token))).status_code == 422


@pytest.mark.asyncio
async def test_regenerating_one_avoids_questions_already_on_screen(client, teacher_token, monkeypatch):
    fake = use(monkeypatch, FakeProvider({"questions": [mcq(1)]}, {"questions": [mcq(2)]}))
    res = await client.post(GENERATE, json=dict(REQUEST, count=1, avoid_texts=[mcq(1)["text"]]), headers=auth(teacher_token))
    assert res.status_code == 200 and [q["text"] for q in res.json()["questions"]] == [mcq(2)["text"]]
    assert mcq(1)["text"] not in fake.calls[0]  # on-screen questions are not sent to the provider


@pytest.mark.asyncio
async def test_generation_is_educator_only(client, student_token, parent_token, provider):
    assert (await client.post(GENERATE, json=REQUEST)).status_code == 401
    for token in (student_token, parent_token):
        assert (await client.post(GENERATE, json=REQUEST, headers=auth(token))).status_code == 403
        assert (await client.post(SAVE, json={"subject_id": "sub-math", "questions": [mcq(1)]}, headers=auth(token))).status_code == 403
    assert provider.calls == []


# --- explicit approval / save ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_teacher_saves_edited_approved_questions(client, teacher_token, cleanup):
    edited = mcq(1, text=f"{MARKER} edited by teacher about a tiled floor", correct_answer="C", marking_rubric="2m edited")
    res = await client.post(SAVE, json={"subject_id": "sub-math", "questions": [edited], "model": "fake-model"},
                            headers=auth(teacher_token))
    assert res.status_code == 201, res.text
    saved = res.json()["questions"][0]
    assert saved["is_ai_generated"] is True and saved["correct_answer"] == "14 m²"
    bank = (await client.get("/api/v1/assessments/question-bank?subject_id=sub-math", headers=auth(teacher_token))).json()
    assert any(q["id"] == saved["id"] and q["is_ai_generated"] for q in bank)
    invalid = {"subject_id": "sub-math", "questions": [mcq(2, correct_answer="not an option")]}
    assert (await client.post(SAVE, json=invalid, headers=auth(teacher_token))).status_code == 422


@pytest.mark.asyncio
async def test_teacher_can_choose_the_local_qwen_model(client, db_session, teacher_token, monkeypatch, no_template_fallback):
    """provider='qwen' uses the local Qwen model (works offline) and never calls Gemini; Qwen's fenced reply is accepted."""
    def gemini_forbidden():
        raise AssertionError("Gemini must not be used when Qwen is chosen")
    monkeypatch.setattr(ai_gateway, "get_ai_provider", gemini_forbidden)
    qwen = FakeProvider("```json\n" + json.dumps({"questions": [mcq(0), mcq(1)]}) + "\n```")
    qwen.name, qwen.model = "qwen", "Qwen/Qwen2.5-VL-3B-Instruct-AWQ"
    monkeypatch.setattr(ai_gateway, "QwenTextProvider", lambda: qwen)
    res = await client.post(GENERATE, json=dict(REQUEST, provider="qwen"), headers=auth(teacher_token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(qwen.calls) == 1 and (body["provider"], body["model"]) == ("qwen", qwen.model)
    assert [q["text"] for q in body["questions"]] == [mcq(0)["text"], mcq(1)["text"]]


@pytest.mark.asyncio
async def test_unavailable_qwen_is_reported_and_unknown_models_are_refused(client, teacher_token, monkeypatch):
    monkeypatch.setattr(ai_gateway, "QwenTextProvider", lambda: FakeProvider(error=ai_gateway.QwenUnavailable()))
    res = await client.post(GENERATE, json=dict(REQUEST, provider="qwen"), headers=auth(teacher_token))
    assert res.status_code == 503 and "Qwen is not available" in res.json()["detail"]
    assert (await client.post(GENERATE, json=dict(REQUEST, provider="gpt"), headers=auth(teacher_token))).status_code == 422


# --- Gemini overload and the local Qwen model's real-world replies -----------------------------

class _ApiError(Exception):
    def __init__(self, code):
        self.code = code


@pytest.mark.asyncio
async def test_gemini_overload_is_retried_then_reported_clearly(monkeypatch):
    from google.genai import errors
    monkeypatch.setattr(errors, "APIError", _ApiError)
    monkeypatch.setattr(ai_gateway.GeminiProvider, "RETRY_DELAYS", (0.0, 0.0))
    from backend.app.services.ai_question_service import _WireResponse

    def client(codes):
        calls = []

        async def gen(model, contents, config):
            calls.append(1)
            code = codes[min(len(calls), len(codes)) - 1]
            if code:
                raise _ApiError(code)
            return pytypes.SimpleNamespace(text='{"questions": []}')
        return pytypes.SimpleNamespace(aio=pytypes.SimpleNamespace(models=pytypes.SimpleNamespace(generate_content=gen))), calls

    c, calls = client([503, None])  # one overload, then success
    assert await ai_gateway.GeminiProvider("k", "m", 5, client=c).generate_json(system="s", prompt="p", schema=_WireResponse) == '{"questions": []}'
    assert len(calls) == 2
    c, calls = client([503])  # still overloaded after the retries
    with pytest.raises(ai_gateway.AIProviderBusy) as info:
        await ai_gateway.GeminiProvider("k", "m", 5, client=c).generate_json(system="s", prompt="p", schema=_WireResponse)
    assert len(calls) == 3 and "Qwen" in info.value.public_message
    c, calls = client([400])  # a real error is not retried
    with pytest.raises(ai_gateway.AIProviderError) as info:
        await ai_gateway.GeminiProvider("k", "m", 5, client=c).generate_json(system="s", prompt="p", schema=_WireResponse)
    assert len(calls) == 1 and not isinstance(info.value, ai_gateway.AIProviderBusy)


# Shapes the local Qwen 3B model actually returned (shortened): the schema's "$defs" key wrapped around each
# question, LaTeX with single backslashes, unbalanced brackets, and the answer missing from its own options.
QWEN_DEFS_LATEX = r'''```json
{
  "questions": [
    {
    "$defs": {
      "text": "A school has 100 students in 4 equally filled buses. How many students ride in each bus?",
      "question_type": "mcq", "competency": "AU", "bloom_level": "Apply", "marks": 2,
      "explanation": "We calculate \( \frac{100}{4} = 25 \).",
      "correct_answer": "25", "options": ["10", "20", "30", "40"],
      "marking_rubric": "Correct - 2 mark(s)"
    }
  },
  {
    "$defs": {
      "text": "A farmer packs 150 apples, 10 in each box. How many boxes does he need?",
      "question_type": "mcq", "competency": "AU", "bloom_level": "Apply", "marks": 2,
      "explanation": "We calculate \( \frac{150}{10} = 15 \).",
      "correct_answer": "15", "options": ["10", "15", "30", "40"],
      "marking_rubric": "Correct - 2 mark(s)"
    }
  }
]
}
```'''
QWEN_UNBALANCED = '''```json
{"questions": [
  {"$defs": {"text": "A class of 36 forms teams of 4. How many teams are there?", "question_type": "mcq",
             "correct_answer": "9", "options": ["6", "8", "9", "12"], "marking_rubric": "2 marks for 9",
             "explanation": "36 / 4 = 9"}, "marks": 2}
}
```'''


@pytest.mark.asyncio
async def test_qwen_replies_with_defs_latex_and_missing_answers_become_usable_questions(
        client, teacher_token, monkeypatch, no_template_fallback):
    qwen = FakeProvider(QWEN_DEFS_LATEX)
    qwen.name, qwen.model = "qwen", "Qwen/Qwen2.5-VL-3B-Instruct-AWQ"
    monkeypatch.setattr(ai_gateway, "QwenTextProvider", lambda: qwen)
    body = dict(REQUEST, provider="qwen", topic="Data Handling")
    res = await client.post(GENERATE, json=body, headers=auth(teacher_token))
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["generated"] == 2 and len(qwen.calls) == 1
    first, second = out["questions"]
    assert "25" in first["options"] and first["correct_answer"] == "25"  # Qwen's answer was added to its options
    assert second["correct_answer"] == "15" and sorted(second["options"]) == ["10", "15", "30", "40"]  # untouched
    assert r"\frac{100}{4}" in first["explanation"]  # LaTeX survived the JSON repair
    assert any("Check question(s) 1" in w for w in out["warnings"])


def test_qwen_reply_with_unbalanced_brackets_is_salvaged():
    from backend.app.services.ai_question_service import parse_items
    items = parse_items(QWEN_UNBALANCED)
    assert [i["text"] for i in items] == ["A class of 36 forms teams of 4. How many teams are there?"]
    assert items[0]["correct_answer"] == "9" and items[0]["marks"] == 2


def test_qwen_prompt_schema_has_no_defs_to_copy():
    from backend.app.services.ai_question_service import _WireResponse
    schema = ai_gateway._inline_schema_refs(ai_gateway._gemini_json_schema(_WireResponse))
    text_schema = json.dumps(schema)
    assert "$defs" not in text_schema and "$ref" not in text_schema
    assert "text" in schema["properties"]["questions"]["items"]["properties"]


@pytest.mark.asyncio
async def test_an_unreadable_reply_is_asked_again_instead_of_failing(client, teacher_token, monkeypatch, no_template_fallback):
    """Qwen's first reply sometimes echoes the JSON schema; that is one failed attempt, not the end of the request."""
    echoed_schema = json.dumps({"properties": {"questions": {"type": "array"}}, "type": "object", "title": "_WireResponse"})
    qwen = FakeProvider(echoed_schema, QWEN_DEFS_LATEX)
    qwen.name, qwen.model = "qwen", "Qwen/Qwen2.5-VL-3B-Instruct-AWQ"
    monkeypatch.setattr(ai_gateway, "QwenTextProvider", lambda: qwen)
    res = await client.post(GENERATE, json=dict(REQUEST, provider="qwen"), headers=auth(teacher_token))
    assert res.status_code == 200, res.text
    assert res.json()["generated"] == 2 and len(qwen.calls) == 2
    assert any("could not be read and was requested again" in w for w in res.json()["warnings"])

    always_bad = FakeProvider(echoed_schema)
    always_bad.name, always_bad.model = "qwen", "m"
    monkeypatch.setattr(ai_gateway, "QwenTextProvider", lambda: always_bad)
    res = await client.post(GENERATE, json=dict(REQUEST, provider="qwen"), headers=auth(teacher_token))
    assert res.status_code == 502 and "choose Gemini" in res.json()["detail"]
