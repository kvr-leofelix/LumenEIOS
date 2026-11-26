/** Step 2: requirements come from the relational teacher plan. The engine and its recovery rules are unchanged. */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { generateSchedule, requirementSnapshot, unitClass } from '../../lib/planning/engine';
import type { EngineContext } from '../../lib/planning/engine';
import { approvedRequirement, classificationOf, proposeRequirement, review } from '../../lib/planning/governance';
import type { Classifications } from '../../lib/planning/governance';
import { approveDraft, createDraft, generateRecovery, recordLossBatchAndPropose } from '../../lib/planning/execution';
import { lossCandidates } from '../../lib/planning/losses';
import { syllabusFor, VERIFIED_DATASET } from '../../lib/planning/syllabus';
import type { RequirementItem } from '../../lib/teacherPlanApi';
import { classificationsFromRequirements, invalidateRequirements, lossRecordsFor, resetRequirementsStore, useTeacherClassifications, withLosses } from '../../features/teacherPlan/requirementsStore';
import type { LostRow } from '../../lib/teacherPlanApi';
import { topicKeyOf } from '../../features/teacherPlan/useTeacherCoverage';
import { fakeStore } from '../fakeTeacherPlanApi';
import { principal, smallConfig, teacher } from './fixtures';

vi.mock('../../lib/teacherPlanApi', async (orig) => {
  const real = await orig<typeof import('../../lib/teacherPlanApi')>();
  const { makeFakeTeacherPlanApi } = await import('../fakeTeacherPlanApi');
  return { ...real, teacherPlanApi: makeFakeTeacherPlanApi() };
});

const [A, B] = syllabusFor(VERIFIED_DATASET, 7, 'Mathematics').units;
const row = (id: string, core: number, non: number, origin: RequirementItem['origin'] = 'teacher', independent = 0, mode: RequirementItem['teaching_mode'] = 'INDEPENDENT'): RequirementItem => ({
  topic_key: topicKeyOf(id), grade: 7, subject: 'Mathematics', classification: core && non ? 'mixed' : core ? 'core' : 'non_core',
  core_periods: core, non_core_periods: non, independent_periods: independent, teaching_mode: mode, origin, version: 1,
});

function legacy(a: [number, number], b: [number, number]): Classifications {
  const ap = (c: Classifications, id: string, core: number, non: number) =>
    review(proposeRequirement(c, id, core, non, [...(core ? ['FOUNDATIONAL_CONCEPT'] : []), ...(non ? ['ENRICHMENT'] : [])], 'Approved requirement for this topic in the fixture.', 'Fixture', teacher), id, 'APPROVED', '', principal);
  return ap(ap({}, A.id, ...a), B.id, ...b);
}

function approvedPlan(classifications: Classifications, perDay = 3, days = 3) {
  const ctx: EngineContext = { datasets: [VERIFIED_DATASET], classifications, relationships: [] };
  const config = { ...smallConfig, horizonDays: days, subjectPeriodsPerDay: { Mathematics: perDay, Science: 1 } };
  const result = generateSchedule({ dataset: VERIFIED_DATASET, units: [A, B], grade: 7, subject: 'Mathematics', config }, ctx);
  const draft = createDraft({ grade: 7, subject: 'Mathematics', datasetId: VERIFIED_DATASET.id, datasetLabel: VERIFIED_DATASET.label, datasetKind: VERIFIED_DATASET.kind, createdBy: teacher, config, estimates: requirementSnapshot(result.lessons), draft: result });
  return { p: approveDraft([draft], draft.id, principal, '')[0], ctx };
}

