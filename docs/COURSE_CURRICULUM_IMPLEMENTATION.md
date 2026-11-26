# Curriculum Catalogue: syllabus and coverage (implementation)

There is **one Curriculum Catalogue**. Course Curriculum is how that existing catalogue now displays the syllabus. No page, route or navigation item was added: the catalogue keeps its routes (`/curriculum/catalogue`, `/curriculum/catalogue/:grade/:subject`) and its sidebar entry (*Curriculum Catalogue*, Admin / Principal / Teacher, permission `VIEW_CURRICULUM_CATALOGUE`). `/curriculum/course` does not exist.

## 1. The flow (existing routes, simplified in place)
1. `/curriculum/catalogue`: **Select class** (Class VI, VII, VIII), then **Select subject** (Mathematics, Science; a subject with no syllabus is disabled and says so, nothing is fabricated). Choosing a subject opens:
2. `/curriculum/catalogue/:grade/:subject` (e.g. `/6/mathematics`): the **full available syllabus** with coverage: percentage, Done / In progress / Not done counts, a progress bar, and every chapter as an expandable row (calculated status, "done of total", sections, topics, subtopics). The existing class/subject selector switches combination without leaving the page. Unknown class/subject values redirect to the catalogue start; students get the existing unauthorized state.

Header: *Curriculum Catalogue*, "Explore the syllabus and track teaching coverage.", and the single neutral notice "Demonstration syllabus and coverage data."

## 2. The three statuses
| Status | Colour | Meaning |
|---|---|---|
| Done | green `#16A34A` | covered |
| Not done | grey `#9CA3AF` | not covered (default) |
| In progress | orange `#F59E0B` | being covered |

Each teachable topic has one compact inline `<select>` (Done / Not done / In progress) beside a colour dot. No source-quality, verification, publication or approval wording or controls remain in the catalogue.

## 3. What changed in the existing catalogue
* **Rewritten in place:** `pages/CatalogueDashboard.tsx`, `pages/CatalogueCombinationPage.tsx`. **New component inside the catalogue feature (not a page):** `components/CoverageSyllabus.tsx`. Reused: `CombinationSelector`, `UnauthorizedState`, the `ROMAN` / `SUBJECT_LABEL` / `parseGrade` / `parseSubject` helpers and the module shell `CurriculumModule`.
* **Retired from the UI (no longer routed or rendered):** the *Curriculum overview*, *Chapters & topics* and *Mapping review* tabs, the verification count bars, the data-source banner, the evidence drawer and the API-mode review screens.
* **Retained, unrouted, not deleted** (so no uncommitted work is lost): `pages/views/*`, `pages/api/*`, `components/EvidenceDrawer|DataSourceBanner|StatusBadge|...`, `api/*`, `mocks/*`. Two shared symbols moved to neutral files so these still compile: the `OpenEvidence` type (to `types.ts`) and `CountsBar` (to `components/CountsBar.tsx`). They are candidates for removal once you confirm.
* **Tests:** `__tests__/CatalogueScreens.test.tsx` rewritten for the simplified catalogue (its 19 tests of the retired verification/review screens were removed; 15 new tests cover the flow, hierarchy, statuses, persistence, permissions and parity with Time-Aware). `__tests__/ApiScreens.test.tsx` now renders the retained API components directly and is otherwise unchanged. `ncertApi`, `services` and test HTTP helpers are untouched.

