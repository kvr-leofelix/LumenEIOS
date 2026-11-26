# Seeded database integration acceptance ? 19 November 2026

The integrated application reads and writes a populated, isolated SQLite database through its real HTTP APIs. Four roles were checked in a real headless Edge browser with no API mocks or browser demo store. A backend process restart retained saved data. Successful AI-dependent pipeline checks used explicitly labelled model-text fixtures; live Qwen inference is unavailable in this Python environment. Native failure handling was verified separately, without those fixtures.

## Existing architecture and selected implementation

The latest KVR implementation is authoritative: SQLAlchemy declarative Base in backend/app/db/session.py, async aiosqlite/asyncpg engine, async_sessionmaker, per-request commit/rollback, and explicit registration in backend/app/db/base.py plus the API router. SQLite is the local default; PostgreSQL is supported by asyncpg and the existing infrastructure/docker-compose.yml pgvector/pg16 service.

Compared with arena-learnsphere, KVR adds SQLite initialization of missing LearnSphere tables, newer optional columns (username/admission/birth data, subject-aware snapshots, bank topic/grade), Qwen-compatible homework suggestion constraints, learning interventions and a much richer synthetic school roster. The source migration files through revision 0004 already match; KVR adds revision 0005. The original source folder was not modified or used as a database copy.

The current application seed is backend/app/seed/seed_data.py, using school_content.py, build_students(), roster_users() and seed_database_if_empty(). It defines two fictional schools, 12 classes, 240 student profiles, 497 accounts, 14 subject teachers, parent-child and login-profile links, historical assessments/submissions, bank questions and teacher allocations. Passwords are defined by PASSWORDS and student dates of birth. The legacy backend/tests/sample_seed.py is a different unit-test fixture; it was not substituted for the current roster.

Existing tools inspected: migrate_learnsphere.py (backup/rehearsal/guarded apply), build_demo_database.py, demo_scenario.py, demo_learnsphere.py, local_demo.py, seed_demo_samples.py, seed_teacher_plan_demo.py, init_curriculum.py and the test/browser launchers. The full build-demo tool would also initialise curriculum and write a credentials document; it was not used. demo_learnsphere.py hardcodes the default DB path and contains a competency-to-stage demo lookup, so it was not used. No --fresh, reset or default database operation ran.

## Created database and migrations

Database, relative to apps/lumeneios:

    .local-demo/seeded-acceptance-verified-20261119/acceptance.db

All test files/uploads, credentials, backups, JSON evidence and screenshots are under that ignored run directory. An earlier debugging run is retained separately; it was not reset or copied into this verified database.

For a new file, current non-LearnSphere base tables were created with the existing ORM. The existing migration runner backed up that new file, rehearsed upgrades, checked record fingerprints and applied the complete chain:

    0001_learnsphere -> 0002_assessment_results -> 0003_panchapadi
    -> 0004_unmapped_activities -> 0005_learning_interventions

Current init_db then added the remaining registered application tables; the current seed populated synthetic records. No Alembic stamp, rewritten migration or new migration was introduced. Catalogue and planning tables use the existing ORM initialization path; their standalone additive scripts are not a second Alembic history. Curriculum auto-seeding was explicitly disabled. Catalogue nodes/releases remain empty.

The final database has 85 tables (84 ORM runtime tables plus alembic_version), 2 schools, 12 classes, 497 users, 240 students, 410 assessments, 6,481 legacy-compatible submissions, 3 LearnSphere assessment results, 2 automatically assigned activities/assignments, 2 completed attempts and 2 activity-evidence records. The three results consist of the controlled full-pipeline paper, a missing-evidence paper, and an existing seeded paper submitted to the native unpatched backend.

## Persisted workflow checks

The controlled pipeline made 52 HTTP requests, with real authentication, database sessions, permissions, background workers, Pydantic model-output validation, scoring, JSON revisions and activity services. Only Qwen text output was replaced by an explicit acceptance fixture in the optional launcher; no frontend/API response was mocked. Question-content stage fixtures reuse backend/tests/test_panchapadi.py rather than the old demo's competency-stage lookup.

Passed:

