# LumenEIOS — Final acceptance report

> **Superseded:** this report describes an earlier acceptance run, not the current isolated takeover demo. See [`docs/FINAL_ACCEPTANCE_REPORT.md`](project/FINAL_ACCEPTANCE_REPORT.md) for current tests, hashes, browser evidence, and limitations.

Two parts. **Part A** covers the Curriculum Catalogue (syllabus and coverage) and Time-Aware Engine assignment: one catalogue, one syllabus source of truth, one coverage state. **Part B** is the platform acceptance (authentication, planning workspace security, calendar, recovery, approval) re-run on the final code. Neither part claims the underlying syllabus is complete or verified; it is demonstration data.

## Part A — Curriculum Catalogue and Time-Aware Engine

Generated from a real browser run: **Microsoft Edge 157.0.4341.46 via playwright-core**, started 2026-11-11T18:14:50.042Z (UTC).

### A1. Result summary

| Check | Result | Detail |
|---|---|---|
| Backend pytest | PASSED | 117 passed |
| Frontend Vitest | PASSED | 195 tests in 20 files (17 coverage-library and 15 catalogue tests are new; 19 tests of the retired verification/review screens were removed) |
| TypeScript typecheck | PASSED | tsc --noEmit exit 0 |
| Production build | PASSED | built; Vite still warns about one application chunk over 500 kB |
| Lint | NOT RUN | no linter installed or configured; none invented |
| Real-browser acceptance: Curriculum Catalogue + Time-Aware (this assignment) | PASSED | 30/30 steps, Microsoft Edge 157; 28 steps interact with the live UI, 2 are API/state checks (TA03 bulk requirement seed, TA11 invariants); 0 console errors, 0 failed requests |
| Real-browser acceptance: platform suite re-run on the final code | PASSED | 65/65 on the final run. An earlier run on an earlier build scored 64/65 from one 30-second page.goto timeout in step I01; it did not reproduce |
| Original databases | UNCHANGED | SHA-256 of all four identical to the start of the session |
| Isolated database | PASSED | integrity ok, 0 foreign-key violations; the 531-node syllabus import and the run's coverage records are stored there; the original has no planning tables |

### A2. Implemented

- The existing Curriculum Catalogue (routes `/curriculum/catalogue` and `/curriculum/catalogue/:grade/:subject`, existing sidebar entry) simplified in place to: select class -> select subject -> the full available syllabus with coverage. No new page, route or navigation item exists; `/curriculum/course` is not found.
- Three coverage statuses only (green Done, grey Not done, orange In progress), one inline status control per teachable topic, calculated chapter status, overview percentage and counts, expandable chapters, responsive layout, read-only for Principal, unauthorized for students. No source-quality, verification, publication or approval UI remains in the catalogue.
- Coverage stored in the existing planning workspace (`COVERAGE_UPDATE`) with server-side role, status and append-only history rules; classroom execution moves coverage only when the plan's completion rule says so; scheduling, approvals, lost periods, recovery and homework never do.
- One syllabus source of truth and one teachable-topic rule shared by the catalogue, the Time-Aware allocator, coverage and progress; both modules open the same default dataset; the Time-Aware tables show a read-only 'Syllabus coverage' tag per topic.
- Converter `scripts/build_planning_import.py` from the validated NCERT review package to the existing syllabus import format (headings and locators only), with true document order.

### A3. Browser verified (this assignment)

- Curriculum Catalogue: opened from its existing sidebar entry (no 'Course Curriculum' link, `/curriculum/course` not found); Class VI -> Mathematics lands on `/curriculum/catalogue/6/mathematics`; full syllabus (10 chapters, 65 teachable topics) equal to an independent computation from the import file; no tabs, review/approval/publication controls or source-quality wording; expand/collapse; In progress (orange) -> Done (green) -> Not done (grey) with counts and percentage; chapter aggregation; refresh, logout/login and a fresh session; all six class/subject combinations listed in full; Science, VII and VIII changes; 390 px layout; principal read-only, student unauthorized, API refusals.
- Time-Aware Engine: the same 65 topics in the same order as the catalogue, each with a coverage tag equal to the catalogue state; calendar configuration; schedule generation compared with an independently derived timetable (195 periods, 210 of capacity); principal approval; recording lost periods #1 and #2 together; recovery proposal rows equal to a first-principles derivation (Core recovered in later topics' Non-Core slots #6 and #9 inside the 3-teaching-day window); rejection leaving v1 intact; a second proposal approved as v2; Core 130 / Non-Core 65 accounting with no lost, duplicate or non-teaching slots; progress (3 lost periods are not lost days; 65 subject teaching days vs the 70-day school calendar).
- Integration: scheduling, approval, lost periods, rejection and recovery approval left catalogue coverage unchanged; partial classroom teaching made a topic In progress, completion made it Done, homework did not; the Time-Aware page showed the completed topic as Done and a scheduled topic as Not done; a manual override was recorded and the catalogue showed that classroom records show the topic taught; v2, coverage and execution persisted into a fresh session.

### A4. Not verified

- Prerequisite constraints, shared cross-subject instruction, topics with only Core or only Non-Core periods, insufficient-capacity shortfall display, Deferred and Assessment evidence: covered by engine/recovery Vitest tests only.
- The Time-Aware workflow was run in the browser for Class VI Mathematics only; the catalogue was browser-verified for all six combinations.
- The 65 requirement approvals for Class VI Mathematics were seeded through the real API (teacher proposes, principal approves) with the app's own governance functions, not clicked through 65 times.
- The retired verification/review screens and the API-mode catalogue screens are retained in the repository but unrouted; they are exercised only by the unchanged `ApiScreens` tests rendering the components directly. With `VITE_CURRICULUM_DATA_SOURCE=api` the catalogue pages now still show the simplified view (they read planning datasets), not the old API screens.
- Two teachers editing coverage for the same topic at once: the revision/409 mechanism is shared with the rest of the workspace (browser-verified for the Academic Configuration), not separately exercised for coverage.
- Coverage is one record per topic for the whole school workspace; per-section or per-teacher coverage is not modelled.
- Parent role, Firefox/Safari, a served production build and an automated accessibility audit were not used. Screenshots were reviewed by eye for the catalogue home, the Class VI Mathematics views and the Time-Aware table only.

