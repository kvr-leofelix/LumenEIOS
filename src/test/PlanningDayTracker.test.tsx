/**
 * End-to-end lost-period journey through the real App (browser-only store). Role switches remount the App, which is
 * also how reloads are simulated.
 *
 * Calendar: Mathematics 3 periods/day, horizon 3 instructional days (2026-04-01 … 2026-04-03) = periods #1–#9.
 * Approved requirements (no ratio): Multiplication 3 Core + 1 Non-Core, Division 2 Core + 3 Non-Core.
 *   04-01: #1 M-Core  #2 M-Core  #3 M-Core
 *   04-02: #4 M-Non   #5 D-Core  #6 D-Core
 *   04-03: #7 D-Non   #8 D-Non   #9 D-Non
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import { DataProvider } from '../context/DataContext';
import { initialUsers } from '../data/seedData';
import { App } from '../App';
import { EMPTY_WORKSPACE, LOCAL_KEY, Workspace } from '../lib/planning/store';
import { syllabusFor, VERIFIED_DATASET } from '../lib/planning/syllabus';

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
import { signInAs } from './signIn';

beforeEach(() => {
  fakeStore.reset();
  resetRequirementsStore();
  resetPlansStore();
  resetCalendarStore();
});
afterEach(() => resetRequirementsStore());

const [mult, div] = syllabusFor(VERIFIED_DATASET, 7, 'Mathematics').units;

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

/** The teacher's saved requirement in the relational store (the only place requirements live). */
function saveRequirement(unitId: string, core: number, nonCore: number) {
  fakeStore.preloadRequirement('user-teacher-1', topicKeyOf(unitId), 7, 'Mathematics', core, nonCore);
  resetRequirementsStore();
}

async function approvedPlanSetup() {
  let view = open('/principal/academic-config', 'principal');
  fireEvent.change(screen.getByLabelText('Mathematics periods per instructional day'), { target: { value: '3' } });
  fireEvent.change(screen.getByLabelText('Curriculum planning horizon'), { target: { value: '3' } });
  click('Save Academic Configuration');
  await screen.findByText(/Calendar version \d+ saved/);
  view.unmount();
  const reference = stored();
  reference.asOf = '2026-03-31';
  localStorage.setItem(LOCAL_KEY, JSON.stringify(reference));

  saveRequirement(mult.id, 3, 1);
  saveRequirement(div.id, 2, 3);

  view = open('/teacher/time-aware', 'teacher');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Generate draft schedule for approval' })).toBeEnabled()); // requirements load from the API
  click('Generate draft schedule for approval');
  await screen.findByText(/Draft saved for/);
  view.unmount();
  view = open('/principal/curriculum', 'principal');
  fireEvent.click(within(await screen.findByTestId('draft-review')).getByRole('button', { name: 'Approve teaching schedule' }));
  await waitFor(() => expect(screen.queryByTestId('draft-review')).toBeNull());
  view.unmount();
  const lessons = serverPlans()[0].versions[0].lessons;
  expect(lessons.map((l) => l.slots.map((s) => `${s.date.slice(8)}#${s.period}${s.kind === 'CORE' ? 'C' : 'N'}`))).toEqual([
    ['01#1C', '01#2C', '01#3C', '02#1N'],
    ['02#2C', '02#3C', '03#1N', '03#2N', '03#3N'],
  ]);
}

function openRecorder() {
  const recorder = screen.getByTestId('lost-period-recorder');
  fireEvent.click(within(recorder).getByRole('button', { name: 'Record a Lost Day' }));
  return screen.getByRole('dialog');
}

describe('Time-Aware page scope', () => {
  it('keeps period requirements without rendering a second syllabus browser', () => {
    open('/teacher/time-aware', 'teacher');
    expect(screen.queryByRole('tab', { name: 'Syllabus & classification' })).not.toBeInTheDocument();
    expect(screen.queryByText('Curriculum source documents')).not.toBeInTheDocument();
    expect(screen.queryByText('Syllabus data oversight')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Syllabus dataset')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Requirements' }));
    expect(screen.getByText(/Each topic has a saved Core \/ Non-Core classification and period requirement for this teacher/)).toBeInTheDocument();
    expect(screen.getByTestId('approved-requirements-list').children.length).toBeGreaterThan(0);
    // internal provenance wording never reaches the teacher-facing page
    expect(document.body.textContent).not.toMatch(/planning baseline|not reviewed|planning default|default classification|seeded configuration|demo default|Classification pending/i);
    expect(screen.queryByText(/^Chapter 1:/)).not.toBeInTheDocument();
  });
});

