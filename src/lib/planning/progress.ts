/**
 * Single source of truth for instructional progress metrics (Time-Aware Engine, Daily Curriculum, Curriculum
 * Oversight and dashboards all read these functions).
 *
 * Units are never mixed: teaching DAYS and classroom PERIODS are reported separately.
 * Never counted as taught: lost periods, homework / independent learning, proposed (unapproved) recovery, and
 * topics without an approved requirement. Only the current approved schedule version and the execution records
 * drive these numbers; the academic calendar is never modified by them.
 */
import { isLegacyRequirement, lessonRequirement, slotKind, type PlannedLesson, type Slot } from './engine';
import { currentVersion, lessonProgress, pendingProposal, planLabel, type Plan } from './execution';
import { effectiveLosses } from './losses';

const slotKey = (s: Pick<Slot, 'date' | 'period'>) => `${s.date}#${String(s.period).padStart(3, '0')}`;

export interface PlanProgress {
  planId: string;
  grade: number;
  subject: Plan['subject'];
  label: string;
  version: number;
  /** Teaching days (dates with at least one scheduled period of this subject in the approved schedule, lost ones included). */
  teachingDaysTotal: number;
  /** Days whose every remaining (non-lost) classroom period has been taught. */
  teachingDaysCompleted: number;
  /** Days on which every scheduled period was lost (not completed teaching). */
  teachingDaysLost: number;
  teachingDaysRemaining: number;
  /** Periods recorded as lost (effective records). */
  lostPeriodsRecorded: number;
  lostCorePeriods: number;
  lostNonCorePeriods: number;
  /** Lost periods applied in the current approved version (recovery approved). */
  lostPeriodsApplied: number;
  /** Recorded lost periods not yet covered by an approved recovery. */
  unaccountedLostPeriods: number;
  /** Classroom periods actually taught (homework never included). */
  classroomTaught: number;
  /** Classroom periods required (approved requirement minus periods tracked as independent learning). */
  classroomRequired: number;
  classroomRemaining: number;
  classroomPct: number;
  coreRequired: number;
  coreTaught: number;
  coreRemaining: number;
  nonCoreRequired: number;
  nonCoreTaught: number;
  /** Non-Core still needing classroom time (excludes periods moved to independent learning). */
  nonCoreRemaining: number;
  /** Non-Core periods tracked as independent learning / homework — never counted as taught. */
  independentPeriods: number;
  recoveryPending: boolean;
  recoveryRevisions: number;
  rejectedProposals: number;
  /** Lost Core periods covered by approved recovery so far. */
  coreLostApplied: number;
  /** Lost Core periods recovered into classroom slots by approved recovery. */
  coreRecovered: number;
  /** Lost Core periods still awaiting a classroom slot (approved schedule). */
  coreAwaitingRecovery: number;
  /** All Core periods without a classroom slot in the approved schedule (lost and not recovered, or horizon shortfall). */
  coreUnscheduled: number;
  /** Classroom periods (Core + Non-Core) without a slot in the approved schedule for topics not yet taught. */
  unresolvedShortfall: number;
  /** What the pending proposal would do — shown as proposed, never counted as approved. */
  proposed: { coreRecovered: number; coreUnresolved: number; nonCoreToIndependent: number } | null;
  unitsTaught: number;
  unitsTotal: number;
  unitsIncomplete: number;
  homeworkOpen: number;
  /** Topics in the plan without an approved requirement (never scheduled, never counted). */
  unitsWithoutRequirement: number;
}

function remainingNeed(lesson: PlannedLesson, taughtPeriods: number) {
  const req = lessonRequirement(lesson);
  const taughtCore = Math.min(req.core, taughtPeriods);
  const taughtNonCore = Math.max(0, Math.min(req.nonCore, taughtPeriods - taughtCore));
  return {
    core: Math.max(0, req.core - taughtCore),
    nonCore: Math.max(0, req.nonCore - lesson.independentPeriods - taughtNonCore),
    taughtCore,
    taughtNonCore,
  };
}

/**
 * Which approved classroom periods count as taught: for each topic, its first N remaining (non-lost) slots, where N is
 * the number of classroom periods recorded as taught. Used for teaching-day completion only.
 */
function taughtSlotKeys(plan: Plan, lessons: PlannedLesson[], lost: Set<string>): Set<string> {
  const taught = new Set<string>();
  for (const l of lessons) {
    const n = lessonProgress(plan, l).taughtPeriods;
    l.slots.filter((s) => !lost.has(slotKey(s))).slice(0, n).forEach((s) => taught.add(slotKey(s)));
  }
  return taught;
}

