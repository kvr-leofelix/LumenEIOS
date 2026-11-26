import { describe, expect, it } from 'vitest';
import { PLANNING_GRADES, PLANNING_SUBJECTS, summarizeCalendar } from '../../lib/planning/calendar';
import {
  approveDraft,
  approveRecovery,
  attachProposal,
  createDraft,
  currentVersion,
  generateRecovery,
  lessonProgress,
  originalVersion,
  pendingProposal,
  recordAndPropose,
  recordEvidence,
  recordExecution,
  rejectDraft,
  rejectRecovery,
} from '../../lib/planning/execution';
import { generateSchedule } from '../../lib/planning/engine';
import { syllabusFor, VERIFIED_DATASET } from '../../lib/planning/syllabus';
import { admin, approvedPlan, emptyCtx, principal, requirementCtx, smallConfig, teacher } from './fixtures';

const ctx = emptyCtx();

describe('plan approval', () => {
  it('requires Admin/Principal approval and preserves the superseded plan', () => {
    const first = approvedPlan(7, 'Mathematics');
    const view = syllabusFor(VERIFIED_DATASET, 7, 'Mathematics');
    const draft = createDraft({ ...first, createdBy: teacher, draft: generateSchedule({ dataset: VERIFIED_DATASET, units: view.units, grade: 7, subject: 'Mathematics', config: smallConfig, estimates: first.estimates }, requirementCtx(7, 'Mathematics')) });
    expect(() => approveDraft([first, draft], draft.id, teacher, '')).toThrow(/Admin or Principal/);
    // A draft generated without approved requirements cannot be approved.
    const unapproved = createDraft({ ...first, createdBy: teacher, draft: generateSchedule({ dataset: VERIFIED_DATASET, units: view.units, grade: 7, subject: 'Mathematics', config: smallConfig }, ctx) });
    expect(() => approveDraft([first, unapproved], unapproved.id, principal, '')).toThrow(/missing approved requirements/);
    const after = approveDraft([first, draft], draft.id, principal, 'new year');
    expect(after.find((p) => p.id === first.id)!.status).toBe('SUPERSEDED');
    expect(after.find((p) => p.id === first.id)!.versions).toEqual(first.versions);
    expect(after.find((p) => p.id === draft.id)!.status).toBe('APPROVED');
    expect(() => rejectDraft([draft], draft.id, principal, '')).toThrow(/reason/);
  });
});

describe('teacher execution', () => {
  it('homework is incomplete and never counts as teaching or mastery', () => {
    const p = approvedPlan(7, 'Mathematics');
    const l = currentVersion(p)!.lessons[0];
    const r = recordAndPropose(p, { nodeId: l.nodeId, date: '2026-04-01', status: 'HOMEWORK' }, teacher, ctx);
    const pr = lessonProgress(r.plan, l);
    expect(pr.state).toBe('HOMEWORK');
    expect(pr.complete).toBe(false);
    expect(pr.remainingPeriods).toBe(2);
    expect(originalVersion(r.plan)).toEqual(originalVersion(p)); // original untouched
    expect(currentVersion(r.plan)).toEqual(currentVersion(p)); // approved untouched until approval
    // Submitted homework is still not teaching, and mastery needs teaching + evidence.
    const sub = recordExecution(r.plan, { nodeId: l.nodeId, date: '2026-04-01', status: 'HOMEWORK_COMPLETED' }, teacher);
    expect(lessonProgress(sub, l)).toMatchObject({ complete: false, homeworkSubmitted: true });
    expect(() => recordEvidence(sub, l.nodeId, 'ASSESSMENT', 'Quiz 3', '8/10', teacher)).toThrow(/homework alone is not sufficient/);
  });

  it('partial completion carries the remaining periods forward', () => {
    const p = approvedPlan(7, 'Mathematics', smallConfig, 3);
    const l = currentVersion(p)!.lessons[0];
    expect(() => recordExecution(p, { nodeId: l.nodeId, date: '2026-04-01', status: 'PARTIAL', periodsTaught: 3 }, teacher)).toThrow(/between 1 and 2/);
    const r = recordAndPropose(p, { nodeId: l.nodeId, date: '2026-04-02', status: 'PARTIAL', periodsTaught: 2 }, teacher, ctx);
    expect(lessonProgress(r.plan, l)).toMatchObject({ state: 'PARTIAL', taughtPeriods: 2, remainingPeriods: 1 });
    expect(r.proposal!.lessons[0].slots).toHaveLength(1);
    expect(r.proposal!.lessons[0].slots[0].date > '2026-04-02').toBe(true);
  });

  it('rejects duplicates, keeps corrections traceable, and validates dates/roles', () => {
    const p = approvedPlan(7, 'Mathematics');
    const l = currentVersion(p)!.lessons[0];
    const a = recordExecution(p, { nodeId: l.nodeId, date: '2026-04-01', status: 'DEFERRED' }, teacher);
    expect(() => recordExecution(a, { nodeId: l.nodeId, date: '2026-04-01', status: 'DEFERRED' }, teacher)).toThrow(/Duplicate/);
    const b = recordExecution(a, { nodeId: l.nodeId, date: '2026-04-01', status: 'TAUGHT' }, teacher);
    expect(b.execution).toHaveLength(2);
    expect(b.execution[1].supersedes).toBe(b.execution[0].id);
    expect(lessonProgress(b, l).state).toBe('TAUGHT');
    expect(() => recordExecution(b, { nodeId: l.nodeId, date: '2026-04-02', status: 'TAUGHT' }, teacher)).toThrow(/already recorded as taught/);
    expect(() => recordExecution(p, { nodeId: l.nodeId, date: '2026-04-03', status: 'TAUGHT' }, teacher)).toThrow(/not an instructional day/);
    expect(() => recordExecution(p, { nodeId: l.nodeId, date: '2026-04-01', status: 'TAUGHT' }, principal)).toThrow(/teacher/);
  });

  it('assessed state requires taught unit plus evidence', () => {
    const p = approvedPlan(7, 'Mathematics');
    const l = currentVersion(p)!.lessons[0];
    const t = recordExecution(p, { nodeId: l.nodeId, date: '2026-04-02', status: 'TAUGHT' }, teacher);
    expect(lessonProgress(t, l).state).toBe('TAUGHT');
    const e = recordEvidence(t, l.nodeId, 'ASSESSMENT', 'Unit quiz 4', '7/10 class average', teacher);
    expect(lessonProgress(e, l).state).toBe('ASSESSED');
  });
});

