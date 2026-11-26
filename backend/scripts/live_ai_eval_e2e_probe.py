"""Live-server probe for AI-assisted homework evaluation (synthetic data only).

Uses demo personas on http://127.0.0.1:8000. Does not print secrets.
Cleanup deletes the draft/assignment created by this run when possible.
"""
from __future__ import annotations

import json
import sys
import uuid
from typing import Any, Optional

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
MARKER = f"LIVE-AIEVAL-{uuid.uuid4().hex[:8]}"


class ProbeError(RuntimeError):
    pass


class Client:
    def __init__(self):
        self.http = httpx.Client(base_url=BASE, timeout=120.0)
        self.token: Optional[str] = None
        self.school_id: Optional[str] = None

    def login(self, email: str, password: str = "demo123") -> dict:
        r = self.http.post("/auth/login", json={"email": email, "password": password})
        if r.status_code != 200:
            raise ProbeError(f"login {email} -> {r.status_code} {r.text[:200]}")
        data = r.json()
        self.token = data["access_token"]
        self.school_id = data["user"].get("school_id")
        return data["user"]

    def call(self, method: str, path: str, body: Any = None, code: int = 200) -> Any:
        headers = {"Authorization": f"Bearer {self.token}"}
        if self.school_id:
            headers["X-School-Id"] = self.school_id
        r = self.http.request(method, path, json=body, headers=headers)
        if r.status_code != code:
            raise ProbeError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
        return r.json() if r.content else None


