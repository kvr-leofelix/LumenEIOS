# Workspace document → relational teacher-plan API: migration map

**Status: all seven steps are implemented and verified by automated tests. Browser acceptance has NOT been run** (no browser tool was
available): see `BROWSER_ACCEPTANCE_CHECKLIST.md`. Final verification run: backend 223 passed; frontend 251 passed (27 files); `tsc --noEmit`
clean; production build succeeds; the four protected databases are byte-identical to their recorded SHA-256 prefixes.

Decisions taken (by the product owner): a teacher saves their own requirements directly (the earlier propose -> independent-review step
for classifications was dropped); unapproved demonstration defaults feed the engine but are flagged `demo_default` and never shown as
approved; legacy school-level plans are imported under the teacher who created them when that is unambiguous.

| Step | Status |
| --- | --- |
| 1 Coverage | **Done.** One store: `teacher_topic_coverage` (+ `source`, migration 005). Workspace rejects coverage changes. Import: `import_workspace_coverage` |
| 2 Requirements / classifications | **Done.** One store: `teacher_topic_configs` (`origin`: `demo_default`, `teacher`, `approved_import`). Catalogue panel, Time-Aware Requirements tab and the engine context all read it (`GET /teacher-plans/{id}/requirements`, shared `requirementsStore`). Saves go through `PUT .../requirements` (capacity-checked, all-or-nothing, audited as `period_requirement` / `topic_classification`). Workspace now rejects any change to `classifications`; old values stay readable, nothing deleted. Import: `import_workspace_requirements` (approved + counts only, single unambiguous owner only, over untouched demo defaults only, capacity-checked, idempotent) |
| 3 Relationships | **Done and verified (backend 167, frontend 228).** One store: `teacher_topic_relationships` (+ kind, explanation, evidence, shared_periods, lead, soft `status`, `origin`; migration 006). `relationship_service` enforces the former governance rules plus ownership and cycle rejection. Catalogue/Time-Aware panel and `ctx.relationships` read it through the shared store; the panel no longer writes the workspace. Workspace rejects relationship changes (history readable). Import `import_workspace_relationships`: approved only, single holder of both topics only, same validation, never replaces or revives a row, idempotent |
| 4 Lost periods | **Done and verified (backend 176, frontend 231).** One store: `teacher_lost_periods` (+ batch_id, soft withdrawal fields, `schedule_version` link; migration 007). `lost_period_service`: atomic multi-date batch, calendar-validated (instructional day, timetabled period), duplicate-proof, withdrawal needs a reason and is refused once an approved recovery uses the period (set in step 5), lost days = distinct active dates. Recorder, Day tracker log/correction, lost-days card and `usePlanning().workspace.plans[].losses` all read the same rows; the recovery engine runs on plans overlaid with them. Workspace rejects `plans[].losses` changes (history readable). Import `import_workspace_losses`: effective records only, recording teacher (or sole holder) as owner, nothing invented, incomplete/invalid/ambiguous reported, idempotent. Since step 5 the server validates a loss against the teacher's approved schedule itself (a period must be one of its classroom periods, so a later timetable change cannot hide a real period; a topic recorded as taught cannot lose one) and falls back to the school's timetable only when no plan is approved; the import alone may record history an approved recovery already absorbed |
| 5 Plans, versions, proposals, execution | **Done and verified (backend 183, frontend 238).** One store: `teacher_plans` + append-only `teacher_plan_versions`, `teacher_plan_proposals`, `teacher_plan_execution`, `teacher_plan_evidence` (migration 008). `plan_service`: only the owning teacher creates plans / records execution and evidence; only Admin/Principal approve or reject a draft or proposal; the server builds version 1 and every later version itself from the stored draft/proposal; stale proposals (base version moved) are refused; approving a recovery freezes the lost periods it absorbed (`schedule_version`); all steps audited in `plan_audit_events` (plan_draft, plan_approval, plan_rejection, recovery_proposal, recovery_approval, recovery_rejection, schedule_version, teaching_execution) with before/after, reason, version and proposal id; logs filterable by proposal id and version. Deterministic recovery engine unchanged (TypeScript); `usePlanning().commit` turns its results into server commands (`planCommands`) and the server revalidates (calendar membership, period range, no double allocation, no dropped topics, no reduced Core). Workspace rejects any change to `plans`. Planning Oversight now reports scheduled / taught / outstanding Core / pending proposals / approval status / version per teacher, null (shown as a dash) when no approved schedule exists. Import `import_workspace_plans` + `backend/scripts/import_workspace_to_teacher_plans.py` (rehearsed on a COPY of the takeover acceptance DB: 1 plan and 1 lost period imported, 2 classifications reported ambiguous, second run a no-op). Behaviour changes: reviewers no longer create drafts (teacher-owned); browser-only mode no longer holds plans |
| 6 Calendar | **Done and verified (backend 193, frontend 243).** One store: `school_plan_calendars` (append-only versions; reason, who, when). `calendar_service`: server-side port of the planner's validation, optimistic concurrency (`expected_version` -> 409), no-op/empty-reason refused, audit `calendar_change` with capacity before/after and the plans needing teacher review. `POST /plan-calendar/preview` (teachers see their own plans, Admin/Principal all): P/R/T before and after (hand-checked: 40 -> 38 periods with a holiday, R=ceil, 20 with one Maths period/day), per-teacher saved total vs new capacity, equal-weight defaults under the new calendar, approved-schedule impact; writes nothing. **Annual P ignores `horizonDays`; that value only limits the visible/scheduling horizon.** Impact rows also include `periods_gained_or_lost` (change in T), `core_requirements_fit`, `core_shortfall`, and per-topic `original_allocation`, `revised_allocation`, `allocation_change`, and `is_affected`. These are proposed equal-weight comparisons only: saved/customized requirements and approved schedules remain unchanged pending their existing decision flow. `GET /teacher-plans/{id}/calendar-impact` and a collapsible panel in the requirements view for the teacher. Academic Configuration saves via the API (reason, version, stale draft detection kept) and shows the preview; `usePlanning().workspace.config/configHistory` come from the versions. Workspace rejects `config`/`configHistory` changes. Import `import_workspace_calendar` (version 1 only if none exists). Saving a requirement that does not fit stays blocked; approved schedules keep their calendar snapshot until a recalculation proposal is approved |
| 7 Workspace cleanup | **Done and verified.** The workspace document now accepts only two writes: syllabus dataset import (admin) and the reviewer-set planning date (`PLANNING_DATE`). Every migrated field (`coverage`, `classifications`, `relationships`, `plans` with their versions/proposals/execution/evidence/losses, `config`, `configHistory`) is frozen for every role whatever action is declared; the 13 retired action names answer **410** and name their replacement endpoint. The shared schedule validator moved to `schedule_validation.py`, so no relational code imports the workspace service. The two screens that still rendered `workspace.audit` (Planning Oversight trail, admin Audit & Security) now read the plan log. Enforced by `backend/tests/test_single_store.py` and `src/test/singleStore.test.ts` (source scans fail if a screen starts reading or writing the stored document again) |

