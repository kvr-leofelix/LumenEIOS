# LearnSphere improvements — 13 November 2026

## Delivered

Learning Support now starts with a submitted-assessment selector showing name, subject and assessment date. Only the selected student's authorized results are listed. Selecting a result fetches that assessment's own questions, saved answers, evaluated marks, correctness, competency and mapped Panchapadi stages. It shows persisted, question-specific expected concepts, supported gaps, improvement explanations, practical exercises and optional practice questions. The selected assessment's five-stage table and distribution chart are here rather than in Journey. Independent stage percentages need not total 100.

Question guidance is generated through the existing Qwen integration after submission/evaluation and review, and is saved inside the existing result metadata. Teacher-reviewed question outcomes take precedence over automatic marks. AI advice remains explicitly provisional even when its source marks have been teacher-reviewed. Unknown/full-credit outcomes cannot acquire an asserted misconception through this generator; absent keys/rubrics cannot acquire an invented expected concept. Missing guidance and unknown scores have explicit states, never a default zero. Students/parents do not receive teacher-only scoring explanations or unverified stored answer keys. Verified MCQ keys are available as feedback only for that student's already submitted result; educators can inspect stored keys.

Teachers can inspect question-wise advice in Learning Support, refresh it explicitly, and review marks in the existing Studio. The refresh regenerates advice while preserving answers and earlier evaluations/reviews. Students and parents cannot force that educator refresh. Ordinary retries reuse successful work; GET requests never run inference or create assignments. Historical results without per-question advice require one educator refresh; no historical responses or reviews were backfilled or rewritten during this implementation.

General activity-based support remains available in a collapsed section, and custom support interventions remain available. Aggregate feedback from unrelated assessments is no longer mixed into the selected assessment's guidance. Existing approved support suggestions remain associated with their source assessment.

Learning Journey now contains only the five assessment progress charts. Its activity-completion counters, repeated question observations and Learning history display were removed without deleting any underlying records or API history. Green solid series show teacher-confirmed stage scores; amber dashed series show provisional scores separately. Single observations render visible dots, missing values have no dots and do not become zero, and lines do not bridge insufficient/unverified gaps. Chronological assessment submission timestamps and assessment names are available in labels/tooltips. No intermediate observations or single-assessment improvement claims are created. The existing history API defaults to confirmed-only behavior; the charts explicitly request `include_provisional=true`.

## Automatic activities

A successful evaluation now assigns one Teach-Back challenge and one Real-Life Mission through the existing `learning_activities`, `learning_assignments` and `learning_attempts` structures. Stable IDs derived from the saved result and activity kind enforce one automatic assignment of each kind per assessment/student, independent of retries or teacher-review revisions. Activities use genuine saved model drafts and evidence references. Assignment snapshots clearly label their origin `automatic_provisional`; no teacher verification, student response, completion or scored evidence is manufactured.

Assignments are scoped through the actual result's school/class/subject, current enrollment and authorized class teacher. That teacher is the responsible educator in the existing assignment ownership fields; the automatic-origin marker distinguishes this from a teacher approval. A missing/inconsistent enrollment or authorized teacher leaves a clear warning and a retryable state rather than inventing an owner or changing relationships.

No topic is inferred or created. If the relevant reviewed outcomes share an existing verified topic, it is reused. Otherwise the topic link is null and the display says `Topic unmapped`. Unmapped activities do not get pooled as though they were a verified concept in the three-observations/across-two-activities support rule. Actual completion and observations can still be recorded through existing reviews; mapped custom follow-ups remain available for comparable topic-based support.

The existing custom Teach-Back and mission creation controls are retained alongside automatic assignments. Students submit actual responses through the existing workflow; Teach-Back uses its existing structured Qwen feedback and retry history. Teachers review actual attempts and record completion. Assignment snapshots retain the instructions/rubric that were assigned; refreshing assessment guidance does not silently rewrite past assigned work or create replacement duplicates.

## Database and preservation

