/**
 * Pace: is a class on track, given today's date, the approved schedule and what has actually been taught?
 *
 * Scheduled, taught and covered are three different things and are never merged:
 *   scheduled = a period in the approved timetable;  taught = a classroom period recorded as taught (Daily Curriculum);
 *   covered   = the Curriculum Catalogue's Done / In progress / Not done (a separate state, see coverage.ts).
 * Healthy pace is only ever claimed from TAUGHT periods against the periods that were DUE (scheduled before today); future
 * scheduled periods never make a class look on pace. Core that is overdue, lost and unrecovered, or without any time left is
 * reported as unresolved Core and always makes the plan "behind", regardless of how much Non-Core work is scheduled.
 */
import { summarizeCalendar } from './calendar';
import { isLegacyRequirement, lessonRequirement, slotKind, type PlannedLesson } from './engine';
import { currentVersion, lessonProgress, type Plan } from './execution';
import { effectiveLosses } from './losses';

export type PaceState = 'NOT_STARTED' | 'ON_PACE' | 'AHEAD' | 'BEHIND_NON_CORE' | 'BEHIND_CORE' | 'REQUIREMENTS_MISSING';

export const PACE_LABEL: Record<PaceState, string> = {
  NOT_STARTED: 'Not started',
  ON_PACE: 'On pace',
  AHEAD: 'Ahead of plan',
  BEHIND_NON_CORE: 'Slightly behind',
  BEHIND_CORE: 'Behind on Core',
  REQUIREMENTS_MISSING: 'Requirements missing',
};

export interface PeriodCounts {
  required: number;
  scheduled: number;
  taught: number;
  remaining: number;
  /** Periods scheduled before today and not taught. */
  overdue: number;
}

export interface OwedCore {
  nodeId: string;
  number: string;
  title: string;
  periods: number;
  reason: 'OVERDUE' | 'LOST_AWAITING_RECOVERY' | 'NO_TIME_LEFT';
}

export interface PaceReport {
  asOf: string;
  academicDay: number;
  academicDaysTotal: number;
  /** Teaching days after today. */
  daysRemaining: number;
  /** Periods of this subject from today to the end of the planning horizon. */
  periodsAvailable: number;
  /** Classroom periods still to teach (Core + Non-Core, excluding independent learning). */
  periodsStillNeeded: number;
  /** available - stillNeeded: negative means the remaining syllabus does not fit. */
  spare: number;
  core: PeriodCounts & { unscheduled: number };
  nonCore: PeriodCounts & { independent: number };
  coreOwed: OwedCore[];
  topicsWithoutRequirement: number;
  state: PaceState;
  headline: string;
}

const key = (s: { date: string; period: number }) => `${s.date}#${s.period}`;

function split(lesson: PlannedLesson, taught: number) {
  const req = lessonRequirement(lesson);
  const core = Math.min(req.core, taught);
  const non = Math.max(0, Math.min(req.nonCore, taught - core));
  return { req, taughtCore: core, taughtNon: non };
}

/** The instructional day a date falls on (count of planning days up to and including it) and the calendar extent. */
export function academicDayOf(plan: Plan, asOf: string) {
  const version = currentVersion(plan);
  const days = summarizeCalendar(version?.config ?? plan.config).planningDates;
  return { day: days.filter((d) => d <= asOf).length, total: days.length, days };
}

