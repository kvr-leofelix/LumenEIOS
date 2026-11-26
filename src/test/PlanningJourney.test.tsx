import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import { DataProvider } from '../context/DataContext';
import { initialUsers } from '../data/seedData';
import { VERIFIED_DATASET } from '../lib/planning/syllabus';
vi.mock('../lib/teacherPlanApi', async (orig) => {
  const real = await orig<typeof import('../lib/teacherPlanApi')>();
  const { makeFakeTeacherPlanApi } = await import('./fakeTeacherPlanApi');
  return { ...real, teacherPlanApi: makeFakeTeacherPlanApi() };
});
import { fakeStore } from './fakeTeacherPlanApi';
import type { Plan } from '../lib/planning/execution';
import { resetRequirementsStore } from '../features/teacherPlan/requirementsStore';
import { resetPlansStore, seedPlansCache } from '../features/teacherPlan/plansStore';
import { resetCalendarStore, seedCalendarCache } from '../features/teacherPlan/calendarStore';
import { topicKeyOf } from '../features/teacherPlan/useTeacherCoverage';

beforeEach(() => {
  fakeStore.reset();
  resetRequirementsStore();
  resetPlansStore();
  resetCalendarStore();
});
import { App } from '../App';
import { EMPTY_WORKSPACE, LOCAL_KEY, setPlanningTransport, Transport, Workspace } from '../lib/planning/store';
import { signInAs } from './signIn';

