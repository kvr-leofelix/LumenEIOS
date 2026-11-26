/** Presentation honesty and navigation checks for the finishing pass. */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import { DataProvider } from '../context/DataContext';
import { initialUsers } from '../data/seedData';
import { App } from '../App';
import { setPlanningTransport } from '../lib/planning/store';

vi.mock('../lib/teacherPlanApi', async (orig) => {
  const real = await orig<typeof import('../lib/teacherPlanApi')>();
  const { makeFakeTeacherPlanApi } = await import('./fakeTeacherPlanApi');
  return { ...real, teacherPlanApi: makeFakeTeacherPlanApi() };
});
import { fakeStore } from './fakeTeacherPlanApi';
import { resetCalendarStore } from '../features/teacherPlan/calendarStore';
import { resetPlansStore } from '../features/teacherPlan/plansStore';
import { resetRequirementsStore } from '../features/teacherPlan/requirementsStore';
import { signInAs } from './signIn';
import { demoNoticeFor } from '../components/common/DemoDataNotice';

beforeEach(() => {
  localStorage.clear();
  fakeStore.reset();
  resetCalendarStore();
  resetPlansStore();
  resetRequirementsStore();
});

function open(path: string, role: string) {
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

afterEach(() => setPlanningTransport(undefined));

describe('demonstration-data labelling', () => {
  it.each([
    ['/teacher/assessments', /no AI model is connected/],
    ['/admin/schools', /Campus profiles are seeded demonstration records/],
    ['/principal/teachers', /reassignments are kept in this browser only/],
  ])('offline demo build labels %s as demonstration data', (path, text) => {
    expect(demoNoticeFor(path, true)).toMatch(text);
  });

  it.each([
    ['/teacher/assessments', 'teacher'],
    ['/admin/schools', 'admin'],
    ['/principal/teachers', 'principal'],
    ['/teacher/remediation', 'teacher'],
    ['/teacher/time-aware', 'teacher'],
    ['/teacher/curriculum-180', 'teacher'],
    ['/principal/curriculum', 'principal'],
    ['/principal/academic-config', 'principal'],
    ['/teacher/dashboard', 'teacher'],
    ['/upload', 'teacher'],
  ])('live page %s carries no demo notice', (path, role) => {
    const view = open(path, role);
    expect(screen.queryByTestId('demo-data-notice')).toBeNull();
    view.unmount();
  });
});

describe('audit trail', () => {
  it('shows the persisted central planning records with their actor alongside labelled sample events', async () => {
    // The admin audit page reads the same append-only records as Central Logs; the old workspace audit entries are history only.
    fakeStore.logItems.push({ id: 'e1', occurred_at: '2026-11-10T10:00:00', actor_id: 'user-teacher-1', actor_name: 'Vikram Sengupta', actor_role: 'teacher', school_id: 'school-1', teacher_id: 'user-teacher-1', grade: 7, subject: 'Mathematics', topic_keys: [], category: 'lost_period', status: 'recorded', previous_value: null, new_value: null, reason: null, schedule_version: null, related_event_id: null, related_proposal_id: null, summary: 'Recorded 2 lost period(s) #1, #2 for Class VII Mathematics' });
    const view = open('/admin/audit-logs', 'admin');
    const table = screen.getByRole('table', { name: 'Audit trail' });
    const row = (await within(table).findByText('Lost period')).closest('tr')!;
    expect(row).toHaveTextContent('Planning workspace');
    expect(row).toHaveTextContent('Vikram Sengupta (teacher)');
    expect(row).toHaveTextContent('Recorded 2 lost period(s) #1, #2');
    expect(within(table).getAllByText(/^Sample ·/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/syllabus compression approvals/i)).toBeNull();
    view.unmount();
  });
});

describe('navigation', () => {
  it('uses school-facing navigation labels and keeps campus selection clear', () => {
    const view = open('/admin/dashboard', 'admin');
    fireEvent.click(screen.getAllByRole('button', { name: /Sunrise Public School/ })[0]);
    expect(screen.getAllByText('Green Valley Academy').length).toBeGreaterThan(1);
    view.unmount();
  });

  it('student sidebar links point to distinct sections and only the current one is marked active', () => {
    const view = open('/student/dashboard', 'student');
    const nav = screen.getAllByRole('complementary', { name: 'Main navigation' })[0];
    const links = within(nav).getAllByRole('link');
    expect(new Set(links.map((l) => l.getAttribute('href'))).size).toBe(links.length);
    expect(links.filter((l) => l.getAttribute('aria-current') === 'page')).toHaveLength(1);
    view.unmount();
  });

  it('students never request the staff-only planning workspace', async () => {
    const load = vi.fn(async () => ({ revision: 0, state: null, updated_at: null, updated_by: null }));
    setPlanningTransport({ load, save: vi.fn() } as never);
    const view = open('/student/dashboard', 'student');
    await new Promise((r) => setTimeout(r, 50));
    expect(load).not.toHaveBeenCalled();
    view.unmount();
  });
});
