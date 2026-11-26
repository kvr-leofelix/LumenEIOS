/**
 * Structured syllabus data layer for Classes VI–VIII Mathematics and Science (English textbooks).
 *
 * Built-in content comes ONLY from the existing Codex Phase 0 research snapshot
 * (src/features/curriculum/mocks/researchSnapshot.json, generated from the NCERT_VI_VIII_* research CSVs).
 * Rows are copied field-for-field; nothing is invented. That research verified 10 chapter/topic rows across
 * 6 chapters. Full chapter/topic/activity/exercise extraction is NOT available in any repository dataset and the
 * project source policy (NCERT_SOURCE_POLICY.md) does not authorise textbook-content extraction. Additional data can
 * be imported as a separate, labelled dataset (see validateImport) — it never merges into the verified dataset.
 *
 * Core/Non-Core is deliberately absent here; classification lives in governance.ts.
 */
import snapshot from '../../features/curriculum/mocks/researchSnapshot.json';
import type { PlanningSubject } from './calendar';

export type SyllabusNodeKind = 'CHAPTER' | 'TOPIC' | 'SUBTOPIC' | 'ACTIVITY' | 'INVESTIGATION' | 'EXAMPLE' | 'EXERCISE';
export const NODE_KINDS: SyllabusNodeKind[] = ['CHAPTER', 'TOPIC', 'SUBTOPIC', 'ACTIVITY', 'INVESTIGATION', 'EXAMPLE', 'EXERCISE'];
/**
 * Kinds that receive their own classroom time: conceptual topics and subtopics ONLY.
 * Activities, investigations, examples and exercises stay in the catalogue as instructional resources attached to
 * their parent concept; they never become independent period requirements.
 */
export const SCHEDULABLE_KINDS: SyllabusNodeKind[] = ['TOPIC', 'SUBTOPIC'];
/** Kinds that are associated instructional resources of a conceptual topic. */
export const RESOURCE_KINDS: SyllabusNodeKind[] = ['ACTIVITY', 'INVESTIGATION', 'EXAMPLE', 'EXERCISE'];

export type DatasetKind = 'VERIFIED_RESEARCH' | 'PUBLISHED_API' | 'SCHOOL_IMPORT';

export const DATASET_KIND_LABEL: Record<DatasetKind, string> = {
  VERIFIED_RESEARCH: 'Source-checked research metadata',
  PUBLISHED_API: 'Published catalogue (backend API)',
  SCHOOL_IMPORT: 'School import — unverified',
};

export interface Provenance {
  datasetId: string;
  sourceId: string;
  officialUrl?: string;
  locator: string;
  verification: string;
}

export interface Textbook {
  id: string;
  datasetId: string;
  grade: number;
  subject: PlanningSubject;
  language: 'en';
  code: string;
  title: string;
  part: string;
  edition: string;
  reprint: string;
  publicationYear: string;
  editionVerification: string;
  evidenceUrl: string;
  locator: string;
}

export interface SyllabusNode {
  id: string;
  datasetId: string;
  textbookId: string;
  grade: number;
  subject: PlanningSubject;
  kind: SyllabusNodeKind;
  parentId: string | null;
  number: string;
  title: string;
  sequence: number;
  provenance: Provenance;
}

/** A pointer to an official outcome document location. Official wording is never stored. */
export interface OutcomeReference {
  id: string;
  datasetId: string;
  grade: number;
  subject: PlanningSubject;
  sourceTitle: string;
  edition: string;
  officialUrl: string;
  locator: string;
  researchLabel: string;
  identifierStatus: string;
  linkedNodeIds: string[];
  relationshipBasis: string;
  linkVerification: string;
  applicability: string;
  /** true when the topic→outcome link is inferred rather than published by NCERT. */
  inferred: boolean;
}

export interface SourceDocument {
  id: string;
  grade: number;
  subject: string;
  type: string;
  title: string;
  edition: string;
  url: string;
  verification: string;
  issues: string;
}

export interface SyllabusDataset {
  id: string;
  kind: DatasetKind;
  label: string;
  description: string;
  importedAt?: string;
  importedBy?: string;
  textbooks: Textbook[];
  nodes: SyllabusNode[];
  outcomes: OutcomeReference[];
}

type Row = Record<string, string>;
const snap = snapshot as unknown as { meta: Row; coverage: Row[]; editions: Row[]; crosswalk: Row[] };

export const VERIFIED_DATASET_ID = 'codex-phase0-research';