/** Progress for one approved plan from its current approved version + execution records + loss records. */
export function planProgress(plan: Plan): PlanProgress | null {
  if (plan.status !== 'APPROVED') return null;
  const version = currentVersion(plan);
  if (!version) return null;

  const losses = effectiveLosses(plan);
  const lost = new Set<string>();
  for (const r of losses) for (const period of r.periods ?? []) lost.add(slotKey({ date: r.date, period }));
  for (const s of version.lostSlots ?? []) lost.add(slotKey(s));

  // Teaching days: every date that has (or had, before a loss) a scheduled period of this subject.
  const dayStatus = new Map<string, { live: number; taught: number }>();
  const taught = taughtSlotKeys(plan, version.lessons, lost);
  for (const l of version.lessons) {
    for (const s of l.slots) {
      const d = dayStatus.get(s.date) ?? { live: 0, taught: 0 };
      if (!lost.has(slotKey(s))) {
        d.live++;
        if (taught.has(slotKey(s))) d.taught++;
      }
      dayStatus.set(s.date, d);
    }
  }
  // Recovery revisions remove old slots from the active timetable. For each date with
  // a recorded loss, consult v1 to decide whether every originally scheduled subject
  // period was actually lost. A selected-period loss must not turn the whole date into
  // a lost teaching day just because later revisions moved its remaining lessons.
  const originalByDate = new Map<string, Set<string>>();
  for (const lesson of plan.versions[0]?.lessons ?? []) {
    for (const slot of lesson.slots) {
      const keys = originalByDate.get(slot.date) ?? new Set<string>();
      keys.add(slotKey(slot));
      originalByDate.set(slot.date, keys);
    }
  }
  const lossDates = new Set([...lost].map((k) => k.split('#')[0]));
  for (const date of lossDates) {
    const originalSlots = originalByDate.get(date);
    if (!originalSlots?.size) continue;
    const survivingOriginal = [...originalSlots].filter((k) => !lost.has(k)).length;
    const d = dayStatus.get(date) ?? { live: 0, taught: 0 };
    d.live = Math.max(d.live, survivingOriginal);
    dayStatus.set(date, d);
  }
  let teachingDaysCompleted = 0;
  let teachingDaysLost = 0;
  for (const d of dayStatus.values()) {
    if (d.live === 0) teachingDaysLost++;
    else if (d.taught === d.live) teachingDaysCompleted++;
  }
  const teachingDaysTotal = dayStatus.size;

  // Lost periods by kind: applied ones from the approved loss notes, unapplied ones from the current schedule.
  const kindOfSlot = new Map<string, 'CORE' | 'NON_CORE'>();
  for (const v of plan.versions) for (const l of v.lessons) for (const s of l.slots) kindOfSlot.set(slotKey(s), slotKind(l, s));
  let lostCorePeriods = 0;
  for (const r of losses) for (const period of r.periods ?? []) if (kindOfSlot.get(slotKey({ date: r.date, period })) === 'CORE') lostCorePeriods++;
  const lostPeriodsRecorded = losses.reduce((s, r) => s + r.periodsLost, 0);

  let classroomTaught = 0;
  let classroomRequired = 0;
  let coreRequired = 0;
  let coreTaught = 0;
  let coreRemaining = 0;
  let nonCoreRequired = 0;
  let nonCoreTaught = 0;
  let nonCoreRemaining = 0;
  let independentPeriods = 0;
  let coreLostApplied = 0;
  let coreRecovered = 0;
  let coreAwaitingRecovery = 0;
  let coreUnscheduled = 0;
  let unresolvedShortfall = 0;
  let unitsTaught = 0;
  let unitsIncomplete = 0;
  let homeworkOpen = 0;
  let unitsWithoutRequirement = 0;

  for (const lesson of version.lessons) {
    if (lesson.requirementStatus === 'MISSING') {
      unitsWithoutRequirement++;
      continue;
    }
    const pr = lessonProgress(plan, lesson);
    if (isLegacyRequirement(lesson)) {
      // Keep a historical total period count visible without inventing a Core/Non-Core split.
      unitsWithoutRequirement++;
      classroomTaught += pr.taughtPeriods;
      classroomRequired += pr.classroomTotal;
      if (pr.complete) unitsTaught++;
      if (!pr.complete && (pr.lastIncomplete || pr.state === 'LOSS_RESCHEDULED')) unitsIncomplete++;
      if (pr.homeworkAssigned && !pr.complete) homeworkOpen++;
      continue;
    }
    const req = lessonRequirement(lesson);
    const need = remainingNeed(lesson, pr.taughtPeriods);
    classroomTaught += pr.taughtPeriods;
    classroomRequired += pr.classroomTotal;
    coreRequired += req.core;
    nonCoreRequired += req.nonCore;
    coreTaught += need.taughtCore;
    nonCoreTaught += need.taughtNonCore;
    coreRemaining += need.core;
    nonCoreRemaining += need.nonCore;
    independentPeriods += lesson.independentPeriods;
    const notes = lesson.lossNotes ?? [];
    const recovered = notes.reduce((s, n) => s + (n.recovered ?? 0), 0);
    const awaiting = notes.reduce((s, n) => s + n.incomplete, 0);
    coreRecovered += recovered;
    coreLostApplied += recovered + awaiting;
    if (!pr.complete) {
      coreAwaitingRecovery += Math.min(awaiting, lesson.coreUnscheduled ?? 0);
      coreUnscheduled += lesson.coreUnscheduled ?? 0;
      unresolvedShortfall += lesson.unscheduledPeriods;
    }
    if (pr.complete) unitsTaught++;
    if (!pr.complete && (pr.lastIncomplete || pr.state === 'LOSS_RESCHEDULED')) unitsIncomplete++;
    if (pr.homeworkAssigned && !pr.complete) homeworkOpen++;
  }

  const lostPeriodsApplied = (version.lostSlots ?? []).length;
  const classroomRemaining = Math.max(0, classroomRequired - classroomTaught);
  const classroomPct = classroomRequired === 0 ? 0 : Math.round((classroomTaught / classroomRequired) * 100);

  const pending = pendingProposal(plan);
  const proposed = pending
    ? {
        coreRecovered: (pending.lossDays ?? []).reduce((s, d) => s + (d.recovered ?? []).reduce((a, x) => a + x.periods, 0), 0),
        coreUnresolved: (pending.lossDays ?? []).reduce((s, d) => s + d.incomplete.reduce((a, x) => a + x.periods, 0), 0),
        nonCoreToIndependent: (pending.lossDays ?? []).reduce((s, d) => s + d.homework.reduce((a, x) => a + x.periods, 0), 0),
      }
    : null;

  return {
    planId: plan.id,
    grade: plan.grade,
    subject: plan.subject,
    label: planLabel(plan),
    version: version.version,
    teachingDaysTotal,
    teachingDaysCompleted,
    teachingDaysLost,
    teachingDaysRemaining: Math.max(0, teachingDaysTotal - teachingDaysCompleted - teachingDaysLost),
    lostPeriodsRecorded,
    lostCorePeriods,
    lostNonCorePeriods: lostPeriodsRecorded - lostCorePeriods,
    lostPeriodsApplied,
    unaccountedLostPeriods: Math.max(0, lostPeriodsRecorded - lostPeriodsApplied),
    classroomTaught,
    classroomRequired,
    classroomRemaining,
    classroomPct,
    coreRequired,
    coreTaught,
    coreRemaining,
    nonCoreRequired,
    nonCoreTaught,
    nonCoreRemaining,
    independentPeriods,
    recoveryPending: !!pending,
    recoveryRevisions: Math.max(0, plan.versions.length - 1),
    rejectedProposals: plan.proposals.filter((x) => x.status === 'REJECTED').length,
    coreLostApplied,
    coreRecovered,
    coreAwaitingRecovery,
    coreUnscheduled,
    unresolvedShortfall,
    proposed,
    unitsTaught,
    unitsTotal: version.lessons.length,
    unitsIncomplete,
    homeworkOpen,
    unitsWithoutRequirement,
  };
}

