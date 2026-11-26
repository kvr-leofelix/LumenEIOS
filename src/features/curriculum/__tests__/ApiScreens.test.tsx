import React from 'react';
import { beforeEach, describe, expect, it } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '../../../context/AuthContext';
import { initialUsers } from '../../../data/seedData';
import type { Role } from '../../../types';
import { CatalogueServiceProvider } from '../api/CatalogueServiceContext';
import { createNcertApi } from '../api/ncertApi';
import type { Mapping } from '../api/contract';
import { ApiSubjectPage as CatalogueCombinationPage } from '../pages/api/ApiSubjectPage';
import { ApiCatalogueDashboard as CatalogueDashboard } from '../pages/api/ApiCatalogueDashboard';
import { citation, domainError, ids, installFetch, json, mapping, node, path, release, review, type Call } from './ncertTestHttp';
import { signInAs as storeSession } from '../../../test/signIn';

function signInAs(role: Role) {
  const user = initialUsers.find((u) => u.role === role)!;
  storeSession(user);
  localStorage.setItem('lumeneios_token', `token-${role}`);
}

function renderApi(pathname: string) {
  return render(
    <MemoryRouter initialEntries={[pathname]}>
      <AuthProvider>
        <CatalogueServiceProvider api={createNcertApi()}>
          <Routes>
            <Route path="/curriculum/catalogue" element={<CatalogueDashboard />} />
            <Route path="/curriculum/catalogue/:grade/:subject" element={<CatalogueCombinationPage />} />
          </Routes>
        </CatalogueServiceProvider>
      </AuthProvider>
    </MemoryRouter>
  );
}

const subjectUrl = (view?: string) =>
  `/curriculum/catalogue/6/${ids.subject}?release=${ids.draft}&lang=en${view ? `&view=${view}` : ''}`;

beforeEach(() => localStorage.clear());

describe('API mode: dashboard', () => {
  it('shows an honest empty state for an empty release list and never claims verified data', async () => {
    signInAs('teacher');
    installFetch((c) => (path(c) === '/ncert/releases' ? json(200, { items: [], next_offset: null }) : undefined));
    renderApi('/curriculum/catalogue');
    expect(await screen.findByTestId('state-empty')).toHaveTextContent('No catalogue releases are visible to your account');
    expect(screen.getByTestId('data-source-banner')).toHaveTextContent(/backend API/);
    expect(screen.getByTestId('data-source-banner')).toHaveTextContent(/none selected/);
    // No release/subject records are rendered; the only "Verified" text is the status legend.
    expect(screen.queryAllByTestId(/^(release|subject)-/)).toHaveLength(0);
    expect(screen.getByTestId('state-empty')).not.toHaveTextContent(/verified|complete/i);
  });

  it('requires an explicit release choice, then lists subjects from the backend', async () => {
    signInAs('admin');
    const { calls } = installFetch((c) => {
      const p = path(c);
      if (p === '/ncert/releases')
        return json(200, { items: [release(), release({ id: ids.published, release_key: 'synthetic-published', status: 'PUBLISHED', published_at: '2026-11-01T00:00:00Z' })], next_offset: null });
      if (p === '/ncert/subjects') return json(200, { items: [node(), node({ id: 'subj-no-title', title: null, resolved_language: null })], next_offset: null });
    });
    const user = userEvent.setup();
    renderApi('/curriculum/catalogue');
    await screen.findByTestId(`release-${ids.draft}`);
    expect(calls.some((c) => path(c) === '/ncert/subjects')).toBe(false); // no silent latest-release selection
    expect(within(screen.getByTestId(`release-${ids.draft}`)).getByText('Draft (not published)')).toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: /synthetic-draft/ }));
    const link = await screen.findByTestId(`subject-${ids.subject}`);
    expect(link).toHaveAttribute('href', `/curriculum/catalogue/6/${ids.subject}?release=${ids.draft}&lang=en`);
    expect(screen.getByTestId('subject-subj-no-title')).toHaveTextContent('Subject title not available in English');
    const subjectsCall = calls.find((c) => path(c) === '/ncert/subjects')!;
    expect(subjectsCall.url.searchParams.get('release_id')).toBe(ids.draft);
    expect(subjectsCall.url.searchParams.get('grade')).toBe('6');

    await user.click(screen.getByRole('radio', { name: 'Class VIII' }));
    await waitFor(() => expect(calls.filter((c) => path(c) === '/ncert/subjects').at(-1)!.url.searchParams.get('grade')).toBe('8'));
  });

  it('shows the empty subjects state', async () => {
    signInAs('admin');
    installFetch((c) =>
      path(c) === '/ncert/releases' ? json(200, { items: [release()], next_offset: null }) : json(200, { items: [], next_offset: null })
    );
    renderApi(`/curriculum/catalogue?release=${ids.draft}&grade=7`);
    expect(await screen.findByText('No subjects are recorded for Class VII in this release')).toBeInTheDocument();
  });

  it.each([
    [401, 'INVALID_TOKEN', 'Sign in required'],
    [403, 'FORBIDDEN', 'You do not have access to this area'],
  ])('maps %s from the backend to the unauthorized state', async (status, code, title) => {
    signInAs('teacher');
    installFetch(() => domainError(status, code));
    renderApi('/curriculum/catalogue');
    // A 401 now also expires the shared session (the app then returns to sign-in), so the page may already show the no-access state.
    const text = status === 401 ? new RegExp(`${title}|You do not have access to this area`) : title;
    expect(await screen.findByTestId('state-unauthorized')).toHaveTextContent(text);
  });
});

