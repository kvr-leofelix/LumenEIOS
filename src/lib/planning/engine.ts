/**
 * Time-Aware scheduling engine.
 *
 * Class counts come from each topic's APPROVED instructional requirement: required Core periods and required
 * Non-Core periods (governance.ts). There is no Core/Non-Core ratio or percentage anywhere in scheduling: a topic
 * requiring 3 Core + 1 Non-Core receives exactly 3 Core and 1 Non-Core period. A topic without an approved
 * requirement receives no periods and is flagged; a requirement is never invented.
 *
 * Policy, applied in order and explained per topic:
 *  1. Approved cross-curricular links: shared periods are taught once, in the lead topic; the other topic's required
 *     periods are reduced by the shared amount (Core first, then Non-Core), so time is never double-counted.
 *  2. Topics are scheduled in textbook order; within a topic its Core periods come first, then its Non-Core periods.
 *  3. Only if the required periods exceed the available periods, approved Non-Core periods (from the end of the
 *     sequence) move to tracked independent learning. Core periods are never reduced; any remaining shortfall is left
 *     unscheduled and reported. No topic is dropped.
 */
import { AcademicConfig, PlanningSubject, summarizeCalendar, GRADE_LABEL } from './calendar';
import { approvedRequirement, Classifications, Relationship } from './governance';
import type { OutcomeReference, SyllabusDataset, SyllabusNode } from './syllabus';
import { chapterOf, findNode } from './syllabus';

export type PeriodKind = 'CORE' | 'NON_CORE';

export interface Slot {
  date: string;
  /** Subject period index on that date (1 … subject periods per day). */
  period: number;
  /** Which part of the topic's requirement this classroom period serves. */
  kind?: PeriodKind;
}

export type UnitClass = 'CORE' | 'NON_CORE' | 'MIXED' | 'PENDING';

export interface PlannedLesson {
  nodeId: string;
  grade: number;
  subject: PlanningSubject;
  chapterTitle: string;
  chapterNumber: string;
  number: string;
  title: string;
  kind: string;
  outcomeIds: string[];
  classification: UnitClass;
  /** Total approved requirement (Core + Non-Core) before shared-period reduction. */
  estimatedPeriods: number;
  sharedReduction: number;
  /** Required Core / Non-Core classroom periods for this topic (fixed for the life of the plan). */
  corePeriods?: number;
  nonCorePeriods?: number;
  requirementStatus?: 'APPROVED' | 'DEMO_DEFAULT' | 'TEACHER_CUSTOM' | 'MISSING';
  /** corePeriods + nonCorePeriods. */
  requiredPeriods: number;
  /** Classroom periods still needing a slot or already holding one (slots + unscheduled). */
  classroomPeriods: number;
  /** Non-Core periods tracked as independent learning / homework (never counted as classroom teaching). */
  independentPeriods: number;
  slots: Slot[];
  unscheduledPeriods: number;
  /** Core periods without a classroom slot (shortfall, or lost and awaiting recovery). */
  coreUnscheduled?: number;
  explanation: string[];
  /** Non-Core periods moved to homework / independent learning because of recorded lost periods. */
  lossHomeworkPeriods?: number;
  /** Lost-period effects applied to this topic by approved (or proposed) recovery. */
  lossNotes?: LossNote[];
}

export interface LossNote {
  date: string;
  reason: string;
  /** Non-Core periods moved to independent learning (lost, or given up to free a slot for Core). */
  homework: number;
  /** Core periods lost and still awaiting a classroom slot. */
  incomplete: number;
  /** Lost Core periods given a new classroom slot. */
  recovered?: number;
  /** Subject period numbers lost on that date for this topic. */
  periods?: number[];
  detail?: string;
}

export interface Conflict {
  severity: 'error' | 'warning';
  code: string;
  message: string;
  nodeIds?: string[];
}

export interface ClassTotals {
  units: number;
  requiredPeriods: number;
  scheduledPeriods: number;
  independentPeriods: number;
  unscheduledPeriods: number;
}

export interface PlanMetrics {
  periodMinutes: number;
  availablePeriods: number;
  requiredPeriods: number;
  scheduledPeriods: number;
  independentPeriods: number;
  unscheduledPeriods: number;
  sharedPeriodsSaved: number;
  core: ClassTotals;
  nonCore: ClassTotals;
  /** Topics without an approved instructional requirement. */
  pending: ClassTotals;
}

