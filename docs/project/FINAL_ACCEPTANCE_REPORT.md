# LumenEIOS — Syllabus restoration report

Date: 2026-11-12  
Branch: `integration/curriculum-catalogue`

## Result

**The complete available Mathematics and Science structure is restored and verified in the running application.** The exact previously imported dataset, `import-mwcgxn30`, is persisted in the isolated demonstration workspace. After restarting FastAPI with the explicit isolated database URL, a live Microsoft Edge walkthrough verified all six Class VI–VIII Mathematics/Science selections, every chapter and every available topic/subtopic, and shared topic IDs between the Catalogue and Time-Aware.

The recovered source is a structural inventory, not a claim that these are complete official textbooks. Three chapters in it have no child topics; they remain visible. The import contains no approved period counts, so the engine correctly leaves requirements and scheduling unresolved.

## Why the syllabus disappeared

The full data was not deleted from the prior acceptance artifacts. A new isolated database had been created by cloning the baseline `lumeneios.db`, then the Day 100 initializer wrote a workspace with `datasets: []` in `e2e/demo_browser.mjs`. The full syllabus existed only in the previous isolated planning workspace, not in the baseline database. With the new workspace empty, `defaultDatasetFor()` selected the small bundled `researchSnapshot.json` dataset because it was the only available source. That is why Mathematics showed a small number of chapters and Science appeared incomplete.

The prior Time-Aware simplification also removed the in-page import controls without arranging for the already-reviewed structure to be initialized. The Catalogue did not truncate the full data; the new workspace never loaded it.

## Recovery and regression prevention

I recovered the exact `ncert_structure_import.json` and the earlier isolated `lumeneios_e2e.db` from:

`C:\Users\Tanav\AppData\Local\Temp\claude\6bd9b17a29b4239b\b7dfc046-5f60-42a6-ac91-e23d350b7124\scratchpad\acceptance`

The database’s first `SYLLABUS_IMPORT` revision contains dataset `import-mwcgxn30`: 8 textbooks and 531 nodes. I restored that exact dataset into `scratchpad/acceptance/lumeneios_e2e.db` through the existing Admin workspace import action. Dataset ID, textbook IDs, node IDs, parent links, ordering, and provenance locators were preserved. The raw import file and exact persisted dataset export are retained in the ignored local `scratchpad/acceptance` folder.

The shared syllabus code remains unchanged: both Catalogue and Time-Aware use `defaultDatasetFor()` and `syllabusFor()` from `src/lib/planning/syllabus.ts`. With the recovered dataset present, the full import wins over the bundled snapshot by its eligible-topic count. The demo initializer now requires this recovered dataset, imports it only when absent, verifies exact contents if already present, and refuses to continue with a sample-only or conflicting workspace. No second syllabus source or UI was created.

## Verified data counts

Counts are computed from the restored dataset and were checked against the actual rendered Catalogue. The structural import has `CHAPTER`, `TOPIC`, and `SUBTOPIC` nodes; section headings are represented as nested numbered topic nodes rather than a distinct `SECTION` kind.

| Class / subject | Dataset | Textbooks | Chapters | Sections as distinct nodes | Conceptual topics | Subtopics | Eligible schedulable topics | Missing child records |
|---|---|---|---:|---:|---:|---:|---:|---|
| VI Mathematics | `import-mwcgxn30` | Ganita Prakash | 10 | 0* | 65 | 0 | 65 | None identified in this import |
| VI Science | `import-mwcgxn30` | Curiosity | 12 | 0* | 53 | 18 | 65 | Chapters 1 and 9 have no child topics |
| VII Mathematics | `import-mwcgxn30` | Ganita Prakash, Parts I and II | 15 | 0* | 65 | 0 | 65 | None identified in this import |
| VII Science | `import-mwcgxn30` | Curiosity | 12 | 0* | 50 | 45 | 78 | None identified in this import |
| VIII Mathematics | `import-mwcgxn30` | Ganita Prakash, Parts I and II | 14 | 0* | 58 | 0 | 58 | None identified in this import |
| VIII Science | `import-mwcgxn30` | Curiosity | 13 | 0* | 62 | 39 | 84 | Chapter 1 has no child topics |

Across the import: 8 textbook/part records, 76 chapters, 353 conceptual-topic nodes, 102 subtopic nodes, and 415 eligible schedulable topics. The VI Science, VII Science, and VIII Science hierarchies include parent topic headings with child subtopics; eligible counts avoid counting a parent and its children twice. Empty chapters are retained in the Catalogue.

\* No distinct `SECTION` node kind is present in this recovered dataset. The original structural headings and numbering remain in the topic/subtopic parent hierarchy.

## Browser and persistence verification

Live walkthrough: [restoration screenshots and logs](../apps/lumeneios/e2e-shots/20261112-syllabus-restoration/)