Migration `0004_unmapped_activities` relaxes only `learning_activities.topic_id` from required to nullable. This is necessary to reuse genuine activity assignments without inventing syllabus topics. There are no new tables, columns, dependencies, providers or job platforms. PostgreSQL uses `ALTER COLUMN DROP NOT NULL`; SQLite requires Alembic's table-copy mechanism for the nullability change. Existing rows, indexes, foreign keys and all three activity CHECK constraints are retained. Custom teacher-created activities still require a verified topic through their existing API.

The migration was applied to this project's configured `lumeneios.db` after verified backup and rehearsal. Backup: `migration_backups/learnsphere-e02ad6d2383f4ad2ab4b15b151a05e67.backup.db`. Independent read-only comparison confirmed every original table value was preserved except the migration revision; integrity passed and foreign-key check results were unchanged. No student, school, class, assessment, original response or review values changed. The original `arena-clean` project/database was not accessed.

Downgrade refuses to restore the non-null constraint while unmapped activities exist, preventing destructive rollback or invented mappings. Retain the relaxed constraint when rolling back application code unless genuine topic mappings have been reviewed separately.

## Files changed

- New backend support adapter: `backend/app/services/assessment_guidance.py`.
- Existing worker/approval/model integration: `backend/app/services/panchapadi.py`, `assessment_learning.py`, `llm_service.py`; `backend/app/api/v1/assessment_results.py`.
- Contracts: `backend/app/schemas/assessment_learning.py`, `panchapadi.py`; `backend/app/modules/learnsphere/schemas.py`.
- Existing activity/evidence APIs: `backend/app/modules/learnsphere/models.py`, `router.py`, `evidence_service.py`.
- Migration: `backend/migrations/versions/0004_unmapped_activities.py`.
- New frontend support: `src/components/learnsphere/AssessmentQuestionSupport.tsx`, `src/types/assessmentGuidance.ts`.
- Existing frontend: `src/pages/learnsphere/LearningSupport.tsx`, `LearningJourney.tsx`, `ActivityWorkspace.tsx`; `src/components/learnsphere/PanchapadiEvaluation.tsx`, `PanchapadiProgress.tsx`.
- Frontend clients/contracts: `src/lib/learnsphere.ts`, `assessmentResults.ts`; `src/types/learnsphere.ts`, `panchapadi.ts`.
- Tests: `backend/tests/test_learnsphere_improvements.py` (13 new tests), `conftest.py`, `test_assessment_learning_automation.py`, `test_assessment_learnsphere_connection.py`; `tests/assessment-results-ui.mjs`, `tests/learnsphere-ui.mjs`. Existing assertions expecting zero assignments were updated for the requested automatic assignments while keeping zero attempts/completions/evidence assertions.
- Documentation: this report and `docs/learnsphere-implementation-report.md`.

## Verification

- Full backend suite: **581 passed, 4 opt-in tests skipped**. A final focused run after small guard/read-adapter refinements passed **22 tests**.
- New tests cover scoped selection, actual answers, per-question advice, reviewed outcome preference, forced educator refresh, all four role families and denied accounts, provisional/confirmed graph data, missing marks/advice, no invented expected concept or unknown weakness, automatic assignment/access/retry behavior, unchanged completion counts, and migration preservation/CHECK constraints/PostgreSQL SQL.
- All three isolated Chrome scripts passed: Studio regression, LearnSphere custom creation/student feedback/teacher-parent/mobile regression, and assessment submission/review plus selector isolation, selected distribution, exactly five Journey charts, missing-evidence gaps and one-dot rendering. API calls were intercepted with synthetic fixtures; browser tests never mutated actual records.
- Production TypeScript/Vite build passed, retaining the existing large-bundle advisory. No new dependency was installed.

## Remaining limits

Restart the backend/frontend as appropriate to load the changes. New submitted assessments automatically enter the pipeline. Use **Learning Support → select the historical assessment → Refresh assessment guidance** once for older results that predate question-wise guidance and automatic assignment.

Live model quality and latency are not guaranteed. CPU-only inference may take minutes or time out; saved responses remain intact and the UI shows warnings and retry states. This task used isolated synthetic tests rather than generating additional real student results. Background inference remains in-process, with the existing running lease/retry behavior. A live PostgreSQL deployment was not tested. No commit, push or GitHub operation was performed.