function buildVerifiedDataset(): SyllabusDataset {
  const textbooks: Textbook[] = snap.editions
    .filter((e) => e.language === 'en' && (e.subject === 'Mathematics' || e.subject === 'Science'))
    .map((e) => ({
      id: e.sourceId,
      datasetId: VERIFIED_DATASET_ID,
      grade: Number(e.grade),
      subject: e.subject as PlanningSubject,
      language: 'en',
      code: e.code,
      title: e.exactTitle,
      part: e.partVolume,
      edition: e.edition,
      reprint: e.reprintStatement,
      publicationYear: e.publicationYear,
      editionVerification: e.editionVerification,
      evidenceUrl: e.frontMatterUrl || e.portalUrl,
      locator: e.locator,
    }));

  const nodes: SyllabusNode[] = [];
  const outcomes = new Map<string, OutcomeReference>();
  const rows = snap.crosswalk.filter((r) => r.language === 'en');
  for (const r of rows) {
    const subject = r.subject as PlanningSubject;
    const grade = Number(r.grade);
    if (!nodes.some((n) => n.id === r.chapterSourceId)) {
      nodes.push({
        id: r.chapterSourceId,
        datasetId: VERIFIED_DATASET_ID,
        textbookId: r.bookSourceId,
        grade,
        subject,
        kind: 'CHAPTER',
        parentId: null,
        number: r.chapterNumber,
        title: r.chapterTitle,
        sequence: Number(r.chapterNumber) * 1000,
        provenance: {
          datasetId: VERIFIED_DATASET_ID,
          sourceId: r.chapterSourceId,
          officialUrl: r.chapterOfficialUrl,
          locator: `${r.bookExactTitle}, ${r.bookEdition}; ${r.bookReprint}`,
          verification: r.chapterTopicVerification,
        },
      });
    }
    const topicId = `${r.chapterSourceId}-S${r.topicSection}`;
    if (!nodes.some((n) => n.id === topicId)) {
      const depth = r.topicSection.split('.').length;
      nodes.push({
        id: topicId,
        datasetId: VERIFIED_DATASET_ID,
        textbookId: r.bookSourceId,
        grade,
        subject,
        // Kind follows section-numbering depth only; the research did not record activity/investigation status.
        kind: depth > 2 ? 'SUBTOPIC' : 'TOPIC',
        parentId: r.chapterSourceId,
        number: r.topicSection,
        title: r.topicLabel,
        sequence: sectionSequence(r.chapterNumber, r.topicSection),
        provenance: {
          datasetId: VERIFIED_DATASET_ID,
          sourceId: r.mappingId,
          officialUrl: r.chapterOfficialUrl,
          locator: r.topicLocator,
          verification: r.chapterTopicVerification,
        },
      });
    }
    const existing = outcomes.get(r.outcomeReferenceId);
    if (existing) {
      if (!existing.linkedNodeIds.includes(topicId)) existing.linkedNodeIds.push(topicId);
    } else {
      outcomes.set(r.outcomeReferenceId, {
        id: r.outcomeReferenceId,
        datasetId: VERIFIED_DATASET_ID,
        grade,
        subject,
        sourceTitle: r.outcomeSourceTitle,
        edition: r.outcomeEdition,
        officialUrl: r.outcomeOfficialUrl,
        locator: r.outcomeLocator,
        researchLabel: r.outcomeResearchLabel,
        identifierStatus: r.outcomeIdentifierStatus,
        linkedNodeIds: [topicId],
        relationshipBasis: r.relationshipBasis,
        linkVerification: r.topicOutcomeVerification,
        applicability: r.currentCurriculumApplicability,
        inferred: true,
      });
    }
  }
  return {
    id: VERIFIED_DATASET_ID,
    kind: 'VERIFIED_RESEARCH',
    label: 'Codex Phase 0 NCERT research (source-checked metadata)',
    description:
      'Exact textbook editions and source-checked chapter/section headings with page locators. Partial coverage: only the researched sections are present; most chapters are not yet extracted. Outcome links are AI-suggested partial overlaps awaiting expert review, never official NCERT mappings. No textbook prose or outcome wording is stored.',
    textbooks,
    nodes,
    outcomes: [...outcomes.values()],
  };
}

/** "4.3" in chapter 4 → 4003; "6.3.4" → 6003.004 — preserves textbook order across depths. */
function sectionSequence(chapter: string, section: string): number {
  const parts = section.split('.').map(Number);
  return Number(chapter) * 1000 + (parts[1] || 0) + (parts[2] || 0) / 1000 + (parts[3] || 0) / 1e6;
}

export const VERIFIED_DATASET: SyllabusDataset = buildVerifiedDataset();

export const SOURCE_DOCUMENTS: SourceDocument[] = snap.coverage
  .filter((c) => c.language === 'en')
  .map((c) => ({
    id: c.resourceRecordId,
    grade: Number(c.grade),
    subject: c.subject,
    type: c.resourceType,
    title: c.exactOfficialTitle,
    edition: c.editionPublication,
    url: c.officialUrl,
    verification: c.directVerificationStatus,
    issues: c.unresolvedIssues,
  }));

