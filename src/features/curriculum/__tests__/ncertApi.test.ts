import { beforeEach, describe, expect, it } from 'vitest';
import { ApiError } from '../../../lib/apiClient';
import { createNcertApi, describeApiError, fetchAllPages } from '../api/ncertApi';
import { allowedDecisions } from '../api/contract';
import { citationToEvidence, reviewStateStatus, verificationStatus } from '../api/presentation';
import { citation, domainError, ids, installFetch, json, mapping, node, path, release, review } from './ncertTestHttp';

beforeEach(() => {
  localStorage.setItem('lumeneios_token', 'test-token');
});

describe('NCERT API adapter: routes and parameters match the contract', () => {
  it('GET /ncert/releases sends the bearer token and pagination parameters', async () => {
    const { calls } = installFetch(() => json(200, { items: [release()], next_offset: null }));
    const page = await createNcertApi().listReleases({ limit: 100, offset: 0 });
    expect(page.items[0].release_key).toBe('synthetic-draft');
    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe('GET');
    expect(path(calls[0])).toBe('/ncert/releases');
    expect(Object.fromEntries(calls[0].url.searchParams)).toEqual({ limit: '100', offset: '0' });
    expect(calls[0].headers.Authorization).toBe('Bearer test-token');
  });

  it('GET /ncert/subjects requires release_id and grade, passes language', async () => {
    const { calls } = installFetch(() => json(200, { items: [node()], next_offset: null }));
    await createNcertApi().listSubjects({ releaseId: ids.draft, grade: 7, language: 'hi' });
    expect(path(calls[0])).toBe('/ncert/subjects');
    expect(Object.fromEntries(calls[0].url.searchParams)).toEqual({ release_id: ids.draft, grade: '7', language: 'hi' });
  });

  it('GET /ncert/availability omits absent optional parameters', async () => {
    const empty = {
      grade: 6, requested_language: 'en', release: null, subject: null, status: 'NO_RELEASE_SELECTED', resources: [],
      missing_resource_types: ['FRAMEWORK', 'SYLLABUS', 'LEARNING_OUTCOMES', 'TEXTBOOK'], permissions_status: 'NOT_EVALUATED', applicability: 'UNVERIFIED',
    };
    const { calls } = installFetch(() => json(200, empty));
    const api = createNcertApi();
    const a = await api.getAvailability({ grade: 6 });
    expect(a.status).toBe('NO_RELEASE_SELECTED');
    expect(Object.fromEntries(calls[0].url.searchParams)).toEqual({ grade: '6' });

    await api.getAvailability({ grade: 8, releaseId: ids.draft, subjectIdentityId: ids.subjectIdentity, language: 'ur' });
    expect(path(calls[1])).toBe('/ncert/availability');
    expect(Object.fromEntries(calls[1].url.searchParams)).toEqual({
      grade: '8', release_id: ids.draft, subject_identity_id: ids.subjectIdentity, language: 'ur',
    });
  });

  it('GET /ncert/nodes/{id}, /ncert/mappings, /ncert/mappings/{id} and /reviews', async () => {
    const { calls } = installFetch((c) => {
      const p = path(c);
      if (p === `/ncert/nodes/${ids.subject}`) return json(200, node());
      if (p === '/ncert/mappings') return json(200, { items: [mapping()], next_offset: null });
      if (p === `/ncert/mappings/${ids.mapping}`) return json(200, mapping());
      if (p === `/ncert/mappings/${ids.mapping}/reviews`) return json(200, { items: [review()], next_offset: null });
    });
    const api = createNcertApi();
    await api.getNode(ids.subject, 'en');
    await api.listMappings({ releaseId: ids.draft, subjectNodeId: ids.subject, language: 'en', limit: 50, offset: 0 });
    await api.getMapping(ids.mapping, 'hi');
    await api.listReviews(ids.mapping, { limit: 100, offset: 0 });

    expect(calls.map((c) => `${c.method} ${path(c)}?${c.url.searchParams}`)).toEqual([
      `GET /ncert/nodes/${ids.subject}?language=en`,
      `GET /ncert/mappings?release_id=${ids.draft}&subject_node_id=${ids.subject}&language=en&limit=50&offset=0`,
      `GET /ncert/mappings/${ids.mapping}?language=hi`,
      `GET /ncert/mappings/${ids.mapping}/reviews?limit=100&offset=0`,
    ]);
  });

  it('POST /ncert/mappings/{id}/reviews sends exactly decision, trimmed rationale and expected_revision', async () => {
    const { calls } = installFetch(() => json(201, review({ revision: 3, decision: 'APPROVED' })));
    const r = await createNcertApi().submitReview(ids.mapping, {
      decision: 'APPROVED',
      rationale: '   Both endpoints checked against sources.  ',
      expected_revision: 2,
    });
    expect(r.revision).toBe(3);
    expect(calls[0].method).toBe('POST');
    expect(path(calls[0])).toBe(`/ncert/mappings/${ids.mapping}/reviews`);
    expect(calls[0].body).toEqual({ decision: 'APPROVED', rationale: 'Both endpoints checked against sources.', expected_revision: 2 });
    expect(calls[0].headers['Content-Type']).toBe('application/json');
  });

  it('validates a review request client-side before sending', async () => {
    const { calls } = installFetch(() => json(201, review()));
    const api = createNcertApi();
    await expect(api.submitReview(ids.mapping, { decision: 'REJECTED', rationale: ' short ', expected_revision: 0 })).rejects.toMatchObject({ status: 422 });
    await expect(api.submitReview(ids.mapping, { decision: 'REJECTED', rationale: 'x'.repeat(4001), expected_revision: 0 })).rejects.toMatchObject({ status: 422 });
    await expect(api.submitReview(ids.mapping, { decision: 'REJECTED', rationale: 'Long enough rationale', expected_revision: -1 })).rejects.toMatchObject({ status: 422 });
    expect(calls).toHaveLength(0);
  });

  it('follows next_offset across pages', async () => {
    const { calls } = installFetch((c) => {
      const offset = Number(c.url.searchParams.get('offset'));
      return json(200, offset === 0 ? { items: [release()], next_offset: 1 } : { items: [release({ id: ids.published, status: 'PUBLISHED' })], next_offset: null });
    });
    const api = createNcertApi();
    const all = await fetchAllPages((offset) => api.listReleases({ limit: 1, offset }));
    expect(all.map((r) => r.id)).toEqual([ids.draft, ids.published]);
    expect(calls).toHaveLength(2);
  });

  it('returns an empty release list as-is (no fabricated records)', async () => {
    installFetch(() => json(200, { items: [], next_offset: null }));
    expect(await createNcertApi().listReleases()).toEqual({ items: [], next_offset: null });
  });
});

