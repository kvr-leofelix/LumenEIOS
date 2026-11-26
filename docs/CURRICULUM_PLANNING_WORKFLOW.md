> **Architecture update (migration steps 1-7) — read this first.**
> The "one workspace document per school" described below is **retired for everything except syllabus datasets and the reviewer-set
> planning date**. Calendar, requirements/classifications, relationships, coverage, lost periods, plans, schedule versions, proposals,
> execution, evidence and the planning audit trail now live in relational, **teacher-scoped** tables and are exposed by
> `/api/v1/plan-calendar`, `/api/v1/teacher-plans/*`, `/api/v1/plans/*` and `/api/v1/plan-logs`. The workspace document is frozen for those
> fields (history stays readable; the old action names answer 410). See `TEACHER_PLAN_MIGRATION_MAP.md` for the exact state, and
> `BROWSER_ACCEPTANCE_CHECKLIST.md` for what still has to be checked in a real browser.
> **Governance change, recorded as decided:** a teacher saves their own requirements directly and a Principal/Admin cannot edit them
> (the earlier propose -> independent-review step for classifications was dropped by the product owner's decision of this migration).
> Plan drafts and recovery proposals are still approved or rejected only by an Admin/Principal, with a reason on rejection. Core/Non-Core
> values that were never saved by a teacher are hypothetical demonstration defaults (`origin = demo_default`), never presented as approved.
> The sections below describe the *rules* (which still hold) in their original workspace terms.

# Curriculum planning workflow — Classes VI–VIII Mathematics & Science

Status as of 10 November 2026. Flow: Academic Configuration → syllabus & pedagogical governance → Time-Aware Engine → approval → Daily Curriculum execution → adaptive recovery → approval.

## Architecture and source of truth

| Layer | Location |
| --- | --- |
| Calendar model and validation | `src/lib/planning/calendar.ts` |
| Syllabus data layer and imports | `src/lib/planning/syllabus.ts`, `src/lib/planningSyllabus.ts` (published API loader) |
| Core/Non-Core classification and relationships | `src/lib/planning/governance.ts` |
| Scheduling engine | `src/lib/planning/engine.ts` |
| Plans, execution, recovery, approvals | `src/lib/planning/execution.ts` |
| Persistence | `src/lib/planning/store.ts`, exposed as `useData().planning` |
| Backend store | `backend/app/api/v1/planning.py`, `backend/app/services/planning_workspace_service.py`, `backend/app/models/planning_workspace.py`, migration `backend/migrations/003_planning_workspace.py` |

**One workspace document per school** holds configuration (plus its save history), imported datasets, classifications, relationships, plans and the audit trail.

- **Server mode** (backend reachable): `GET/PUT /api/v1/planning/workspace`.
  - Each save is a new append-only row in `planning_workspace_revisions`, with the unique key (school, revision).
  - Stale writes get `409`.
  - The server compares the old and new documents and rejects role violations, edits to append-only history (original schedule, versions, execution, evidence, audit) and removal of records.
  - The server stamps the authenticated user on new audit entries.
  - Before each write, the client verifies that the backend session (`/auth/me`) matches the signed-in user. This blocks the existing DEMO_MODE fallback, where a request without a token is treated as admin.
- **Browser-only mode** (backend unreachable): the same document is kept in localStorage under `lumeneios_planning_workspace_v2`, with a visible banner. The two stores are never merged.
- Codex's prototype key `lumeneios_academicWorkflow` is read once to migrate the configuration. It is never written or deleted. The prototype source files are archived in `docs/archive/codex-workflow-prototype/`.

## Data sources and provenance

| Data | Source | Status |
| --- | --- | --- |
| English textbook editions (8 book parts) | Codex Phase 0 research snapshot (`researchSnapshot.json`, built from `NCERT_VI_VIII_*` CSVs) | Source-checked bibliographic metadata |
| Chapters / sections (6 chapters, 10 sections, all six class–subject combinations) | Same snapshot, copied field-for-field, with PDF and printed-page locators | `SOURCE_VERIFIED_FOR_HEADING_AND_SECTION_MEMBERSHIP` |
| Outcome references (6) | Same snapshot. Locator plus research label only; official wording is not stored | Inferred partial overlap, AI-suggested, `AWAITING_REVIEW`. Shown as inferred everywhere |
| Published catalogue | Existing `/api/v1/ncert` API (Admin: "Load published catalogue") | Used only if a published release exists. Never replaced by sample data |
| School imports | Admin JSON import | Labelled "School import — unverified". Per-record locator required. Core/Non-Core values rejected |
| Core/Non-Core | None pre-populated | Every unit is **Classification pending** until proposed and approved by a second reviewer |
| Cross-curricular and prerequisite links | None pre-populated | The data documents no overlap, so none is invented |
| Period estimates | Teacher input | Planning estimates, not official requirements |

**Blocker:** a complete syllabus is not available.
- No repository dataset contains full chapter, topic, activity, example or exercise lists.
- `NCERT_SOURCE_POLICY.md` and the Phase 0 closure report state that textbook-content extraction is not authorised while permission is pending.

The data model supports every requested record kind (chapter, topic, subtopic, activity, investigation, example, exercise, outcome reference, provenance), so permitted data can be imported or published through the catalogue API without code changes.

## Pedagogical rules enforced

- Only APPROVED classifications affect scheduling. Pending units are protected and never reduced.
- Classifications and relationships need a different user to review them than the one who proposed them.
- "Insufficient time" is rejected as a reason for a Non-Core classification.
- Each topic is scheduled with exactly its approved Core and Non-Core period counts (no ratio). When the horizon is short, only approved Non-Core periods (from the end of the sequence) move to tracked independent learning; Core is never reduced.
- Any remaining shortfall leaves units unscheduled and reports it as a conflict. Nothing is dropped.
- Approved cross-curricular links teach the shared periods once, in the lead unit. The other unit's requirement is reduced. Outcomes are de-duplicated in the class-level summary, and both units stay visible.
- Homework assigned and homework submitted are both distinct from teaching. "Assessed" requires a taught unit plus an evidence record.
- Plans start as DRAFT and are approved by an Admin or Principal. Approving a new plan marks the previous one SUPERSEDED, keeping its history.
- Recovery and recalculation proposals never change the approved schedule until approved. Rejected and superseded proposals are kept.

## Launch locally

From `apps/lumeneios`:

```bash
# 1. Backend on an ISOLATED copy (startup runs create_all + seed on whatever DB it is given)
cp lumeneios.db lumeneios_planning_dev.db          # once; *.db is gitignored
DATABASE_URL="sqlite+aiosqlite:///./lumeneios_planning_dev.db" venv/Scripts/python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
# 2. Frontend
npm run dev                                         # http://localhost:3000
```

PowerShell form of step 1: `$env:DATABASE_URL="sqlite+aiosqlite:///./lumeneios_planning_dev.db"; venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`.

Without the backend, the app runs in browser-only mode, and a banner says so.

## Demo sequence

1. **Principal → Academic Config.** Set holidays, periods per day and the horizon. Save.
2. **Teacher → Time-Aware Engine → Syllabus & classification.** Propose each topic's Core and Non-Core periods (for example 3 + 1 and 2 + 3).
3. **Principal → same tab.** Approve the requirements. The proposer cannot self-approve.
4. **Teacher → Schedule planner.** Review the exact counts and generate the draft. **Principal → Curriculum Oversight:** approve it.
5. **Teacher → Record a Lost Day** (bottom of the Time-Aware Engine). Tick periods (for example #1, #2), choose a reason, add a note and submit. The Day tracker shows them as lost and awaiting approval, with the proposed effect labelled "not yet approved".
6. **Principal → Curriculum Oversight.** Review every changed period and approve, or reject with a reason.
7. **Teacher → Daily Curriculum.** See the progress bars, the schedule-change notice and the By-period view. Record execution, then reload: progress persists.

## Verification (10 Nov 2026, takeover pass)

- Frontend:
  - `tsc --noEmit` is clean.
  - `vitest` passes 161/161. This includes `recovery.test.ts` and the rewritten `PlanningDayTracker.test.tsx` journey.
  - `npm run build` passes, with the existing large-bundle warning.
- Backend: `pytest backend/tests` passes 100/100. The two legacy compression tests now assert retirement (410 / refusal).
- Browser acceptance:
  - Run in headless Chrome via `playwright-core`, installed outside the repo.
  - Stack: Vite :3107 → FastAPI :8107, on `lumeneios_takeover_acceptance.db`, a fresh copy of `lumeneios.db`.
  - Result: 28/28 checks pass with 0 console errors.
  - The run covered:
    - config save;
    - requirement proposal and approval by different users;
    - exact 3+1 / 2+3 scheduling and draft approval;
    - Record a Lost Day for #1 and #2, including the required reason and double-click safety;
    - pending vs approved progress;
    - the changed-period table and Principal approval;
    - the Daily Curriculum period view and execution;
    - reload persistence;
    - all three dashboards;
    - no horizontal overflow at 1024, 768 and 390 px.
- The original `lumeneios.db` SHA-256 (`5a5fee7b…12e8`) was verified unchanged.

## Save / revision handling (fixed 10 Nov 2026)

**Root cause of the repeated "Another user saved changes first" message:** when the page loaded with an expired or invalid token, `GET /planning/workspace` returned 401. The store stayed in server mode with **revision 0 and an empty workspace**, and saving was still allowed. The first save re-authenticated and sent `expected_revision: 0`, so the backend correctly answered 409. Separate Admin and Principal windows also never refreshed, so alternating saves always conflicted. The backend revisioning itself was correct: 40 rapid sequential saves produced 0 false conflicts.

**Fix (`src/lib/planning/store.ts`, `AcademicConfig.tsx`):**
- A 401/403 on load re-establishes the signed-in user's session once and retries.
- If loading still fails, the store enters `error` mode. Saving is blocked, the user's input stays on screen, and a **Retry** button is shown.
- Server-mode sessions quietly re-check the workspace on focus, when the tab becomes visible, and every 30 s. State only updates when the revision changed, and never during a save.
- A 409 reloads the latest version and reports who saved which revision. The user's form input is kept, and nothing is re-applied automatically.
- Configuration saves carry an **edit-base guard**: a draft started from an older configuration can never replace a newer one, even when the revision is current. A conflict panel shows the differences and offers *Keep my edits* (then save deliberately) or *Discard my edits*.

## Lost periods, Core-priority recovery and progress (revised 10 Nov 2026, takeover pass)

**History:**
- The committed Time-Aware Engine recorded whole lost *days* (`DataContext.lostTeachingDays`) feeding a hardcoded 180-day pacing calculation and a 60/40 compression.
- Later passes restored a per-date Day tracker, but it still showed a "≈70/30" diagnostic.
- The legacy `lostTeachingDays` state and seed rows are left untouched and are not used by the planning workflow.
- The legacy fixed-ratio compression endpoints now return **410 Gone**: `POST /classes/{id}/time-aware/compression-preview` and `POST /curriculum-proposals/{id}/approve`. Historical proposal rows are kept unchanged.

There is **no Core/Non-Core ratio anywhere**. Each topic's approved requirement (required Core periods + required Non-Core periods, `governance.ts`) is scheduled exactly. Topics without an approved requirement get no periods and block plan approval (`REQUIREMENT_MISSING`).

### Recording lost periods — "Record a Lost Day" (bottom of the Time-Aware Engine)

The label is kept as requested. The control records **individual scheduled periods**, never a whole-day cancellation (`LostPeriodRecorder.tsx`).

- Periods carry plan-wide numbers (#1, #2, …) over every subject period of the plan's original approved calendar, so a number is stable across schedule versions (`periodNumbers`).
- The dialog lists each period with its number, date, day period, class, subject, topic, Core/Non-Core type and status. It has filtering and search.
- One or many periods, across dates, can be ticked and submitted together. The reason is mandatory; the note is optional.
- Periods already recorded lost, and periods of topics recorded as taught, cannot be selected. The library rejects duplicates again on save.
- A ref guard ignores repeated clicks while a save is in flight.
- One submission writes one record per date, sharing a `batchId`, and generates **one** recovery proposal (`recordLossBatchAndPropose`).
- Teachers and Admins can record. Principals see the control disabled, with an explanation.
- Corrections are made in **Day tracker → Lost-period log**. Untick the periods that were taught after all and give a reason. The correction is a new record that supersedes the old one. A loss already covered by an approved recovery cannot be corrected.

### Recovery (`losses.ts › applyLosses`, via `generateRecovery`)

1. Each lost slot is removed from the proposed schedule. The original v1 keeps it.
2. A lost **Non-Core** period moves to tracked independent learning. The requirement is unchanged and it never counts as taught.
3. Each lost **Core** period is placed, if possible, within the **next 3 teaching days**, in this order of preference:
   - the same topic's own later Non-Core session;
   - an unused subject period;
   - a later topic's approved Non-Core session. The displaced Non-Core session becomes independent learning.
4. These sessions are never taken:
   - a slot of a taught topic;
   - another Core session;
   - an earlier topic's session;
   - any slot before the lost topic's approved prerequisites finish;
   - a session of an approved dependent that has already started its Core teaching.
5. Core that cannot be placed stays on the topic as `coreUnscheduled`. The proposal states why, for example no eligible capacity in the window, or a prerequisite.
6. Unaffected sessions are held fixed. Topics are not pushed forward wholesale.
7. The proposal shows:
   - summary tiles;
   - every changed period (Lost / Core recovered / Non-Core → independent learning, with reasons);
   - topic-level changes;
   - original vs current vs proposed schedules;
   - remaining capacity conflicts.
8. Approve or reject: Principal/Admin only. Rejection needs a reason.
   - On approval, a new version records the approver and timestamp, and v1 and earlier versions are kept.
   - A rejected proposal stays in history, and the approved schedule is unchanged.
9. The calendar, working days and horizon are never changed by losses.

### Progress (`progress.ts`) — single source for every screen

`planProgress` and `workspaceProgress` feed the Day tracker, Daily Curriculum, Curriculum Oversight and the Admin/Principal/Teacher dashboards. All of them use `ProgressBar.tsx`.

Teaching days and classroom periods are separate bars:

| Measure | Definition |
| --- | --- |
| Teaching days completed | Days on which every remaining (non-lost) period is taught. Taught periods are attributed to each topic's earliest slots. |
| Days whose periods were all lost | Counted separately, never as completed. |
| Classroom periods | Approved requirement minus independent learning; taught periods are split into Core and Non-Core. |
| Remaining requirement | Core and Non-Core shown separately. |
| Independent learning | Shown separately; not classroom teaching. |
| Lost periods | Core and Non-Core counts, split into awaiting approval vs applied. |
| Recovered Core | Approved recovery only. |
| Core awaiting recovery | Lost Core not yet recovered. |
| Unresolved shortfall | Required periods with no slot in the approved schedule. |

A pending proposal's effect is shown in a separate "Proposed, not yet approved" line and is never added to the approved figures.

The Daily Curriculum also has a **By period** view (`periodLedger`). For each period it shows the original v1 topic and type, the current approved topic, and a status: Taught, Scheduled, Lost (approved or awaiting), Core recovery, or Moved to independent learning. Lost periods include their reason and notes.

### Workspace-document fields (JSON; no database migration; backward compatible)

- `plan.losses[]` (append-only; `periods`, `batchId`, `supersedes`).
- `version.lostSlots`.
- `lesson.lossHomeworkPeriods` and `lesson.lossNotes`.
- `proposal.lostSlots`.
- `proposal.lossDays[]`, including `recovered`, `unresolved` and period-level `moves`.

The backend enforces that `losses`, `execution`, `evidence` and `versions` are append-only. It also enforces the role of every action.
