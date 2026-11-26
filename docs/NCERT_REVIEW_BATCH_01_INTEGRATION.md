# NCERT Review Batch 01 — integration record

Package: `LumenEIOS_NCERT_Review_Batch_01.zip` (SHA-256 `5b391ee3a6a93c3e965605d7073bf54a00e407e5b0c3268f3cda8dbefe6d1ecc`).
Tool: `scripts/import_ncert_review.py` → `backend/app/services/ncert_review_import.py`. Tests: `backend/tests/test_ncert_review_import.py` (synthetic data only).

## Status: structure staged as DRAFT, awaiting review. NOT a complete curriculum.

The package declares itself INCOMPLETE (`complete_curriculum=false`, `production_ready=false`). The importer never overrides that.

| Textbook (English) | Chapters | Numbered sections | Numbered subheadings | Unnumbered candidates (quarantined) |
|---|---|---|---|---|
| Class 6 Mathematics, Ganita Prakash | 10 | 65 | 0 | 56 |
| Class 6 Science, Curiosity | 12 | 53 | 18 | 89 |
| Class 7 Mathematics Part I | 8 | 43 | 0 | 66 |
| Class 7 Mathematics Part II | 7 | 22 | 0 | 52 |
| Class 7 Science, Curiosity | 12 | 50 | 45 | 50 |
| Class 8 Mathematics Part I | 7 | 31 | 0 | 59 |
| Class 8 Mathematics Part II | 7 | 27 | 0 | 45 |
| Class 8 Science, Curiosity | 13 | 62 | 39 | 36 |
| **Total** | **76** | **353** | **102** | **453** |

Counts are structure extracted from the package, validated for parent kinds, page provenance within each PDF's page count, and a matching source-register row. They do not establish that the textbooks are fully covered.

## What was staged (isolated database copy only)
Grade → Subject → Chapter → numbered section (TOPIC) → numbered subheading (SUBTOPIC): 540 nodes including 3 grade and 6 subject nodes, 519 evidence rows with `file, PDF p. N` locators, 8 source rows from `NCERT_SOURCE_REGISTER.csv`. Every node is `AWAITING_REVIEW` / `PARTIAL`; release `DRAFT`, batch `VALIDATED`; nothing is published. Rights stay `PERMISSION_REQUIRED`.

## What was deliberately NOT imported
- Page text, lines, blocks, citation quotes (`NCERT_SOURCE_POLICY.md`: text storage is not authorised).
- 453 unnumbered typographic heading candidates (need structure review).
- 33 learning outcomes: all analyst-INFERRED, none official NCERT wording, none audited as explicit.
- 29 concept relationships, 7 prerequisites, 4 synergies: selected, PENDING EXPERT REVIEW, reference concept occurrences rather than catalogue nodes.
- 2 Core proposals: PENDING EXPERT REVIEW. No Core/Non-Core decision or period count exists for any topic, so every imported topic stays "requirement pending" in the scheduler.
- 1,555 resource start-markers (activities, exercises, figures): no catalogue table exists; they are never independent period requirements.

## Source issues carried forward (not corrected)
Printed p. 99 arithmetic (110 ÷ 5 = 21) retained as printed; a duplicate section 2.5 title in one book; 286 appended-solution pages with unestablished provenance; 39 near-empty pages needing visual inspection.

## Usage
Audit only: `python scripts/import_ncert_review.py --zip <zip>`.
Stage: `python scripts/import_ncert_review.py --zip <zip> --apply --database <COPY.db>`. It refuses `lumeneios.db`; back up and use a copy.
Publishing a release remains unauthorised pending NCERT permission and expert review.
