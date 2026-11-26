/** Teacher-plan UI against a mocked API: the backend stays authoritative, the UI only renders and relays it. */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider, useAuth } from '../../../context/AuthContext';
import { initialUsers } from '../../../data/seedData';

vi.mock('../../../lib/teacherPlanApi', async (orig) => {
  const real = await orig<typeof import('../../../lib/teacherPlanApi')>();
  return {
    ...real,
    teacherPlanApi: {
      plan: vi.fn(), initialize: vi.fn(), saveRequirements: vi.fn(), setCoverage: vi.fn(), lost: vi.fn(), recordLost: vi.fn(),
      planningOversight: vi.fn(), curriculumOversight: vi.fn(), logs: vi.fn(),
      calendarImpact: vi.fn().mockResolvedValue({ current_version: 1, previous_version: null, changed_at: null, reason: null, has_previous: false, impact: null }),
    },
  };
});
import { teacherPlanApi as api } from '../../../lib/teacherPlanApi';
import { PlanLogs } from '../../../pages/shared/PlanLogs';
import { CoverageOversight } from '../../../pages/principal/CoverageOversight';
import { PlanningTeacherTable } from '../PlanningTeacherTable';
import { TeacherPlanPanel } from '../TeacherPlanPanel';
import { TeacherLostDays } from '../TeacherLostDays';
import { invalidateRequirements } from '../requirementsStore';
import { signInAs } from '../../../test/signIn';

const m = <T,>(f: unknown) => f as ReturnType<typeof vi.fn> & T;

function mount(ui: React.ReactElement, role: 'teacher' | 'principal', path = '/') {
  const user = initialUsers.find((u) => u.role === role)!;
  signInAs(user);
  return { user, ...render(<MemoryRouter initialEntries={[path]}><AuthProvider>{ui}</AuthProvider></MemoryRouter>) };
}

const topic = (k: string, cov: 'done' | 'in_progress' | 'not_done', core: number, non: number): import('../../../lib/teacherPlanApi').PlanTopicRow => ({
  topic_key: k, chapter_number: '1', chapter_title: 'Squares', section: `1.${k}`, classification: 'mixed' as const,
  core_periods: core, non_core_periods: non, teaching_mode: 'INDEPENDENT', independent_periods: Math.floor(non / 2), classroom_periods: core + non - Math.floor(non / 2), origin: 'demo_default', version: 1, coverage: cov, coverage_source: 'MANUAL', coverage_updated_at: null, prerequisites: [],
});
const planFor = (topics: ReturnType<typeof topic>[], cap = 20) => ({
  teacher_id: 't', grade: 8, subject: 'Mathematics', calendar_version: 1,
  capacity: { available_periods: 22, reserved_periods: 2, topic_capacity: cap },
  allocation: { proposed_total: 0, topic_capacity: cap, remaining: 0, deficit: 0, valid: true, errors: [] },
  topic_count: topics.length, configured_topic_count: topics.length,
  topics, coverage: { eligible: topics.length, done: topics.filter((t) => t.coverage === 'done').length, in_progress: 0, not_done: 0, percent: 50 },
});

beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); });
afterEach(() => cleanup());

describe('Central Logs', () => {
  const ev = (id: string, category: string) => ({ id, occurred_at: '2026-11-01T10:00:00', actor_name: 'A', actor_role: 'teacher', school_id: 's', teacher_id: 'u1', grade: 7, subject: 'Mathematics', topic_keys: ['k1'], category, status: 'recorded', previous_value: { a: 1 }, new_value: { a: 2 }, reason: 'Because', schedule_version: null, related_event_id: null, related_proposal_id: null, summary: `Event ${id}` });

  it('lists events, expands details, and filters by category through the API', async () => {
    m(api.logs).mockResolvedValue({ total: 2, items: [ev('1', 'lost_period'), ev('2', 'coverage_status')] });
    mount(<PlanLogs />, 'principal');
    expect(await screen.findAllByTestId('log-row')).toHaveLength(2);
    fireEvent.click(screen.getByText('Event 1'));
    expect(screen.getByTestId('log-detail')).toHaveTextContent('Because');
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'lost_period' } });
    await waitFor(() => expect(m(api.logs).mock.calls.at(-1)![0]).toMatchObject({ category: 'lost_period' }));
  });

  it('contextual history links open the same log with their filters pre-applied', async () => {
    m(api.logs).mockResolvedValue({ total: 0, items: [] });
    mount(<PlanLogs />, 'principal', '/logs?teacher_id=u1&topic_key=k1&category=period_requirement');
    await waitFor(() => expect(m(api.logs).mock.calls[0][0]).toMatchObject({ teacher_id: 'u1', topic_key: 'k1', category: 'period_requirement' }));
    expect(await screen.findByText('No events match these filters.')).toBeInTheDocument();
  });
});

