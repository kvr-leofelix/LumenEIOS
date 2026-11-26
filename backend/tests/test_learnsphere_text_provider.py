"""LEARNSPHERE_TEXT_PROVIDER switches text-only LearnSphere/Studio steps between local Qwen and Gemini."""
from backend.app.core.config import settings
from backend.app.services import llm_service


def _fail(*_args, **_kwargs):
    raise AssertionError("wrong provider")


def test_text_steps_use_gemini_when_selected(monkeypatch):
    monkeypatch.setattr(settings, "LEARNSPHERE_TEXT_PROVIDER", "gemini")
    monkeypatch.setattr(llm_service.qwen_model, "generate", _fail)
    calls = []
    monkeypatch.setattr(llm_service, "_gemini_text", lambda prompt, json_output: calls.append(json_output) or '{"ok": true}')
    assert llm_service.qwen_question_studio._generate_text("Hello", output_schema={"type": "object"}) == '{"ok": true}'
    assert calls == [True]


def test_qwen_stays_the_default_and_images_always_use_qwen(monkeypatch):
    monkeypatch.setattr(llm_service, "_gemini_text", _fail)
    monkeypatch.setattr(llm_service.qwen_model, "generate", lambda messages, tokens: "from qwen")
    monkeypatch.setattr(settings, "LEARNSPHERE_TEXT_PROVIDER", "qwen")
    assert llm_service.qwen_question_studio._generate_text("Hello") == "from qwen"
    monkeypatch.setattr(settings, "LEARNSPHERE_TEXT_PROVIDER", "gemini")
    import io
    from PIL import Image
    buffer = io.BytesIO(); Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
    assert llm_service.qwen_question_studio._generate_text("Read this page", buffer.getvalue()) == "from qwen"
