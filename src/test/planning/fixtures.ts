import { AcademicConfig, DEFAULT_CONFIG } from '../../lib/planning/calendar';
import { proposeRequirement, review } from '../../lib/planning/governance';
import type { Actor } from '../../lib/planning/governance';
import type { EngineContext } from '../../lib/planning/engine';
import { generateSchedule } from '../../lib/planning/engine';
import { approveDraft, createDraft, Plan } from '../../lib/planning/execution';
import { syllabusFor, VERIFIED_DATASET } from '../../lib/planning/syllabus';
import type { PlanningSubject as PlanningSubjectAlias } from '../../lib/planning/calendar';

export const teacher: Actor = { id: 'user-teacher-1', name: 'Vikram Sengupta', role: 'teacher' };
export const principal: Actor = { id: 'user-principal-1', name: 'Principal', role: 'principal' };
export const admin: Actor = { id: 'user-admin', name: 'Admin', role: 'admin' };

/** Two-week April calendar: 8 weekdays after one holiday and one exam day. */
export const smallConfig: AcademicConfig = {
  ...DEFAULT_CONFIG,
  start: '2026-04-01',
  end: '2027-03-31',
  horizonDays: 10,
  entries: [
    { id: 'h1', type: 'HOLIDAY', label: 'Holiday', start: '2026-04-03', end: '2026-04-03' },
    { id: 'x1', type: 'EXAM', label: 'Unit test', start: '2026-04-06', end: '2026-04-06' },
  ],
  subjectPeriodsPerDay: { Mathematics: 1, Science: 1 },
};

export const emptyCtx = (): EngineContext => ({ datasets: [VERIFIED_DATASET], classifications: {}, relationships: [] });

/** Context in which every unit of the class/subject has an approved requirement of `core` + `nonCore` periods. */
export function requirementCtx(grade: number, subject: PlanningSubjectAlias, core = 2, nonCore = 0, ctx = emptyCtx()): EngineContext {
  let classifications = { ...ctx.classifications };
  for (const u of syllabusFor(VERIFIED_DATASET, grade, subject).units) {
    if (classifications[u.id]) continue;
    const criteria = [...(core > 0 ? ['FOUNDATIONAL_CONCEPT'] : []), ...(nonCore > 0 ? ['ENRICHMENT'] : [])];
    classifications = review(proposeRequirement(classifications, u.id, core, nonCore, criteria, 'Approved test requirement for foundational instruction.', 'Test fixture', teacher), u.id, 'APPROVED', '', principal);
  }
  return { ...ctx, classifications };
}

export function approvedPlan(grade: number, subject: PlanningSubjectAlias, config = smallConfig, perUnit = 2, ctx = emptyCtx()): Plan {
  const view = syllabusFor(VERIFIED_DATASET, grade, subject);
  const estimates = Object.fromEntries(view.units.map((u) => [u.id, perUnit]));
  ctx = { ...ctx, classifications: { ...ctx.classifications } };
  for (const u of view.units) if (!ctx.classifications[u.id]) ctx.classifications = review(proposeRequirement(ctx.classifications, u.id, perUnit, 0, ['FOUNDATIONAL_CONCEPT'], 'Approved test requirement for foundational instruction.', 'Test fixture', teacher), u.id, 'APPROVED', '', principal);
  const draft = createDraft({
    grade,
    subject,
    datasetId: VERIFIED_DATASET.id,
    datasetLabel: VERIFIED_DATASET.label,
    datasetKind: VERIFIED_DATASET.kind,
    createdBy: teacher,
    config,
    estimates,
    draft: generateSchedule({ dataset: VERIFIED_DATASET, units: view.units, grade, subject, config, estimates }, ctx),
  });
  return approveDraft([draft], draft.id, principal, 'ok')[0];
}
