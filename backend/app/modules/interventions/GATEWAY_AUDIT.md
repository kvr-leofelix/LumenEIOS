# Phase A — AI gateway audit (LumenEIOS interventions)

## Arena source of truth

- File: `arena-homework/apps/lumeneios/backend/app/services/ai_gateway.py`
- Entry: `get_ai_provider()` → `GeminiProvider.generate_json(...)`
- Config: `GEMINI_API_KEY` (SecretStr), `GEMINI_MODEL`, `AI_REQUEST_TIMEOUT_SECONDS`
- Errors: `AINotConfigured`, `AIProviderTimeout`, `AIProviderError`, `AIInvalidResponse`
- Consumers: Differentiated Homework AI evaluation, AI Question Studio

## LumenEIOS before this milestone

- `llm_service` for Assessment Studio (deterministic / optional hosted) — separate path
- No `ai_gateway.py`
- No `GEMINI_*` settings

## Integration decision

**Port the arena `ai_gateway` module verbatim in contract** into
`backend/app/services/ai_gateway.py` and add matching settings fields.

- Does **not** introduce a second independent Gemini client API surface
- Features call `ai_gateway.get_ai_provider()` only
- Tests monkeypatch `get_ai_provider` (same pattern as arena)
- Optional dependency: `google-genai` only required when a live key is configured

## Compatibility notes

- LumenEIOS default `GEMINI_MODEL` set to `gemini-2.0-flash` (override via env)
- Existing `LLM_PROVIDER` / `llm_service` unchanged for Assessment Studio
- Empty `GEMINI_API_KEY` → generate endpoint returns 503 with safe public message
