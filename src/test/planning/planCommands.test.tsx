/** Step 5: the plan changes the existing pure functions make become server commands; the server decides the outcome. */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../../context/AuthContext';
import { initialUsers } from '../../data/seedData';
import { generateSchedule, requirementSnapshot } from '../../lib/planning/engine';
import { approveDraft, approveRecovery, attachProposal, createDraft, generateRecovery, recordAndPropose, recordExecution, rejectDraft, rejectRecovery } from '../../lib/planning/execution';
import { lossCandidates, recordLossBatch } from '../../lib/planning/losses';
import { syllabusFor, VERIFIED_DATASET } from '../../lib/planning/syllabus';
import { classificationsFromRequirements } from '../../features/teacherPlan/requirementsStore';
import { applyPlanCommands, planCommands } from '../../features/teacherPlan/plansStore';
import { PlanningTeacherTable } from '../../features/teacherPlan/PlanningTeacherTable';
import type { RequirementItem } from '../../lib/teacherPlanApi';
import { topicKeyOf } from '../../features/teacherPlan/useTeacherCoverage';
import { fakeStore } from '../fakeTeacherPlanApi';
import { principal, smallConfig, teacher } from './fixtures';
import { signInAs } from '../signIn';

vi.mock('../../lib/teacherPlanApi', async (orig) => {
  const real = await orig<typeof import('../../lib/teacherPlanApi')>();
  const { makeFakeTeacherPlanApi } = await import('../fakeTeacherPlanApi');
  return { ...real, teacherPlanApi: makeFakeTeacherPlanApi() };
});

const [A, B] = syllabusFor(VERIFIED_DATASET, 7, 'Mathematics').units;
const req = (id: string, core: number, non: number): RequirementItem => ({ topic_key: topicKeyOf(id), grade: 7, subject: 'Mathematics', classification: core && non ? 'mixed' : core ? 'core' : 'non_core', core_periods: core, non_core_periods: non, independent_periods: 0, teaching_mode: 'INDEPENDENT', origin: 'teacher', version: 1 });
const ctx = { datasets: [VERIFIED_DATASET], classifications: classificationsFromRequirements([req(A.id, 3, 1), req(B.id, 2, 3)], teacher.id), relationships: [] };
const config = { ...smallConfig, horizonDays: 4, subjectPeriodsPerDay: { Mathematics: 3, Science: 1 } };

function draft() {
  const result = generateSchedule({ dataset: VERIFIED_DATASET, units: [A, B], grade: 7, subject: 'Mathematics', config }, ctx);
  return { ...createDraft({ grade: 7, subject: 'Mathematics', datasetId: VERIFIED_DATASET.id, datasetLabel: VERIFIED_DATASET.label, datasetKind: VERIFIED_DATASET.kind, createdBy: teacher, config, estimates: requirementSnapshot(result.lessons), draft: result }), teacherId: teacher.id };
}

describe('planCommands: pure planning functions -> server commands', () => {
  it('a new draft is a create; approving or rejecting it is a review with the reviewer’s note', () => {
    const d = draft();
    expect(planCommands([], [d], teacher.id).map((c) => c.kind)).toEqual(['create']);
    const ok = approveDraft([d], d.id, principal, 'Looks right');
    expect(planCommands([d], ok, principal.id)).toEqual([{ kind: 'review-plan', planId: d.id, decision: 'APPROVED', note: 'Looks right' }]);
    const no = rejectDraft([d], d.id, principal, 'Rework the order');
    expect(planCommands([d], no, principal.id)).toEqual([{ kind: 'review-plan', planId: d.id, decision: 'REJECTED', note: 'Rework the order' }]);
  });

  it('execution, an attached proposal and a proposal decision map in order; versions and SUPERSEDED are the server’s to derive', () => {
    const d = draft();
    const [plan] = approveDraft([d], d.id, principal, '');
    const { plan: after } = recordAndPropose(plan, { nodeId: A.id, date: '2026-04-01', status: 'HOMEWORK' }, teacher, ctx);
    const cmds = planCommands([plan], [after], teacher.id);
    expect(cmds.map((c) => c.kind)).toEqual(['execution', 'proposal']);
    const pending = after.proposals.find((x) => x.status === 'PENDING')!;
    const decided = approveRecovery(after, pending.id, principal, 'ok');
    const review = planCommands([after], [decided], principal.id);
    expect(review).toEqual([{ kind: 'review-proposal', planId: plan.id, proposalId: pending.id, decision: 'APPROVED', note: 'ok' }]);
    expect(decided.versions.length).toBe(2); // the client computed a version, but no command carries it: the server builds its own
    const rejected = rejectRecovery(after, pending.id, principal, 'No thanks');
    expect(planCommands([after], [rejected], principal.id)[0]).toMatchObject({ kind: 'review-proposal', decision: 'REJECTED', note: 'No thanks' });
  });

  it('dropping a pending proposal without a replacement is a supersede', () => {
    const d = draft();
    const [plan] = approveDraft([d], d.id, principal, '');
    const withProposal = recordAndPropose(plan, { nodeId: A.id, date: '2026-04-01', status: 'HOMEWORK' }, teacher, ctx).plan;
    const cleared = attachProposal(withProposal, null);
    expect(planCommands([withProposal], [cleared], teacher.id)).toEqual([{ kind: 'supersede', planId: plan.id }]);
  });

  it('no change means no command', () => {
    const d = draft();
    expect(planCommands([d], [d], teacher.id)).toEqual([]);
  });
});

