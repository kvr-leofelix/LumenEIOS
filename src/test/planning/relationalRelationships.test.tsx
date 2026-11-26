/** Step 3: relationships come from the relational teacher plan; the Catalogue/Time-Aware panel never writes the workspace. */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../../context/AuthContext';
import { DataProvider } from '../../context/DataContext';
import { initialUsers } from '../../data/seedData';
import { generateSchedule } from '../../lib/planning/engine';
import type { EngineContext } from '../../lib/planning/engine';
import { LOCAL_KEY } from '../../lib/planning/store';
import { syllabusFor, VERIFIED_DATASET } from '../../lib/planning/syllabus';
import { RelationshipsPanel } from '../../pages/time-aware/RelationshipsPanel';
import { classificationsFromRequirements, relationshipsFromItems, resetRequirementsStore } from '../../features/teacherPlan/requirementsStore';
import { topicKeyOf } from '../../features/teacherPlan/useTeacherCoverage';
import type { RelationshipItem, RequirementItem } from '../../lib/teacherPlanApi';
import { fakeStore } from '../fakeTeacherPlanApi';
import { smallConfig } from './fixtures';
import { signInAs } from '../signIn';

vi.mock('../../lib/teacherPlanApi', async (orig) => {
  const real = await orig<typeof import('../../lib/teacherPlanApi')>();
  const { makeFakeTeacherPlanApi } = await import('../fakeTeacherPlanApi');
  return { ...real, teacherPlanApi: makeFakeTeacherPlanApi() };
});

const [M1, M2] = syllabusFor(VERIFIED_DATASET, 7, 'Mathematics').units;
const [S1] = syllabusFor(VERIFIED_DATASET, 7, 'Science').units;
const item = (over: Partial<RelationshipItem>): RelationshipItem => ({
  id: 'r1', kind: 'PREREQUISITE', from_key: topicKeyOf(M1.id), to_key: topicKeyOf(M2.id), explanation: 'x'.repeat(24), evidence: 'loc', shared_periods: 0,
  lead_key: null, status: 'active', origin: 'teacher', created_by: 't', created_at: '2026-11-01T00:00:00', ...over,
});
const req = (id: string, grade: number, subject: string, core: number, non: number): RequirementItem => ({
  topic_key: topicKeyOf(id), grade, subject, classification: core && non ? 'mixed' : core ? 'core' : 'non_core', core_periods: core, non_core_periods: non, independent_periods: 0, teaching_mode: 'INDEPENDENT', origin: 'teacher', version: 1,
});

beforeEach(() => {
  localStorage.clear();
  fakeStore.reset();
  resetRequirementsStore();
});
afterEach(() => cleanup());

describe('adapter and engine', () => {
  it('only active links reach the engine, as approved relationships with their shared-period fields', () => {
    const out = relationshipsFromItems([item({}), item({ id: 'r2', status: 'removed' }), item({ id: 'r3', kind: 'CROSS_CURRICULAR', from_key: topicKeyOf(M1.id), to_key: topicKeyOf(S1.id), shared_periods: 2, lead_key: topicKeyOf(M1.id) })], 't');
    expect(out.map((r) => [r.id, r.type, r.status])).toEqual([['r1', 'PREREQUISITE', 'APPROVED'], ['r3', 'CROSS_CURRICULAR', 'APPROVED']]);
    expect(out[1]).toMatchObject({ fromNodeId: M1.id, toNodeId: S1.id, sharedPeriods: 2, leadNodeId: M1.id });
  });

  it('a relational cross-curricular link reduces the non-lead topic exactly as the workspace link did', () => {
    const classifications = classificationsFromRequirements([req(S1.id, 7, 'Science', 4, 0), req(M1.id, 7, 'Mathematics', 4, 0)], 't');
    const config = { ...smallConfig, horizonDays: 10, subjectPeriodsPerDay: { Mathematics: 1, Science: 1 } };
    const run = (relationships: EngineContext['relationships']) =>
      generateSchedule({ dataset: VERIFIED_DATASET, units: [S1], grade: 7, subject: 'Science', config }, { datasets: [VERIFIED_DATASET], classifications, relationships }).lessons[0];
    const none = run([]);
    const linked = run(relationshipsFromItems([item({ id: 'c', kind: 'CROSS_CURRICULAR', from_key: topicKeyOf(M1.id), to_key: topicKeyOf(S1.id), shared_periods: 2, lead_key: topicKeyOf(M1.id) })], 't'));
    expect(none.requiredPeriods).toBe(4);
    expect(linked.requiredPeriods).toBe(2); // 2 shared periods are taught once, in the lead unit
  });

  it('a relational prerequisite is enforced in sequencing', () => {
    const classifications = classificationsFromRequirements([req(M1.id, 7, 'Mathematics', 2, 0), req(M2.id, 7, 'Mathematics', 2, 0)], 't');
    const ctx = (r: RelationshipItem[]): EngineContext => ({ datasets: [VERIFIED_DATASET], classifications, relationships: relationshipsFromItems(r, 't') });
    const gen = (c: EngineContext, units = [M1, M2]) => generateSchedule({ dataset: VERIFIED_DATASET, units, grade: 7, subject: 'Mathematics', config: smallConfig }, c);
    expect(gen(ctx([item({})])).conflicts.some((c) => c.code === 'PREREQUISITE_ORDER')).toBe(false); // M1 before M2: fine
    expect(gen(ctx([item({ from_key: topicKeyOf(M2.id), to_key: topicKeyOf(M1.id) })])).conflicts.some((c) => c.code === 'PREREQUISITE_ORDER')).toBe(true);
  });
});