/** Pace of one approved plan as of a date (yyyy-mm-dd). Null when the plan has no approved schedule. */
export function paceReport(plan: Plan, asOf: string): PaceReport | null {
  if (plan.status !== 'APPROVED') return null;
  const version = currentVersion(plan);
  if (!version) return null;
  const { day, total, days } = academicDayOf(plan, asOf);
  // Revisions may move an overdue unit into future slots, but that does not erase the
  // original obligation or make the class appear on pace. Keep the first approved
  // timetable as the due-date baseline; current-version slots remain the scheduled metric.
  const baselineLessons = plan.versions[0]?.lessons ?? version.lessons;

  const lost = new Set<string>();
  for (const r of effectiveLosses(plan)) for (const p of r.periods ?? []) lost.add(key({ date: r.date, period: p }));
  for (const s of version.lostSlots ?? []) lost.add(key(s));

  const core: PaceReport['core'] = { required: 0, scheduled: 0, taught: 0, remaining: 0, overdue: 0, unscheduled: 0 };
  const nonCore: PaceReport['nonCore'] = { required: 0, scheduled: 0, taught: 0, remaining: 0, overdue: 0, independent: 0 };
  const coreOwed: OwedCore[] = [];
  let topicsWithoutRequirement = 0;

  for (const lesson of version.lessons) {
    if (lesson.requirementStatus === 'MISSING' || isLegacyRequirement(lesson)) {
      topicsWithoutRequirement++;
      continue;
    }
    const pr = lessonProgress(plan, lesson);
    const { req, taughtCore, taughtNon } = split(lesson, pr.taughtPeriods);
    const live = lesson.slots.filter((s) => !lost.has(key(s)));
    const baseline = baselineLessons.find((item) => item.nodeId === lesson.nodeId) ?? lesson;
    const dueCore = baseline.slots.filter((s) => s.date < asOf && slotKind(baseline, s) === 'CORE').length;
    const dueNon = Math.max(0, baseline.slots.filter((s) => s.date < asOf && slotKind(baseline, s) !== 'CORE').length - lesson.independentPeriods);
    core.required += req.core;
    core.scheduled += live.filter((s) => slotKind(lesson, s) === 'CORE').length;
    core.taught += taughtCore;
    core.remaining += Math.max(0, req.core - taughtCore);
    nonCore.required += req.nonCore;
    nonCore.scheduled += live.filter((s) => slotKind(lesson, s) !== 'CORE').length;
    nonCore.taught += taughtNon;
    nonCore.independent += lesson.independentPeriods;
    nonCore.remaining += Math.max(0, req.nonCore - lesson.independentPeriods - taughtNon);
    if (pr.complete) continue;
    const overdueCore = Math.max(0, dueCore - taughtCore);
    const overdueNon = Math.max(0, dueNon - taughtNon);
    core.overdue += overdueCore;
    nonCore.overdue += overdueNon;
    const unscheduled = lesson.coreUnscheduled ?? 0;
    core.unscheduled += unscheduled;
    if (overdueCore > 0) coreOwed.push({ nodeId: lesson.nodeId, number: lesson.number, title: lesson.title, periods: overdueCore, reason: 'OVERDUE' });
    if (unscheduled > 0) {
      const lostHere = (lesson.lossNotes ?? []).some((n) => n.incomplete > 0);
      coreOwed.push({ nodeId: lesson.nodeId, number: lesson.number, title: lesson.title, periods: unscheduled, reason: lostHere ? 'LOST_AWAITING_RECOVERY' : 'NO_TIME_LEFT' });
    }
  }

  const periodsPerDay = (version.config ?? plan.config).subjectPeriodsPerDay[plan.subject] || 0;
  let periodsAvailable = 0;
  for (const d of days) if (d >= asOf) for (let p = 1; p <= periodsPerDay; p++) if (!lost.has(key({ date: d, period: p }))) periodsAvailable++;
  const periodsStillNeeded = core.remaining + nonCore.remaining;
  const spare = periodsAvailable - periodsStillNeeded;

  const dueTotal = version.lessons.reduce((n, l) => {
    const baseline = baselineLessons.find((item) => item.nodeId === l.nodeId) ?? l;
    const due = baseline.slots.filter((s) => s.date < asOf).length;
    return n + Math.max(0, due - l.independentPeriods);
  }, 0);
  const taughtTotal = core.taught + nonCore.taught;
  let state: PaceState;
  let headline: string;
  const coreBehind = core.overdue + core.unscheduled;
  if (topicsWithoutRequirement > 0) {
    state = 'REQUIREMENTS_MISSING';
    headline = `${topicsWithoutRequirement} topic(s) need approved Core and Non-Core period counts before the class pace can be verified.`;
  } else if (day === 0) {
    state = 'NOT_STARTED';
    headline = 'The academic year has not started yet.';
  } else if (coreBehind > 0 || spare < 0) {
    state = 'BEHIND_CORE';
    const parts: string[] = [];
    if (core.overdue > 0) parts.push(`${core.overdue} Core period(s) were due before today and have not been taught`);
    if (core.unscheduled > 0) parts.push(`${core.unscheduled} Core period(s) have no classroom time scheduled`);
    if (spare < 0) parts.push(`the remaining syllabus needs ${-spare} more period(s) than the calendar has left`);
    headline = `Behind on Core: ${parts.join('; ')}.`;
  } else if (nonCore.overdue > 0) {
    state = 'BEHIND_NON_CORE';
    headline = `Slightly behind: ${nonCore.overdue} Non-Core period(s) were due before today and have not been taught. All Core teaching due so far is complete.`;
  } else if (taughtTotal > dueTotal) {
    state = 'AHEAD';
    headline = `Ahead of plan: ${taughtTotal - dueTotal} period(s) taught beyond what was due so far.`;
  } else {
    state = 'ON_PACE';
    headline = 'On pace: all periods due before today have been taught.';
  }

  return {
    asOf,
    academicDay: day,
    academicDaysTotal: total,
    daysRemaining: Math.max(0, total - day),
    periodsAvailable,
    periodsStillNeeded,
    spare,
    core,
    nonCore,
    coreOwed,
    topicsWithoutRequirement,
    state,
    headline,
  };
}

export const todayIso = (now = new Date()) => `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;

/** The planning date: an explicit workspace reference date if one was set, otherwise today's real date. */
export const effectiveAsOf = (workspace: { asOf?: string | null }, now?: Date) => (workspace.asOf && /^\d{4}-\d{2}-\d{2}$/.test(workspace.asOf) ? workspace.asOf : todayIso(now));
