import { describe, expect, it } from 'vitest';
import { generateSchedule } from '../../lib/planning/engine';
import {
  COVERAGE_COLOR,
  COVERAGE_LABEL,
  COVERAGE_STATUSES,
  chapterStatus,
  coverageAfterExecution,
  executionEvidence,
  setCoverage,
  statusOf,
  summarizeCoverage,
  summarizeStatuses,
  type Coverage,
} from '../../lib/planning/coverage';
import { approveRecovery, currentVersion, lessonProgress, recordAndPropose, recordExecution, type Plan } from '../../lib/planning/execution';
import { defaultDatasetFor, eligibleUnits, syllabusFor, validateImport, VERIFIED_DATASET } from '../../lib/planning/syllabus';
import { admin, approvedPlan, emptyCtx, principal, requirementCtx, smallConfig, teacher } from './fixtures';

const ctx = emptyCtx();
const lesson0 = (p: Plan) => currentVersion(p)!.lessons[0];
const cov = (c: Coverage, id: string) => statusOf(c, id);

describe('the three coverage statuses', () => {
  it('are exactly Done, Not done and In progress with the specified colours', () => {
    expect(COVERAGE_STATUSES).toEqual(['DONE', 'NOT_DONE', 'IN_PROGRESS']);
    expect(Object.values(COVERAGE_LABEL)).toEqual(['Done', 'Not done', 'In progress']);
    expect(COVERAGE_COLOR).toEqual({ DONE: '#16A34A', NOT_DONE: '#9CA3AF', IN_PROGRESS: '#F59E0B' });
  });

  it('rejects any other status', () => {
    expect(() => setCoverage({}, 'n', 'VERIFIED' as never, teacher, 'MANUAL')).toThrow(/Unknown coverage status/);
    expect(() => setCoverage({}, 'n', 'PARTIAL' as never, teacher, 'MANUAL')).toThrow();
  });

  it('an unrecorded topic is Not done; every change appends history and keeps one authoritative record', () => {
    let c: Coverage = {};
    expect(statusOf(c, 'n')).toBe('NOT_DONE');
    c = setCoverage(c, 'n', 'IN_PROGRESS', teacher, 'MANUAL', '2026-04-01T09:00:00Z');
    c = setCoverage(c, 'n', 'DONE', teacher, 'MANUAL', '2026-04-02T09:00:00Z');
    c = setCoverage(c, 'n', 'NOT_DONE', admin, 'MANUAL', '2026-04-03T09:00:00Z', 'corrected');
    expect(Object.keys(c)).toEqual(['n']);
    expect(c.n.status).toBe('NOT_DONE');
    expect(c.n.history.map((h) => h.status)).toEqual(['IN_PROGRESS', 'DONE', 'NOT_DONE']);
    expect(c.n.history[2]).toMatchObject({ by: admin, note: 'corrected' });
    // no-op changes return the same object (no spurious history)
    expect(setCoverage(c, 'n', 'NOT_DONE', teacher, 'MANUAL')).toBe(c);
  });
});