## Final single-store audit (every remaining workspace access, classified)

**1. Legitimate, unrelated workspace functionality**
- `lib/planning/store.ts`, `DataContext.planning`: the workspace store itself (loads/saves `datasets`, `asOf`; revision and 409 handling; browser-only fallback for those two).
- `lib/planning/usePlanning.ts`: reads `workspace.datasets` and `workspace.asOf`; the only consumer of the store.
- `lib/planning/pace.ts effectiveAsOf`: uses the planning date.
- `api/v1/planning.py`, `planning_workspace_service.py`: the endpoint for those two writes.

**2. Read-only historical compatibility**
- The `Workspace` type and `normalizeWorkspace` still carry the migrated fields so old documents load; nothing writes them. `usePlanning` shows the relational calendar/plans in their place, and only a school with no saved calendar version yet falls back to the document's historical configuration.
- `LegacyWorkspaceAction` (names found in historical audit entries); the legacy prototype key notice in `planningUi.tsx`.
- Workspace revisions are never modified or deleted.

**3. Import / migration**
- `services/workspace_import.py` (six importers) and `backend/scripts/import_workspace_to_teacher_plans.py`; `seed/teacher_plan_demo.py` reads the document only to avoid shadowing a school's real calendar.

**4. Obsolete access removed in this migration**
- Workspace coverage writes (Catalogue, execution), classification propose/review (SyllabusPanel), relationship propose/review, `plan.losses` writes (recorder, day tracker), `CONFIG_SAVE` (Academic Configuration), all plan/proposal/execution/evidence writes, `workspace.audit` rendering, dashboards reading `workspace.plans`, the workspace-side authorization rules for all of the above.
- No occurrence of class 4 remains (asserted by the two source-scan tests).

