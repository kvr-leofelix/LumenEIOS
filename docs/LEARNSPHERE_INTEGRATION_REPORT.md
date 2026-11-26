# LearnSphere integration report ? 2026-11-19

Workspace: arena-integration. Branch: `integration/learnsphere-latest`. Baseline: `0831c651a91b01361af0a5d683644c48c7ad31c1`. No commit, push, merge, application database operation or original-source edit was performed.

## Comparison

Compared backend application code, models/schemas, migrations, tests, frontend, documentation, infrastructure and root application configuration. The [file inventory](LEARNSPHERE_COMPARISON_INVENTORY.md) records 259 eligible source files: 107 identical at baseline, 131 with a different target counterpart, 21 source-only. Runtime directories, databases, credentials, backups and generated output were excluded. Root package/lock/configuration/requirements files were compared separately; target versions were retained.

All six source migration Python files match target equivalents after line-ending normalization. KVR additionally has curriculum/planning migrations 001?009 and Alembic revision 0005_learning_interventions; these are preserved. Source code hashes were checked again after testing and were unchanged. The existing GitHub clone was not used as a source of application changes; Git necessarily updated its shared worktree metadata to attach the requested branch.

## Already present in KVR

- LearnSphere activities, assignments, saved attempts, versioned teacher review/evidence, Learning Support, Learning Journey, Teach-Back and Real-Life Missions.
- Assessment response snapshots, automatic MCQ evaluation, provisional written marking, teacher corrections, evidence-linked learning drafts and automatic stable Teach-Back/mission assignment IDs.
- Independent Panchapadi stages (Adheeti, Bodh, Abhyas, Prayog, Prasar), eligibility gates, weighted percentages, null evidence gaps, five historical graphs and separate provisional/confirmed series.
- Guidance recovery, heartbeats, compare-and-swap updates, privacy filtering and role/class/student access rules. KVR adds a bounded automatic retry cap, retained here.
- Question Studio PDF/web sources, streaming progress, manual bank authoring in the homework workspace, bank editing/deletion routes and subject/topic metadata. The missing Studio controls are connected to these existing APIs rather than introducing a second manual-question backend.
- Newer KVR shared Qwen runtime, Windows/CPU paths, OCR quality handling, Gemini gateway/preview APIs, calendar hub, teacher planning, authentication, active-school context, dashboards, roles, security floors and learning interventions remain in place.

These observations were established by code comparison; runtime quality of live AI providers is not claimed.

## Additional work integrated

1. LearnSphere post-submission competency analysis using question wording, rubric, expected answer and available learning objective/topic. Stored LU/CU/AU/CT tags are excluded from model analysis input. Suggestions have fingerprints, reasons, confidence and provenance. Confidence below 0.85 or absent evidence remains unmapped; provider failures remain pending.
2. Separate educator competency decisions with request-key idempotency, optimistic version checks and append-only JSON review history. Decisions override model suggestions without rewriting original questions/answers, marking reviews, stage mappings or activity snapshots.
3. Semantic written-marking instructions and provisional concept evidence, with nullable marks/correctness when evidence is insufficient. Teacher feedback and competency decisions invalidate incompatible guidance. Reliable competency mappings gate new automatic follow-ups.
4. Compact assessment-scoped marks/stage review within Learning Support, alongside competency review and concept evidence by stage. The old broad review panel on that page is replaced by this scoped entry, avoiding duplicate reviewers. Unknown marks remain blank; correct answers have collapsed optional enrichment. Existing math rendering is retained and used in the new review.
5. Strict Studio count validation, stable even allocation, editable LU/CU/AU/CT totals and exact competency constraints per generation slot, without relabelling model output. Regeneration retains the selected competency. KVR source-fact targeting, duplicate checks, per-question generation and advisory answer-key checks remain.
6. Studio manual creation and saved-bank loading reuse the current backend. Bank edits/deletions await success, surface errors and do not rewrite existing assessment snapshots. Deletion rejects assessment references (409), missing/out-of-school records return 404, and empty banks return an honest empty array. Duplicate option comparison ignores labels/case/repeated spaces.
7. Assignment targets carry school metadata and enforce teacher teaching scope. Both class-teacher ownership and KVR TeacherAssignment subject allocations are accepted; principals/admins retain authorized school context. Added school/class audience regression tests.

