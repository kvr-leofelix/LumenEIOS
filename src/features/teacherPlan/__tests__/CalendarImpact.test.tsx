/** Step 6: calendar recalculation previews for reviewers and the teacher-facing impact of a calendar change. */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../../../context/AuthContext';
import { DataProvider } from '../../../context/DataContext';
import { initialUsers } from '../../../data/seedData';
import { App } from '../../../App';
import { CalendarPreviewPanel, TeacherCalendarImpactPanel } from '../CalendarImpact';

vi.mock('../../../lib/teacherPlanApi', async (orig) => {
  const real = await orig<typeof import('../../../lib/teacherPlanApi')>();
  const { makeFakeTeacherPlanApi } = await import('../../../test/fakeTeacherPlanApi');
  return { ...real, teacherPlanApi: makeFakeTeacherPlanApi() };
});
import { teacherPlanApi as api, type CalendarImpactRow, type CalendarPreview } from '../../../lib/teacherPlanApi';
import { fakeStore } from '../../../test/fakeTeacherPlanApi';
import { resetCalendarStore } from '../calendarStore';
import { resetPlansStore } from '../plansStore';
import { resetRequirementsStore } from '../requirementsStore';
import { signInAs } from '../../../test/signIn';

const cap = (a: number, r: number, t: number) => ({ available_periods: a, reserved_periods: r, topic_capacity: t });
const change = (key: string, section: string, origin: 'teacher' | 'demo_default'): CalendarImpactRow['topics'][number] => ({
  topic_key: key, section, classification: 'mixed', teaching_mode: 'INDEPENDENT', origin,
  original_allocation: 18, revised_allocation: 9, allocation_change: -9,
  original_classroom: 15, revised_classroom: 8, classroom_change: -7,
  original_independent: 3, revised_independent: 1, independent_change: -2,
  saved: 18, saved_core: 12, default_before: 18, default_after: 9, is_affected: true, customization_conflict: origin === 'teacher',
});
const row = (over: Partial<CalendarImpactRow> = {}): CalendarImpactRow => ({
  teacher_id: 'u1', teacher_name: 'Asha', grade: 7, subject: 'Mathematics', capacity_before: cap(40, 4, 36), capacity_after: cap(20, 2, 18), saved_total: 36,
  remaining_before: 0, remaining_after: -18, deficit_after: 18, needs_teacher_review: true,
  periods_gained_or_lost: -18, core_requirements_fit: false, core_shortfall: 3, insufficient_capacity: true,
  topics: [change('k1', '8.1 Multiplication of Fractions', 'teacher'), change('k2', '8.2 Division of Fractions', 'demo_default')],
  approved_schedule: { plan_id: 'p1', calendar_differs: true, capacity_conflict: true, note: 'The approved schedule keeps its calendar snapshot until a recalculation proposal is approved.' }, ...over,
});
const preview = (rows: CalendarImpactRow[]): CalendarPreview => ({
  current_version: 1, proposed_version: 2, unchanged: false, capacity_before: { Mathematics: cap(40, 4, 36), Science: cap(20, 2, 18) },
  capacity_after: { Mathematics: cap(20, 2, 18), Science: cap(20, 2, 18) }, impact: rows, teacher_configurations_changed: false,
});
const as = (role: string) => signInAs(initialUsers.find((u) => u.role === role));

beforeEach(() => {
  localStorage.clear();
  fakeStore.reset();
  resetCalendarStore();
  resetPlansStore();
  resetRequirementsStore();
  vi.restoreAllMocks();
});
afterEach(() => cleanup());

