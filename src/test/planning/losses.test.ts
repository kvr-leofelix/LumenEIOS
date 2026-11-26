import { describe, expect, it } from 'vitest';
import { allocate, generateSchedule, requirementSnapshot, slotKind } from '../../lib/planning/engine';
import { proposeRequirement, review } from '../../lib/planning/governance';
import { approveDraft, approveRecovery, createDraft, currentVersion, lessonProgress, originalVersion, pendingProposal, recordLossAndPropose, rejectRecovery } from '../../lib/planning/execution';
import { effectiveLosses, recordLoss } from '../../lib/planning/losses';
import { syllabusFor, VERIFIED_DATASET } from '../../lib/planning/syllabus';
import { principal, smallConfig, teacher } from './fixtures';

const view = syllabusFor(VERIFIED_DATASET, 7, 'Mathematics');
export function requirementPlan(core = 3, nonCore = 1, horizonDays = 10) {
  const config = { ...smallConfig, horizonDays };
  const unit = view.units[0];
  const classifications = review(proposeRequirement({}, unit.id, core, nonCore, [...(core ? ['FOUNDATIONAL_CONCEPT'] : []), ...(nonCore ? ['INDEPENDENT_LEARNING_SUITABLE'] : [])], 'Approved requirements based on the instructional outcomes.', 'Fixture reference', teacher), unit.id, 'APPROVED', '', principal);
  const ctx = { datasets: [VERIFIED_DATASET], classifications, relationships: [] };
  const result = generateSchedule({ dataset: VERIFIED_DATASET, units: [unit], grade: 7, subject: 'Mathematics', config }, ctx);
  const draft = createDraft({ grade: 7, subject: 'Mathematics', datasetId: VERIFIED_DATASET.id, datasetLabel: VERIFIED_DATASET.label, datasetKind: VERIFIED_DATASET.kind, createdBy: teacher, config, estimates: requirementSnapshot(result.lessons), draft: result });
  return { p: approveDraft([draft], draft.id, principal, '')[0], ctx, unit };
}
describe('approved period requirements and selected-period recovery', () => {
  it.each([[3, 1], [2, 3], [1, 8]])('schedules exactly %i Core + %i Non-Core without a ratio', (core, nonCore) => {
    const { p } = requirementPlan(core, nonCore);
    const l = currentVersion(p)!.lessons[0];
    expect(l.slots).toHaveLength(core + nonCore);
    expect(l.slots.filter((s) => s.kind === 'CORE')).toHaveLength(core);
    expect(l.slots.filter((s) => s.kind === 'NON_CORE')).toHaveLength(nonCore);
    expect(currentVersion(p)!.metrics.core.requiredPeriods).toBe(core);
    expect(currentVersion(p)!.metrics.nonCore.requiredPeriods).toBe(nonCore);
  });
  it('flags missing, pending and legacy requirements and ignores legacy estimates', () => {
    const { ctx, unit, p } = requirementPlan();
    for (const classifications of [{}, { [unit.id]: { ...ctx.classifications[unit.id], status: 'PROPOSED' as const } }, { [unit.id]: { ...ctx.classifications[unit.id], corePeriods: undefined } }]) {
      const r = generateSchedule({ dataset: VERIFIED_DATASET, units: [unit], grade: 7, subject: 'Mathematics', config: p.config, estimates: { [unit.id]: 99 } }, { ...ctx, classifications });
      expect(r.lessons[0].slots).toEqual([]);
      expect(r.conflicts.map((c) => c.code)).toContain('REQUIREMENT_MISSING');
    }
  });
  it('recovers one lost Core into an approved Non-Core position and preserves 3 Core', () => {
    const { p, ctx } = requirementPlan();
    const original = structuredClone(p.versions);
    const r = recordLossAndPropose(p, { date: '2026-04-01', periods: [1], periodsLost: 1, reason: 'Election Duties' }, teacher, ctx);
    expect(r.plan.versions).toEqual(original);
    const l = r.proposal!.lessons[0];
    expect(l.slots.filter((s) => s.kind === 'CORE')).toHaveLength(3);
    expect(l.slots.filter((s) => s.kind === 'NON_CORE')).toHaveLength(0);
    expect(l.independentPeriods).toBe(1);
    expect(l.requiredPeriods).toBe(4);
    expect(l.coreUnscheduled).toBe(0);
    expect(l.lossNotes![0]).toMatchObject({ recovered: 1, incomplete: 0 });
    expect(new Set(l.slots.map((s) => s.date + '#' + s.period)).size).toBe(l.slots.length);
    const approved = approveRecovery(r.plan, r.proposal!.id, principal, '');
    const reloaded = JSON.parse(JSON.stringify(approved));
    expect(currentVersion(reloaded)!.version).toBe(2);
    expect(originalVersion(reloaded)).toEqual(original[0]);
    expect(lessonProgress(reloaded, currentVersion(reloaded)!.lessons[0])).toMatchObject({ taughtPeriods: 0, homeworkAssigned: true, complete: false });
    expect(reloaded.config).toEqual(p.config);
  });
  it('flags unresolved Core if the next three days contain no eligible capacity', () => {
    const { p, ctx } = requirementPlan(5, 0, 5);
    const r = recordLossAndPropose(p, { date: '2026-04-01', periods: [1], periodsLost: 1, reason: 'Teacher Training' }, teacher, ctx);
    expect(r.proposal!.metrics.core.unscheduledPeriods).toBe(1);
    expect(r.proposal!.metrics.independentPeriods).toBe(0);
    expect(r.proposal!.conflicts.map((c) => c.code)).toContain('TIME_SHORTFALL');
  });
  it('selects multiple exact positions without losing the whole day', () => {
    const { p, ctx } = requirementPlan(3, 1);
    p.config = { ...p.config, subjectPeriodsPerDay: { Mathematics: 4, Science: 1 } };
    const l = currentVersion(p)!.lessons[0];
    l.slots = l.slots.map((s, i) => ({ ...s, date: '2026-04-01', period: i + 1 }));
    const r = recordLossAndPropose(p, { date: '2026-04-01', periods: [1, 4], periodsLost: 2, reason: 'Other' }, teacher, ctx);
    expect(r.proposal!.lostSlots!.map((s) => s.period)).toEqual([1, 4]);
    expect(r.proposal!.lessons[0].slots.filter((s) => s.date === '2026-04-01').map((s) => s.period)).toEqual([2, 3]);
    expect(r.plan.losses![0].periodsLost).toBe(2);
    expect(r.proposal!.lessons[0].independentPeriods).toBe(1);
  });
  it('prevents duplicate positions irrespective of reason and requires explicit selection', () => {
    const { p, ctx } = requirementPlan();
    const input = { date: '2026-04-01', periods: [1], periodsLost: 1, reason: 'Election Duties' };
    const r = recordLossAndPropose(p, input, teacher, ctx);
    expect(() => recordLoss(r.plan, { ...input, reason: 'Other' }, teacher, 'dup')).toThrow(/Duplicate/);
    expect(() => recordLoss(p, { ...input, periods: undefined }, teacher, 'missing')).toThrow(/explicitly/);
    expect(() => recordLoss(p, { ...input, periods: [1, 1], periodsLost: 2 }, teacher, 'repeat')).toThrow(/explicitly/);
    expect(() => recordLoss(p, { ...input, reason: '' }, teacher, 'reason')).toThrow(/reason/);
  });
  it('rejection retains the original version and lost-period audit', () => {
    const { p, ctx } = requirementPlan();
    const r = recordLossAndPropose(p, { date: '2026-04-01', periods: [1], periodsLost: 1, reason: 'Election Duties' }, teacher, ctx);
    const rejected = rejectRecovery(r.plan, pendingProposal(r.plan)!.id, principal, 'Review alternative recovery');
    expect(rejected.versions).toEqual(p.versions);
    expect(effectiveLosses(rejected)).toHaveLength(1);
  });
  it('does not duplicate allocator positions even if the supplied capacity repeats', () => {
    const { p } = requirementPlan();
    const l = currentVersion(p)!.lessons[0];
    const r = allocate([{ base: l, needCore: 3, needNonCore: 0 }], [l.slots[0], l.slots[0]]);
    expect(r[0].slots).toHaveLength(1);
    expect(r[0].unscheduledPeriods).toBe(2);
  });
  it('corrections are append-only before approval and cannot undo an approved version', () => {
    const { p, ctx } = requirementPlan();
    const r = recordLossAndPropose(p, { date: '2026-04-01', periods: [1], periodsLost: 1, reason: 'Election Duties' }, teacher, ctx);
    const corrected = recordLossAndPropose(r.plan, { date: '2026-04-01', periods: [], periodsLost: 0, reason: 'Election Duties', correctsId: r.plan.losses![0].id, correctionReason: 'Recorded against the wrong period' }, teacher, ctx);
    expect(corrected.plan.losses).toHaveLength(2);
    expect(effectiveLosses(corrected.plan)[0].periodsLost).toBe(0);
    const approved = approveRecovery(r.plan, r.proposal!.id, principal, '');
    expect(() => recordLoss(approved, { date: '2026-04-01', periods: [], periodsLost: 0, reason: 'Election Duties', correctsId: r.plan.losses![0].id, correctionReason: 'Wrong period' }, teacher, 'correction')).toThrow(/approved recovery/);
  });
});

