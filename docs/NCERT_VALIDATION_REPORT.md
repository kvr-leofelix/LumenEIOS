# Current VI-VIII validation and exit assessment - 2026-11-09

Structural consistency PASS. Research exit BLOCKED on authoritative current applicability and reviewed alignment, separately from pending permission. No runtime tests/database actions performed.

```json
{
  "priority_combinations": 6,
  "resource_records": 128,
  "syllabus_records": 36,
  "outcome_records": 36,
  "edition_rows": 24,
  "listed_book_parts": 22,
  "book_first_edition_years_verified": 22,
  "missing_Urdu_part_II_records": 2,
  "historical_English_syllabus_coverage_records_verified": 6,
  "current_separate_syllabus_records_with_verified_applicability": 0,
  "current_class_outcome_records_verified": 0,
  "broad_framework_reference_edges": 8,
  "verified_current_chapter_topic_outcome_edges": 0,
  "source_register_records_including_deferred": 139,
  "permission_grants": 0,
  "preserved_I_XII_coverage_rows": 24,
  "deferred_class_subject_rows": 18
}
```

Checks executed: six exact grade/subject pairs; 128 unique resource IDs; all source references resolve; missing documents have blank source IDs/URLs and separate checked-channel fields; 18 language pairs in both syllabus/outcome matrices with two era records each; 22 listed fronts with printed titles or Latin-script colophon titles and first-edition years; two explicit Urdu Part II gaps; 32 alignment assessments with recovery disabled; no verified grant; original 24/108 I-XII coverage/language rows retained; 18 non-priority class/subject rows explicitly deferred.

The six historical English syllabus coverage entries refer to two physical subject documents, not six newly discovered syllabi. The 2017 outcome sections do not establish current textbook alignment. Book titles verified through Urdu Latin-script colophons are not claimed as verified Urdu native-script transcription. First-edition years are not proof of translation or current adoption. Eight broad framework-reference edges do not verify the particular framework print edition or chapter/topic/outcome coverage.

Gate failures remain: current course-defining syllabus/source status per language, applicable current outcome source/class mapping, source-language/edition equivalence and missing-part publication status, and reviewed chapter/topic/outcome crosswalks. NCERT clarification/source evidence and accepted curriculum review are external dependencies, not waived. Permission remains separate: zero grants, ingestion not authorised. No Phase 1 recommendation.

---

## Historical I-XII validation snapshot retained below

# Phase 0 research validation - 2026-11-09

Canonical location: apps/lumeneios/docs/. Research scope: Mathematics and Science categories, Classes I-XII.

## Exact research counts

```json
{
  "sources": 136,
  "directly_accessed_sources": 128,
  "inaccessible_sources": 8,
  "unverified_discovery_sources": 0,
  "listed_textbook_parts": 97,
  "front_matter_accesses_verified": 97,
  "language_rows": 108,
  "coverage_rows": 24,
  "book_first_edition_year_verified": 43,
  "book_exact_titles_verified": 28,
  "complete_archive_links_responding": 95,
  "permission_grants": 0
}
```

Direct access is not full bibliographic verification, current-edition validation or permission. Counts of source records are not counts of unique books across languages. Language rows include explicit gaps; no source records are invented for missing variants.

## Structural checks performed

PASS: exactly 24 unique grade/category pairs; all I-XII present for both categories; each pair has explicit en/hi/ur language entries; 97 listed book-part rows; unique source IDs; every coverage source ID resolves; one permission row per source; no grant marked received. CSVs read/written as UTF-8. No runtime import performed.

## Substantive validation failures / blockers

OPEN EDITION_UNVERIFIED: original-script and some exact title/edition metadata remain unverified; source rows identify these. OPEN TRANSLATION_UNVERIFIED: no chapter/outcome equivalence review completed. OPEN SOURCE_ACCESS: some framework/syllabus/outcome/rationalisation sources inaccessible or scanned/unreadable. OPEN APPLICABILITY: legacy syllabus/outcome and rationalisation documents are not automatically aligned to new books. OPEN RIGHTS: no authoritative grant for intended software uses. OPEN SCHEMA: bibliographic lifecycle/reprint and broad outcome scope need a contract amendment. RESEARCH_COMPLETE=false; CONTENT_INGESTION_AUTHORISED=false.

## Historical implementation evidence, not rerun here

Prior catalogue tests: 7 passed in 1.23s; full backend suite: 76 passed in 3.76s. No runtime tests were run for this research-only task. No application database migration/reset/ingestion occurred. The 13-model foundation and prior code changes were preserved. Global SQLite FK compatibility and live PostgreSQL validation remain unresolved from prior work.

## Further count distinctions
Of the 97 directly accessed book-part front matters, first-edition years remain UNVERIFIED for 54 and exact printed titles remain UNVERIFIED for 69. The English first-edition-year count is 34/34; Hindi 9/33; Urdu 0/30. Exact printed titles verified: English 28/34; Hindi 0/33; Urdu 0/30. This does not mean those languages lack books: official listing/front-matter access is verified for all 97 listed variants. All 63 non-English counterpart/equivalence relationships remain unresolved. Complete-book link HEAD responses succeeded for 95/97 (en 34/34, hi 32/33, ur 29/30); archives were not downloaded and integrity/content completeness was not established. Two failed HEAD checks do not erase successful front-matter access.
The 8 inaccessible count denotes latest unresolved source access, not proof that all were never retrieved: RATIONAL-7 and LO-HIGHER-DRAFT had an earlier machine retrieval before the temporary logger failed; their bibliographic verification is still unresolved, and the access history is retained. Framework mirror browser retry returned 404; separate shell attempt timed out. No TLS verification was bypassed.

Final read-back validation also passed: 136 unique sources and permission rows; every listed language source resolves; all 72 grade/category/medium combinations are present; seven retained root/canonical mirrors have matching SHA-256 hashes. This validates artifact structure only. Rationalisation records use document_type NOTICE plus research document_subtype RATIONALISED_CONTENT; the subtype is not an implemented runtime field. No research process remains pending.

Latest research checks: ten new crosswalk rows reference six directly inspected official chapters and six located 2017 outcome paragraphs. All ten are source-checked AI inferences awaiting qualified review, not verified current outcome mappings. Source/permission registers have 146 unique rows each; priority resource records have 130. A directly verified NCERT 16 August 2024 advisory supplies dated Grade VI learning-standard guidance. Existing structural counts above are historical snapshots where superseded. Full chapter coverage, current applicability, language equivalence and permission are not closed. No runtime tests or database actions performed.
