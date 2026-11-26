/**
 * Presentation helpers for API-mode data. Pure functions: they never add facts that the backend did not return.
 */
import { toDisplayStatus } from '../status';
import type { DisplayStatus, EvidenceRecord } from '../types';
import type { ApiLanguage, CatalogueNode, Citation } from './contract';

export const DOCUMENT_TYPE_LABEL: Record<string, string> = {
  FRAMEWORK: 'Curriculum framework',
  SYLLABUS: 'Syllabus',
  LEARNING_OUTCOMES: 'Learning outcomes',
  TEXTBOOK: 'Textbook',
};

export const NODE_KIND_LABEL: Record<string, string> = {
  GRADE: 'Class',
  SUBJECT: 'Subject',
  CHAPTER: 'Chapter',
  TOPIC: 'Topic',
  SUBTOPIC: 'Subtopic',
  LEARNING_OUTCOME: 'Learning outcome',
};

export const API_LANGUAGE_LABEL: Record<ApiLanguage, string> = { en: 'English', hi: 'Hindi', ur: 'Urdu' };

export const docTypeLabel = (t: string) => DOCUMENT_TYPE_LABEL[t] ?? t.replace(/_/g, ' ').toLowerCase();
export const nodeKindLabel = (k: string) => NODE_KIND_LABEL[k] ?? k.replace(/_/g, ' ').toLowerCase();
export const codeLabel = (c: string | null | undefined) => (c ? c.replace(/_/g, ' ').toLowerCase() : '');

/** Node verification enum → display status. Unknown values fall back to UNVERIFIED (never VERIFIED). */
export const verificationStatus = (v: string): DisplayStatus => toDisplayStatus(v);

/** Human editorial decision state → display status. Independent of verification/publication/rights. */
export function reviewStateStatus(state: string): DisplayStatus {
  switch (state) {
    case 'APPROVED':
      return 'APPROVED';
    case 'REJECTED':
      return 'REJECTED';
    case 'REVISION_REQUESTED':
      return 'REVISION_REQUESTED';
    default:
      return 'AWAITING_REVIEW';
  }
}

/** Citation → evidence panel record. Redacted values stay null and are labelled as redacted. */
export function citationToEvidence(c: Citation): EvidenceRecord {
  const notes: string[] = [];
  if (c.notes) notes.push(c.notes);
  notes.push(
    `Source verification "${codeLabel(c.source_verification)}" describes research access to the source. It is not legal clearance, current-curriculum applicability or publication.`
  );
  return {
    id: c.evidence_id,
    sourceId: c.source_id,
    sourceTitle: c.title,
    officialUrl: c.official_url,
    secondaryUrl: null,
    edition: c.edition,
    reprint: null,
    locator: c.locator,
    status: toDisplayStatus(c.source_verification),
    rawStatus: c.source_verification,
    rightsStatus: c.rights_status,
    accessedOn: null,
    notes,
    redacted: !c.metadata_visible,
  };
}

/** Title for display: the backend returns null when text in the requested language is absent or not cleared. */
export function nodeTitle(node: Pick<CatalogueNode, 'title'>): string | null {
  return node.title && node.title.trim() ? node.title : null;
}

export function missingTitleText(node: Pick<CatalogueNode, 'requested_language' | 'kind'>): string {
  const lang = API_LANGUAGE_LABEL[node.requested_language] ?? node.requested_language;
  return `${nodeKindLabel(node.kind)} title not available in ${lang} (absent or not rights-cleared)`;
}
