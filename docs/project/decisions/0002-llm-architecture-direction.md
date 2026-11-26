# 0002: Future direction for LLM features

**Status:** Agreed direction, **not implemented**. Recorded 2026-11-08.

## Decision

LumenEIOS will eventually use:

1. **Separate, task-specific AI conversations.** Each AI task, such as question generation or homework support, has its own conversation instead of one shared conversation.
2. **Shared, approved student context across tasks.** Tasks can draw on the same student context, limited to context that has been approved for use.
3. **Persistent, backend-managed conversation history.** The backend stores conversation history, not the client or the model provider.
4. **A provider-independent LLM Gateway.** One backend interface supports several providers, such as Gemini, Groq and a local Qwen model, so features don't depend on a single provider.

## Current state

- **No LLM infrastructure exists yet.** `services/llm_service.py` returns fixed templates, and the `LLM_PROVIDER` and `LLM_API_KEY` settings aren't read anywhere.
- **New features shouldn't call a provider SDK directly.** Until the gateway exists, AI features should be deferred or use deterministic logic. The Differentiated Homework MVP uses the existing question bank for this reason.

## Not yet decided

- Gateway interface, request and response shapes, and error handling.
- Which student context counts as approved, who approves it, and how consent and privacy rules apply to children's data.
- Storage design and retention period for conversation history.
- Provider selection rules, fallback order, and cost and rate limits.
- Ownership of the gateway within the team.
