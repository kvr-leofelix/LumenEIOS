/**
 * MOCK-ONLY: maps the research snapshot fixture (researchSnapshot.json) into UI view models.
 * Lives under mocks/ so production code paths never import fixture data.
 */
import { countStatuses, knownOrNull, toDisplayStatus } from '../status';
import {
  LANGUAGES,
  type CandidateMapping,
  type CatalogueMeta,
  type CatalogueResource,
  type ChapterRecord,
  type CombinationSummary,
  type DisplayStatus,
  type EvidenceRecord,
  type GradeNumber,
  type LanguageAvailabilityRow,
  type LanguageTag,
  type ReviewRecord,
  type SubjectKey,
  type TextbookEdition,
} from '../types';

export interface CoverageRow {
  resourceRecordId: string;
  combinationId: string;
  grade: string;
  subject: string;
  resourceType: string;
  language: string;
  sourceId: string;
  exactOfficialTitle: string;
  editionPublication: string;
  officialUrl: string;
  directVerificationStatus: string;
  evidenceLocator: string;
  unresolvedIssues: string;
  era: string;
  permissionStatus: string;
  accessed: string;
  availabilityClass: string;
  parentResourceRecordId: string;
  linkedEditionRecordId: string;
  checkedPublicationChannelUrl: string;
  publicationYear: string;
  reprintStatement: string;
  partVolume: string;
}

export interface EditionRow {
  resourceRecordId: string;
  combinationId: string;
  parentTextbookWorkId: string;
  grade: string;
  subject: string;
  language: string;
  code: string;
  sourceId: string;
  rowType: string;
  exactTitle: string;
  originalScriptTitle: string;
  titleVerification: string;
  partVolume: string;
  edition: string;
  publicationYear: string;
  reprintStatement: string;
  editionVerification: string;
  accessStatus: string;
  availability: string;
  portalUrl: string;
  frontMatterUrl: string;
  editionEvidence: string;
  locator: string;
  translationEquivalence: string;
  officialTranslationStatus: string;
  chapterOutcomeEquivalence: string;
  academicApplicabilityEvidence: string;
  rightsStatus: string;
  unresolvedIssues: string;
  dateAccessed: string;
  latestCandidateProbe: string;
  latestProbeResult: string;
}

export interface CrosswalkRow {
  mappingId: string;
  combinationId: string;
  grade: string;
  subject: string;
  language: string;
  chapterNumber: string;
  chapterTitle: string;
  topicSection: string;
  topicLabel: string;
  chapterSourceId: string;
  bookSourceId: string;
  bookExactTitle: string;
  bookEdition: string;
  bookReprint: string;
  bookEditionEvidenceUrl: string;
  bookEditionLocator: string;
  chapterOfficialUrl: string;
  topicLocator: string;
  chapterTopicVerification: string;
  outcomeReferenceId: string;
  outcomeIdentifierStatus: string;
  outcomeSourceId: string;
  outcomeSourceTitle: string;
  outcomeEdition: string;
  outcomeOfficialUrl: string;
  outcomeLocator: string;
  outcomeResearchLabel: string;
  outcomeWordingStored: string;
  relationshipBasis: string;
  supportingEvidenceReview: string;
  uncoveredScope: string;
  fullOutcomeCoverage: string;
  currentCurriculumApplicability: string;
  topicOutcomeVerification: string;
  creationMethod: string;
  sourceCheckReviewer: string;
  sourceCheckDate: string;
  sourceCheckStatus: string;
  expertReviewStatus: string;
  recoveryEligible: string;
  rightsStatus: string;
}

export interface ResearchSnapshot {
  meta: {
    kind: string;
    description: string;
    generatedAt: string;
    sourceFiles: Record<string, string>;
    releaseId: string | null;
    releaseStatus: string;
  };
  coverage: CoverageRow[];
  editions: EditionRow[];
  crosswalk: CrosswalkRow[];
}

const notes = (...values: (string | null | undefined)[]) =>
  values.map((v) => (v ?? '').trim()).filter((v) => v && v.toUpperCase() !== 'UNVERIFIED');