describe('NCERT API adapter: errors', () => {
  it.each([
    [401, 'AUTHENTICATION_REQUIRED', /Sign in is required/],
    [401, 'INVALID_TOKEN', /not accepted/],
    [403, 'FORBIDDEN', /not permitted/],
    [404, 'NOT_FOUND', /not found/],
    [409, 'STALE_REVISION', /changed this mapping/],
    [409, 'INVALID_TRANSITION', /not a valid change/],
    [409, 'READ_ONLY_RELEASE', /published and read-only/],
    [409, 'RELEASE_UNAVAILABLE', /withdrawn/],
    [409, 'EVIDENCE_INCOMPLETE', /evidence/],
    [409, 'RIGHTS_BLOCKED', /rights/],
    [503, 'DATABASE_UNAVAILABLE', /unavailable/],
  ])('maps %s %s to a readable message', async (status, code, message) => {
    installFetch(() => domainError(status, code, 'backend message'));
    const err = await createNcertApi().getMapping(ids.mapping).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    const d = describeApiError(err);
    expect(d).toMatchObject({ status, code });
    expect(d.message).toMatch(message);
    expect(d.message).not.toContain('[object Object]');
  });

  it('formats FastAPI 422 validation errors', async () => {
    installFetch(() => json(422, { detail: [{ loc: ['query', 'grade'], msg: 'Input should be less than or equal to 8', type: 'less_than_equal' }] }));
    const err = await createNcertApi().listSubjects({ releaseId: ids.draft, grade: 9 }).catch((e) => e);
    expect(describeApiError(err)).toMatchObject({ status: 422, code: 'VALIDATION_ERROR' });
    expect(describeApiError(err).message).toContain('query.grade: Input should be less than or equal to 8');
  });

  it('reports network failures without falling back to mock data', async () => {
    (globalThis as any).fetch = () => Promise.reject(new TypeError('Failed to fetch'));
    const err = await createNcertApi().listReleases().catch((e) => e);
    expect(describeApiError(err)).toMatchObject({ status: 0 });
  });
});

describe('API presentation rules', () => {
  it('never maps unknown or AI-suggested verification to VERIFIED', () => {
    expect(verificationStatus('SOURCE_VERIFIED')).toBe('VERIFIED');
    expect(verificationStatus('AI_SUGGESTED')).toBe('AWAITING_REVIEW');
    expect(verificationStatus('SOMETHING_NEW')).toBe('UNVERIFIED');
    expect(reviewStateStatus('APPROVED')).toBe('APPROVED');
    expect(reviewStateStatus('UNKNOWN')).toBe('AWAITING_REVIEW');
  });

  it('marks redacted citations and keeps their values null', () => {
    const e = citationToEvidence(citation());
    expect(e.redacted).toBe(true);
    expect(e.sourceTitle).toBeNull();
    expect(e.officialUrl).toBeNull();
    expect(e.notes.join(' ')).toMatch(/not legal clearance/);
  });

  it('allows only the contract transitions', () => {
    expect(allowedDecisions('AWAITING_REVIEW')).toEqual(['APPROVED', 'REJECTED', 'REVISION_REQUESTED']);
    expect(allowedDecisions('REVISION_REQUESTED')).toEqual(['APPROVED', 'REJECTED']);
    expect(allowedDecisions('APPROVED')).toEqual(['REJECTED', 'REVISION_REQUESTED']);
    expect(allowedDecisions('REJECTED')).toEqual(['APPROVED', 'REVISION_REQUESTED']);
    expect(allowedDecisions('BOGUS')).toEqual([]);
  });
});
