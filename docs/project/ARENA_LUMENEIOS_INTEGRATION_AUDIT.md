# Arena × LumenEIOS integration audit

Audit date: 2026-11-12

## Repository safety inventory

| Item | Observed state |
|---|---|
| Checkout | `C:\Users\Tanav\Downloads\DP\CODE\arena` |
| Original remote | `origin` → `https://github.com/kvr-leofelix/arena.git` (fetch/push) |
| Original repository/default branch | `kvr-leofelix/arena`, `main` (`origin/HEAD` → `origin/main`) |
| Current branch before integration | `integration/curriculum-catalogue`, HEAD `3c5b796` |
| Latest original remote after fetch | `c729729` (PR #21, OCR evaluation pipeline), 36 first-parent commits after old shared base `9c62849` |
| Existing local Catalogue commits | `65916e4` (catalogue API), `2682652` (API frontend), merged at `3c5b796`; not contained by any configured remote ref |
| Configured remotes | `origin` only; no fork remote configured |
| Existing local branches/worktrees | `TANAV-codex`, `TANAV-claudecode`, `TANAV-dev`, `claude/curriculum-catalogue`; do not modify their worktrees |
| Staged changes at audit | None |
| Existing dirty tracked paths | 51 paths, including backend planning/time-aware, auth/data contexts, Catalogue, layout, dashboards, tests, package files and Vite config; one deleted Time-Aware modal |
| Existing untracked paths | Root guidance/audit docs; backend planning workspace and import; migration 003; Catalogue and planning tests; feature docs; e2e scripts; planning utilities and pages; review spreadsheets; scratchpad audit outputs |
| Existing original databases | Four app databases were previously hash-audited; no DB is to be copied into a PR. Demo DBs stay isolated and ignored. |
| Push status | Local-only Catalogue commit ancestry is absent from configured remote refs. No second configured remote exists, so no claim is made about unrelated forks. |
| GitHub CLI | `gh` is not installed. No GitHub integration tool is available in this session. |

`git fetch origin --prune` updated only remote-tracking refs. It advanced `origin/main` from `9c62849` to `c729729`; the working tree remained unchanged. No reset, clean, rebase, commit, push or worktree mutation was used during discovery.

## Latest Arena architecture and design inventory

Arena is the existing React 18 / TypeScript / Vite SPA plus FastAPI / SQLAlchemy async API. The current main host uses protected React Router routes, AuthContext/JWT-backed sessions, role permissions, a school-aware DataContext and an offline demo host selected by `DEMO_MODE`. Backend routers are registered centrally at `/api/v1`; legacy tables are SQLAlchemy entities initialized through `Base.metadata.create_all` with a narrow additive document-column upgrade, not an Alembic migration chain.

Arena main includes the differentiated-homework module and APIs, student homework submissions/history, AI question generation and grading, OCR upload/review, school onboarding, roster, notifications, audit and reporting. The remote advancement changes 186 files (31k insertions) since the local branch's old base; latest work includes OCR evaluation pipeline PR #21, AI-assisted homework evaluation PR #18, differentiated homework PR #17, roster/studio links PR #16, and preceding homework workflow PRs. These remain protected.

| Design area | Current Arena convention observed at `origin/main` |
|---|---|
| Palette | CSS custom properties in `src/styles/themes.css`; navy chrome, dynamic ink, surface/background/border/content tokens. Light mode uses purple (`#8C66D6`) accent; dark mode uses blue (`#2563EB`). |
| Theme | `ThemeContext`, `ThemeMenu`; stored `light`/`dark`; `data-theme` drives CSS tokens. |
| Typography | Inter/system sans; compact labels and clear heading hierarchy; Tailwind `font-sans`. |
| Layout | sticky Topbar, role-based Sidebar, responsive drawer, max-width content, `bg-surface-bg`; AppLayout hosts role banner and Outlet. |
| Components | Shared Button/Card/Badge/Modal patterns in `components/common`; semantic token classes (`surface-*`, `content-*`, `navy-*`, `teal-*`). |
| Forms/tables | Rounded controls, border tokens, visible focus, compact responsive overflow wrappers, inline validation/status. |
| Accessibility | Protected route loading states; accessible labels and focus styles in shared components; role-based route restrictions. |
| Loading/error states | `role=status`, route-level session status; API screens use loading/empty/error state patterns. |
| Tests | Backend pytest (temporary DB fixtures); frontend Vitest; Playwright acceptance specs/config. |

The LumenEIOS catalogue and planning screens already use many of the semantic Tailwind names, but the dirty branch modifies shared palette configuration and common UI. The integration should use Arena's remote token definitions and ThemeContext and avoid global palette replacement.

## Feature reconciliation matrix (pre-implementation)

| Area | Classification | Arena capability to preserve | Local LumenEIOS addition / conflict | Integration direction |
|---|---|---|---|---|
| Auth, roles, school scope | EXISTING IN BOTH / INCOMPATIBLE | Latest JWT/session restore, onboarding, developer role, school switch, tenant checks, password/demo-root controls | Dirty AuthContext/Login edits and planning dependencies adapted against older API | Keep latest Arena auth/session API; add only narrowly scoped planner authorization and route access; add regression tests for existing roles/session. |
| App shell, theme, navigation | EXISTING IN BOTH | ThemeContext, light/dark theme, FontSizeControl, ThemeMenu, full feature links and mobile drawer | Dirty Sidebar/AppLayout changes add Catalogue/Planning labels, role-specific links, drawer/hash behavior and demo notice | Merge routes into latest App/Sidebar; preserve every Arena link; use latest shared chrome/tokens; one Catalogue destination. |
| Catalogue/Course Curriculum | NEW IN LUMENEIOS | Arena has a legacy Curriculum API and Daily Curriculum; no full Catalogue route/source register found in latest main | Committed NCERT editorial API/review workflow and catalogue UI; current local simplified Catalogue changes; static research mock and recovered structural data in ignored demo artifacts | Add Catalogue as one route, keep Daily Curriculum; preserve API schema boundaries, no runtime sample fallback when imported full data exists; no source publication claim. |
| NCERT catalogue backend | NEW IN LUMENEIOS | Existing `/api/v1/curriculum` lesson APIs and SQLAlchemy Base | `ncert_*` models/API/migrations 001–002 and review contract; ownership rules restrict source ingestion/publication | Additive registration/migrations only; keep legacy curriculum endpoints; catalogue school-independent; no production/demo DB copy. |
| Shared syllabus identities/coverage | NEW IN LUMENEIOS | Legacy `CurriculumDay` topic text/status and coverage dashboards | stable NCERT node IDs, three-state coverage, planning workspace revisions | Map plan/topic IDs to Catalogue identity; do not replace legacy CurriculumDay API; execution alone drives classroom coverage; keep manual entries labeled. |
| Time-Aware scheduling | MODIFIED IN BOTH | Legacy disruption/pacing/compression APIs, cross-curricular proposal/audit/notifications, role/school checks | revisioned plan allocator, approved requirements, selected lost periods, recovery proposal/versioning, Day 100 scenario; dirty UI/API replaces old endpoints and deletes CompressionPreviewModal | Preserve compatible legacy endpoints/behavior and existing cross-curricular proposals; expose the revisioned engine as an additive workflow. Keep proposal/approval semantics, prevent lost-Core and homework completion errors. |
| Daily Curriculum | EXISTING IN BOTH | `/teacher/curriculum-180` and legacy class-scoped `CurriculumDay` completion | new execution period ledger with shared stable topic IDs; dirty CurriculumPlanner180 edits | Preserve route and old feature; integrate execution links where identities map; no second allocation engine. |
| Homework / independent learning | EXISTING IN BOTH | Full latest differentiated homework learner/teacher/parent workflows, AI/evaluation and submissions | plan lessons may be shifted to independent learning | Link only as tracked independent work if contract allows; do not count homework as classroom teaching or syllabus Done. Never replace the homework module. |
| AI/OCR/evaluation | EXISTING IN ARENA | latest OCR and AI question/evaluation pipeline, human review | local commits/dirty pages may overlay older assessment pages | Preserve latest components/APIs; catalogue/planning integration must not rewrite these modules. |
| Lesson planning | INCOMPLETE | Daily Curriculum has legacy objectives/topic/period concepts | Panchapadi PDF template not persisted or implemented; prior task explicitly allowed deferral | Defer structured editable lesson plan unless an additive schema/workflow can be safely implemented after base integration. No fabricated outcomes. |
| Day 100 scenario | INCOMPLETE / demo-only | no upstream production requirement | isolated `scratchpad/acceptance/lumeneios_day100.db`, revisions/loss/recovery/history | Keep isolated locally for browser proof; never commit/import into production or PR. Seed reproducibly only if non-sensitive and schema-approved; do not check in database. |
| Database migrations | EXISTING IN BOTH / INCOMPATIBLE | SQLAlchemy model registration and create_all; no configured Alembic migrations | NCERT 001–002 and planning workspace 003 additive scripts | Review script ordering/idempotency and PostgreSQL compatibility; avoid destructive DDL; no unrelated schema replacement. |
| Tests and acceptance | EXISTING IN BOTH | expanded Arena backend/frontend/Playwright tests | local catalogue, planning, live API and Day100 scripts | Retain all upstream tests; merge configuration without shrinking suite; run baseline on upstream and final integration. |

## Initial integration risks and incomplete evidence

1. The dirty local `TimeAwareEngine.tsx`, `api/v1/time_aware.py`, `schemas/time_aware.py`, and `time_aware_engine.py` remove/replace legacy compression and pacing surface; semantic preservation is required, not a blind file copy.
2. The dirty `AuthContext`, `DataContext`, `App.tsx`, `Sidebar`, `Topbar`, and dashboards were developed from an older baseline and overlap extensive upstream updates. Upstream versions must remain the base.
3. The local raw recovered dataset and Day 100 database live in ignored scratchpad paths. They prove the local acceptance run but are not yet a reproducible production catalogue seed. Dataset rights/completeness remain explicitly limited in the curriculum docs.
4. The backend currently mixes SQLAlchemy application entities with a separate revisioned JSON workspace. Tenant authorization, persistence, migration ordering and coexistence with legacy models need tests against latest main.
5. No fork URL or user remote is configured. `gh` is missing, so creating a fork/PR may require authenticated GitHub access unavailable here.
6. No structured Panchapadi lesson-plan persistence was implemented in the local feature set; only Daily Curriculum execution exists.

This is the pre-change reconciliation record. Items marked as intended integration directions remain subject to post-merge tests and code review.