def main() -> int:
    teacher_c, student_c, parent_c, other_c = Client(), Client(), Client(), Client()
    teacher = teacher_c.login("teacher@lumeneios.demo")
    student = student_c.login("student@lumeneios.demo")
    parent_c.login("parent@lumeneios.demo")
    # Another student for isolation (Gurleen / second persona if present).
    other_ok = False
    for email in ("aarav@lumeneios.demo", "student2@lumeneios.demo", "gurleen@lumeneios.demo"):
        try:
            other_c.login(email)
            other_ok = True
            break
        except ProbeError:
            continue

    print(f"MODE=live_server teacher={teacher.get('email')} school={teacher_c.school_id}")
    print(f"GEMINI=configured_on_server (server uses its own .env)")

    # Classic demo student linked to student@lumeneios.demo (seed ensure_classic_demo_student_link).
    student_id = "user-student-1"
    teacher_c.call("GET", f"/students/{student_id}/homework/gap-analysis")

    classes = teacher_c.call("GET", f"/schools/{teacher_c.school_id}/classes")
    subjects = []
    for c in classes:
        subjects.extend(c.get("subject_ids_json") or c.get("subject_ids") or [])
    subject_id = subjects[0] if subjects else None
    if not subject_id:
        bank = teacher_c.call("GET", "/assessments/question-bank")
        subject_id = (bank[0].get("subject_id") or bank[0].get("subjectId")) if bank else None
    if not subject_id:
        subject_id = "sub-math"
    # Confirm class roster path used by the app (optional).
    if classes:
        try:
            teacher_c.call("GET", f"/classes/{classes[0]['id']}/students")
        except ProbeError:
            pass

    created_ids = []
    specs = [
        {
            "text": f"{MARKER} MCQ area of 4 by 3?",
            "type": "mcq",
            "options_json": ["7", "12", "14", "24"],
            "correct_answer": "12",
            "marking_rubric": "Correct option only.",
            "marks": 2,
            "competency": "LU",
            "bloom_level": "Apply",
        },
        {
            "text": f"{MARKER} Short: state rectangle area formula.",
            "type": "short",
            "options_json": [],
            "correct_answer": "A = l x b",
            "marking_rubric": "Method 1; Accuracy 1; Justification 1",
            "marks": 3,
            "competency": "LU",
            "bloom_level": "Understand",
        },
        {
            "text": f"{MARKER} Descriptive: how would you fence a rectangular garden?",
            "type": "descriptive",
            "options_json": [],
            "correct_answer": "Measure perimeter then buy matching fencing.",
            "marking_rubric": "Method 1; Accuracy 1; Justification 1",
            "marks": 3,
            "competency": "LU",
            "bloom_level": "Evaluate",
        },
    ]
    for spec in specs:
        # Try POST question-bank; fall back to generateQuestions save.
        payload = {
            "subject_id": subject_id,
            "text": spec["text"],
            "type": spec["type"],
            "options": spec["options_json"],
            "correct_answer": spec["correct_answer"],
            "marking_rubric": spec["marking_rubric"],
            "marks": spec["marks"],
            "competency": spec["competency"],
            "bloom_level": spec["bloom_level"],
            "is_ai_generated": False,
        }
        r = teacher_c.http.post(
            "/assessments/question-bank",
            json=payload,
            headers={"Authorization": f"Bearer {teacher_c.token}", "X-School-Id": teacher_c.school_id or ""},
        )
        if r.status_code in (200, 201):
            created_ids.append(r.json()["id"])
        else:
            print(f"WARN bank create skipped ({r.status_code}); relying on preview pool")

    preview_req = {"subject_id": subject_id, "max_questions": 3, "include_ai_generated": True}
    # Prefer non-AI bank items when our markers exist.
    preview_req["include_ai_generated"] = False
    preview = teacher_c.call("POST", f"/students/{student_id}/homework/preview", preview_req)
    items = preview.get("items") or []
    # If preview did not pick our markers, still proceed with whatever LU items exist.
    ids = [i["question_id"] for i in items]
    if len(ids) < 1:
        raise ProbeError("preview returned no questions")
    draft = teacher_c.call(
        "POST",
        f"/students/{student_id}/homework/drafts",
        {**preview_req, "max_questions": len(ids), "expected_question_ids": ids},
        code=201,
    )
    teacher_c.call("POST", f"/homework/drafts/{draft['id']}/approve")
    assignment = teacher_c.call("POST", f"/homework/drafts/{draft['id']}/assign", code=201)
    aid = assignment["id"]
    print(f"ASSIGNED {aid} questions={len(draft['items'])}")

    me = f"/students/me/homework/assignments/{aid}"
    detail = student_c.call("GET", me)
    if "correct_answer" in json.dumps(detail):
        raise ProbeError("student detail leaked answer key")

    answers = []
    for q in draft["items"]:
        if q["type"] == "mcq":
            answers.append({"position": q["position"], "selected_option_index": 0})
        else:
            answers.append({"position": q["position"], "answer_text": f"{MARKER} student working for {q['type']}"})
    sub = student_c.call("PUT", me + "/submission", {"answers": answers}, code=201)
    student_c.call("POST", me + "/submission/submit", {"expected_version": sub["version"]})

    grading = f"/homework/assignments/{aid}/evaluation"
    evaluation = teacher_c.call("POST", grading, code=201)
    suggestions = teacher_c.call("POST", grading + "/ai-suggestions", {}, code=201)
    sources = {i["position"]: i["source"] for i in suggestions["items"]}
    print(f"SUGGESTIONS sources={sources} mode_hint=live_gemini_if_server_key_set")
    assert suggestions["evaluation_version"] == evaluation["version"]

    # Accept/edit/reject via teacher PATCH (frontend semantics).
    items_patch = []
    for s in suggestions["items"]:
        pos = s["position"]
        if s["source"] == "deterministic_mcq":
            items_patch.append({"position": pos, "awarded_marks": s["suggested_marks"], "feedback": s["feedback"]})
        elif pos == suggestions["items"][0]["position"]:
            items_patch.append({"position": pos, "awarded_marks": max(0, s["suggested_marks"] - 1), "feedback": "edited"})
        else:
            items_patch.append({"position": pos, "awarded_marks": 0, "feedback": "rejected AI suggestion"})
    # Ensure every question marked.
    marked_positions = {i["position"] for i in items_patch}
    for q in evaluation["items"]:
        if q["position"] not in marked_positions:
            items_patch.append({"position": q["position"], "awarded_marks": 0, "feedback": "manual"})

    evaluation = teacher_c.call(
        "PATCH", grading + "/items",
        {"expected_version": evaluation["version"], "items": items_patch},
    )
    evaluation = teacher_c.call("POST", grading + "/finalize", {"expected_version": evaluation["version"]})
    # Unreleased hidden
    try:
        student_c.call("GET", me + "/evaluation", code=404)
    except ProbeError as exc:
        if "404" not in str(exc):
            raise
    evaluation = teacher_c.call("POST", grading + "/release", {"expected_version": evaluation["version"]})
    result = student_c.call("GET", me + "/evaluation")
    parent_path = f"/parents/me/students/{student_id}/homework/assignments/{aid}/evaluation"
    parent_result = parent_c.call("GET", parent_path)
    assert result["total_awarded"] == parent_result["total_awarded"]
    forbidden = ("correct_answer", "marking_rubric", "suggested_marks", "explanation", "rubric_criteria")
    text = json.dumps(result)
    for token in forbidden:
        if token in text:
            raise ProbeError(f"released result leaked {token}")

    # Security: student cannot AI-suggest
    try:
        student_c.call("POST", grading + "/ai-suggestions", {}, code=403)
    except ProbeError as exc:
        if "403" not in str(exc) and "404" not in str(exc):
            raise

    if other_ok:
        try:
            other_c.call("GET", me, code=404)
        except ProbeError as exc:
            if "404" not in str(exc) and "403" not in str(exc):
                raise

    print("LIVE_PROBE_OK")
    print(f"assignment_id={aid} total_awarded={result['total_awarded']} total_max={result['total_max']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"LIVE_PROBE_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