## Active dual-store paths remaining: none
Each responsibility has exactly one writer path (the relational API) and one reader path (the shared stores in `src/features/teacherPlan/*` and the services behind the API).

## Known limitations (not hidden)
- **Browser acceptance not run.** All UI checks are component/flow tests against an in-memory fake of the API plus direct HTTP calls to the real backend.
- **The deterministic scheduling and recovery engine still runs in the browser (TypeScript).** The server validates and authorises what it produces (calendar membership, period range, no double allocation, no dropped topic, no reduced Core, staleness, roles, versioning, audit) but does not recompute it, so it cannot prove a structurally valid proposal is the one the engine would have generated.
- **Governance:** the independent-reviewer step for classifications is gone by decision (a teacher's own saved requirement is authoritative; reviewers inspect only). Plan drafts and recovery proposals still need an Admin/Principal decision, with a reason on rejection.
- **Historical detail with no relational home** (criteria, rationale, evidence, proposer/reviewer events of old classifications) stays readable in the workspace revisions only.
- **Ambiguous ownership is never guessed.** In the rehearsal on a copy of the takeover acceptance database two school-level approved classifications could belong to either of two teachers and were reported, not imported.
- **Reviewers no longer create plan drafts** (a plan has exactly one owning teacher); browser-only (offline) mode no longer holds plans.
- **Syllabus identities** are the 10 source-verified research sections (6 chapters); the complete NCERT hierarchy is still not available, so equal-weight defaults give large per-topic allocations.
- Pure governance helpers in `lib/planning/governance.ts` (propose/review...) remain only because engine unit tests and types use them; no screen calls them.
- Daily Curriculum: `CurriculumPlanner180.tsx` was not modified by this migration. Its detail view (`PlanDetail.tsx`) kept its markup; only its data calls changed (execution goes to the plan API, coverage tag and execution-derived coverage use the relational record).

## 1. What the workspace document held before the migration (historical audit, kept for reference)

| Field | Written by (commit action, file) | Read by | Notes |
| --- | --- | --- | --- |
| `config` (+ `configHistory`) | `CONFIG_SAVE` AcademicConfig.tsx | calendar.ts, engine, Time-Aware, DayTracker | Calendar and subject periods per day |
| `datasets` | `SYLLABUS_IMPORT` (admin) | syllabus.ts, Catalogue | Syllabus imports; **stays** (shared identity, not teacher data) |
| `classifications[nodeId]` | `CLASSIFICATION_PROPOSE` / `_REVIEW` SyllabusPanel.tsx | engine (`approvedRequirement`), Catalogue | **Per school**, proposal + second-reviewer, criteria, rationale, evidence, history |
| `relationships[]` | `RELATIONSHIP_PROPOSE` / `_REVIEW` RelationshipsPanel.tsx | engine (prerequisite order, cross-curricular shared periods) | **Per school**, PREREQUISITE and CROSS_CURRICULAR, reviewed |
| `coverage[nodeId]` | `COVERAGE_UPDATE` CoverageSyllabus.tsx; also derived from execution (`coverageAfterExecution`, PlanDetail.tsx) | Catalogue, planningUi.tsx | **Per school**, source MANUAL or EXECUTION, history |
| `plans[]` | `PLAN_DRAFT`, `PLAN_REVIEW`, `EXECUTION_RECORD`, `EVIDENCE_RECORD`, `RECOVERY_PROPOSE`, `RECOVERY_REVIEW` | everything in Time-Aware, Oversight, Reports | **Per school, class, subject** (not per teacher). Holds draft, schedule versions, execution events, evidence, recovery proposals, losses |
| `plans[].losses[]` | `LOSS_RECORD` LostPeriodRecorder.tsx, DayTracker.tsx | pace.ts, progress.ts, losses.ts, PrincipalReports.tsx | Plan-scoped, corrections via `supersedes`, batch ids, reason free-text list |
| `asOf` | store | pace.ts | Reference date |
| `audit[]` | stamped by server | StoreBanner / PlanDetail | **Second audit trail**, separate from `plan_audit_events` |

Server rules in `planning_workspace_service.authorize_changes` enforce role-per-action, append-only history (versions, execution, evidence, audit) and no deletion.

## 2. Mapping to relational equivalents

| Workspace | Relational target | Gap |
| --- | --- | --- |
| `coverage[nodeId].status` | `teacher_topic_coverage.status` | Needs `source` (MANUAL/EXECUTION); history lives in `plan_audit_events` (category `coverage_status`). Node id `CH-x-Sn` ↔ topic key `XW-x-Sn` (deterministic) |
| `classifications[nodeId]` value + counts | `teacher_topic_configs` | **Per teacher now.** Missing: review status (demo_default / proposed / approved / rejected), proposer, reviewer, criteria, rationale, evidence |
| `relationships` PREREQUISITE | `teacher_topic_relationships` | Missing: review status, explanation, evidence |
| `relationships` CROSS_CURRICULAR | none | Needs `kind`, `shared_periods`, `lead_topic_key`, cross-subject reference |
| `plans[].losses[]` | `teacher_lost_periods` | Missing: `supersedes`/correction, `batch_id`, plan link. Reason list differs (workspace: 9 labels; relational: 5 codes). `periodsLost` count vs explicit period numbers |
| `config` | `school_plan_calendars` | Table exists and is versioned; Academic Config screen still writes the workspace |
| `plans[]` draft/versions/execution/evidence/proposals | **none** | No relational tables for schedule versions, execution events, evidence or recovery proposals |
| `audit[]` | `plan_audit_events` | Needs recovery proposal/approval/rejection, schedule version and before/after timetable payloads (columns exist: `schedule_version`, `related_proposal_id`, `previous_value`, `new_value`) |

Historical data with no direct relational equivalent: classification proposal/review history and rationale; cross-curricular links; plan drafts, schedule versions, execution events, evidence, proposals; coverage history entries; loss corrections and batches.

## 3. The recovery engine

`generateRecovery`, `applyLosses`, `allocate`, `paceReport`, `planProgress` (TypeScript, `src/lib/planning/*`) take a `Plan` plus `EngineContext` (classifications, relationships, config) and return a proposal. They are pure. They can be kept unchanged behind an adapter that builds `Plan`/`EngineContext` from relational data; the adapter must supply: effective requirements, relationships, calendar, losses, and the plan's version/execution history. The last item is the blocking gap (no relational home yet).

## 4. Compatibility that must remain

- `/api/v1/planning/workspace` GET/PUT (tests in `test_planning_workspace.py`, frontend `PlanningSaveConflicts` tests).
- `/api/v1/ncert` catalogue API and its mocks.
- Existing Daily Curriculum execution path (not to be redesigned) currently writes coverage and execution into the workspace.

## 5. Decisions needed before implementing (genuine conflicts)

1. **Governance vs teacher ownership.** The workspace requires every requirement to be *proposed* and then *approved by a different user*; only approved values reach scheduling. The teacher-plan API lets the owning teacher save directly, and Principals have no edit rights. Proposed resolution: a teacher's saved requirement becomes `proposed`; a Principal/Admin may only approve or reject it (never edit values); the recovery engine consumes approved values, falling back to demo defaults flagged `demo_default`.
2. **Do demo defaults feed scheduling?** Existing behaviour treats unapproved topics as "Classification pending" and never schedules or reduces them. Using demo defaults in the engine changes that behaviour.
3. **Plan scope.** Existing plans are per class and subject. Relational plans must be per teacher. Existing school-level plans have no owner; they need an explicit mapping to a teacher (or stay read-only history).
4. **Relational home for plans.** Schedule versions, execution events, evidence and proposals need new tables (or per-teacher append-only plan documents with the existing `authorize_changes` rules). This is the largest piece of work.
5. **Execution-derived coverage.** Daily Curriculum recording must write coverage with source EXECUTION through the new API without changing its UI.

## 6. Proposed order (each step leaves one source of truth per entity)

1. Coverage: server-side source field and history; CoverageSyllabus and execution path read and write only the relational records; remove `coverage` from the workspace write path.
2. Requirements and classifications: add review fields; SyllabusPanel and Catalogue read and write the relational plan; capacity validation on every save.
3. Relationships: add kind and review fields; RelationshipsPanel migrated.
4. Lost periods: add correction and batch fields; LostPeriodRecorder and DayTracker migrated.
5. Plans, versions, proposals, execution: new tables with the existing append-only and role rules; recovery engine runs on an adapter.
6. Calendar: Academic Config writes `school_plan_calendars`; teacher-facing recalculation preview.
7. One-time idempotent import of existing workspace documents, then remove migrated fields from the workspace write path (server rejects them).

No step is complete until the old field is no longer written or read for that entity.