### A5. Blocked by missing data or external dependencies

- A complete or verified syllabus: the NCERT review package is a structural inventory (incomplete by its own validation report). Publication, textbook-text storage and official outcome wording are blocked until NCERT grants written permission.
- Approved Core/Non-Core requirements for the other 350 topics (and all of VII/VIII/Science) need reviewers in the app; none were invented.
- Without the Admin import of the NCERT heading structure, a fresh environment shows only the 10 built-in research rows (2 topics per class and subject).

### A6. Browser steps

30/30 passed; 28/28 UI-interaction steps; API/state-check steps: TA03, TA11.

| Test ID | Role | Workflow | Expected behaviour | Actual behaviour | Result |
|---|---|---|---|---|---|
| CC00 | admin | Load the NCERT heading structure through the existing Syllabus import | Import validated and stored as one dataset; 531 nodes in the shared workspace | 531 nodes stored at revision 1 | PASS |
| CC01 | teacher | Open the Curriculum Catalogue from its existing sidebar entry | Header, subtitle and the single neutral notice; three class choices; no subject or syllabus yet; no extra route or navigation item exists | As expected | PASS |
| CC02 | teacher | Select Class VI then Mathematics; view the full syllabus | Overview counts and chapters equal the independently computed syllabus (65 teachable topics, 10 chapters) | 10 chapters, 65 teachable topics | PASS |
| CC03 | teacher | Expand chapters: sections, topics and subtopics; resources absent | Collapsed rows hide topics; one chapter expands to exactly its teachable topics; Expand all shows all 65 | As expected | PASS |
| CC04 | teacher | No source-quality, approval or publication wording in the module chrome | Header, selectors, overview, legend and status options contain none of the banned words | As expected | PASS |
| CC05 | teacher | Inline status: In progress -> Done -> Not done on one topic | Orange, green and grey; counts and percentage recalculate immediately | percent 1.5%; server history IN_PROGRESS>DONE>NOT_DONE>DONE by teacher | PASS |
| CC06 | teacher | Chapter status is calculated from its topics | All topics Done = Done; a mixture = In progress; counts "x of y" | As expected | PASS |
| CC07 | teacher | Refresh, log out and back in, and a fresh browser session | Coverage, counts and chapter status persist each time | 5 Done of 65 persisted across refresh, re-login and a fresh principal session | PASS |
| CC08 | teacher | All six class/subject combinations list the full available syllabus | For each: chapter count, teachable-topic total and every chapter title match the independent computation | Class VI Mathematics: 10 ch / 65 topics; Class VI Science: 12 ch / 65 topics; Class VII Mathematics: 15 ch / 65 topics; Class VII Science: 12 ch / 78 topics; Class VIII Mathematics: 14 ch / 58 topics; Class VIII Science: 13 ch / 84 topics | PASS |
| CC09 | teacher | Set coverage in Science and Classes VII and VIII | Each change shows the right colour and updates that combination's totals only | Class VI Science: 1.5%; Class VII Mathematics: 1.5%; Class VIII Science: 1.2% | PASS |
| CC10 | teacher | Mobile layout (390 px) | No horizontal overflow; status control usable; chapters expand | As expected | PASS |
| CC11 | principal/student | Permissions | Principal read-only (disabled controls); student sees a staff-only message; API refuses both | As expected | PASS |
| TA01 | admin | Academic Configuration: holiday 2 Apr, exam 6 Apr, 3 Mathematics periods per day, 70-day horizon | Saved; the calendar skips the holiday, weekend and exam | As expected | PASS |
| TA02 | teacher | Time-Aware Engine lists the same topics as the Curriculum Catalogue (same class and subject) | Same count and the same titles, in the same order; activities/headings are not units; every topic flagged as missing an approved requirement | 65 topics in the same order as the Curriculum Catalogue, each with its catalogue coverage tag | PASS |
| TA03 | teacher+principal (bulk API seed) | Approve 2 Core + 1 Non-Core for each of the 65 topics (teacher proposes, principal approves; seeded through the real API with the app's own governance functions) | Server accepts both; 65 approved records; no fixed ratio is implied by the engine | As expected | PASS |
| TA04 | teacher | Generate the schedule from the approved requirements | Required 195 periods; calendar capacity 210; draft allocation equals the independently derived timetable (each topic: 2 Core then 1 Non-Core, in order) | As expected | PASS |
| TA05 | principal | Principal approves the schedule | v1 approved; the catalogue shows nothing Done because topics were scheduled | scheduled+approved: Done stays 5; manual records: 5 | PASS |
| TA06 | teacher | Record a Lost Day: periods #1 and #2 together (both Core of the first topic) | One submission; only those two periods lost; calendar and v1 unchanged; one pending proposal | As expected | PASS |
| TA07 | principal | Review the recovery proposal | Changed periods equal the derivation: #1,#2 lost on 04-01; Core recovered in the next topics' Non-Core slots #6 (04-03) and #9 (04-07), which move to independent learning; 0 Core unresolved | #1 2026-04-01 Lost What is Mathematics? What is Mathematics? (Core) Core period lost (Election Duties). \|\| #2 2026-04-01 Lost What is Mathematics? What is Mathematics? (Core) Core period lost (Election Duties). \|\| #6 2026-04-03 Core recovered What is | PASS |
| TA08 | principal | Reject it (reason required); v1 stays authoritative; coverage untouched | Rejected with a note; v1 identical; no execution-derived coverage | As expected | PASS |
| TA09 | teacher | Generate another proposal: also lose period #4 (second topic, Core) | New pending proposal covering all unresolved losses; v1 still authoritative | As expected | PASS |
| TA10 | principal | Approve the new proposal | v2 created from v1, linked to the proposal; v1 unchanged | As expected | PASS |
| TA11 | server | Reconcile v2 against independent invariants | Core 130 and Non-Core 65 account exactly; no lost, duplicate or non-teaching slots; recovered Core is within 3 teaching days; calendar unchanged | Core 130 classroom + 0 unresolved = 130; Non-Core 62 classroom + 3 independent = 65; lost 3 | PASS |
| TA12 | teacher | Progress: lost periods are not lost days; metrics distinct | 3 lost periods recorded; subject teaching days "of 65" (195 periods / 3 per day; the school calendar has 70); no "lost day" count | Teaching days completed 0 of 65 days · 0% Completed: 0 All periods lost: 0 Not yet done: 65 | PASS |
| TA13 | teacher | Catalogue coverage is unchanged after lost periods, rejection and recovery approval | Done count identical; nothing execution-derived | As expected | PASS |
| TA14 | teacher | Daily Curriculum: partially complete a topic, then complete it | Coverage: Not done -> In progress (orange) after a partial period -> Done (green) when the required teaching is complete; history source EXECUTION | As expected | PASS |
| TA15 | teacher | Homework assigned does not make a topic Done | Coverage for that topic stays Not done; homework is shown as not counted | As expected | PASS |
| TA16 | teacher | Manual override never silently contradicts classroom records | Setting the completed topic back to Not done is recorded manually; the page shows that classroom records show it taught | As expected | PASS |
| TA17 | teacher | Fresh session: approved v2, coverage and execution all persisted | New browser context shows v2 and the same coverage numbers | As expected | PASS |
| UI01 | all roles | Curriculum Catalogue route sweep | Staff roles load it; mobile shows no overflow; no uncaught page errors | As expected | PASS |

Console errors recorded by this run: 0; failed API requests: 0.

### A7. Defects and changes in this assignment

| Ref | Issue | Found by | Fix | Test |
|---|---|---|---|---|
| C0 | A separate Course Curriculum page, route and sidebar entry had been added (duplicate of the catalogue) | Your correction | Page, route, nav items and its test deleted; the existing catalogue pages rewritten in place | CatalogueScreens.test.tsx (asserts no extra link or route); browser CC01 |
| C1 | A topic and its own subtopic were both counted as teachable units (double counting) | Scope requirement | eligibleUnits(): a topic that only heads teachable children is a heading; PlanningSyllabus test updated to the new rule | coverage.test.ts, PlanningSyllabus.test.ts |
| C2 | Time-Aware always opened the first dataset, so it could list different topics from the catalogue | Parity requirement | defaultDatasetFor() shared by both modules | CatalogueScreens.test.tsx, browser TA02 |
| C3 | Archive order_in_book is a per-kind counter in the Science books, so converted topics were out of textbook order | Own cross-check of converted order | Document order rebuilt from chapter, page, block and line | test_ncert_review_import.py |
| C4 | Chapter titles truncated on a 390 px screen | Screenshot review | Titles wrap | browser CC10 (overflow) and screenshot |
| C5 | Scheduled periods carried no indication of syllabus coverage in the Time-Aware tables | Requirement | Read-only 'Syllabus coverage' tag per topic (Time-Aware and Daily Curriculum tables) | CatalogueScreens.test.tsx, browser TA02/TA14 |
| - | Early acceptance-script failures (wrong selectors, a step editing a topic an earlier step relied on, expecting 70 school days where the subject metric is 65) | First browser runs | Script corrected; product behaviour was right | n/a |

### A8. Database

- Original databases unchanged (hashes in the platform report below). All imports, migrations and runs used `<ACCEPT_DIR>/lumeneios_e2e.db`, recreated from a copy of lumeneios.db by e2e/reset_env.sh before every run, with DATABASE_URL set explicitly.
- The isolated copy holds the Admin-imported 531-node syllabus dataset in the planning workspace and the coverage records created by the final run.

### A9. Files

**Modified:** `apps/lumeneios/src/features/curriculum/pages/CatalogueDashboard.tsx and pages/CatalogueCombinationPage.tsx (rewritten in place)`; `apps/lumeneios/src/features/curriculum/types.ts (OpenEvidence moved here); pages/views/*.tsx and pages/api/*.tsx (import paths only)`; `apps/lumeneios/src/features/curriculum/__tests__/CatalogueScreens.test.tsx (rewritten), __tests__/ApiScreens.test.tsx (imports only)`; `apps/lumeneios/src/lib/planning/syllabus.ts, store.ts; src/pages/time-aware/PlanDetail.tsx, TimeAwareEngine.tsx, planningUi.tsx`; `apps/lumeneios/backend/app/services/planning_workspace_service.py, backend/app/api/v1/planning.py, backend/app/services/ncert_review_import.py`; `apps/lumeneios/src/test/PlanningSyllabus.test.ts; apps/lumeneios/package.json (e2e:course script)`

**Added:** `apps/lumeneios/src/features/curriculum/components/CoverageSyllabus.tsx, components/CountsBar.tsx`, `apps/lumeneios/src/lib/planning/coverage.ts, src/test/planning/coverage.test.ts, backend/tests/test_course_coverage.py`, `apps/lumeneios/scripts/build_planning_import.py, e2e/course_curriculum.mjs, e2e/make_cc_section.py`, `apps/lumeneios/docs/COURSE_CURRICULUM_IMPLEMENTATION.md`

### A10. Launch

```powershell
cd C:\Users\Tanav\Downloads\DP\CODE\arena\apps\lumeneios
$env:ACCEPT_DIR="C:/path/outside/repo/acceptance"
bash e2e/reset_env.sh                      # isolated copy of lumeneios.db, NCERT draft staged, backend on :8000
npx vite --port 3000                       # frontend: http://localhost:3000  (Curriculum Catalogue: /curriculum/catalogue)
venv\Scripts\python.exe -I scripts/build_planning_import.py --zip ..\..\LumenEIOS_NCERT_Review_Batch_01.zip --out "$env:ACCEPT_DIR/ncert_structure_import.json"
# Admin: Time-Aware Engine > Syllabus & classification > paste that JSON > Validate and import
$env:NCERT_IMPORT="$env:ACCEPT_DIR/ncert_structure_import.json"; $env:SHOTS="$env:ACCEPT_DIR/screenshots"; $env:OUT_DIR=$env:ACCEPT_DIR; npm run e2e:course
```


---

## Part B — Platform acceptance (re-run on the final code)

Generated from a real browser run: **Microsoft Edge 157.0.4341.46 via playwright-core**, started 2026-11-11T18:13:26.210Z (UTC). Verification date: 2026-11-11.
Repository `C:\Users\Tanav\Downloads\DP\CODE\arena` · branch `integration/curriculum-catalogue` · no commits were made by this work.

## 1. Result summary

| Check | Result | Detail |
|---|---|---|
| Backend pytest | PASSED | 117 passed (pytest backend/tests) |
| Frontend Vitest | PASSED | 212 tests in 21 files |
| TypeScript typecheck (tsc --noEmit) | PASSED | exit 0 |
| Production build (npm run build) | PASSED | built; entry chunk reduced 1,355 kB -> 724 kB; Vite's >500 kB chunk warning remains for the application chunk |
| Lint | NOT RUN | No linter (eslint/ruff/flake8) is installed or configured in the project; none was invented |
| Real-browser acceptance | PASSED | 54/54 browser-interaction steps (65/65 including 11 API/state-check steps); Microsoft Edge 157 driven by playwright-core, from a freshly created isolated database |
| Live API checks | PASSED | Included in the browser run: A01, A07, C05, D02, E06, H01-H06 (401/403/409 and server-side rejection of tampered approvals) |
| Original databases | UNCHANGED | SHA-256 of all four original .db files identical before and after |
| Isolated DB integrity / foreign keys | PASSED | PRAGMA integrity_check ok; 0 foreign-key violations |
| NCERT staging idempotency | PASSED | Re-running the importer returned ALREADY_STAGED; 540 nodes, 1 batch (no duplicates) |

Overall: **65/65 steps passed**. Of these, **54/54 steps interacted with the live UI in a real browser** (frontend :3000, backend :8000, isolated database); the other 11 are API/state checks against the running backend (A01, A07, F06, G05, H01, H02, H03, H04, H05, H06, K03) and are not browser interaction. Several browser steps also verify server state over the API.

## 2. Real-browser acceptance steps

| Test ID | Role | Workflow | Expected behaviour | Actual behaviour | Result |
|---|---|---|---|---|---|
| A01 | anonymous | Planning API without a token | 401 even though DEMO_MODE is on | 401 | PASS |
| A02 | anonymous | Open a protected route without a session | Redirected to login | http://localhost:3000/login | PASS |
| A03-admin | admin | 1-click demo login and role landing page | Lands on /admin/dashboard | http://localhost:3000/admin/dashboard · nav: Platform Overview, Schools Directory, Users & Roles, Academic Config, Planning Oversight, Time-Aware Engine Core, AI Question Studio AI, Auto-Grade & OCR Batch, Curriculum Catalogue VI–VIII, Audit & Security | PASS |
| A03-principal | principal | 1-click demo login and role landing page | Lands on /principal/dashboard | http://localhost:3000/principal/dashboard · nav: Academic Config, Campus Dashboard, Teacher Assignments, Classes & Roster, Curriculum Oversight, Time-Aware Engine Pacing, AI Question Studio AI, Auto-Grade & OCR Batch, Curriculum Catalogue VI–VIII, Compliance R | PASS |
| A03-teacher | teacher | 1-click demo login and role landing page | Lands on /teacher/dashboard | http://localhost:3000/teacher/dashboard · nav: Teacher Dashboard, My Classes & Heatmap, Time-Aware Engine Key, Curriculum Catalogue VI–VIII, Daily Curriculum, AI Question Studio AI, Differentiated Homework, Auto-Grade & OCR Batch | PASS |
| A03-student | student | 1-click demo login and role landing page | Lands on /student/dashboard | http://localhost:3000/student/dashboard · nav: My Learning Mission, My Competencies, Adaptive Practice | PASS |
| A04 | teacher | Session persists across reload | Still signed in as teacher after reload | As expected | PASS |
| A05 | teacher | Form login with the demo password; wrong password | Correct credentials sign in; a wrong password must not | As expected | PASS |
| A06 | student | Student opens a teacher route directly | Blocked (unauthorized page or redirect) | http://localhost:3000/teacher/time-aware | PASS |
| A07 | student/teacher | Server-side authorization over the API | Student 403 on planning; teacher 403 on config save; stale revision 409 | As expected | PASS |
| A08 | teacher | Logout | Session cleared and protected routes redirect to login | As expected | PASS |
| B01 | admin | Open Academic Configuration; defaults visible | Calendar, weekdays, period settings and entries shown | As expected | PASS |
| B02 | admin | Validation: overlapping/invalid calendar entries are rejected | A validation message appears and saving is blocked | As expected | PASS |
| B03 | admin | Configure calendar: holiday 2 Apr, exam 6 Apr, 3 Mathematics periods/day, 3-day horizon | Configuration is valid and saves; first three teaching dates skip the holiday, weekend and exam | server revision 1 | PASS |
| B04 | principal | Principal can also edit/save the shared configuration; teacher cannot | Principal sees the same saved values; teacher has read-only/disabled save | As expected | PASS |
| C01 | teacher | Time-Aware Engine: Class VII Mathematics lists only conceptual topics | Topics shown with source provenance; no activity/exercise units; both flagged as lacking approved requirements | As expected | PASS |
| C02 | teacher | Schedule generation is blocked or empty while requirements are unapproved | Nothing is scheduled; 0 approved periods; shortfall not invented | As expected | PASS |
| C03 | teacher | Propose per-topic requirements: 8.1 = 3 Core + 1 Non-Core; 8.2 = 2 Core + 3 Non-Core | Both proposals recorded as awaiting review (different splits, no fixed ratio) | As expected | PASS |
| C04 | teacher | A proposal cannot enter the scheduler while only proposed | Engine still shows 0 approved required periods | As expected | PASS |
| C05 | teacher | Teacher cannot approve a requirement (UI and API) | No approve button for teacher; API approval returns 403 | As expected | PASS |
| C06 | principal | Principal reviews and approves both requirements | Both approved with reviewer identity; audit summary states the exact counts | As expected | PASS |
| D01 | teacher | Generate the schedule from approved requirements | Calendar-aware draft: 9 required = 9 available; allocation equals the independently derived timetable | draft allocation matches independent derivation: 2026-04-01#1C 2026-04-01#2C 2026-04-01#3C 2026-04-03#1N / 2026-04-03#2C 2026-04-03#3C 2026-04-07#1N 2026-04-07#2N 2026-04-07#3N | PASS |
| D02 | teacher | Teacher cannot approve the schedule | No approve button for teacher; API approval returns 403 | As expected | PASS |
| D03 | principal | Principal approves the schedule | Plan APPROVED with exactly one version v1 approved by the principal; draft panel disappears | As expected | PASS |
| E01 | teacher | Daily Curriculum shows the approved v1 schedule | Heading for Class 7 Mathematics; 9 scheduled periods by period; no pending change notice | As expected | PASS |
| E02 | teacher | Record a Lost Day: select periods #1 and #2 together | Dialog lists all 9 periods with date/class/subject/topic/Core-Non-Core; submit disabled until a reason is given; re-toggling never duplicates | recorded #1,#2 in one submission | PASS |
| E03 | teacher | Only the selected periods are lost; calendar and approved schedule untouched | One loss record [1,2]; exactly one pending proposal; v1 and calendar byte-identical; loss not written into the calendar | As expected | PASS |
| E04 | teacher | Recorded periods cannot be selected again | 7 selectable periods; period 1 disabled under "all" | As expected | PASS |
| E05 | teacher | Teacher sees recovery as PROPOSED only | 2 lost periods; proposal 2 Core recovered / 2 Non-Core to independent learning / 0 unresolved; approved recovery counter 0 | As expected | PASS |
| E06 | teacher | Teacher cannot approve recovery (UI and API) | No approve button; API approval by a teacher returns 403 | As expected | PASS |
| F01 | principal | Review the recovery proposal: original vs proposed, every change explained | Loss summary, original (v1) and proposed columns, changed-period rows match the independently derived recovery | #1 2026-04-01 Lost Multiplication of Fractions Multiplication of Fractions (Core) Core period lost (Election Duties). \|\| #2 2026-04-01 Lost Multiplication of Fractions Multiplication of Fractions (Core) Core period lost (Election Duties). \|\| #4 2026-04-03  | PASS |
| F02 | principal | Reject the proposal (reason required) | No reason -> alert; with reason the proposal is REJECTED, v1 stays authoritative, the loss record is retained | As expected | PASS |
| F03 | teacher | After rejection the teacher still sees the original approved schedule | No change notice; 2 lost awaiting recovery; 1 rejected kept; 0 approved revisions | As expected | PASS |
| F04 | teacher | Generate another proposal: record period #5 (Division Core) as lost | A new pending proposal is created; v1 still authoritative; 3 lost periods in total | As expected | PASS |
| F05 | principal | Approve the new proposal | v2 created from v1, approved by the principal, linked to the proposal; v1 unchanged | As expected | PASS |
| F06 | server | Reconcile approved v2 against independent invariants | Core and Non-Core accounting closes exactly; no lost/duplicate/non-teaching slots; calendar unchanged | Core 5 classroom + 0 unresolved = 5; Non-Core 1 classroom + 3 independent = 4; lost 3 | PASS |
| G01 | teacher | Daily Curriculum reflects the approved v2 after reload | Change notice names v2; lost periods labelled with reason/note; Core recovery rows; independent learning shown as not taught | As expected | PASS |
| G02 | teacher | Record execution: Multiplication completed as scheduled | Classroom progress rises by the topic's approved classroom periods only | As expected | PASS |
| G03 | teacher | Homework is not classroom teaching | Division recorded as homework leaves classroom progress unchanged and shows "not counted as completed" | As expected | PASS |
| G04 | teacher | Progress metrics: lost periods are not lost days | Teaching days "x of 3"; lost periods recorded = 3; academic calendar unchanged | Teaching days completed 1 of 3 days · 33% Completed: 1 All periods lost: 0 Not yet done: 2 \| LOST PERIODS AND RECOVERY Proposal pending Lost periods recorded 3 3 Core · 0 Non-Core Lost, awaiting approval 0 3 in approved schedule Core recovered (approved) 3 of | PASS |
| G05 | server | Homework triggers a pending proposal; approved schedule stays v2 until approval | Pending proposal exists; 2 versions | As expected | PASS |
| H01 | principal (API) | Stale approval of a proposal built on an older version | Server answers 403 "Stale proposal" although the principal is authorised | As expected | PASS |
| H02 | principal (API) | Approve a proposal whose allocation uses the configured holiday | Server answers 403 "not a teaching date" | As expected | PASS |
| H03 | principal (API) | Approval that silently drops a topic | Server answers 403 "silently dropped" | As expected | PASS |
| H04 | principal (API) | Approval that double-books a period | Server answers 403 "allocated to both" | As expected | PASS |
| H05 | principal/admin (API) | Re-open a decided proposal; rewrite an approved schedule version | Server answers 403 for both | As expected | PASS |
| H06 | admin (API) | Workspace history and audit trail | Every change is a numbered revision with action and authenticated actor; audit entries carry the stamped actor | 13 revisions; roles teacher,principal,admin | PASS |
| I01 | principal | Fresh browser context (no local storage): approved v2 persists on the server | New session sees v2 as authoritative | As expected | PASS |
| J01 | admin+principal | Two sessions edit the Academic Configuration; the second save is stale | Stale save refused with a conflict message, typed input kept, server keeps the first save | As expected | PASS |
| J02 | teacher | A failed workspace load is not an empty revision-0 workspace | With an invalid backend token the app re-authenticates or shows an error; it never saves over real data | As expected | PASS |
| K01 | admin | Curriculum catalogue loads and does not present draft NCERT staging as verified or complete | Page loads; no completeness / production-ready claim | Curriculum Catalogue VI–VIII Audit & Security Pedagogical Guardrail Approved topic requirements determine Core and Non-Core periods. Core classroom periods remain protected. Curriculum Catalogue Explore the syllabus and track teaching cover | PASS |
| K02 | admin | Only conceptual topics are schedulable units in the planner | Class VII Mathematics shows exactly 2 unit rows (topics); the scheduler has 2 lessons | As expected | PASS |
| K03 | admin | Staged NCERT review batch (isolated database) | Draft structure only: 540 nodes, complete_curriculum=false, production_ready=false | status STAGED_DRAFT, nodes 540, complete_curriculum=false | PASS |
| L-admin-1440 | admin | UI sweep at 1440px | Every route renders content, no uncaught errors, no horizontal page overflow, no redirect away | 7 routes ok | PASS |
| L-admin-390 | admin | UI sweep at 390px | Every route renders content, no uncaught errors, no horizontal page overflow, no redirect away | 7 routes ok | PASS |
| L-principal-1440 | principal | UI sweep at 1440px | Every route renders content, no uncaught errors, no horizontal page overflow, no redirect away | 5 routes ok | PASS |
| L-principal-390 | principal | UI sweep at 390px | Every route renders content, no uncaught errors, no horizontal page overflow, no redirect away | 5 routes ok | PASS |
| L-teacher-1440 | teacher | UI sweep at 1440px | Every route renders content, no uncaught errors, no horizontal page overflow, no redirect away | 7 routes ok | PASS |
| L-teacher-390 | teacher | UI sweep at 390px | Every route renders content, no uncaught errors, no horizontal page overflow, no redirect away | 7 routes ok | PASS |
| L-student-1440 | student | UI sweep at 1440px | Every route renders content, no uncaught errors, no horizontal page overflow, no redirect away | 1 routes ok | PASS |
| L-student-390 | student | UI sweep at 390px | Every route renders content, no uncaught errors, no horizontal page overflow, no redirect away | 1 routes ok | PASS |
| L-parent-1440 | parent | UI sweep at 1440px | Every route renders content, no uncaught errors, no horizontal page overflow, no redirect away | 1 routes ok | PASS |
| L-parent-390 | parent | UI sweep at 390px | Every route renders content, no uncaught errors, no horizontal page overflow, no redirect away | 1 routes ok | PASS |
| L-keyboard | teacher | Keyboard: Record a Lost Day dialog is operable and dismissible | Reachable by keyboard, role=dialog, focus moves into it, Escape closes it | As expected | PASS |
| L-404 | teacher | Unknown route | A not-found page, not a blank screen | As expected | PASS |

Run history (each from a freshly created isolated database): a first partial run (24 steps) found 4 failures; full runs then scored 30/65, 62/65, 64/65, 65/65, 65/65 and 65/65; after the later Course Curriculum work the suite was re-run on the final code: one run scored 64/65 (a 30-second page.goto timeout in I01, not an assertion failure) and the immediately following full run scored 65/65. Most early failures were errors in the acceptance script itself (wrong selectors, a `<select>` filled as text, CSS-uppercased headings, an unimported variable), not product defects. The product defects the browser found are D6, D7, D8 and D9 in section 5. This table is the final run.

### Console / network issues recorded by the final run

- 7 browser console errors and 7 failed requests in the final run, all deliberate: A05 (wrong-password sign-in -> 401) and J02 (invalid backend token -> 401 on workspace, documents and /auth/me).
- Before the fixes in section 5 the same suite recorded 123 console errors (118 were avoidable 401s on /planning/workspace during sign-in).

## 3. Not verified in a real browser

- Execution statuses Partial, Deferred and Assessment evidence: covered only by Vitest. The browser run exercised Completed as scheduled and Homework.
- Prerequisite constraints, shared cross-subject instruction, topics with only Core or only Non-Core periods, and the insufficient-time shortfall display: covered by engine/recovery Vitest tests only. The browser run used one calendar (holiday + weekend + examination day) with a sufficient-capacity timetable for Class VII Mathematics.
- Class VI and VIII, and Science: not driven in the browser (Vitest journey tests cover Class VI Science).
- Activities, investigations and exercises staying attached resources: covered by Vitest. The built-in verified dataset contains no resource nodes and the dataset-import UI was not driven in the browser.
- The legacy-requirement warning on screen: covered by component tests. A legacy plan cannot be created through the UI, so it could not be shown in a real browser.
- Student and parent roles: only landing pages, route sweeps at 1440 px and 390 px, and access restrictions were checked; their dashboards' content was not verified.
- Only Microsoft Edge was used. Firefox/Safari were not tested. Accessibility was checked for keyboard operation of the Record a Lost Day dialog only; no automated accessibility audit (e.g. axe) was run.
- The frontend was served by the Vite dev server; the production build was compiled but not served and browsed.
- Screenshots were captured for key steps and the 390 px sweeps (scratchpad/acceptance/screenshots, not committed) but visual quality was only reviewed automatically (overflow, empty pages, errors) plus one manual look at the recovery proposal screen.

## 4. Known limitations and remaining external dependencies

- The scheduling allocator runs in the browser. The server now rejects persisted schedule versions and proposals that double-book a period, use a non-teaching date or an out-of-range period, drop a topic, reduce an approved Core count, break requirement arithmetic, or approve a stale/unlinked proposal. It does NOT recompute the allocation, so a client could still submit a structurally valid but unfaithful schedule (for example ignoring prerequisites or Core-first order). Full server-side recomputation needs a shared allocator (e.g. porting engine.ts) and was not attempted to avoid a duplicate, inconsistent allocation path.
- Broader demo-mode exposure remains: DEMO_MODE defaults to true, so every router except planning still resolves a request with no token to the first admin user. Only the planning router was hardened.
- Demo authentication is not production authentication: the demo password is in the documented README and apiClient default, the persona switcher and 1-click buttons sign in as any role without a password, and the planning store logs in on behalf of the selected persona. This is by design for demonstrations; production needs real accounts and no embedded credentials.
- The planner uses only the built-in source-checked research dataset (10 chapter/topic rows, two topics per class/subject). The 540 staged NCERT draft nodes are not visible to the planner or the published catalogue and carry no approved Core/Non-Core requirements or period counts.
- The curriculum is not complete. The review package is a structural inventory; semantic extraction, explicit-outcome audit, visual review and expert verification are missing. Publication and text storage remain unauthorised until NCERT grants written permission (NCERT_SOURCE_POLICY.md).
- Core/Non-Core requirements for the 540 staged nodes require reviewers in the application; none were invented.
- Vite still warns about a >500 kB application chunk; route-level lazy loading would fix it but breaks the many synchronous component tests, so it was not applied.
- The Reset Demo Data button in the top bar was not exercised and its effect on the shared planning workspace was not verified.

## 5. Defects found and fixed in this work

| Ref | Defect | Found by | Fix | Regression test |
|---|---|---|---|---|
| D1 | Activities and investigations were independently schedulable units | Code review against the spec | Only TOPIC and SUBTOPIC are schedulable; ACTIVITY/INVESTIGATION/EXAMPLE/EXERCISE are attached resources | src/test/planning/engine.test.ts |
| D2 | isLegacyRequirement() existed but no screen warned about legacy single-total requirements | Prior report | Shared LegacyRequirementNote shown in the schedule comparison, plan detail and engine tables | src/test/planning/legacy.test.tsx |
| D3 | With DEMO_MODE on, an anonymous request to the planning API became the admin user | Live API check | Planning router requires a real bearer token | backend test_planning_never_falls_back_to_demo_admin_without_a_token; browser A01 |
| D4 | Server did not verify that an approved recovery proposal matched the current schedule version | Spec review | 403 on stale proposals and on approvals that do not append exactly one linked version | backend test_server_rejects_stale_or_malformed_recovery_approval; browser H01 |
| D5 | Server accepted structurally invalid schedules and proposals | Architecture review | validate_schedule(): double booking, non-teaching dates, period range, dropped topics, reduced Core, arithmetic | backend test_server_validates_*; browser H02-H04 |
| D6 | No saved session silently signed the visitor in as admin | Browser A02 | Secure by default (login required); VITE_DEMO_AUTO_LOGIN=true opts in to the old behaviour | src/test/AuthSecurity.test.tsx; browser A02 |
| D7 | The sign-in form ignored the password | Browser A05 | Password verified against the backend; unreachable backend never signs in | src/test/AuthSecurity.test.tsx; browser A05 |
| D8 | Modal dialogs did not move focus inside, trap Tab or restore focus (Record a Lost Day dialog) | Browser L-keyboard | Shared Modal focuses the dialog, wraps Tab, restores focus on close | src/test/ModalAccessibility.test.tsx; browser L-keyboard |
| D9 | Planning store sent requests certain to return 401 on the login page and on every sign-in (123 console errors) | Browser console capture | Store skips loading while signed out and signs in before the first request when no token exists | Browser console count 123 -> 7 (deliberate only); existing store tests (182) still pass; no new unit test |
| D10 | Entry bundle 1,355 kB | Build warning | Vendor libraries split into separate chunks (entry 724 kB) | Build; warning not fully removed |

## 6. Database integrity

- Original databases (apps/lumeneios): lumeneios.db 5a5fee7b3c09743dfa7a1a4dc60358f9e668a898a043aa463d8c5d47b1cc12e8; lumeneios_acceptance.db 5af49b5116617d08a109a6ba77c95a88d0928c7211f71ff5a05c83ad0a8a65b7; lumeneios_planning_dev.db d306e9c12f1876e3f9089d62fa2de99102dc2e76417248c906aa026a6cdc6175; lumeneios_takeover_acceptance.db 9056becbfd7b1de4564822379a808563dca2e13a572c62bd045eaca121a09f3e. Identical at the start, after every environment reset, and at the end.
- Isolated database used for all migrations, imports and browser runs: <ACCEPT_DIR>/lumeneios_e2e.db, recreated from a copy of lumeneios.db by e2e/reset_env.sh before each run. The backend was started with DATABASE_URL set explicitly; the original has no planning tables and no ncert_* tables, while the isolated copy holds the 14 planning revisions written by the run.
- PRAGMA integrity_check: ok. PRAGMA foreign_key_check: 0 violations.
- e2e/reset_env.sh refuses to continue if the original database hash changes; scripts/import_ncert_review.py still refuses to target lumeneios.db.
- No migration was added. Migrations 001 (catalogue) was applied to the isolated copy by the importer; the pre-existing 002/003 were not re-run against the original.

## 7. NCERT review batch

- Archive verified against its own CSV tables: 8 textbooks, 2,142 source pages, 984 structural nodes (76 chapters, 353 numbered sections, 102 numbered subheadings, 453 unnumbered heading candidates), 33 outcomes (all INFERRED), 29 relationships and 2 Core proposals (all PENDING EXPERT REVIEW), 7 prerequisites, 1,555 resource markers, 85 source files (76 chapter PDFs + 8 front-matter PDFs + 1 image).
- Staged into the isolated database as DRAFT release / VALIDATED batch: 540 nodes (3 grade, 6 subject, 76 chapter, 353 topic, 102 subtopic), all AWAITING_REVIEW and PARTIAL, rights PERMISSION_REQUIRED, nothing published; complete_curriculum=false, production_ready=false.
- Not imported: page text, quotes, 453 unreviewed heading candidates, inferred outcomes, relationships, prerequisites, Core proposals and resource markers.
- LumenEIOS_NCERT_Review_Batch_01.zip is now ignored by git (scoped rule) and was not deleted.

## 8. Files

**Modified this session:** `.gitignore`, `apps/lumeneios/package.json`, `apps/lumeneios/package-lock.json`, `apps/lumeneios/vite.config.ts`, `apps/lumeneios/src/lib/planning/syllabus.ts`, `apps/lumeneios/src/lib/planning/governance.ts`, `apps/lumeneios/src/lib/planning/engine.ts`, `apps/lumeneios/src/lib/planning/store.ts`, `apps/lumeneios/src/test/planning/engine.test.ts`, `apps/lumeneios/src/pages/time-aware/planningUi.tsx`, `apps/lumeneios/src/pages/time-aware/PlanDetail.tsx`, `apps/lumeneios/src/pages/time-aware/TimeAwareEngine.tsx`, `apps/lumeneios/src/context/AuthContext.tsx`, `apps/lumeneios/src/pages/auth/LoginPage.tsx`, `apps/lumeneios/src/components/common/Modal.tsx`, `apps/lumeneios/backend/app/api/dependencies.py`, `apps/lumeneios/backend/app/api/v1/planning.py`, `apps/lumeneios/backend/app/services/planning_workspace_service.py`, `apps/lumeneios/backend/tests/test_planning_workspace.py`

**Added this session:** `apps/lumeneios/backend/app/services/ncert_review_import.py`, `apps/lumeneios/scripts/import_ncert_review.py`, `apps/lumeneios/backend/tests/test_ncert_review_import.py`, `apps/lumeneios/docs/NCERT_REVIEW_BATCH_01_INTEGRATION.md`, `apps/lumeneios/e2e/acceptance.mjs`, `apps/lumeneios/e2e/lib.mjs`, `apps/lumeneios/e2e/reset_env.sh`, `apps/lumeneios/e2e/make_report.py`, `apps/lumeneios/src/test/AuthSecurity.test.tsx`, `apps/lumeneios/src/test/ModalAccessibility.test.tsx`, `apps/lumeneios/src/test/planning/legacy.test.tsx`, `apps/lumeneios/docs/FINAL_ACCEPTANCE_REPORT.md`, `26 curriculum/NCERT documents and CSVs plus AGENTS.md and CLAUDE.md copied (no-clobber) from arena-codex`

Pre-existing uncommitted work (Time-Aware Engine, planning workspace, catalogue, migrations 001–003, earlier tests) was preserved untouched. Secondary worktrees were not modified.

## 9. Launch instructions

```powershell
cd C:\Users\Tanav\Downloads\DP\CODE\arena\apps\lumeneios
# Isolated database (never the original lumeneios.db): copy, stage NCERT draft structure, start backend on :8000
$env:ACCEPT_DIR="C:/path/outside/repo/acceptance"; bash e2e/reset_env.sh
# Frontend
npx vite --port 3000        # http://localhost:3000
# Real-browser acceptance (uses installed Microsoft Edge via playwright-core)
$env:ACCEPT_DIR="C:/path/outside/repo/acceptance"; $env:SHOTS="$env:ACCEPT_DIR/screenshots"; $env:OUT_DIR=$env:ACCEPT_DIR; npm run e2e
```

Backend started manually must set `DATABASE_URL` explicitly, e.g. `$env:DATABASE_URL="sqlite+aiosqlite:///C:/path/acceptance/lumeneios_e2e.db"; venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000`. Without it the backend reads `.env`/the default and uses the ORIGINAL `lumeneios.db`.
Demo logins: `admin@`, `principal@`, `teacher@`, `student@`, `parent@lumeneios.demo`, password `demo123`. Sign-in is now required (no implicit admin session); set `VITE_DEMO_AUTO_LOGIN=true` only for an explicit stakeholder demo.
