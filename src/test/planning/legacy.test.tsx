import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { generateSchedule, isLegacyRequirement, lessonRequirement, PlannedLesson, requirementSnapshot } from '../../lib/planning/engine';
import { approveDraft, createDraft } from '../../lib/planning/execution';
import { proposeRequirement, review } from '../../lib/planning/governance';
import { paceReport } from '../../lib/planning/pace';
import { planProgress } from '../../lib/planning/progress';
import { syllabusFor, VERIFIED_DATASET } from '../../lib/planning/syllabus';
import { LegacyRequirementNote, ScheduleComparison } from '../../pages/time-aware/planningUi';
import { principal, smallConfig, teacher } from './fixtures';

const view = syllabusFor(VERIFIED_DATASET, 7, 'Mathematics');

function approvedLessons(): PlannedLesson[] {
  let c = {};
  for (const u of view.units) c = review(proposeRequirement(c, u.id, 2, 1, ['FOUNDATIONAL_CONCEPT', 'ENRICHMENT'], 'Explicit fixture requirement for foundational instruction.', 'Fixture', teacher), u.id, 'APPROVED', '', principal);
  const estimates = Object.fromEntries(view.units.map((u) => [u.id, 3]));
  return generateSchedule({ dataset: VERIFIED_DATASET, units: view.units, grade: 7, subject: 'Mathematics', config: smallConfig, estimates }, { datasets: [VERIFIED_DATASET], classifications: c, relationships: [] }).lessons;
}

/** A plan approved before explicit counts existed: only the old single total survives. */
const toLegacy = (l: PlannedLesson): PlannedLesson => ({ ...l, corePeriods: undefined, nonCorePeriods: undefined });

function approvedLegacyPlan() {
  const generated = generateSchedule({ dataset: VERIFIED_DATASET, units: view.units, grade: 7, subject: 'Mathematics', config: smallConfig }, { datasets: [VERIFIED_DATASET], classifications: (() => { let c = {}; for (const u of view.units) c = review(proposeRequirement(c, u.id, 2, 1, ['FOUNDATIONAL_CONCEPT', 'ENRICHMENT'], 'Explicit fixture requirement for foundational instruction.', 'Fixture', teacher), u.id, 'APPROVED', '', principal); return c; })(), relationships: [] });
  const legacy = { ...generated, lessons: generated.lessons.map(toLegacy) };
  const draft = createDraft({ grade: 7, subject: 'Mathematics', datasetId: VERIFIED_DATASET.id, datasetLabel: VERIFIED_DATASET.label, datasetKind: VERIFIED_DATASET.kind, createdBy: teacher, config: smallConfig, estimates: requirementSnapshot(generated.lessons), draft: legacy });
  return approveDraft([draft], draft.id, principal, '')[0];
}

describe('legacy single-total requirements', () => {
  it('a freshly approved split is not legacy; a bare total is', () => {
    const [fresh] = approvedLessons();
    expect(isLegacyRequirement(fresh)).toBe(false);
    expect(lessonRequirement(fresh)).toEqual({ core: fresh.corePeriods, nonCore: fresh.nonCorePeriods });
    expect(isLegacyRequirement(toLegacy(fresh))).toBe(true);
  });

  it('the display fallback never makes a legacy total look like an approved split', () => {
    const legacy = toLegacy(approvedLessons()[0]);
    expect(isLegacyRequirement(legacy)).toBe(true);
    expect(legacy.corePeriods).toBeUndefined();
    expect(legacy.nonCorePeriods).toBeUndefined();
  });

  it('shows a visible warning only for legacy lessons', () => {
    const [fresh, other] = approvedLessons();
    const { rerender } = render(<LegacyRequirementNote lesson={fresh} />);
    expect(screen.queryByRole('note')).toBeNull();
    rerender(<LegacyRequirementNote lesson={toLegacy(other)} />);
    expect(screen.getByRole('note').textContent).toMatch(/Legacy requirement.*no approved Core\/Non-Core split.*cannot be used as an approved requirement/);
  });

  it('the schedule comparison table flags legacy rows', () => {
    const lessons = approvedLessons();
    const mixed = lessons.map((l, i) => (i === 0 ? toLegacy(l) : l));
    render(<ScheduleComparison columns={[{ label: 'Approved', lessons: mixed }]} />);
    expect(screen.getByTestId(`legacy-${mixed[0].nodeId}`)).toBeTruthy();
    expect(screen.queryAllByRole('note')).toHaveLength(1);
  });

  it('does not guess Core/Non-Core pace from a legacy total-period plan', () => {
    const plan = approvedLegacyPlan();
    const progress = planProgress(plan)!;
    const pace = paceReport(plan, '2026-04-08')!;
    expect(progress.classroomRequired).toBeGreaterThan(0);
    expect(progress.coreRequired).toBe(0);
    expect(progress.nonCoreRequired).toBe(0);
    expect(progress.unitsWithoutRequirement).toBe(view.units.length);
    expect(pace.topicsWithoutRequirement).toBe(view.units.length);
    expect(pace.state).toBe('REQUIREMENTS_MISSING');
    expect(pace.headline).toMatch(/approved Core and Non-Core period counts/);
  });
});