describe('API mode: subject overview and explorer', () => {
  it('renders availability with missing types as placeholders and redacted evidence', async () => {
    signInAs('teacher');
    const { calls } = installFetch((c) => {
      const p = path(c);
      if (p === `/ncert/nodes/${ids.subject}`) return json(200, node());
      if (p === '/ncert/availability')
        return json(200, {
          grade: 6, requested_language: 'en', release: release(), subject: node(), status: 'PARTIAL',
          resources: [{ source_id: 'src-1', document_type: 'TEXTBOOK', language: 'en', rights_status: 'PERMISSION_REQUIRED', source_verification: 'FULL_REVIEW', citations: [citation()] }],
          missing_resource_types: ['FRAMEWORK', 'SYLLABUS', 'LEARNING_OUTCOMES'], permissions_status: 'PENDING', applicability: 'UNVERIFIED',
        });
    });
    const user = userEvent.setup();
    renderApi(subjectUrl());
    expect(await screen.findByRole('heading', { level: 1, name: 'Class VI Synthetic Subject' })).toBeInTheDocument();
    const status = await screen.findByTestId('availability-status');
    expect(status).toHaveTextContent('partial');
    expect(status).toHaveTextContent(/applicability: unverified/i);
    expect(status).toHaveTextContent(/do not show whether the official publication is complete/);
    for (const t of ['FRAMEWORK', 'SYLLABUS', 'LEARNING_OUTCOMES']) {
      expect(screen.getByTestId(`missing-${t}`)).toHaveTextContent('Placeholder');
    }
    expect(screen.getByTestId('resource-src-1')).toHaveTextContent('Title redacted pending rights clearance');

    const call = calls.find((c) => path(c) === '/ncert/availability')!;
    expect(Object.fromEntries(call.url.searchParams)).toEqual({
      grade: '6', release_id: ids.draft, subject_identity_id: ids.subjectIdentity, language: 'en',
    });

    await user.click(within(screen.getByTestId('resource-src-1')).getByRole('button', { name: /View evidence/ }));
    const dialog = screen.getByRole('dialog', { name: 'Source evidence' });
    expect(within(dialog).getByTestId('evidence-redacted')).toBeInTheDocument();
    expect(dialog).toHaveTextContent('FULL_REVIEW');
    expect(dialog).toHaveTextContent('PERMISSION_REQUIRED');
  });

  it('shows SUBJECT_NOT_FOUND honestly', async () => {
    signInAs('teacher');
    installFetch((c) =>
      path(c) === '/ncert/availability'
        ? json(200, { grade: 6, requested_language: 'en', release: release(), subject: null, status: 'SUBJECT_NOT_FOUND', resources: [], missing_resource_types: ['FRAMEWORK', 'SYLLABUS', 'LEARNING_OUTCOMES', 'TEXTBOOK'], permissions_status: 'NOT_EVALUATED', applicability: 'UNVERIFIED' })
        : json(200, node())
    );
    renderApi(subjectUrl());
    expect(await screen.findByTestId('availability-status')).toHaveTextContent('not found for this class');
  });

  it('shows a not-found state for a 404 subject', async () => {
    signInAs('teacher');
    installFetch(() => domainError(404, 'NOT_FOUND'));
    renderApi(subjectUrl());
    expect(await screen.findByTestId('state-not-found')).toBeInTheDocument();
  });

  it('explores the hierarchy one level at a time without inventing children', async () => {
    signInAs('teacher');
    const chapter = node({ id: ids.chapter, kind: 'CHAPTER', sequence: 1, title: 'Synthetic Chapter', parent_id: ids.subject });
    installFetch((c) => {
      const p = path(c);
      if (p === `/ncert/nodes/${ids.subject}`) return json(200, node({ children: [chapter] }));
      if (p === `/ncert/nodes/${ids.chapter}`) return json(200, { ...chapter, children: [] });
    });
    const user = userEvent.setup();
    renderApi(subjectUrl('explorer'));
    const row = await screen.findByTestId(`node-${ids.chapter}`);
    await user.click(within(row).getByRole('button', { name: /Open Chapter Synthetic Chapter/ }));
    expect(await screen.findByText('No records are stored under this chapter')).toBeInTheDocument();
    expect(screen.getByTestId('explorer-current')).toHaveTextContent('Synthetic Chapter');
  });
});

