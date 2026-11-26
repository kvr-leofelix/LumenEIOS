# Curriculum backend handoff — 2026-11-10

Implemented an authenticated, database-backed API and persistent editorial review workflow under CURRICULUM_API_INTEGRATION_CONTRACT.md. No frontend changes were made in this backend task. No runtime catalogue source/node/mapping rows were imported or invented. A populated demonstration remains blocked; an empty real API is available after schema installation.

## Files changed in this backend task

Paths relative to apps/lumeneios unless noted:

- `docs/CURRICULUM_API_INTEGRATION_CONTRACT.md` — canonical routes, typed schemas, role policy, errors, review transitions and migration amendment, written before implementation.
- `backend/app/api/v1/ncert.py` — eight routes, mandatory bearer authentication, database role enforcement, isolated FK-enabled connection, resource availability and subject/node lookup.
- `backend/app/api/v1/router.py` — registers the new router; old routes preserved.
- `backend/app/schemas/ncert.py` — response models and strict review validation; no outcome prose response field.
- `backend/app/services/ncert_catalogue_service.py` — evidence-aware read projections, rights redaction, explicit missing translations, versioned append-only review decisions and conflicts; no import/publication.
- `backend/app/models/ncert_review.py` — one additive editorial audit model independent of the 13 catalogue tables.
- `backend/app/db/base.py` — adds registration of the editorial model to earlier uncommitted catalogue registration.
- `backend/migrations/002_ncert_mapping_decisions.py` — idempotent additive review table creation; rejects missing prerequisite/column mismatches and destructive downgrade.
- `backend/tests/test_ncert_api.py` — 15 tests (including parameter cases), synthetic isolated fixtures; endpoint reads, auth, invalid input, state changes, concurrency, persistence, rights/evidence gates, release restrictions, migration preservation and PostgreSQL DDL compilation.
- `docs/NCERT_DATABASE_INTEGRATION.md`, `docs/CURRICULUM_IMPLEMENTATION_PLAN.md` — append current user-authorised API phase and ownership override; preserve historical research/deficiencies.
- repository-root `AGENTS.md`, `CLAUDE.md` — append Codex-backend/Claude-frontend ownership and canonical API reference; preserve existing instructions.
- this status report.

Pre-existing uncommitted foundation (`ncert_catalogue.py`, migration001, its tests, session.py registration), source research, root documentation mirrors and isolated stopped frontend worktree are preserved. They are not newly authored in this backend task. No files under src/ or either frontend checkout were modified by this task.

## Actual verification

From `apps/lumeneios`:

1. `python -m pytest backend/tests/test_ncert_api.py -q` — **9 passed in 3.76s** at the initial endpoint milestone.
2. `python -m pytest backend/tests -q` — **85 passed in 5.38s** after auth/transaction changes.
3. `python -m pytest backend/tests -q` — **91 passed in 5.70s**, final implementation including additional token, concurrency, transition and storage-constraint coverage.

Existing pytest-asyncio fixture-loop-scope deprecation warning remains. Tests use the existing conftest's temporary database/upload directory and original-file integrity guard. No development database reset/migration/seed was run. PostgreSQL has DDL compilation coverage only; no live PostgreSQL test. No frontend browser/integration test was run. No claim of populated API or frontend integration is made.

At the original implementation handoff, `git diff --check` passed and the staging area was empty. During integration preparation, the full suite passed again: **91 passed in 6.77s**. Staged-diff inspection found one trailing space in the newly tracked API contract; it was removed. The commit includes 16 explicit backend/foundation/canonical-document paths; research artifacts, root instruction files, frontend worktrees and generated files are excluded. No push/merge/reset/discard or application database migration is performed.

## Deployment and schema requirements

The normal backend startup imports all models and creates missing tables through existing `init_db`; do not use it as an updater for incompatible schemas. For a controlled existing database upgrade: stop writers, back up/verify restore of the actual configured database, then run `upgrade(sync_connection)` in migration001 followed by migration002 using an `engine.begin()` async transaction with `connection.run_sync(module.upgrade)`. These are Python migration modules loaded by path (the numeric filenames are not normal import identifiers). No Alembic revision runner is configured for them. Review existing catalogue schemas before running: the guards compare column names, not full column types/constraints. Incompatible existing tables require an explicitly reviewed migration, never deletion/reset. Migration002 creates only `ncert_mapping_decisions`; no source data, school data or existing enums are changed.

The original SQLite seed-order limitation remains. Catalogue API operations enable/check FK enforcement before auth/database reads on their checked-out connection and restore its original setting on return. Legacy seed code is not executed by these endpoints. Other catalogue ingestion/writes remain unauthorised. No dependency additions are needed; use backend/requirements.txt in the established Python environment.

Start normally from `apps/lumeneios`: `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`. Open `/api/v1/docs`, use the existing login to obtain an access token, authorise Swagger, and call `/api/v1/ncert/releases`. Expect an empty list on the existing empty catalogue. `/api/v1/ncert/availability?grade=6&language=en` returns NO_RELEASE_SELECTED. Explicit release selection and returned subject IDs are required for nonempty queries; never synthesize IDs or match by title.

## Frontend handoff / remaining dependencies

- Claude can integrate the actual HTTP contract now. Principals/teachers are read-only published-catalogue readers; only admin may inspect/review drafts. Existing local role switching is not sufficient: obtain a valid bearer token. No demo-admin auth fallback on these routes.
- No catalogue records are seeded. Ten research-CSV candidates are not runtime mapping records and must not be silently served as verified/published data. Reviews return404 until an authorised record exists.
- Catalogue part/reprint/lifecycle and independently scoped outcome schema deficiencies remain in NCERT_DATABASE_INTEGRATION.md. Source preparation/import needs a separate approved design and authorisation; this API phase is not an importer.
- Current syllabus applicability, qualified crosswalk review, Hindi/Urdu equivalence, Urdu Mathematics Part II status and permission grants remain unresolved as recorded in NCERT_PHASE0_CLOSURE_REPORT.md. Phase0 research is not declared complete.
- No legal/rights grant exists. API metadata permission checks are based on explicitly recorded scoped rights decisions, not public URL accessibility. Restricted source title/URL/locator and mapping prose remain null.
- Human editorial APPROVED is separate from SOURCE_VERIFIED/EXPERT_VERIFIED. API applicability stays UNVERIFIED and recovery_eligible false. No approval changes publication, permissions or school teaching completion.
- Live PostgreSQL execution, deployment migration and Claude's browser/API integration remain unverified external execution steps, not passing-test claims.
