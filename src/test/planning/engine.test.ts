import { describe, expect, it } from 'vitest';
import { PLANNING_GRADES, PLANNING_SUBJECTS, summarizeCalendar } from '../../lib/planning/calendar';
import { crossCurricularSummary, generateSchedule } from '../../lib/planning/engine';
import { Classifications, propose, proposeRequirement, review, Relationship, validateProposal, validateRelationship } from '../../lib/planning/governance';
import { practiceItems, SyllabusDataset, syllabusFor, validateImport, VERIFIED_DATASET } from '../../lib/planning/syllabus';
import { admin, principal, smallConfig, teacher } from './fixtures';

const view7 = syllabusFor(VERIFIED_DATASET, 7, 'Mathematics');
const est = (n: number, v = view7) => Object.fromEntries(v.units.map((u) => [u.id, n]));
const gen = (estimates: Record<string, number>, classifications: Classifications = {}, relationships: Relationship[] = [], config = smallConfig, v = view7, subject: 'Mathematics' | 'Science' = 'Mathematics') => {
  const c = { ...classifications };
  for (const u of v.units) if (!c[u.id]) c[u.id] = review(proposeRequirement({}, u.id, estimates[u.id], 0, ['FOUNDATIONAL_CONCEPT'], 'Explicit fixture requirement for foundational instruction.', 'Fixture', teacher), u.id, 'APPROVED', '', principal)[u.id];
  return generateSchedule({ dataset: VERIFIED_DATASET, units: v.units, grade: v.units[0]?.grade ?? 7, subject, config, estimates }, { datasets: [VERIFIED_DATASET], classifications: c, relationships });
};

const approveAs = (c: Classifications, nodeId: string, value: 'CORE' | 'NON_CORE') =>
  review(proposeRequirement(c, nodeId, value === 'CORE' ? 8 : 0, value === 'NON_CORE' ? 8 : 0, value === 'CORE' ? ['FOUNDATIONAL_CONCEPT'] : ['ENRICHMENT'], 'Pedagogical reasoning recorded for testing purposes.', 'Chapter PDF p1', teacher), nodeId, 'APPROVED', 'ok', principal);

describe('syllabus data layer', () => {
  it('provides source-checked units with provenance for all six combinations', () => {
    for (const g of PLANNING_GRADES)
      for (const s of PLANNING_SUBJECTS) {
        const v = syllabusFor(VERIFIED_DATASET, g, s);
        expect(v.units.length).toBeGreaterThan(0);
        expect(v.textbooks.length).toBeGreaterThan(0);
        v.units.forEach((u) => {
          expect(u.provenance.locator).toMatch(/PDF p\d+/);
          expect(u.provenance.verification).toBe('SOURCE_VERIFIED_FOR_HEADING_AND_SECTION_MEMBERSHIP');
        });
      }
    expect(VERIFIED_DATASET.nodes.filter((n) => n.kind !== 'CHAPTER')).toHaveLength(10);
    expect(VERIFIED_DATASET.textbooks.every((t) => t.language === 'en' && t.edition)).toBe(true);
  });

  it('marks outcome links as inferred and stores no official wording', () => {
    expect(view7.outcomes).toHaveLength(1);
    const o = view7.outcomes[0];
    expect(o.inferred).toBe(true);
    expect(o.linkVerification).toBe('AWAITING_REVIEW');
    expect(o.linkedNodeIds).toHaveLength(2);
  });

  it('carries no Core/Non-Core classification at ingestion, and rejects it on import', () => {
    expect(JSON.stringify(VERIFIED_DATASET)).not.toMatch(/"(CORE|NON_CORE)"/);
    const bad = validateImport(JSON.stringify({ label: 'x', textbooks: [{ id: 'b', grade: 7, subject: 'Mathematics', title: 'T', edition: 'E' }], nodes: [{ id: 'c', textbookId: 'b', kind: 'CHAPTER', title: 'C', sourceLocator: 'p1', classification: 'Core' }] }), [], 'Admin');
    expect(bad.errors.join()).toMatch(/not accepted during ingestion/);
  });

  it('validates imports and labels them unverified', () => {
    expect(validateImport('nope', [], 'A').errors).toEqual(['The file is not valid JSON.']);
    const ok = validateImport(
      JSON.stringify({
        label: 'School list',
        textbooks: [{ id: 'b', grade: 7, subject: 'Science', title: 'T', edition: 'E' }],
        nodes: [
          { id: 'c', textbookId: 'b', kind: 'CHAPTER', title: 'C', sourceLocator: 'p1' },
          { id: 't', textbookId: 'b', kind: 'TOPIC', parentId: 'c', title: 'Topic 1', sourceLocator: 'p2' },
          { id: 'a', textbookId: 'b', kind: 'ACTIVITY', parentId: 't', title: 'Activity 1', sourceLocator: 'p3' },
          { id: 'x', textbookId: 'b', kind: 'EXERCISE', parentId: 't', title: 'Ex 1', sourceLocator: 'p4' },
        ],
      }),
      [],
      'Admin',
    );
    expect(ok.errors).toEqual([]);
    expect(ok.dataset!.kind).toBe('SCHOOL_IMPORT');
    const v = syllabusFor(ok.dataset!, 7, 'Science');
    expect(v.units.map((u) => u.kind)).toEqual(['TOPIC']); // activities/exercises stay attached resources, never separately timed
    expect(v.nodes.some((n) => n.kind === 'ACTIVITY')).toBe(true); // ...but are preserved in the catalogue
    expect(practiceItems(ok.dataset!, 't').map((n) => n.id).sort()).toEqual(['a', 'x']);
  });
});