export const RESEARCH_META = snap.meta;

export function allDatasets(imported: SyllabusDataset[]): SyllabusDataset[] {
  return [VERIFIED_DATASET, ...imported];
}

export interface SyllabusView {
  dataset: SyllabusDataset;
  textbooks: Textbook[];
  chapters: SyllabusNode[];
  /** Every node for the combination, in textbook order. */
  nodes: SyllabusNode[];
  /** Units that receive classroom time, in textbook order. */
  units: SyllabusNode[];
  outcomes: OutcomeReference[];
}

/**
 * The ONE rule for which syllabus entries are independently teachable (scheduled, tracked for coverage, counted in progress):
 * conceptual topics and subtopics, excluding a topic that is only a heading for schedulable children (so a parent and its
 * child are never counted twice). Activities, investigations, examples, exercises and diagrams are resources, never units.
 */
export function eligibleUnits(nodes: SyllabusNode[]): SyllabusNode[] {
  const parents = new Set(nodes.filter((n) => SCHEDULABLE_KINDS.includes(n.kind) && n.parentId).map((n) => n.parentId as string));
  return nodes.filter((n) => SCHEDULABLE_KINDS.includes(n.kind) && !parents.has(n.id));
}

/**
 * Dataset both Course Curriculum and the Time-Aware Engine open by default for a class and subject: the one with the most
 * teachable units (ties keep the earlier dataset), so the two modules show the same topics and topic identities.
 */
export function defaultDatasetFor(datasets: SyllabusDataset[], grade: number, subject: PlanningSubject): SyllabusDataset {
  let best = datasets[0];
  let bestCount = -1;
  for (const d of datasets) {
    const count = syllabusFor(d, grade, subject).units.length;
    if (count > bestCount) {
      best = d;
      bestCount = count;
    }
  }
  return best;
}

export function syllabusFor(dataset: SyllabusDataset, grade: number, subject: PlanningSubject): SyllabusView {
  const textbooks = dataset.textbooks.filter((t) => t.grade === grade && t.subject === subject);
  const nodes = dataset.nodes.filter((n) => n.grade === grade && n.subject === subject);
  const bookOrder = (id: string) => {
    const i = textbooks.findIndex((t) => t.id === id);
    return i < 0 ? 99 : i;
  };
  nodes.sort((a, b) => bookOrder(a.textbookId) - bookOrder(b.textbookId) || a.sequence - b.sequence);
  return {
    dataset,
    textbooks,
    chapters: nodes.filter((n) => n.kind === 'CHAPTER'),
    nodes,
    units: eligibleUnits(nodes),
    outcomes: dataset.outcomes.filter((o) => o.grade === grade && o.subject === subject),
  };
}

export function findNode(datasets: SyllabusDataset[], id: string): SyllabusNode | undefined {
  for (const d of datasets) {
    const n = d.nodes.find((x) => x.id === id);
    if (n) return n;
  }
  return undefined;
}

export function chapterOf(datasets: SyllabusDataset[], node: SyllabusNode): SyllabusNode | undefined {
  let cur: SyllabusNode | undefined = node;
  while (cur && cur.kind !== 'CHAPTER' && cur.parentId) cur = findNode(datasets, cur.parentId);
  return cur && cur.kind === 'CHAPTER' ? cur : undefined;
}

/** Instructional resources (activities, investigations, examples, exercises) attached beneath a unit. */
export function practiceItems(dataset: SyllabusDataset, unitId: string): SyllabusNode[] {
  return dataset.nodes.filter((n) => n.parentId === unitId && RESOURCE_KINDS.includes(n.kind));
}

/* ------------------------------------------------------------------ import ---- */

export interface ImportResult {
  dataset?: SyllabusDataset;
  errors: string[];
}

/**
 * Validates a JSON syllabus import. Imports are always stored as SCHOOL_IMPORT datasets: they are labelled as
 * unverified by LumenEIOS, require per-record provenance, and are never mixed into the verified research dataset.
 * Expected shape: { label, description, textbooks: Textbook-like[], nodes: SyllabusNode-like[], outcomes?: [] }
 */