function open(path: string, role: string) {
  const signedIn = initialUsers.find((u) => u.role === role)!;
  signInAs(signedIn);
  seedPlansCache(signedIn.schoolId || 'school-1', signedIn.id, signedIn.role, fakeStore.plansFor(signedIn.role, signedIn.id));
  const cal = fakeStore.calendar[fakeStore.calendar.length - 1];
  seedCalendarCache(signedIn.schoolId || 'school-1', cal?.version ?? 0, cal?.config ?? null, JSON.parse(JSON.stringify(fakeStore.calendar)));
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

/** The plans as the backend holds them (versions, proposals, execution): the only copy. */
const serverPlans = (): Plan[] => [...fakeStore.plans.values()] as Plan[];
const stored = (): Workspace => JSON.parse(localStorage.getItem(LOCAL_KEY) ?? JSON.stringify(EMPTY_WORKSPACE));
const click = (name: string | RegExp) => fireEvent.click(screen.getByRole('button', { name }));

async function configureCalendar() {
  const view = open('/principal/academic-config', 'principal');
  click(/Add holiday/);
  fireEvent.change(screen.getByLabelText('Entry 1 description'), { target: { value: 'Ram Navami' } });
  fireEvent.change(screen.getByLabelText('Entry 1 from'), { target: { value: '2026-04-02' } });
  click(/Add examination period/);
  fireEvent.change(screen.getByLabelText('Entry 2 description'), { target: { value: 'Periodic test' } });
  fireEvent.change(screen.getByLabelText('Entry 2 from'), { target: { value: '2026-04-06' } });
  // This journey's expected dates assume one period a day (the default timetable is now 2+2).
  fireEvent.change(screen.getByLabelText('Mathematics periods per instructional day'), { target: { value: '1' } });
  fireEvent.change(screen.getByLabelText('Science periods per instructional day'), { target: { value: '1' } });
  fireEvent.change(screen.getByLabelText('Curriculum planning horizon'), { target: { value: '60' } });
  expect(screen.getByText('Configuration is valid.')).toBeInTheDocument();
  click('Save Academic Configuration');
  await screen.findByText(/Calendar version \d+ saved/);
  view.unmount();
  // Explicit saved requirements for this fixture, held in the relational store like in the application.
  const w = stored();
  w.asOf = '2026-03-31';
  for (const n of VERIFIED_DATASET.nodes.filter((n) => n.kind !== 'CHAPTER')) fakeStore.preloadRequirement('user-teacher-1', topicKeyOf(n.id), n.grade, n.subject, 4, 0);
  resetRequirementsStore();
  localStorage.setItem(LOCAL_KEY, JSON.stringify(w));
}

async function generateAndApprove(grade: string, subject: string) {
  let view = open('/teacher/time-aware', 'teacher');
  fireEvent.change(screen.getByLabelText('Class'), { target: { value: grade } });
  fireEvent.change(screen.getByLabelText('Subject'), { target: { value: subject } });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Generate draft schedule for approval' })).toBeEnabled()); // requirements load from the API
  click('Generate draft schedule for approval');
  await screen.findByText(/Draft saved for/);
  view.unmount();

  view = open('/principal/curriculum', 'principal');
  const draft = await screen.findByTestId('draft-review');
  fireEvent.click(within(draft).getByRole('button', { name: 'Approve teaching schedule' }));
  await waitFor(() => expect(screen.queryByTestId('draft-review')).toBeNull());
  view.unmount();
}

afterEach(() => setPlanningTransport(undefined));

describe('end-to-end planning workflow (browser-only mode)', () => {
  it('config → Class VII Mathematics schedule → homework → recovery approval → reload', async () => {
    await configureCalendar();
    const saved = fakeStore.calendar[fakeStore.calendar.length - 1];
    expect(saved.config.entries.map((e: { type: string }) => e.type)).toEqual(['HOLIDAY', 'EXAM']);
    expect(saved.version).toBe(1);
    expect(saved.created_by).toBe(initialUsers.find((u) => u.role === 'principal')!.id); // saved as a calendar version by the principal
    expect(stored().configHistory).toEqual([]); // the workspace holds no configuration history of its own any more

    // Engine uses the saved configuration and the real syllabus.
    let view = open('/teacher/time-aware', 'teacher');
    expect(await screen.findByText('8.1 Multiplication of Fractions')).toBeInTheDocument();
    expect(screen.getByText('8.2 Division of Fractions')).toBeInTheDocument();
    expect(within(screen.getByTestId('engine-metrics')).getByText('60')).toBeInTheDocument();
    // Holiday (2 Apr) and exam (6 Apr) are skipped: first unit runs 1, 3, 7, 8 April.
    await waitFor(() => expect(screen.getByText('2026-04-01 → 2026-04-08')).toBeInTheDocument()); // requirements arrive from the API
    view.unmount();

    await generateAndApprove('7', 'Mathematics');
    const plan = serverPlans()[0];
    expect(plan.status).toBe('APPROVED');
    const original = plan.versions[0];

    // Teacher records homework for the first unit.
    view = open('/teacher/curriculum-180', 'teacher');
    expect(screen.getByRole('heading', { name: /Class 7 · Mathematics · Daily Curriculum/ })).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: 'Record execution' })[0]);
    click('Not completed — assigned as homework');
    await screen.findByTestId('recovery-proposal');
    expect(screen.getAllByText('Incomplete — homework assigned').length).toBeGreaterThan(0);
    expect(screen.getByText('Homework assigned — not counted as completed')).toBeInTheDocument();
    expect(screen.getByText(/Awaiting Principal\/Admin approval/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve recovery schedule' })).toBeNull();
    let state = serverPlans()[0];
    expect(state.versions).toEqual([original]); // original and approved untouched
    expect(state.execution[0]).toMatchObject({ status: 'HOMEWORK', recordedBy: { role: 'teacher' } });
    view.unmount();

    // Principal reviews original vs proposed and approves.
    view = open('/principal/curriculum', 'principal');
    const proposal = await screen.findByTestId('recovery-proposal');
    expect(within(proposal).getByText('Original (v1)')).toBeInTheDocument();
    expect(within(proposal).getByText('Proposed')).toBeInTheDocument();
    expect(within(proposal).getByText(/homework does not count as classroom teaching/i)).toBeTruthy();
    fireEvent.click(within(proposal).getByRole('button', { name: 'Approve recovery schedule' }));
    await waitFor(() => expect(screen.queryByTestId('recovery-proposal')).toBeNull());
    state = serverPlans()[0];
    expect(state.versions).toHaveLength(2);
    expect(state.versions[0]).toEqual(original);
    expect(state.versions[1].lessons[0].slots[0].date).not.toBe(original.lessons[0].slots[0].date);
    expect(state.proposals[0].status).toBe('APPROVED');
    view.unmount();

    // Teacher reloads: revised schedule is approved; homework still distinct from teaching.
    view = open('/teacher/curriculum-180', 'teacher');
    expect(screen.getByTestId('schedule-change-notice')).toHaveTextContent(/v2 approved by/);
    expect(screen.getAllByText('Rescheduled (approved recovery)').length).toBeGreaterThan(0);
    expect(screen.getByText('Homework assigned — not counted as completed')).toBeInTheDocument();
    expect(screen.queryByTestId('recovery-proposal')).toBeNull();
    // Nothing is written to the workspace document; draft, approval, execution and recovery review went to the plan API in order.
    expect(stored().audit).toEqual([]);
    expect(fakeStore.planCalls.map((c) => c.op)).toEqual(['create', 'review-plan', 'execution', 'proposal', 'review-proposal']);
    view.unmount();
  });

  it('works for Science in another class, and a rejected proposal leaves the schedule unchanged', async () => {
    await configureCalendar();
    await generateAndApprove('6', 'Science');
    const original = serverPlans()[0].versions;

    let view = open('/teacher/curriculum-180', 'teacher');
    expect(screen.getByText(/Explore materials through which one can see/)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: 'Record execution' })[0]);
    click('Not completed — deferred/rescheduled');
    await screen.findByTestId('recovery-proposal');
    view.unmount();

    view = open('/principal/curriculum', 'principal');
    const proposal = await screen.findByTestId('recovery-proposal');
    fireEvent.click(within(proposal).getByRole('button', { name: 'Reject proposal' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/rejection reason is required/);
    fireEvent.change(within(proposal).getByLabelText('Recovery review note'), { target: { value: 'Cover in Saturday class' } });
    fireEvent.click(within(proposal).getByRole('button', { name: 'Reject proposal' }));
    await waitFor(() => expect(screen.queryByTestId('recovery-proposal')).toBeNull());
    expect(serverPlans()[0].versions).toEqual(original);
    expect(serverPlans()[0].proposals[0]).toMatchObject({ status: 'REJECTED', review: { note: 'Cover in Saturday class' } });
    view.unmount();
  });

  it('shows failed saves visibly and keeps the previous state', async () => {
    const view = open('/principal/academic-config', 'principal');
    const { teacherPlanApi } = await import('../lib/teacherPlanApi');
    const spy = vi.spyOn(teacherPlanApi, 'saveCalendar').mockRejectedValueOnce(Object.assign(new Error('x'), { status: 503, data: { detail: 'Calendar service unavailable' } }));
    click('Save Academic Configuration');
    expect(await screen.findByTestId('calendar-save-error')).toHaveTextContent(/Calendar service unavailable/);
    expect(fakeStore.calendar).toEqual([]); // nothing was saved
    expect(screen.queryByText(/Calendar version \d+ saved/)).toBeNull();
    spy.mockRestore();
    click('Save Academic Configuration');
    await screen.findByText(/Calendar version 1 saved/); // the same screen recovers and saves
    expect(fakeStore.calendar).toHaveLength(1);
    view.unmount();
  });

  it('a stale draft is refused with a 409 and nothing is overwritten', async () => {
    const view = open('/principal/academic-config', 'principal');
    click('Save Academic Configuration');
    await screen.findByText(/Calendar version 1 saved/);
    fireEvent.change(screen.getByLabelText('Curriculum planning horizon'), { target: { value: '30' } });
    // someone else saves version 2 while this principal is editing
    fakeStore.calendar.push({ ...fakeStore.calendar[0], version: 2, config: { ...fakeStore.calendar[0].config, horizonDays: 90 }, reason: 'other user' });
    fireEvent.change(screen.getByLabelText('Reason for the calendar change'), { target: { value: 'My change' } });
    click('Save Academic Configuration');
    expect(await screen.findByTestId('calendar-save-error')).toHaveTextContent(/different Academic Configuration was saved/);
    expect(fakeStore.calendar.map((v) => v.version)).toEqual([1, 2]); // mine was not written
    view.unmount();
  });

  it('blocks invalid or conflicting calendars from being saved', () => {
    open('/admin/academic-config', 'admin');
    click(/Add holiday/);
    fireEvent.change(screen.getByLabelText('Entry 1 description'), { target: { value: 'Diwali' } });
    fireEvent.change(screen.getByLabelText('Entry 1 from'), { target: { value: '2026-11-09' } });
    click(/Add school event/);
    fireEvent.change(screen.getByLabelText('Entry 2 description'), { target: { value: 'Annual day' } });
    fireEvent.change(screen.getByLabelText('Entry 2 from'), { target: { value: '2026-11-09' } });
    expect(screen.getByText(/Conflict: "Diwali".*overlaps "Annual day"/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save Academic Configuration' })).toBeDisabled();
  });

  it('teachers cannot open Academic Configuration or Curriculum Oversight', () => {
    // Refused at the route, before the page renders (typing the URL must not open a leadership workspace).
    open('/principal/academic-config', 'teacher');
    expect(screen.getByRole('heading', { name: 'Access Restricted' })).toBeInTheDocument();
    cleanup();
    open('/principal/coverage', 'teacher');
    expect(screen.getByRole('heading', { name: 'Access Restricted' })).toBeInTheDocument();
    for (const path of ['/admin/users', '/admin/audit-logs', '/parent/dashboard']) {
      cleanup();
      open(path, 'teacher');
      expect(screen.getByRole('heading', { name: 'Access Restricted' })).toBeInTheDocument();
    }
  });
});

describe('shared backend store (server mode)', () => {
  it('Admin and Principal read and write the same authoritative calendar', async () => {
    let view = open('/principal/academic-config', 'principal');
    click('Save Academic Configuration');
    await screen.findByText(/Calendar version 1 saved/);
    expect(fakeStore.calendar).toHaveLength(1);
    expect(localStorage.getItem(LOCAL_KEY)).toBeNull(); // no competing browser copy
    view.unmount();

    view = open('/admin/academic-config', 'admin');
    // The admin sees the save made by the principal: one shared calendar history, with who saved it.
    expect(await screen.findByText(/Dr\. Sunita Deshmukh \(principal\) · 2026-2027/)).toBeInTheDocument();
    view.unmount();
  });

  it('reports concurrent-edit conflicts and server errors without claiming success', async () => {
    open('/principal/academic-config', 'principal');
    const { teacherPlanApi } = await import('../lib/teacherPlanApi');
    const conflict = vi.spyOn(teacherPlanApi, 'saveCalendar').mockRejectedValueOnce(Object.assign(new Error('x'), { status: 409, data: { detail: 'A different Academic Configuration was saved while you were editing.' } }));
    click('Save Academic Configuration');
    expect(await screen.findByRole('alert')).toHaveTextContent(/Not saved: a different Academic Configuration was saved while you were editing.*Your edits are kept/);
    conflict.mockRejectedValueOnce(Object.assign(new Error('x'), { status: 500, data: { detail: 'Internal error' } }));
    click('Save Academic Configuration');
    await waitFor(() => expect(screen.getByTestId('calendar-save-error')).toHaveTextContent(/Internal error/));
    expect(fakeStore.calendar).toEqual([]);
    expect(screen.queryByText(/Calendar version \d+ saved/)).toBeNull();
    conflict.mockRestore();
  });

  it('falls back to a clearly labelled browser-only mode when the backend is unreachable', async () => {
    const { ApiError } = await import('../lib/apiClient');
    setPlanningTransport({ load: async () => Promise.reject(new ApiError(0, 'offline')), save: async () => Promise.reject(new ApiError(0, 'offline')) });
    open('/teacher/curriculum-180', 'teacher');
    expect(await screen.findByTestId('local-mode-banner')).toHaveTextContent(/backend is unreachable/);
  });
});