function open(role: 'teacher' | 'principal', path = '/') {
  const user = initialUsers.find((u) => u.role === role)!;
  signInAs(user);
  return {
    user,
    ...render(
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <DataProvider>
            <RelationshipsPanel grade={7} />
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    ),
  };
}

describe('Relationships panel', () => {
  it('lists the teacher’s relational links and removes one through the API, never the workspace', async () => {
    fakeStore.relationships.set('user-teacher-1', [item({})]);
    const { user } = open('teacher');
    const row = await screen.findByTestId('relationship-row');
    expect(row).toHaveTextContent('Prerequisite');
    fireEvent.click(within(row).getByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(fakeStore.relationshipCalls).toEqual([{ op: 'remove', teacher: user.id, body: 'r1' }]));
    await waitFor(() => expect(screen.queryByTestId('relationship-row')).toBeNull());
    expect(JSON.parse(localStorage.getItem(LOCAL_KEY) ?? '{}').relationships ?? []).toEqual([]);
  });

  it('adds a link through the API after the existing client-side rules, and shows server rejections', async () => {
    const { user } = open('teacher');
    await screen.findByText(/No relationships recorded/);
    const fill = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fill('Relationship type', 'PREREQUISITE');
    fill('From unit', M1.id);
    fill('To unit', M2.id);
    fill('Relationship explanation', 'too short');
    fireEvent.click(screen.getByRole('button', { name: 'Save relationship' }));
    expect(await screen.findByText(/at least 20 characters/)).toBeInTheDocument();
    expect(fakeStore.relationshipCalls).toEqual([]); // blocked before any call
    fill('Relationship explanation', 'Multiplication of fractions is needed before division.');
    fill('Relationship evidence', '8.1 and 8.2 locators');
    fireEvent.click(screen.getByRole('button', { name: 'Save relationship' }));
    await waitFor(() => expect(fakeStore.relationshipCalls).toHaveLength(1));
    expect(fakeStore.relationshipCalls[0]).toMatchObject({ op: 'add', teacher: user.id, body: { kind: 'PREREQUISITE', from_key: topicKeyOf(M1.id), to_key: topicKeyOf(M2.id) } });
    expect(await screen.findByTestId('relationship-row')).toBeInTheDocument(); // reloaded from the store
    expect(JSON.parse(localStorage.getItem(LOCAL_KEY) ?? '{}').relationships ?? []).toEqual([]);
  });

  it('is read-only for a Principal inspecting a teacher', async () => {
    fakeStore.relationships.set('user-teacher-2', [item({})]);
    open('principal', '/?teacher=user-teacher-2');
    const row = await screen.findByTestId('relationship-row');
    expect(within(row).queryByRole('button', { name: 'Remove' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Save relationship' })).toBeDisabled();
  });
});
