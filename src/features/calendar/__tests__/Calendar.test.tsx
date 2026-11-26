/** Unified calendar: pure date/feed helpers, the full page (view, filter, add) and the dashboard overview that opens it. */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

const request = vi.fn();
vi.mock('../../../lib/apiClient', async (orig) => ({ ...(await orig<typeof import('../../../lib/apiClient')>()), apiRequest: (...a: unknown[]) => request(...a) }));
const auth = vi.hoisted(() => ({ value: { currentUser: { id: 'u1', role: 'student', name: 'Asha' }, currentSchoolId: 's1' } as any }));
vi.mock('../../../context/AuthContext', () => ({ useAuth: () => auth.value }));

import { CalendarPage } from '../CalendarPage';
import { CalendarOverview } from '../CalendarOverview';
import {
  addDays, eventsOn, friendlyDate, fromIso, monthGrid, monthStart, sortForDay, toIso, upcoming,
  type CalendarEvent, type CalendarFeed,
} from '../calendarModel';

const ev = (id: string, category: CalendarEvent['category'], title: string, start: string, end = start, extra: Partial<CalendarEvent> = {}): CalendarEvent =>
  ({ id, category, title, start, end, source: 'school', detail: '', editable: false, ...extra });

const EVENTS: CalendarEvent[] = [
  ev('h', 'holiday', 'Winter Festival', '2026-12-25'),
  ev('v', 'vacation', 'Winter Break', '2026-12-28', '2027-01-02'),
  ev('x', 'exam', 'Unit Test 1', '2026-12-12', '2026-12-12', { source: 'assessment', detail: 'Mathematics · Class 7-A' }),
  ev('d', 'deadline', 'Homework due: Mathematics', '2026-12-14', '2026-12-14', { source: 'homework' }),
  ev('l', 'lost', 'Teaching disrupted: Rain', '2026-12-11'),
  ev('p', 'personal', 'Revise fractions', '2026-12-16', '2026-12-16', { source: 'personal', editable: true, personal_id: 'pp1', personal_kind: 'TASK', done: false }),
  ev('pd', 'personal', 'Old finished task', '2026-12-10', '2026-12-10', { source: 'personal', editable: true, personal_id: 'pp2', personal_kind: 'TASK', done: true }),
];
const feed = (events = EVENTS): CalendarFeed => ({
  start: '2026-11-30', end: '2027-01-10', events,
  meta: { schools: [{ id: 's1', name: 'Sunrise School' }], session_start: '2026-04-01', session_end: '2027-03-31', working_weekdays: [1, 2, 3, 4, 5], year: '2026-2027' },
});

beforeEach(() => {
  auth.value = { currentUser: { id: 'u1', role: 'student', name: 'Asha' }, currentSchoolId: 's1' };
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 11, 10, 9, 0, 0)); // 10 Dec 2026
  request.mockReset();
  request.mockImplementation(async (url: string, opts?: RequestInit) => {
    if (url.startsWith('/calendar/events')) return feed();
    if (url === '/calendar/personal' && opts?.method === 'POST') {
      const b = JSON.parse(String(opts.body));
      return ev('new', 'personal', b.title, b.start_date, b.end_date || b.start_date, { editable: true, personal_id: 'n1', personal_kind: b.kind });
    }
    return {};
  });
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('calendar helpers', () => {
  it('builds a Monday-first six-week grid that contains the whole month', () => {
    const grid = monthGrid(new Date(2026, 11, 1)); // 1 Dec 2026 is a Tuesday
    expect(grid).toHaveLength(42);
    expect(toIso(grid[0])).toBe('2026-11-30');
    expect(grid[0].getDay()).toBe(1);
    expect(grid.map(toIso)).toContain('2026-12-31');
  });
  it('parses and adds dates in local time, never through UTC', () => {
    expect(toIso(fromIso('2026-03-01'))).toBe('2026-03-01');
    expect(toIso(addDays(fromIso('2026-12-31'), 1))).toBe('2027-01-01');
    expect(toIso(monthStart(new Date(2026, 5, 17)))).toBe('2026-06-01');
  });
  it('finds events that span a day and orders exams before holidays and sessions', () => {
    expect(eventsOn(EVENTS, '2026-12-30').map((e) => e.id)).toEqual(['v']);
    const order = sortForDay([ev('a', 'session', 'S', '2026-12-01'), ev('b', 'holiday', 'H', '2026-12-01'), ev('c', 'exam', 'E', '2026-12-01')]);
    expect(order.map((e) => e.category)).toEqual(['exam', 'holiday', 'session']);
  });
  it('lists upcoming items nearest first, skipping lost days and finished tasks, and shows running spans as now', () => {
    const next = upcoming(EVENTS, '2026-12-27', 10).map((e) => e.id);
    expect(next).toEqual(['v']); // the break is running; earlier items are in the past
    expect(upcoming(EVENTS, '2026-12-10', 10).map((e) => e.id)).toEqual(['x', 'd', 'p', 'h', 'v']);
  });
  it('words relative days', () => {
    expect(friendlyDate('2026-12-10', '2026-12-10')).toBe('Today');
    expect(friendlyDate('2026-12-11', '2026-12-10')).toBe('Tomorrow');
    expect(friendlyDate('2026-12-25', '2026-12-10')).toMatch(/25/);
  });
});