Microsoft Edge showed all chapters and expanded structural entries for all six class/subject combinations. The walkthrough used the actual Catalogue route and subject/class selectors, checked each rendered chapter and topic ID against the recovered source, and captured a screenshot for each combination. It then opened Time-Aware Class VI Science and verified that its 65 schedulable topic IDs match the Catalogue’s IDs. Edge remains open on the expanded Class VI Science Catalogue.

The backend was restarted with:

`DATABASE_URL=sqlite+aiosqlite:///C:/Users/Tanav/Downloads/DP/CODE/arena/scratchpad/acceptance/lumeneios_e2e.db`

After restart, the API returned workspace revision 8 with dataset `import-mwcgxn30`, all 8 textbooks and all 531 nodes. Re-running the restore operation reported “Already restored” and kept revision 8, confirming it does not add duplicates. The SQLite `integrity_check` returned `ok`; `foreign_key_check` returned no rows.

Screenshots include `06-mathematics-expanded.png`, `06-science-expanded.png`, the four VII/VIII subject screenshots, `time-aware-class-vi-science.png`, and `final-class-vi-science-expanded.png`.

## Automated verification

- Frontend Vitest: **200 passed across 20 files**.
- Backend pytest: **117 passed**.
- TypeScript typecheck: **passed** as part of `npm run build`.
- Production build: **passed**. Existing Vite warnings remain for a circular vendor chunk dependency and an application chunk larger than 500 kB.
- Regression coverage includes dataset selection over the bundled snapshot, refusing repeat imports with existing stable IDs, and the live source-to-rendered counts/identity checks.
- Lint is not configured in `package.json`.

Backend health is `http://localhost:8000/health`; the Catalogue is `http://localhost:3000/curriculum/catalogue`. Both services remain running.

## Remaining data limitations

- The recovered review package is an English structural inventory and its own report marks it incomplete. It contains no textbook prose, official outcome wording, or approved Core/Non-Core period requirements. No chapter, section, topic, or period count was fabricated.
- VI Science Chapters 1 and 9 and VIII Science Chapter 1 have no topic children in the recovered import. These are visibly empty in the application rather than hidden.
- The import contains the eight listed book/part records for VI–VIII Mathematics and Science. It does not establish completeness or applicability of other languages or textbook editions.
- With no approved period requirements in this isolated workspace, a realistic timetable and live lost-period recovery approval/rejection cannot be verified from real plan data in this restoration run.

## Database protection

The four original databases were hashed before and after restoration; all hashes are unchanged:

| Original database | SHA-256 |
|---|---|
| `apps/lumeneios/lumeneios.db` | `5A5FEE7B3C09743DFA7A1A4DC60358F9E668A898A043AA463D8C5D47B1CC12E8` |
| `apps/lumeneios/lumeneios_acceptance.db` | `5AF49B5116617D08A109A6BA77C95A88D0928C7211F71FF5A05C83AD0A8A65B7` |
| `apps/lumeneios/lumeneios_planning_dev.db` | `D306E9C12F1876E3F9089D62FA2DE99102DC2E76417248C906AA026A6CDC6175` |
| `apps/lumeneios/lumeneios_takeover_acceptance.db` | `9056BECBFD7B1DE4564822379A808563DCA2E13A572C62BD045EACA121A09F3E` |

## Resume checkpoint — Day 100 and classification audit

This section supersedes the earlier statements above that no approved requirements or recovery history were available. Those statements describe the initial restored-syllabus workspace, `scratchpad/acceptance/lumeneios_e2e.db` (revision 8). The active Day 100 demonstration is the separate isolated `scratchpad/acceptance/lumeneios_day100.db` (revision 45), recovered from the prior isolated acceptance history. Neither is an original application database.

### Preserved classification state

Audit artifacts: `scratchpad/acceptance/classification-audit.txt`, `prior_demo_summary.json`, and `day100-snapshot.txt`. The prior isolated acceptance database was still present at `C:\Users\Tanav\AppData\Local\Temp\claude\6bd9b17a29b4239b\b7dfc046-5f60-42a6-ac91-e23d350b7124\scratchpad\acceptance\lumeneios_e2e.db`. Its 65 Class VI Mathematics decisions and their teacher proposal / principal approval histories were preserved byte-for-record when copied into the isolated Day 100 workspace. No missing records were classified by inference.

| Class | Subject | Eligible topics | Core | Non-Core | Unclassified | Approved classification | Pending |
|---|---|---:|---:|---:|---:|---:|---:|
| VI | Mathematics | 65 | 0* | 0* | 0 | 65 | 0 |
| VI | Science | 65 | 0 | 0 | 65 | 0 | 0 |
| VII | Mathematics | 65 | 0 | 0 | 65 | 0 | 0 |
| VII | Science | 78 | 0 | 0 | 78 | 0 | 0 |
| VIII | Mathematics | 58 | 0 | 0 | 58 | 0 | 0 |
| VIII | Science | 84 | 0 | 0 | 84 | 0 | 0 |
| **Total** |  | **415** | **0*** | **0*** | **350** | **65** | **0** |

