/**
 * TEST-ONLY synthetic contract payloads and a fetch router. These are not catalogue data and are never
 * used at runtime; they exist to exercise the HTTP adapter against the contract's response shapes.
 */
import { vi } from 'vitest';
import type { CatalogueNode, Citation, Mapping, Release, Review } from '../api/contract';

export const API = 'http://localhost:8000/api/v1';

export const ids = {
  draft: '11111111-1111-4111-8111-111111111111',
  published: '22222222-2222-4222-8222-222222222222',
  subject: '33333333-3333-4333-8333-333333333333',
  subjectIdentity: '44444444-4444-4444-8444-444444444444',
  chapter: '55555555-5555-4555-8555-555555555555',
  topic: '66666666-6666-4666-8666-666666666666',
  outcome: '77777777-7777-4777-8777-777777777777',
  mapping: '88888888-8888-4888-8888-888888888888',
};

export const release = (over: Partial<Release> = {}): Release => ({
  id: ids.draft,
  release_key: 'synthetic-draft',
  edition: 'synthetic edition',
  academic_year: null,
  status: 'DRAFT',
  created_at: '2026-11-10T00:00:00Z',
  published_at: null,
  ...over,
});

export const citation = (over: Partial<Citation> = {}): Citation => ({
  evidence_id: 'ev-1',
  source_id: 'src-1',
  document_type: 'TEXTBOOK',
  source_verification: 'FULL_REVIEW',
  rights_status: 'PERMISSION_REQUIRED',
  metadata_visible: false,
  title: null,
  official_url: null,
  edition: null,
  language: 'en',
  locator: null,
  notes: null,
  ...over,
});

export const node = (over: Partial<CatalogueNode> = {}): CatalogueNode => ({
  id: ids.subject,
  identity_id: ids.subjectIdentity,
  release_id: ids.draft,
  parent_id: null,
  kind: 'SUBJECT',
  sequence: 1,
  grade_number: 6,
  title: 'Synthetic Subject',
  requested_language: 'en',
  resolved_language: 'en',
  translation_origin: null,
  verification: 'AWAITING_REVIEW',
  completeness: 'PARTIAL',
  citations: [],
  children: [],
  ...over,
});

export const review = (over: Partial<Review> = {}): Review => ({
  id: 'rev-1',
  relationship_id: ids.mapping,
  revision: 1,
  decision: 'REVISION_REQUESTED',
  rationale: 'Synthetic rationale for testing.',
  reviewer_id: 'user-admin',
  reviewed_at: '2026-11-10T10:00:00Z',
  ...over,
});

export const mapping = (over: Partial<Mapping> = {}): Mapping => ({
  id: ids.mapping,
  release_id: ids.draft,
  relationship_type: 'SHARED_LEARNING_OUTCOME',
  directionality: 'SYMMETRIC',
  source: node({ id: ids.topic, kind: 'TOPIC', title: 'Synthetic Topic', parent_id: ids.chapter }),
  destination: node({ id: ids.outcome, kind: 'LEARNING_OUTCOME', title: null, resolved_language: null }),
  verification: 'AI_SUGGESTED',
  creation_method: 'AI_SUGGESTED',
  curriculum_applicability: 'UNVERIFIED',
  publication_status: 'DRAFT',
  permissions_status: 'PENDING',
  evidence: [],
  rationale: null,
  overlapping_outcomes: null,
  uncovered_outcomes: null,
  coverage_assessment: null,
  human_review_state: 'AWAITING_REVIEW',
  revision: 0,
  latest_review: null,
  recovery_eligible: false,
  ...over,
});

export const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

export const domainError = (status: number, code: string, message = code) => json(status, { detail: { code, message } });

export interface Call {
  method: string;
  url: URL;
  body: any;
  headers: Record<string, string>;
}

type Handler = (call: Call) => Response | Promise<Response> | undefined;

/** Installs a fetch stub that routes requests to `handler` and records every call. */
export function installFetch(handler: Handler) {
  const calls: Call[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input));
    const call: Call = {
      method: (init.method ?? 'GET').toUpperCase(),
      url,
      body: init.body ? JSON.parse(String(init.body)) : undefined,
      headers: (init.headers ?? {}) as Record<string, string>,
    };
    calls.push(call);
    const res = await handler(call);
    if (!res) return json(500, { detail: `Unhandled test route ${call.method} ${url.pathname}` });
    return res;
  });
  (globalThis as any).fetch = fn;
  return { calls, fn };
}

export const path = (c: Call) => c.url.pathname.replace('/api/v1', '');