export interface WorkspaceProgress {
  plans: PlanProgress[];
  teachingDaysCompleted: number;
  teachingDaysRemaining: number;
  teachingDaysLost: number;
  teachingDaysTotal: number;
  lostPeriodsRecorded: number;
  unaccountedLostPeriods: number;
  classroomTaught: number;
  classroomRequired: number;
  classroomPct: number;
  coreRemaining: number;
  nonCoreRemaining: number;
  independentPeriods: number;
  coreRecovered: number;
  coreAwaitingRecovery: number;
  recoveryPending: number;
  unresolvedShortfall: number;
}

/** Aggregate progress across all approved plans (sums of per-plan values; days are subject-teaching days). */
export function workspaceProgress(plans: Plan[]): WorkspaceProgress {
  const list = plans.map(planProgress).filter((x): x is PlanProgress => !!x);
  const sum = (fn: (p: PlanProgress) => number) => list.reduce((s, p) => s + fn(p), 0);
  const classroomRequired = sum((p) => p.classroomRequired);
  const classroomTaught = sum((p) => p.classroomTaught);
  return {
    plans: list,
    teachingDaysCompleted: sum((p) => p.teachingDaysCompleted),
    teachingDaysRemaining: sum((p) => p.teachingDaysRemaining),
    teachingDaysLost: sum((p) => p.teachingDaysLost),
    teachingDaysTotal: sum((p) => p.teachingDaysTotal),
    lostPeriodsRecorded: sum((p) => p.lostPeriodsRecorded),
    unaccountedLostPeriods: sum((p) => p.unaccountedLostPeriods),
    classroomTaught,
    classroomRequired,
    classroomPct: classroomRequired === 0 ? 0 : Math.round((classroomTaught / classroomRequired) * 100),
    coreRemaining: sum((p) => p.coreRemaining),
    nonCoreRemaining: sum((p) => p.nonCoreRemaining),
    independentPeriods: sum((p) => p.independentPeriods),
    coreRecovered: sum((p) => p.coreRecovered),
    coreAwaitingRecovery: sum((p) => p.coreAwaitingRecovery),
    recoveryPending: list.filter((p) => p.recoveryPending).length,
    unresolvedShortfall: sum((p) => p.unresolvedShortfall),
  };
}

