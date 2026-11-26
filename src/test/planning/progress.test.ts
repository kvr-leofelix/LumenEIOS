import { describe, expect, it } from 'vitest';
import { approveRecovery, currentVersion, recordAndPropose, recordLossAndPropose, rejectRecovery } from '../../lib/planning/execution';
import { planProgress } from '../../lib/planning/progress';
import { approvedPlan, emptyCtx, principal, smallConfig, teacher } from './fixtures';

describe('planProgress', () => {
  it('keeps teaching-day progress separate from classroom periods and never counts homework as taught', () => {
    const plan = approvedPlan(7, 'Mathematics', undefined, 2);
    const before = planProgress(plan)!;
    expect(before.classroomRequired).toBeGreaterThan(0);
    expect(before.classroomTaught).toBe(0);
    expect(before.classroomPct).toBe(0);
    expect(before.teachingDaysCompleted).toBe(0);
    expect(before.teachingDaysRemaining).toBe(before.teachingDaysTotal);
    expect(before.coreRemaining + before.nonCoreRemaining).toBe(before.classroomRemaining);
    expect(before.lostPeriodsRecorded).toBe(0);

    const lesson = currentVersion(plan)!.lessons[0];
    const date = lesson.slots[0].date;
    const taught = recordAndPropose(plan, { nodeId: lesson.nodeId, date, status: 'TAUGHT' }, teacher, emptyCtx()).plan;
    const afterTeach = planProgress(taught)!;
    expect(afterTeach.classroomTaught).toBe(lesson.slots.length);
    expect(afterTeach.unitsTaught).toBe(1);
    expect(afterTeach.coreTaught + afterTeach.nonCoreTaught).toBe(afterTeach.classroomTaught);

    const withHomework = recordAndPropose(taught, { nodeId: currentVersion(taught)!.lessons[1].nodeId, date: currentVersion(taught)!.lessons[1].slots[0].date, status: 'HOMEWORK' }, teacher, emptyCtx()).plan;
    const afterHw = planProgress(withHomework)!;
    expect(afterHw.classroomTaught).toBe(afterTeach.classroomTaught);
    expect(afterHw.homeworkOpen).toBeGreaterThan(0);
    expect(afterHw.unitsTaught).toBe(1);
  });

  it('counts lost periods without treating them as completed teaching or changing day totals incorrectly', () => {
    const plan = approvedPlan(7, 'Mathematics', undefined, 2);
    const lesson = currentVersion(plan)!.lessons[0];
    const slot = lesson.slots[0];
    const { plan: lost } = recordLossAndPropose(plan, { date: slot.date, periodsLost: 1, periods: [slot.period], reason: 'Election Duties', note: 'booth' }, teacher, emptyCtx());
    const pending = planProgress(lost)!;
    expect(pending.lostPeriodsRecorded).toBe(1);
    expect(pending.lostPeriodsApplied).toBe(0);
    expect(pending.unaccountedLostPeriods).toBe(1);
    expect(pending.recoveryPending).toBe(true);
    expect(pending.classroomTaught).toBe(0);

    const proposal = lost.proposals.find((x) => x.status === 'PENDING')!;
    const approved = approveRecovery(lost, proposal.id, principal, 'ok');
    const after = planProgress(approved)!;
    expect(after.lostPeriodsApplied).toBe(1);
    expect(after.unaccountedLostPeriods).toBe(0);
    expect(after.recoveryPending).toBe(false);
    expect(after.recoveryRevisions).toBe(1);
    expect(after.classroomTaught).toBe(0);
  });

  it('counts a partial period loss once by date and counts a whole lost schedule day once', () => {
    const config = { ...smallConfig, subjectPeriodsPerDay: { Mathematics: 3, Science: 1 } };
    const plan = approvedPlan(7, 'Mathematics', config, 2);
    const date = currentVersion(plan)!.lessons[0].slots[0].date;
    const slots = currentVersion(plan)!.lessons.flatMap((lesson) => lesson.slots).filter((slot) => slot.date === date);
    expect(slots.length).toBeGreaterThan(2);

    const partial = recordLossAndPropose(plan, { date, periodsLost: 2, periods: slots.slice(0, 2).map((slot) => slot.period), reason: 'Unplanned school event' }, teacher, emptyCtx()).plan;
    expect(planProgress(partial)!.teachingDaysLost).toBe(0);

    const wholeDay = recordLossAndPropose(plan, { date, periodsLost: slots.length, periods: slots.map((slot) => slot.period), reason: 'Unplanned school event' }, teacher, emptyCtx()).plan;
    expect(planProgress(wholeDay)!.teachingDaysLost).toBe(1);
  });

  it('does not count rejected recovery as approved progress', () => {
    const plan = approvedPlan(7, 'Mathematics', undefined, 2);
    const lesson = currentVersion(plan)!.lessons[0];
    const slot = lesson.slots[0];
    const { plan: lost } = recordLossAndPropose(plan, { date: slot.date, periodsLost: 1, periods: [slot.period], reason: 'Health Drive' }, teacher, emptyCtx());
    const proposal = lost.proposals.find((x) => x.status === 'PENDING')!;
    const rejected = rejectRecovery(lost, proposal.id, principal, 'not needed');
    const p = planProgress(rejected)!;
    expect(p.recoveryPending).toBe(false);
    expect(p.rejectedProposals).toBe(1);
    expect(p.lostPeriodsApplied).toBe(0);
    expect(p.unaccountedLostPeriods).toBe(1);
    expect(p.recoveryRevisions).toBe(0);
  });
});
