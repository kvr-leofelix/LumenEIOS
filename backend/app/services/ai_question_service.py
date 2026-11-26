"""AI question generation: request/response schemas, prompt building and validation.

Generation is a PREVIEW. Nothing here touches the database; questions reach the bank only
when an educator explicitly approves them (see the save endpoint in api/v1/assessments.py).

Privacy: the prompt is built only from teaching parameters (subject name, grade, topic,
competency, Bloom level, type, marks, count, language, teacher instructions). No student names,
IDs, emails, scores or school identifiers are ever sent to the provider.
"""
import json
import random
from typing import ClassVar, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

import difflib
import re

from backend.app.services.ai_gateway import AIGatewayError, AIInvalidResponse, AIProvider


class AIAllDuplicates(AIInvalidResponse):
    public_message = ("The AI model only produced questions that already exist in this subject's question bank. "
                      "Try a more specific topic or add teacher instructions, then generate again.")

Competency = Literal["LU", "CU", "AU", "CT"]
Bloom = Literal["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"]
# Same vocabulary as QuestionBankItem.type. "descriptive" is the bank's long-answer type.
QuestionType = Literal["mcq", "short", "descriptive"]

COMPETENCY_DESCRIPTIONS = {
    "LU": "Language Understanding - reading and interpreting the language of the problem",
    "CU": "Concept Understanding - explaining and connecting the underlying concepts",
    "AU": "Application Understanding - applying concepts to solve real or practical problems",
    "CT": "Critical Thinking - analysing, evaluating or justifying claims and reasoning",
}
TYPE_DESCRIPTIONS = {
    "mcq": "multiple-choice with exactly 4 distinct options and one correct option",
    "short": "short answer (1-3 sentences or a short calculation)",
    "descriptive": "long answer (structured explanation, multi-step working or argument)",
}
MAX_QUESTIONS = 10


class AIQuestionRequest(BaseModel):
    subject_id: str = Field(min_length=1, max_length=64)
    grade: int = Field(ge=1, le=12)
    topic: str = Field(min_length=2, max_length=200)
    competency: Competency
    bloom_level: Bloom
    question_type: QuestionType
    marks: int = Field(ge=1, le=20)
    count: int = Field(ge=1, le=MAX_QUESTIONS)
    language: str = Field(default="English", min_length=2, max_length=40)
    instructions: Optional[str] = Field(default=None, max_length=1000)
    # Questions already on the teacher's screen (when regenerating one). Used only for the
    # duplicate check; never sent to the AI provider.
    avoid_texts: List[str] = Field(default_factory=list, max_length=20)
    # Which model writes the questions: the local Qwen model (works offline) or Gemini.
    provider: Literal["gemini", "qwen"] = "gemini"

    @field_validator("topic", "language", "instructions")
    @classmethod
    def strip(cls, value):
        return value.strip() if isinstance(value, str) else value


class _WireQuestion(BaseModel):
    """Shape requested from the model (no constraints: provider schema support varies).

    Property order matters: models fill JSON in schema order, so the worked solution
    (explanation) is written BEFORE the answer key and the options. That makes the key the result
    of solving the question instead of a guess the solution then has to justify."""
    text: str
    question_type: str
    competency: str
    bloom_level: str
    marks: int
    explanation: str
    correct_answer: str
    options: List[str]
    marking_rubric: str


class _WireResponse(BaseModel):
    ai_temperature: ClassVar[float] = 0.8  # variety in contexts and numbers; validation guards quality
    questions: List[_WireQuestion]


