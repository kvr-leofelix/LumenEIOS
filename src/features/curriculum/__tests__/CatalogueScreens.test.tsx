/**
 * The Curriculum Catalogue: SELECT CLASS -> SELECT SUBJECT -> the full available syllabus with teaching coverage.
 * Rendered through the real App so the existing routes, sidebar and planning store are exercised together.
 * (The earlier verification/review screens were retired from the catalogue; see docs/COURSE_CURRICULUM_IMPLEMENTATION.md.)
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../../../context/AuthContext';
import { DataProvider } from '../../../context/DataContext';
import { initialUsers } from '../../../data/seedData';
import { App } from '../../../App';
import { EMPTY_WORKSPACE, LOCAL_KEY, type Workspace } from '../../../lib/planning/store';
import { defaultDatasetFor, syllabusFor, validateImport, VERIFIED_DATASET } from '../../../lib/planning/syllabus';
import { setCoverage } from '../../../lib/planning/coverage';

vi.mock('../../../lib/teacherPlanApi', async (orig) => {
  const real = await orig<typeof import('../../../lib/teacherPlanApi')>();
  const { makeFakeTeacherPlanApi } = await import('../../../test/fakeTeacherPlanApi');
  return { ...real, teacherPlanApi: makeFakeTeacherPlanApi() };
});
import { fakeStore } from '../../../test/fakeTeacherPlanApi';
import { signInAs } from '../../../test/signIn';

function open(path: string, role = 'teacher') {
  signInAs(initialUsers.find((u) => u.role === role));
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <DataProvider>
          <App />
        </DataProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}
const stored = (): Workspace => JSON.parse(localStorage.getItem(LOCAL_KEY)!);
const topicRows = () => screen.queryAllByTestId(/^topic-/);
const chapterBoxes = () => screen.queryAllByTestId(/^chapter-(?!status-|count-)/);
const expandAll = () => fireEvent.click(screen.getByRole('button', { name: 'Expand all' }));
const BANNED = /unverified|inferred|partial|review required|draft|approved|published|pending|permission required|verified|source-checked|awaiting/i;

beforeEach(() => {
  localStorage.clear();
  fakeStore.reset();
});
afterEach(() => cleanup());

describe('Curriculum Catalogue: select class -> select subject -> syllabus', () => {
  it('keeps the existing route and sidebar entry, and adds no new page, route or navigation item', () => {
    open('/curriculum/catalogue');
    expect(screen.getByRole('heading', { level: 1, name: 'Curriculum Catalogue' })).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: /Curriculum Catalogue/ }).length).toBeGreaterThan(0);
    expect(screen.queryByRole('link', { name: /Course Curriculum/ })).toBeNull();
    cleanup();
    open('/curriculum/course');
    expect(screen.queryByTestId('curriculum-catalogue')).toBeNull(); // no such route
  });

  it('shows header copy, the single demonstration notice and only the class choice first', () => {
    open('/curriculum/catalogue');
    expect(screen.getByText('Explore the syllabus and track teaching coverage.')).toBeInTheDocument();
    expect(screen.getByTestId('demo-notice')).toHaveTextContent(/^Demonstration syllabus and coverage data\.$/);
    for (const c of ['Class VI', 'Class VII', 'Class VIII']) expect(screen.getByRole('button', { name: c })).toBeInTheDocument();
    expect(screen.getByText('Choose a class first.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Mathematics' })).toBeNull();
    expect(screen.queryByTestId('syllabus-view')).toBeNull();
  });

  it('class, then subject, then the full syllabus with overview counts', () => {
    open('/curriculum/catalogue');
    fireEvent.click(screen.getByRole('button', { name: 'Class VI' }));
    expect(screen.getByRole('button', { name: 'Mathematics' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Science' })).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('combo-6-mathematics'));
    const view = screen.getByTestId('syllabus-view');
    expect(within(view).getByRole('heading', { name: 'Class VI · Mathematics' })).toBeInTheDocument();
    const units = syllabusFor(VERIFIED_DATASET, 6, 'Mathematics').units;
    expect(screen.getByTestId('coverage-total')).toHaveTextContent(String(units.length));
    expect(screen.getByTestId('coverage-done')).toHaveTextContent('0');
    expect(screen.getByTestId('coverage-inprogress')).toHaveTextContent('0');
    expect(screen.getByTestId('coverage-notdone')).toHaveTextContent(String(units.length));
    expect(screen.getByTestId('coverage-percent')).toHaveTextContent('0%');
    expect(screen.getByRole('progressbar', { name: 'Syllabus coverage' })).toHaveAttribute('aria-valuenow', '0');
  });

  it('every class and subject opens its full syllabus; the selector switches without leaving the page', () => {
    for (const grade of [6, 7, 8]) {
      for (const subject of ['mathematics', 'science'] as const) {
        const view = open(`/curriculum/catalogue/${grade}/${subject}`);
        const expected = syllabusFor(VERIFIED_DATASET, grade, subject === 'science' ? 'Science' : 'Mathematics');
        expect(chapterBoxes()).toHaveLength(expected.chapters.length);
        expect(screen.getByTestId('coverage-total')).toHaveTextContent(String(expected.units.length));
        view.unmount();
      }
    }
    open('/curriculum/catalogue/6/mathematics');
    fireEvent.click(screen.getByRole('radio', { name: 'Class VIII' }));
    expect(screen.getByRole('heading', { name: 'Class VIII · Mathematics' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: 'Science' }));
    expect(screen.getByRole('heading', { name: 'Class VIII · Science' })).toBeInTheDocument();
  });

  it('an unknown class or subject falls back to the catalogue start; students are not authorised', () => {
    open('/curriculum/catalogue/9/art');
    expect(screen.getByText('Choose a class first.')).toBeInTheDocument();
    cleanup();
    open('/curriculum/catalogue/6/mathematics', 'student');
    expect(screen.queryByTestId('syllabus-view')).toBeNull();
    expect(screen.queryByLabelText(/^Coverage status/)).toBeNull();
    cleanup();
    open('/curriculum/catalogue', 'student');
    expect(screen.queryByRole('button', { name: 'Class VI' })).toBeNull();
  });

  it('every available chapter is listed; chapters expand and collapse to reveal every topic', () => {
    open('/curriculum/catalogue/7/mathematics');
    const expected = syllabusFor(VERIFIED_DATASET, 7, 'Mathematics');
    expect(chapterBoxes()).toHaveLength(expected.chapters.length);
    expect(topicRows()).toHaveLength(0);
    const toggle = within(chapterBoxes()[0]).getByRole('button');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(topicRows().length).toBeGreaterThan(0);
    fireEvent.click(toggle);
    expect(topicRows()).toHaveLength(0);
    expandAll();
    expect(topicRows()).toHaveLength(expected.units.length);
    for (const u of expected.units) expect(screen.getByTestId(`topic-${u.id}`)).toHaveTextContent(u.title);
    fireEvent.click(screen.getByRole('button', { name: 'Collapse all' }));
    expect(topicRows()).toHaveLength(0);
  });

  it('shows no source-quality, verification, approval or publication wording in the catalogue content', () => {
    open('/curriculum/catalogue');
    expect(screen.getByTestId('curriculum-catalogue').textContent).not.toMatch(BANNED);
    cleanup();
    open('/curriculum/catalogue/7/mathematics');
    expandAll();
    const chrome = [
      screen.getByRole('heading', { level: 1 }).textContent,
      screen.getByTestId('demo-notice').textContent,
      screen.getByTestId('coverage-overview').textContent,
      ...screen.getAllByRole('radiogroup').map((g) => g.textContent),
      ...within(screen.getAllByLabelText(/^Coverage status/)[0]).getAllByRole('option').map((o) => o.textContent),
    ].join(' ');
    expect(chrome).not.toMatch(BANNED);
    // the old review controls are gone
    expect(screen.queryByRole('tab')).toBeNull();
    expect(screen.queryByRole('button', { name: /review|approve|publish|verify|evidence/i })).toBeNull();
  });
});

describe('inline coverage status in the catalogue', () => {
  const firstSelect = () => screen.getAllByLabelText(/^Coverage status/)[0] as HTMLSelectElement;

  it('offers exactly Done, Not done and In progress', () => {
    open('/curriculum/catalogue/6/mathematics');
    expandAll();
    expect(within(firstSelect()).getAllByRole('option').map((o) => o.textContent)).toEqual(['Done', 'Not done', 'In progress']);
  });

  it('changes colour with each status, updates counts and percentage immediately, and persists', async () => {
    const view = open('/curriculum/catalogue/7/mathematics');
    const units = syllabusFor(VERIFIED_DATASET, 7, 'Mathematics').units;
    expandAll();
    const target = units[0];
    const dot = () => screen.getByTestId(`dot-${target.id}`);
    const select = () => within(screen.getByTestId(`topic-${target.id}`)).getByLabelText(/^Coverage status/) as HTMLSelectElement;
    expect(dot()).toHaveStyle({ backgroundColor: '#9CA3AF' });

    fireEvent.change(select(), { target: { value: 'IN_PROGRESS' } });
    await waitFor(() => expect(dot()).toHaveAttribute('data-status', 'IN_PROGRESS'));
    expect(dot()).toHaveStyle({ backgroundColor: '#F59E0B' });
    expect(screen.getByTestId('coverage-inprogress')).toHaveTextContent('1');
    expect(screen.getByTestId('coverage-percent')).toHaveTextContent('0%');

    fireEvent.change(select(), { target: { value: 'DONE' } });
    await waitFor(() => expect(dot()).toHaveAttribute('data-status', 'DONE'));
    expect(dot()).toHaveStyle({ backgroundColor: '#16A34A' });
    expect(screen.getByTestId('coverage-done')).toHaveTextContent('1');
    expect(screen.getByTestId('coverage-notdone')).toHaveTextContent(String(units.length - 1));
    expect(screen.getByTestId('coverage-percent')).toHaveTextContent(`${Math.round((1 / units.length) * 1000) / 10}%`);

    fireEvent.change(select(), { target: { value: 'NOT_DONE' } });
    await waitFor(() => expect(dot()).toHaveAttribute('data-status', 'NOT_DONE'));
    expect(dot()).toHaveStyle({ backgroundColor: '#9CA3AF' });

    // every change reached the relational store, in order, attributed to the signed-in teacher, as MANUAL
    expect(fakeStore.events.map((e) => [e.teacher, e.to, e.source])).toEqual([
      ['user-teacher-1', 'in_progress', 'MANUAL'],
      ['user-teacher-1', 'done', 'MANUAL'],
      ['user-teacher-1', 'not_done', 'MANUAL'],
    ]);
    // and nothing was written to the workspace document
    expect(JSON.parse(localStorage.getItem(LOCAL_KEY) ?? '{}').coverage ?? {}).toEqual({});

    fireEvent.change(select(), { target: { value: 'DONE' } });
    await waitFor(() => expect(dot()).toHaveAttribute('data-status', 'DONE'));
    view.unmount();
    open('/curriculum/catalogue/7/mathematics');
    await waitFor(() => expect(screen.getByTestId('coverage-done')).toHaveTextContent('1')); // reloaded from the store, not memory
    expandAll();
    expect(screen.getByTestId(`dot-${target.id}`)).toHaveAttribute('data-status', 'DONE');
  });

  it('every teachable topic shows a saved Core/Non-Core control and a coverage control; a classification change persists per teacher', async () => {
    const units = syllabusFor(VERIFIED_DATASET, 7, 'Mathematics').units;
    for (const u of units) fakeStore.preload('user-teacher-1', u.id.replace('CH-', 'XW-'), 'not_done', 'MANUAL'); // the plan's persisted rows
    const view = open('/curriculum/catalogue/7/mathematics');
    expandAll();
    await waitFor(() => expect(screen.getAllByLabelText(/^Core or Non-Core for/)).toHaveLength(units.length));
    expect(screen.getAllByLabelText(/^Coverage status for/)).toHaveLength(units.length);
    expect(screen.queryAllByTestId(/^unconfigured-/)).toHaveLength(0);
    expect(screen.getByTestId('plan-context')).toHaveTextContent(/Class VII \(grade 7\) · Mathematics/);
    expect(document.body.textContent).not.toMatch(/planning baseline|not reviewed|planning default|default classification|seeded configuration|demo default/i);
    const sel = () => within(screen.getByTestId(`topic-${units[0].id}`)).getByLabelText(/^Core or Non-Core for/) as HTMLSelectElement;
    fireEvent.change(sel(), { target: { value: 'non_core' } });
    await waitFor(() => expect(sel().value).toBe('non_core'));
    expect(screen.getByTestId('saved-note')).toBeInTheDocument();
    expect(fakeStore.classes.get('user-teacher-1')?.get(units[0].id.replace('CH-', 'XW-'))).toMatchObject({ classification: 'non_core', core: 0, non: 2 });
    view.unmount();
    open('/curriculum/catalogue/7/mathematics');
    expandAll();
    await waitFor(() => expect(sel().value).toBe('non_core')); // reloaded from the store
  });

  it('chapter status is calculated: mixture is In progress, all Done is Done, none is Not done', async () => {
    open('/curriculum/catalogue/7/mathematics');
    const view = syllabusFor(VERIFIED_DATASET, 7, 'Mathematics');
    const chapterId = view.units[0].parentId!;
    const inChapter = view.units.filter((u) => u.parentId === chapterId);
    const status = () => screen.getByTestId(`chapter-status-${chapterId}`);
    expect(status()).toHaveAttribute('data-status', 'NOT_DONE');
    expandAll();
    const set = async (id: string, value: string) => {
      fireEvent.change(within(screen.getByTestId(`topic-${id}`)).getByLabelText(/^Coverage status/), { target: { value } });
      await waitFor(() => expect(screen.getByTestId(`dot-${id}`)).toHaveAttribute('data-status', value));
    };
    await set(inChapter[0].id, 'DONE');
    expect(status()).toHaveAttribute('data-status', inChapter.length === 1 ? 'DONE' : 'IN_PROGRESS');
    for (const u of inChapter.slice(1)) await set(u.id, 'DONE');
    expect(status()).toHaveAttribute('data-status', 'DONE');
    expect(screen.getByTestId(`chapter-count-${chapterId}`)).toHaveTextContent(`${inChapter.length} of ${inChapter.length}`);
    await set(inChapter[0].id, 'IN_PROGRESS');
    expect(status()).toHaveAttribute('data-status', 'IN_PROGRESS');
  });

  it('missing approved period requirements never hide a topic', () => {
    open('/curriculum/catalogue/8/science');
    expandAll();
    const units = syllabusFor(VERIFIED_DATASET, 8, 'Science').units;
    expect(units.length).toBeGreaterThan(0);
    expect(topicRows()).toHaveLength(units.length);
  });

  it('labels manual coverage as separate from recorded classroom teaching', () => {
    const topic = syllabusFor(VERIFIED_DATASET, 6, 'Mathematics').units[0];
    fakeStore.preload('user-teacher-1', topic.id, 'done', 'MANUAL');
    open('/curriculum/catalogue/6/mathematics');
    expandAll();
    return waitFor(() => expect(within(screen.getByTestId(`topic-${topic.id}`)).getByText(/Manual coverage · no classroom periods recorded\./)).toBeInTheDocument());
  });
});

describe('permissions', () => {
  it('only the owning teacher edits; principals and admins see read-only coverage', async () => {
    open('/curriculum/catalogue/6/mathematics', 'principal');
    expandAll();
    expect(screen.getAllByLabelText(/^Coverage status/)[0]).toBeDisabled();
    expect(screen.getByText('Coverage is read-only: only the owning teacher can change it.')).toBeInTheDocument();
    cleanup();
    open('/curriculum/catalogue/6/mathematics', 'admin');
    expandAll();
    expect(screen.getAllByLabelText(/^Coverage status/)[0]).toBeDisabled();
    cleanup();
    open('/curriculum/catalogue/6/mathematics', 'teacher');
    expandAll();
    await waitFor(() => expect(screen.getAllByLabelText(/^Coverage status/)[0]).toBeEnabled());
  });

  it('a Principal opening ?teacher=<id> sees that teacher’s coverage, read-only, and another teacher’s stays separate', async () => {
    const topic = syllabusFor(VERIFIED_DATASET, 6, 'Mathematics').units[0];
    fakeStore.preload('user-teacher-2', topic.id, 'done');
    open(`/curriculum/catalogue/6/mathematics?teacher=user-teacher-2`, 'principal');
    expandAll();
    await waitFor(() => expect(screen.getByTestId(`dot-${topic.id}`)).toHaveAttribute('data-status', 'DONE'));
    expect(screen.getAllByLabelText(/^Coverage status/)[0]).toBeDisabled();
    cleanup();
    open('/curriculum/catalogue/6/mathematics', 'teacher'); // user-teacher-1: untouched
    expandAll();
    await waitFor(() => expect(screen.getByTestId('coverage-done')).toHaveTextContent('0'));
  });
});

describe('data shape: resources, parent headings and the same topics as the Time-Aware Engine', () => {
  const json = JSON.stringify({
    label: 'Fixture syllabus',
    textbooks: [{ id: 'tb', grade: 6, subject: 'Mathematics', title: 'Fixture Book', edition: 'E1' }],
    nodes: [
      { id: 'c1', textbookId: 'tb', kind: 'CHAPTER', number: '1', title: 'Fixture Chapter', sourceLocator: 'p1' },
      { id: 't1', textbookId: 'tb', kind: 'TOPIC', parentId: 'c1', number: '1.1', title: 'Parent Heading', sourceLocator: 'p2' },
      { id: 's1', textbookId: 'tb', kind: 'SUBTOPIC', parentId: 't1', number: '1.1.1', title: 'Sub Alpha', sourceLocator: 'p3' },
      { id: 's2', textbookId: 'tb', kind: 'SUBTOPIC', parentId: 't1', number: '1.1.2', title: 'Sub Beta', sourceLocator: 'p4' },
      { id: 'a1', textbookId: 'tb', kind: 'ACTIVITY', parentId: 's1', title: 'Fold the paper activity', sourceLocator: 'p3' },
      { id: 'x1', textbookId: 'tb', kind: 'EXERCISE', parentId: 's2', title: 'Exercise set one', sourceLocator: 'p4' },
      { id: 't2', textbookId: 'tb', kind: 'TOPIC', parentId: 'c1', number: '1.2', title: 'Leaf Topic', sourceLocator: 'p5' },
    ],
  });
  const seed = () => {
    const ds = validateImport(json, [], 'Admin').dataset!;
    localStorage.setItem(LOCAL_KEY, JSON.stringify({ ...EMPTY_WORKSPACE, datasets: [ds] }));
    return ds;
  };

  it('counts only teachable topics once: resources and parent headings are not coverage topics', () => {
    seed();
    open('/curriculum/catalogue/6/mathematics');
    expect(screen.getByTestId('coverage-total')).toHaveTextContent('3');
    expandAll();
    expect(screen.getByText(/Sub Alpha/)).toBeInTheDocument();
    expect(screen.getByText(/Sub Beta/)).toBeInTheDocument();
    expect(screen.getByText(/Leaf Topic/)).toBeInTheDocument();
    expect(screen.getByText(/Parent Heading/)).toBeInTheDocument();
    expect(within(screen.getByTestId('topic-t1')).queryByLabelText(/^Coverage status/)).toBeNull();
    expect(screen.getAllByLabelText(/^Coverage status/)).toHaveLength(3);
    expect(screen.queryByText(/Fold the paper activity|Exercise set one/)).toBeNull();
  });

  it('the catalogue and the Time-Aware Engine show the same topics; scheduling data never marks coverage', async () => {
    const ds = seed();
    expect(defaultDatasetFor([VERIFIED_DATASET, ds], 6, 'Mathematics').id).toBe(ds.id);
    const titles = syllabusFor(ds, 6, 'Mathematics').units.map((u) => u.title);
    expect(titles).toEqual(['Sub Alpha', 'Sub Beta', 'Leaf Topic']);

    const catalogue = open('/curriculum/catalogue/6/mathematics');
    expandAll();
    const catalogueTopics = topicRows().map((r) => r.getAttribute('data-testid'));
    catalogue.unmount();

    open('/teacher/time-aware');
    fireEvent.change(screen.getByLabelText('Class'), { target: { value: '6' } });
    fireEvent.change(screen.getByLabelText('Subject'), { target: { value: 'Mathematics' } });
    const table = await screen.findByRole('table', { name: 'Topic requirements' });
    for (const t of titles) expect(within(table).getByText(new RegExp(t))).toBeInTheDocument();
    expect(within(table).queryByText(/Fold the paper activity|Exercise set one|Parent Heading/)).toBeNull();
    expect(catalogueTopics).toEqual(['topic-t1', 'topic-s1', 'topic-s2', 'topic-t2']);
    // the engine shows each topic's coverage read-only, and a generated schedule leaves it Not done
    for (const id of ['s1', 's2', 't2']) expect(screen.getByTestId(`req-status-${id}`)).toHaveTextContent('Not started');
    expect(JSON.parse(localStorage.getItem(LOCAL_KEY)!).coverage ?? {}).toEqual({});
  });

  it('coverage set in the catalogue appears beside the same topic in the Time-Aware Engine', async () => {
    const ds = seed();
    const catalogue = open('/curriculum/catalogue/6/mathematics');
    expandAll();
    fireEvent.change(within(screen.getByTestId('topic-s2')).getByRole('combobox'), { target: { value: 'IN_PROGRESS' } });
    await waitFor(() => expect(screen.getByTestId('dot-s2')).toHaveAttribute('data-status', 'IN_PROGRESS'));
    catalogue.unmount();
    open('/teacher/time-aware');
    fireEvent.change(screen.getByLabelText('Class'), { target: { value: '6' } });
    fireEvent.change(screen.getByLabelText('Subject'), { target: { value: 'Mathematics' } });
    await waitFor(() => expect(screen.getByTestId('req-status-s2')).toHaveTextContent('In progress'));
    // both screens read the one relational record for this teacher
    expect(fakeStore.coverage.get('user-teacher-1')?.get('s2')?.status).toBe('in_progress');
    expect(ds.nodes.some((n) => n.id === 's2')).toBe(true);
  });
});
