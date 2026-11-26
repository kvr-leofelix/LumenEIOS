# Differentiated Homework: API Contract

**Status: draft for discussion.** Section 1 describes code that exists. Sections 2–4 are **proposed**: no teammate has agreed to them, and field names and meanings may change.

## 1. Existing endpoints (implemented)

Paths are under `/api/v1`. Authentication uses a bearer JWT from `POST /auth/login`.

### `POST /classes/{class_id}/homework`

Roles: admin, principal, teacher, with school access and a real bearer token (including in DEMO_MODE). The request class and student's class/school must match the path. Returns 201 with a homework object.

Request:

| Field | Type | Required |
|---|---|---|
| `student_id` | string | Yes |
| `class_id` | string | Yes |
| `subject_id` | string | No, defaults to `sub-math` |
| `title` | string | Yes |
| `competency_target` | string | Yes |
| `reason` | string | No |
| `description` | string | Yes |
| `due_date` | string | Yes |

### Homework object

Returned by the create and list endpoints:

`id`, `student_id`, `student_name`, `class_id`, `subject_id`, `title`, `competency_target`, `reason`, `description`, `due_date`, `status`, `score`

### Other endpoints

| Method and path | Response | Notes |
|---|---|---|
| `GET /classes/{class_id}/homework` | List of homework objects | Admin or school-authorized educator only |
| `GET /students/{student_id}/homework` | List of homework objects | Explicit StudentAccountLink/ParentStudentLink or authorized educator/admin; no ID matching |
| `POST /homework/{homework_id}/submissions` | `{"message", "score"}` | Linked student owner only; completion without grading; existing nullable score and reviewed state preserved |
| `GET /students/{student_id}/remediation/recommendation` | `{"competency", "title", "reason", "description"}` | Same student access as listing; existing fixed text blocks |

All these legacy operations require a real bearer token. They do not update formal assessment or competency records. For the separate snapshot-based draft/assignment/submission/evaluation workflow, see the [module README](../../apps/lumeneios/backend/app/modules/differentiated_homework/README.md).

**Not implemented, although `apps/lumeneios/docs/frontend-api-mapping.md` lists them:** `POST /homework/{homework_id}/assign` and `GET /students/{student_id}/remediation`.

## 2. Expected from the assessment engine (proposed)

Owner: Extracted Text Understanding, Assessment and Grading. **Not agreed.**

Homework needs to know what a student needs and how confident that conclusion is. A possible shape, per student and concept:

| Field | Purpose |
|---|---|
| `student_id`, `subject_id` | Who and what |
| `concept` | The specific concept, if available |
| `dimension` | The competency or assessment dimension |
| `evidence_state` | What the evidence shows, including an uncertain state |
| `observation_count` | How much evidence supports it |
| `suspected_causes` | Possible misconceptions or causes, marked as hypotheses |
| `blocking_prerequisite` | A prerequisite to address first, if any |
| `rule_version`, `source` | Which rules and data produced this |

**Open questions for the owner**
- Which dimensions and evidence vocabulary will be final?
- Is diagnosis delivered through an API call, shared tables or events?
- Do evaluated homework submissions count as assessment evidence?

**Until this exists,** homework may read the current `lu_score`, `cu_score`, `au_score` and `ct_score` as a clearly labelled temporary input. Those scores aren't reliable diagnostic evidence, because current grading paths are partly simulated.

## 3. Expected from AI Question Studio Beta (proposed)

Owner: AI Question Studio Beta. **Not agreed.**

**Existing today:** `POST /assessments/generate-questions-beta` and `GET /assessments/question-bank`. Beta generates questions from an uploaded chapter PDF with Qwen. The bank has no topic, difficulty or review state.

**Homework would need:**

| Need | Purpose |
|---|---|
| Search by subject, topic, competency, difficulty and cognitive level | Selecting suitable questions |
| A review state on questions | Students should only receive reviewed questions |
| A way to request questions for a specific gap | Filling shortfalls |
| Questions safe to show students | Without answers or rubrics |

**Open questions:** who owns the new question fields, and whether Bloom's level, a novelty level or both describe cognitive demand.

## 4. APIs for the frontend (proposed)

Owner: Frontend. **Not agreed, and not yet connected.** The homework screens currently use browser storage rather than this API.

**Available now:** the endpoints in section 1.

**Likely future endpoints, names not final:**

| Purpose | Possible endpoint |
|---|---|
| View a student's learning gaps | `GET /students/{student_id}/learning-gaps` |
| Generate draft homework | `POST /classes/{class_id}/homework/drafts` |
| Teacher approves, edits or rejects | `POST /homework/{homework_id}/approve` and similar |
| Student submits answers | `POST /homework/{homework_id}/submissions`, with a real request body |
| View feedback | `GET /homework/{homework_id}/feedback` |

**Compatibility:** changing the submission endpoint will alter its behaviour, so that change should be announced to the frontend owner first.

## 5. Time Aware Engine (proposed)

Owner: Time Aware Engine. **Not agreed.**

Approving a syllabus compression marks lessons `compressed_to_homework`, but doesn't create any homework. A future link could let those lessons produce draft homework for teacher review.


## Implemented live client

The default frontend uses the snapshot-based homework endpoints documented in the module README.
See [deployment readiness](../deployment-readiness.md) for the formal assessment endpoint matrix.
All formal assessment authoring, grade-write and result-list operations require a real educator
access token and authorized school context. Student/parent roles cannot read authoring snapshots
or submit formal grades. Homework result access remains through explicit student/parent links,
released evaluations only. Offline demo routes have no live API writes.

### Parent discovery (read-only, added 2026-11-10)

Authorization is the existing `ParentStudentLink` row (same rule as the parent result endpoint).
Parents only; other roles get 403. An unlinked or missing student gives the same generic 404.

- `GET /parents/me/students` → `[{id, name, class_name, school_id}]` for linked students only.
- `GET /parents/me/students/{student_id}/homework/assignments` → the child's assignment summaries
  (same fields as the student list) plus `submission_status` (`not_started` | `in_progress` |
  `submitted`) and `result_released` (bool). No questions, answers, keys, rubrics or marks; the
  result itself still comes only from `.../assignments/{assignment_id}/evaluation` once released.
