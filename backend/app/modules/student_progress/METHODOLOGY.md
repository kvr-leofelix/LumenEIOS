# Subject-specific competency scoring methodology

## Scope

Subject-specific LU / CU / AU / CT reporting is a **read-only projection** over verified
assessment evidence. Global `students.*` live scores and unscoped
`student_competency_snapshots` rows remain unchanged and are **never** used to invent
subject scores.

## Eligible evidence

Included:

- `AssessmentSubmission` rows joined to an `Assessment` in the student's school with
  status in `{scheduled, graded, closed}`.
- Teacher-approved OCR evidence **only after** it is published as an
  `AssessmentSubmission` (same table). Orphan `HumanReview` rows contribute to mark
  history elsewhere but **do not** supply LU/CU/AU/CT vectors.
- Scored differentiated remediations (`HomeworkRemediation` with a non-null `score`)
  contribute to **one** dimension (`competency_target`) only, never a fabricated
  full vector.

Excluded:

- AI suggestions / unverified engine drafts.
- Global competency snapshots without `subject_id`.
- Global live student competencies as a subject fallback.
- Rejected / pending / draft OCR reviews.

## Deduplication

For each `(assessment_id, student_id)` pair, only the **latest** submission
(by `created_at` / `submission_date`, then `id`) is kept. This prevents OCR publish +
manual grade double-counting the same assessment.

Homework remediations are unique by remediation `id`.

## Normalization

Competency dimensions on submissions are already stored on a **0–100 comparable scale**.
Subject dimension scores are the **unweighted arithmetic mean** of those comparable
dimension values across the deduplicated evidence set for that subject.

We **do not** average raw `marks_obtained` across assessments with different
`total_marks` when computing LU/CU/AU/CT. Mark percentages remain a separate
performance metric (`awarded ÷ max`).

Homework `score` is treated as a 0–100 value for its single `competency_target`.

## Availability

| Condition | API representation |
|---|---|
| No eligible evidence for the subject | `status=unavailable`; all dimension values `null`; `evidence_count=0` |
| Evidence present for some dimensions only | `status=partial`; missing dimensions `null`; counts exposed |
| All four dimensions have ≥1 evidence point | `status=available`; `overall` = mean of the four |

Missing values are **never** coerced to zero.

## Overall subject score

`overall` is computed only when all four of LU, CU, AU and CT are available.
Otherwise `overall` is `null`.

## Historical / global behaviour

- `GET .../progress/competencies` without `subject_id` continues to return global live
  scores + unscoped snapshot history.
- New snapshot writes may optionally store `subject_id` / `source_assessment_id` for
  forward compatibility; historical rows keep `subject_id = NULL` and stay global.
