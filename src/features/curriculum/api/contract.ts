/**
 * Wire types for the Curriculum Catalogue API contract v1 (2026-11-10).
 * Source of truth: apps/lumeneios/docs/CURRICULUM_API_INTEGRATION_CONTRACT.md (Codex-owned) and the
 * backend pydantic models in backend/app/schemas/ncert.py. Field names are copied verbatim (snake_case).
 * Do not add fields here that the contract does not define.
 */

export type ApiLanguage = 'en' | 'hi' | 'ur';
export const API_LANGUAGES: readonly ApiLanguage[] = ['en', 'hi', 'ur'];

export type ReleaseStatus = 'DRAFT' | 'PUBLISHED' | 'WITHDRAWN';
export type NodeKind = 'GRADE' | 'SUBJECT' | 'CHAPTER' | 'TOPIC' | 'SUBTOPIC' | 'LEARNING_OUTCOME';
export type NodeVerification = 'SOURCE_VERIFIED' | 'EXPERT_VERIFIED' | 'AI_SUGGESTED' | 'AWAITING_REVIEW' | 'REJECTED';
export type Completeness = 'VERIFIED' | 'PARTIAL' | 'UNAVAILABLE' | 'AWAITING_RIGHTS_REVIEW';
export type SourceVerification = 'FULL_REVIEW' | 'DISCOVERY_ONLY' | 'INACCESSIBLE';
export type RightsStatus = 'PERMISSION_REQUIRED' | 'RIGHTS_REVIEW_REQUIRED' | 'METADATA_APPROVED' | 'CONTENT_APPROVED' | 'DENIED';
export type ResourceDocumentType = 'FRAMEWORK' | 'SYLLABUS' | 'LEARNING_OUTCOMES' | 'TEXTBOOK';
export type AvailabilityStatus = 'NO_RELEASE_SELECTED' | 'SUBJECT_NOT_SELECTED' | 'SUBJECT_NOT_FOUND' | 'AVAILABLE' | 'PARTIAL';
export type AvailabilityPermissions = 'NOT_EVALUATED' | 'PENDING' | 'CLEARED_FOR_METADATA';
export type MappingPermissions = 'PENDING' | 'CLEARED_FOR_METADATA';
export type HumanReviewState = 'AWAITING_REVIEW' | 'APPROVED' | 'REJECTED' | 'REVISION_REQUESTED';
export type ApiReviewDecision = 'APPROVED' | 'REJECTED' | 'REVISION_REQUESTED';
export type EvidenceRole = 'SOURCE_ENDPOINT' | 'DESTINATION_ENDPOINT' | 'RELATIONSHIP';

/** Backend may add enum members; string fallbacks keep rendering honest (unknown → UNVERIFIED in the UI). */
type Open<T extends string> = T | (string & {});

export interface Page<T> {
  items: T[];
  next_offset: number | null;
}

export interface Release {
  id: string;
  release_key: string;
  edition: string;
  academic_year: string | null;
  status: Open<ReleaseStatus>;
  created_at: string;
  published_at: string | null;
}

export interface Citation {
  evidence_id: string;
  source_id: string;
  document_type: Open<ResourceDocumentType>;
  source_verification: Open<SourceVerification>;
  rights_status: Open<RightsStatus>;
  metadata_visible: boolean;
  title: string | null;
  official_url: string | null;
  edition: string | null;
  language: string | null;
  locator: string | null;
  notes: string | null;
}

export interface CatalogueNode {
  id: string;
  identity_id: string;
  release_id: string;
  parent_id: string | null;
  kind: Open<NodeKind>;
  sequence: number;
  grade_number: number | null;
  title: string | null;
  requested_language: ApiLanguage;
  resolved_language: string | null;
  translation_origin: string | null;
  verification: Open<NodeVerification>;
  completeness: Open<Completeness>;
  citations: Citation[];
  children: CatalogueNode[];
}

export interface Resource {
  source_id: string;
  document_type: Open<ResourceDocumentType>;
  language: string | null;
  rights_status: Open<RightsStatus>;
  source_verification: Open<SourceVerification>;
  citations: Citation[];
}

export interface Availability {
  grade: number;
  requested_language: ApiLanguage;
  release: Release | null;
  subject: CatalogueNode | null;
  status: Open<AvailabilityStatus>;
  resources: Resource[];
  missing_resource_types: string[];
  permissions_status: Open<AvailabilityPermissions>;
  applicability: 'UNVERIFIED';
}

export interface Review {
  id: string;
  relationship_id: string;
  revision: number;
  decision: ApiReviewDecision;
  rationale: string;
  reviewer_id: string;
  reviewed_at: string;
}

export interface Mapping {
  id: string;
  release_id: string;
  relationship_type: string;
  directionality: string;
  source: CatalogueNode;
  destination: CatalogueNode;
  verification: Open<NodeVerification>;
  creation_method: string;
  curriculum_applicability: 'UNVERIFIED';
  publication_status: Open<ReleaseStatus>;
  permissions_status: Open<MappingPermissions>;
  evidence: { role: Open<EvidenceRole>; citation: Citation }[];
  rationale: string | null;
  overlapping_outcomes: string | null;
  uncovered_outcomes: string | null;
  coverage_assessment: string | null;
  human_review_state: Open<HumanReviewState>;
  revision: number;
  latest_review: Review | null;
  recovery_eligible: false;
}

/** POST body. The backend forbids unknown fields (extra='forbid'); send exactly these three. */
export interface ReviewRequest {
  decision: ApiReviewDecision;
  rationale: string;
  expected_revision: number;
}

export const REVIEW_RATIONALE_MIN = 10;
export const REVIEW_RATIONALE_MAX = 4000;

/**
 * Allowed human-review transitions. The contract text says "REVISION_REQUESTED -> any decision" but also
 * "Same decision twice => 409"; the backend implementation (ncert_catalogue_service.decide) rejects every
 * repeated decision, so REVISION_REQUESTED -> REVISION_REQUESTED is not offered. Reported to Codex.
 */
export const ALLOWED_TRANSITIONS: Record<HumanReviewState, ApiReviewDecision[]> = {
  AWAITING_REVIEW: ['APPROVED', 'REJECTED', 'REVISION_REQUESTED'],
  REVISION_REQUESTED: ['APPROVED', 'REJECTED'],
  APPROVED: ['REJECTED', 'REVISION_REQUESTED'],
  REJECTED: ['APPROVED', 'REVISION_REQUESTED'],
};

export function allowedDecisions(state: string): ApiReviewDecision[] {
  return ALLOWED_TRANSITIONS[state as HumanReviewState] ?? [];
}

/** Domain error codes (contract: "Errors"). */
export type DomainErrorCode =
  | 'AUTHENTICATION_REQUIRED'
  | 'INVALID_TOKEN'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'RELEASE_UNAVAILABLE'
  | 'READ_ONLY_RELEASE'
  | 'STALE_REVISION'
  | 'INVALID_TRANSITION'
  | 'EVIDENCE_INCOMPLETE'
  | 'RIGHTS_BLOCKED'
  | 'INVALID_MAPPING'
  | 'DATABASE_UNAVAILABLE';
