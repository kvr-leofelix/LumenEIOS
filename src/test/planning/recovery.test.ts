/** Core-priority recovery after lost periods, and the progress figures that follow it. */
import { describe, expect, it } from 'vitest';
import { generateSchedule, requirementSnapshot } from '../../lib/planning/engine';
import type { EngineContext } from '../../lib/planning/engine';
import { proposeRequirement, review } from '../../lib/planning/governance';
import type { Classifications, Relationship } from '../../lib/planning/governance';
import { approveDraft, approveRecovery, createDraft, currentVersion, newId, recordAndPropose, recordLossBatchAndPropose, rejectRecovery } from '../../lib/planning/execution';
import { lossCandidates, periodNumbers, recordLossBatch } from '../../lib/planning/losses';
import { periodLedger, planProgress } from '../../lib/planning/progress';
import { syllabusFor, VERIFIED_DATASET } from '../../lib/planning/syllabus';
import { principal, smallConfig, teacher } from './fixtures';

const [A, B] = syllabusFor(VERIFIED_DATASET, 7, 'Mathematics').units;

function approve(c: Classifications, id: string, core: number, nonCore: number): Classifications {
  const criteria = [...(core ? ['FOUNDATIONAL_CONCEPT'] : []), ...(nonCore ? ['ENRICHMENT'] : [])];
  return review(proposeRequirement(c, id, core, nonCore, criteria, 'Approved requirement for this topic in the fixture.', 'Fixture', teacher), id, 'APPROVED', '', principal);
}

/** Two-topic Class VII Mathematics plan; `perDay` Mathematics periods on each of `days` instructional days. */
function plan(a: [number, number], b: [number, number], perDay: number, days: number, relationships: Relationship[] = []) {
  let classifications = approve({}, A.id, ...a);
  classifications = approve(classifications, B.id, ...b);
  const ctx: EngineContext = { datasets: [VERIFIED_DATASET], classifications, relationships };
  const config = { ...smallConfig, horizonDays: days, subjectPeriodsPerDay: { Mathematics: perDay, Science: 1 } };
  const result = generateSchedule({ dataset: VERIFIED_DATASET, units: [A, B], grade: 7, subject: 'Mathematics', config }, ctx);
  const draft = createDraft({ grade: 7, subject: 'Mathematics', datasetId: VERIFIED_DATASET.id, datasetLabel: VERIFIED_DATASET.label, datasetKind: VERIFIED_DATASET.kind, createdBy: teacher, config, estimates: requirementSnapshot(result.lessons), draft: result });
  return { p: approveDraft([draft], draft.id, principal, '')[0], ctx };
}

const keysOf = (p: ReturnType<typeof plan>['p'], numbers: number[]) => lossCandidates(p).filter((c) => numbers.includes(c.number)).map((c) => c.key);
const layout = (l: { slots: { date: string; period: number; kind?: string }[] }) => l.slots.map((s) => `${s.date.slice(5)}#${s.period}${s.kind === 'CORE' ? 'C' : 'N'}`);