/** Why a draft was generated and against what: stored with a recalculated draft so the result stays reviewable and duplicates are recognised. */
export interface RecalcBasis {
  kind: 'RECALCULATION';
  fromPlanId: string;
  fromVersion: number;
  calendarVersion: number;
  planningDate: string;
  calendarDays: number;
  daysLeft: number;
  periodsLeft: number;
  reserveLeft: number;
  capacityLeft: number;
  remainingCore: number;
  remainingNonCore: number;
  doneTopics: number;
  taughtPeriods: number;
  fingerprint: string;
  generatedAt: string;
}

export interface ScheduleResult {
  lessons: PlannedLesson[];
  metrics: PlanMetrics;
  conflicts: Conflict[];
  basis?: RecalcBasis;
}

export interface EngineContext {
  datasets: SyllabusDataset[];
  classifications: Classifications;
  relationships: Relationship[];
}

export function subjectSlots(config: AcademicConfig, subject: PlanningSubject, after?: string): Slot[] {
  const per = config.subjectPeriodsPerDay[subject] || 0;
  const slots: Slot[] = [];
  for (const date of summarizeCalendar(config).planningDates) {
    if (after && date <= after) continue;
    for (let p = 1; p <= per; p++) slots.push({ date, period: p });
  }
  return slots;
}

/**
 * True when a historical lesson has no explicit approved Core/Non-Core split (a legacy single total). Such a total never
 * establishes an approved split: it is displayed for history only and must be reviewed and re-approved before reuse.
 */
export function isLegacyRequirement(l: PlannedLesson): boolean {
  return !(l.corePeriods != null && l.nonCorePeriods != null);
}

/**
 * Required Core / Non-Core counts of a planned topic. The fallback below exists ONLY so plans approved before explicit
 * counts existed keep rendering; use isLegacyRequirement() to flag them as unresolved. New planning never reaches it.
 */
export function lessonRequirement(l: PlannedLesson): { core: number; nonCore: number } {
  if (l.corePeriods != null && l.nonCorePeriods != null) return { core: l.corePeriods, nonCore: l.nonCorePeriods };
  return l.classification === 'NON_CORE' ? { core: 0, nonCore: l.requiredPeriods } : { core: l.requiredPeriods, nonCore: 0 };
}

/** Kind of a classroom slot; legacy slots without a kind take the topic's legacy classification. */
export function slotKind(l: PlannedLesson, s: Slot): PeriodKind {
  return s.kind ?? (l.classification === 'NON_CORE' ? 'NON_CORE' : 'CORE');
}

export interface AllocItem {
  base: Omit<PlannedLesson, 'classroomPeriods' | 'independentPeriods' | 'slots' | 'unscheduledPeriods'> & { independentPeriods?: number };
  /** Core / Non-Core classroom periods still to place (defaults: the full requirement). */
  needCore?: number;
  needNonCore?: number;
}

/**
 * Places topics, in order, into the given slots: each topic's Core periods, then its Non-Core periods.
 * If demand exceeds the slots, approved Non-Core periods (from the end) become tracked independent learning;
 * Core is never reduced and any remainder is reported as unscheduled.
 */
export function allocate(items: AllocItem[], slots: Slot[], _ctx?: EngineContext): PlannedLesson[] {
  slots = [...new Map(slots.map((s) => [s.date + '#' + s.period, s])).values()].sort((a, b) => a.date.localeCompare(b.date) || a.period - b.period);
  const needCore = items.map((i) => i.needCore ?? i.base.corePeriods ?? 0);
  const needNon = items.map((i) => i.needNonCore ?? i.base.nonCorePeriods ?? 0);
  const moved = items.map(() => 0);
  const notes = items.map((i) => [...i.base.explanation]);
  let shortfall = needCore.reduce((a, b) => a + b, 0) + needNon.reduce((a, b) => a + b, 0) - slots.length;
  const initialShortfall = shortfall;
  for (let i = items.length - 1; i >= 0 && shortfall > 0; i--) {
    const cut = Math.min(needNon[i], shortfall);
    if (cut <= 0) continue;
    needNon[i] -= cut;
    moved[i] += cut;
    shortfall -= cut;
  }
  if (initialShortfall > 0) {
    items.forEach((it, i) => {
      if (moved[i] > 0) {
        notes[i].push(
          `${moved[i]} approved Non-Core period(s) move to tracked independent learning because the plan is ${initialShortfall} period(s) short. They are not counted as classroom teaching.`,
        );
      } else if (needCore[i] > 0) notes[i].push('Core periods are protected and were not reduced for the shortfall.');
    });
  }
  let cursor = 0;
  return items.map((it, i) => {
    const take = (n: number) => {
      const got = slots.slice(cursor, cursor + Math.max(0, Math.min(n, slots.length - cursor)));
      cursor += got.length;
      return got;
    };
    const coreSlots = take(needCore[i]).map((s) => ({ date: s.date, period: s.period, kind: 'CORE' as const }));
    const nonSlots = take(needNon[i]).map((s) => ({ date: s.date, period: s.period, kind: 'NON_CORE' as const }));
    const coreUnscheduled = needCore[i] - coreSlots.length;
    const unscheduled = coreUnscheduled + (needNon[i] - nonSlots.length);
    const assigned = [...coreSlots, ...nonSlots];
    if (unscheduled > 0) {
      notes[i].push(
        coreUnscheduled > 0
          ? `${coreUnscheduled} Core period(s) do not fit before the end of the planning horizon and are unscheduled (flagged, not dropped).`
          : `${unscheduled} Non-Core period(s) do not fit before the end of the planning horizon.`,
      );
    } else if (assigned.length) {
      notes[i].push(
        `Scheduled in textbook sequence: ${coreSlots.length} Core then ${nonSlots.length} Non-Core period(s), ${assigned[0].date} to ${assigned[assigned.length - 1].date}.`,
      );
    }
    return {
      ...it.base,
      independentPeriods: (it.base.independentPeriods ?? 0) + moved[i],
      slots: assigned,
      unscheduledPeriods: unscheduled,
      coreUnscheduled,
      classroomPeriods: assigned.length + unscheduled,
      explanation: notes[i],
    };
  });
}