describe('Curriculum Oversight', () => {
  const stats = { eligible: 2, done: 1, in_progress: 0, not_done: 1, percent: 50 };
  const row = (id: string, name: string, done: boolean) => ({
    teacher_id: id, teacher_name: name, grade: 7, subject: 'Mathematics', ...stats, done: done ? 1 : 0, not_done: done ? 1 : 2, percent: done ? 50 : 0,
    chapters: [{ chapter_number: '8', chapter_title: 'Fractions', stats, topics: [{ topic_key: 'a', section: '8.1', status: done ? 'done' : 'not_done' }] }],
  });

  it('shows one separate row per teacher, expands chapters with coloured status boxes and links to the Catalogue', async () => {
    m(api.curriculumOversight).mockResolvedValue({ rows: [row('u1', 'Asha', true), row('u2', 'Ravi', false)] });
    mount(<CoverageOversight />, 'principal');
    const rows = await screen.findAllByTestId('coverage-row');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText('50%')).toBeInTheDocument();
    expect(within(rows[1]).getByText('0%')).toBeInTheDocument();
    expect(within(rows[0]).getByRole('link', { name: 'Asha' })).toHaveAttribute('href', '/curriculum/catalogue/7/mathematics?teacher=u1');
    fireEvent.click(screen.getByLabelText('Toggle chapters for Asha'));
    expect(screen.getByTestId('chapter-row').querySelector('[data-status="done"]')).not.toBeNull();
  });

  it('passes class, subject and teacher filters to the API', async () => {
    m(api.curriculumOversight).mockResolvedValue({ rows: [row('u1', 'Asha', true)] });
    mount(<CoverageOversight />, 'principal');
    await screen.findAllByTestId('coverage-row');
    fireEvent.change(screen.getByLabelText('Class'), { target: { value: '7' } });
    fireEvent.change(screen.getByLabelText('Subject'), { target: { value: 'Science' } });
    fireEvent.change(screen.getByLabelText('Teacher'), { target: { value: 'u1' } });
    await waitFor(() => expect(m(api.curriculumOversight).mock.calls.at(-1)![0]).toEqual({ grade: 7, subject: 'Science', teacher_id: 'u1' }));
  });
});

describe('Planning Oversight table', () => {
  it('lists separate teacher plans with RAG indicators', async () => {
    const base = { grade: 7, subject: 'Mathematics', config_status: 'within_capacity', teaching_days_completed: 10, teaching_days_remaining: 90, lost_days: 2, lost_periods: 3, scheduled_periods: 40, outstanding_core_periods: 12, capacity: { topic_capacity: 40 } };
    m(api.planningOversight).mockResolvedValue({ rows: [{ ...base, teacher_id: 'a', teacher_name: 'Asha', indicator: 'green' }, { ...base, teacher_id: 'b', teacher_name: 'Ravi', indicator: 'red', config_status: 'over_capacity' }] });
    mount(<PlanningTeacherTable />, 'principal');
    const rows = await screen.findAllByTestId('planning-row');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByRole('img', { name: 'On track' })).toBeInTheDocument();
    expect(within(rows[1]).getByRole('img', { name: 'Critical' })).toBeInTheDocument();
    expect(within(rows[1]).getByText('Over capacity')).toBeInTheDocument();
  });
});

