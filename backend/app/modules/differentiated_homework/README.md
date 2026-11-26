# Differentiated Homework Module

Backend for giving students homework matched to their learning needs, with teacher oversight.

**Current state:** the deterministic workflow supports gap analysis, preview, saved drafts, teacher review, single-student assignment, incremental answers, final submission, manual evaluation and released student/parent results. The inherited remediation routes below remain separate legacy functionality.

## Inherited remediation routes

| Capability | State |
|---|---|
| Create a homework task for one student | Educator school access; student/request must match the target class |
| List homework by class or student | Educator class lists; linked student/parent or authorized educator student lists |
| Submit homework | Linked owner completion only; no answers or grading, historical scores preserved |
| Recommend remediation | Authorized student access; picks the lowest of LU, CU, AU and CT, then returns one of four fixed maths-specific texts |

## Implemented in this module

| Component | Files | What it does |
|---|---|---|
| **Gap Analyzer** | `gap_analyzer.py`, `schemas.py` | Ranks a student's LU, CU, AU and CT scores and reports the lowest. Ties are reported as ties, and all-equal scores mean no weakest. **No threshold is applied:** "weakest" means lowest relative to the student's own scores |
| **Competency adapter** (temporary) | `competency_adapter.py` | The only reader of competency data. Reads `Student` live and baseline scores, read-only. Rejects out-of-range values. To be replaced when the assessment engine provides diagnosis |

| **Question Selector** (service only; no endpoint) | `question_selector.py`, `schemas.py` | `select_questions(analysis, candidates, request)` picks question bank items for the weaker competencies. Pure logic, deterministic |
| **Question bank adapter** | `question_bank_adapter.py` | `load_candidate_questions(db, school_id, subject_id)` returns `QuestionBankLoad`: candidates plus IDs of malformed rows, which are skipped, not allowed to crash the load. Read-only; filters by school and subject in SQL; never loads answers, rubrics or options |

| **Homework Assembler** (service only; no endpoint, nothing saved) | `homework_assembler.py`, `schemas.py` | `assemble_homework_draft(analysis, selection, request)` builds an unsaved `HomeworkDraft` for teacher review. Pure logic; raises `AssemblyError` on inconsistent input |

| **Homework preview endpoint** | `router.py`, `access.py` | `POST /students/{student_id}/homework/preview` runs the whole pipeline for one student and returns the `HomeworkDraft`. **Nothing is saved** |

| **Saved homework drafts** | `models.py`, `draft_service.py`, `router.py`, `access.py` | Save a draft explicitly, list it, view it, approve or reject it, reopen it, and remove a question. Stored in `homework_drafts` and `homework_draft_items` |
| **Homework assignments** | `models.py`, `draft_service.py`, `router.py`, `access.py` | Assign an approved draft (once); list and view assignments. Stored in `homework_assignments` |
| **Student homework access** | `models.py`, `student_access.py`, `router.py` | Admin links a student login to a Student record (`student_account_links`); the linked student lists and views their own assignments |
| **Answer submission** | `models.py`, `schemas.py`, `submission_service.py`, `router.py` | Tables `homework_submissions` and `homework_submission_answers`, the save and final-submit rules, the three student endpoints (Phase 2), and read-only teacher views (Phase 3, `teacher_submissions.py`) |
| **Homework grading** (manual) | `models.py`, `schemas.py`, `evaluation_service.py`, `router.py` | Tables `homework_evaluations` and `homework_evaluation_items`. The teacher marks each question, finalizes, and releases; the student then sees released results. No automatic marking and no competency changes |

Tests: `backend/tests/test_homework_gap_analyzer.py`, `test_homework_gap_analysis_api.py`, `test_homework_question_selection.py`, `test_homework_assembly.py`, `test_homework_preview_api.py`, `test_homework_drafts.py`, `test_homework_assignments.py`, `test_student_homework_access.py`, `test_homework_submissions.py`, `test_homework_submission_api.py`, `test_homework_teacher_submissions.py`, `test_homework_evaluations.py`.

### Saved homework drafts

**Tables (new; `models.py`):**
- `homework_drafts`: student, school, subject, `created_by`, `status` (enforced by the database as `draft`, `approved`, `rejected` or `assigned`), the request settings, totals, the rationale and notes as JSON, `reviewed_by`, `reviewed_at`, `review_note`, `created_at` and `updated_at`.
- `homework_draft_items`: an ordered **snapshot** of each question: text, type, options, marks, competency, rank, Bloom level, the AI flag, and the answer key and rubric. Positions and questions are unique within a draft. `source_question_id` is deliberately not a foreign key, so a snapshot survives if the bank question is edited or deleted.

**How the tables are created:** there's no migration tool. `init_db()` runs `create_all` on startup, which creates missing tables and never alters or drops existing ones. These tables are new, so adding them is non-destructive. A test confirms this on a disposable "old" database. Setting up Alembic is still a team decision.

**Answer keys:** the answer key and rubric are stored for future grading, but **no response returns them**.

