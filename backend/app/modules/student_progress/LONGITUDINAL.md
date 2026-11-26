# Longitudinal Student Progress — methodology & evidence foundation

## Relationship to existing work

This builds on Unified Student Progress. It does **not** replace:

- `subject_competency.v1.mean_of_comparable_0_100`
- Teacher/principal `EducatorProgressReport` / student-parent `LearnerProgressReport`
- School-scoped access and learner release filters

Longitudinal reporting is a **time-indexed projection** over the same verified evidence.

## Snapshot ≠ historical evidence

`StudentCompetencySnapshot` rows are point-in-time **checkpoints** (often global,
`subject_id = NULL`). They cannot alone reconstruct a subject-specific monthly
timeline. Monthly scores must be derived from dated evidence (submissions,
reviewed homework, verified OCR published as submissions).

Unscoped snapshots remain available as global history only.

## Academic evidence observation (logical record)

Every eligible observation exposes:

| Field | Source |
|---|---|
| student_id | submission / remediation / review |
| subject_id | Assessment.subject_id or HomeworkRemediation.subject_id |
| competency | LU/CU/AU/CT (vector dims or homework target) |
| source_type | assessment_studio / answer_sheet_ocr / differentiated_homework |
| source_id | submission id / remediation id |
| assessment_id | assessment id when applicable |
| awarded_marks / max_marks | marks or homework score/100 |
| normalized_score | 0–100 comparable dimension value |
| assessed_on | submission_date / reviewed_at / due_date |
| academic_year / month_key / term_id | derived from school calendar config |
| verification_status | verified (published submission / reviewed HW) |
| release_status | released for learners when HW reviewed+scored; assessments graded/closed |
| methodology_version | scoring contract id |

AI suggestions and unverified OCR drafts are **never** observations.

## Deduplication

Same rules as subject competency:

- Latest `AssessmentSubmission` per `(assessment_id, student_id)`
- Skip orphan HumanReview when a matching submission exists
- Homework unique by remediation id
- Do not invent subject_id for global snapshots

## Scoring evolution

### Current production subject scores

`subject_competency.v1.mean_of_comparable_0_100` — unweighted mean of comparable
0–100 dimension values.

### Longitudinal checkpoints (v1)

`longitudinal.checkpoint.v1.equal_weight_verified`

For a subject × competency × period (month or term):

1. Collect verified observations in that period with a valid normalized_score.
2. Apply **reliability class weight** (not invented per-assessment weights):
   - `verified_assessment` (Assessment Studio / OCR published submission): **1.0**
   - `verified_homework` (reviewed scored remediation): **1.0**
   - Everything else: excluded (weight 0)
3. Score = Σ(score × weight) / Σ(weight). With equal class weights this equals
   the arithmetic mean of verified observations — transparent and defensible.
4. Missing period / competency → `null` / `unavailable` (never 0).

Future `longitudinal.checkpoint.v2` may introduce **documented** relevance and
coverage factors once rubric metadata is consistently stored. Until then we do
not invent arbitrary weights.

Provenance stored on every checkpoint response:

- methodology id
- evidence_count, assessment_count
- coverage (dims present / 4)
- observation source ids

## Academic calendar

Schools do not share identical term dates. Defaults (June–May academic year):

| Term | Months |
|---|---|
| T1 | Jun, Jul, Aug, Sep |
| T2 | Oct, Nov, Dec |
| T3 | Jan, Feb, Mar |
| T4 | Apr, May |

Override via school calendar config when present; otherwise use defaults.
`School.academic_year` (e.g. `2026-2027`) anchors year boundaries.

## Progress explanations

Deterministic rules only (no AI causation claims). Each finding cites observation
ids. AI intervention proposals are a later layer over these explanations and
never auto-assign or alter scores.
