# Browser acceptance checklist — OUTSTANDING (not yet run)

**Status: NOT EXECUTED.** No browser tool was available while the relational migration was built, so everything below has only been
verified through automated backend tests, frontend component/flow tests against a faithful in-memory fake of the API, and direct HTTP
calls to the backend. None of it has been seen in a real browser. Tick each line yourself.

## Setup (isolated demo database — never a protected one)

From `apps/lumeneios`:

```bash
# 1. backend, isolated DB (copy once; *.db is gitignored)
cp lumeneios.db lumeneios_teacherplan_demo.db
DATABASE_URL="sqlite+aiosqlite:///./lumeneios_teacherplan_demo.db" PYTHONPATH=. venv/Scripts/python.exe backend/scripts/seed_teacher_plan_demo.py
DATABASE_URL="sqlite+aiosqlite:///./lumeneios_teacherplan_demo.db" venv/Scripts/python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
# 2. frontend
npm run dev        # http://localhost:3000
```

Demo logins use the password `demo123`: `teacher@lumeneios.demo` (school-1, Class VII Mathematics + Class VIII Science, teacher 1),
`principal@lumeneios.demo`, `admin@lumeneios.demo`. School-1 also has a second teacher (user-teacher-2, same class and subject) for the isolation checks;
school-2 and school-3 have their own teachers, principals (`demo-plan-principal-2/3`) and different calendars.
If a server is already listening on port 8000 that you did not start, use another port and set the frontend proxy accordingly.

## Checklist

### Teacher (school-1)
1. [ ] Log in as the teacher. Open **Curriculum Catalogue → Class VII → Mathematics**. The full syllabus list is intact; **My teaching plan** shows capacity (available, 10% reserve, topic capacity, proposed total, remaining).
2. [ ] Change a topic's **coverage** (Not done → In progress → Done). Refresh the page: the status and the percentage persist. A different teacher (log in as teacher 2) still sees Not done.
3. [ ] Change a **Core/Non-Core requirement**; save. Refresh: it persists. Raise a number until the proposed total exceeds the capacity: the "Saving is blocked … deficit N" message appears, Save is disabled, and nothing is written (refresh to confirm).
4. [ ] Open **Time-Aware Engine → Requirements**: the same numbers are shown, the basis column reads "Demonstration default (hypothetical)" for untouched topics and "Set by teacher" for edited ones.
5. [ ] **Relationships** tab: add a prerequisite with a 20+ character explanation and evidence; a self-link, duplicate, later-class prerequisite and a cycle are each refused with a message. Remove it; the row disappears but **Central Logs** keeps both events.
6. [ ] **Schedule planner**: generate a draft (button waits for requirements to load). It appears as awaiting approval; it does not change anything approved.

### Principal (school-1)
7. [ ] **Planning Oversight**: one row per teacher plan (both teachers separately). Teacher 1 shows the draft; scheduled/taught/proposals/version show "—" (not zero) until a plan is approved. Approve the draft (a rejection needs a reason). Reload: version v1, status Approved.
8. [ ] **Academic Configuration**: edit the calendar (e.g. add a holiday, or reduce Mathematics periods per day). The **Effect on annual allocations** panel shows available periods, reserve and topic capacity before → after, and per-teacher deficits. Save with a reason: "Calendar version N saved". Open it in a second browser/tab as the admin: the history shows who saved it.

### Teacher again
9. [ ] The requirements area shows **Calendar changed (version N-1 → N)** with the deficit if the new capacity is smaller; saved requirements were not changed; further saves stay blocked until reduced.
10. [ ] **Record a Lost Day** (select 2 periods on one date, give a reason). The card shows **Lost days 1 / Lost periods 2**. The Day tracker log shows the same record; **Correct** withdraws a period with a reason and the proposal is regenerated. A recovery proposal appears (Pending).
11. [ ] Record execution in **Daily Curriculum** (layout and behaviour unchanged): "Completed" marks coverage Done through the same record you see in the Catalogue; "Homework" does not.

### Principal again
12. [ ] **Planning Oversight / Plan detail**: the Pending recovery proposal can be approved or rejected (rejection needs a reason). After approval the table shows **v2**; the approved recovery froze the lost period (the teacher cannot withdraw it).
13. [ ] **Curriculum Oversight**: one coverage row per teacher; expand a row for chapters (green/orange/grey boxes); the teacher's name opens that teacher's Catalogue read-only.
14. [ ] **Central Logs**: all of the above appear (requirement changes, relationships, lost periods, proposals, approvals/rejections, schedule versions, calendar change, coverage). Filters (category, class, subject, teacher, dates) work; rows expand to show before/after, reason, version and proposal.
15. [ ] **Contextual history**: the "History →" links in Time-Aware, the Catalogue panel, Planning Oversight (per row) and Curriculum Oversight open Central Logs pre-filtered and show the same events (same ids) as the unfiltered log.

### Isolation and persistence
16. [ ] Teacher 2 (same school, class and subject) never sees teacher 1's requirements, coverage, relationships, lost periods, plans or proposals.
17. [ ] Switch school in the header to school-3 (as admin): calendars, plans, teachers, logs and oversight tables all change; nothing from school-1 leaks.
18. [ ] Refresh every page above: all data persists. Stop and restart the backend: all data persists.
19. [ ] **Daily Curriculum** is visually and functionally as before.

### Edge checks
20. [ ] Anonymous request to any planning URL in a private window returns the login page / 401 (no demo-admin fallback).
21. [ ] A principal or admin cannot edit a teacher's requirements, coverage, relationships or lost periods (controls are disabled/read-only; the API answers 403).