**Endpoints** (all under `/api/v1`; parents and students always get 403, because drafts aren't assigned yet):

| Method and path | Purpose |
|---|---|
| `POST /students/{student_id}/homework/drafts` | Save. The body is the preview body plus an optional `expected_question_ids` |
| `GET /homework/drafts?status=&student_id=` | List the drafts you may see |
| `GET /homework/drafts/{draft_id}` | View one draft with its questions |
| `POST /homework/drafts/{draft_id}/approve` | Draft to approved. Optional `{"note"}` |
| `POST /homework/drafts/{draft_id}/reject` | Draft to rejected. Optional `{"note"}` |
| `POST /homework/drafts/{draft_id}/reopen` | Rejected to draft; clears the review fields |
| `DELETE /homework/drafts/{draft_id}/items/{position}` | Remove a question (draft status only); renumbers, recounts and updates the rationale |

**How saving works:** saving is never automatic. The server **re-runs the same pipeline as the preview**; it doesn't accept a draft posted by the client.
- **409 when the questions differ:** if `expected_question_ids` is given and doesn't match the regenerated selection exactly.
- **409 when a question changed:** if a question changed or disappeared between selection and saving.
- **422 when there's nothing to save:** if no questions were selected.
- **All or nothing:** the draft, its questions and an audit event are written in one transaction.

**Status rules:** `draft` goes to `approved` or `rejected`, and `rejected` goes back to `draft` (reopen). `approved` to `assigned` is defined for the next milestone, with no endpoint yet. Anything else is refused with 409.

**Access:**
- **Admin:** any draft.
- **Principal:** drafts in schools they have access to (own school or an active membership).
- **Teacher:** only drafts they created, while they still have access to that school.

The same rules cover viewing, review and editing. **Assumption:** a teacher may approve their own draft, since "teacher review" is the agreed step.

**Audit:** every save, review and edit adds an `AuditEvent`, which keeps a history even though reopening clears the review fields.

**Simultaneous changes:** `homework_drafts.version` is an integer version counter (SQLAlchemy `version_id_col`). It starts at 1 and goes up by 1 on every successful change. Every update also requires the version this request read. If another request changed the draft in between, nothing is written and the endpoint returns **409**: "This draft was changed by another request. Reload it and try again." The winning request's change is kept.

An integer is used instead of `updated_at`, because on Windows most consecutive clock readings are identical, so a timestamp version could miss a conflict. A test freezes the clock to prove detection doesn't depend on it. `version` isn't returned by the API.

**Timestamps** in responses are always UTC with an explicit offset, and look the same before and after a reload.

**Renumbering** after a removal goes through temporary high positions, so the unique (draft, position) rule can't be broken, whatever order the database applies the updates in. A test reproduces the worst-case order every time, by choosing item keys. If two requests remove questions at once, the second gets 409, and positions stay unique and gap-free.

**Deleting drafts and foreign keys:** SQLite doesn't check foreign keys unless `PRAGMA foreign_keys = ON` is set, and this app's shared engine (`db/session.py`) doesn't set it.
- **ORM deletes** of a draft remove its items, through the relationship cascade.
- **A raw SQL delete** would leave the items behind.
- **The schema itself is correct:** the tables' `ON DELETE CASCADE` works when foreign keys are on. Both behaviours are tested on a disposable database.
- **Turning foreign keys on is a shared-engine decision,** so it's left to the backend owner.

**Failing closed:** roles must match exactly (`admin`, `principal` or `teacher`); `""`, `"Teacher"` and `"admin "` are refused. The role stored on the user counts, not the role claimed in the token.
- **Educators with no school,** and **teachers who moved school**, lose access to drafts in schools they're no longer part of.
- **Invalid, tampered or non-Bearer tokens** get 401.
- **Tokens for unknown users** never return draft data.

Shared `DEMO_MODE` code still contains a tokenless-admin shortcut, but every protected router now requires an explicit bearer token before it can be used.

**Not yet:** student visibility, submission, grading, and content edits other than removing a question.

### Homework assignments

An **assignment** issues an approved draft to its student. It's a separate table, `homework_assignments`:

| Column | Notes |
|---|---|
| `id` | |
| `draft_id` | **Unique**, so a draft can be assigned only once |
| `student_id`, `school_id`, `subject_id` | Copied from the draft |
| `assigned_by` | The logged-in user |
| `assigned_at` | |
| `due_at` | Optional, stored in UTC |
| `status` | Only `assigned` for now |

**No question copy:** the assignment shows the draft's snapshot items, which can't change once the draft is `assigned`. The question bank is never read.

**Status validation:** `status` is checked by the application. There's deliberately no database `CHECK` rule, because SQLite can't change one without rebuilding the table, and submission statuses will be added later.

**Assign:** `POST /api/v1/homework/drafts/{draft_id}/assign`

```json
{"due_at": "2026-11-20T17:00:00+05:30"}
```

The body is optional. `due_at` must include a time zone and be in the future. Unknown fields are refused, so a client can't send `student_id`, `school_id` or `assigned_by`.

**Response 201:**

```json
{
  "id": "…", "draft_id": "…", "student_id": "…", "school_id": "school-1", "subject_id": "sub-math",
  "status": "assigned", "assigned_by": "user-teacher-1",
  "assigned_at": "2026-11-09T10:00:00Z", "due_at": "2026-11-20T11:30:00Z",
  "question_count": 2, "total_marks": 5,
  "items": [{"position": 1, "source_question_id": "…", "text": "…", "type": "mcq", "options": ["A", "B"],
             "marks": 3, "competency": "LU", "competency_rank": 1, "bloom_level": "Apply",
             "is_ai_generated": false}]
}
```

**On assign, in one transaction:** the assignment is created, the draft becomes `assigned`, and an audit event is written. If anything fails, all of it is rolled back. The draft's approval record (`reviewed_by`, `reviewed_at`, `review_note`) is kept.

**Errors:**

| Code | Reason |
|---|---|
| 403 | Role or access |
| 404 | Draft not found |
| 409 | Draft not approved, already assigned (including a simultaneous assignment caught by the unique `draft_id`), or changed by another request |
| 500 | Any other database failure. Everything is rolled back, and it's never reported as "already assigned" |
| 422 | Invalid body or due date |

**List:** `GET /api/v1/homework/assignments?student_id=&subject_id=&status=` returns summaries: the same fields without `items`. Access filtering happens in the database query.

**View:** `GET /api/v1/homework/assignments/{assignment_id}` returns the full assignment with questions.

**Access:** the same rules as the source draft.
- **Admin:** all assignments.
- **Principal:** assignments in their schools.
- **Teacher:** assignments for drafts they created, even if a principal did the assigning.

**Parents and students get 403.** There's no approved link from a student login to a `Student` record, so **student access is blocked until that identity mapping is approved**.

**After assignment:** the draft can't be approved, rejected, reopened or edited (409), and its questions stay exactly as assigned even if the question bank changes.

**Deleting an assigned draft is refused** (`AssignedDraftDeletionError`, raised by an ORM `before_delete` hook). Deleting a draft would cascade to the question snapshots the assignment shows, and SQLite foreign keys are off, so the database wouldn't stop it. Unassigned drafts can still be deleted. A raw SQL delete bypasses this hook; see the foreign-key notes above.

**Answer keys:** no response returns the answer key or rubric.

**Not yet:** submission, evaluation, due-date reminders, changing or cancelling an assignment, and class-wide assignment.

### Student homework access

**How a student is identified:** only through an explicit link in `student_account_links`. One student login is linked to one `Student` record:
- **Never by matching IDs:** `User.id == Student.id` is a coincidence in the seed data, not a rule.
- **Never by email:** `Student` has no email field.
- **One to one:** both `user_id` and `student_id` are unique.
- **Created only by an admin:** nothing is inferred.

**Why a new table and not a `Student.user_id` column:** `create_all()` doesn't add columns to existing tables, and there's no migration tool. A new table is created without touching existing data, and it follows the existing `ParentStudentLink` pattern. A test confirms the `students` table is left unchanged.

**Linking accounts (admin only):**

| Method and path | Purpose |
|---|---|
| `POST /api/v1/student-account-links` with `{"user_id", "student_id"}` | Create a link. **201**. 404 if the user or student doesn't exist; 422 if the account's role isn't exactly `student` or it belongs to a different school; 409 if either side is already linked (also enforced by the database) |
| `GET /api/v1/student-account-links?user_id=&student_id=` | List links, newest first; both filters optional and combinable. Each item: `id, user_id, student_id, created_by, created_at, user_exists, student_exists, is_stale`. IDs and flags only, with no names or emails. **200**; an empty filter value gives 422 |
| `DELETE /api/v1/student-account-links/{link_id}` | Remove a link. **204**. The account loses homework access immediately |

Creating and deleting write an audit event; listing writes nothing. Other roles get 403.

**Stale links:** on SQLite (foreign keys off), deleting a User or Student directly in the database leaves its link behind. A stale link grants no access (the student endpoints fail closed), but it blocks relinking (409). To clean up, list links, pick those with `is_stale: true`, and delete them by `id`; replacements can then be created. On PostgreSQL the foreign keys cascade, so links are removed together with the User or Student.

**Student endpoints:** the student always comes from the login and is never supplied by the client.

| Method and path | Returns |
|---|---|
| `GET /api/v1/students/me/homework/assignments?status=assigned` | The student's own assignments, newest first: `id`, `subject_id`, `subject_name`, `status`, `assigned_at`, `due_at`, `question_count`, `total_marks` |
| `GET /api/v1/students/me/homework/assignments/{assignment_id}` | The same fields, plus `items`: `position`, `text`, `type`, `options`, `marks` |

**Not returned to students:**
- the answer key and rubric
- each question's competency, rank, Bloom level, AI flag and source question ID
- the draft ID, school, assigning teacher, review data and rationale

**Access rules (fail closed, all 403 unless noted):**
- **Wrong role:** the role must be exactly `student`.
- **No link:** "This account isn't linked to a student record."
- **School mismatch:** the linked student's school must still match the account's school.
- **Other roles:** teachers, principals, admins and parents are refused.
- **Someone else's assignment:** returns **404**, the same as a missing one, so a student can't tell whether another assignment exists.
- **No token, `DEMO_MODE` off:** 401.
- **No token, `DEMO_MODE` on:** 401; the protected router requires a real login.

**Parents** keep their existing access (`GET /students/{student_id}/homework/gap-analysis`, through `ParentStudentLink`) and don't gain access through these student endpoints.

**Not yet:**
- answer submission and grading
- a self-service or bulk way to create links
- linking for existing student accounts: the seeded `user-student-1` has no link, so it gets 403 until an admin links it
- updating the older routes that still compare `User.id` with `Student.id`, in teammate code and in this module's older homework list route

### Answer submission

Students save answers to an assignment, change them, and then submit once. Phase 1 added the tables, request shapes and service logic; Phase 2 added the student endpoints (below). **No grading:** nothing stores or calculates marks, scores, grades or feedback, and nothing reads the answer key or rubric.

**Tables** (new, created by `create_all`; existing tables are unchanged):

| Table | Key rules |
|---|---|
| `homework_submissions` | One per assignment (UNIQUE `assignment_id`). `student_id` and `school_id` are copied from the assignment. `status` is `in_progress` or `submitted` (CHECK). `submitted_at` is set exactly when submitted (CHECK). `is_late` can only be true when submitted (CHECK). `version` provides optimistic locking |
| `homework_submission_answers` | One per question per submission (UNIQUE `submission_id, draft_item_id`). Exactly one of `answer_text` and `selected_option_index` (CHECK). The index can't be negative (CHECK). Deleted with its submission (`ON DELETE CASCADE`). A row exists only while the question is answered |

Foreign keys: a submission belongs to an assignment and a student; an answer belongs to a submission and a frozen question (`homework_draft_items`). With foreign keys enforced (PostgreSQL), a question that has an answer can't be deleted. The app's SQLite engine has foreign keys off, so there the application rules apply. The CHECK rules use syntax that works on both databases, and a test compiles the tables for PostgreSQL.

**The save request** (`SubmissionAnswersUpdate`):

```json
{
  "expected_version": 3,
  "answers": [
    {"position": 1, "selected_option_index": 2},
    {"position": 2, "answer_text": "Because both sides double."},
    {"position": 4, "clear": true}
  ]
}
```

- **Partial:** only the listed questions change; others keep their answers. An empty `answers` list is allowed.
- **Exactly one action per entry:**
  - `answer_text` for `short`, `descriptive` and `practical` questions: plain text, not blank, at most `MAX_ANSWER_TEXT_LENGTH` (10,000) characters;
  - `selected_option_index` for `mcq`: a 0-based index into the question's frozen options, as listed in `options` on the student assignment view;
  - `clear: true` removes an answer; clearing an unanswered question does nothing.
- **No null:** an explicit `null` is rejected. In this module's other requests `null` means "not provided", so clearing has its own explicit form. `clear: false` is rejected too.
- **Positions:** 1-based, as in the assignment view. Each may appear once per request, and it must exist.
- **Size:** at most `MAX_ANSWER_UPDATES` (500) entries.
- **Unknown fields:** rejected.
- **Versioning:** `expected_version` is omitted for the first save (which creates the submission) and must equal the current `version` afterwards.
- **All or nothing:** the whole request is validated before anything changes; every problem is reported together (`InvalidAnswers`).

**Final submit** (`SubmissionFinalizeRequest`, just `expected_version`): locks the submission for good. Blank and partial submissions are allowed; submitting with nothing saved creates a blank submitted record. `is_late` is true only when the assignment has a due time and the submission is after it (exactly at the due time is on time). There is no penalty.

**Service** (`submission_service.py`, no database I/O; the caller commits once):

| Function | Does |
|---|---|
| `validate_answer_updates(updates, items)` | Checks each update against the frozen question: position exists, answer form matches the type, the option index is in range, text isn't blank or too long. Repeats the shape checks for direct callers |
| `save_answers(assignment, submission, request, now)` | Creates the submission if needed, then applies the changes |
| `finalize_submission(assignment, submission, request, now)` | Submits and sets `is_late` |
| `to_submission_out(submission, assignment)` | Student-facing view: `id, assignment_id, status, version, is_late, started_at, updated_at, submitted_at, answered_count, question_count, answers[{position, answer_text, selected_option_index}]` |

Service errors (the endpoints map them to HTTP statuses below):
- `NotSubmittable`: the assignment isn't open;
- `SubmissionMismatch` (a subclass of `NotSubmittable`): stored data is inconsistent, a server-side fault;
- `SubmissionLocked`: already submitted;
- `VersionConflict`: missing or outdated `expected_version`;
- `InvalidAnswers`: lists each problem.

**Concurrency:** every save also updates the submission row, so its version always rises, even when two saves share a timestamp. Two simultaneous saves from the same version: one commits, the other gets `StaleDataError`, and nothing of the losing request is written. Two simultaneous first saves: the UNIQUE rule lets only one submission exist.

#### Student endpoints (Phase 2)

All three go through the same checks first:
1. The caller must be a linked student. This uses the existing `StudentAccountLink` path: exact `student` role, a link, an existing Student record, and the same school. Otherwise **403**.
2. The assignment is loaded by its ID **and** the student's ID. Another student's assignment, in the same school or another, gets **404**, the same as a missing one.

The student is never taken from the request, and the request never names a submission; it's always found through the student's own assignment.

| Method and path (under `/api/v1/students/me/homework/assignments/{assignment_id}`) | Body | Success |
|---|---|---|
| `GET /submission` | none | **200**. Before any save, the `not_started` state; nothing is created |
| `PUT /submission` | `SubmissionAnswersUpdate` | **201** when this creates the submission, **200** when it updates one. Saving after the due time is allowed |
| `POST /submission/submit` | `SubmissionFinalizeRequest` | **200**. Locks the answers; sets `submitted_at` and `is_late` |

All three return `HomeworkSubmissionOut`, one shape for every state:

```json
{"id": null, "assignment_id": "a1", "status": "not_started", "version": null, "is_late": false,
 "started_at": null, "updated_at": null, "submitted_at": null,
 "answered_count": 0, "question_count": 4, "answers": []}
```

```json
{"id": "s1", "assignment_id": "a1", "status": "in_progress", "version": 2, "is_late": false,
 "started_at": "2026-11-19T12:00:00Z", "updated_at": "2026-11-19T12:05:00Z", "submitted_at": null,
 "answered_count": 2, "question_count": 4,
 "answers": [{"position": 1, "answer_text": null, "selected_option_index": 2},
             {"position": 3, "answer_text": "Because both sides double.", "selected_option_index": null}]}
```

- **`version`:** send it back as `expected_version` on the next PUT or submit. `null` (not started) means omit it.
- **`question_count`:** the assignment's real number of questions in every state.
- **Questions:** not repeated here; they come from `GET /students/me/homework/assignments/{assignment_id}`.
- **Never returned:** answer keys, rubrics, marks, grades, feedback, competency or Bloom data, source question IDs, review data, or internal student and school IDs.

The class is named `HomeworkSubmissionOut`, not `SubmissionOut`, because the assessment module already publishes a `SubmissionOut`. Two classes with the same name make FastAPI rename both in OpenAPI, which would change the existing schema's public name.

**Errors:**

| Cause | Status | `detail` |
|---|---|---|
| Not logged in (in either demo setting) or an invalid token | 401 | explicit bearer requirement |
| Authenticated role is not exactly `student` | 403 | "Access denied." |
| No link, a deleted Student record, or a school mismatch | 403 | "This account isn't linked to a student record." |
| Assignment missing or someone else's | 404 | "Assignment not found." |
| Malformed body (null, two actions, `clear: false`, blank or too-long text, unknown field, repeated position) | 422 | FastAPI's standard list of `{loc, msg, type}` |
| Answers don't fit the questions (`InvalidAnswers`) | 422 | `[{"position": 1, "reason": "..."}]`, one entry per invalid answer |
| Already submitted (`SubmissionLocked`) | 409 | "This homework has been submitted and can't be changed." |
| `expected_version` missing, outdated, or sent on a first save (`VersionConflict`) | 409 | the reason |
| Changed by another request between reading and saving | 409 | "This submission was changed by another request. Reload it and try again." |
| Another first save created the submission first | 409 | "A submission was started by another request. Reload it and try again." |
| Assignment not open (`NotSubmittable`) | 409 | the reason |
| Inconsistent stored data (`SubmissionMismatch`) | 500 | a fixed message. Details are logged, not returned. Checked before PUT or submit changes anything, so nothing is written |

**Transactions and concurrency:** each request makes one commit. The service validates everything before it changes anything; on any failure the transaction is rolled back, so no partial answers and no audit event remain. Simultaneous requests are handled with the existing unique rules and SQLAlchemy versioning, not row locks:
- **Two first saves (or two blank first submits):** the unique `assignment_id` lets one through; the other is rolled back, finds the winner, and gets 409. Only that unique rule is treated this way: any other database error is rolled back and re-raised (500), never reported as a conflict.
- **Save vs save, save vs submit, submit vs submit:** both read the same version, so the second commit fails its version check and gets 409.

The response is built after the commit.

**Audit:** exactly one "Homework Submitted" event (category `curriculum`) per successful final submit, saved in the same transaction as the lock, with "(late)" noted when late. Saves and failed requests aren't audited.

#### Teacher views (Phase 3, read-only)

| Method and path (under `/api/v1/homework/assignments/{assignment_id}`) | Returns |
|---|---|
| `GET /submissions` | `TeacherAssignmentSubmissionsOut`: assignment details (`assignment_id`, `subject_id`, `subject_name`, `assignment_status`, `assigned_at`, `due_at`, `question_count`), `counts` (`total_students`, `not_started`, `in_progress`, `submitted`, `submitted_late`), and `students` (one row each: `student_id`, `student_name`, `status`, `started_at`, `updated_at`, `submitted_at`, `is_late`, `answered_count`, `question_count`) |
| `GET /submissions/{student_id}` | `TeacherSubmissionDetailOut`: the same student row plus `assignment_id` and `questions`. Every question by position, with `text`, `type`, `options`, `answered`, `answer_text` and `selected_option_index` |

**Access** (the same rules as `GET /homework/assignments/{assignment_id}`, using `can_access_assignment`):

| Role | Can view |
|---|---|
| admin | Any assignment |
| principal | Assignments in a school they can access (own school or an active membership) |
| teacher | Only assignments of drafts they created, in a school they can access. Not other teachers' assignments in the same school |
| student, parent | Nothing (403) |

- **Order of checks:** the role is checked first, with no lookup for other roles (403). Then a missing assignment and one the user can't access (another teacher's, another school's) give the **same** 404 "Assignment not found.", so these views don't reveal whether an assignment exists. The older assignment endpoints keep their separate 404 and 403.
- **A real login is required:** these views show student answers, so a request without a bearer token gets **401**, even with `DEMO_MODE` on. All protected routers now explicitly reject tokenless requests.
- **Student IDs:** a `student_id` that isn't the assignment's student gives 404 "Student not found on this assignment."
- **No student login involved:** these views never use `StudentAccountLink`, so a stale or removed link changes nothing here.

**Roster:** each assignment names exactly one student (`homework_assignments.student_id`); that row is the authoritative roster, never derived from submissions. A student with no submission appears as `not_started`, so `total_students` is always 1. Homework for a whole class is several assignments, and there's no class-level view yet.

**States:**
- `not_started`: no submission; all times are null.
- `in_progress`: saved, not submitted.
- `submitted`: locked.

`is_late` is null unless submitted, so an in-progress submission past its due time is never labelled late. A deleted Student record shows as `student_name: null`; inconsistent stored data gives 500 with no details.

**Read-only:** GET only (other methods get 405). Viewing never creates a submission, and never changes answers, versions, assignment status or due dates. Nothing is audited. Each request runs a fixed number of queries (assignment with questions, access check, student, submission with answers, subject name), regardless of the number of answers. There's no pagination, because each assignment has exactly one student.

**Never returned:** answer keys, rubrics, marks, scores, grades, feedback, competency or Bloom data, source question IDs, review data, the submission's version, and school IDs.

**Not done yet:** a class-level progress view across assignments, and reopening a submitted submission.

### Homework grading (manual)

A teacher marks submitted homework question by question, finalizes the marking, and releases the results to the student.

**Lifecycle:** `pending` (marks and feedback can change) -> `marked` (finalized; totals stored; read-only) -> `released` (the student can see it; read-only).

**What grading never does:**
- change the submission or its answers;
- touch competency data (`Student` live scores, baselines, `needs_support`, `StudentCompetencySnapshot`, `AssessmentSubmission`);
- mark anything automatically (no AI, no answer-key matching, no simulated grading);
- compute percentages, grades or thresholds;
- return answer keys or rubrics anywhere except the teacher's grading evaluation (see below).

**Tables** (new; `create_all` adds them without changing existing tables):

| Table | Key rules |
|---|---|
| `homework_evaluations` | One per submission (UNIQUE `submission_id`). `student_id` and `school_id` copied from the assignment. CHECK rules: `status` in pending/marked/released; `finalized_at`/`finalized_by` set exactly when not pending; `released_at`/`released_by` set exactly when released; `total_awarded` set exactly when not pending and within 0..`total_max`. `version` for optimistic locking |
| `homework_evaluation_items` | One per frozen question, answered or not (UNIQUE per evaluation on `draft_item_id` and on `position`). `max_marks` copied from the frozen question; `awarded_marks` null until marked and, by CHECK, within 0..`max_marks`; `marked_by`/`marked_at` set together |

**Marks are whole numbers,** like every marks column in the project. Strict integers reject floats, booleans and strings. `NaN`, `Infinity` and out-of-range numbers (such as `1e309`) are refused with a 422 before validation, because FastAPI's standard 422 response can't encode them.

**Teacher endpoints** (under `/api/v1/homework/assignments/{assignment_id}`):

| Method and path | Body | Result |
|---|---|---|
| `GET /evaluations` | none | Submitted homework for the assignment and its evaluation state (`not_started`, `pending`, `marked`, `released`), with `evaluation_id` and `marked_count`. Homework that isn't submitted isn't listed |
| `POST /evaluation` | none | Start marking. **201** with a new pending evaluation (one unmarked item per question), or **200** with the existing one; never a duplicate, and no marks are assigned. **409** if the homework isn't submitted |
| `GET /evaluation` | none | The evaluation (`TeacherEvaluationOut`): each question's text, type and options; the student's answer; `max_marks`, `awarded_marks`, `feedback`, `marked_by`, `marked_at`; the teacher-only `correct_answer` and `marking_rubric`; plus status, `version`, totals, and who finalized and released it. **404** "Evaluation not found." before it's started |
| `PATCH /evaluation/items` | `{"expected_version": 1, "items": [{"position": 1, "awarded_marks": 2, "feedback": "..."}]}` | Set marks and/or feedback. Fields left out keep their values; `null` is rejected; `feedback: ""` clears it. All or nothing |
| `POST /evaluation/finalize` | `{"expected_version": n}` | pending -> marked. Every question needs an explicit mark (0 included); stores `total_awarded` and `total_max` |
| `POST /evaluation/release` | `{"expected_version": n}` | marked -> released. **Idempotent:** releasing again returns the evaluation unchanged, writes nothing and adds no audit event |

**Teacher-only answer keys and rubrics.** Each question in `TeacherEvaluationOut` (`TeacherEvaluationItemOut`) includes `correct_answer` and `marking_rubric`:
- **Source:** the question's **frozen snapshot** (`homework_draft_items`), never the live question bank, so later bank edits don't change what the teacher marks against.
- **Format:** exactly as stored (text; for an MCQ, the key is the option text). `null` when the snapshot has none; nothing is invented.
- **Where:** every response that returns the teacher evaluation: `POST /evaluation`, `GET /evaluation`, `PATCH /evaluation/items`, `POST /evaluation/finalize`, `POST /evaluation/release`.
- **Never in:** the evaluation queue, the Phase 3 submission views, any student endpoint (assignment detail, submission, submit, result), parent endpoints, audit text, error messages or logs. Tests check each of these with distinctive secret values.
- **Use:** shown to the teacher only. They aren't used to calculate marks; grading stays manual.

**Access:** the same as the Phase 3 views.
- **Who can grade:** admin, any assignment; principal, their schools; teacher, only assignments of drafts they created.
- **Other roles:** students and parents get 403.
- **Inaccessible or missing assignments:** the same 404 "Assignment not found.".
- **Login:** a real bearer token is required, so a request with no token gets 401, even with `DEMO_MODE` on.

**Errors:**

| Cause | Status |
|---|---|
| Malformed body, or NaN/Infinity | 422 (FastAPI's standard format) |
| Mark above the question's maximum, or an unknown position | 422, `[{"position": n, "reason": "..."}]`, one entry per problem |
| Homework not submitted; editing or finalizing a finalized evaluation; finalizing with unmarked questions (the detail lists them); releasing before finalizing; stale `expected_version` | 409 |
| Inconsistent stored data: the submission, answers or evaluation items don't match the frozen questions; a wrong student, school or assignment; an evaluation of homework that isn't submitted; a finalized evaluation with an unmarked question or a total that isn't the sum of its marks | 500 with a fixed message; details are logged. Checked before any change and before any response, including the student's |

**Concurrency:** every change also updates the evaluation row, so its version always rises.
- **Two teachers marking at once:** the second gets 409 and none of its changes are saved.
- **Two starts at once:** the unique `submission_id` keeps one; the other request returns that evaluation.
- **Two releases at once:** both get 200 with the released evaluation, and only one audit event is written. If the competing change wasn't a release, the request gets 409.
- **Deleting an evaluated submission** through the ORM raises `EvaluatedSubmissionDeletionError` (like the assigned-draft guard), so an evaluation can't be orphaned. Deleting an evaluation removes its items.

**Audit:** one event per start, finalize and release ("Homework Evaluation Started", "Homework Evaluation Finalized", "Homework Results Released"; category `curriculum`), each in the same transaction as its change. Marking itself isn't audited; each item records `marked_by` and `marked_at`.

**Student result:** `GET /api/v1/students/me/homework/assignments/{assignment_id}/evaluation`.
- **Identity:** `StudentAccountLink` only.
- **Released results only:** before release (not started, pending or marked) it returns the same **404** "Evaluation not found.", so unreleased marks can't be detected. Another student's assignment gives 404 "Assignment not found.".
- **Returns** `assignment_id`, `released_at`, `total_awarded`, `total_max`, and per question `position`, `text`, `type`, `options`, `answer_text`, `selected_option_index`, `max_marks`, `awarded_marks` and `feedback`.
- **Never returns** answer keys, rubrics, the evaluation ID, its version, or teacher IDs and marking timestamps.

**Parent result:** `GET /api/v1/parents/me/students/{student_id}/homework/assignments/{assignment_id}/evaluation`.
- **Same as the student's result:** the same `StudentResultOut`, built by the same `to_student_result`. It never includes answer keys, rubrics, the evaluation's version, teacher identities or unreleased marks.
- **Who:** authenticated parents only; another authenticated role gets 403; missing/invalid token gets 401 in either demo setting.
- **The link:** the existing `ParentStudentLink`, checked through the existing `can_view_student`. There is no "verified" flag on that table and no endpoint that creates links, so a link row is the authorization, as for the gap-analysis endpoint. No new mapping, and no matching of IDs or emails.
- **Everything else is one 404** "Result not found.": no link to that student; a link to a deleted Student (stale); a missing assignment, or one belonging to another student; a result that isn't released (not started, pending or marked). So a parent can't learn whether another student, assignment or unreleased evaluation exists. Unlike the gap-analysis endpoint, an unlinked student doesn't give a different status.
- **Read-only:** parents still get 403 on the student submission endpoints and every teacher grading endpoint.

**Not done yet:**
- unreleasing or re-marking after release;
- an overall feedback comment;
- half marks;
- connecting marks to competency scores, which needs an agreed rule and a single owner of competency updates.

### Homework preview endpoint

`POST /api/v1/students/{student_id}/homework/preview`

**Request body (`HomeworkPreviewRequest`; unknown fields rejected):**

| Field | Rule |
|---|---|
| `subject_id` | Required, non-empty |
| `max_questions` | Required integer, at least 1 |
| `max_total_marks` | Optional integer, at least 1 |
| `include_ai_generated` | Required, a real `true` or `false` |

**No `school_id`:** the school comes from the student's record, and sending one gives 422.

**Order of checks:**
1. **Role:** must be admin, principal or teacher, otherwise 403 before any lookup. Parents and students are refused; parents can still view the gap analysis.
2. **Student:** must exist, otherwise 404.
3. **Access:** the same rule as the gap analysis endpoint (`can_view_student`): admin any school; teachers and principals their own school or an active membership. Otherwise 403.
4. **Subject:** must exist in `subjects`, otherwise 404, **and** be in the student's class `subject_ids_json`, otherwise 422 (agreed rule). A missing or inconsistent class record gives 500.
5. **Scores:** invalid stored scores give a 500 with a safe message.
6. **Pipeline:** gap analysis, then questions from the student's school and the requested subject, then selection, then assembly.
7. **Result:** 200 with the `HomeworkDraft`. Malformed question rows are skipped, and a note gives the count.

An `AssemblyError` here would mean the pipeline produced inconsistent data, so it returns a generic 500.

### How homework assembly works

Flow: gap analysis, then question selection, then **assembly**, then teacher review (not built yet).

1. **Check consistency.** All three inputs must agree:
   - **Same student:** the selection and the analysis refer to the same student.
   - **Same request:** the request's question count and marks limit match the selection's.
   - **Valid gap analysis:** it ranks LU, CU, AU and CT exactly once each, and its lowest, highest, spread, weakest and every rank agree with its own scores. The rationale copies these fields, so a contradiction is rejected.
   - **AI rule respected:** no AI-generated question appears unless the request allows them.
   - **Ranks agree:** each question's competency rank matches the analysis.
   - **Valid questions:** no question appears twice, and every question has marks of at least 1.
   - **Totals add up:** total marks, shortfall and question count are consistent, and the marks limit isn't exceeded.

   Any problem raises `AssemblyError`; nothing is silently corrected.
2. **Copy questions** in selection order into numbered `DraftItem`s (position 1, 2, ...). Text, marks, competency, rank, type, Bloom level and the AI flag are kept as they are.
3. **Recalculate** the question count and total marks from the items.
4. **Rationale** comes from the gap analysis only: targeted competencies, weakest, all four scores, lowest and highest, score source, and a factual summary such as `Targets LU (40), CT (50). Student's lowest score: LU (40); score range 40-70.` No teaching advice is added.
5. **Notes:** gap-analysis notes, then selection notes, then assembly notes (empty draft, incomplete draft, AI questions included).

**Output `HomeworkDraft`:**
- `student_id`, `school_id`, `subject_id`
- `items`, `question_count`, `total_marks`
- `requested_questions`, `max_total_marks`, `shortfall`, `is_complete`
- `contains_ai_generated`, `rationale`, `notes`

There are no answers, rubrics or options.

**Deliberately not included:** title, due date, assigning teacher, review status, or any saved record.

**Trusted upstream assumptions** (current schemas can't verify them):
- **School and subject:** `SelectionResult` and `SelectedQuestion` don't carry them, so the draft copies them from the request. They're correct when the request passed to the assembler is the same one given to the selector, which filters by it.
  - **Smallest change if independent checking becomes necessary** (proposal, not implemented): the selector copies `school_id`, `subject_id` and `include_ai_generated` from the request into `SelectionResult`, and the assembler checks they match. Checking each question would also need `school_id` and `subject_id` on `SelectedQuestion`.
- **Competency label within a tie:** if a question is relabelled to another competency with the same rank, that can't be detected, because `SelectedQuestion` is the only source of the label.

### Why drafts use dedicated tables

`HomeworkRemediation` **can't safely store a draft**:
- **No question links:** there's nowhere to store the questions except as text in `description`.
- **Required fields with no agreed values:** `title`, `due_date` and `description` must be filled in.
- **One competency only:** `competency_target` holds a single value, but a draft can target several.
- **Drafts would leak to students:** `status` is free text, and both list routes (`GET /classes/{class_id}/homework`, `GET /students/{student_id}/homework`) return every row with no status filter. A draft would appear to students straight away, and "draft" would be an invented status anyway.

Dedicated `HomeworkDraftRecord` and `HomeworkDraftItemRecord` tables implement storage,
frozen snapshots, review and ownership. Approved drafts become separate single-student
`HomeworkAssignmentRecord` rows, leaving legacy remediation lists separate. See the saved-draft
and assignment sections above for the implemented fields and transitions. Retention and a
migration framework still need team decisions.

### How question selection works

1. **Filter.** Candidates are first sorted on all their fields, so the result never depends on input order. Each excluded question is counted under the first rule it breaks:
   - duplicate ID: any later copy of an ID already seen
   - wrong school or wrong subject
   - unsupported competency
   - marks below 1
   - AI-generated, unless requested
   - duplicate text: same as an already-accepted question, ignoring case and spacing; the lowest ID is kept
2. **Prioritise.** Competencies are grouped by gap-analysis rank, weakest first; tied scores share a group.
3. **Fill.** Questions come from the weakest group first. Tied competencies take turns, and within a competency questions are taken in ID order.
4. **Marks limit.** If the caller sets one, a question that doesn't fit is skipped and the next is tried.
5. **Report.** The result includes the selection, total marks, shortfall, eligible counts per competency, exclusion counts and notes.

**The caller decides** the number of questions, an optional marks limit, and whether AI-generated questions may be used. AI questions have no review status, so there's no default.

**Provisional policy, not agreed by the team:** weakest-first priority, turn-taking within ties, ID order, and skipping questions over the marks limit.

**Not done, because the data or an agreed policy doesn't exist:** topic, difficulty or Bloom-level balancing.

**Competency matching** accepts only LU, CU, AU and CT, ignoring case and surrounding spaces. Other spellings, such as "Language Understanding", are reported as unsupported, not guessed.

**Limitation:** the scores it reads are unverified. Some code paths set them from request input, fixed increments or simulated grading. Results are relative comparisons, not diagnosis.

## Planned, not implemented

- Learning gap analysis beyond relative ranking (needs assessment data)
- Pedagogical strategies
- Question selection by topic, difficulty and cognitive level (no such data or agreed policy yet; selection currently uses subject, school and competency)
- AI-assisted question generation for gaps in the question bank
- Group distribution (individual homework and teacher review are implemented)
- A class-level progress view; connecting homework marks to competency scores (needs an agreed rule)

## Responsibilities and boundaries

**This module owns:** homework workflow, strategy and question selection logic, and the homework API.

**This module doesn't own:** OCR, formal assessment grading, assessment and diagnosis, the question generation pipeline, the time-aware engine, shared backend infrastructure, or the frontend.

**Code outside this folder that it relies on:**

| Code | Location | Note |
|---|---|---|
| `HomeworkRemediation` model | `backend/app/models/entities.py` | All models currently share this file |
| `HomeworkOut` schema | `backend/app/schemas/competencies.py` | Homework is its only user today |
| `generate_differentiated_recommendation` | `backend/app/services/competency_service.py` | Stays there until its logic is replaced |
| `get_db`, `get_current_user`, `require_roles` | `backend/app/db/session.py`, `backend/app/api/dependencies.py` | Shared infrastructure |
| Router registration | `backend/app/api/v1/router.py` | One import line points here |

## Architecture

```text
HTTP request
    |
    v
router.py  (this module: validates input, checks role, handles the request)
    |
    +--> competency_service.py   recommendation logic
    +--> entities.py             HomeworkRemediation, Student, AuditEvent
    |
    v
Database, through the shared session
```

## Setup

Run all commands from `apps/lumeneios/`.

```bash
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

API docs are at `http://localhost:8000/api/v1/docs`. The first start creates and seeds a local `lumeneios.db`, which git ignores.

## Running tests

```bash
python -m pytest backend/tests -v -p no:cacheprovider
```

`backend/tests/conftest.py` redirects each run to a temporary database and upload folder, and stops if those paths are unsafe. Your local `lumeneios.db` and `storage_uploads/` aren't used.

## API endpoints

All paths are under `/api/v1`.

| Method and path | Role check in code | State |
|---|---|---|
| `GET /classes/{class_id}/homework` | Real login; admin or school-authorized educator | Works |
| `POST /classes/{class_id}/homework` | Real login; admin or school-authorized educator; student/class match | Works |
| `GET /students/{student_id}/homework` | Real login; student/parent link or authorized educator/admin | Works |
| `POST /homework/{homework_id}/submissions` | Real login; linked student owning the task | Completion only; no fabricated grade |
| `GET /students/{student_id}/remediation/recommendation` | Real login; student/parent link or authorized educator/admin | Existing recommendation logic |
| `GET /students/{student_id}/homework/gap-analysis` | admin; principal or teacher (school or active membership); linked parent | Works; read-only |
| `POST /students/{student_id}/homework/preview` | admin; principal or teacher (school or active membership) | Works; saves nothing |
| `POST /students/{student_id}/homework/drafts` | admin; principal or teacher (school or active membership) | Works; saves a draft |
| `GET /homework/drafts`, `GET /homework/drafts/{draft_id}` | admin; principal (their schools); teacher (own drafts) | Works |
| `POST /homework/drafts/{draft_id}/approve`, `/reject`, `/reopen` | Same as viewing a draft | Works; 409 on invalid or simultaneous changes |
| `DELETE /homework/drafts/{draft_id}/items/{position}` | Same as viewing a draft | Works; draft status only |
| `POST /homework/drafts/{draft_id}/assign` | Same as viewing a draft | Works; approved drafts only, once |
| `GET /homework/assignments`, `GET /homework/assignments/{assignment_id}` | admin; principal (their schools); teacher (own drafts' assignments) | Works; teacher-facing |
| `POST /student-account-links`, `DELETE /student-account-links/{link_id}` | admin only | Works |
| `GET`/`PUT /students/me/homework/assignments/{assignment_id}/submission`, `POST .../submission/submit` | linked student only, own assignments | Works; no grading |
| `GET /homework/assignments/{assignment_id}/submissions`, `GET .../submissions/{student_id}` | Same as viewing the assignment; a bearer token is required (no `DEMO_MODE` stand-in) | Works; read-only |
| `GET .../evaluations`, `POST`/`GET .../evaluation`, `PATCH .../evaluation/items`, `POST .../evaluation/finalize`, `POST .../evaluation/release` (under `/homework/assignments/{assignment_id}`) | Same as viewing the assignment; a bearer token is required | Works; manual marking only |
| `GET /students/me/homework/assignments/{assignment_id}/evaluation` | linked student only, own assignments | Works; released results only |
| `GET /parents/me/students/{student_id}/homework/assignments/{assignment_id}/evaluation` | parent linked through `ParentStudentLink` | Works; released results only, the same content as the student sees |
| `GET /students/me/homework/assignments`, `GET /students/me/homework/assignments/{assignment_id}` | linked student only | Works; read-only |

## Integration with other modules

See [the API contract](../../../../docs/project/api-contracts/differentiated-homework.md). **Those interfaces are proposed and haven't been agreed with the owning teammates.**


## Reliability audit and deployment limitations

Student answer-save and final-submit requests, like marking and evaluation transitions,
reject numeric NaN, positive/negative Infinity and overflowing exponents with JSON-safe 422
responses. The guard runs before business logic; rejected requests create no submission or
audit event. Literal words such as "Infinity" in text answers remain valid text.

The concurrency tests interleave competing requests after a read to verify unique constraints,
version checks, rollback and audit atomicity. They do not prove behavior under every database
load pattern; SQLite can still report lock contention. No row-lock guarantee is assumed.

SQLite foreign keys are not enabled by the shared engine. ORM deletion guards do not protect
bulk or raw SQL deletes; maintenance scripts must explicitly preserve references. There is no
Alembic migration workflow. The evaluation tables are new tables created by existing
`create_all`; this does not migrate or repair existing table definitions or orphaned data.

Deployment/team issues outside this workflow:
- Shared `DEMO_MODE` remains a development setting. All protected routers now explicitly
  require real access tokens; production configuration refuses demo mode. Disable it for live data.
- The question-bank and legacy remediation access defects identified in the first audit are
  remediated below. Formal assessment routes retain separate inherited access concerns;
  this patch does not change formal assessment scoring or competency updates.
- Parent links authorize access by row existence; independent verification is unavailable.
- Each assignment has one student; queue counts describe that single student. Group rosters,
  AI generation, automatic grading, competency updates and post-release edits are not added.


## Question-bank and legacy remediation security remediation

### Question-bank access

`GET /api/v1/assessments/question-bank` requires a real bearer token (401 without one, even
in DEMO_MODE) and admin, principal or teacher role (403 otherwise). It is an authoring endpoint.
Ordinary question content would include text, type, options and marks; keys, rubrics and source
document references are teaching-only. There is no existing student bank reader requirement,
so no new public/student endpoint is introduced. Students use key-free homework snapshots.

The full authoring response is preserved for authorized educators. Results are scoped to the
authorized `X-School-Id` through existing school-context rules: admin can select any school;
other educators need their own school or active membership. Subject filtering is preserved.
The legacy demo fallback is restricted to its original school-1/math context after login/role
checks; an empty unrelated bank returns an empty list.

Update, regenerate, delete and generation endpoints also require real login. Updates and
regeneration use scoped lookup and generic 404 for missing/inaccessible questions, closing
key retrieval via an empty update. Regeneration requires a persisted bank question rather than
an arbitrary absent ID. Delete retains an idempotent response without deleting foreign rows.
Generation requires every source document to exist in the selected school (generic 404
otherwise) and saves bank questions under that school. No provider or grading logic changed.

### Legacy remediation

All five legacy operations require real login. Student-specific reads/recommendations use
StudentAccountLink for students, ParentStudentLink for parents, and existing school access
for educators/admin. Missing and inaccessible students return the same 404. Class lists and
creation are educator-only and school-scoped. Creation requires the request class and student
class/school to match the path; stored mismatches are excluded from lists and submission.

Only the linked student owner can submit a legacy task. Submission changes assigned to
submitted, never invents a grade, and preserves historical score and reviewed status on
repetition. Its response retains `message` and nullable `score`. It accepts no answers and
never writes formal assessment submissions, competency snapshots, live scores or baselines.
The complete differentiated assignment/submission/evaluation workflow is unchanged.

### Callers and compatibility

`src/lib/apiClient.ts` calls the bank through getQuestionBank and already sends bearer and
X-School-Id headers. DataContext loads it for teacher/AssessmentBuilder.tsx; authorized teacher
key/rubric fields retain their names and shape. DataContext also attempts loading for other
logged-in roles and catches errors; those requests now receive 403.

DataContext persists bank data in browser local storage and uses bundled demo fallback data.
The integrated frontend clears known legacy teaching caches, isolates demo browser storage and
excludes demo chunks from live builds. Copies exported before the fix cannot be erased remotely.

Legacy creation/completion in DataContext, teacher/MyClasses.tsx, teacher/RemediationManager.tsx
and student views operate on local state, not these backend routes. The local completion
demonstration no longer invents score 92; real workflows use server-evaluated results. External clients relying on
anonymous bank access, student/parent bank access, all-school results, arbitrary-ID regeneration,
class-wide student lists or fabricated backend scores must adopt these restricted contracts.

Regression coverage is in `tests/test_homework_legacy_security.py`: roles, school memberships,
keys/rubrics, cross-student access, explicit identity, revoked links, mismatched records,
creation validation and unchanged competency/formal-assessment records.


## Live integration and final audit

The default frontend now uses the real authenticated homework API, explicit identities,
versioned saves and released results. Student/parent demo identities are never used by the
live workspace. The offline demonstration is opt-in, isolated from backend writes, and uses
separate browser storage. The live bank no longer falls back to cached/bundled teaching keys.
See [deployment readiness](../../../../docs/deployment.md) for the complete
assessment security matrix, frontend compatibility, environment checklist, migration gates,
remaining platform risks and required team decisions. Earlier caller/cache observations above
describe the pre-integration audit; this section and the deployment checklist describe current behavior.

The API lifecycle from gap analysis through parent result access is exercised in
`backend/tests/test_homework_end_to_end.py`; it verifies that homework never writes formal
assessment submissions, competency snapshots or student scores. Formal assessment routes are
now real-login educator-only and school/class scoped; their existing authorized grading logic
is preserved. No new grading algorithm is used in either frontend or homework services.


The full platform stabilization audit is recorded in [final acceptance report](../../../../docs/project/FINAL_ACCEPTANCE_REPORT.md).
All protected API operations require a real bearer token, and non-finite JSON is rejected by the
shared API dependency. Database faults return a redacted 500 without exposing SQL parameters;
rollback/audit assertions remain tested. No homework academic rules or snapshots changed.