export function unitClass(ctx: EngineContext, nodeId: string): UnitClass {
  const r = approvedRequirement(ctx.classifications, nodeId);
  if (!r) return 'PENDING';
  if (r.core + r.nonCore === 0 && ctx.classifications[nodeId]?.origin === 'demo_default') return ctx.classifications[nodeId].value;
  return r.core > 0 && r.nonCore > 0 ? 'MIXED' : r.core > 0 ? 'CORE' : 'NON_CORE';
}

/** Shared-instruction reduction for a topic that is NOT the lead of an approved cross-curricular link. */
export function sharedReductionFor(ctx: EngineContext, node: SyllabusNode, estimate: number): { periods: number; notes: string[] } {
  let periods = 0;
  const notes: string[] = [];
  for (const r of ctx.relationships) {
    if (r.status !== 'APPROVED' || r.type !== 'CROSS_CURRICULAR' || r.sharedPeriods <= 0) continue;
    if (r.fromNodeId !== node.id && r.toNodeId !== node.id) continue;
    const otherId = r.fromNodeId === node.id ? r.toNodeId : r.fromNodeId;
    const other = findNode(ctx.datasets, otherId);
    const otherLabel = other ? `${other.number} ${other.title} (Class ${GRADE_LABEL[other.grade]} ${other.subject})` : otherId;
    if (r.leadNodeId === node.id) {
      notes.push(`Teaches ${r.sharedPeriods} shared period(s) that also serve ${otherLabel}; counted once here.`);
    } else {
      const cut = Math.min(r.sharedPeriods, estimate - periods);
      if (cut > 0) {
        periods += cut;
        notes.push(`${cut} period(s) of shared content are taught in ${otherLabel} and are not double-counted here.`);
      }
    }
  }
  return { periods, notes };
}

/** Builds a topic's planning record from its APPROVED requirement. Missing requirements are flagged, never invented. */
export function lessonBase(ctx: EngineContext, node: SyllabusNode, outcomes: OutcomeReference[]): AllocItem['base'] {
  const chapter = chapterOf(ctx.datasets, node);
  const req = approvedRequirement(ctx.classifications, node.id);
  const total = req ? req.core + req.nonCore : 0;
  const shared = sharedReductionFor(ctx, node, total);
  // Shared periods are satisfied in the lead topic: they reduce this topic's Core requirement first, then Non-Core.
  const coreCut = req ? Math.min(req.core, shared.periods) : 0;
  const core = req ? req.core - coreCut : 0;
  const nonCore = req ? Math.max(0, req.nonCore - (shared.periods - coreCut)) : 0;
  const independent = req ? Math.min(req.independent, nonCore) : 0;
  const explanation = req
    ? [`${'Saved'} requirement: ${req.core} Core + ${req.nonCore} Non-Core period(s), including ${independent} independent-learning period(s).`, ...shared.notes]
    : ['No approved instructional requirement: no periods are scheduled. Set Core and Non-Core periods in Syllabus & classification and have them approved.'];
  return {
    nodeId: node.id,
    grade: node.grade,
    subject: node.subject,
    chapterTitle: chapter?.title ?? 'Chapter not recorded',
    chapterNumber: chapter?.number ?? '',
    number: node.number,
    title: node.title,
    kind: node.kind,
    outcomeIds: outcomes.filter((o) => o.linkedNodeIds.includes(node.id)).map((o) => o.id),
    classification: unitClass(ctx, node.id),
    estimatedPeriods: total,
    sharedReduction: req ? shared.periods : 0,
    corePeriods: core,
    nonCorePeriods: nonCore,
    independentPeriods: independent,
    requirementStatus: req ? (ctx.classifications[node.id]?.origin === 'demo_default' ? 'DEMO_DEFAULT' : ctx.classifications[node.id]?.origin === 'teacher' ? 'TEACHER_CUSTOM' : 'APPROVED') : 'MISSING',
    requiredPeriods: core + nonCore,
    explanation,
  };
}