// smallConfig planning dates: 04-01, 04-02, 04-07, 04-08, 04-09 … (04-03 holiday, 04-06 exam).
describe('lost periods: Core-priority recovery', () => {
  it('numbers periods across the plan and keeps those numbers stable', () => {
    const { p } = plan([3, 1], [2, 3], 3, 3);
    const n = periodNumbers(p);
    expect([...n.values()]).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
    expect(lossCandidates(p).map((c) => `${c.number}${c.kind[0]}`)).toEqual(['1C', '2C', '3C', '4N', '5C', '6C', '7N', '8N', '9N']);
  });

  it('records several periods across dates in one submission with one proposal', () => {
    const { p, ctx } = plan([3, 1], [2, 3], 3, 3);
    const r = recordLossBatchAndPropose(p, keysOf(p, [3, 4, 5]), 'Health Drive', 'drive', teacher, ctx);
    expect(r.plan.losses!.map((x) => [x.date, x.periods])).toEqual([
      ['2026-04-01', [3]],
      ['2026-04-02', [1, 2]],
    ]);
    expect(new Set(r.plan.losses!.map((x) => x.batchId)).size).toBe(1);
    expect(r.plan.proposals).toHaveLength(1);
    expect(() => recordLossBatch(r.plan, keysOf(p, [3]), 'Other', '', teacher, () => newId('x'))).toThrow(/Duplicate/);
    expect(() => recordLossBatch(p, [...keysOf(p, [1]), ...keysOf(p, [1])], 'Other', '', teacher, () => newId('x'))).toThrow(/only once/);
    expect(() => recordLossBatch(p, keysOf(p, [1]), '', '', teacher, () => newId('x'))).toThrow(/reason/);
    expect(() => recordLossBatch(p, keysOf(p, [1]), 'Other', '', principal, () => newId('x'))).toThrow(/teacher or Admin/);
  });

  it('prefers the topic’s own Non-Core, then unused periods, then a later topic’s Non-Core; Non-Core requirements are preserved', () => {
    // 3/day for 4 days = 12 periods; A 3C+1N, B 2C+3N = 9 → #10–#12 unused.
    const { p, ctx } = plan([3, 1], [2, 3], 3, 4);
    const r = recordLossBatchAndPropose(p, keysOf(p, [1, 2]), 'Election Duties', '', teacher, ctx);
    const [a, b] = r.proposal!.lessons;
    // #4 (own Non-Core) then the first unused period #10 (04-08 #1); B's Non-Core sessions stay in class.
    expect(layout(a)).toEqual(['04-01#3C', '04-02#1C', '04-08#1C']);
    expect(layout(b)).toEqual(['04-02#2C', '04-02#3C', '04-07#1N', '04-07#2N', '04-07#3N']);
    expect(b.independentPeriods).toBe(0);
    expect(a).toMatchObject({ corePeriods: 3, nonCorePeriods: 1, independentPeriods: 1, requiredPeriods: 4, coreUnscheduled: 0 });
  });

  it('takes a later topic’s Non-Core when no unused capacity exists, and reports unresolved Core when Non-Core runs out', () => {
    const full = plan([3, 1], [2, 3], 3, 3); // exactly 9 periods
    const r = recordLossBatchAndPropose(full.p, keysOf(full.p, [1, 2]), 'Election Duties', '', teacher, full.ctx);
    const [a, b] = r.proposal!.lessons;
    expect(layout(a)).toEqual(['04-01#3C', '04-02#1C', '04-07#1C']);
    expect(b.independentPeriods).toBe(1);
    expect(b.nonCorePeriods).toBe(3); // requirement unchanged
    expect(r.proposal!.lossDays![0].unresolved).toEqual([]);

    // All-Core topics: no Non-Core to release and no unused periods → unresolved, explained, never dropped.
    const tight = plan([3, 0], [3, 0], 2, 3);
    const t = recordLossBatchAndPropose(tight.p, keysOf(tight.p, [1]), 'Teacher Training', '', teacher, tight.ctx);
    const ta = t.proposal!.lessons[0];
    expect(ta.coreUnscheduled).toBe(1);
    expect(ta.corePeriods).toBe(3);
    expect(t.proposal!.lossDays![0].unresolved![0]).toMatch(/1 Core period\(s\) unresolved — no eligible Non-Core or unused Mathematics period remains in the next 2 teaching day\(s\) \(2026-04-02 – 2026-04-07\)/);
    expect(t.proposal!.conflicts.map((c) => c.code)).toContain('TIME_SHORTFALL');
  });

  it('only evaluates the next three teaching days', () => {
    // 1/day for 8 days: A 2C+0N on 04-01, 04-02; B 1C+5N from 04-07. Unused periods only exist after the window.
    const { p, ctx } = plan([2, 0], [1, 5], 1, 9);
    const r = recordLossBatchAndPropose(p, keysOf(p, [1]), 'Other', '', teacher, ctx);
    const a = r.proposal!.lessons[0];
    // Window after 04-01 = 04-02 (A's own Core), 04-07 (B Core), 04-08 (B Non-Core) → recovered into 04-08.
    expect(layout(a)).toEqual(['04-02#1C', '04-08#1C']);
    expect(r.proposal!.lessons[1].independentPeriods).toBe(1);
  });

  it('never takes a period from a taught topic, and blocks losses on taught topics', () => {
    const { p, ctx } = plan([3, 1], [2, 3], 3, 3);
    const taught = recordAndPropose(p, { nodeId: B.id, date: '2026-04-02', status: 'TAUGHT' }, teacher, ctx).plan;
    expect(lossCandidates(taught).filter((c) => c.state === 'TAUGHT')).toHaveLength(5);
    expect(() => recordLossBatch(taught, keysOf(taught, [5]), 'Other', '', teacher, () => newId('x'))).toThrow(/recorded as taught/);
    const r = recordLossBatchAndPropose(taught, keysOf(taught, [1, 2]), 'Other', '', teacher, ctx);
    const a = r.proposal!.lessons.find((l) => l.nodeId === A.id)!;
    expect(a.coreUnscheduled).toBe(1); // own Non-Core #4 used; B's taught sessions untouched
    expect(r.proposal!.lessons.find((l) => l.nodeId === B.id)!.slots).toEqual(currentVersion(taught)!.lessons[1].slots);
  });

  it('respects an approved prerequisite: recovered Core is not placed before the prerequisite finishes', () => {
    // A is an approved prerequisite of B. B has started its Core teaching, so A’s lost Core may not take B’s later
    // Non-Core sessions (that would teach the prerequisite after its dependent).
    const rel: Relationship = { id: 'r1', type: 'PREREQUISITE', fromNodeId: A.id, toNodeId: B.id, explanation: 'B must be understood before A can be completed.', evidence: 'fixture', sharedPeriods: 0, leadNodeId: null, status: 'APPROVED', proposedBy: teacher, proposedAt: '' };
    const { p, ctx } = plan([3, 1], [2, 3], 3, 3, [rel]);
    const r = recordLossBatchAndPropose(p, keysOf(p, [1, 2]), 'Other', '', teacher, ctx);
    const a = r.proposal!.lessons[0];
    expect(layout(a)).toEqual(['04-01#3C', '04-02#1C']); // own Non-Core #4 only
    expect(a.coreUnscheduled).toBe(1);
    expect(r.proposal!.lessons[1].independentPeriods).toBe(0);
    expect(r.proposal!.lossDays![0].unresolved).toHaveLength(1);
  });
});

