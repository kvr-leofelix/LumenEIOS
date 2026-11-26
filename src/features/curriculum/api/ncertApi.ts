/**
 * HTTP adapter for the Curriculum Catalogue API contract v1 (base /api/v1/ncert).
 * Uses the app's existing authenticated request helper (Bearer token from the existing login).
 * Routes, query parameters and bodies match CURRICULUM_API_INTEGRATION_CONTRACT.md exactly; no other routes are called.
 */
import { ApiError, apiRequest } from '../../../lib/apiClient';
import type {
  ApiLanguage,
  Availability,
  CatalogueNode,
  Mapping,
  Page,
  Release,
  Review,
  ReviewRequest,
} from './contract';
import { REVIEW_RATIONALE_MAX, REVIEW_RATIONALE_MIN } from './contract';

type Request = <T>(endpoint: string, options?: RequestInit) => Promise<T>;

export interface PageParams {
  limit?: number;
  offset?: number;
}

export interface NcertApi {
  listReleases(params?: PageParams): Promise<Page<Release>>;
  listSubjects(params: { releaseId: string; grade: number; language?: ApiLanguage } & PageParams): Promise<Page<CatalogueNode>>;
  getAvailability(params: {
    grade: number;
    releaseId?: string | null;
    subjectIdentityId?: string | null;
    language?: ApiLanguage;
  }): Promise<Availability>;
  getNode(nodeId: string, language?: ApiLanguage): Promise<CatalogueNode>;
  listMappings(params: { releaseId: string; subjectNodeId?: string | null; language?: ApiLanguage } & PageParams): Promise<Page<Mapping>>;
  getMapping(mappingId: string, language?: ApiLanguage): Promise<Mapping>;
  listReviews(mappingId: string, params?: PageParams): Promise<Page<Review>>;
  submitReview(mappingId: string, body: ReviewRequest): Promise<Review>;
}

export const NCERT_BASE = '/ncert';

function query(params: Record<string, string | number | null | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') q.append(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : '';
}

const seg = (id: string) => encodeURIComponent(id);

/** Client-side mirror of ReviewRequest validation (backend remains authoritative). */
export function validateReviewRequest(body: ReviewRequest): string | null {
  if (!['APPROVED', 'REJECTED', 'REVISION_REQUESTED'].includes(body.decision)) return 'Choose a review decision.';
  const n = body.rationale.trim().length;
  if (n < REVIEW_RATIONALE_MIN) return `A decision rationale of at least ${REVIEW_RATIONALE_MIN} characters is required.`;
  if (n > REVIEW_RATIONALE_MAX) return `The rationale must be at most ${REVIEW_RATIONALE_MAX} characters.`;
  if (!Number.isInteger(body.expected_revision) || body.expected_revision < 0) return 'The mapping revision is missing; reload the mapping.';
  return null;
}

