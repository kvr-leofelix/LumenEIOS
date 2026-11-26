import { describe, expect, it } from 'vitest';
import { ApiError } from '../../../lib/apiClient';
import { validateReviewInput } from '../api/catalogueService';
import { createMockCatalogueService, type ReviewStore } from '../mocks/mockCatalogueService';
import snapshot from '../mocks/researchSnapshot.json';
import { knownOrNull, toDisplayStatus } from '../status';
import type { CatalogueActor } from '../api/catalogueService';

const admin: CatalogueActor = { name: 'Rajesh Kumar', role: 'admin' };
const principal: CatalogueActor = { name: 'Dr. Sunita Deshmukh', role: 'principal' };
const teacher: CatalogueActor = { name: 'Vikram Sengupta', role: 'teacher' };

const mock = (actor: CatalogueActor | null, store: ReviewStore = new Map()) =>
  createMockCatalogueService({ getActor: () => actor, latencyMs: 0, store });

describe('status mapping', () => {
  it('maps known research codes and never defaults unknown codes to VERIFIED', () => {
    expect(toDisplayStatus('DIRECT_FRONT_MATTER_VERIFIED')).toBe('VERIFIED');
    expect(toDisplayStatus('VISUAL_PRINTED_TITLE_AND_FIRST_EDITION_YEAR_VERIFIED; translation unresolved')).toBe('PARTIALLY_VERIFIED');
    expect(toDisplayStatus('NOT_FOUND_IN_CHECKED_NCERT_CHANNELS; publication status UNCONFIRMED')).toBe('PLACEHOLDER');
    expect(toDisplayStatus('AI_SUGGESTED')).toBe('AWAITING_REVIEW');
    expect(toDisplayStatus('SOMETHING_NEW_VERIFIED')).toBe('UNVERIFIED');
    expect(toDisplayStatus('')).toBe('UNVERIFIED');
  });

  it('treats UNVERIFIED literals as missing values', () => {
    expect(knownOrNull('UNVERIFIED')).toBeNull();
    expect(knownOrNull('  ')).toBeNull();
    expect(knownOrNull('UNVERIFIED_NATIVE_SCRIPT_TRANSCRIPTION')).toBeNull();
    expect(knownOrNull('UNVERIFIED; no matching assumed')).toBeNull();
    expect(knownOrNull('Ganita Prakash')).toBe('Ganita Prakash');
  });
});

describe('research snapshot fixture', () => {
  it('is a metadata-only snapshot with no stored outcome wording and no published release', () => {
    expect(snapshot.meta.kind).toBe('MOCK_RESEARCH_SNAPSHOT');
    expect(snapshot.meta.releaseId).toBeNull();
    expect(snapshot.crosswalk.every((m) => m.outcomeWordingStored === 'false')).toBe(true);
    expect(snapshot.crosswalk.every((m) => m.creationMethod === 'AI_SUGGESTED')).toBe(true);
  });
});