## 4. One syllabus source of truth
The catalogue reads the planning syllabus datasets (`src/lib/planning/syllabus.ts`), the same datasets the Time-Aware Engine schedules from: the built-in research snapshot (`mocks/researchSnapshot.json`, the file the catalogue's own mock data is built from), any Admin-imported dataset, and the published-catalogue loader. No second syllabus dataset exists. Topic names, order and node ids are therefore identical in both modules.
* **Teachable topics** are decided by one rule, `eligibleUnits()`: TOPIC and SUBTOPIC nodes, excluding a topic that is only the heading of teachable children (a parent and child are never counted twice). Activities, investigations, examples, exercises and diagrams are resources, never units. The allocator, coverage and progress all use it.
* **Default dataset** for a class and subject, shared by both modules: `defaultDatasetFor()` (the dataset with the most teachable topics). Choosing a different dataset in the Time-Aware "Syllabus dataset" selector shows that dataset's topics there; the catalogue always shows the default.

## 5. Coverage calculations
`percent = Done / total x 100` (one decimal; in-progress does not count; empty syllabus = 0%). Chapter status is calculated (all Done = Done; all Not done = Not done; any mixture = In progress; no topics = "No topics"). The subject summary is derived from all teachable topics; nothing editable is stored as a percentage.

## 6. Persistence, permissions and execution
Coverage is `workspace.coverage` in the existing planning workspace, saved through the existing `PUT /api/v1/planning/workspace` with action `COVERAGE_UPDATE`; no second database. One record per topic: status, source (`MANUAL` / `EXECUTION`) and an append-only history. Server rules: only Admin and Teacher may change coverage; three statuses only; each change appends exactly one matching history entry; no removal or rewriting; authenticated user stamped; stale revisions return 409. Principals see it read-only.

Daily Curriculum remains the classroom evidence. Scheduling, approved schedules, lost periods, recovery proposals, rejection and approval, homework and deferrals **never** change coverage. Recording execution updates coverage in the same commit using the plan's own completion rule: a topic is **In progress** after a partial period and **Done** only when its required classroom teaching is complete; an execution-derived record follows later corrections; a manual record is only raised by newer classroom evidence. A manual override is recorded, and the topic row says when classroom records show it taught.

## 7. Time-Aware Engine
Unchanged apart from: it opens the same default dataset and teachable-topic rule, and each scheduled topic shows a read-only **"Syllabus coverage: ..."** tag (also in Daily Curriculum's by-topic table) so a scheduled period is never mistaken for covered teaching. Approved Core/Non-Core requirements, allocation, lost-period recording, recovery (3-teaching-day window), approval and versioning are untouched.

## 8. Syllabus data that is actually available
* **Built in:** the source-checked research snapshot only: 10 chapter/topic rows (about 2 topics per class and subject).
* **NCERT review batch:** an Admin imports the heading structure through the existing *Time-Aware Engine > Syllabus & classification > Import*. The file comes from `python scripts/build_planning_import.py --zip <zip> --out <path outside the repo>` (headings and PDF-page locators only; no page text, outcomes, relationships or Core/Non-Core data; not committed).

| Class and subject | Chapters | Teachable topics |
|---|---|---|
| VI Mathematics | 10 | 65 |
| VI Science | 12 | 65 |
| VII Mathematics (Parts I and II) | 15 | 65 |
| VII Science | 12 | 78 |
| VIII Mathematics (Parts I and II) | 14 | 58 |
| VIII Science | 13 | 84 |
| **Total** | **76** | **415** |

Gaps: 453 unnumbered heading candidates are not imported; resources are not listed; the package is an incomplete structural inventory, not a verified syllabus. Without the import, a fresh environment shows only the 10 built-in rows. The converter rebuilds true document order from chapter, page, block and line because `order_in_book` is a per-kind counter in some books.

## 9. Tests
* `src/test/planning/coverage.test.ts` (17): statuses/colours, history, calculations, empty data, chapter aggregation, the shared topic rule, allocator parity, execution rules.
* `src/features/curriculum/__tests__/CatalogueScreens.test.tsx` (15): the catalogue flow through the real `App`.
* `backend/tests/test_course_coverage.py` (6), `test_ncert_review_import.py` (ordering).
* `e2e/course_curriculum.mjs` (30 browser steps, Edge via Playwright, isolated database); results in `FINAL_ACCEPTANCE_REPORT.md`.