*All 65 approved VI Mathematics classifications are `MIXED`; each has 2 approved Core and 1 approved Non-Core period, totaling **130 Core + 65 Non-Core approved periods**. The classification counters above count pure Core and pure Non-Core labels, so both are zero for this mixed set. All 65 have approved period requirements; the other 350 topics have no classification or period requirement. There are zero pending decisions. Older decisions in unrelated small research snapshots were excluded.

### Day 100 reconciliation

- The active isolated calendar is `2026-08-20`, academic Day **100 of 180**, with **80** instructional days remaining. The approved Class VI Mathematics plan uses the recovered `import-mwcgxn30` topic IDs and retains its original calendar/period settings; only the isolated demo horizon and as-of date were reconciled.
- Loss records are individual periods, with dates, affected topics and reasons: Apr 1 periods 1–2 (Election Duties / polling-booth setup) and Apr 3 period 1 (teacher training). The dates had other scheduled periods, so they are partial-day disruptions; there are zero whole teaching days lost.
- History retains the rejected first recovery and approved recovery version 2. The final approved active version 3 is preserved after the Day 100 calendar recalculation. The recovery reallocated Core classroom slots and shifted 3 eligible Non-Core periods to independently tracked homework; approval is in the audit history. Superseded proposals remain visible.
- Progress is derived from the plan, losses and execution ledger: Core 130 required / 130 scheduled / 2 taught / **128 remaining**; Non-Core 65 required / 62 classroom scheduled / 1 taught / **61 remaining** / 3 independent-learning periods. Homework contributes zero classroom periods. One topic has genuine classroom execution and is Done; VI Mathematics coverage is Done 1, In progress 0, Not done 64. Manual coverage records remain identified as manual in the Catalogue and are not presented as classroom execution.
- The final live browser run after backend restart showed the active approved v3 schedule and the outstanding Core deficit. Schedule allocation is not represented as teaching progress. The unclassified 350 topics are outside this approved Class VI Mathematics plan and have no invented requirements.

### Verification at resume

- Frontend Vitest: **203 passed across 21 files**.
- Backend pytest: **117 passed**.
- TypeScript typecheck and production build: **passed** (`npm.cmd run build`). Existing Vite warnings: vendor chunk cycle and one chunk over 500 kB. No lint script is configured.
- Real Microsoft Edge acceptance: **passed** after backend restart. See [Day 100 screenshots and logs](../apps/lumeneios/e2e-shots/20261112-day100-recovery/); especially `10_day100_approved_schedule_and_audit.png`, `11_day100_version_execution_proposal_history.png`, `12_day100_daily_curriculum_periods_and_execution.png`, and `13_day100_live_after_restart.png`. Earlier screenshots in the same folder show the full VI–VIII Mathematics/Science Catalogue and expanded chapters. Live health: `http://localhost:8000/health`; Catalogue: `http://localhost:3000/curriculum/catalogue`.
- Active isolated DB integrity: `integrity_check=ok`; `foreign_key_check` returned no rows. The backend was explicitly started with `DATABASE_URL=sqlite+aiosqlite:///C:/Users/Tanav/Downloads/DP/CODE/arena/scratchpad/acceptance/lumeneios_day100.db`; after restart it returned revision 45 with the same 8 textbooks, 531 structural nodes, 415 eligible topics and preserved recovery records.
- Rechecked hashes of all four original app databases match the values in the database-protection table above.

### Lesson-planning PDF

The supplied `C:\Users\Tanav\Downloads\DP\LESSON PLANNING 2026 [Autosaved].pdf` describes the Panchapadi planning template. No lesson-plan persistence/API template was added in this continuation: doing that safely requires an agreed Daily Curriculum schema and editable plan workflow, which would be a separate implementation from the existing execution ledger. This is explicitly deferred under the user's scope instruction. No syllabus records, topic identities, Core/Non-Core decisions, period requirements, or allocation rules were changed based on the PDF. The actual period execution ledger remains the source of classroom completion.

### Current limits and conclusion

The structural syllabus remains the recovered review inventory, not a claim of complete official textbook content. VI Science chapters 1 and 9 and VIII Science chapter 1 have no child topics in that source. Only VI Mathematics has approved classifications/period requirements; 350 other eligible topics remain unclassified, and no valid Day 100 subject plan can be demonstrated for them. The Day 100 VI Mathematics scenario is **ready to demonstrate with those limitations**. The Panchapadi lesson-plan template is not yet implemented.