describe('progress after losses, recovery and execution', () => {
  it('keeps teaching days, periods, lost periods and proposed vs approved recovery distinct', () => {
    const { p, ctx } = plan([3, 1], [2, 3], 3, 3);
    const base = planProgress(p)!;
    expect(base).toMatchObject({ teachingDaysTotal: 3, teachingDaysCompleted: 0, teachingDaysRemaining: 3, classroomRequired: 9, coreRequired: 5, nonCoreRequired: 4, coreRemaining: 5, nonCoreRemaining: 4 });

    const lost = recordLossBatchAndPropose(p, keysOf(p, [1, 2]), 'Election Duties', '', teacher, ctx).plan;
    const pending = planProgress(lost)!;
    expect(pending).toMatchObject({ lostPeriodsRecorded: 2, lostCorePeriods: 2, lostNonCorePeriods: 0, unaccountedLostPeriods: 2, coreRecovered: 0, classroomTaught: 0, recoveryPending: true });
    expect(pending.proposed).toEqual({ coreRecovered: 2, coreUnresolved: 0, nonCoreToIndependent: 2 });

    const rejected = rejectRecovery(lost, lost.proposals[0].id, principal, 'Not this week');
    expect(planProgress(rejected)).toMatchObject({ coreRecovered: 0, unaccountedLostPeriods: 2, proposed: null, rejectedProposals: 1, recoveryRevisions: 0 });

    const approved = approveRecovery(lost, lost.proposals[0].id, principal, '');
    const after = planProgress(approved)!;
    expect(after).toMatchObject({ coreRecovered: 2, coreLostApplied: 2, coreAwaitingRecovery: 0, unaccountedLostPeriods: 0, independentPeriods: 2, classroomRequired: 7, coreRemaining: 5, nonCoreRemaining: 2, unresolvedShortfall: 0, teachingDaysTotal: 3 });
    expect(approved.config).toEqual(p.config);

    // Teaching A completes 04-01 (its only live period #3) but not 04-02 (B's Core is still untaught).
    const taught = recordAndPropose(approved, { nodeId: A.id, date: '2026-04-01', status: 'TAUGHT' }, teacher, ctx).plan;
    expect(planProgress(taught)).toMatchObject({ classroomTaught: 3, coreTaught: 3, teachingDaysCompleted: 1, teachingDaysRemaining: 2 });
    const ledger = periodLedger(taught, periodNumbers(taught));
    expect(ledger.map((r) => `${r.number}:${r.status}`)).toEqual(['1:LOST', '2:LOST', '3:TAUGHT', '4:TAUGHT', '5:SCHEDULED', '6:SCHEDULED', '7:TAUGHT', '8:SCHEDULED', '9:SCHEDULED']);
  });

  it('a day whose every period is lost is not a completed teaching day; its Core is recovered into unused periods', () => {
    const { p, ctx } = plan([2, 0], [2, 0], 2, 3);
    const lost = recordLossBatchAndPropose(p, keysOf(p, [1, 2]), 'Extreme Weather', '', teacher, ctx).plan;
    const approved = approveRecovery(lost, lost.proposals[0].id, principal, '');
    expect(planProgress(approved)).toMatchObject({ teachingDaysTotal: 3, teachingDaysLost: 1, teachingDaysCompleted: 0, teachingDaysRemaining: 2, coreRecovered: 2, coreAwaitingRecovery: 0, unresolvedShortfall: 0 });
    expect(layout(currentVersion(approved)!.lessons[0])).toEqual(['04-07#1C', '04-07#2C']);
  });
});