describe('coverage calculations', () => {
  it('percentage is Done / Total; in progress does not count; counts are separate', () => {
    const s = summarizeStatuses(['DONE', 'IN_PROGRESS', 'NOT_DONE', 'NOT_DONE']);
    expect(s).toEqual({ total: 4, done: 1, inProgress: 1, notDone: 2, percent: 25 });
    expect(summarizeStatuses(['DONE', 'NOT_DONE', 'NOT_DONE']).percent).toBe(33.3);
    expect(summarizeStatuses(['IN_PROGRESS', 'IN_PROGRESS']).percent).toBe(0);
    expect(summarizeStatuses(['DONE', 'DONE']).percent).toBe(100);
  });

  it('an empty syllabus never divides by zero', () => {
    expect(summarizeStatuses([])).toEqual({ total: 0, done: 0, inProgress: 0, notDone: 0, percent: 0 });
    expect(summarizeCoverage([], {})).toMatchObject({ total: 0, percent: 0 });
    expect(chapterStatus([])).toBeNull();
  });

  it('chapter status is calculated from its topics', () => {
    expect(chapterStatus(['DONE', 'DONE'])).toBe('DONE');
    expect(chapterStatus(['NOT_DONE', 'NOT_DONE'])).toBe('NOT_DONE');
    expect(chapterStatus(['DONE', 'NOT_DONE'])).toBe('IN_PROGRESS');
    expect(chapterStatus(['IN_PROGRESS', 'IN_PROGRESS'])).toBe('IN_PROGRESS');
    expect(chapterStatus(['DONE', 'IN_PROGRESS', 'NOT_DONE'])).toBe('IN_PROGRESS');
  });

  it('subject summary is derived from every eligible topic of the class and subject', () => {
    const units = syllabusFor(VERIFIED_DATASET, 7, 'Mathematics').units;
    const c = setCoverage({}, units[0].id, 'DONE', teacher, 'MANUAL');
    expect(summarizeCoverage(units, c)).toMatchObject({ total: units.length, done: 1, notDone: units.length - 1 });
  });
});

describe('one rule for what is a teachable topic (shared by Course Curriculum and the Time-Aware Engine)', () => {
  const json = JSON.stringify({
    label: 'Fixture',
    textbooks: [{ id: 'tb', grade: 6, subject: 'Mathematics', title: 'T', edition: 'E' }],
    nodes: [
      { id: 'c1', textbookId: 'tb', kind: 'CHAPTER', number: '1', title: 'Chapter', sourceLocator: 'p1' },
      { id: 't1', textbookId: 'tb', kind: 'TOPIC', parentId: 'c1', title: 'Parent heading', sourceLocator: 'p2' },
      { id: 's1', textbookId: 'tb', kind: 'SUBTOPIC', parentId: 't1', title: 'Sub A', sourceLocator: 'p3' },
      { id: 's2', textbookId: 'tb', kind: 'SUBTOPIC', parentId: 't1', title: 'Sub B', sourceLocator: 'p4' },
      { id: 'a1', textbookId: 'tb', kind: 'ACTIVITY', parentId: 's1', title: 'Activity', sourceLocator: 'p3' },
      { id: 'i1', textbookId: 'tb', kind: 'INVESTIGATION', parentId: 's2', title: 'Investigation', sourceLocator: 'p4' },
      { id: 'e1', textbookId: 'tb', kind: 'EXERCISE', parentId: 's2', title: 'Exercise', sourceLocator: 'p4' },
      { id: 't2', textbookId: 'tb', kind: 'TOPIC', parentId: 'c1', title: 'Leaf topic', sourceLocator: 'p5' },
    ],
  });
  const ds = validateImport(json, [], 'Admin').dataset!;

  it('parents with teachable children and every resource are excluded; leaves are counted once', () => {
    const view = syllabusFor(ds, 6, 'Mathematics');
    expect(view.units.map((u) => u.id)).toEqual(['s1', 's2', 't2']);
    expect(eligibleUnits(ds.nodes).map((n) => n.id)).toEqual(['s1', 's2', 't2']);
    ['t1', 'a1', 'i1', 'e1', 'c1'].forEach((id) => expect(view.units.some((u) => u.id === id)).toBe(false));
  });

  it('the Time-Aware allocator schedules exactly the same topics, with the same identities, even without requirements', () => {
    const view = syllabusFor(ds, 6, 'Mathematics');
    const result = generateSchedule({ dataset: ds, units: view.units, grade: 6, subject: 'Mathematics', config: smallConfig }, { datasets: [ds], classifications: {}, relationships: [] });
    expect(result.lessons.map((l) => l.nodeId)).toEqual(view.units.map((u) => u.id));
    expect(result.lessons.map((l) => l.title)).toEqual(view.units.map((u) => u.title));
    // A missing approved requirement flags the topic; it is not dropped
    expect(result.lessons.every((l) => l.requirementStatus === 'MISSING')).toBe(true);
  });

  it('the dataset with the most teachable topics is the default for both modules', () => {
    expect(defaultDatasetFor([VERIFIED_DATASET, ds], 6, 'Mathematics').id).toBe(ds.id);
    expect(defaultDatasetFor([VERIFIED_DATASET, ds], 7, 'Mathematics').id).toBe(VERIFIED_DATASET.id);
  });

  it('refuses a repeated import when the stable textbook and node identities already exist', () => {
    const existingIds = [...ds.textbooks.map((book) => book.id), ...ds.nodes.map((node) => node.id)];
    const repeated = validateImport(json, existingIds, 'Admin');
    expect(repeated.dataset).toBeUndefined();
    expect(repeated.errors.join(' ')).toMatch(/already exists/);
  });
});

