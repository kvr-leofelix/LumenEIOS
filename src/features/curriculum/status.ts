import type { DisplayStatus, StatusCounts } from './types';

/**
 * Presentation mapping from raw research/backend verification codes to display statuses.
 * Explicit table: anything not listed falls back to UNVERIFIED (never VERIFIED).
 */
const RAW_STATUS_TABLE: Record<string, DisplayStatus> = {
  // Coverage matrix: direct_verification_status (first clause)
  DIRECT_FRAMEWORK_SECTION_VERIFIED: 'VERIFIED',
  SOURCE_VERIFIED_FOR_DATED_GRADE_VI_IMPLEMENTATION_GUIDANCE: 'VERIFIED',
  DIRECT_FRONT_MATTER_VERIFIED: 'VERIFIED',
  CLASS_SUBJECT_SECTION_VERIFIED: 'VERIFIED',
  AVAILABLE_VERIFIED_ENGLISH_ARCHIVE_MEMBER: 'VERIFIED',
  PRINTED_TITLE_EDITION_AND_PART_SOURCE_VERIFIED: 'VERIFIED',
  VISUAL_PRINTED_TITLE_AND_FIRST_EDITION_YEAR_VERIFIED: 'PARTIALLY_VERIFIED',
  OFFICIAL_HINDI_DOCUMENT_AND_TITLE_VERIFIED: 'PARTIALLY_VERIFIED',
  OFFICIAL_URDU_DOCUMENT_AND_CLASS_VI_SUBJECT_HEADER_VERIFIED: 'PARTIALLY_VERIFIED',
  OFFICIAL_URDU_DOCUMENT_TITLE_AND_YEAR_VERIFIED: 'PARTIALLY_VERIFIED',
  NCERT_PUBLICATION_SET_LISTED: 'PARTIALLY_VERIFIED',
  LANGUAGE_NOT_VERIFIED: 'UNVERIFIED',
  NO_INDIVIDUAL_SOURCE_IDENTIFIED: 'PLACEHOLDER',
  CURRENT_CLASS_SPECIFIC_DOCUMENT_NOT_VERIFIED: 'PLACEHOLDER',
  NOT_FOUND_IN_CHECKED_NCERT_CHANNELS: 'PLACEHOLDER',
  // Editions: edition_verification
  VERIFIED_FIRST_EDITION: 'VERIFIED',
  VISUAL_FIRST_EDITION_YEAR_VERIFIED: 'PARTIALLY_VERIFIED',
  // Crosswalk
  SOURCE_VERIFIED_FOR_HEADING_AND_SECTION_MEMBERSHIP: 'VERIFIED',
  // Catalogue contract v1 verification enum
  SOURCE_VERIFIED: 'VERIFIED',
  EXPERT_VERIFIED: 'VERIFIED',
  AI_SUGGESTED: 'AWAITING_REVIEW',
  AWAITING_REVIEW: 'AWAITING_REVIEW',
  REJECTED: 'REJECTED',
  // Catalogue contract v1 completeness enum
  PARTIAL: 'PARTIALLY_VERIFIED',
  UNAVAILABLE: 'PLACEHOLDER',
  AWAITING_RIGHTS_REVIEW: 'BLOCKED',
  // Contract v1 source_verification (research access status, never legal clearance)
  FULL_REVIEW: 'VERIFIED',
  DISCOVERY_ONLY: 'UNVERIFIED',
  INACCESSIBLE: 'PLACEHOLDER',
};

export function toDisplayStatus(raw: string | null | undefined): DisplayStatus {
  if (!raw) return 'UNVERIFIED';
  const head = raw.split(';')[0].trim();
  return RAW_STATUS_TABLE[head] ?? 'UNVERIFIED';
}

/** Research CSVs use the literal 'UNVERIFIED' / '' for unknown values; normalise to null. */
export function knownOrNull(value: string | null | undefined): string | null {
  if (value == null) return null;
  const v = value.trim();
  // Research CSVs encode unknowns as 'UNVERIFIED', 'UNVERIFIED; …' or codes like 'UNVERIFIED_NATIVE_SCRIPT_TRANSCRIPTION'.
  if (!v || /^UNVERIFIED(\b|_)/.test(v.toUpperCase())) return null;
  return v;
}

export const STATUS_LABEL: Record<DisplayStatus, string> = {
  VERIFIED: 'Verified',
  PARTIALLY_VERIFIED: 'Partially verified',
  UNVERIFIED: 'Unverified',
  PLACEHOLDER: 'Placeholder',
  AWAITING_REVIEW: 'Awaiting review',
  BLOCKED: 'Blocked',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  REVISION_REQUESTED: 'Revision requested',
};

export const STATUS_DESCRIPTION: Record<DisplayStatus, string> = {
  VERIFIED: 'Checked directly against an official source.',
  PARTIALLY_VERIFIED: 'Some attributes are source-checked; others remain open.',
  UNVERIFIED: 'Not yet checked against an official source.',
  PLACEHOLDER: 'Expected record not found or not yet identified. No content is shown.',
  AWAITING_REVIEW: 'Candidate awaiting a recorded human review decision.',
  BLOCKED: 'Blocked pending rights or permission review.',
  APPROVED: 'A reviewer approved this candidate.',
  REJECTED: 'A reviewer rejected this candidate.',
  REVISION_REQUESTED: 'A reviewer asked for this candidate to be revised.',
};

export function countStatuses(statuses: DisplayStatus[]): StatusCounts {
  return {
    total: statuses.length,
    verified: statuses.filter((s) => s === 'VERIFIED').length,
    partiallyVerified: statuses.filter((s) => s === 'PARTIALLY_VERIFIED').length,
    unverified: statuses.filter((s) => s === 'UNVERIFIED').length,
    placeholder: statuses.filter((s) => s === 'PLACEHOLDER').length,
  };
}