describe('adapter: relational rows -> engine classifications', () => {
  it('teacher-saved and imported rows are approved; demo defaults are never labelled approved but still feed the engine', () => {
    const c = classificationsFromRequirements([row(A.id, 3, 1, 'teacher'), row(B.id, 2, 3, 'demo_default')], teacher.id);
    expect(classificationOf(c, A.id).status).toBe('TEACHER_CUSTOM');
    expect(classificationOf(c, B.id).status).toBe('DEMO_DEFAULT'); // not human-approved
    expect(c[B.id].origin).toBe('demo_default');
    expect(approvedRequirement(c, B.id)).toEqual({ core: 2, nonCore: 3, independent: 0, teachingMode: 'INDEPENDENT' }); // engine still schedules the default
    expect(unitClass({ datasets: [], classifications: c, relationships: [] }, B.id)).toBe('MIXED');
    const imported = classificationsFromRequirements([row(A.id, 4, 0, 'approved_import')], teacher.id);
    expect(classificationOf(imported, A.id).status).toBe('APPROVED');
  });

  it('a pending workspace-style proposal without the demo origin still does not schedule (rule preserved)', () => {
    const proposed = proposeRequirement({}, A.id, 3, 0, ['FOUNDATIONAL_CONCEPT'], 'Pedagogical reasoning for this fixture topic.', 'Fixture', teacher);
    expect(approvedRequirement(proposed, A.id)).toBeNull();
  });

  it('uses demo defaults with zero classroom allocation without calling them approved, and keeps independent periods outside classroom slots', () => {
    const zero = classificationsFromRequirements([{ ...row(A.id, 0, 0, 'demo_default'), classification: 'core' }], teacher.id);
    expect(approvedRequirement(zero, A.id)).toEqual({ core: 0, nonCore: 0, independent: 0, teachingMode: 'INDEPENDENT' });
    expect(unitClass({ datasets: [], classifications: zero, relationships: [] }, A.id)).toBe('CORE');
    expect(classificationOf(zero, A.id).status).toBe('DEMO_DEFAULT');
    const independent = classificationsFromRequirements([row(B.id, 2, 4, 'demo_default', 2)], teacher.id);
    const testConfig = { ...smallConfig, horizonDays: 3, subjectPeriodsPerDay: { Mathematics: 3, Science: 1 } };
    const result = generateSchedule({ dataset: VERIFIED_DATASET, units: [B], grade: 7, subject: 'Mathematics', config: testConfig }, {
      datasets: [VERIFIED_DATASET], classifications: independent, relationships: [],
    });
    expect(result.lessons[0].requirementStatus).toBe('DEMO_DEFAULT');
    expect(result.lessons[0].independentPeriods).toBe(2);
    expect(result.lessons[0].slots).toHaveLength(4); // only Core + remaining classroom Non-Core
  });
});

describe('engine and recovery consume relational requirements unchanged', () => {
  it('produces the identical schedule and the identical recovery proposal as the legacy approved path', () => {
    const rel = approvedPlan(classificationsFromRequirements([row(A.id, 3, 1), row(B.id, 2, 3)], teacher.id));
    const old = approvedPlan(legacy([3, 1], [2, 3]));
    const shape = (p: typeof rel.p) => p.versions[0].lessons.map((l) => [l.nodeId, l.slots.map((s) => `${s.date}#${s.period}${s.kind}`)]);
    expect(shape(rel.p)).toEqual(shape(old.p));
    const keys = (p: typeof rel.p) => lossCandidates(p).filter((c) => [3, 4, 5].includes(c.number)).map((c) => c.key);
    const a = recordLossBatchAndPropose(rel.p, keys(rel.p), 'Health Drive', 'drive', teacher, rel.ctx);
    const b = recordLossBatchAndPropose(old.p, keys(old.p), 'Health Drive', 'drive', teacher, old.ctx);
    const norm = (r: typeof a) => r.proposal && { changes: r.proposal.changes.map((c) => [c.nodeId, c.kind, c.before, c.after]), conflicts: r.proposal.conflicts.map((c) => c.code), moves: r.proposal.lossDays?.map((d) => d.moves?.map((m) => [m.kind, m.nodeId, m.date, m.period])) };
    expect(norm(a)).toEqual(norm(b));
    expect(a.proposal).not.toBeNull();
    expect(a.plan.status).toBe('APPROVED'); // the approved plan itself is not rewritten by proposing
  });

  it('changing a teacher requirement changes the schedule (the engine really reads the relational values)', () => {
    const base = approvedPlan(classificationsFromRequirements([row(A.id, 3, 1), row(B.id, 2, 3)], teacher.id)).p.versions[0].lessons;
    const edited = approvedPlan(classificationsFromRequirements([row(A.id, 4, 0), row(B.id, 2, 3)], teacher.id)).p.versions[0].lessons;
    expect(base[0].slots.length).toBe(4);
    expect(edited[0].slots.map((s) => s.kind)).toEqual(['CORE', 'CORE', 'CORE', 'CORE']);
  });

  it('with no requirements at all, nothing is invented: units stay pending', () => {
    const ctx: EngineContext = { datasets: [VERIFIED_DATASET], classifications: classificationsFromRequirements([], teacher.id), relationships: [] };
    expect(unitClass(ctx, A.id)).toBe('PENDING');
  });
});