See [the integration contract amendment](LEARNSPHERE_INTEGRATION_CONTRACT.md) for request/response and persistence details.

## Overlaps resolved

- Shared files were merged at feature/function level; the source's older authentication, seeds, entities, dashboards, OCR transport and dependency versions were not substituted.
- Source automation removed KVR's retry limit. The integration retains that limit and accounts for competency-review revisions separately.
- Source support components omitted MathText and role-specific answer labels. Both KVR behaviors are retained.
- Source Studio used older Ollama batch generation, whole-batch quality review and timeout audit metadata. Those implementations were not copied over KVR's shared-model per-question pipeline; explicit count/competency validation was adapted into the current pipeline. KVR's advisory key check already tolerates check failures. No new claim of automatic factual verification is introduced.
- Source-only StudentAnswerSheets/StudentHomework browser-storage/demo screens were not added alongside current live assessment/homework/upload workflows.
- Source-only CompressionPreviewModal and fixed-ratio/day-based compression were not restored; current approved period-based planning rules remain authoritative.
- Existing security tests were updated only for intentional empty-bank/404 deletion semantics. An upload test now supplies explicit cross-class teaching allocations, retaining its student/school/upload assertions. Separate tests verify unauthorized teachers are refused and assigned subject teachers are accepted.

## Migrations and data

No new migration is required. No model/table/column changed. Competency analyses and reviews use the existing result JSON metadata and version column. Alembic reports the single existing head `0005_learning_interventions`. Existing migration tests exercise additive upgrades, preserved rows/reviews, idempotence and PostgreSQL DDL compilation using test databases. No live PostgreSQL migration was attempted.

No catalogue ingestion, publication, runtime NCERT data creation, database resets or application database upgrades were performed. Original plans and teaching-completion rules were not changed.

## Verification

- Backend full final run: **1,218 passed, 1 failed, 1 skipped, 3 deselected** in 250.80 seconds. The sole failure was an existing upload fixture lacking the new explicit cross-class teacher allocations. Its fixture was corrected without changing production permissions; all **9 tests** in assignment uploads, source school-audience regressions and Studio integration passed on the focused rerun. Thus **1,219 distinct backend tests have passing results across the full run and focused rerun**. The full suite was not rerun after this fixture-only correction.
- The skipped test is the opt-in GPU smoke test. The three deselected Gemini SDK tests had failed with missing google.genai on the initial full run; downloads failed TLS certificate validation. They are not counted as passing.
- Earlier focused LearnSphere/Panchapadi/guidance checks: **53 passed**. Source count/deletion and adapted Studio/school checks: **21 passed**, followed by the final allocation/upload rerun above. These overlap the full-suite counts.
- Frontend full Vitest run: **303 passed, 0 failed** using `--maxWorkers=1 --testTimeout=20000`. The final added scoped-marks review test then passed in a **4-test** focused run (3 overlapping), giving **304 distinct passing frontend tests**. The earlier default 5-second run timed out in 23 tests under concurrent load; no production timeout/configuration was changed.
- Final TypeScript `tsc --noEmit`: **passed**. Configured live `npm run build`: **passed**, using VITE_API_URL=http://localhost:8000/api/v1 and VITE_DEMO_MODE=false. Builds without an explicit API URL intentionally fail under KVR's existing safety configuration.
- Separate frontend contract runner: **20 passed, 1 failed**. The dashboard-label assertion reproduces on untouched baseline; details below. Baseline's additional build-artifact assertion was not evaluated as a product regression because the isolated baseline snapshot had no build.
- Alembic heads: **0005_learning_interventions**, single existing head. Existing migration tests passed within backend runs; source migration equivalents match and migration files are unchanged.
- `git diff --check`: **passed**. Source hashes: **unchanged**. Package manifests, lockfile, requirement files, runtime configuration and migration history: **unchanged**.