describe('Teacher plan panel', () => {
  it('shows capacity, blocks an over-capacity edit before saving and never calls save', async () => {
    const teacher = initialUsers.find((u) => u.role === 'teacher')!;
    m(api.plan).mockResolvedValue({ ...planFor([topic('a', 'not_done', 6, 3), topic('b', 'done', 7, 4)], 20), teacher_id: teacher.id });
    mount(<TeacherPlanPanel grade={8} subject="mathematics" />, 'teacher');
    expect(await screen.findAllByTestId('plan-topic-row')).toHaveLength(2);
    const cap = screen.getByTestId('capacity-summary');
    expect(within(cap).getByText('Topic capacity').nextSibling).toHaveTextContent('20');
    expect(within(cap).getByText('Proposed total').nextSibling).toHaveTextContent('20');
    fireEvent.change(screen.getByLabelText('Core periods 1.a'), { target: { value: '9' } });
    expect(screen.getByTestId('capacity-error')).toHaveTextContent(/blocked.*deficit 3/i);
    const save = screen.getByRole('button', { name: 'Save requirements' });
    expect(save).toBeDisabled();
    fireEvent.click(save);
    expect(api.saveRequirements).not.toHaveBeenCalled();
  });

  it('saves a valid edit and shows the backend rejection text when the server refuses', async () => {
    const teacher = initialUsers.find((u) => u.role === 'teacher')!;
    m(api.plan).mockResolvedValue({ ...planFor([topic('a', 'not_done', 6, 3)], 20), teacher_id: teacher.id });
    m(api.saveRequirements).mockRejectedValueOnce(Object.assign(new Error('x'), { data: { detail: { errors: ['Requirements total 21 periods but only 20 are available.'] } } }));
    mount(<TeacherPlanPanel grade={8} subject="mathematics" />, 'teacher');
    await screen.findByTestId('plan-topic-row');
    fireEvent.change(screen.getByLabelText('Core periods 1.a'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save requirements' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('only 20 are available');
    expect(m(api.saveRequirements).mock.calls[0][1].items).toEqual([{ topic_key: 'a', core_periods: 5, non_core_periods: 3 }]);
    m(api.saveRequirements).mockResolvedValueOnce({ changed: ['a'] });
    fireEvent.click(screen.getByRole('button', { name: 'Save requirements' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Requirements saved.');
  });

  it('labels initial values as editable in the Time-Aware requirements view only', async () => {
    const teacher = initialUsers.find((u) => u.role === 'teacher')!;
    const topics = [{ ...topic('a', 'not_done', 6, 3), origin: 'demo_default' as const }, { ...topic('b', 'not_done', 7, 4), origin: 'teacher' as const }];
    m(api.plan).mockResolvedValue({ ...planFor(topics, 30), teacher_id: teacher.id });
    mount(<TeacherPlanPanel grade={8} subject="mathematics" showOrigin />, 'teacher');
    expect(await screen.findByTestId('origin-a')).toHaveTextContent('Initial value (editable)');
    expect(screen.getByTestId('origin-b')).toHaveTextContent('Set by teacher');
    cleanup();
    mount(<TeacherPlanPanel grade={8} subject="mathematics" />, 'teacher'); // Catalogue: no provenance clutter
    await screen.findAllByTestId('plan-topic-row');
    expect(screen.queryByTestId('origin-a')).toBeNull();
  });

  it('is read-only when a principal inspects a teacher', async () => {
    m(api.plan).mockResolvedValue({ ...planFor([topic('a', 'done', 6, 3)], 20), teacher_id: 'u9' });
    mount(<TeacherPlanPanel grade={8} subject="mathematics" />, 'principal', '/?teacher=u9');
    const row = await screen.findByTestId('plan-topic-row');
    expect(m(api.plan).mock.calls[0][0]).toBe('u9');
    expect(within(row).getByLabelText('Core periods 1.a')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Save requirements' })).toBeNull();
  });
});

describe('Lost periods card', () => {
  it('shows the backend counts and refetches when the shared planning rows change, with no recording form of its own', async () => {
    const base = { total_days: 200, completed_days: 50, remaining_days: 140, log: [], records: [] };
    m(api.lost).mockResolvedValueOnce({ ...base, lost_days: 1, lost_periods: 2 }).mockResolvedValue({ ...base, lost_days: 2, lost_periods: 3 });
    mount(<TeacherLostDays grade={7} subject="Mathematics" />, 'teacher');
    const card = await screen.findByTestId('teacher-lost-days');
    await waitFor(() => expect(card).toHaveTextContent('140'));
    expect(card.textContent).toMatch(/Lost days\s*1/);
    expect(card.textContent).toMatch(/Lost periods\s*2/);
    expect(screen.queryByRole('button', { name: 'Record a Lost Day' })).toBeNull(); // the recorder is the single entry point
    expect(card.querySelector('a')).toHaveAttribute('href', expect.stringContaining('category=lost_period'));
    act(() => invalidateRequirements());
    await waitFor(() => expect(card.textContent).toMatch(/Lost periods\s*3/));
    expect(card.textContent).toMatch(/Lost days\s*2/);
  });

  it('renders nothing for a Principal (lost periods belong to the teacher)', () => {
    mount(<TeacherLostDays grade={7} subject="Mathematics" />, 'principal');
    expect(screen.queryByTestId('teacher-lost-days')).toBeNull();
  });
});

describe('School switching', () => {
  it('reloads backend data when the active school changes', async () => {
    m(api.planningOversight).mockResolvedValue({ rows: [] });
    const Switch = () => { const { switchSchool } = useAuth(); return <button onClick={() => switchSchool('school-3')}>switch</button>; };
    mount(<><Switch /><PlanningTeacherTable /></>, 'principal');
    await screen.findByText('No teacher plans in this school yet.');
    expect(api.planningOversight).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText('switch'));
    await waitFor(() => expect(api.planningOversight).toHaveBeenCalledTimes(2));
  });
});