export function computeMetrics(lessons: PlannedLesson[], availablePeriods: number, periodMinutes: number): PlanMetrics {
  const kindCount = (l: PlannedLesson, k: PeriodKind) => l.slots.filter((s) => slotKind(l, s) === k).length;
  const core: ClassTotals = { units: 0, requiredPeriods: 0, scheduledPeriods: 0, independentPeriods: 0, unscheduledPeriods: 0 };
  const nonCore: ClassTotals = { units: 0, requiredPeriods: 0, scheduledPeriods: 0, independentPeriods: 0, unscheduledPeriods: 0 };
  const pending: ClassTotals = { units: 0, requiredPeriods: 0, scheduledPeriods: 0, independentPeriods: 0, unscheduledPeriods: 0 };
  for (const l of lessons) {
    if (l.requirementStatus === 'MISSING') {
      pending.units += 1;
      continue;
    }
    const r = lessonRequirement(l);
    const coreUnsched = l.coreUnscheduled ?? (r.core > 0 ? l.unscheduledPeriods : 0);
    if (r.core > 0) core.units += 1;
    if (r.nonCore > 0) nonCore.units += 1;
    core.requiredPeriods += r.core;
    core.scheduledPeriods += kindCount(l, 'CORE');
    core.unscheduledPeriods += coreUnsched;
    nonCore.requiredPeriods += r.nonCore;
    nonCore.scheduledPeriods += kindCount(l, 'NON_CORE');
    nonCore.independentPeriods += l.independentPeriods;
    nonCore.unscheduledPeriods += l.unscheduledPeriods - coreUnsched;
  }
  return {
    periodMinutes,
    availablePeriods,
    requiredPeriods: lessons.reduce((s, l) => s + l.requiredPeriods, 0),
    scheduledPeriods: lessons.reduce((s, l) => s + l.slots.length, 0),
    independentPeriods: lessons.reduce((s, l) => s + l.independentPeriods, 0),
    unscheduledPeriods: lessons.reduce((s, l) => s + l.unscheduledPeriods, 0),
    sharedPeriodsSaved: lessons.reduce((s, l) => s + l.sharedReduction, 0),
    core,
    nonCore,
    pending,
  };
}