describe('time-aware scheduling', () => {
  it('allocates the remaining schedule after the reference day and recalculates available periods', () => {
    const after = summarizeCalendar(smallConfig).planningDates[2];
    const r = generateSchedule({ dataset: VERIFIED_DATASET, units: view7.units, grade: 7, subject: 'Mathematics', config: smallConfig, after }, { datasets: [VERIFIED_DATASET], classifications: Object.fromEntries(view7.units.map((u) => [u.id, review(proposeRequirement({}, u.id, 3, 0, ['FOUNDATIONAL_CONCEPT'], 'Approved fixture requirement.', 'Fixture', teacher), u.id, 'APPROVED', '', principal)[u.id]])), relationships: [] });
    expect(r.metrics.availablePeriods).toBe((summarizeCalendar(smallConfig).planningDates.length - 3) * smallConfig.subjectPeriodsPerDay.Mathematics);
    expect(r.lessons.flatMap((l) => l.slots).every((slot) => slot.date > after)).toBe(true);
    expect(r.metrics.scheduledPeriods + r.metrics.unscheduledPeriods).toBe(r.metrics.requiredPeriods);
  });

  it('generates an actual dated schedule from the syllabus and saved configuration', () => {
    const r = gen(est(3));
    expect(r.metrics.availablePeriods).toBe(10);
    expect(r.metrics.requiredPeriods).toBe(6);
    expect(r.lessons.map((l) => l.title)).toEqual(['Multiplication of Fractions', 'Division of Fractions']);
    expect(r.lessons[0].slots.map((s) => s.date)).toEqual(['2026-04-01', '2026-04-02', '2026-04-07']); // skips holiday and exam day
    expect(r.lessons[1].slots[0].date).toBe('2026-04-08');
    expect(r.lessons[0].chapterTitle).toBe('Working with Fractions');
    expect(r.conflicts).toEqual([]);
  });

  it('recalculates when the configuration changes', () => {
    const a = gen(est(3));
    const b = gen(est(3), {}, [], { ...smallConfig, subjectPeriodsPerDay: { Mathematics: 2, Science: 1 } });
    expect(b.metrics.availablePeriods).toBe(20);
    expect(b.lessons[1].slots[0].date).not.toBe(a.lessons[1].slots[0].date);
  });

  it('reports insufficient time and keeps every unit (pending units are never reduced)', () => {
    const r = gen(est(8));
    expect(r.lessons).toHaveLength(2);
    expect(r.metrics.unscheduledPeriods).toBe(6);
    expect(r.lessons[1].unscheduledPeriods).toBe(6);
    expect(r.lessons.every((l) => l.independentPeriods === 0)).toBe(true);
    expect(r.conflicts.find((c) => c.code === 'TIME_SHORTFALL')!.message).toMatch(/Insufficient instructional time: 6/);
  });

  it('reduces only approved Non-Core classroom time, tracks it, and protects Core', () => {
    let c: Classifications = {};
    c = approveAs(c, view7.units[0].id, 'CORE');
    c = approveAs(c, view7.units[1].id, 'NON_CORE');
    const r = gen(est(8), c);
    expect(r.lessons[0].classroomPeriods).toBe(8);
    expect(r.lessons[1].classroomPeriods).toBe(2);
    expect(r.lessons[1].independentPeriods).toBe(6);
    expect(r.lessons[1].explanation.join(' ')).toMatch(/independent learning/);
    expect(r.metrics.unscheduledPeriods).toBe(0);
    expect(r.metrics.core.scheduledPeriods).toBe(8);
  });

  it('a proposed (unapproved) classification has no effect on scheduling', () => {
    const c = propose({}, view7.units[1].id, 'NON_CORE', ['ENRICHMENT'], 'Pedagogical reasoning recorded for testing.', 'p1', teacher);
    expect(gen(est(8), c).lessons[1].independentPeriods).toBe(0);
  });

  it('rejects time shortage as a reason to classify Non-Core, and self-approval', () => {
    expect(validateProposal('NON_CORE', ['ENRICHMENT'], 'There is insufficient time in the calendar for this', 'p1').join()).toMatch(/not a valid reason/);
    const c = propose({}, 'n', 'CORE', ['FOUNDATIONAL_CONCEPT'], 'Pedagogical reasoning recorded.....', 'p1', principal);
    expect(() => review(c, 'n', 'APPROVED', '', principal)).toThrow(/proposer cannot approve/);
    expect(() => review(c, 'n', 'APPROVED', '', teacher)).toThrow(/Admin or Principal/);
    expect(review(c, 'n', 'APPROVED', '', admin).n.reviewedBy).toEqual(admin);
  });

  it('flags prerequisite ordering conflicts from approved relationships', () => {
    const [mult, div] = view7.units;
    const rel: Relationship = {
      id: 'r', type: 'PREREQUISITE', fromNodeId: div.id, toNodeId: mult.id, explanation: 'x'.repeat(25), evidence: 'e', sharedPeriods: 0, leadNodeId: null,
      status: 'APPROVED', proposedBy: teacher, proposedAt: '2026-11-10',
    };
    expect(gen(est(2), {}, [rel]).conflicts.map((c) => c.code)).toContain('PREREQUISITE_ORDER');
    expect(gen(est(2), {}, [{ ...rel, status: 'PROPOSED' }]).conflicts.map((c) => c.code)).not.toContain('PREREQUISITE_ORDER');
  });

  it('reports missing syllabus data instead of inventing units', () => {
    const empty: SyllabusDataset = { ...VERIFIED_DATASET, id: 'empty', nodes: [], outcomes: [] };
    const v = syllabusFor(empty, 7, 'Mathematics');
    const r = generateSchedule({ dataset: empty, units: v.units, grade: 7, subject: 'Mathematics', config: smallConfig, estimates: {} }, { datasets: [empty], classifications: {}, relationships: [] });
    expect(r.lessons).toEqual([]);
    expect(r.conflicts[0].code).toBe('NO_SYLLABUS');
  });
});

