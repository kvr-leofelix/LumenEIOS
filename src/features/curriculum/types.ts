/**
 * View-model types for the MOCK (research snapshot) mode of the Curriculum Catalogue.
 * API mode renders the backend contract types directly (see api/contract.ts); these shapes
 * are not an API definition.
 */

export type GradeNumber = 6 | 7 | 8;
export type SubjectKey = 'mathematics' | 'science';
export type LanguageTag = 'en' | 'hi' | 'ur';

export const GRADES: readonly GradeNumber[] = [6, 7, 8];
export const SUBJECTS: readonly SubjectKey[] = ['mathematics', 'science'];
export const LANGUAGES: readonly LanguageTag[] = ['en', 'hi', 'ur'];

/** User-facing status vocabulary. Every status is rendered with text + icon, never colour alone. */
export type DisplayStatus =
  | 'VERIFIED'
  | 'PARTIALLY_VERIFIED'
  | 'UNVERIFIED'
  | 'PLACEHOLDER'
  | 'AWAITING_REVIEW'
  | 'BLOCKED'
  | 'APPROVED'
  | 'REJECTED'
  | 'REVISION_REQUESTED';

export type ResourceType =
  | 'CURRICULUM_FRAMEWORK'
  | 'SYLLABUS'
  | 'LEARNING_OUTCOMES_DOCUMENT'
  | 'PRESCRIBED_TEXTBOOK_WORK'
  | 'TEXTBOOK_PART'
  | 'LANGUAGE_EDITION'
  | 'COURSE_IMPLEMENTATION_GUIDANCE';

export type DataSourceKind = 'mock' | 'api';

/** Provenance for any catalogue record (screen 4). */
export interface EvidenceRecord {
  id: string;
  sourceTitle: string | null;
  sourceId: string | null;
  officialUrl: string | null;
  /** Additional official URL (e.g. front matter PDF, chapter PDF). */
  secondaryUrl: { label: string; url: string } | null;
  edition: string | null;
  reprint: string | null;
  locator: string | null;
  status: DisplayStatus;
  /** Raw research/backend status code, shown verbatim for auditability. */
  rawStatus: string;
  rightsStatus: string | null;
  accessedOn: string | null;
  notes: string[];
  /** true when the backend redacted bibliographic values pending scoped rights clearance. */
  redacted?: boolean;
}

export interface CatalogueResource {
  id: string;
  combinationId: string;
  resourceType: ResourceType | string;
  language: LanguageTag | string;
  era: string;
  /** null when the title itself is not verified. Never substituted with another record's title. */
  title: string | null;
  edition: string | null;
  partLabel: string | null;
  status: DisplayStatus;
  evidence: EvidenceRecord;
}

export interface TextbookEdition {
  id: string;
  combinationId: string;
  textbookWorkId: string;
  language: LanguageTag | string;
  code: string | null;
  title: string | null;
  originalScriptTitle: string | null;
  partLabel: string | null;
  edition: string | null;
  reprint: string | null;
  /** true for an explicit research gap row (expected part not identified). */
  isGap: boolean;
  status: DisplayStatus;
  translationEquivalence: string;
  evidence: EvidenceRecord;
}

export interface TopicRecord {
  id: string;
  section: string;
  label: string;
  status: DisplayStatus;
  evidence: EvidenceRecord;
  /** Prerequisite relationships; empty means none verified (not "none exist"). */
  prerequisites: { id: string; label: string; status: DisplayStatus }[];
}

export interface ChapterRecord {
  id: string;
  number: string;
  title: string;
  textbookSourceId: string;
  textbookTitle: string;
  textbookEdition: string | null;
  status: DisplayStatus;
  evidence: EvidenceRecord;
  topics: TopicRecord[];
}

/** Same vocabulary as the backend ReviewRequest.decision (contract v1). */
export type ReviewDecision = 'APPROVED' | 'REJECTED' | 'REVISION_REQUESTED';