Local machine-readable evidence is in ignored `node_modules/.cache/learnsphere-backend-final.xml` and `node_modules/.cache/learnsphere-frontend-final.json`. The XML records the full run before the fixture correction; the focused rerun is reported separately above.

## Remaining limits

- Gemini SDK tests need the already-declared google-genai dependency. Installation into an ignored integration-only directory was attempted with no source-environment writes; both sandboxed and approved network attempts failed TLS certificate validation. No certificate checks were disabled.
- No live Qwen/Gemini inference, GPU smoke run, real-student submission or manual browser acceptance is claimed. Model semantics/confidence/latency remain provisional. The optional CDP browser script requires a separately running Chrome debugging endpoint on port 9331 and a frontend origin; that environment was not available.
- Existing Vite circular-chunk, mixed-import and bundle-size advisories remain. Existing pytest-asyncio fixture-scope advisory remains.
- The separate frontend contract test expects an older dashboard button label (Open homework/Open Differentiated Homework); baseline and integrated code use My homework and navigate to /student/homework. The failure reproduces on untouched 0831c65, and that teammate label was preserved.

## Files changed or added

Paths below are relative to `apps/lumeneios/`. Generated builds, installed dependencies and local verification snapshots/results remain ignored and are not integration source files.

- `backend/app/api/v1/assessments.py`
- `backend/app/lib/question_content.py`
- `backend/app/lib/question_distribution.py`
- `backend/app/modules/learnsphere/automation.py`
- `backend/app/modules/learnsphere/router.py`
- `backend/app/schemas/assessment_learning.py`
- `backend/app/schemas/assessments.py`
- `backend/app/services/assessment_guidance.py`
- `backend/app/services/assessment_learning.py`
- `backend/app/services/llm_service.py`
- `backend/app/services/panchapadi.py`
- `backend/tests/conftest.py`
- `backend/tests/test_assessment_security.py`
- `backend/tests/test_assignment_uploads.py`
- `backend/tests/test_homework_legacy_security.py`
- `backend/tests/test_learnsphere_automation_scope.py`
- `backend/tests/test_studio_assignment_school_audience.py`
- `backend/tests/test_studio_counts_and_deletion.py`
- `backend/tests/test_studio_integration.py`
- `docs/LEARNSPHERE_COMPARISON_INVENTORY.md`
- `docs/LEARNSPHERE_INTEGRATION_CONTRACT.md`
- `docs/LEARNSPHERE_INTEGRATION_REPORT.md`
- `src/components/common/ManualQuestionForm.tsx`
- `src/components/learnsphere/AssessmentQuestionSupport.tsx`
- `src/components/learnsphere/CompetencyReview.tsx`
- `src/components/learnsphere/LearnSphereResultReview.tsx`
- `src/context/DataContext.tsx`
- `src/lib/apiClient.ts`
- `src/lib/learnsphere.ts`
- `src/lib/questionStudio.ts`
- `src/pages/learnsphere/LearningSupport.tsx`
- `src/pages/teacher/AssessmentBuilder.tsx`
- `src/test/LearnSphereIntegration.test.tsx`
- `src/types/assessmentGuidance.ts`
- `tests/learnsphere-automation-ui.mjs`

## Subsequent seeded-database acceptance

The additional database task is documented in [LEARNSPHERE_DATABASE_ACCEPTANCE_REPORT.md](LEARNSPHERE_DATABASE_ACCEPTANCE_REPORT.md). It adds an isolated populated SQLite run, real HTTP workflow/restart/integrity checks and four-role browser acceptance. Those newer browser/database results supersede the earlier unexecuted-browser limitation in this first integration report. Successful AI-path tests use explicit acceptance model-text fixtures; native provider failure and saved-record behavior are checked separately. No original database or migration history was modified.
