> **Superseded (10 Nov 2026):** the workflow described below was replaced by the full planning model documented in
> [CURRICULUM_PLANNING_WORKFLOW.md](CURRICULUM_PLANNING_WORKFLOW.md) (backend-authoritative store, calendar entries,
> classification governance, draft approval, execution log, recovery proposals). This file is kept as Codex's audit record.

# Presentation readiness — 10 November 2026

## Audit findings

- AcademicConfig used component state and a success toast without saving anything.
- Principal had no configuration route or navigation entry. The application shell authenticated routes but did not enforce role authorization for individual pages.
- TimeAwareEngine fixed class-8a/sub-math, 180 days, day 104, and a 60/40 Core/Supplementary split. Existing compression approval changed seeded lesson statuses and called a separate legacy backend preview/approval path.
- CurriculumPlanner180 was read-only, displayed only 30 seeded rows, and had no execution entry mechanism. No independent actual-execution record existed in that screen.
- DataContext already used browser localStorage. Backend hydration was limited to source documents and question bank; curriculum came from seedData/localStorage.
- Legacy `/curriculum/classes/{class_id}` reads existing curriculum rows; `/curriculum/days/{id}/complete` mutates the lesson status. These endpoints do not provide separate execution records, calendar configuration, or versioned recovery schedules. They are not called by this new workflow.
- Existing `/ncert` client provides published releases, subjects, and source-backed nodes. Node responses contain only immediate children. The existing research snapshot provides explicitly mock/sample topic metadata for all six class/subject combinations.

## Implemented workflow and data provenance

| Feature | Data and persistence |
| --- | --- |
| Academic Configuration | Validated user input, persisted through DataContext's new academic workflow state in `lumeneios_academicWorkflow` localStorage. Shared across Admin/Principal within this browser profile and origin. Defaults are demo defaults. |
| API syllabus | Existing authenticated NCERT HTTP client; reads published release metadata and recursively loads node descendants. Explicit fetch action. Unavailable/hidden data raises an error; no automatic sample fallback. No live API dataset is claimed as verified by this implementation. |
| Sample syllabus | Explicit **Use sample research dataset** action. Existing research snapshot, English-language topic metadata for Mathematics/Science VI–VIII. Partial research coverage, not a complete or officially applicable syllabus. Labels remain visible on every saved plan. |
| Instructional estimates | User supplies estimated periods per topic; duration derives from the saved period length. These are not official curriculum requirements. Each topic reserves whole periods, which can span multiple teaching dates. Table shows start date, start period and total periods/minutes. |
| Teaching schedule | Local deterministic allocation against actual days, horizon, weekdays and excluded dates. All loaded topics retained; topics beyond capacity remain visible as unscheduled. Calendar/configuration snapshot saved per plan. Generating a new plan retains older plans. |
| Teacher execution | Separate local records with status, timestamp and note. Homework does not mark completion. Original and approved lesson rows remain intact when recording execution. |
| Recovery | Local conservative proposal: requeue incomplete instruction after the last recorded lesson's occupied teaching day, shifting future unfinished topics. Completed topics remain fixed. Unscheduled instruction and every affected topic/date are shown. Admin/Principal UI approval required; old approved rows retained in versions for comparison. |
| Dashboard/oversight | Teacher curriculum summary and Principal Curriculum Oversight read saved workflow plans. Other legacy dashboard analytics, student assessments and rosters still use existing seed/demo data and are outside this path. |

This is browser persistence, not database-backed multi-user synchronization. Role restrictions use the existing demo authentication/role switcher and UI checks; this workflow does not add server authorization endpoints. Do the presentation in one browser profile at the same origin (`localhost:3000`). Storage does not transfer between `localhost` and `127.0.0.1`, browsers, profiles or machines. No migrations, database resets, seed scripts or database writes were run.

## Demo sequence

1. Principal → Academic Config: adjust calendar, actual instructional days, horizon, subject periods/day and minutes/period; exclude holidays/non-teaching dates; save.
2. Time-Aware Engine: select VI/VII/VIII and Mathematics/Science. Fetch API syllabus if a published API release is available, or explicitly choose sample research data. Set estimated periods/topic; inspect available/required time and shortfall; generate and approve a new schedule.
3. Teacher → Daily Curriculum: choose the same saved plan. Record completion, homework, or deferral. Inspect original versus approved dates and execution timestamps.
4. Principal → Curriculum Oversight: inspect recovery's affected future topics/dates and unscheduled instruction. Approve or reject. Compare preserved schedules.
5. Reload: configuration, plans, execution and schedule versions remain saved.

## Verification

Frontend typecheck and production build pass. Tests cover existing routes/catalogue screens, calendar exclusions, time shortfall preservation, all six sample selections, homework semantics, recovery approval/version preservation, shallow API traversal, and a full role-based journey across remounts. Localhost:3000 was initially unreachable; Vite was restarted and HTTP 200 verified. Verification uses React Testing Library/jsdom and HTTP module checks, not a visual browser automation run. Build reports the existing large-bundle warning; tests report existing Router future-flag and chart-size warnings.