describe('server enforces what the client computes', () => {
  beforeEach(() => fakeStore.reset());
  const as = (role: 'teacher' | 'principal') => signInAs(initialUsers.find((u) => u.role === role));

  it('a principal cannot create a teacher’s plan and a teacher cannot approve one: the commands are refused with the server’s message', async () => {
    const d = draft();
    as('principal');
    const refusedCreate = await applyPlanCommands(planCommands([], [d], 'user-principal-1'));
    expect(refusedCreate.ok).toBe(false);
    as('teacher');
    expect((await applyPlanCommands(planCommands([], [d], teacher.id))).ok).toBe(true);
    const approved = approveDraft([d], d.id, principal, '');
    const refusedApprove = await applyPlanCommands(planCommands([d], approved, teacher.id));
    expect(refusedApprove.ok).toBe(false);
    expect(refusedApprove.error).toMatch(/Admin or Principal/);
    expect(fakeStore.plans.get(d.id).status).toBe('DRAFT'); // nothing approved
    as('principal');
    expect((await applyPlanCommands(planCommands([d], approved, principal.id))).ok).toBe(true);
    expect(fakeStore.plans.get(d.id).versions).toHaveLength(1);
  });

  it('losses recorded before a proposal still produce one pending proposal that never touches the approved version', async () => {
    const d = draft();
    as('teacher');
    await applyPlanCommands(planCommands([], [d], teacher.id));
    as('principal');
    const [plan] = approveDraft([d], d.id, principal, '');
    await applyPlanCommands(planCommands([d], [plan], principal.id));
    as('teacher');
    const served = fakeStore.plansFor('teacher', teacher.id)[0];
    const keys = lossCandidates(served).filter((c) => [3, 4].includes(c.number)).map((c) => c.key);
    const lost = recordLossBatch(served, keys, 'Health Drive', '', teacher, () => 'x');
    const proposal = generateRecovery(lost, ctx, { trigger: { kind: 'LOST_PERIODS' }, actor: teacher })!;
    const res = await applyPlanCommands(planCommands([served], [attachProposal(served, proposal)], teacher.id));
    expect(res.ok).toBe(true);
    const stored = fakeStore.plans.get(d.id);
    expect(stored.proposals.map((x: { status: string }) => x.status)).toEqual(['PENDING']);
    expect(stored.versions).toHaveLength(1);
    expect(stored.versions[0].lessons).toEqual(plan.versions[0].lessons);
  });
});

describe('Planning Oversight table', () => {
  afterEach(() => cleanup());
  it('shows a dash for figures that have no approved schedule behind them, never zero', async () => {
    const { teacherPlanApi } = await import('../../lib/teacherPlanApi');
    const base = { config_status: 'within_capacity', teaching_days_completed: 10, teaching_days_remaining: 90, lost_days: 0, lost_periods: 0, required_periods: 40, capacity: { topic_capacity: 40 }, grade: 7, subject: 'Mathematics', pending_drafts: 0 };
    (teacherPlanApi.planningOversight as unknown as ReturnType<typeof vi.fn>) = vi.fn().mockResolvedValue({ rows: [
      { ...base, teacher_id: 'a', teacher_name: 'Asha', indicator: 'green', scheduled_periods: 40, taught_periods: 0, outstanding_core_periods: 0, pending_proposals: 0, approval_status: 'APPROVED', schedule_version: 2, plan_id: 'p' },
      { ...base, teacher_id: 'b', teacher_name: 'Ravi', indicator: 'amber', scheduled_periods: null, taught_periods: null, outstanding_core_periods: null, pending_proposals: null, pending_drafts: 1, approval_status: 'DRAFT', schedule_version: null, plan_id: 'q' },
    ] });
    signInAs(initialUsers.find((u) => u.role === 'principal'));
    render(<MemoryRouter><AuthProvider><PlanningTeacherTable /></AuthProvider></MemoryRouter>);
    const rows = await screen.findAllByTestId('planning-row');
    expect(rows).toHaveLength(2);
    // Asha: real zeros are shown as zero; version is v2
    expect(within(rows[0]).getByTestId('taught')).toHaveTextContent('0');
    expect(within(rows[0]).getByTestId('version')).toHaveTextContent('v2');
    expect(within(rows[0]).getByText('Approved')).toBeInTheDocument();
    // Ravi: nothing approved yet -> unknown, not zero
    for (const id of ['scheduled', 'taught', 'core-outstanding', 'version']) expect(within(rows[1]).getByTestId(id)).toHaveTextContent('—');
    expect(within(rows[1]).getByTestId('proposals')).toHaveTextContent('— (+1 draft)');
    expect(within(rows[1]).getByText('Awaiting approval')).toBeInTheDocument();
    expect(within(rows[1]).getByLabelText('History for Ravi')).toHaveAttribute('href', '/logs?teacher_id=b&grade=7&subject=Mathematics');
    await waitFor(() => expect(rows).toHaveLength(2));
  });
});
