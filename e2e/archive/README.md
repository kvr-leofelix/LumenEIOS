# Archived acceptance scripts

These scripts recorded one-off acceptance runs during earlier development of curriculum planning, the
Time-Aware Engine and Day-100 recovery (see `docs/FINAL_ACCEPTANCE_REPORT.md`). They targeted the data and
APIs of that time:

* the earlier demonstration roster (`teacher@lumeneios.demo`, `teacher2a@…`, password `demo123`) and the
  `demo-plan-teacher-*` planning seed, which the current demonstration database no longer contains;
* the single planning-workspace document (for example `CONFIG_SAVE`), whose actions were migrated to
  `/api/v1/plan-calendar`, `/api/v1/teacher-plans/*` and `/api/v1/plans/*` and now deliberately answer 410 Gone.

They are kept for reference and history, not run. The maintained browser tests are the Playwright specs in
`tests/e2e/` (`npm run e2e`): sign-in and dashboards for every role, Differentiated Homework end to end, and the
Time-Aware Engine (schedule, approval, lost periods and Core-protecting recovery).