describe('Calendar page', () => {
  const page = (path = '/calendar?date=2026-12-25') => render(<MemoryRouter initialEntries={[path]}><CalendarPage /></MemoryRouter>);

  it('opens on the requested day and shows its school items with the session and school name', async () => {
    page();
    expect(await screen.findByRole('heading', { name: 'December 2026' })).toBeTruthy();
    expect(screen.getByText(/Session 2026-2027/)).toBeTruthy();
    expect(screen.getByText(/Sunrise School/)).toBeTruthy();
    const panel = screen.getByRole('region', { name: 'Selected day' });
    expect(within(panel).getByText('Winter Festival')).toBeTruthy();
    expect(within(panel).getByText(/Holiday ·/)).toBeTruthy();
    expect(within(panel).getByText(/School day/)).toBeTruthy(); // 25 Dec 2026 is a Friday
  });

  it('marks weekends as non-working from Academic Config', async () => {
    page('/calendar?date=2026-12-27'); // a Sunday
    const panel = await screen.findByRole('region', { name: 'Selected day' });
    expect(within(panel).getByText(/Non-working day/)).toBeTruthy();
    expect(within(panel).getByText(/Nothing scheduled/)).toBeTruthy();
  });

  it('shows a multi-day break on every day it covers, with its full range', async () => {
    page('/calendar?date=2026-12-30');
    const panel = await screen.findByRole('region', { name: 'Selected day' });
    expect(within(panel).getByText('Winter Break')).toBeTruthy();
    expect(within(panel).getByText(/28 Dec 2026 – 2 Jan 2027/)).toBeTruthy();
    expect(within(panel).getByText(/School day/)).toBeTruthy();
  });

  it('hides a colour from the legend filter and counts what is in the month', async () => {
    page();
    const legend = await screen.findByRole('region', { name: 'Legend and filters' });
    const holiday = within(legend).getByRole('button', { name: /Holiday/ });
    expect(holiday.getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(holiday);
    expect(holiday.getAttribute('aria-pressed')).toBe('false');
    const panel = screen.getByRole('region', { name: 'Selected day' });
    expect(within(panel).queryByText('Winter Festival')).toBeNull();
  });

  it('adds a personal task: validates, posts, and refreshes', async () => {
    page('/calendar?date=2026-12-18');
    fireEvent.click(await screen.findByRole('button', { name: 'Add task or deadline' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add to calendar' }));
    expect((await within(dialog).findByRole('alert')).textContent).toMatch(/Enter a title/);
    expect(request.mock.calls.some(([u]) => u === '/calendar/personal')).toBe(false);

    fireEvent.change(within(dialog).getByLabelText('Title'), { target: { value: 'Science project' } });
    fireEvent.click(within(dialog).getByLabelText(/Deadline/));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add to calendar' }));
    await waitFor(() => expect(request.mock.calls.some(([u]) => u === '/calendar/personal')).toBe(true));
    const [, opts] = request.mock.calls.find(([u]) => u === '/calendar/personal')!;
    expect(JSON.parse(opts.body)).toMatchObject({ title: 'Science project', kind: 'DEADLINE', start_date: '2026-12-18', end_date: null });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    // after saving it reloads the feed
    await waitFor(() => expect(request.mock.calls.filter(([u]) => String(u).startsWith('/calendar/events')).length).toBeGreaterThan(1));
  });

  it('only offers edit, done and delete on the user\'s own items', async () => {
    page('/calendar?date=2026-12-16');
    const panel = await screen.findByRole('region', { name: 'Selected day' });
    expect(within(panel).getByText('Revise fractions')).toBeTruthy();
    expect(within(panel).getByRole('button', { name: 'Edit Revise fractions' })).toBeTruthy();
    expect(within(panel).getByRole('button', { name: 'Delete Revise fractions' })).toBeTruthy();
    cleanup();
    page('/calendar?date=2026-12-25');
    const holidayPanel = await screen.findByRole('region', { name: 'Selected day' });
    expect(within(holidayPanel).queryByRole('button', { name: /Edit|Delete/ })).toBeNull();
  });

  it('reloads for the new campus when management switches school', async () => {
    const view = render(<MemoryRouter initialEntries={['/calendar?date=2026-12-12']}><CalendarPage /></MemoryRouter>);
    await screen.findAllByText('Unit Test 1');
    const loads = () => request.mock.calls.filter(([url]) => String(url).startsWith('/calendar/events')).length;
    const before = loads();
    auth.value = { currentUser: { id: 'u1', role: 'admin', name: 'Asha' }, currentSchoolId: 's2' };
    view.rerender(<MemoryRouter initialEntries={['/calendar?date=2026-12-12']}><CalendarPage /></MemoryRouter>);
    await waitFor(() => expect(loads()).toBe(before + 1));
  });

  it('shows a retry when the calendar cannot load', async () => {
    request.mockReset();
    request.mockRejectedValue(new Error('Server unavailable'));
    page();
    expect((await screen.findByRole('alert')).textContent).toMatch(/Server unavailable/);
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();
  });
});

describe('Dashboard overview', () => {
  const Where = () => <p data-testid="where">{useLocation().pathname + useLocation().search}</p>;
  const mount = () => render(
    <MemoryRouter initialEntries={['/dash']}>
      <Routes>
        <Route path="/dash" element={<CalendarOverview />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );

  it('lists what is coming up, colour coded, nearest first', async () => {
    mount();
    await screen.findByText('Unit Test 1');
    const items = screen.getAllByRole('listitem').map((li) => li.textContent ?? '');
    const order = ['Unit Test 1', 'Homework due: Mathematics', 'Revise fractions', 'Winter Festival'].map((t) => items.findIndex((x) => x.includes(t)));
    expect(order.every((i) => i >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    expect(screen.queryByText('Old finished task')).toBeNull();
    expect(screen.queryByText(/Teaching disrupted/)).toBeNull();
  });

  it('opens the calendar when the card is clicked, or a specific day from a date or item', async () => {
    mount();
    fireEvent.click(await screen.findByRole('link', { name: 'Open the full calendar' }));
    expect((await screen.findByTestId('where')).textContent).toBe('/calendar');
    cleanup();
    mount();
    fireEvent.click(await screen.findByText('Unit Test 1'));
    expect((await screen.findByTestId('where')).textContent).toBe('/calendar?date=2026-12-12');
  });

  it('degrades quietly when the calendar is unavailable', async () => {
    request.mockReset();
    request.mockRejectedValue(new Error('offline'));
    mount();
    expect(await screen.findByText(/calendar is unavailable/i)).toBeTruthy();
  });
});