export function createNcertApi(request: Request = apiRequest): NcertApi {
  return {
    listReleases: ({ limit, offset } = {}) => request<Page<Release>>(`${NCERT_BASE}/releases${query({ limit, offset })}`),

    listSubjects: ({ releaseId, grade, language, limit, offset }) =>
      request<Page<CatalogueNode>>(
        `${NCERT_BASE}/subjects${query({ release_id: releaseId, grade, language, limit, offset })}`
      ),

    getAvailability: ({ grade, releaseId, subjectIdentityId, language }) =>
      request<Availability>(
        `${NCERT_BASE}/availability${query({ grade, release_id: releaseId, subject_identity_id: subjectIdentityId, language })}`
      ),

    getNode: (nodeId, language) => request<CatalogueNode>(`${NCERT_BASE}/nodes/${seg(nodeId)}${query({ language })}`),

    listMappings: ({ releaseId, subjectNodeId, language, limit, offset }) =>
      request<Page<Mapping>>(
        `${NCERT_BASE}/mappings${query({ release_id: releaseId, subject_node_id: subjectNodeId, language, limit, offset })}`
      ),

    getMapping: (mappingId, language) => request<Mapping>(`${NCERT_BASE}/mappings/${seg(mappingId)}${query({ language })}`),

    listReviews: (mappingId, { limit, offset } = {}) =>
      request<Page<Review>>(`${NCERT_BASE}/mappings/${seg(mappingId)}/reviews${query({ limit, offset })}`),

    submitReview: (mappingId, body) => {
      const problem = validateReviewRequest(body);
      if (problem) return Promise.reject(new ApiError(422, problem));
      // Exactly the three contract fields: extra fields are rejected by the backend.
      const payload: ReviewRequest = {
        decision: body.decision,
        rationale: body.rationale.trim(),
        expected_revision: body.expected_revision,
      };
      return request<Review>(`${NCERT_BASE}/mappings/${seg(mappingId)}/reviews`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
  };
}

/** Follows next_offset until exhausted (bounded, deterministic id ordering per contract). */
export async function fetchAllPages<T>(
  load: (offset: number) => Promise<Page<T>>,
  maxPages = 20
): Promise<T[]> {
  const items: T[] = [];
  let offset: number | null = 0;
  for (let i = 0; offset !== null && i < maxPages; i++) {
    const page: Page<T> = await load(offset);
    items.push(...page.items);
    offset = page.next_offset;
  }
  return items;
}

export interface DescribedApiError {
  status: number;
  code: string | null;
  message: string;
}

const CODE_MESSAGES: Record<string, string> = {
  AUTHENTICATION_REQUIRED: 'Sign in is required. The backend did not receive a login token.',
  INVALID_TOKEN: 'Your login session was not accepted by the backend. Sign in again.',
  FORBIDDEN: 'Your account role is not permitted to perform this action.',
  NOT_FOUND: 'The requested catalogue record was not found.',
  RELEASE_UNAVAILABLE: 'This catalogue release has been withdrawn and is no longer available.',
  READ_ONLY_RELEASE: 'This release is published and read-only. Decisions can only be recorded on a draft release.',
  STALE_REVISION: 'Someone else changed this mapping since you loaded it. It has been reloaded; review it and try again.',
  INVALID_TRANSITION: 'That decision is not a valid change from the current review state.',
  EVIDENCE_INCOMPLETE: 'Approval needs evidence for both endpoints and all three relationship roles. Approval is blocked.',
  RIGHTS_BLOCKED: 'Approval needs scoped metadata permission for all evidence. Approval is blocked pending rights.',
  INVALID_MAPPING: 'The backend rejected this record as an invalid topic-to-outcome mapping.',
  DATABASE_UNAVAILABLE: 'The catalogue database is unavailable. Try again later.',
};

/**
 * Normalises errors from the shared client. Domain errors arrive as {detail:{code,message}};
 * FastAPI validation errors as {detail:[{loc,msg,type}]}.
 */
export function describeApiError(err: unknown): DescribedApiError {
  if (!(err instanceof ApiError)) {
    return { status: -1, code: null, message: err instanceof Error ? err.message : 'Unexpected error.' };
  }
  if (err.status === 0) {
    return { status: 0, code: null, message: 'Could not reach the LumenEIOS backend. Check that the API server is running.' };
  }
  const detail = err.data?.detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail) && typeof detail.code === 'string') {
    return { status: err.status, code: detail.code, message: CODE_MESSAGES[detail.code] ?? detail.message ?? detail.code };
  }
  if (Array.isArray(detail)) {
    const msgs = detail.map((d: any) => [Array.isArray(d?.loc) ? d.loc.join('.') : null, d?.msg].filter(Boolean).join(': '));
    return { status: err.status, code: 'VALIDATION_ERROR', message: `The request was rejected: ${msgs.join('; ') || 'invalid input'}.` };
  }
  const message = typeof detail === 'string' ? detail : typeof err.message === 'string' && err.message !== '[object Object]' ? err.message : 'Request failed.';
  return { status: err.status, code: null, message };
}