describe('mock catalogue service', () => {
  it('returns all six VI–VIII Mathematics/Science combinations', async () => {
    const data = await mock(principal).getDashboard();
    expect(data.meta.dataSource).toBe('mock');
    expect(data.combinations.map((c) => `${c.grade}-${c.subject}`)).toEqual([
      '6-mathematics', '6-science', '7-mathematics', '7-science', '8-mathematics', '8-science',
    ]);
    for (const c of data.combinations) {
      expect(c.counts.total).toBeGreaterThan(0);
      expect(c.counts.verified + c.counts.partiallyVerified + c.counts.unverified + c.counts.placeholder).toBe(c.counts.total);
    }
  });

  it('never presents a textbook title as a syllabus title', async () => {
    const detail = await mock(principal).getCombination(6, 'mathematics');
    const textbookTitles = new Set(detail.editions.map((e) => e.title).filter(Boolean));
    for (const s of detail.syllabi) {
      if (s.title) expect(textbookTitles.has(s.title)).toBe(false);
    }
    expect(detail.syllabi.some((s) => s.status === 'PLACEHOLDER' && s.title === null)).toBe(true);
  });

  it('exposes explicit gap rows for unidentified textbook parts', async () => {
    const detail = await mock(principal).getCombination(7, 'mathematics');
    const gap = detail.editions.find((e) => e.isGap);
    expect(gap).toBeDefined();
    expect(gap!.status).toBe('PLACEHOLDER');
    expect(gap!.title).toBeNull();
  });

  it('candidate mappings start unapproved', async () => {
    const list = await mock(principal).listCandidateMappings(8, 'science');
    expect(list.length).toBeGreaterThan(0);
    expect(list.every((m) => m.reviewerStatus === 'AWAITING_REVIEW' && m.verification === 'AWAITING_REVIEW')).toBe(true);
    expect(list.every((m) => !m.recoveryEligible)).toBe(true);
  });

  it('rejects review decisions from non-admin roles (simulated 403, contract: review is admin-only)', async () => {
    for (const actor of [teacher, principal]) {
      const [m] = await mock(actor).listCandidateMappings(6, 'mathematics');
      await expect(
        mock(actor).submitReview(m.id, { decision: 'APPROVED', rationale: 'Looks right to me.', expectedRevision: 0 })
      ).rejects.toMatchObject({ status: 403 });
    }
  });

  it('requires a rationale (simulated 422) and records valid decisions append-only with revisions', async () => {
    const store: ReviewStore = new Map();
    const svc = mock(admin, store);
    const [m] = await svc.listCandidateMappings(6, 'mathematics');
    expect(m.revision).toBe(0);
    await expect(svc.submitReview(m.id, { decision: 'REJECTED', rationale: 'short', expectedRevision: 0 })).rejects.toBeInstanceOf(ApiError);

    const revised = await svc.submitReview(m.id, { decision: 'REVISION_REQUESTED', rationale: 'Outcome scope needs narrowing first.', expectedRevision: 0 });
    expect(revised.reviewerStatus).toBe('REVISION_REQUESTED');
    expect(revised.revision).toBe(1);
    const approved = await svc.submitReview(m.id, { decision: 'APPROVED', rationale: 'Narrowed scope confirmed against both sources.', expectedRevision: 1 });
    expect(approved.reviewerStatus).toBe('APPROVED');
    expect(approved.reviews.map((r) => r.decision)).toEqual(['REVISION_REQUESTED', 'APPROVED']);
    expect(approved.reviews[1].reviewer).toBe(admin.name);
    expect(approved.recoveryEligible).toBe(false);

    const dashboard = await svc.getDashboard();
    const combo = dashboard.combinations.find((c) => c.grade === 6 && c.subject === 'mathematics')!;
    expect(combo.pendingReview).toBe(0);
  });

  it('mirrors backend 409s for stale revisions and repeated decisions', async () => {
    const svc = mock(admin);
    const [m] = await svc.listCandidateMappings(7, 'science');
    const body = { decision: 'REJECTED' as const, rationale: 'Evidence does not support this.' };
    await expect(svc.submitReview(m.id, { ...body, expectedRevision: 3 })).rejects.toMatchObject({ status: 409 });
    await svc.submitReview(m.id, { ...body, expectedRevision: 0 });
    await expect(svc.submitReview(m.id, { ...body, expectedRevision: 1 })).rejects.toMatchObject({ status: 409 });
  });

  it('denies access to roles outside the catalogue audience', async () => {
    await expect(mock({ name: 'Aarav', role: 'student' }).getDashboard()).rejects.toMatchObject({ status: 403 });
    await expect(mock(null).getDashboard()).rejects.toMatchObject({ status: 401 });
  });

  it('validateReviewInput enforces rationale length', () => {
    expect(validateReviewInput({ decision: 'APPROVED', rationale: '   ', expectedRevision: 0 })).toMatch(/rationale/);
    expect(validateReviewInput({ decision: 'APPROVED', rationale: 'x'.repeat(4001), expectedRevision: 0 })).toMatch(/at most 4000/);
    expect(validateReviewInput({ decision: 'APPROVED', rationale: 'Evidence on both ends agrees.', expectedRevision: 0 })).toBeNull();
  });
});
