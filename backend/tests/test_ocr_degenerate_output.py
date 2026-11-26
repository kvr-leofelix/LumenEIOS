"""Qwen float16 overflow yields a run of "!"; it must be detected and retried at a smaller size."""
from PIL import Image

from backend.app.services import ocr_service
from backend.app.services.ocr_service import QwenVisionOCRProvider, is_degenerate_output


def test_detects_punctuation_runs_only():
    assert is_degenerate_output("!" * 400)
    assert is_degenerate_output("! ! ! ! ! ! ! ! ! !")
    assert not is_degenerate_output("Q1. burning of paper")
    assert not is_degenerate_output("")
    assert not is_degenerate_output("2 + 2 = 4")


def test_retries_once_at_reduced_resolution(monkeypatch):
    provider = QwenVisionOCRProvider()
    widths = []

    def fake(messages, max_new_tokens):
        img = messages[0]["content"][0]["image"]
        widths.append(img.width)
        return "!!!!!!!!!!!!" if img.width > 700 else "Q1. burning of paper"

    monkeypatch.setattr(provider, "_generate_locked", fake)
    assert provider._infer_image(Image.new("RGB", (1240, 1754), "white")) == "Q1. burning of paper"
    assert widths == [1240, 700]


def test_gives_empty_text_when_retry_also_fails(monkeypatch):
    provider = QwenVisionOCRProvider()
    monkeypatch.setattr(provider, "_generate_locked", lambda messages, max_new_tokens: "!" * 50)
    assert provider._infer_image(Image.new("RGB", (1240, 1754), "white")) == ""
    assert ocr_service.is_degenerate_output("!" * 50)