export interface ReviewRecord {
  decision: ReviewDecision;
  rationale: string;
  reviewer: string;
  reviewedAt: string;
}

export interface CandidateMapping {
  id: string;
  combinationId: string;
  chapterTitle: string;
  chapterNumber: string;
  topicId: string;
  topicSection: string;
  topicLabel: string;
  topicEvidence: EvidenceRecord;
  outcomeReferenceId: string;
  outcomeReferenceIsOfficialCode: boolean;
  /** Research label summarising the outcome. NOT official outcome wording. */
  outcomeResearchLabel: string;
  outcomeWordingStored: boolean;
  outcomeEvidence: EvidenceRecord;
  relationshipBasis: string;
  aiRationale: string;
  uncoveredScope: string;
  fullOutcomeCoverage: boolean;
  applicability: string;
  creationMethod: string;
  aiCheckedBy: string | null;
  aiCheckedOn: string | null;
  verification: DisplayStatus;
  reviewerStatus: DisplayStatus;
  reviews: ReviewRecord[];
  /** Latest review revision (0 = never reviewed); sent back as expected_revision. */
  revision: number;
  recoveryEligible: boolean;
}

export interface LanguageAvailabilityCell {
  status: DisplayStatus;
  label: string;
  recordIds: string[];
}

export interface LanguageAvailabilityRow {
  key: string;
  label: string;
  cells: Record<LanguageTag, LanguageAvailabilityCell>;
}

export interface StatusCounts {
  total: number;
  verified: number;
  partiallyVerified: number;
  unverified: number;
  placeholder: number;
}

export interface CombinationSummary {
  combinationId: string;
  grade: GradeNumber;
  subject: SubjectKey;
  textbookTitles: string[];
  counts: StatusCounts;
  pendingReview: number;
}

export interface CatalogueMeta {
  dataSource: DataSourceKind;
  snapshotLabel: string;
  generatedAt: string | null;
  researchAccessedOn: string | null;
  releaseId: string | null;
  releaseStatus: string;
  scopeNote: string;
}

export interface CatalogueDashboardData {
  meta: CatalogueMeta;
  combinations: CombinationSummary[];
}

export interface CombinationDetail {
  meta: CatalogueMeta;
  summary: CombinationSummary;
  frameworks: CatalogueResource[];
  syllabi: CatalogueResource[];
  learningOutcomes: CatalogueResource[];
  textbookWorks: CatalogueResource[];
  guidance: CatalogueResource[];
  editions: TextbookEdition[];
  languageMatrix: LanguageAvailabilityRow[];
  rightsNote: string;
}

export interface ChapterExplorerData {
  editions: TextbookEdition[];
  /** Chapters keyed by textbook source id (e.g. TB-fegp1). */
  chaptersBySource: Record<string, ChapterRecord[]>;
  completenessNote: string;
}

export function combinationId(grade: GradeNumber, subject: SubjectKey): string {
  return `VI-VIII-${grade}-${subject === 'mathematics' ? 'MATH' : 'SCIENCE'}`;
}

export const ROMAN: Record<GradeNumber, string> = { 6: 'VI', 7: 'VII', 8: 'VIII' };
export const SUBJECT_LABEL: Record<SubjectKey, string> = { mathematics: 'Mathematics', science: 'Science' };
export const LANGUAGE_LABEL: Record<LanguageTag, string> = { en: 'English', hi: 'Hindi', ur: 'Urdu' };

export function parseGrade(value: string | undefined): GradeNumber | null {
  const n = Number(value);
  return n === 6 || n === 7 || n === 8 ? n : null;
}

export function parseSubject(value: string | undefined): SubjectKey | null {
  return value === 'mathematics' || value === 'science' ? value : null;
}

/** Opens the evidence drawer for a record (used by the retained legacy review screens). */
export type OpenEvidence = (evidence: EvidenceRecord, heading?: string) => void;