- Seeded teacher, student, principal and parent logins, plus another teacher. Native DEMO_MODE=false, APP_ENV=test, developer bypass disabled; no default demo-admin or fabricated password.
- Correct student/parent reads; unrelated same-school child and other-school student denied. Wrong-class teacher denied; principal stayed in its school. Role dashboards read the real /workspace API.
- Authored assessment persisted, seven responses saved, MCQ keys evaluated, written partial mark stored, unsupported written mark left unknown. Missing evidence in a separate result yielded null/absent JSON score fields and five unassessed stage values, never zero.
- All four competency labels and evidence observed through saved question outcomes/Learning Journey. Competency review persisted independently; replaying the same request key did not append a duplicate decision.
- All five Panchapadi stages classified provisionally from question-content fixtures. Two teacher revisions persisted and changed scores; final confirmed five-stage values were derived by the existing scoring implementation from reviewed marks. Earlier revisions and responses survived guidance refresh. No new scoring formula or runtime stage mapping was introduced.
- Question-specific Learning Support guidance, separate provisional/confirmed history and null gaps persisted. The result-detail endpoint's top-level panchapadi is the automatic view; confirmed snapshots are in reviews and the Learning Support/Journey projections. Tests use those existing contracts.
- Automatic Teach-Back and Mission assignments persisted. Submission replay, guidance retry and both teacher revisions left exactly two assignments for the result.
- Student attempts persisted and replay reused the same attempt IDs; parent submission denied. Teach-Back fixture evaluation, teacher review, rubric observations and completion persisted independently of assessment marks.

A new backend process, started without AI fixtures, passed 27 restart-read/auth checks: original answers, two marks-review revisions, assignment IDs, completed attempts and guidance remained available to authorized roles. The native server is the one left running.

## Native provider check

The unpatched backend accepted four responses to the existing seeded assessment asm-sps-7a-sci-open1. Its MCQ scored 1/1. All three written scores remained unknown because torch/transformers/qwen_vl_utils are absent. Errors remained explicit and saved answers were retained; no automatic activity or verified evidence was fabricated from that failure. A real authenticated Qwen OCR preview request returned 503 with: Qwen OCR dependencies are missing. Install backend/requirements-ocr.txt with a CUDA-enabled PyTorch build.

Thus native AI evaluation quality/success is NOT verified. The fixture tests establish database/service integration of the successful pipeline; the native tests establish safe persisted failure behavior. Gemini is not exercised here; the earlier missing google-genai dependency limitation remains.

## Integrity and compatibility

- SQLite integrity_check: ok. foreign_key_check: zero violations before and after workflows and restart.
- Exact column sets and non-primary-key nullability of all seven learning_* tables match current ORM models.
- No duplicate composite groups in assessment results, assignments, attempts or activity evidence. Real rolled-back probes reject a missing FK, null required topic title and duplicate assessment/student result. Existing automatic activities legitimately retain nullable topic_id; no topic was invented.
- Server connections explicitly enforce and assert PRAGMA foreign_keys=ON after seeding. This is confined to the isolated acceptance launcher. The ordinary legacy SQLite engine still does not globally enable FK enforcement; its seed-order compatibility constraint is unchanged.
- Existing Alembic history compiled to PostgreSQL offline SQL; all 84 current runtime ORM tables and indexes compiled using the PostgreSQL dialect. asyncpg is installed. No live PostgreSQL test ran: Docker/psql are not available on PATH and no disposable PostgreSQL test service was provisioned. DDL compilation is not a live-database guarantee. The existing production Compose settings also need their already-required security provisioning; no shared service was started.
- Hashes of each original lumeneios.db path are checked against the run's starting manifest, including absent files. All remained unchanged. No source database, production data or original upload directory was opened for writes.

## Browser and regression results

Headless Edge uses the installed @playwright/test browser driver and existing API contracts. The runner logs in through /login, opens each role dashboard, selects the exercised student, loads saved Learning Support, checks read-only parent/student controls, verifies all five confirmed Journey dots and reloads. No API interception occurs; requests to nonlocal origins are blocked. Screenshots and browser.json are in the run directory.

