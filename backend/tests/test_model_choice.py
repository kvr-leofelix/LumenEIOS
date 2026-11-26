import io
import json

import pytest
from PIL import Image

from backend.app.api.v1 import ocr as ocr_api
from backend.app.models.entities import Assessment
from backend.app.services import kc_graph_service


@pytest.mark.asyncio
async def test_upload_can_choose_qwen_for_ocr_and_evaluation(client, db_session, monkeypatch, teacher_token):
    db_session.add(Assessment(
        id="provider-choice-paper", school_id="school-1", class_id="class-8a", subject_id="sub-math",
        title="Provider choice", date="2026-11-14", total_marks=2, status="scheduled",
        questions_json=[{
            "text": "What is twice 6?", "type": "short", "marks": 2, "competency": "AU",
            "correctAnswer": "12", "markingRubric": "Award 2 marks for 12.",
        }],
    ))
    await db_session.commit()
    teacher = {"Authorization": f"Bearer {teacher_token}"}

    image = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(image, "PNG")
    rejected = await client.post(
        "/api/v1/ocr/extract-preview", headers=teacher,
        files={"files": ("sheet.png", image.getvalue(), "image/png")},
        data={"provider": "other"},
    )
    assert rejected.status_code == 422

    async def qwen_extract(path, options=None):
        assert options["file_name"] == "sheet.png"
        return {"extracted_text": "12", "pages_processed": 1}

    async def gemini_extract(*args, **kwargs):
        raise AssertionError("Gemini OCR should not run when Qwen is selected")

    monkeypatch.setattr(ocr_api.qwen_model, "extract_document", qwen_extract)
    monkeypatch.setattr(ocr_api, "extract_gemini_text", gemini_extract)
    preview = await client.post(
        "/api/v1/ocr/extract-preview", headers=teacher,
        files={"files": ("sheet.png", image.getvalue(), "image/png")},
        data={"provider": "qwen"},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["provider"] == "qwen"
    assert preview.json()["results"][0]["extracted_text"] == "12"

    used = []

    class FakeQwen:
        def __init__(self):
            used.append("qwen")

        async def generate_json(self, *, system, prompt, schema):
            if schema.__name__ == "KcMappingResponse":
                return json.dumps({"questions": []})
            assert "What is twice 6?" in prompt
            return json.dumps({
                "question_evaluations": [{
                    "question_id": "1", "question_index": 1, "question_text": "What is twice 6?",
                    "competency": "AU", "max_marks": 2, "awarded_marks": 2, "competency_score": 100,
                    "student_answer_extracted": "12", "status": "attempted",
                }],
                "scoring_summary": {"total_marks_obtained": 2, "max_possible_marks": 2, "percentage": 100},
            })

    def gemini_provider():
        raise AssertionError("Gemini evaluation should not run when Qwen is selected")

    monkeypatch.setattr(ocr_api, "QwenTextProvider", FakeQwen)
    monkeypatch.setattr(ocr_api, "get_ai_provider", gemini_provider)
    monkeypatch.setattr(kc_graph_service, "QwenTextProvider", FakeQwen)
    monkeypatch.setattr(kc_graph_service, "get_ai_provider", gemini_provider)
    graded = await client.post("/api/v1/ocr/evaluate-scan", headers=teacher, json={
        "assessment_id": "provider-choice-paper", "extracted_text": "12", "provider": "qwen",
    })
    assert graded.status_code == 200, graded.text
    assert graded.json()["scoring_summary"]["percentage"] == 100
    assert "qwen" in used