describe('API mode: mapping review', () => {
  function reviewServer(initial: Mapping, onPost?: (c: Call) => Response) {
    let current = initial;
    const history: ReturnType<typeof review>[] = [];
    const handle = installFetch((c) => {
      const p = path(c);
      if (p === `/ncert/nodes/${ids.subject}`) return json(200, node());
      if (p === '/ncert/mappings') return json(200, { items: [current], next_offset: null });
      if (p === `/ncert/mappings/${ids.mapping}`) return json(200, current);
      if (p === `/ncert/mappings/${ids.mapping}/reviews` && c.method === 'GET') return json(200, { items: history, next_offset: null });
      if (p === `/ncert/mappings/${ids.mapping}/reviews` && c.method === 'POST') {
        if (onPost) return onPost(c);
        const r = review({ id: `rev-${history.length + 1}`, revision: current.revision + 1, decision: c.body.decision, rationale: c.body.rationale });
        history.push(r);
        current = { ...current, revision: r.revision, human_review_state: r.decision, latest_review: r };
        return json(201, r);
      }
    });
    return { ...handle, setCurrent: (m: Mapping) => (current = m) };
  }

  it('persists a decision with expected_revision and rationale, then refetches mapping and history', async () => {
    signInAs('admin');
    const { calls } = reviewServer(mapping({ revision: 0 }));
    const user = userEvent.setup();
    renderApi(subjectUrl('review'));

    const card = await screen.findByTestId(`api-mapping-${ids.mapping}`);
    expect(card).toHaveTextContent('AI-suggested mapping. Not approved.');
    expect(card).toHaveTextContent('Learning outcome title not available in English');
    expect(card).toHaveTextContent(/Free text stays hidden/);
    expect(within(card).getAllByText('Awaiting review').length).toBeGreaterThanOrEqual(1);

    await user.click(within(card).getByRole('button', { name: 'Request revision' }));
    const modal = screen.getByRole('dialog', { name: /Request revision candidate mapping/ });
    await user.click(within(modal).getByRole('button', { name: 'Record decision' }));
    expect(within(modal).getByRole('alert')).toHaveTextContent(/rationale/);
    expect(calls.some((c) => c.method === 'POST')).toBe(false);

    await user.type(within(modal).getByLabelText(/Decision rationale/), '  Outcome scope is broader than the topic.  ');
    await user.click(within(modal).getByRole('button', { name: 'Record decision' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: /candidate mapping/ })).not.toBeInTheDocument());

    const post = calls.find((c) => c.method === 'POST')!;
    expect(path(post)).toBe(`/ncert/mappings/${ids.mapping}/reviews`);
    expect(post.body).toEqual({ decision: 'REVISION_REQUESTED', rationale: 'Outcome scope is broader than the topic.', expected_revision: 0 });
    const postIndex = calls.indexOf(post);
    expect(calls.slice(postIndex + 1).some((c) => c.method === 'GET' && path(c) === `/ncert/mappings/${ids.mapping}`)).toBe(true);

    const updated = screen.getByTestId(`api-mapping-${ids.mapping}`);
    expect(within(updated).getByText('Revision requested')).toBeInTheDocument();
    expect(screen.getByTestId('review-announcement')).toHaveTextContent('Revision requested recorded as revision 1');
    // Same decision again is not an allowed transition, so it is not offered.
    expect(within(updated).queryByRole('button', { name: 'Request revision' })).not.toBeInTheDocument();
    expect(within(updated).getByRole('button', { name: 'Approve' })).toBeInTheDocument();
    await user.click(within(updated).getByRole('button', { name: 'Show review history' }));
    expect(await screen.findByTestId(`history-${ids.mapping}`)).toHaveTextContent('Revision 1: Revision requested');
  });

  it('offers only allowed transitions (no repeat of the current decision)', async () => {
    signInAs('admin');
    reviewServer(mapping({ human_review_state: 'APPROVED', revision: 2 }));
    renderApi(subjectUrl('review'));
    const card = await screen.findByTestId(`api-mapping-${ids.mapping}`);
    expect(within(card).queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    expect(within(card).getByRole('button', { name: 'Reject' })).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: 'Request revision' })).toBeInTheDocument();
  });

  it('handles 409 STALE_REVISION by reloading the mapping and keeping the dialog open', async () => {
    signInAs('admin');
    const server = reviewServer(mapping({ revision: 0 }), () => {
      server.setCurrent(mapping({ revision: 1, human_review_state: 'REJECTED' }));
      return domainError(409, 'STALE_REVISION');
    });
    const user = userEvent.setup();
    renderApi(subjectUrl('review'));
    const card = await screen.findByTestId(`api-mapping-${ids.mapping}`);
    await user.click(within(card).getByRole('button', { name: 'Approve' }));
    const modal = screen.getByRole('dialog', { name: /Approve candidate mapping/ });
    await user.type(within(modal).getByLabelText(/Decision rationale/), 'Both endpoints were checked.');
    await user.click(within(modal).getByRole('button', { name: 'Record decision' }));
    expect(await within(modal).findByRole('alert')).toHaveTextContent(/changed this mapping/);
    expect(modal).toHaveTextContent('revision 1');
    expect(within(screen.getByTestId(`api-mapping-${ids.mapping}`)).getByText('Rejected')).toBeInTheDocument();
  });

  it.each([
    [409, 'EVIDENCE_INCOMPLETE', /Approval is blocked/],
    [409, 'RIGHTS_BLOCKED', /pending rights/],
    [403, 'FORBIDDEN', /Not permitted/],
    [404, 'NOT_FOUND', /not found/],
  ])('shows %s %s inside the decision dialog without changing state', async (status, code, msg) => {
    signInAs('admin');
    reviewServer(mapping(), () => domainError(status, code));
    const user = userEvent.setup();
    renderApi(subjectUrl('review'));
    const card = await screen.findByTestId(`api-mapping-${ids.mapping}`);
    await user.click(within(card).getByRole('button', { name: 'Approve' }));
    const modal = screen.getByRole('dialog', { name: /Approve candidate mapping/ });
    await user.type(within(modal).getByLabelText(/Decision rationale/), 'Both endpoints were checked.');
    await user.click(within(modal).getByRole('button', { name: 'Record decision' }));
    expect(await within(modal).findByRole('alert')).toHaveTextContent(msg);
    expect(within(screen.getByTestId(`api-mapping-${ids.mapping}`)).queryByText('Approved')).not.toBeInTheDocument();
  });

  it('teachers and principals are view-only; published releases are read-only for admins', async () => {
    signInAs('principal');
    reviewServer(mapping());
    const { unmount } = renderApi(subjectUrl('review'));
    const card = await screen.findByTestId(`api-mapping-${ids.mapping}`);
    expect(within(card).queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    expect(card).toHaveTextContent(/Only an administrator/);
    unmount();

    signInAs('admin');
    reviewServer(mapping({ publication_status: 'PUBLISHED' }));
    renderApi(subjectUrl('review'));
    const pub = await screen.findByTestId(`api-mapping-${ids.mapping}`);
    expect(within(pub).queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    expect(pub).toHaveTextContent(/only be recorded on a draft release/);
  });

  it('shows an empty state when the backend returns no mappings', async () => {
    signInAs('admin');
    installFetch((c) => (path(c) === '/ncert/mappings' ? json(200, { items: [], next_offset: null }) : json(200, node())));
    renderApi(subjectUrl('review'));
    expect(await screen.findByText('No topic-to-outcome mappings are recorded for this subject in this release')).toBeInTheDocument();
  });
});
