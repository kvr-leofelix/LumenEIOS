"""Minimal provider-independent AI gateway (first step toward ADR 0002's LLM Gateway).

Features ask the gateway for structured JSON; they never import a provider SDK. Gemini is the
only provider today. Adding another provider means implementing `AIProvider.generate_json`.

Safety rules enforced here:
- The API key comes only from settings (environment), is held as a SecretStr and is never
  logged, returned or included in exception messages.
- Provider failures are mapped to a small set of gateway errors with generic messages, so raw
  SDK errors (which can echo request details) never reach HTTP responses.
- Callers are responsible for not putting personal data in prompts (see ai_question_service).
"""
import asyncio
import json
import logging
from typing import Protocol, Type

from pydantic import BaseModel

from backend.app.core.config import settings

logger = logging.getLogger("lumeneios.ai_gateway")


class AIGatewayError(Exception):
    """Base class. `public_message` is safe to show to an educator."""

    public_message = "The AI service could not complete the request."


class AINotConfigured(AIGatewayError):
    public_message = "AI features are not configured on this server (GEMINI_API_KEY is not set)."


class QwenUnavailable(AINotConfigured):
    public_message = "Qwen is not available on this server. Choose Gemini, or install the Qwen model."


class AIProviderTimeout(AIGatewayError):
    public_message = "The AI service took too long to respond. Try again, or request fewer questions."


class AIProviderError(AIGatewayError):
    public_message = "The AI service returned an error. Try again in a moment."


class AIProviderBusy(AIProviderError):
    public_message = ("Gemini is overloaded right now (Google's service is busy). Try again in a minute, "
                      "or choose Qwen to run it on this server.")


class AIInvalidResponse(AIGatewayError):
    public_message = "The AI response could not be understood. Try generating again."


class AIProvider(Protocol):
    name: str
    model: str

    async def generate_json(self, *, system: str, prompt: str, schema: Type[BaseModel]) -> str:
        """Return the raw JSON text the model produced for `schema`."""


class GeminiProvider:
    """Google Gemini through the official `google-genai` SDK, using structured JSON output."""

    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout_seconds: float, client=None):
        if not api_key:
            raise AINotConfigured()
        self.model = model
        self._timeout = timeout_seconds
        if client is None:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)))
        self._client = client

    async def generate_json(self, *, system: str, prompt: str, schema: Type[BaseModel]) -> str:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=_gemini_json_schema(schema),
            temperature=schema_temperature(schema),
        )
        return await self._generate(prompt, config)

    async def transcribe_image(self, *, system: str, image: bytes, mime_type: str) -> str:
        from google.genai import types

        return await self._generate(
            ["Transcribe this page.", types.Part.from_bytes(data=image, mime_type=mime_type)],
            types.GenerateContentConfig(system_instruction=system),
        )

    # Google answers 429/5xx when the model is overloaded; these usually clear within seconds.
    TRANSIENT_CODES = {429, 500, 502, 503, 504}
    RETRY_DELAYS = (2.0, 5.0)

    async def _generate(self, contents, config) -> str:
        from google.genai import errors

        loop = asyncio.get_running_loop()
        started = loop.time()
        for attempt in range(len(self.RETRY_DELAYS) + 1):
            remaining = self._timeout - (loop.time() - started)
            try:
                response = await asyncio.wait_for(
                    self._client.aio.models.generate_content(model=self.model, contents=contents, config=config),
                    timeout=max(0.01, remaining),
                )
                break
            except asyncio.TimeoutError:
                logger.warning("Gemini request timed out (model=%s).", self.model)
                raise AIProviderTimeout() from None
            except errors.APIError as exc:
                code = getattr(exc, "code", None)
                # Log only the status code; messages can contain request details.
                logger.warning("Gemini API error (model=%s, code=%s, attempt %d).", self.model, code if code else "?", attempt + 1)
                if code not in self.TRANSIENT_CODES:
                    raise AIProviderError() from None
                delay = self.RETRY_DELAYS[attempt] if attempt < len(self.RETRY_DELAYS) else None
                if delay is None or (loop.time() - started) + delay >= self._timeout:
                    raise (AIProviderBusy() if code in (429, 503) else AIProviderError()) from None
                await asyncio.sleep(delay)
            except Exception as exc:  # network/transport errors from the SDK
                logger.warning("Gemini request failed (model=%s, %s).", self.model, type(exc).__name__)
                raise AIProviderError() from None
        text = getattr(response, "text", None)
        if not text:
            logger.warning("Gemini returned no text (model=%s).", self.model)
            raise AIInvalidResponse()
        return text


