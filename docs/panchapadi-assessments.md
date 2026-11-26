# Panchapadi assessment extension

Student assessment submission schedules a provisional Panchapadi evaluation after the existing answers and automatic outcomes have committed. It uses the existing Qwen/Ollama service, frozen questions, expected answers, rubrics and actual responses. The subsequent [automated marking and personalised learning extension](assessment-learning-automation.md) adds provisional written marking and educator-approved support/challenge/mission drafts to this same pipeline. Unknown or unavailable marks remain unknown; classification does not invent marks.

## Evaluation and verification

Qwen classifies actual cognitive demand, with a separate explanation for each question/stage mapping. Competency labels are context, never a fixed LU/CU/AU/CT lookup. Each real question must occur exactly once in the classification and can have no stages, one stage or several justified stages.

| Stage | Evidence required | Minimum scored questions |
| --- | --- | --- |
| Adheeti — Prepare | Explicit prerequisite/prior knowledge or readiness demand, with prerequisite flag | 1 |
| Bodh — Understand | Conceptual understanding, explanations or relationships | 1 |
| Abhyas — Practise | Performing learned procedures, with procedural-practice flag | 2 |
| Prayog — Apply | Applying knowledge in unfamiliar or real-life situations | 1 |
| Prasar — Extend | Independent extension, new connections or deeper exploration, with extension flag | 1 |

The Abhyas threshold is a conservative within-assessment evidence gate, not a claim of consistent practice or mastery. Routine application alone cannot establish Prasar. Teachers must verify the cognitive classification as well as marks.

For each stage, the score is `100 × sum(actual earned marks) / sum(eligible question maximum marks)`. Missing, non-finite, out-of-range or inconsistent marks are excluded with reasons. The denominator includes only eligible scored questions. A stage below its minimum has a null percentage and `Insufficient evidence`; a genuinely scored zero remains zero. All five stages are always returned, with counts, available marks, question references, explanations and exclusions.

In Question Studio's **Review submitted assessment answers**, teachers see all five automatic evaluations, edit mappings and reasons, clear stages to exclude questions, and verify the three special demand flags. They explicitly select **Confirm the corrected Panchapadi mappings and exclusions with this review**. The server recalculates stage scores from the submitted teacher-confirmed question marks and appends the snapshot to the existing immutable review revision. Later corrections append another revision. Existing review clients that omit stage confirmation do not silently publish AI mappings.

Only the latest eligible teacher review can publish historical stage scores. Changing marks without confirming stages leaves a graph gap for that review instead of retaining stale scores. Existing topic mapping remains explicit and optional; stages do not infer topics.

## Persistence and migration

`0003_panchapadi`, following `0002_assessment_results`, adds only two nullable columns to `learning_assessment_results`: `panchapadi_json` for automatic attempt history and `panchapadi_version` for independent optimistic concurrency. Student, school, class, subject, assessment, answers and questions reuse the existing result record. Verified stage snapshots live inside newly appended `reviews_json` entries, including their revision and timestamp. No new tables or dependencies were introduced.

Successful inference is cached by the frozen-input fingerprint. A running lease and compare-and-swap writes prevent concurrent retries from duplicating completed evaluations; failures are retained and can be retried. Background metadata does not change the teacher-review version or overwrite reviews. No database transaction spans model inference. Full responses are batched rather than silently truncated; oversized individual inputs fail safely to manual teacher mapping.

The migration was applied to the project's existing SQLite database after a verified backup and rehearsal. Backup: `migration_backups/learnsphere-ea52f30f357b4cba8bd77cc4da1b15e8.backup.db`. Independent read-only verification confirmed original column values and review contents were preserved, SQLite integrity passed, foreign-key check results were unchanged, and all historical rows retained null new columns. No student, enrollment, school or teacher relationships were changed.

The migration runner now fingerprints original columns when validating additive migrations. PostgreSQL offline SQL is tested; a live PostgreSQL deployment was not exercised. Downgrade removes the columns only when no stage history exists; it refuses to destroy recorded evaluation history. For a populated deployment, roll back application code while retaining the additive columns unless history has been archived through a separate approved process.

## LearnSphere and graphs