export function validateImport(raw: string, existingIds: string[], importedBy: string): ImportResult {
  let data: Record<string, unknown>;
  try {
    data = JSON.parse(raw);
  } catch {
    return { errors: ['The file is not valid JSON.'] };
  }
  const errors: string[] = [];
  const label = typeof data.label === 'string' ? data.label.trim() : '';
  if (!label) errors.push('A dataset "label" is required.');
  const textbooks = Array.isArray(data.textbooks) ? (data.textbooks as Record<string, unknown>[]) : [];
  const nodes = Array.isArray(data.nodes) ? (data.nodes as Record<string, unknown>[]) : [];
  if (!textbooks.length) errors.push('At least one textbook record is required.');
  if (!nodes.length) errors.push('At least one syllabus node is required.');
  const id = `import-${Date.now().toString(36)}`;
  const tbIds = new Set<string>();
  const outBooks: Textbook[] = [];
  textbooks.forEach((t, i) => {
    const where = `Textbook ${i + 1}`;
    const grade = Number(t.grade);
    if (![6, 7, 8].includes(grade)) errors.push(`${where}: grade must be 6, 7 or 8.`);
    if (t.subject !== 'Mathematics' && t.subject !== 'Science') errors.push(`${where}: subject must be Mathematics or Science.`);
    if (t.language !== undefined && t.language !== 'en') errors.push(`${where}: only English-language textbooks are in scope.`);
    for (const f of ['id', 'title', 'edition']) if (!String(t[f] ?? '').trim()) errors.push(`${where}: "${f}" is required.`);
    if (existingIds.includes(String(t.id)) || tbIds.has(String(t.id))) errors.push(`${where}: id "${t.id}" already exists.`);
    tbIds.add(String(t.id));
    outBooks.push({
      id: String(t.id),
      datasetId: id,
      grade,
      subject: t.subject as PlanningSubject,
      language: 'en',
      code: String(t.code ?? ''),
      title: String(t.title ?? ''),
      part: String(t.part ?? ''),
      edition: String(t.edition ?? ''),
      reprint: String(t.reprint ?? 'Not stated'),
      publicationYear: String(t.publicationYear ?? ''),
      editionVerification: 'UNVERIFIED_SCHOOL_IMPORT',
      evidenceUrl: String(t.evidenceUrl ?? ''),
      locator: String(t.locator ?? ''),
    });
  });
  const nodeIds = new Set<string>();
  const outNodes: SyllabusNode[] = [];
  nodes.forEach((n, i) => {
    const where = `Node ${i + 1}`;
    const tb = outBooks.find((b) => b.id === n.textbookId);
    if (!tb) errors.push(`${where}: textbookId "${n.textbookId}" does not match an imported textbook.`);
    if (!NODE_KINDS.includes(n.kind as SyllabusNodeKind)) errors.push(`${where}: kind must be one of ${NODE_KINDS.join(', ')}.`);
    if (n.kind === 'CHAPTER' && n.parentId) errors.push(`${where}: chapters cannot have a parent.`);
    if (n.kind !== 'CHAPTER' && !n.parentId) errors.push(`${where}: non-chapter nodes need a parentId.`);
    for (const f of ['id', 'title']) if (!String(n[f] ?? '').trim()) errors.push(`${where}: "${f}" is required.`);
    if (!String(n.sourceLocator ?? '').trim()) errors.push(`${where}: "sourceLocator" (page/chapter provenance) is required.`);
    if (existingIds.includes(String(n.id)) || nodeIds.has(String(n.id))) errors.push(`${where}: id "${n.id}" already exists.`);
    if (/core/i.test(String(n.classification ?? ''))) errors.push(`${where}: Core/Non-Core classification is not accepted during ingestion.`);
    nodeIds.add(String(n.id));
    outNodes.push({
      id: String(n.id),
      datasetId: id,
      textbookId: String(n.textbookId),
      grade: tb?.grade ?? 0,
      subject: tb?.subject ?? 'Mathematics',
      kind: n.kind as SyllabusNodeKind,
      parentId: n.parentId ? String(n.parentId) : null,
      number: String(n.number ?? ''),
      title: String(n.title ?? ''),
      sequence: Number.isFinite(Number(n.sequence)) ? Number(n.sequence) : i,
      provenance: {
        datasetId: id,
        sourceId: String(n.id),
        officialUrl: n.sourceUrl ? String(n.sourceUrl) : undefined,
        locator: String(n.sourceLocator ?? ''),
        verification: 'UNVERIFIED_SCHOOL_IMPORT',
      },
    });
  });
  outNodes.forEach((n, i) => {
    if (n.parentId && !nodeIds.has(n.parentId)) errors.push(`Node ${i + 1}: parentId "${n.parentId}" not found in this import.`);
  });
  if (errors.length) return { errors };
  return {
    errors: [],
    dataset: {
      id,
      kind: 'SCHOOL_IMPORT',
      label,
      description: `${String(data.description ?? '').trim() || 'School-supplied dataset.'} Imported data is not verified by LumenEIOS.`,
      importedAt: new Date().toISOString(),
      importedBy,
      textbooks: outBooks,
      nodes: outNodes,
      outcomes: [],
    },
  };
}