describe('adaptive recovery', () => {
  it('builds a proposal, requires approval, then becomes the approved schedule with history', () => {
    const p = approvedPlan(7, 'Mathematics');
    const [a, b] = currentVersion(p)!.lessons;
    expect(a.slots.map((s) => s.date)).toEqual(['2026-04-01', '2026-04-02']);
    const r = recordAndPropose(p, { nodeId: a.nodeId, date: '2026-04-01', status: 'HOMEWORK' }, teacher, ctx);
    const prop = pendingProposal(r.plan)!;
    expect(prop.cutoffDate).toBe('2026-04-01');
    expect(prop.lessons[0].slots[0].date).toBe('2026-04-02');
    expect(prop.lessons[1].slots[0].date > b.slots[0].date).toBe(true);
    expect(prop.changes.map((c) => c.kind)).toEqual(['REQUEUED', 'SHIFTED']);
    expect(prop.affected[0].reason).toMatch(/homework assigned.*outcome reference/i);
    expect(prop.explanation.join(' ')).toMatch(/Nothing changes in the approved schedule until/);

    expect(() => approveRecovery(r.plan, prop.id, teacher, '')).toThrow(/Admin or Principal/);
    const approved = approveRecovery(r.plan, prop.id, principal, 'Agreed');
    expect(approved.versions).toHaveLength(2);
    expect(originalVersion(approved)).toEqual(originalVersion(p));
    expect(currentVersion(approved)!.lessons[0].slots[0].date).toBe('2026-04-02');
    expect(lessonProgress(approved, currentVersion(approved)!.lessons[0]).state).toBe('RESCHEDULED');
    expect(lessonProgress(approved, currentVersion(approved)!.lessons[0]).complete).toBe(false);
    expect(pendingProposal(approved)).toBeUndefined();

    // Teaching it later yields "completed through subsequent teaching".
    const later = recordAndPropose(approved, { nodeId: a.nodeId, date: '2026-04-02', status: 'TAUGHT' }, teacher, ctx);
    expect(lessonProgress(later.plan, currentVersion(later.plan)!.lessons[0]).state).toBe('COMPLETED_LATER');
    expect(later.proposal).toBeNull();
  });

  it('rejection leaves the approved schedule unchanged and is recorded', () => {
    const p = approvedPlan(8, 'Science');
    const l = currentVersion(p)!.lessons[0];
    const r = recordAndPropose(p, { nodeId: l.nodeId, date: '2026-04-01', status: 'DEFERRED' }, teacher, ctx);
    const prop = pendingProposal(r.plan)!;
    expect(() => rejectRecovery(r.plan, prop.id, principal, '')).toThrow(/reason/);
    const rejected = rejectRecovery(r.plan, prop.id, principal, 'Use Saturday class instead');
    expect(rejected.versions).toEqual(p.versions);
    expect(rejected.proposals[0]).toMatchObject({ status: 'REJECTED', review: { note: 'Use Saturday class instead' } });
    expect(lessonProgress(rejected, l).state).toBe('DEFERRED');
  });

  it('refuses to approve a stale proposal', () => {
    const p = approvedPlan(7, 'Science');
    const l = currentVersion(p)!.lessons[0];
    const r = recordAndPropose(p, { nodeId: l.nodeId, date: '2026-04-01', status: 'DEFERRED' }, teacher, ctx).plan;
    const prop = pendingProposal(r)!;
    const advanced = approveRecovery(r, prop.id, admin, '');
    const stale = { ...advanced, proposals: [...advanced.proposals, { ...prop, id: 'old', status: 'PENDING' as const }] };
    expect(() => approveRecovery(stale, 'old', principal, '')).toThrow(/changed after this proposal/);
  });

  it('a new incomplete record supersedes the earlier pending proposal (kept in history)', () => {
    const p = approvedPlan(7, 'Mathematics');
    const [a] = currentVersion(p)!.lessons;
    const r1 = recordAndPropose(p, { nodeId: a.nodeId, date: '2026-04-01', status: 'HOMEWORK' }, teacher, ctx).plan;
    const r2 = recordAndPropose(r1, { nodeId: a.nodeId, date: '2026-04-02', status: 'DEFERRED' }, teacher, ctx).plan;
    expect(r2.proposals.map((x) => x.status)).toEqual(['SUPERSEDED', 'PENDING']);
  });

  it('reports remaining-time shortfall in recovery without dropping units', () => {
    const tight = { ...smallConfig, horizonDays: 4 };
    const p = approvedPlan(7, 'Mathematics', tight, 2);
    const [a] = currentVersion(p)!.lessons;
    const prop = recordAndPropose(p, { nodeId: a.nodeId, date: '2026-04-01', status: 'HOMEWORK' }, teacher, ctx).proposal!;
    expect(prop.remainingAvailablePeriods).toBe(3);
    expect(prop.remainingRequiredPeriods).toBe(4);
    expect(prop.lessons).toHaveLength(2);
    expect(prop.metrics.unscheduledPeriods).toBe(1);
    expect(prop.changes.some((c) => c.kind === 'NEWLY_UNSCHEDULED')).toBe(true);
  });

  it('recalculates an approved plan for a configuration change only through approval', () => {
    const p = approvedPlan(6, 'Science');
    const changed = { ...smallConfig, subjectPeriodsPerDay: { Mathematics: 1, Science: 2 } };
    const prop = generateRecovery(p, ctx, { trigger: { kind: 'CONFIG_CHANGE' }, config: changed, actor: teacher })!;
    const withProp = attachProposal(p, prop);
    expect(withProp.config).toEqual(smallConfig);
    const approved = approveRecovery(withProp, prop.id, principal, '');
    expect(approved.config).toEqual(changed);
    expect(currentVersion(approved)!.config).toEqual(changed);
  });

  it('starts a configuration-change proposal after the Day 100 reference date', () => {
    const p = approvedPlan(6, 'Science');
    const changed = { ...smallConfig, horizonDays: 180, subjectPeriodsPerDay: { Mathematics: 1, Science: 1 } };
    const day100 = summarizeCalendar(changed).planningDates[99];
    const prop = generateRecovery(p, ctx, { trigger: { kind: 'CONFIG_CHANGE' }, config: changed, actor: teacher, asOf: day100 })!;
    expect(prop.cutoffDate).toBe(day100);
    expect(prop.lessons.flatMap((l) => l.slots).every((slot) => slot.date > day100)).toBe(true);
    expect(prop.remainingAvailablePeriods).toBeGreaterThan(0);
    expect(currentVersion(approveRecovery(attachProposal(p, prop), prop.id, principal, ''))!.lessons.flatMap((l) => l.slots).every((slot) => slot.date > day100)).toBe(true);
  });

  it.each(PLANNING_GRADES.flatMap((g) => PLANNING_SUBJECTS.map((s) => [g, s] as const)))('full loop works for Class %s %s', (g, s) => {
    const p = approvedPlan(g, s);
    const l = currentVersion(p)!.lessons[0];
    const r = recordAndPropose(p, { nodeId: l.nodeId, date: '2026-04-01', status: 'HOMEWORK' }, teacher, ctx);
    const approved = approveRecovery(r.plan, pendingProposal(r.plan)!.id, principal, '');
    expect(currentVersion(approved)!.version).toBe(2);
    expect(lessonProgress(approved, currentVersion(approved)!.lessons[0]).complete).toBe(false);
    expect(originalVersion(approved)).toEqual(originalVersion(p));
  });
});
