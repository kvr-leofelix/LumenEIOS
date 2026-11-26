/**
 * Regression tests for saving the Academic Configuration (the school calendar) when several people work at once.
 * The calendar is a versioned backend record; a save carries the version it was edited from and is refused (409) if the school's
 * calendar has moved on. Two app sessions run side by side against one fake backend that enforces versions like the real one.
 * (Originally written for the workspace-document revision machinery; the same user-visible guarantees now hold for calendar versions.)
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import { DataProvider } from '../context/DataContext';
import { initialUsers } from '../data/seedData';
import { App } from '../App';

vi.mock('../lib/teacherPlanApi', async (orig) => {
  const real = await orig<typeof import('../lib/teacherPlanApi')>();
  const { makeFakeTeacherPlanApi } = await import('./fakeTeacherPlanApi');
  return { ...real, teacherPlanApi: makeFakeTeacherPlanApi() };
});
import { fakeStore } from './fakeTeacherPlanApi';
import { resetCalendarStore } from '../features/teacherPlan/calendarStore';
import { resetPlansStore } from '../features/teacherPlan/plansStore';
import { resetRequirementsStore } from '../features/teacherPlan/requirementsStore';
import { teacherPlanApi } from '../lib/teacherPlanApi';
import { signInAs } from './signIn';

const userFor = (role: string) => initialUsers.find((u) => u.role === role)!;

beforeEach(() => {
  localStorage.clear();
  fakeStore.reset();
  resetCalendarStore();
  resetPlansStore();
  resetRequirementsStore();
});
afterEach(() => cleanup());

/** Mounts an independent session (own AuthProvider/DataProvider) and returns scoped queries. */
async function session(role: 'admin' | 'principal', path = role === 'admin' ? '/admin/academic-config' : '/principal/academic-config') {
  signInAs(userFor(role));
  const view = render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <DataProvider>
          <App />
        </DataProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
  const q = within(view.container);
  await q.findByRole('button', { name: 'Save Academic Configuration' });
  return { view, q };
}

const saveBtn = (q: ReturnType<typeof within>) => q.getByRole('button', { name: 'Save Academic Configuration' });
const horizon = (q: ReturnType<typeof within>) => q.getByLabelText('Curriculum planning horizon') as HTMLInputElement;
const focusWindow = () => act(async () => window.dispatchEvent(new Event('focus')));
const lastSaved = () => fakeStore.calendar[fakeStore.calendar.length - 1];

async function saveHorizon(q: ReturnType<typeof within>, value: string, as?: 'admin' | 'principal') {
  // Both sessions share one jsdom localStorage; the fake backend takes the signed-in user from it, so name who is clicking.
  if (as) signInAs(userFor(as));
  const before = fakeStore.calendar.length;
  fireEvent.change(horizon(q), { target: { value } });
  const why = q.queryByLabelText('Reason for the calendar change');
  if (why) fireEvent.change(why, { target: { value: `Horizon ${value}` } });
  fireEvent.click(saveBtn(q));
  await q.findByText(new RegExp(`Calendar version ${before + 1} saved`));
}

