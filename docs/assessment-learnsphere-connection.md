# Assessment results → LearnSphere

## Existing workflow inspected

AI Question Studio creates bank questions using its existing Qwen prompts, then creates an
`Assessment` for a class/subject with frozen `questions_json`, marks, competency metadata and
`scheduled` status. The student upload list already restricts these assessments through
`StudentAccountLink`, school, class and subject membership and strips answer keys.

Before this connection, student OCR upload saved transcription, not graded answers. The
dashboard practice quiz was a demonstration. The existing grade endpoint accepts educator
totals and competency scores and writes `assessment_submissions`, student live scores and
competency snapshots. Its aggregate payload does not retain question responses or scoring
provenance. Batch grading includes simulated results, and one OCR review path uses fixed
competency increments. Those paths cannot safely be assumed to establish genuine
question-level understanding.

## Connection implemented

The existing assessments, question snapshots, account links, school/class authorization,
assessment submissions and competency dimensions are reused. No second assessment definition
or assignment system was created. Student dashboard **My assigned assessments** adds answer
submission to the existing scheduled assessments. Studio's **Review submitted assessment
answers** panel provides educator review of those responses.

Endpoints under the existing `/api/v1/assessments` group:

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/{assessment_id}/answers` | Linked student submits their own actual answers |
| GET | `/my-results` | Student's saved responses and feedback |
| GET | `/results-for-review` | Results within educator school/class scope |
| GET | `/results/{result_id}` | Authorized student, linked parent or educator result read |
| POST | `/results/{result_id}/review` | Educator review, correction and optional topic mapping |

Student identity and school are derived on the server. Clients cannot supply marks, student
IDs, school IDs or competency scores in answer submissions. Positions reference frozen
assessment questions, including their bank IDs, marks, rubrics, options and LU/CU/AU/CT.
Answer keys/rubrics are available to educators and are not exposed in student result reads.

MCQs are evaluated only against an unambiguous stored answer key. That score is explicitly
`automatic_key_unverified`, because an AI-generated stored key is not teacher verification.
Written responses, or MCQs without usable keys, retain unknown scores until reviewed.
No LLM grading or synthetic score fallback was added.

Once every question is scored, the existing `assessment_submissions` row stores the total,
maximum and percentage. Mixed assessments awaiting written grading do not publish an
incomplete total: the new result API returns unknown overall marks until review. Automatic
scores do not update student live competencies. Teacher review publishes weighted question
scores by assessed competency and updates only those measured student dimensions.

Legacy submission competency columns are non-nullable. Unassessed dimensions in a new
submission have compatibility placeholders; they are not used as evidence. The source's
question outcomes retain unknown values, and LearnSphere derives evidence exclusively from
the latest verified outcomes, never these legacy columns or student baseline/default values.

## Minimal additive schema

Existing `learning_evidence` requires non-null activity assignment and attempt foreign keys.
Using it for assessments would fabricate activity relationships or require rebuilding the
SQLite table to change those constraints. Revision `0002_assessment_results` therefore adds
one companion table: `learning_assessment_results`.

It holds references to the existing assessment/student/school/class/subject and an optional
existing assessment submission, frozen questions and actual answers, original automatic
outcomes, append-only teacher review revisions and an optimistic version. It does not create
`LearningActivity`, `LearningAssignment` or `LearningAttempt` records for assessments.

One result per assessment/student is enforced by a unique constraint. An exact request-key
retry returns the saved response; changed or repeated final submissions return 409. Student
responses lock on submission. Teacher corrections update the same published submission and
append review history; original automatic marks remain unchanged in the source record.
Only the latest valid review contributes observations, so retries/revisions do not inflate
evidence. Concurrent stale reviews return 409.

The migration creates only the new table and its indexes/constraints; it does not alter,
rebuild, reseed or delete existing application tables or records. SQLite execution and
PostgreSQL offline DDL are tested. Use the existing backup/rehearsal migration runner:

```powershell
.venv/Scripts/python.exe -B -m backend.scripts.migrate_learnsphere --database lumeneios.db
.venv/Scripts/python.exe -B -m backend.scripts.migrate_learnsphere --database lumeneios.db --apply
```

The second command creates a fresh verified backup, rehearses on a copy and applies only
after source checks, inside an exclusive SQLite transaction. Database configuration is unchanged.

## Eligibility, topics and recommendation rules

LearnSphere's source adapter validates the student/assessment/submission/school/subject chain,
the latest teacher review, per-question marks/maximum and consistency with the published total.
If another writer changes that total outside the reviewed source, it stops qualifying until
the source is reviewed again. Original automatic outcomes remain visibly unverified. Legacy
aggregates and simulated grading records are not automatically promoted or backfilled.

No existing verified topic mapping was found in assessment question schemas. Outcomes are
therefore unmapped initially. During review an educator can explicitly choose a LearningTopic
matching the assessment's class, school and subject. No text matching or inferred chapter
names are used. Unmapped observations remain visible at subject/competency level.

Learning Support exposes separate `assessment_findings`, with reviewed source marks,
denominators, correctness, provenance, assessment count and suggested review of partially
credited responses. Assessment questions never contribute to the activity-rule counters.
The existing three-observations-across-two-distinct-activities rule is unchanged.

Learning Journey exposes `assessment_observations` and actual assessment submission/review
events. Assessment events have no Panchapadi stage, and do not increase activity participation
or completion counts. One assessment does not generate an invented improvement trend.

## Verification and actual student testing

The final full backend suite passed **538 tests**, with **4 existing opt-in model tests skipped**. The 11 dedicated connection tests also passed separately.
New integration tests cover real answer persistence in an isolated database, server-derived
identity, weighted competency evidence, pending written scores, duplicate prevention,
unverified versus reviewed outcomes, review revision replacement, unmapped/explicit topics,
unauthorized users, changed-total exclusion and portable additive migration SQL.
A publication regression additionally enables SQLite foreign-key enforcement. Existing LearnSphere regression tests remain intact; its migration table-count assertion now
includes the one new source table. Production build and the three browser suites cover
existing Studio/LearnSphere and the new answer/review/support screens.

All automated student responses were synthetic fixtures in isolated test databases or
intercepted browser responses. No real student outcome was manufactured or inserted.

To test actual use:

1. Start the existing backend and frontend after applying the migration.
2. A teacher creates and assigns an assessment through Studio to a valid class/subject.
3. A linked student opens their dashboard, expands **My assigned assessments**, answers
   every question and selects **Submit assessment answers**.
4. Automatic MCQ scores remain visibly unverified. Written questions await teacher grading.
5. The authorized teacher opens Studio's **Review submitted assessment answers**, verifies
   each score/correctness, provides feedback and optionally selects verified topics.
6. Select **Confirm reviewed assessment results**. Open that student's LearnSphere Support
   and Journey; verify original marks, competency, provenance and unmapped/mapped topic state.
7. Retry the response/review request: no additional activity or duplicate observation should appear.

The existing transcription-only upload is still transcription-only. Legacy aggregate grades
without genuine per-question source data cannot be certified retrospectively by this bridge.
Use the real response/review flow above rather than the demonstration practice quiz.

## Current workspace verification

Revision `0002_assessment_results` has been applied through the verified backup/rehearsal
runner. The pre-upgrade backup is
`migration_backups/learnsphere-35b8f11983e349048130b030f273a689.backup.db`.
Read-only checks confirmed all pre-existing application table record fingerprints unchanged
(excluding Alembic's version marker), SQLite integrity `ok`, zero declared-FK violations,
and zero rows in the new assessment source table. No real student response/result was inserted.
The database URL/configuration was not changed. No commit, push or merge was performed.

A final-suite test-isolation issue was found and fixed: the FK-enforcement test now closes
its session and disposes its temporary connection pool so later tests do not inherit PRAGMA
settings. No tests were skipped or assertions weakened to conceal that issue.