def _inline_schema_refs(schema: dict) -> dict:
    """The same JSON schema with every "$ref" replaced by its definition and no "$defs" section. The small local Qwen
    model copied the "$defs" key into its answers (wrapping each question in it), which made them unusable."""
    defs = schema.get("$defs", {})

    def resolve(node, depth=0):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/") and depth < 10:
                return resolve(defs.get(ref.split("/")[-1], {}), depth + 1)
            return {k: resolve(v, depth) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [resolve(v, depth) for v in node]
        return node

    return resolve(schema)


def _gemini_json_schema(schema: Type[BaseModel]) -> dict:
    """JSON Schema for Gemini. Drop open-object maps; the Developer API rejects them."""
    data = schema.model_json_schema()

    def walk(node) -> None:
        if isinstance(node, dict):
            node.pop("additionalProperties", None)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return data


_selected_model: str | None = None


def active_gemini_model() -> str:
    """Model used for OCR and evaluation. A developer choice overrides the env default."""
    return _selected_model or settings.GEMINI_MODEL


def select_gemini_model(model: str) -> str:
    global _selected_model
    chosen = model.strip()
    if not chosen:
        raise ValueError("Choose a Gemini model.")
    _selected_model = chosen
    return chosen


def clear_gemini_model_selection() -> None:
    global _selected_model
    _selected_model = None


class QwenTextProvider:
    """JSON generation through the existing local Qwen vision model."""

    name = "qwen"

    def __init__(self) -> None:
        self.model = settings.QWEN_VL_MODEL_ID

    async def generate_json(self, *, system: str, prompt: str, schema: Type[BaseModel]) -> str:
        instruction = (
            f"{system}\n\n{prompt}\n\n"
            "Return only one JSON object matching this schema:\n"
            + json.dumps(_inline_schema_refs(_gemini_json_schema(schema)))
        )
        try:
            from backend.app.services.ocr_service import (
                QwenOCRInferenceError,
                QwenOCRUnavailableError,
                qwen_model,
            )
            return await asyncio.to_thread(
                qwen_model.generate,
                [{"role": "user", "content": [{"type": "text", "text": instruction}]}],
                2048,
            )
        except QwenOCRUnavailableError:
            logger.warning("Qwen model is unavailable.")
            raise QwenUnavailable() from None
        except QwenOCRInferenceError:
            logger.warning("Qwen generation failed.")
            raise AIProviderError() from None


DEFAULT_TEMPERATURE = 0.7


def schema_temperature(schema: Type[BaseModel]) -> float:
    """Sampling temperature for a response schema.

    A schema opts in with `ai_temperature: ClassVar[float]`. Marking and mapping schemas use a low
    value so the same answer gets the same marks on every run; question writing uses a higher one
    for variety."""
    value = getattr(schema, "ai_temperature", DEFAULT_TEMPERATURE)
    return float(value) if isinstance(value, (int, float)) else DEFAULT_TEMPERATURE


def get_ai_provider() -> GeminiProvider:
    """Build the configured provider. Raises AINotConfigured if no key is set.
    Tests replace this function; they never reach a real provider."""
    return GeminiProvider(
        api_key=settings.GEMINI_API_KEY.get_secret_value().strip(),
        model=active_gemini_model(),
        timeout_seconds=settings.AI_REQUEST_TIMEOUT_SECONDS,
    )


async def list_gemini_models() -> list[dict[str, str]]:
    """Gemini models this key can call for text generation."""
    from google.genai import errors

    provider = get_ai_provider()
    found: dict[str, str] = {}
    try:
        pager = await provider._client.aio.models.list()
        async for model in pager:
            model_id = (getattr(model, "name", "") or "").split("/")[-1].strip()
            actions = getattr(model, "supported_actions", None) or []
            if not model_id.startswith("gemini") or "generateContent" not in actions:
                continue
            found[model_id] = (getattr(model, "display_name", None) or model_id).strip()
    except errors.APIError as exc:
        logger.warning("Gemini model list failed (code=%s).", getattr(exc, "code", "?"))
        raise AIProviderError() from None
    except Exception as exc:
        logger.warning("Gemini model list failed (%s).", type(exc).__name__)
        raise AIProviderError() from None
    return [{"id": model_id, "label": found[model_id]} for model_id in sorted(found)]