describe('calendar preview panel', () => {
  it('shows capacity and per-topic proposed comparisons, shortfalls and preserved customized/approved state', async () => {
    vi.spyOn(api, 'previewCalendar').mockResolvedValue(preview([row(), row({ teacher_id: 'u2', teacher_name: 'Ravi', saved_total: 10, remaining_after: 8, deficit_after: 0, needs_teacher_review: false, approved_schedule: null })]));
    render(<MemoryRouter><CalendarPreviewPanel config={{ any: 1 }} valid dirty /></MemoryRouter>);
    const panel = await screen.findByTestId('calendar-preview');
    expect(panel).toHaveTextContent('Calendar version 1 -> 2');
    expect(within(screen.getByTestId('capacity-Mathematics')).getByText(/40/).textContent).toMatch(/40 -> 20/);
    expect(screen.getByTestId('capacity-Mathematics').textContent).toMatch(/4 -> 2/);
    expect(screen.getByTestId('capacity-Mathematics').textContent).toMatch(/36 -> 18/);
    const rows = screen.getAllByTestId('impact-row');
    expect(rows[0]).toHaveAttribute('data-review', 'true');
    expect(rows[0]).toHaveTextContent('Saved requirements 36; short by 18.');
    expect(rows[0]).toHaveTextContent('approved schedule conflict');
    expect(rows[1]).toHaveAttribute('data-review', 'false');
    expect(rows[1]).toHaveTextContent('No approved plan');
    expect(within(rows[1]).queryByText(/Insufficient annual capacity/)).toBeNull();
    expect(panel).toHaveTextContent('total change -18');
    expect(panel).toHaveTextContent('Core requirement shortfall: 3 period(s)');
    expect(panel).toHaveTextContent('Classroom original -> proposed');
    expect(panel).toHaveTextContent('15 -> 8');
    expect(panel).toHaveTextContent('3 -> 1');
    expect(panel).toHaveTextContent('Conflicts with teacher customization');
    expect(panel).toHaveTextContent('remains unchanged pending an authorized proposal and approval');
    expect(panel).toHaveTextContent(/proposal preview/);
    expect(panel).toHaveTextContent(/does not apply proposed allocations/);
  });

  it('asks the backend only for a valid, changed configuration, and shows the backend’s reason when it refuses', async () => {
    const spy = vi.spyOn(api, 'previewCalendar').mockRejectedValue(Object.assign(new Error('x'), { data: { detail: { errors: ['Calendar end must be after calendar start.'] } } }));
    const { rerender } = render(<MemoryRouter><CalendarPreviewPanel config={{}} valid={false} dirty /></MemoryRouter>);
    expect(screen.getByText(/Edit a valid configuration to preview/)).toBeInTheDocument();
    rerender(<MemoryRouter><CalendarPreviewPanel config={{}} valid dirty={false} /></MemoryRouter>);
    expect(spy).not.toHaveBeenCalled();
    rerender(<MemoryRouter><CalendarPreviewPanel config={{}} valid dirty /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Calendar end must be after calendar start.'));
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('shows a loading state while the annual-capacity preview is pending', async () => {
    vi.spyOn(api, 'previewCalendar').mockImplementation(() => new Promise<CalendarPreview>(() => undefined));
    render(<MemoryRouter><CalendarPreviewPanel config={{ any: 1 }} valid dirty /></MemoryRouter>);
    expect(await screen.findByRole('status')).toHaveTextContent('Calculating the effect');
  });

  it('the Academic Configuration page previews an edit through the backend before anything is saved', async () => {
    as('principal');
    const spy = vi.spyOn(api, 'previewCalendar');
    render(<MemoryRouter initialEntries={['/principal/academic-config']}><AuthProvider><DataProvider><App /></DataProvider></AuthProvider></MemoryRouter>);
    const horizon = await screen.findByLabelText('Curriculum planning horizon');
    fireEvent.change(horizon, { target: { value: '45' } });
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect((spy.mock.calls.at(-1)![0] as { horizonDays: number }).horizonDays).toBe(45);
    expect(fakeStore.calendar).toEqual([]); // looking is not saving
    expect(await screen.findByTestId('calendar-preview')).toHaveTextContent('Calendar version none -> 1');
  });
});

describe('teacher-facing calendar impact', () => {
  const asTeacher = () => render(<MemoryRouter><AuthProvider><TeacherCalendarImpactPanel teacherId="u1" grade={7} subject="Mathematics" /></AuthProvider></MemoryRouter>);

  it('tells a teacher how the latest calendar change moved their annual allocation, without having changed it', async () => {
    as('teacher');
    vi.spyOn(api, 'calendarImpact').mockResolvedValue({ current_version: 3, previous_version: 2, changed_at: '2026-11-01', reason: 'Timetable revised', has_previous: true, impact: row() });
    asTeacher();
    const box = await screen.findByTestId('teacher-calendar-impact');
    expect(box).toHaveTextContent('Calendar changed (version 2 -> 3) - Timetable revised');
    expect(box).toHaveTextContent('requirements exceed the revised capacity');
    expect(box).toHaveTextContent(/topic capacity 36 -> 18/);
    expect(box).toHaveTextContent(/Your saved requirements total 36; 18 period\(s\) exceed revised capacity/);
    expect(box).toHaveTextContent('This is a proposal preview. Saved requirements and approved allocations remain unchanged.');
    expect(box).toHaveTextContent('The approved schedule keeps its calendar snapshot');
    const table = within(box).getByRole('table', { name: 'Allocation comparison after the calendar change' });
    expect(within(table).getAllByRole('row').slice(1)).toHaveLength(2);
    expect(table).toHaveTextContent('15 -> 8');
    expect(box).toHaveAttribute('open'); // opened by default when action is needed
  });

  it('is quiet when there was no earlier version or no plan, and when the allocation still fits', async () => {
    as('teacher');
    vi.spyOn(api, 'calendarImpact').mockResolvedValue({ current_version: 1, previous_version: null, changed_at: null, reason: null, has_previous: false, impact: null });
    const { unmount } = asTeacher();
    await waitFor(() => expect(api.calendarImpact).toHaveBeenCalled());
    expect(screen.queryByTestId('teacher-calendar-impact')).toBeNull();
    unmount();
    vi.spyOn(api, 'calendarImpact').mockResolvedValue({ current_version: 2, previous_version: 1, changed_at: null, reason: 'x', has_previous: true, impact: row({ needs_teacher_review: false, deficit_after: 0, remaining_after: 4, saved_total: 14, core_shortfall: 0, core_requirements_fit: true, insufficient_capacity: false, topics: [] }) });
    asTeacher();
    const box = await screen.findByTestId('teacher-calendar-impact');
    expect(box).toHaveTextContent('4 periods remain');
    expect(box).not.toHaveAttribute('open');
  });

  it('surfaces load errors and shortfalls without turning them into an approved update', async () => {
    as('teacher');
    vi.spyOn(api, 'calendarImpact').mockRejectedValue(new Error('Calendar impact unavailable'));
    asTeacher();
    expect(await screen.findByRole('alert')).toHaveTextContent('Calendar impact unavailable');
  });
});