Four-role browser checks passed against the fixture server, then were repeated against the native restarted server (final result below). The runner initially assumed / was the login form, exact stage headings without Progress, and a featured parent instead of the exercised child's linked parent. Those runner assumptions were corrected; no app permission or UI behavior was weakened.

Backend regression checks: 49 passed for launcher safety plus existing LearnSphere/Panchapadi/automation workflows. A further initialization/roster/safety run is recorded below. These runs use the existing isolated pytest fixtures and supplement the persistent HTTP/database/browser evidence.

Final native-server browser rerun: **all four roles passed**. Initialization/roster/safety regression run: **8 passed** (including the 2 safety tests already counted in the 49-test run). Invalid-password login and anonymous LearnSphere access both returned **401**. Final git diff --check passed. No unresolved acceptance assertion remains; native AI success and live PostgreSQL testing remain unavailable for the reasons stated above.

## Exact start commands

Run from PowerShell. The test servers are already running on ports 18880 and 18881; use these commands for a subsequent start after stopping the current processes. They resume the verified file and never seed/reset it.

```powershell
Set-Location 'D:\Gurleen\College\Years\Sem 3\IC 202P DP\arena-integration\apps\lumeneios'
& '..\..\..\arena-learnsphere\.venv\Scripts\python.exe' -B -m backend.scripts.seeded_learnsphere_acceptance serve --run-dir .local-demo/seeded-acceptance-verified-20261119 --port 18880
```

In a second PowerShell terminal:

```powershell
Set-Location 'D:\Gurleen\College\Years\Sem 3\IC 202P DP\arena-integration\apps\lumeneios'
$env:VITE_API_URL='http://127.0.0.1:18880/api/v1'
$env:VITE_DEMO_MODE='false'
$env:LUMENEIOS_BACKEND_URL='http://127.0.0.1:18880'
npm.cmd run dev -- --host 127.0.0.1 --port 18881 --strictPort
```

Frontend: http://127.0.0.1:18881/login
Health: http://127.0.0.1:18880/health
API documentation: http://127.0.0.1:18880/api/v1/docs

The existing source environment is used read-only as a Python interpreter; no .venv was copied or modified. A newly installed compatible environment may replace that interpreter path.

Optional successful-pipeline fixture verification uses the same serve command with --fixture-ai. This explicitly replaces model text output for tests and must not be described as live AI. A new database can be prepared with command prepare and a NEW child directory under .local-demo; existing run directories are refused. The exercise command creates new acceptance assessments, so do not use it merely to inspect this completed run. verify-restart and audit are the inspection commands (audit's constraint probes are rolled back).

```powershell
& '..\..\..\arena-learnsphere\.venv\Scripts\python.exe' -B -m backend.scripts.seeded_learnsphere_acceptance verify-restart --run-dir .local-demo/seeded-acceptance-verified-20261119 --port 18880
node tests/seeded-database-ui.mjs
```

## Existing seed credentials actually exercised

| Role | Existing seeded email | Existing seeded password |
|---|---|---|
| Teacher | garima.sharma@sps.lumeneios.demo | Teacher@123 |
| Principal | lakshmi.narayanan@sps.lumeneios.demo | Principal@123 |
| Student (Aditya Patel) | aditya.patel.041@sps.lumeneios.demo | 09072013 |
| Linked parent (Naresh Patel) | parent.sps25041@sps.lumeneios.demo | Parent@123 |

These are the seed's explicitly defined fictional accounts, not invented credentials or production accounts. The featured Gurleen/Harpreet seed accounts are different people; tests deliberately use the actual stored relationship for Aditya/Naresh.

## Source changes for this additional task

- backend/scripts/seeded_learnsphere_acceptance.py: guarded opt-in setup, real migration/seed reuse, fixture/native server profiles, persistent API/restart tests, integrity probes.
- backend/tests/test_seeded_acceptance_safety.py: refuses external paths and existing-run resets.
- tests/seeded-database-ui.mjs: real-browser checks against the populated database.
- docs/LEARNSPHERE_DATABASE_ACCEPTANCE_REPORT.md: this report and startup commands.

Application database architecture, seed definitions, production models, migration files, frontend implementation and dependency manifests were not changed by this additional task. Prior uncommitted integration work remains intact. Nothing was committed or pushed.
