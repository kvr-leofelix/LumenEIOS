# Automated assessment-to-learning workflow

## Why the five activity values were zero

`journey.stages` counts distinct, actually completed LearnSphere assignments by their activity stage. Assessment reviews are a different source and deliberately do not increment those counts. The Science result had saved answers and two reviews, but no Panchapadi evaluation metadata. Its reviews did not explicitly confirm stage mappings. Thus an assessment review alone could neither complete an activity nor publish verified stage scores.

The UI now labels **Panchapadi activity completion** separately and explains the distinction. **Panchapadi assessment performance** shows an assessment selector, five-row Stage/Score/Evidence/Status table and a separate distribution bar chart. These five percentages are independent scores, not shares totalling 100. Missing evidence has no score or bar. Learning Journey retains exactly five separate historical line graphs using only confirmed stage evidence; provisional evaluations appear in the selected-assessment section instead.

## Integrated processing

The existing submission route still saves and locks actual answers, freezes questions, performs deterministic MCQ marking and schedules background evaluation. It does not call a second assessment system. The worker now:

1. Reads frozen questions, original maximum marks, actual responses and question-specific keys/rubrics.
2. Provisionally marks written responses with the existing Qwen transport. Marks are bounded integers; partial credit has `correct=false`, with separate student-ready feedback and teacher-only scoring explanation. Missing rubrics/answers, invalid output, unavailable inference or oversized input leave marks unknown for teacher review.
3. Classifies actual cognitive demand independently of competency labels and calculates all five weighted stage percentages using eligible real marks. Existing prerequisite, procedural-practice and independent-extension gates remain; Abhyas requires two scored procedural questions. Insufficient stages identify additional evidence needed, rather than claiming mastery or assigning zero.
4. Selects up to three actual incorrect/partial responses, or enrichment evidence when no gap is demonstrated, and generates one support/practice draft, one Teach-Back draft and one Real-Life Mission draft. Inputs include the real subject, only explicitly mapped topic titles, responses, marks and stage evidence. Every draft references actual supplied question positions and contains explanation, tip, scenario, instructions, expected submission format, objective and rubric.

MCQs use their unambiguous stored keys with unverified provenance by default. A teacher can explicitly verify an MCQ key during review; later submissions to that assessment reuse verification only when the frozen stem, options, key and maximum match. These automatically marked student results still require teacher confirmation. Model-produced written grades are always provisional.

The existing generation prompt has an additive Panchapadi coverage objective while retaining requested source scope, counts, competency totals and Bloom constraints. It asks for readiness, understanding, two procedural practice questions, application and independent extension where compatible. Small or tightly constrained papers may not cover every stage; coverage is never forced through relabelling.

## Teacher control and publication

In **AI Question Studio → Review submitted assessment answers**, automatic marks, feedback and scoring explanations prefill the existing controls. An overall evidence summary and weighted competency percentages show strengths, partial understanding, incorrect responses and unknown dimensions. The teacher can edit question marks, correctness, feedback and teacher-only explanations; edit stage mappings and reasons; and explicitly confirm stages. Stage scores are recalculated from corrected marks and eligible mappings rather than accepting an unsupported percentage override.

The same panel contains editable support, Teach-Back and mission drafts. Each can be left as a draft, approved or rejected. All content, stages and evidence references are editable; teachers can author content when inference fails. A **Load refreshed AI suggestions as drafts** action makes updated suggestions available without overwriting edits. Review confirmation schedules fresh draft generation against the newly confirmed marks. Publication remains an explicit educator decision.

Approval uses existing `learning_activities` and `learning_assignments`. A verified existing topic in the assessment's school/class/subject is required for challenge and mission assignment. Unmapped support tips can be approved as suggestions without an assignment. No topic is inferred from text. A teacher may create an appropriate topic through the existing LearnSphere controls, then select it on the draft.

Approved tips appear in Learning Support and the selected assessment's performance section with source question references. Approved Teach-Back and missions appear in their existing student sections. Their assignment snapshots retain source assessment/result references and question positions. The existing authoring/assignment controls can edit templates and reassign approved missions. New approved content creates a new assignment; unchanged approval reuses the existing assignment. Rejecting a draft does not delete past assigned work or its history.

Students submit their own explanations or mission findings through the existing activity workflow. Responses are saved, Teach-Back receives structured AI feedback, and attempts/retries and teacher reviews retain their existing protections. Generated work is not marked completed. Actual teacher-recorded activity completion and scored observations remain separate from assessment evidence. The three-observations-across-two-activities recommendation rule is unchanged.

## Persistence, history and safety

No new table or migration is needed: automatic marks and draft revisions use the existing nullable `panchapadi_json` attempt history and independent `panchapadi_version`; explicit teacher decisions and approved assignment references are appended inside new existing review revisions. Original `automatic_json`, frozen responses and older reviews are preserved. Confirmed marks still publish through the existing assessment submission/competency service.

Frozen inputs plus the latest review form an evaluation fingerprint. Completed work is cached; identical running requests share a lease. A draft-only retry retains completed classification and written marks. Changed teacher reviews get a new fingerprint. Compare-and-swap metadata writes and deterministic source/content assignment IDs protect against retries and late results. Database transactions do not span inference. GET requests do not start model calls or create assignments.

Prompts exclude account and roster identifiers, source filenames, school IDs and student IDs. Known student names and contact-like text are redacted from educational inputs; student text is treated as untrusted data. Student/parent result responses omit keys, rubrics, draft plans, raw AI mapping reasoning and teacher-only scoring explanations. Approved generated-activity rubrics remain teacher-only. Approved student-ready explanations/tips and published instructions are separate from scoring explanations.