describe('Record a Lost Day → Core-priority recovery → approval → Daily Curriculum', () => {
  it('records periods #1 and #2 together, recovers lost Core from Non-Core capacity, and progress follows approval and execution across reloads', async () => {
    await approvedPlanSetup();
    const original = serverPlans()[0].versions[0];
    const config = fakeStore.calendar[fakeStore.calendar.length - 1].config; // the school's current calendar version

    let view = open('/teacher/time-aware', 'teacher');
    // The button sits at the bottom of the Time-Aware Engine, after the planner content.
    const recorderCard = screen.getByTestId('lost-period-recorder');
    expect(recorderCard.compareDocumentPosition(await screen.findByRole('table', { name: 'Topic requirements' })) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
    const dialog = openRecorder();
    expect(within(dialog).getAllByRole('checkbox')).toHaveLength(9);
    const p1 = within(dialog).getByLabelText(`Period 1: 2026-04-01, 8.1 ${mult.title}`);
    const p2 = within(dialog).getByLabelText(`Period 2: 2026-04-01, 8.1 ${mult.title}`);
    expect(p1.closest('tr')!).toHaveTextContent('Core');
    expect(p1.closest('tr')!).toHaveTextContent('VII');
    expect(p1.closest('tr')!).toHaveTextContent('Mathematics');
    fireEvent.click(p1);
    fireEvent.click(p2);
    fireEvent.click(p2); // de-selecting and re-selecting never duplicates a period
    fireEvent.click(p2);
    expect(within(within(dialog).getByRole('list', { name: 'Selected periods' })).getAllByRole('listitem')).toHaveLength(2);
    const submit = within(dialog).getByRole('button', { name: 'Record 2 lost period(s)' });
    expect(submit).toBeDisabled(); // reason is mandatory
    fireEvent.change(within(dialog).getByLabelText('Loss reason'), { target: { value: 'Election Duties' } });
    fireEvent.change(within(dialog).getByLabelText('Loss note'), { target: { value: 'Polling booth setup' } });
    fireEvent.click(submit);
    fireEvent.click(submit); // a second click while saving is ignored
    await screen.findByText(/Recorded period\(s\) #1, #2 as lost \(Election Duties\)/);
    let plan = serverPlans()[0];
    // The lost periods live in the teacher's relational rows (one batch), never in the workspace document.
    expect(fakeStore.lost.get('user-teacher-1')!.map((r) => [r.date, r.period, r.reason, r.notes, r.status])).toEqual([
      ['2026-04-01', 1, 'Election Duties', 'Polling booth setup', 'active'],
      ['2026-04-01', 2, 'Election Duties', 'Polling booth setup', 'active'],
    ]);
    expect(new Set(fakeStore.lost.get('user-teacher-1')!.map((r) => r.batch_id)).size).toBe(1);
    expect(fakeStore.lostCalls.filter((c) => c.op === 'batch')).toHaveLength(1); // the double click recorded once
    expect(plan.losses ?? []).toEqual([]);
    expect(plan.proposals.filter((x) => x.status === 'PENDING')).toHaveLength(1);
    expect(plan.versions).toEqual([original]);
    expect(fakeStore.calendar[fakeStore.calendar.length - 1].config).toEqual(config);

    // Recorded periods cannot be selected again.
    fireEvent.click(within(screen.getByTestId('lost-period-recorder')).getByRole('button', { name: 'Record a Lost Day' }));
    expect(within(screen.getByRole('dialog')).getAllByRole('checkbox')).toHaveLength(7);
    fireEvent.change(within(screen.getByRole('dialog')).getByLabelText('Period filter'), { target: { value: 'all' } });
    expect(within(screen.getByRole('dialog')).getByLabelText(`Period 1: 2026-04-01, 8.1 ${mult.title}`)).toBeDisabled();
    click('Cancel');

    // Progress shows the loss as unaccounted and the proposal as proposed only.
    fireEvent.click(screen.getByRole('tab', { name: 'Day tracker' }));
    expect(screen.getByTestId('recovery-progress')).toHaveTextContent('Lost periods recorded2');
    expect(screen.getByTestId('proposed-recovery')).toHaveTextContent('2 Core period(s) recovered · 2 Non-Core period(s) to independent learning · 0 Core period(s) still unresolved');
    expect(within(screen.getByTestId('recovery-progress')).getByText('Core recovered (approved)').nextSibling).toHaveTextContent('0');
    view.unmount();

    view = open('/principal/curriculum', 'principal');
    const proposal = await screen.findByTestId('recovery-proposal');
    expect(within(proposal).getByTestId('loss-day')).toHaveTextContent('Lost periods on 2026-04-01 (Election Duties): 2 of 3 scheduled Mathematics period(s)');
    const changed = within(proposal).getByRole('table', { name: 'Changed periods' });
    const rows = within(changed).getAllByRole('row').slice(1).map((r) => r.textContent);
    expect(rows).toEqual([
      expect.stringMatching(/^#12026-04-01Lost/),
      expect.stringMatching(/^#22026-04-01Lost/),
      expect.stringMatching(/^#42026-04-02Core recovered.*Multiplication.*Non-Core/),
      expect.stringMatching(/^#42026-04-02Non-Core → independent learning/),
      expect.stringMatching(/^#72026-04-03Core recovered.*Division of Fractions \(Non-Core\)/),
      expect.stringMatching(/^#72026-04-03Non-Core → independent learning.*Division/),
    ]);
    // Rejection needs a reason; approval makes the revision authoritative.
    fireEvent.click(within(proposal).getByRole('button', { name: 'Reject proposal' }));
    expect(within(proposal).getByRole('alert')).toHaveTextContent('rejection reason is required');
    fireEvent.click(within(proposal).getByRole('button', { name: 'Approve recovery schedule' }));
    await waitFor(() => expect(screen.queryByTestId('recovery-proposal')).toBeNull());
    view.unmount();
    plan = serverPlans()[0];
    expect(plan.versions).toHaveLength(2);
    expect(plan.versions[0]).toEqual(original);
    expect(plan.versions[1].approvedBy.role).toBe('principal');
    expect(plan.proposals[0]).toMatchObject({ status: 'APPROVED', review: { by: expect.objectContaining({ role: 'principal' }) } });
    const [m, d] = plan.versions[1].lessons;
    expect(m.slots.map((s) => `${s.date.slice(8)}#${s.period}${s.kind === 'CORE' ? 'C' : 'N'}`)).toEqual(['01#3C', '02#1C', '03#1C']);
    expect(m).toMatchObject({ corePeriods: 3, nonCorePeriods: 1, independentPeriods: 1, coreUnscheduled: 0 });
    expect(d).toMatchObject({ corePeriods: 2, nonCorePeriods: 3, independentPeriods: 1 });
    expect(fakeStore.calendar[fakeStore.calendar.length - 1].config).toEqual(config);

    view = open('/teacher/curriculum-180', 'teacher');
    expect(screen.getByTestId('schedule-change-notice')).toBeInTheDocument();
    expect(screen.getByTestId('classroom-progress')).toHaveTextContent('0 of 7 periods');
    expect(screen.getByTestId('recovery-progress')).toHaveTextContent('Core recovered (approved)2');
    expect(screen.getByTestId('recovery-progress')).toHaveTextContent('Lost, awaiting approval0');
    fireEvent.click(screen.getByRole('tab', { name: 'By period' }));
    const ledger = screen.getByRole('table', { name: 'Daily curriculum by period' });
    const ledgerRow = (n: number) => within(ledger).getByText(`#${n}`).closest('tr')!;
    expect(ledgerRow(1)).toHaveTextContent('Lost — recovery approved');
    expect(ledgerRow(1)).toHaveTextContent('Election Duties — “Polling booth setup”');
    expect(ledgerRow(4)).toHaveTextContent('Core recovery (approved)');
    expect(ledgerRow(8)).toHaveTextContent('Scheduled');
    fireEvent.click(screen.getByRole('tab', { name: 'By topic' }));
    const table = screen.getByRole('table', { name: 'Daily curriculum schedule' });
    const multRow = within(table).getByText(`8.1 ${mult.title}`).closest('tr')!;
    expect(multRow).toHaveTextContent('Lost: #1 (Election Duties), #2 (Election Duties)');
    expect(multRow).toHaveTextContent('Recovered2 Core period(s)');
    expect(within(table).getByText(`8.2 ${div.title}`).closest('tr')!).toHaveTextContent('Independent1 Non-Core (tracked, not taught)');

    // Executing the approved revision: Multiplication taught → its 3 approved classroom periods count, day 1 completes.
    fireEvent.click(within(multRow).getByRole('button', { name: 'Record execution' }));
    fireEvent.click(within(multRow).getByRole('button', { name: 'Completed as scheduled' }));
    await waitFor(() => expect(screen.getByTestId('classroom-progress')).toHaveTextContent('3 of 7 periods'));
    view.unmount();

    view = open('/teacher/curriculum-180', 'teacher');
    expect(screen.getByTestId('classroom-progress')).toHaveTextContent('3 of 7 periods');
    expect(screen.getByTestId('teaching-day-progress')).toHaveTextContent('1 of 3 days');
    expect(fakeStore.calendar[fakeStore.calendar.length - 1].config).toEqual(config);
    // Plan history is held by the backend: the order of operations the server received (loss -> proposal -> review -> execution).
    expect(fakeStore.planCalls.map((c) => c.op).slice(-3)).toEqual(['proposal', 'review-proposal', 'execution']);
    expect(stored().audit).toEqual([]); // nothing is written to the workspace document any more
    expect(document.body.textContent).not.toMatch(/Class Cancelled|70\/30|≈70/i);
    view.unmount();
  });

  it('a rejected proposal leaves the approved schedule authoritative and the rejection traceable; corrections supersede records', async () => {
    await approvedPlanSetup();
    const original = serverPlans()[0].versions[0];

    let view = open('/teacher/time-aware', 'teacher');
    let dialog = openRecorder();
    fireEvent.click(within(dialog).getByLabelText(`Period 5: 2026-04-02, 8.2 ${div.title}`));
    fireEvent.change(within(dialog).getByLabelText('Loss reason'), { target: { value: 'Teacher Training' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Record 1 lost period(s)' }));
    await screen.findByText(/Recorded period\(s\) #5 as lost/);
    view.unmount();

    view = open('/principal/curriculum', 'principal');
    const proposal = await screen.findByTestId('recovery-proposal');
    fireEvent.change(within(proposal).getByLabelText('Recovery review note'), { target: { value: 'Use the Saturday make-up class instead' } });
    fireEvent.click(within(proposal).getByRole('button', { name: 'Reject proposal' }));
    await waitFor(() => expect(screen.queryByTestId('recovery-proposal')).toBeNull());
    view.unmount();
    let plan = serverPlans()[0];
    expect(plan.versions).toEqual([original]);
    expect(plan.proposals).toEqual([expect.objectContaining({ status: 'REJECTED', review: expect.objectContaining({ note: 'Use the Saturday make-up class instead' }) })]);

    view = open('/teacher/time-aware', 'teacher');
    fireEvent.click(screen.getByRole('tab', { name: 'Day tracker' }));
    expect(screen.getByTestId('recovery-progress')).toHaveTextContent('Lost, awaiting approval1');
    expect(screen.getByTestId('recovery-progress')).toHaveTextContent('Approved revisions0');
    expect(screen.getByTestId('recovery-progress')).toHaveTextContent('1 rejected (kept)');
    // Correction: the period was taught after all → withdraw it with an explanation.
    const log = screen.getByRole('table', { name: 'Lost-period log' });
    fireEvent.click(within(log).getByRole('button', { name: 'Correct' }));
    click('Record correction');
    expect(await screen.findByRole('alert')).toHaveTextContent(/Explain the correction/);
    fireEvent.change(screen.getByLabelText('Reason for correction'), { target: { value: 'Period was taught after all' } });
    click('Record correction');
    await waitFor(() => expect(fakeStore.lost.get('user-teacher-1')![0]).toMatchObject({ status: 'withdrawn', withdrawn_reason: 'Period was taught after all' }));
    expect(fakeStore.lost.get('user-teacher-1')).toHaveLength(1); // the row is kept, not deleted
    plan = serverPlans()[0];
    expect(plan.losses ?? []).toEqual([]);
    await waitFor(() => expect(within(screen.getByRole('table', { name: 'Lost-period log' })).getByText('Withdrawn')).toBeInTheDocument());
    view.unmount();

    // Period #5 can be recorded again after the withdrawal.
    view = open('/teacher/time-aware', 'teacher');
    dialog = openRecorder();
    expect(within(dialog).getByLabelText(`Period 5: 2026-04-02, 8.2 ${div.title}`)).not.toBeDisabled();
    view.unmount();
  });

  it('principals review but cannot record lost periods', async () => {
    await approvedPlanSetup();
    const view = open('/teacher/time-aware', 'principal');
    expect(within(screen.getByTestId('lost-period-recorder')).getByRole('button', { name: 'Record a Lost Day' })).toBeDisabled();
    expect(screen.getByText(/Only a teacher or Admin can record lost periods/)).toBeInTheDocument();
    view.unmount();
  });
});