**Learning Support** and **Learning Journey** show assessment-stage evaluations separately from activity evidence. **LearnSphere → Learning Journey → Panchapadi Progress** contains exactly five separate Recharts line graphs, one per stage. Their axes show assessment submission date/time and verified percentage from 0 to 100; tooltips show assessment names, dates and marks. Points are chronological. Reviewed assessments without sufficient confirmed stage evidence have null values, and lines do not connect across those gaps. Empty and single-point states avoid invented improvement claims.

APIs, protected by existing student access checks:

- `GET /api/v1/learnsphere/students/{student_id}/panchapadi`: all five histories.
- `GET /api/v1/learnsphere/students/{student_id}/panchapadi/{stage}`: one stage history.
- `POST /api/v1/assessments/results/{result_id}/panchapadi/evaluate`: authorized retry; parents cannot invoke it.

The existing submission endpoint schedules evaluation; result responses expose provisional metadata. GET requests never trigger model inference. Assessments do not write `learning_evidence`, create activities or assignments, or increment activity completions. The existing three-observations-across-two-activities support rule is unchanged.

## Changed files

Backend:

- `backend/app/schemas/panchapadi.py` (new contracts and validation).
- `backend/app/services/panchapadi.py` (new scoring, worker and history adapter).
- `backend/app/services/llm_service.py` (separate structured classification operation).
- `backend/app/modules/learnsphere/assessment_models.py` (nullable metadata columns).
- `backend/app/schemas/assessment_results.py`, `backend/app/services/assessment_results.py`, `backend/app/api/v1/assessment_results.py` (submission scheduling, result output and review confirmation).
- `backend/app/modules/learnsphere/schemas.py`, `evidence_service.py`, `router.py` (relative to that module; support, journey and history APIs).
- `backend/migrations/versions/0003_panchapadi.py`, `backend/scripts/migrate_learnsphere.py`.

Frontend:

- `src/types/panchapadi.ts`, `src/types/assessmentResults.ts`, `src/types/learnsphere.ts`.
- `src/lib/assessmentResults.ts`, `src/lib/learnsphere.ts`.
- `src/components/learnsphere/PanchapadiEvaluation.tsx`, `PanchapadiMappingEditor.tsx`, `PanchapadiProgress.tsx` (new components).
- `src/components/common/StudentAssessments.tsx`, `AssessmentResultsReview.tsx`.
- `src/pages/learnsphere/LearningSupport.tsx`, `LearningJourney.tsx`.

Tests/documentation:

- `backend/tests/test_panchapadi.py` (19 tests), `backend/tests/conftest.py` (isolated inference fixture), `backend/tests/test_assessment_learnsphere_connection.py` (scope the previous migration assertion to revision 0002).
- `tests/assessment-results-ui.mjs`, `tests/learnsphere-ui.mjs` (intercepted browser fixtures and assertions).
- This report, `docs/learnsphere-migrations.md`, `docs/question-studio.md`.

## Verification and limits

The full isolated backend suite passed: **559 passed, 4 opt-in tests skipped**. Coverage includes all stages, multiple mappings, exclusions, weighted marks, unknown versus zero, provisional versus confirmed results, corrections and immutable revisions, retry/cache handling, concurrency with late inference, chronological gaps, all five endpoints, authorization and migration preservation. No synthetic fixtures were inserted into the actual database.

All three Chrome UI scripts passed: assessment answer/review and five graphs, Question Studio regression, and LearnSphere authoring/student/review/parent/mobile regression. Requests were intercepted with synthetic fixtures. The graph check verifies exactly five charts, no drawn lines for empty stages, and no segment bridging a null middle point. The production TypeScript/Vite build passed; Vite reports its existing large-bundle advisory.

Live model classification quality and an actual student's end-to-end submission were not newly verified. Qwen/Ollama must be available using the existing configuration; invalid/unavailable inference leaves saved answers intact and permits teacher mapping or retry. Background work runs in-process, not a durable queue; after a restart a stale running lease can be retried after 30 minutes. Teachers may map and confirm stages immediately without waiting. Historical results/reviews are not automatically reclassified or rewritten: use the authorized retry and a new explicit teacher review when appropriate. No question bank, roster, database configuration, commits or pushes were changed by this extension.