export function snapshotMeta(snapshot: ResearchSnapshot): CatalogueMeta {
  const accessed = snapshot.coverage.map((r) => r.accessed).filter(Boolean).sort();
  return {
    dataSource: 'mock',
    snapshotLabel: 'NCERT Phase 0 research snapshot (mock fixture)',
    generatedAt: snapshot.meta.generatedAt,
    researchAccessedOn: accessed[accessed.length - 1] ?? null,
    releaseId: snapshot.meta.releaseId,
    releaseStatus: snapshot.meta.releaseStatus,
    scopeNote: 'Classes VI–VIII · Mathematics and Science',
  };
}

export function mapResource(row: CoverageRow): CatalogueResource {
  const status = toDisplayStatus(row.directVerificationStatus);
  const title = knownOrNull(row.exactOfficialTitle);
  return {
    id: row.resourceRecordId,
    combinationId: row.combinationId,
    resourceType: row.resourceType,
    language: row.language,
    era: row.era,
    title,
    edition: knownOrNull(row.editionPublication),
    partLabel: knownOrNull(row.partVolume),
    status,
    evidence: {
      id: row.resourceRecordId,
      sourceTitle: title,
      sourceId: knownOrNull(row.sourceId),
      officialUrl: knownOrNull(row.officialUrl),
      secondaryUrl: knownOrNull(row.checkedPublicationChannelUrl)
        ? { label: 'Publication channel checked', url: row.checkedPublicationChannelUrl }
        : null,
      edition: knownOrNull(row.editionPublication),
      reprint: knownOrNull(row.reprintStatement),
      locator: knownOrNull(row.evidenceLocator),
      status,
      rawStatus: row.directVerificationStatus || row.availabilityClass || 'UNKNOWN',
      rightsStatus: knownOrNull(row.permissionStatus),
      accessedOn: knownOrNull(row.accessed),
      notes: notes(row.unresolvedIssues),
    },
  };
}

export function mapEdition(row: EditionRow): TextbookEdition {
  const isGap = row.rowType === 'EXPLICIT_GAP';
  const status: DisplayStatus = isGap ? 'PLACEHOLDER' : toDisplayStatus(row.editionVerification);
  const title = knownOrNull(row.exactTitle);
  return {
    id: row.resourceRecordId,
    combinationId: row.combinationId,
    textbookWorkId: row.parentTextbookWorkId,
    language: row.language,
    code: knownOrNull(row.code),
    title,
    originalScriptTitle: knownOrNull(row.originalScriptTitle),
    partLabel: /^Part\s+[IVX]+$/i.test(row.partVolume) ? row.partVolume : null,
    edition: knownOrNull(row.edition),
    reprint: knownOrNull(row.reprintStatement),
    isGap,
    status,
    translationEquivalence: row.translationEquivalence || 'UNRESOLVED',
    evidence: {
      id: row.resourceRecordId,
      sourceTitle: title,
      sourceId: knownOrNull(row.sourceId),
      officialUrl: knownOrNull(row.portalUrl),
      secondaryUrl: knownOrNull(row.frontMatterUrl)
        ? { label: 'Front matter PDF (edition statement)', url: row.frontMatterUrl }
        : null,
      edition: knownOrNull(row.edition),
      reprint: knownOrNull(row.reprintStatement),
      locator: knownOrNull(row.locator),
      status,
      rawStatus: isGap ? `${row.rowType}: ${row.availability}` : row.editionVerification,
      rightsStatus: knownOrNull(row.rightsStatus),
      accessedOn: knownOrNull(row.dateAccessed),
      notes: notes(
        row.editionEvidence && `Edition evidence: ${row.editionEvidence}`,
        row.titleVerification && `Title verification: ${row.titleVerification}`,
        `Translation equivalence: ${row.translationEquivalence || 'UNRESOLVED'}`,
        row.latestProbeResult && `Latest probe (${row.latestCandidateProbe}): ${row.latestProbeResult}`,
        row.unresolvedIssues
      ),
    },
  };
}

const RANK: Record<DisplayStatus, number> = {
  PLACEHOLDER: 0,
  BLOCKED: 0,
  UNVERIFIED: 1,
  REJECTED: 1,
  REVISION_REQUESTED: 1,
  AWAITING_REVIEW: 2,
  PARTIALLY_VERIFIED: 2,
  VERIFIED: 3,
  APPROVED: 3,
};

function weakest(statuses: DisplayStatus[]): DisplayStatus {
  return statuses.reduce((a, b) => (RANK[b] < RANK[a] ? b : a));
}

