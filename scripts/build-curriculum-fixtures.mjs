#!/usr/bin/env node
/**
 * Builds the curriculum-catalogue MOCK fixture from Codex-owned NCERT research CSVs.
 *
 * Usage:
 *   node scripts/build-curriculum-fixtures.mjs <path-to-apps/lumeneios/docs>
 *
 * The fixture is a metadata-only snapshot of research records (titles, editions,
 * official URLs, locators, verification statuses). It deliberately carries no
 * textbook paragraphs, exercises or learning-outcome wording. Every record keeps
 * its research ID so it can be traced back to the source CSV row.
 *
 * Nothing here is fabricated: rows are copied field-for-field (renamed to camelCase).
 * Display-status classification happens in the frontend mapping layer, not here.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const docsDir = process.argv[2];
if (!docsDir) {
  console.error('Usage: node scripts/build-curriculum-fixtures.mjs <docs-dir>');
  process.exit(1);
}

const FILES = {
  coverage: 'NCERT_VI_VIII_COVERAGE_MATRIX.csv',
  editions: 'NCERT_VI_VIII_TEXTBOOK_EDITIONS.csv',
  crosswalk: 'NCERT_VI_VIII_CHAPTER_TOPIC_OUTCOME_CROSSWALK.csv',
};

/** Minimal RFC 4180 CSV parser (quoted fields, escaped quotes, CRLF). */
function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else quoted = false;
      } else field += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ',') {
      row.push(field);
      field = '';
    } else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
    } else field += ch;
  }
  if (field !== '' || row.length) {
    row.push(field);
    rows.push(row);
  }
  const [header, ...body] = rows.filter((r) => r.length > 1 || r[0] !== '');
  return body.map((r) => Object.fromEntries(header.map((h, idx) => [h.trim(), (r[idx] ?? '').trim()])));
}

const camel = (s) => s.replace(/_([a-z0-9])/g, (_, c) => c.toUpperCase());
const pick = (row, keys) => Object.fromEntries(keys.map((k) => [camel(k), row[k] ?? '']));

const sources = {};
const read = (key) => {
  const raw = readFileSync(join(docsDir, FILES[key]), 'utf8').replace(/^﻿/, '');
  sources[FILES[key]] = createHash('sha256').update(raw).digest('hex');
  return parseCsv(raw);
};

const coverage = read('coverage').map((r) =>
  pick(r, [
    'resource_record_id', 'combination_id', 'grade', 'subject', 'resource_type', 'language', 'source_id',
    'exact_official_title', 'edition_publication', 'official_url', 'direct_verification_status',
    'evidence_locator', 'unresolved_issues', 'era', 'permission_status', 'accessed', 'availability_class',
    'parent_resource_record_id', 'linked_edition_record_id', 'checked_publication_channel_url',
    'publication_year', 'reprint_statement', 'part_volume',
  ])
);

const editions = read('editions').map((r) =>
  pick(r, [
    'resource_record_id', 'combination_id', 'parent_textbook_work_id', 'grade', 'subject', 'language', 'code',
    'source_id', 'row_type', 'exact_title', 'original_script_title', 'title_verification', 'part_volume',
    'edition', 'publication_year', 'reprint_statement', 'edition_verification', 'access_status', 'availability',
    'portal_url', 'front_matter_url', 'edition_evidence', 'locator', 'translation_equivalence',
    'official_translation_status', 'chapter_outcome_equivalence', 'academic_applicability_evidence',
    'rights_status', 'unresolved_issues', 'date_accessed', 'latest_candidate_probe', 'latest_probe_result',
  ])
);

const crosswalk = read('crosswalk').map((r) =>
  pick(r, [
    'mapping_id', 'combination_id', 'grade', 'subject', 'language', 'chapter_number', 'chapter_title',
    'topic_section', 'topic_label', 'chapter_source_id', 'book_source_id', 'book_exact_title', 'book_edition',
    'book_reprint', 'book_edition_evidence_url', 'book_edition_locator', 'chapter_official_url', 'topic_locator',
    'chapter_topic_verification', 'outcome_reference_id', 'outcome_identifier_status', 'outcome_source_id',
    'outcome_source_title', 'outcome_edition', 'outcome_official_url', 'outcome_locator', 'outcome_research_label',
    'outcome_wording_stored', 'relationship_basis', 'supporting_evidence_review', 'uncovered_scope',
    'full_outcome_coverage', 'current_curriculum_applicability', 'topic_outcome_verification', 'creation_method',
    'source_check_reviewer', 'source_check_date', 'source_check_status', 'expert_review_status',
    'recovery_eligible', 'rights_status',
  ])
);

// Defensive guard: no outcome wording may enter the fixture.
if (crosswalk.some((m) => m.outcomeWordingStored !== 'false')) {
  console.error('Refusing to build: a crosswalk row claims stored outcome wording.');
  process.exit(1);
}

const fixture = {
  meta: {
    kind: 'MOCK_RESEARCH_SNAPSHOT',
    description:
      'Metadata-only snapshot of Codex NCERT Phase 0 research CSVs for Classes VI-VIII Mathematics and Science. Not a published catalogue release.',
    generatedAt: new Date().toISOString(),
    sourceFiles: sources,
    releaseId: null,
    releaseStatus: 'NO_PUBLISHED_RELEASE',
  },
  coverage,
  editions,
  crosswalk,
};

const out = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'features', 'curriculum', 'mocks', 'researchSnapshot.json');
writeFileSync(out, JSON.stringify(fixture, null, 2) + '\n', 'utf8');
console.log(`Wrote ${out}: ${coverage.length} resources, ${editions.length} editions, ${crosswalk.length} candidate mappings`);