export function detectConflicts(lessons: PlannedLesson[], ctx: EngineContext, availablePeriods: number, subject: PlanningSubject): Conflict[] {
  const conflicts: Conflict[] = [];
  if (!lessons.length) conflicts.push({ severity: 'error', code: 'NO_SYLLABUS', message: 'No syllabus units are available for this class and subject in the selected dataset.' });
  if (availablePeriods === 0) conflicts.push({ severity: 'error', code: 'NO_TIME', message: `The Academic Configuration allocates no ${subject} periods inside the planning horizon.` });
  const missing = lessons.filter((l) => l.requirementStatus === 'MISSING');
  if (missing.length) {
    conflicts.push({
      severity: 'error',
      code: 'REQUIREMENT_MISSING',
      message: `${missing.length} topic(s) have no approved instructional requirement (Core and Non-Core periods): ${missing.map((l) => l.title).join(', ')}. They are not scheduled until a requirement is proposed and approved.`,
      nodeIds: missing.map((l) => l.nodeId),
    });
  }
  const noCapacityDefaults = lessons.filter((l) => l.requirementStatus === 'DEMO_DEFAULT' && l.requiredPeriods === 0);
  if (noCapacityDefaults.length) conflicts.push({
    severity: 'warning', code: 'DEMO_DEFAULT_ZERO_CAPACITY',
    message: `${noCapacityDefaults.length} demonstration-default topic(s) have zero allocated periods because available annual capacity is exhausted. They are configured, not awaiting human approval; review the capacity shortfall.`,
    nodeIds: noCapacityDefaults.map((l) => l.nodeId),
  });
  const unscheduled = lessons.filter((l) => l.unscheduledPeriods > 0);
  if (unscheduled.length) {
    const total = unscheduled.reduce((s, l) => s + l.unscheduledPeriods, 0);
    const core = unscheduled.reduce((s, l) => s + (l.coreUnscheduled ?? 0), 0);
    conflicts.push({
      severity: 'error',
      code: 'TIME_SHORTFALL',
      message: `Insufficient instructional time: ${total} classroom period(s) across ${unscheduled.length} topic(s) cannot be scheduled${core ? `, including ${core} Core period(s)` : ''}. Add instructional days, extend the horizon, or allocate more ${subject} periods.`,
      nodeIds: unscheduled.map((l) => l.nodeId),
    });
  }
  const index = new Map(lessons.map((l, i) => [l.nodeId, i]));
  for (const r of ctx.relationships) {
    if (r.status !== 'APPROVED' || r.type !== 'PREREQUISITE') continue;
    const a = index.get(r.fromNodeId);
    const b = index.get(r.toNodeId);
    if (a !== undefined && b !== undefined) {
      if (a > b) conflicts.push({ severity: 'error', code: 'PREREQUISITE_ORDER', message: `"${lessons[b].title}" is sequenced before its prerequisite "${lessons[a].title}".`, nodeIds: [r.fromNodeId, r.toNodeId] });
      else if (lessons[a].unscheduledPeriods > 0 && lessons[b].slots.length > 0) {
        conflicts.push({ severity: 'error', code: 'PREREQUISITE_UNSCHEDULED', message: `Prerequisite "${lessons[a].title}" is not fully scheduled but its dependent "${lessons[b].title}" is.`, nodeIds: [r.fromNodeId, r.toNodeId] });
      }
    } else if (b !== undefined && a === undefined) {
      const pre = findNode(ctx.datasets, r.fromNodeId);
      conflicts.push({ severity: 'warning', code: 'EXTERNAL_PREREQUISITE', message: `"${lessons[b].title}" depends on ${pre ? `"${pre.title}" (Class ${GRADE_LABEL[pre.grade]} ${pre.subject})` : r.fromNodeId}, which is outside this plan.`, nodeIds: [r.toNodeId] });
    }
  }
  return conflicts;
}

export interface GenerateInput {
  dataset: SyllabusDataset;
  units: SyllabusNode[];
  grade: number;
  subject: PlanningSubject;
  config: AcademicConfig;
  /** Only allocate teaching periods after this planning reference date when rebuilding the remaining schedule. */
  after?: string;
  /** Ignored legacy input: counts always come from approved topic requirements. */
  estimates?: Record<string, number>;
}

export function generateSchedule(input: GenerateInput, ctx: EngineContext): ScheduleResult {
  const slots = subjectSlots(input.config, input.subject, input.after);
  const items: AllocItem[] = input.units.map((u) => {
    const base = lessonBase(ctx, u, input.dataset.outcomes);
    return { base, needNonCore: Math.max(0, (base.nonCorePeriods ?? 0) - (base.independentPeriods ?? 0)) };
  });
  const lessons = allocate(items, slots, ctx);
  return { lessons, metrics: computeMetrics(lessons, slots.length, input.config.periodMinutes), conflicts: detectConflicts(lessons, ctx, slots.length, input.subject) };
}

/** Snapshot of the approved requirement totals used for a plan (kept in plan.estimates for traceability). */
export function requirementSnapshot(lessons: PlannedLesson[]): Record<string, number> {
  return Object.fromEntries(lessons.map((l) => [l.nodeId, l.requiredPeriods]));
}

export const lessonStart = (l: PlannedLesson) => l.slots[0]?.date ?? null;
export const lessonEnd = (l: PlannedLesson) => l.slots[l.slots.length - 1]?.date ?? null;

/**
 * Cross-curricular coverage across both subjects for one class: each outcome reference and each shared period is
 * counted once even though the linked topics stay visible in both curricula.
 */
export function crossCurricularSummary(lessonsBySubject: PlannedLesson[][], relationships: Relationship[]) {
  const all = lessonsBySubject.flat();
  const outcomeIds = new Set(all.flatMap((l) => l.outcomeIds));
  const naiveOutcomeCount = all.reduce((s, l) => s + l.outcomeIds.length, 0);
  const ids = new Set(all.map((l) => l.nodeId));
  const links = relationships.filter((r) => r.status === 'APPROVED' && r.type === 'CROSS_CURRICULAR' && ids.has(r.fromNodeId) && ids.has(r.toNodeId));
  return {
    uniqueOutcomes: outcomeIds.size,
    naiveOutcomeCount,
    sharedPeriodsCountedOnce: all.reduce((s, l) => s + l.sharedReduction, 0),
    links,
  };
}