function cell(statuses: { status: DisplayStatus; id: string }[], describe: (n: number) => string) {
  if (!statuses.length) return { status: 'PLACEHOLDER' as DisplayStatus, label: 'No record', recordIds: [] };
  return {
    status: weakest(statuses.map((s) => s.status)),
    label: describe(statuses.length),
    recordIds: statuses.map((s) => s.id),
  };
}

export function buildLanguageMatrix(resources: CatalogueResource[], editions: TextbookEdition[]): LanguageAvailabilityRow[] {
  const byLang = <T extends { language: string }>(items: T[], lang: LanguageTag) => items.filter((i) => i.language === lang);
  const resourceRow = (key: string, label: string, filter: (r: CatalogueResource) => boolean): LanguageAvailabilityRow => ({
    key,
    label,
    cells: Object.fromEntries(
      LANGUAGES.map((lang) => [lang, cell(byLang(resources.filter(filter), lang), () => '')])
    ) as LanguageAvailabilityRow['cells'],
  });

  return [
    {
      key: 'textbook',
      label: 'Textbook language edition',
      cells: Object.fromEntries(
        LANGUAGES.map((lang) => {
          const items = byLang(editions, lang);
          const gaps = items.filter((e) => e.isGap).length;
          return [
            lang,
            cell(items, (n) => `${n - gaps} part${n - gaps === 1 ? '' : 's'}${gaps ? ` · ${gaps} gap` : ''}`),
          ];
        })
      ) as LanguageAvailabilityRow['cells'],
    },
    resourceRow('framework', 'Curriculum framework (NCF-SE 2023)', (r) => r.resourceType === 'CURRICULUM_FRAMEWORK'),
    resourceRow('syllabus-current', 'Syllabus — current textbooks', (r) => r.resourceType === 'SYLLABUS' && r.era === 'CURRENT_NEW_TEXTBOOKS'),
    resourceRow('syllabus-2006', 'Syllabus — historical 2006', (r) => r.resourceType === 'SYLLABUS' && r.era === 'HISTORICAL_2006'),
    resourceRow('lo-current', 'Learning outcomes — current class', (r) => r.resourceType === 'LEARNING_OUTCOMES_DOCUMENT' && r.era === 'CURRENT_CLASS_OUTCOMES'),
    resourceRow('lo-legacy', 'Learning outcomes — 2017 document', (r) => r.resourceType === 'LEARNING_OUTCOMES_DOCUMENT' && r.era === 'LEGACY_OUTCOMES'),
  ];
}

export function reviewerStatusFrom(reviews: ReviewRecord[]): DisplayStatus {
  const last = reviews[reviews.length - 1];
  if (!last) return 'AWAITING_REVIEW';
  return last.decision;
}

function topicEvidence(row: CrosswalkRow): EvidenceRecord {
  const status = toDisplayStatus(row.chapterTopicVerification);
  return {
    id: `${row.chapterSourceId}-S${row.topicSection}`,
    sourceTitle: `${row.bookExactTitle} — Chapter ${row.chapterNumber}: ${row.chapterTitle}`,
    sourceId: row.chapterSourceId,
    officialUrl: knownOrNull(row.chapterOfficialUrl),
    secondaryUrl: knownOrNull(row.bookEditionEvidenceUrl)
      ? { label: 'Textbook front matter (edition statement)', url: row.bookEditionEvidenceUrl }
      : null,
    edition: knownOrNull(row.bookEdition),
    reprint: knownOrNull(row.bookReprint),
    locator: knownOrNull(row.topicLocator),
    status,
    rawStatus: row.chapterTopicVerification,
    rightsStatus: knownOrNull(row.rightsStatus),
    accessedOn: knownOrNull(row.sourceCheckDate),
    notes: notes(row.bookEditionLocator),
  };
}