Historical processing uses `backend/scripts/reprocess_assessment_learning.py --result-id <existing-id> --apply`. It uses the configured existing SQLite file, creates and verifies a backup, checks relationship consistency, runs only the metadata worker, and verifies every original column and all unrelated metadata remain unchanged. It does not import application startup, seed, migrate or initialise the database. It never substitutes AI grades for existing teacher-confirmed marks, appends a teacher review or silently verifies inferred mappings.

## Files changed for this extension

- New backend contracts: `backend/app/schemas/assessment_learning.py`.
- New approval adapter: `backend/app/services/assessment_learning.py`.
- Existing pipeline: `backend/app/services/panchapadi.py`, `assessment_results.py`, `llm_service.py`; `backend/app/schemas/assessment_results.py`, `panchapadi.py`; `backend/app/api/v1/assessment_results.py`.
- LearnSphere response/security adapters: `backend/app/modules/learnsphere/schemas.py`, `router.py`.
- Historical runner: `backend/scripts/reprocess_assessment_learning.py`.
- New UI: `src/components/learnsphere/AssessmentLearningEditor.tsx`, `AssessmentPerformanceSummary.tsx`.
- Existing UI: `src/components/common/AssessmentResultsReview.tsx`, `StudentAssessments.tsx`; `src/components/learnsphere/PanchapadiEvaluation.tsx`, `LearningTimeline.tsx`; `src/pages/learnsphere/LearningJourney.tsx`, `ActivityWorkspace.tsx`.
- Frontend contracts: `src/types/assessmentResults.ts`, `panchapadi.ts`, `learnsphere.ts`.
- Tests: `backend/tests/test_assessment_learning_automation.py`, `backend/tests/conftest.py`, `tests/assessment-results-ui.mjs`.
- Documentation: this report and links/updates in the existing assessment/Panchapadi documentation.

## Existing reviewed Science result

Historical processing found four saved answers and two original review revisions. Both revisions, original question/response JSON, teacher-confirmed marks and every other original column passed comparison with the verified pre-processing backup. No school/class relationships, activities or completions were manufactured.

The local model produced these stage hypotheses using the existing teacher-confirmed marks:

| Stage | Percentage | Evidence | Publication status |
| --- | --- | --- | --- |
| Adheeti | 100% | Q1, 2/2 marks | Provisional mapping; teacher must check prerequisite relevance |
| Bodh | 100% | Q2, 2/2 marks | Provisional mapping |
| Abhyas | Insufficient evidence | Q3, 3/5 marks, only one candidate procedural question | No percentage; two scored procedural questions required |
| Prayog | 40% | Q4, 2/5 marks | Provisional mapping |
| Prasar | Insufficient evidence | No eligible independent-extension question | No percentage |

**None of these stage mappings is teacher-verified yet.** Existing teacher confirmation applies to the question marks, not automatically to newly inferred cognitive stages. In particular, the model's Adheeti interpretation of a definition question needs scrutiny: ordinary recall alone does not establish prerequisite readiness. The teacher can correct/exclude any mapping and publish a new explicit stage review without altering either original review. Until then, confirmed historical graphs correctly have missing stage values rather than invented verified points.

The original backup is `migration_backups/assessment-learning-88e23ddb58cb407690d4155c99742317.backup.db`; each explicit retry also creates its own verified backup. One local draft request timed out, leaving completed classification intact. The retry path reuses that classification. An additional content check rejects suggestions based only on fully correct answers when incorrect/partial evidence exists, with one corrective model retry before a clear failure/manual-authoring path.

Generation now requests one bounded draft per kind, validates actual gap references and aggregates the three drafts into the existing saved evaluation. This avoids requiring the CPU model to finish a large three-draft object in one response. When weaknesses exist, the prompt includes only the selected actual incorrect/partial question responses; overall strengths remain visible in the assessment performance summary.

## Verification

The full isolated backend suite passed **568 tests, with 4 opt-in tests skipped**. The nine new automation tests cover written marking and transport validation, confirmed-key reuse, historical preservation, editable/approved content, approval rollback, student access, duplicate assignments/attempts, failed generation retries, semantic correction and privacy redaction. The focused suite passed after splitting draft generation into bounded requests.

All three intercepted Chrome scripts passed: assessment submission/review and performance table/distribution/five historical graphs; Question Studio generation/assignment/bank regression; LearnSphere authoring, student responses, AI retry, teacher/parent and mobile regression. No browser request wrote to the actual database. The TypeScript/Vite production build passed with the existing large-bundle advisory.

## Deployment and limits

Reuse the existing database/model configuration and restart the backend to load the new worker. No dependencies, roster changes, resets, seeding, commits or pushes are required. Ollama must be running; CPU-only inference can be slow or time out. Errors preserve answers and previous reviews, expose a clear retry/manual-authoring path and never publish unverified outcomes. Background tasks run in-process; stale leases can be retried after 30 minutes following a restart. PostgreSQL compatibility uses existing SQLAlchemy/JSON structures and uniqueness protections; this extension has not been exercised against a live PostgreSQL service.

Model classification and feedback require educator scrutiny. In particular, ordinary recall is not automatically proof of prerequisite readiness, and routine application is not independent extension. Historical mappings remain provisional until a real teacher confirms a new review. The system does not impersonate that teacher to populate graphs.