describe('classroom execution and coverage', () => {
  it('scheduling, opening and approving a schedule never makes a topic Done', () => {
    const p = approvedPlan(7, 'Mathematics', smallConfig, 3);
    expect(Object.keys(executionEvidence([p]))).toEqual(currentVersion(p)!.lessons.map((l) => l.nodeId));
    Object.values(executionEvidence([p])).forEach((e) => expect(e).toEqual({ complete: false, taughtPeriods: 0 }));
    expect(statusOf({}, lesson0(p).nodeId)).toBe('NOT_DONE');
  });

  it('a topic with several periods is In progress after a partial period and Done only when its required teaching is complete', () => {
    const p = approvedPlan(7, 'Mathematics', smallConfig, 3);
    const l = lesson0(p);
    const partial = recordExecution(p, { nodeId: l.nodeId, date: '2026-04-01', status: 'PARTIAL', periodsTaught: 1 }, teacher);
    let c = coverageAfterExecution({}, partial, l.nodeId, teacher);
    expect(cov(c, l.nodeId)).toBe('IN_PROGRESS');
    expect(c[l.nodeId].source).toBe('EXECUTION');
    const taught = recordExecution(partial, { nodeId: l.nodeId, date: '2026-04-02', status: 'TAUGHT' }, teacher);
    expect(lessonProgress(taught, l).complete).toBe(true);
    c = coverageAfterExecution(c, taught, l.nodeId, teacher);
    expect(cov(c, l.nodeId)).toBe('DONE');
    expect(c[l.nodeId].history.map((h) => h.status)).toEqual(['IN_PROGRESS', 'DONE']);
  });

  it('homework assigned, homework completed and a deferral never create coverage', () => {
    const p = approvedPlan(7, 'Mathematics', smallConfig, 3);
    const l = lesson0(p);
    const hw = recordAndPropose(p, { nodeId: l.nodeId, date: '2026-04-01', status: 'HOMEWORK' }, teacher, ctx).plan;
    expect(coverageAfterExecution({}, hw, l.nodeId, teacher)).toEqual({});
    const sub = recordExecution(hw, { nodeId: l.nodeId, date: '2026-04-01', status: 'HOMEWORK_COMPLETED' }, teacher);
    expect(coverageAfterExecution({}, sub, l.nodeId, teacher)).toEqual({});
    const deferred = recordAndPropose(p, { nodeId: l.nodeId, date: '2026-04-01', status: 'DEFERRED' }, teacher, ctx).plan;
    expect(coverageAfterExecution({}, deferred, l.nodeId, teacher)).toEqual({});
  });

  it('an approved recovery schedule changes neither coverage nor classroom evidence', () => {
    const p = approvedPlan(7, 'Mathematics', smallConfig, 3);
    const l = lesson0(p);
    const r = recordAndPropose(p, { nodeId: l.nodeId, date: '2026-04-01', status: 'HOMEWORK' }, teacher, ctx);
    const proposal = r.proposal!;
    const plan2 = approveRecovery({ ...r.plan, proposals: [...r.plan.proposals] }, proposal.id, principal, 'ok');
    const existing: Coverage = setCoverage({}, l.nodeId, 'IN_PROGRESS', teacher, 'MANUAL');
    expect(currentVersion(plan2)!.version).toBe(2);
    expect(existing[l.nodeId].status).toBe('IN_PROGRESS'); // coverage lives outside the schedule versions
    expect(executionEvidence([plan2])[l.nodeId].complete).toBe(false);
    expect(coverageAfterExecution(existing, plan2, l.nodeId, teacher)).toBe(existing);
  });

  it('manual and execution-derived changes never silently contradict: newest wins and both are in the history', () => {
    const p = approvedPlan(7, 'Mathematics', smallConfig, 3);
    const l = lesson0(p);
    const taught = recordExecution(p, { nodeId: l.nodeId, date: '2026-04-01', status: 'TAUGHT' }, teacher);
    // teacher manually marks In progress first; later classroom completion raises it to Done (recorded as EXECUTION)
    let c = setCoverage({}, l.nodeId, 'IN_PROGRESS', teacher, 'MANUAL');
    c = coverageAfterExecution(c, taught, l.nodeId, teacher);
    expect(cov(c, l.nodeId)).toBe('DONE');
    expect(c[l.nodeId].history.map((h) => `${h.source}:${h.status}`)).toEqual(['MANUAL:IN_PROGRESS', 'EXECUTION:DONE']);
    // a manual downgrade afterwards is allowed, recorded, and the page can still show the classroom evidence
    c = setCoverage(c, l.nodeId, 'NOT_DONE', teacher, 'MANUAL');
    expect(cov(c, l.nodeId)).toBe('NOT_DONE');
    expect(executionEvidence([taught])[l.nodeId].complete).toBe(true);
    // a manual Done is never lowered by weaker classroom evidence
    const partial = recordExecution(p, { nodeId: l.nodeId, date: '2026-04-01', status: 'PARTIAL', periodsTaught: 1 }, teacher);
    const manualDone = setCoverage({}, l.nodeId, 'DONE', teacher, 'MANUAL');
    expect(coverageAfterExecution(manualDone, partial, l.nodeId, teacher)).toBe(manualDone);
  });

  it('a corrected classroom record withdraws an execution-derived Done', () => {
    const p = approvedPlan(7, 'Mathematics', smallConfig, 3);
    const l = lesson0(p);
    const taught = recordExecution(p, { nodeId: l.nodeId, date: '2026-04-01', status: 'TAUGHT' }, teacher);
    let c = coverageAfterExecution({}, taught, l.nodeId, teacher);
    expect(cov(c, l.nodeId)).toBe('DONE');
    const corrected = recordExecution(taught, { nodeId: l.nodeId, date: '2026-04-01', status: 'HOMEWORK' }, teacher);
    c = coverageAfterExecution(c, corrected, l.nodeId, teacher);
    expect(cov(c, l.nodeId)).toBe('NOT_DONE');
    expect(c[l.nodeId].history.map((h) => h.status)).toEqual(['DONE', 'NOT_DONE']);
  });

  it('requirements are irrelevant to coverage: topics without approved periods still have a status', () => {
    const units = syllabusFor(VERIFIED_DATASET, 8, 'Science').units;
    const result = generateSchedule({ dataset: VERIFIED_DATASET, units, grade: 8, subject: 'Science', config: smallConfig }, ctx);
    expect(result.lessons.every((l) => l.requirementStatus === 'MISSING')).toBe(true);
    expect(units.every((u) => statusOf({}, u.id) === 'NOT_DONE')).toBe(true);
    const withReq = requirementCtx(8, 'Science', 2, 1);
    expect(withReq.classifications[units[0].id]).toBeDefined();
  });
});