class AIGeneratedQuestion(BaseModel):
    """A validated question. Also the shape educators send back (possibly edited) to save."""
    text: str = Field(min_length=5, max_length=3000)
    question_type: QuestionType
    options: List[str] = Field(default_factory=list, max_length=6)
    correct_answer: str = Field(min_length=1, max_length=3000)
    marking_rubric: str = Field(min_length=1, max_length=3000)
    marks: int = Field(ge=1, le=20)
    competency: Competency
    bloom_level: Bloom
    explanation: Optional[str] = Field(default=None, max_length=3000)
    topic: Optional[str] = Field(default=None, max_length=255)  # set from the request, not by the model

    @field_validator("text", "correct_answer", "marking_rubric", "explanation")
    @classmethod
    def strip(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def check_options(self):
        if self.question_type == "mcq":
            options = [o.strip() for o in self.options]
            if len(options) != 4 or any(not o for o in options):
                raise ValueError("MCQs need exactly 4 non-empty options.")
            if len({o.lower() for o in options}) != 4:
                raise ValueError("MCQ options must be distinct.")
            answer = self.correct_answer.strip()
            # Accept a bare letter ("B" / "B)") and map it to the option text.
            letter = answer.rstrip(").:").upper()
            if answer not in options and len(letter) == 1 and "A" <= letter <= "D":
                answer = options[ord(letter) - ord("A")]
            if answer not in options:
                raise ValueError("The MCQ correct answer must be one of the options.")
            self.options, self.correct_answer = options, answer
        elif self.options:
            raise ValueError("Only MCQs can have options.")
        return self


class AIGenerationPreview(BaseModel):
    """Every question here was produced by the provider in this request (source="ai_generated").
    The preview never contains question-bank or template questions."""
    provider: str
    model: str
    source: Literal["ai_generated"]
    requested: int
    generated: int  # == len(questions)
    attempts: int  # provider requests made (1 + replacement requests)
    received: int  # questions the provider returned across all requests
    checked_against: int  # existing bank questions (same school + subject) used for the duplicate check
    rejected_duplicates: int  # matched an existing bank question
    rejected_repeats: int  # repeated another generated or already-shown question
    rejected_invalid: int  # failed validation or didn't match the requested settings
    discarded: int  # total rejected
    questions: List[AIGeneratedQuestion]
    warnings: List[str]


SYSTEM_PROMPT = (
    "You are an experienced Indian school teacher and assessment designer writing ORIGINAL questions for a "
    "teacher-reviewed question bank aligned with NCERT/CBSE and NEP 2020 competency-based learning.\n"
    "Originality: every question is newly written for this request. Do not copy or lightly reword textbook "
    "exercises, sample papers or well-known stock questions; use fresh contexts, names of objects, places "
    "and numbers.\n"
    "Accuracy first: solve every question yourself before writing its answer key. Put the full worked "
    "solution in `explanation`, then copy the final result into `correct_answer`. If you cannot solve a "
    "question with certainty, replace it with one you can.\n"
    "Multiple-choice rules: exactly one option is correct and the other three are unambiguously wrong. "
    "Each wrong option must come from a specific, common student mistake (for example a sign error, "
    "using perimeter instead of area, or a missed unit conversion); name the mistake behind each wrong "
    "option at the end of `explanation`. Keep options similar in length and form, do not use 'all of the "
    "above', 'none of the above' or 'both A and B', and never put A/B/C/D labels inside an option.\n"
    "Mathematics and science notation: write every formula, expression, fraction, power, root, Greek "
    "letter or unit with exponents in LaTeX inside \\( and \\), for example \\( \\frac{3}{4} \\), "
    "\\( x^2 + 5x + 6 = 0 \\), \\( 9.8\\,\\text{m/s}^2 \\). Use the same notation in the question, "
    "options, answer key and rubric so that options and the key match character for character.\n"
    "Level: vocabulary, sentence length and number sizes must suit the stated grade. Prefer Indian everyday "
    "contexts (rupees, metric units, local places) when a context is used.\n"
    "Rubric: split the marks into short criteria written as '<criterion> - <n> mark(s)', one per line, "
    "adding up exactly to the question's marks. For MCQs a single line is enough.\n"
    "Return only JSON matching the provided schema."
)

# What a question for each competency should make the student DO (used in the user prompt).
COMPETENCY_GUIDANCE = {
    "LU": "the question must require careful reading and interpretation of wording, a definition, a diagram "
          "description or a word problem's language before any calculation; avoid pure computation",
    "CU": "the question must require explaining or recognising WHY a concept or rule works, or connecting two "
          "ideas; avoid questions answerable by recall of a formula alone",
    "AU": "the question must require applying a concept or method to a new, realistic situation with concrete numbers",
    "CT": "the question must require evaluating a claim, finding the error in given reasoning, comparing two "
          "methods or justifying a conclusion with evidence",
}
BLOOM_GUIDANCE = {
    "Remember": "recalling or recognising facts (define, list, identify)",
    "Understand": "explaining or interpreting in their own words (explain, summarise, classify)",
    "Apply": "using a method in a given situation (calculate, solve, use)",
    "Analyze": "breaking a problem into parts or finding relationships (compare, distinguish, find the error)",
    "Evaluate": "judging against criteria and justifying the judgement (assess, justify, decide which is better)",
    "Create": "designing or producing something new (design, propose, construct)",
}

MAX_ATTEMPTS = 3  # first request + up to 2 replacement requests for rejected questions
NEAR_DUPLICATE_RATIO = 0.85


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", text.lower()).split())


def is_near_duplicate(text: str, others: List[str]) -> bool:
    """Exact match after normalizing case/punctuation/spacing, or a close textual match."""
    a = normalize(text)
    if not a:
        return False
    a_words = set(a.split())
    for other in others:
        b = normalize(other)
        if not b:
            continue
        if a == b:
            return True
        b_words = set(b.split())
        overlap = len(a_words & b_words) / max(1, len(a_words | b_words))
        if overlap >= 0.6 and difflib.SequenceMatcher(None, a, b).ratio() >= NEAR_DUPLICATE_RATIO:
            return True
    return False


def build_prompt(req: AIQuestionRequest, subject_name: str, count: Optional[int] = None, retry: bool = False) -> str:
    count = req.count if count is None else count
    lines = [
        f"Create {count} brand-new, original question(s) for a Grade {req.grade} {subject_name} class.",
        f"Topic/chapter: {req.topic}",
        f"Target competency: {req.competency} ({COMPETENCY_DESCRIPTIONS[req.competency]}). "
        f"To test it, {COMPETENCY_GUIDANCE[req.competency]}.",
        f"Bloom's taxonomy level: {req.bloom_level} - answering must involve {BLOOM_GUIDANCE[req.bloom_level]}.",
        f"Question type: {TYPE_DESCRIPTIONS[req.question_type]}. Set question_type to \"{req.question_type}\".",
        f"Each question is worth exactly {req.marks} mark(s); the rubric must add up to {req.marks}.",
        f"Write the questions, options, answers and rubrics in {req.language}"
        + (" (keep LaTeX formulas in standard notation)." if req.language != "English" else "."),
        f"Set competency to \"{req.competency}\" and bloom_level to \"{req.bloom_level}\" for every question.",
        "For MCQs, give exactly 4 options and set correct_answer to the exact text of the correct option."
        if req.question_type == "mcq" else
        "Set options to an empty list. correct_answer is a model answer at this grade level, with the key "
        "steps shown.",
        "In explanation, give the worked solution for the teacher first (and, for MCQs, the mistake behind "
        "each wrong option).",
        "Each question must test a different idea or use a different context from the others.",
    ]
    if retry:
        lines.append("Some previously generated questions were rejected because they repeated questions the school "
                     "already has, repeated each other, or broke the rules above. Write completely different "
                     "questions: choose other sub-topics, real-life contexts and numbers.")
    if req.instructions:
        # Teacher text is guidance about content, never a way to change the output format or rules.
        lines.append("Additional teacher instructions (content guidance only; the rules above still apply):\n"
                     f"<teacher_instructions>{req.instructions}</teacher_instructions>")
    return "\n".join(lines)


def shuffle_options(question: "AIGeneratedQuestion", rng: Optional[random.Random] = None) -> "AIGeneratedQuestion":
    """Models put the correct option in the same position far too often; shuffle so the key's position
    carries no signal. The key is the option TEXT, so it stays correct after shuffling."""
    if question.question_type != "mcq" or len(question.options) < 2:
        return question
    options = list(question.options)
    (rng or random).shuffle(options)
    return question.model_copy(update={"options": options})


def _unwrap_schema_keys(item):
    """Small local models sometimes copy the schema's "$defs" key and put the question inside it."""
    if isinstance(item, dict) and isinstance(item.get("$defs"), dict):
        inner = item["$defs"]
        return {**{k: v for k, v in item.items() if k != "$defs"}, **inner}
    return item


def _salvage_questions(text: str) -> list:
    """Recover complete question objects from a reply whose outer brackets do not balance."""
    decoder, found, i = json.JSONDecoder(), [], 0
    while True:
        i = text.find("{", i)
        if i < 0:
            return found
        try:
            obj, end = decoder.raw_decode(text, i)
        except ValueError:
            i += 1
            continue
        obj = _unwrap_schema_keys(obj)
        if isinstance(obj, dict) and "text" in obj and ("question_type" in obj or "correct_answer" in obj):
            found.append(obj); i = end
        else:
            i += 1


def parse_items(raw_json: str) -> list:
    # json_payload also accepts what the small local Qwen model tends to return: fenced JSON, the object nested
    # under the schema title, or copied schema fragments. Gemini's structured output parses on the first try.
    from backend.app.services.llm_service import json_payload, json_object_text, repair_latex_json
    data = None
    try:
        data = json.loads(raw_json)
        if isinstance(data, dict) and "questions" not in data:
            data = json_payload(raw_json, _WireResponse.__name__)
    except (TypeError, ValueError):
        repaired = repair_latex_json(json_object_text(raw_json or ""))
        try:
            data = json_payload(repaired, _WireResponse.__name__)
        except (TypeError, ValueError):
            data = _salvage_questions(repaired) or None
    items = data.get("questions") if isinstance(data, dict) else data if isinstance(data, list) else None
    if not isinstance(items, list):
        raise AIInvalidResponse()
    return [_unwrap_schema_keys(item) for item in items[:MAX_QUESTIONS]]


def check_question(item, req: AIQuestionRequest, existing: List[str], accepted: List[str]):
    """Return (question, None) if usable, else (None, (kind, detail))."""
    try:
        question = AIGeneratedQuestion.model_validate(item)
    except ValidationError as exc:
        return None, ("invalid", exc.errors()[0].get("msg", "invalid"))
    mismatched = [field for field, expected in (("question_type", req.question_type), ("competency", req.competency),
                                               ("bloom_level", req.bloom_level), ("marks", req.marks))
                  if getattr(question, field) != expected]
    if mismatched:
        return None, ("mismatch", ", ".join(mismatched))
    if is_near_duplicate(question.text, existing):
        return None, ("bank_duplicate", None)
    if is_near_duplicate(question.text, accepted):
        return None, ("repeat", None)
    return question, None


def validate_generated(raw_json: str, req: AIQuestionRequest, existing: Optional[List[str]] = None):
    """Validate a single provider response. Returns (valid questions, rejection reasons)."""
    valid, rejected = [], []
    for item in parse_items(raw_json):
        q, why = check_question(item, req, existing or [], [v.text for v in valid])
        if q:
            valid.append(q)
        else:
            rejected.append(why)
    return valid, rejected


def _fit_local_model_item(item, req: "AIQuestionRequest"):
    """Tidy a question from the small local Qwen model before validation. Returns (item, answer_was_added).

    - The settings the teacher chose (competency, Bloom level, marks) are echoed back by the model and often
      dropped or garbled; they are set from the request. The question type is still checked strictly.
    - Qwen frequently computes the right answer but leaves it out of its own four options. Then the answer
      replaces the last distractor (options are shuffled afterwards) and the preview warns the teacher.
    Gemini's questions are never changed this way."""
    if not isinstance(item, dict):
        return item, False
    item = {**item, "competency": req.competency, "bloom_level": req.bloom_level, "marks": req.marks}
    options, answer = item.get("options"), item.get("correct_answer")
    if item.get("question_type") != "mcq" or not isinstance(options, list) or not isinstance(answer, str) or not answer.strip():
        return item, False
    texts = [str(o).strip() for o in options if str(o).strip()]
    answer = answer.strip()
    letter = answer.rstrip(").:").upper()
    if answer.lower() in {t.lower() for t in texts} or (len(letter) == 1 and "A" <= letter <= "D" and len(texts) == 4):
        return item, False
    if len(texts) == 4:
        texts[-1] = answer
    elif len(texts) == 3:
        texts.append(answer)
    else:
        return item, False
    return {**item, "options": texts}, True


async def generate_question_preview(provider: AIProvider, req: AIQuestionRequest, subject_name: str,
                                    existing_texts: List[str]) -> AIGenerationPreview:
    """Ask the provider for NEW questions. Every returned question comes from the provider during
    this call; nothing is ever taken from the bank or a template. Questions that duplicate the
    school's bank, each other, or `req.avoid_texts` are rejected and replacements are requested
    from the provider, up to MAX_ATTEMPTS requests in total."""
    accepted: List[AIGeneratedQuestion] = []
    counts = {"invalid": 0, "mismatch": 0, "bank_duplicate": 0, "repeat": 0}
    details: List[str] = []
    attempts = received = unreadable = 0
    local_model = getattr(provider, "name", "") == "qwen"
    answers_added: List[int] = []  # positions (1-based) where Qwen's answer had to be added to its options
    while len(accepted) < req.count and attempts < MAX_ATTEMPTS:
        needed = req.count - len(accepted)
        attempts += 1
        try:
            raw = await provider.generate_json(system=SYSTEM_PROMPT, schema=_WireResponse,
                                               prompt=build_prompt(req, subject_name, needed, retry=attempts > 1))
            items = parse_items(raw)
        except AIInvalidResponse:
            # An unreadable reply (e.g. the small local model echoing the schema) is one failed attempt: ask again.
            unreadable += 1
            continue
        except AIGatewayError:
            if not accepted:
                raise  # nothing generated: report the failure, never substitute other questions
            details.append(f"Replacement request {attempts - 1} failed; showing the questions generated so far.")
            break
        received += len(items)
        if not items:
            break  # the provider returned nothing; repeating the same request is unlikely to help
        for item in items[:needed]:
            added = False
            if local_model:
                item, added = _fit_local_model_item(item, req)
            q, why = check_question(item, req, existing_texts, [a.text for a in accepted] + list(req.avoid_texts))
            if q:
                accepted.append(shuffle_options(q).model_copy(update={"topic": req.topic}))
                if added:
                    answers_added.append(len(accepted))
            else:
                counts[why[0]] += 1
                if why[0] == "invalid":
                    details.append(f"Rejected a question that failed validation: {why[1]}.")
                elif why[0] == "mismatch":
                    details.append(f"Rejected a question that did not match the requested {why[1]}.")
    if not accepted:
        if counts["bank_duplicate"] or counts["repeat"]:
            raise AIAllDuplicates()
        failure = AIInvalidResponse()
        if local_model:
            failure.public_message = (f"Qwen did not produce a usable question in {attempts} attempt(s). Try again, "
                                      "make the topic more specific, or choose Gemini.")
        raise failure
    warnings = []
    model_label = "Qwen" if getattr(provider, "name", "") == "qwen" else "Gemini"
    duplicates = counts["bank_duplicate"] + counts["repeat"]
    if len(accepted) < req.count:
        reasons = [f"{n} {label}" for n, label in ((counts["bank_duplicate"], "duplicated existing question-bank questions"),
                                                   (counts["repeat"], "repeated another generated question"),
                                                   (counts["invalid"], "failed validation"),
                                                   (counts["mismatch"], "did not match the requested settings")) if n]
        warnings.append(f"{model_label} produced {len(accepted)} of {req.count} requested valid, new questions after "
                        f"{attempts} request(s). " + (f"Rejected: {'; '.join(reasons)}." if reasons
                                                       else "The AI returned fewer questions than requested."))
    elif duplicates:
        warnings.append(f"{duplicates} duplicate question(s) were rejected and replaced with new ones from {model_label}.")
    if unreadable:
        warnings.append(f"{unreadable} {model_label} repl{'y' if unreadable == 1 else 'ies'} could not be read and "
                        f"{'was' if unreadable == 1 else 'were'} requested again.")
    if answers_added:
        listed = ", ".join(str(n) for n in answers_added)
        warnings.append(f"Check question(s) {listed}: Qwen left its own answer out of the options, so the answer was "
                        "added as one of the four options. Confirm the answer and the other options before saving.")
    return AIGenerationPreview(
        provider=provider.name, model=provider.model, source="ai_generated", requested=req.count,
        generated=len(accepted), attempts=attempts, received=received, checked_against=len(existing_texts),
        rejected_duplicates=counts["bank_duplicate"], rejected_repeats=counts["repeat"],
        rejected_invalid=counts["invalid"] + counts["mismatch"], discarded=sum(counts.values()),
        questions=accepted, warnings=warnings + details,
    )


class AIQuestionSaveRequest(BaseModel):
    """Educator-approved (and possibly edited) AI questions to add to the bank."""
    subject_id: str = Field(min_length=1, max_length=64)
    questions: List[AIGeneratedQuestion] = Field(min_length=1, max_length=20)
    model: Optional[str] = Field(default=None, max_length=100)
    topic: Optional[str] = Field(default=None, max_length=255)