describe('shared requirements store', () => {
  const Probe: React.FC<{ school: string; teacher: string }> = ({ school, teacher: t }) => {
    const c = useTeacherClassifications(school, t);
    return <output data-testid="probe">{Object.values(c).map((r) => `${r.nodeId}:${r.corePeriods}+${r.nonCorePeriods}`).join(',')}</output>;
  };
  beforeEach(() => {
    fakeStore.reset();
    resetRequirementsStore();
  });
  afterEach(() => cleanup());

  it('loads the teacher’s own rows, isolates teachers and schools, and reloads after invalidation', async () => {
    fakeStore.preloadRequirement('t-a', topicKeyOf(A.id), 7, 'Mathematics', 3, 1);
    fakeStore.preloadRequirement('t-b', topicKeyOf(A.id), 7, 'Mathematics', 1, 1);
    const a = render(<Probe school="school-1" teacher="t-a" />);
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent(`${A.id}:3+1`));
    a.unmount();
    render(<Probe school="school-1" teacher="t-b" />);
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent(`${A.id}:1+1`));
    cleanup();
    render(<Probe school="school-1" teacher="" />);
    expect(screen.getByTestId('probe')).toHaveTextContent('');
    cleanup();
    render(<Probe school="school-1" teacher="t-a" />);
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent(`${A.id}:3+1`));
    fakeStore.preloadRequirement('t-a', topicKeyOf(A.id), 7, 'Mathematics', 5, 0);
    act(() => invalidateRequirements());
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent(`${A.id}:5+0`));
  });
});


describe('recovery consumes relational lost periods', () => {
  const rowsFor = (p: ReturnType<typeof approvedPlan>['p'], numbers: number[], over: Partial<LostRow> = {}): LostRow[] =>
    lossCandidates(p).filter((c) => numbers.includes(c.number)).map((c, i) => ({
      id: `r${i}`, grade: 7, subject: 'Mathematics', date: c.date, period: c.period, reason: 'Health Drive', topic_keys: [], notes: 'drive', batch_id: 'b1',
      status: 'active' as const, withdrawn_reason: null, recorded_by: teacher.id, recorded_at: '2026-09-01T09:00:00', schedule_version: null, ...over,
    }));

  it('rows -> engine records: grouped per date, active only, withdrawn rows excluded', () => {
    const { p } = approvedPlan(classificationsFromRequirements([row(A.id, 3, 1), row(B.id, 2, 3)], teacher.id));
    const rows = [...rowsFor(p, [3, 4, 5]), ...rowsFor(p, [1], { status: 'withdrawn', batch_id: 'b2' })];
    const recs = lossRecordsFor(rows, teacher.id, 7, 'Mathematics');
    expect(recs.map((r) => [r.date, r.periods, r.periodsLost])).toEqual([['2026-04-01', [3], 1], ['2026-04-02', [1, 2], 2]]);
    expect(lossRecordsFor(rows, teacher.id, 7, 'Science')).toEqual([]);
    expect(lossRecordsFor(rows, teacher.id, 8, 'Mathematics')).toEqual([]);
  });

  it('produces the same recovery proposal as the former workspace records, and ignores stale workspace losses', () => {
    const { p, ctx } = approvedPlan(classificationsFromRequirements([row(A.id, 3, 1), row(B.id, 2, 3)], teacher.id));
    const keys = lossCandidates(p).filter((c) => [3, 4, 5].includes(c.number)).map((c) => c.key);
    const old = recordLossBatchAndPropose(p, keys, 'Health Drive', 'drive', teacher, ctx).proposal!;
    const stale = { ...p, losses: [{ id: 'stale', date: '2026-04-03', periodsLost: 1, periods: [1], reason: 'Other', note: '', recordedBy: teacher, recordedAt: 't', supersedes: null }] };
    const rel = generateRecovery(withLosses(stale, rowsFor(p, [3, 4, 5]), teacher.id), ctx, { trigger: { kind: 'LOST_PERIODS' }, actor: teacher })!;
    const shape = (x: typeof old) => ({ changes: x.changes.map((c) => [c.nodeId, c.kind, c.before, c.after]), moves: x.lossDays?.map((d) => d.moves?.map((m) => [m.kind, m.nodeId, m.date, m.period])), unresolved: x.lossDays?.map((d) => d.unresolved) });
    expect(shape(rel)).toEqual(shape(old)); // the workspace's own (frozen) losses played no part
    expect(rel.lostSlots).toEqual(old.lostSlots);
  });

  it('with the rows withdrawn there is nothing to recover', () => {
    const { p, ctx } = approvedPlan(classificationsFromRequirements([row(A.id, 3, 1), row(B.id, 2, 3)], teacher.id));
    const none = generateRecovery(withLosses(p, rowsFor(p, [3, 4, 5], { status: 'withdrawn' }), teacher.id), ctx, { trigger: { kind: 'LOST_PERIODS' }, actor: teacher });
    expect(none).toBeNull();
  });
});