export type PeriodStatus = 'TAUGHT' | 'SCHEDULED' | 'LOST' | 'LOST_PENDING' | 'RECOVERED_CORE' | 'MOVED_TO_INDEPENDENT';

export const PERIOD_STATUS_LABEL: Record<PeriodStatus, string> = {
  TAUGHT: 'Taught',
  SCHEDULED: 'Scheduled',
  LOST: 'Lost — recovery approved',
  LOST_PENDING: 'Lost — awaiting recovery approval',
  RECOVERED_CORE: 'Core recovery (approved)',
  MOVED_TO_INDEPENDENT: 'Moved to independent learning',
};

export interface PeriodLedgerRow {
  key: string;
  number: number;
  date: string;
  period: number;
  /** Topic and kind in the original approved schedule (v1). */
  original: { nodeId: string; title: string; kind: 'CORE' | 'NON_CORE' } | null;
  /** Topic and kind in the current approved schedule (null if the period was lost or released). */
  current: { nodeId: string; title: string; kind: 'CORE' | 'NON_CORE' } | null;
  status: PeriodStatus;
  lossReason?: string;
  lossNote?: string;
}

/**
 * Period-by-period view of a plan: original approved schedule vs current approved schedule, with execution and losses.
 * Shares the taught-period attribution used for teaching-day progress.
 */
export function periodLedger(plan: Plan, numbers: Map<string, number>): PeriodLedgerRow[] {
  const version = currentVersion(plan);
  const original = plan.versions[0];
  if (!version || !original) return [];
  const losses = effectiveLosses(plan);
  const lossOf = new Map<string, { reason: string; note: string }>();
  for (const r of losses) for (const period of r.periods ?? []) lossOf.set(slotKey({ date: r.date, period }), { reason: r.reason, note: r.note });
  const applied = new Set((version.lostSlots ?? []).map(slotKey));
  const lost = new Set([...lossOf.keys(), ...applied]);
  const taught = taughtSlotKeys(plan, version.lessons, lost);
  const rows = new Map<string, PeriodLedgerRow>();
  const ensure = (s: Slot) => {
    const k = slotKey(s);
    if (!rows.has(k)) rows.set(k, { key: k, number: numbers.get(k) ?? 0, date: s.date, period: s.period, original: null, current: null, status: 'SCHEDULED' });
    return rows.get(k)!;
  };
  for (const l of original.lessons) for (const s of l.slots) ensure(s).original = { nodeId: l.nodeId, title: l.title, kind: slotKind(l, s) };
  for (const l of version.lessons) for (const s of l.slots) ensure(s).current = { nodeId: l.nodeId, title: l.title, kind: slotKind(l, s) };
  for (const s of version.lostSlots ?? []) ensure(s);
  for (const row of rows.values()) {
    const loss = lossOf.get(row.key);
    if (lost.has(row.key)) {
      row.status = applied.has(row.key) ? 'LOST' : 'LOST_PENDING';
      row.lossReason = loss?.reason;
      row.lossNote = loss?.note;
    } else if (taught.has(row.key)) row.status = 'TAUGHT';
    else if (!row.current) row.status = 'MOVED_TO_INDEPENDENT';
    else if (row.current.kind === 'CORE' && (!row.original || row.original.nodeId !== row.current.nodeId || row.original.kind !== 'CORE')) row.status = 'RECOVERED_CORE';
    else row.status = 'SCHEDULED';
  }
  return [...rows.values()].sort((a, b) => a.key.localeCompare(b.key));
}