export function mapCandidate(row: CrosswalkRow, reviews: ReviewRecord[]): CandidateMapping {
  const outcomeEvidence: EvidenceRecord = {
    id: row.outcomeReferenceId,
    sourceTitle: knownOrNull(row.outcomeSourceTitle),
    sourceId: knownOrNull(row.outcomeSourceId),
    officialUrl: knownOrNull(row.outcomeOfficialUrl),
    secondaryUrl: null,
    edition: knownOrNull(row.outcomeEdition),
    reprint: null,
    locator: knownOrNull(row.outcomeLocator),
    // Outcome document is located, but its applicability to the current textbook is unverified.
    status: 'PARTIALLY_VERIFIED',
    rawStatus: row.outcomeIdentifierStatus,
    rightsStatus: knownOrNull(row.rightsStatus),
    accessedOn: knownOrNull(row.sourceCheckDate),
    notes: notes(
      `Applicability: ${row.currentCurriculumApplicability}`,
      'Outcome wording is not stored (rights pending). Only a research label is shown.'
    ),
  };
  return {
    id: row.mappingId,
    combinationId: row.combinationId,
    chapterTitle: row.chapterTitle,
    chapterNumber: row.chapterNumber,
    topicId: `${row.chapterSourceId}-S${row.topicSection}`,
    topicSection: row.topicSection,
    topicLabel: row.topicLabel,
    topicEvidence: topicEvidence(row),
    outcomeReferenceId: row.outcomeReferenceId,
    outcomeReferenceIsOfficialCode: !row.outcomeIdentifierStatus.includes('NOT_OFFICIAL'),
    outcomeResearchLabel: row.outcomeResearchLabel,
    outcomeWordingStored: row.outcomeWordingStored === 'true',
    outcomeEvidence,
    relationshipBasis: row.relationshipBasis,
    aiRationale: row.supportingEvidenceReview,
    uncoveredScope: row.uncoveredScope,
    fullOutcomeCoverage: row.fullOutcomeCoverage === 'true',
    applicability: row.currentCurriculumApplicability,
    creationMethod: row.creationMethod,
    aiCheckedBy: knownOrNull(row.sourceCheckReviewer),
    aiCheckedOn: knownOrNull(row.sourceCheckDate),
    verification: toDisplayStatus(row.topicOutcomeVerification),
    reviewerStatus: reviewerStatusFrom(reviews),
    reviews,
    revision: reviews.length,
    // Recovery eligibility is a backend decision; a frontend review never sets it.
    recoveryEligible: row.recoveryEligible === 'true',
  };
}

export function buildChapters(rows: CrosswalkRow[]): Record<string, ChapterRecord[]> {
  const bySource: Record<string, Map<string, ChapterRecord>> = {};
  for (const row of rows) {
    const chapters = (bySource[row.bookSourceId] ??= new Map());
    let chapter = chapters.get(row.chapterSourceId);
    if (!chapter) {
      const ev = topicEvidence(row);
      chapter = {
        id: row.chapterSourceId,
        number: row.chapterNumber,
        title: row.chapterTitle,
        textbookSourceId: row.bookSourceId,
        textbookTitle: row.bookExactTitle,
        textbookEdition: knownOrNull(row.bookEdition),
        status: ev.status,
        evidence: { ...ev, id: row.chapterSourceId, locator: `Chapter ${row.chapterNumber} heading` },
        topics: [],
      };
      chapters.set(row.chapterSourceId, chapter);
    }
    if (!chapter.topics.some((t) => t.section === row.topicSection)) {
      const ev = topicEvidence(row);
      chapter.topics.push({
        id: ev.id,
        section: row.topicSection,
        label: row.topicLabel,
        status: ev.status,
        evidence: ev,
        prerequisites: [], // No prerequisite relationships are verified in the research data.
      });
    }
  }
  const sectionKey = (s: string) => s.split('.').map((n) => n.padStart(4, '0')).join('.');
  return Object.fromEntries(
    Object.entries(bySource).map(([source, map]) => [
      source,
      [...map.values()]
        .sort((a, b) => Number(a.number) - Number(b.number))
        .map((c) => ({ ...c, topics: c.topics.sort((a, b) => sectionKey(a.section).localeCompare(sectionKey(b.section))) })),
    ])
  );
}

export function summarise(
  grade: GradeNumber,
  subject: SubjectKey,
  combinationId: string,
  resources: CatalogueResource[],
  editions: TextbookEdition[],
  candidates: CandidateMapping[]
): CombinationSummary {
  const titles = editions
    .filter((e) => e.language === 'en' && !e.isGap && e.title)
    .map((e) => e.title!.replace(/,\s*Part\s+[IVX]+$/i, ''));
  return {
    combinationId,
    grade,
    subject,
    textbookTitles: [...new Set(titles)],
    counts: countStatuses(resources.map((r) => r.status)),
    pendingReview: candidates.filter((c) => c.reviewerStatus === 'AWAITING_REVIEW').length,
  };
}