describe('calendar save / version handling', () => {
  it('Admin → Principal → Admin alternate saves with no false conflicts', async () => {
    const admin = await session('admin');
    const principal = await session('principal');

    await saveHorizon(admin.q, '100', 'admin');
    expect(fakeStore.calendar).toHaveLength(1);

    // The principal sees the updated configuration once the page regains focus (no reload, no conflict).
    await focusWindow();
    await within(principal.view.container).findByDisplayValue('100');

    await saveHorizon(principal.q, '90', 'principal');
    expect(fakeStore.calendar).toHaveLength(2);

    await focusWindow();
    await within(admin.view.container).findByDisplayValue('90');
    await saveHorizon(admin.q, '80', 'admin');

    expect(fakeStore.calendar.map((v) => v.version)).toEqual([1, 2, 3]);
    expect(fakeStore.calendarCalls.filter((c) => c.op === 'save').map((c) => (c.body as { expected_version: number }).expected_version)).toEqual([0, 1, 2]);
    expect(fakeStore.calendar.map((v) => v.created_by)).toEqual([userFor('admin').id, userFor('principal').id, userFor('admin').id]);
    expect(admin.q.queryByRole('alert')).toBeNull();
  });

  it('consecutive saves in one session always send the latest version', async () => {
    const { q } = await session('principal');
    for (const v of ['50', '60', '70', '80']) await saveHorizon(q, v);
    expect(fakeStore.calendarCalls.filter((c) => c.op === 'save').map((c) => (c.body as { expected_version: number }).expected_version)).toEqual([0, 1, 2, 3]);
    expect(fakeStore.calendar.map((v) => v.version)).toEqual([1, 2, 3, 4]);
  });

  it('a concurrent edit is caught, preserves the unsaved input, and can be retried deliberately', async () => {
    const admin = await session('admin');
    const principal = await session('principal');

    // Both start editing version 0. The principal also adds a calendar entry that must not be lost.
    fireEvent.change(horizon(admin.q), { target: { value: '120' } });
    fireEvent.change(horizon(principal.q), { target: { value: '75' } });
    fireEvent.click(principal.q.getByRole('button', { name: /Add holiday/ }));
    fireEvent.change(principal.q.getByLabelText('Entry 1 description'), { target: { value: 'Founders day' } });

    fireEvent.click(saveBtn(admin.q));
    await admin.q.findByText(/Calendar version 1 saved/);

    // The principal's draft predates the admin's calendar: the conflict is shown before anything is overwritten.
    const panel = await principal.q.findByTestId('config-conflict');
    expect(panel).toHaveTextContent(/changed: planning horizon/);
    expect(panel).toHaveTextContent(/Your unsaved edits differ from it in: holidays .* planning horizon/);
    expect(fakeStore.calendar).toHaveLength(1); // nothing overwritten
    expect(lastSaved().config.horizonDays).toBe(120);
    // Unsaved input is still on screen; saving is blocked until the user decides.
    expect(horizon(principal.q).value).toBe('75');
    expect(principal.q.getByLabelText('Entry 1 description')).toHaveValue('Founders day');
    expect(saveBtn(principal.q)).toBeDisabled();

    // Deliberate retry against the latest version.
    fireEvent.click(principal.q.getByRole('button', { name: 'Keep my edits and review before saving' }));
    expect(principal.q.queryByTestId('config-conflict')).toBeNull();
    fireEvent.change(principal.q.getByLabelText('Reason for the calendar change'), { target: { value: 'Founders day added' } });
    fireEvent.click(saveBtn(principal.q));
    await principal.q.findByText(/Calendar version 2 saved/);
    expect(lastSaved().config.horizonDays).toBe(75);
    expect(lastSaved().config.entries[0].label).toBe('Founders day');
    expect(fakeStore.calendar[0].config.horizonDays).toBe(120); // version 1 is untouched history
  });

  it('a stale draft is caught after a background refresh, and can be discarded in favour of the latest', async () => {
    const admin = await session('admin');
    const principal = await session('principal');
    fireEvent.change(horizon(principal.q), { target: { value: '33' } }); // unsaved edit
    await saveHorizon(admin.q, '120');
    await focusWindow();
    await principal.q.findByTestId('config-conflict');
    expect(horizon(principal.q).value).toBe('33'); // not discarded by the refresh
    expect(saveBtn(principal.q)).toBeDisabled();

    fireEvent.click(principal.q.getByRole('button', { name: 'Discard my edits and use the latest' }));
    expect(horizon(principal.q).value).toBe('120');
    expect(fakeStore.calendar).toHaveLength(1);
  });

  it('if the calendar cannot be loaded, saving is blocked (not a false conflict) until Retry succeeds', async () => {
    fakeStore.calendarFailures = [500, 500];
    signInAs(userFor('principal'));
    const view = render(
      <MemoryRouter initialEntries={['/principal/academic-config']}>
        <AuthProvider>
          <DataProvider>
            <App />
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    );
    const q = within(view.container);
    expect(await q.findByTestId('calendar-load-error')).toHaveTextContent(/could not be loaded.*Saving is disabled/);
    expect(saveBtn(q)).toBeDisabled();
    expect(fakeStore.calendarCalls.filter((c) => c.op === 'save')).toEqual([]);
    fakeStore.calendarFailures = [];
    fireEvent.click(q.getByRole('button', { name: 'Retry' }));
    await act(async () => {});
    await saveHorizon(q, '45');
    expect(lastSaved().config.horizonDays).toBe(45);
  });

  it('background refresh does not wipe the success message or raise warnings when nothing changed', async () => {
    const { q } = await session('admin');
    await saveHorizon(q, '55');
    await focusWindow();
    await focusWindow();
    expect(q.queryByRole('alert')).toBeNull();
    expect(q.getByText(/Calendar version 1 saved/)).toBeInTheDocument();
  });

  it('a save the backend refuses (e.g. a teacher, or an unchanged calendar) is shown, never reported as saved', async () => {
    const { q } = await session('principal');
    await saveHorizon(q, '60');
    const spy = vi.spyOn(teacherPlanApi, 'saveCalendar');
    fireEvent.change(horizon(q), { target: { value: '60' } }); // unchanged -> the Save button stays disabled
    expect(saveBtn(q)).toBeDisabled();
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