describe('cross-curricular synergy', () => {
  const math = syllabusFor(VERIFIED_DATASET, 8, 'Mathematics').units[0];
  const sci = syllabusFor(VERIFIED_DATASET, 8, 'Science').units[0];
  const link: Relationship = {
    id: 'x', type: 'CROSS_CURRICULAR', fromNodeId: math.id, toNodeId: sci.id, explanation: 'Test-only link to exercise the accounting rules.', evidence: 'test fixture',
    sharedPeriods: 1, leadNodeId: math.id, status: 'APPROVED', proposedBy: teacher, proposedAt: '2026-11-10',
  };

  it('validates that a link joins Mathematics and Science with evidence', () => {
    expect(validateRelationship({ ...link, toNodeId: math.id }, math, math, []).join()).toMatch(/itself|Mathematics and Science/);
    expect(validateRelationship({ ...link, evidence: '' }, math, sci, []).join()).toMatch(/Evidence/);
    expect(validateRelationship(link, math, sci, [link]).join()).toMatch(/already been proposed/);
  });

  it('counts shared time and outcomes once while keeping both units visible', () => {
    const vm = syllabusFor(VERIFIED_DATASET, 8, 'Mathematics');
    const vs = syllabusFor(VERIFIED_DATASET, 8, 'Science');
    const m = gen(est(3, vm), {}, [link], smallConfig, vm, 'Mathematics');
    const s = gen(est(3, vs), {}, [link], smallConfig, vs, 'Science');
    const sciLesson = s.lessons.find((l) => l.nodeId === sci.id)!;
    expect(m.lessons.find((l) => l.nodeId === math.id)!.requiredPeriods).toBe(3); // lead keeps full time
    expect(sciLesson.requiredPeriods).toBe(2); // shared period not double-counted
    expect(sciLesson.explanation.join()).toMatch(/not double-counted/);
    expect(s.lessons).toHaveLength(2); // still visible in Science
    const sum = crossCurricularSummary([m.lessons, s.lessons], [link]);
    expect(sum.links).toHaveLength(1);
    expect(sum.sharedPeriodsCountedOnce).toBe(1);
    expect(sum.uniqueOutcomes).toBeLessThanOrEqual(sum.naiveOutcomeCount);
  });

  it('ignores links that are not approved', () => {
    const vs = syllabusFor(VERIFIED_DATASET, 8, 'Science');
    const s = gen(est(3, vs), {}, [{ ...link, status: 'PROPOSED' }], smallConfig, vs, 'Science');
    expect(s.lessons.find((l) => l.nodeId === sci.id)!.requiredPeriods).toBe(3);
  });
});
