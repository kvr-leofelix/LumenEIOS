import { describe, expect, it } from 'vitest';
import { currentVersion, generateRecovery, attachProposal, approveRecovery, recordExecution } from '../../lib/planning/execution';
import { paceReport } from '../../lib/planning/pace';
import { teacher, principal, smallConfig, approvedPlan, requirementCtx } from './fixtures';

describe('pace after an approved schedule revision', () => {
  it('keeps overdue Core visible after a Day 100 recovery moves untaught lessons into future slots', () => {
    const baseConfig = { ...smallConfig, horizonDays: 70, subjectPeriodsPerDay: { Mathematics: 3, Science: 1 } };
    const extendedConfig = { ...baseConfig, horizonDays: 180 };
    const ctx = requirementCtx(6, 'Mathematics', 2, 1);
    let plan = approvedPlan(6, 'Mathematics', baseConfig, 3, ctx);
    const first = currentVersion(plan)!.lessons[0];
    const firstDate = first.slots[0].date;
    plan = recordExecution(plan, { nodeId: first.nodeId, date: firstDate, status: 'PARTIAL', periodsTaught: 1, note: 'Demonstration partial classroom record' }, teacher);
    const asOf = '2026-08-20';
    const proposal = generateRecovery(plan, ctx, { trigger: { kind: 'CONFIG_CHANGE' }, config: extendedConfig, actor: teacher, asOf });
    expect(proposal).not.toBeNull();
    expect(proposal!.lessons.flatMap((lesson) => lesson.slots).every((slot) => slot.date > asOf)).toBe(true);

    plan = approveRecovery(attachProposal(plan, proposal), proposal!.id, principal, 'Approve Day 100 demonstration recovery');
    const report = paceReport(plan, asOf)!;
    expect(currentVersion(plan)!.version).toBe(2);
    expect(report.academicDay).toBe(100);
    expect(report.daysRemaining).toBe(80);
    expect(report.core.remaining).toBeGreaterThan(0);
    expect(report.core.overdue).toBeGreaterThan(0);
    expect(report.state).toBe('BEHIND_CORE');
    expect(report.headline).toMatch(/Behind on Core/);
  });
});
