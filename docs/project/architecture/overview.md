# Backend Architecture Overview

This describes `apps/lumeneios/` as it stands. Ownership below reflects the team's division of work, and exact code boundaries still need confirming with each owner.

## Request flow

```text
Client
   |  HTTP + JWT
   v
backend/app/main.py  ->  /api/v1  ->  api/v1/router.py
   |
   |-- Dependencies: get_db, get_current_user, require_roles
   |
   |-- Routers
   |     modules/differentiated_homework/router.py -> competency_service
   |     api/v1/competencies.py --------------------> competency_service
   |     api/v1/assessments.py ---------------------> llm_service
   |     api/v1/ocr.py -----------------------------> batch_grading_service -> ocr_service
   |     api/v1/time_aware.py ----------------------> time_aware_engine
   |     api/v1/documents.py -----------------------> storage_service
   |
   v
models/entities.py (async SQLAlchemy)
   v
SQLite by default; settings also allow PostgreSQL
```

## Module responsibilities

| Area | Owner | Related code today |
|---|---|---|
| Differentiated Homework | Differentiated Homework Backend | `backend/app/modules/differentiated_homework/` |
| AI Question Studio Beta | AI Question Studio Beta | `api/v1/assessments.py`, `services/llm_service.py` |
| Time Aware Engine | Time Aware Engine | `api/v1/time_aware.py`, `services/time_aware_engine.py` |
| OCR and Backend | OCR and Backend | `api/v1/ocr.py`, `services/ocr_service.py`, shared backend core |
| Extracted Text, Assessment and Grading | Assessment and Grading | `services/batch_grading_service.py` and related flows |
| Frontend | Frontend | `src/` |

## What's real and what's simulated

| Area | State |
|---|---|
| Homework submission | Versioned saves, immutable final submission, manual evaluation and released student/parent results |
| Question generation | Mock: fixed templates. No LLM provider is connected |
| OCR | All adapters currently simulate output; processing is disabled outside demo mode |
| Batch grading | Demo workflow only for processing/publication; no simulated grades enter live academic records |
| Frontend homework screens | Live authenticated workspace; separate offline demonstration |
| Migrations | Alembic is listed in requirements but isn't set up |

## Expected integration

```text
Assessment and Grading --diagnosis--> Differentiated Homework <--questions-- AI Question Studio Beta
                                           |        ^
                                           |        |  lessons moved to homework
                                           |     Time Aware Engine
                                           v
                                        Frontend
```

These links are proposed. See [the API contract](../api-contracts/differentiated-homework.md).

## Dependency rules (proposed)

- Modules use shared infrastructure, and shared infrastructure doesn't import modules. The API router registers modules; `api/record_access.py` is also a narrow bridge to existing school/link helpers pending agreed shared ownership.
- Modules talk through agreed interfaces, not each other's internal functions.
- Dashboards read conclusions from the backend rather than calculating their own.

## Items for the backend owner

These development defaults are in the code. They're not changed by this integration:

| Item | Location |
|---|---|
| Default `SECRET_KEY` | `backend/app/core/config.py` |
| Default S3 and Neo4j credentials | `backend/app/core/config.py` |
| `SECRET_KEY`, MinIO and PostgreSQL credentials | `infrastructure/docker-compose.yml` |
| `DEMO_MODE=True` by default: requests without a token act as admin, and `demo123` always logs in | `backend/app/core/config.py`, `api/dependencies.py`, `core/security.py` |
| Question-bank authoring access now requires real bearer authentication, educator/admin role and authorized school context; keys/rubrics remain educator-only. Formal assessment routes now have the same login/role/school boundaries plus class/student checks. | `api/v1/assessments.py` |


The live homework client and opt-in offline demonstration are separated at build/runtime.
See [deployment readiness](../deployment-readiness.md) for the exact release checklist,
remaining platform review, database migration requirements and test limitations.

The complete route inventory and remaining release gates are in [release readiness](../release-readiness.md).
