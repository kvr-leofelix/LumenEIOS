/**
 * Plans, teacher execution and the adaptive recovery loop.
 *
 * Separate records, never overwritten:
 *   plan.draft            – the generated schedule awaiting approval
 *   plan.versions[0]      – the original approved schedule
 *   plan.versions[n>0]    – approved revised schedules (each from an approved recovery proposal)
 *   plan.execution        – append-only teacher execution events (corrections supersede, never edit)
 *   plan.evidence         – assessment/observation evidence (the only route to "assessed")
 *   plan.proposals        – every recovery proposal with its review outcome
 */
import type { AcademicConfig, PlanningSubject } from './calendar';
import { GRADE_LABEL, sameConfig, summarizeCalendar } from './calendar';
import type { Actor } from './governance';
import {
  allocate,
  AllocItem,
  computeMetrics,
  Conflict,
  detectConflicts,
  EngineContext,
  isLegacyRequirement,
  lessonRequirement,
  slotKind,
  lessonEnd,
  lessonStart,
  PlanMetrics,
  PlannedLesson,
  ScheduleResult,
  Slot,
  subjectSlots,
} from './engine';
import { findNode } from './syllabus';
import { applyLosses, LossDaySummary, LostPeriodRecord, recordLoss, recordLossBatch, LossInput } from './losses';

export type PlanStatus = 'DRAFT' | 'APPROVED' | 'SUPERSEDED' | 'REJECTED';

export interface ScheduleVersion {
  version: number;
  lessons: PlannedLesson[];
  metrics: PlanMetrics;
  conflicts: Conflict[];
  config: AcademicConfig;
  approvedBy: Actor;
  approvedAt: string;
  reason: string;
  proposalId: string | null;
  /** Cumulative subject periods removed by recorded lost periods (Day Tracker) in this version. */
  lostSlots?: Slot[];
}

export type ExecStatus = 'TAUGHT' | 'PARTIAL' | 'HOMEWORK' | 'DEFERRED' | 'HOMEWORK_COMPLETED';

export const EXEC_LABEL: Record<ExecStatus, string> = {
  TAUGHT: 'Completed as scheduled',
  PARTIAL: 'Partially completed',
  HOMEWORK: 'Not completed — assigned as homework',
  DEFERRED: 'Not completed — deferred/rescheduled',
  HOMEWORK_COMPLETED: 'Homework submitted',
};

export interface ExecutionEvent {
  id: string;
  nodeId: string;
  date: string;
  status: ExecStatus;
  periodsTaught: number;
  note: string;
  recordedBy: Actor;
  recordedAt: string;
  /** id of an earlier event this one corrects (same unit, same date). */
  supersedes: string | null;
  scheduleVersion: number;
}

export interface EvidenceRecord {
  id: string;
  nodeId: string;
  kind: 'ASSESSMENT' | 'OBSERVATION';
  reference: string;
  result: string;
  recordedBy: Actor;
  recordedAt: string;
}

export type ProposalStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'SUPERSEDED';

export interface ScheduleChange {
  nodeId: string;
  title: string;
  kind: 'REQUEUED' | 'SHIFTED' | 'REDUCED' | 'NEWLY_UNSCHEDULED' | 'RESTORED' | 'TO_HOMEWORK' | 'INCOMPLETE_REQUEUED';
  before: { start: string | null; end: string | null; classroom: number; unscheduled: number };
  after: { start: string | null; end: string | null; classroom: number; unscheduled: number };
}

export interface RecoveryProposal {
  id: string;
  createdAt: string;
  createdBy: Actor;
  trigger: { kind: 'EXECUTION' | 'CONFIG_CHANGE' | 'LOST_PERIODS'; eventId?: string; nodeId?: string; status?: ExecStatus; lossId?: string };
  baseVersion: number;
  cutoffDate: string | null;
  config: AcademicConfig;
  lessons: PlannedLesson[];
  metrics: PlanMetrics;
  conflicts: Conflict[];
  /** Date after which remaining time is counted (latest execution or lost-period date); null = from the plan start. */
  remainingAfter?: string | null;
  remainingAvailablePeriods: number;
  remainingRequiredPeriods: number;
  affected: { nodeId: string; title: string; reason: string }[];
  changes: ScheduleChange[];
  explanation: string[];
  status: ProposalStatus;
  review?: { by: Actor; at: string; note: string };
  lostSlots?: Slot[];
  lossDays?: LossDaySummary[];
}

export interface Plan {
  id: string;
  grade: number;
  subject: PlanningSubject;
  datasetId: string;
  datasetLabel: string;
  datasetKind: string;
  createdBy: Actor;
  createdAt: string;
  config: AcademicConfig;
  estimates: Record<string, number>;
  status: PlanStatus;
  draft: ScheduleResult;
  versions: ScheduleVersion[];
  review?: { by: Actor; at: string; note: string; decision: 'APPROVED' | 'REJECTED' };
  supersededBy?: string;
  execution: ExecutionEvent[];
  evidence: EvidenceRecord[];
  proposals: RecoveryProposal[];
  /** Day Tracker: append-only lost-period records (optional for plans created before it existed). */
  losses?: LostPeriodRecord[];
  /** Owning teacher and school (relational plans). Plans are never shared between teachers. */
  teacherId?: string;
  schoolId?: string;
}

export const newId = (prefix: string) =>
  `${prefix}-${typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : Math.random().toString(36).slice(2)}`;

export const planLabel = (p: Pick<Plan, 'grade' | 'subject'>) => `Class ${GRADE_LABEL[p.grade]} ${p.subject}`;

export const currentVersion = (p: Plan): ScheduleVersion | undefined => p.versions[p.versions.length - 1];
export const originalVersion = (p: Plan): ScheduleVersion | undefined => p.versions[0];
export const pendingProposal = (p: Plan): RecoveryProposal | undefined => p.proposals.find((x) => x.status === 'PENDING');
export const configChangedSinceApproval = (p: Plan, current: AcademicConfig) => p.status === 'APPROVED' && !sameConfig(p.config, current);

/* ------------------------------------------------------------- plan approval -- */

export function createDraft(input: Omit<Plan, 'id' | 'status' | 'versions' | 'execution' | 'evidence' | 'proposals' | 'createdAt' | 'losses'>, at = new Date().toISOString()): Plan {
  return { ...input, id: newId('plan'), createdAt: at, status: 'DRAFT', versions: [], execution: [], evidence: [], proposals: [], losses: [] };
}

export function approveDraft(plans: Plan[], planId: string, actor: Actor, note: string, at = new Date().toISOString()): Plan[] {
  const plan = plans.find((p) => p.id === planId);
  if (!plan || plan.status !== 'DRAFT') throw new Error('Only a draft plan can be approved.');
  if (!['admin', 'principal'].includes(actor.role)) throw new Error('Only an Admin or Principal can approve a teaching plan.');
  if (!plan.draft.lessons.length) throw new Error('A plan without syllabus units cannot be approved.');
  if (plan.draft.conflicts.some((c) => ['REQUIREMENT_MISSING', 'PREREQUISITE_ORDER'].includes(c.code))) throw new Error('Resolve missing approved requirements and prerequisite order before approval.');
  return plans.map((p) => {
    if (p.id === planId) {
      const version: ScheduleVersion = {
        version: 1,
        lessons: p.draft.lessons,
        metrics: p.draft.metrics,
        conflicts: p.draft.conflicts,
        config: p.config,
        approvedBy: actor,
        approvedAt: at,
        reason: note.trim() || 'Initial schedule approved',
        proposalId: null,
      };
      return { ...p, status: 'APPROVED', versions: [version], review: { by: actor, at, note: note.trim(), decision: 'APPROVED' } };
    }
    // The previously approved plan for this class/subject is preserved, with its execution history, as SUPERSEDED.
    if (p.status === 'APPROVED' && p.grade === plan.grade && p.subject === plan.subject && p.teacherId === plan.teacherId) {
      return { ...p, status: 'SUPERSEDED', supersededBy: planId, proposals: p.proposals.map((x) => (x.status === 'PENDING' ? { ...x, status: 'SUPERSEDED' } : x)) };
    }
    return p;
  });
}

export function rejectDraft(plans: Plan[], planId: string, actor: Actor, note: string, at = new Date().toISOString()): Plan[] {
  const plan = plans.find((p) => p.id === planId);
  if (!plan || plan.status !== 'DRAFT') throw new Error('Only a draft plan can be rejected.');
  if (!['admin', 'principal'].includes(actor.role)) throw new Error('Only an Admin or Principal can reject a teaching plan.');
  if (note.trim().length < 5) throw new Error('A rejection reason is required.');
  return plans.map((p) => (p.id === planId ? { ...p, status: 'REJECTED', review: { by: actor, at, note: note.trim(), decision: 'REJECTED' } } : p));
}

/* ----------------------------------------------------------------- execution -- */

export const effectiveEvents = (p: Plan, nodeId?: string) => {
  const superseded = new Set(p.execution.map((e) => e.supersedes).filter(Boolean));
  return p.execution.filter((e) => !superseded.has(e.id) && (!nodeId || e.nodeId === nodeId));
};

export type LessonState =
  | 'SCHEDULED'
  | 'UNSCHEDULED'
  | 'TAUGHT'
  | 'PARTIAL'
  | 'HOMEWORK'
  | 'DEFERRED'
  | 'RESCHEDULED'
  | 'COMPLETED_LATER'
  | 'ASSESSED'
  | 'LOSS_HOMEWORK'
  | 'LOSS_RESCHEDULED';

export const STATE_LABEL: Record<LessonState, string> = {
  SCHEDULED: 'Scheduled',
  UNSCHEDULED: 'Unscheduled — time shortfall',
  TAUGHT: 'Taught',
  PARTIAL: 'Partially taught',
  HOMEWORK: 'Incomplete — homework assigned',
  DEFERRED: 'Incomplete — deferred',
  RESCHEDULED: 'Rescheduled (approved recovery)',
  COMPLETED_LATER: 'Completed through subsequent teaching',
  ASSESSED: 'Assessed — evidence recorded',
  LOSS_HOMEWORK: 'Scheduled — Non-Core moved to independent learning',
  LOSS_RESCHEDULED: 'Incomplete — Core awaiting recovery',
};

export interface LessonProgress {
  state: LessonState;
  taughtPeriods: number;
  remainingPeriods: number;
  classroomTotal: number;
  complete: boolean;
  homeworkAssigned: boolean;
  homeworkSubmitted: boolean;
  lastIncomplete?: ExecutionEvent;
  events: ExecutionEvent[];
  evidence: EvidenceRecord[];
}

/** Not yet taught in class and flagged by execution or lost periods (homework never counts as taught). */
export const isIncomplete = (pr: LessonProgress) => !pr.complete && (!!pr.lastIncomplete || pr.state === 'LOSS_RESCHEDULED');

export function lessonProgress(p: Plan, lesson: PlannedLesson): LessonProgress {
  const events = effectiveEvents(p, lesson.nodeId).sort((a, b) => a.date.localeCompare(b.date) || a.recordedAt.localeCompare(b.recordedAt));
  const instruction = events.filter((e) => e.status !== 'HOMEWORK_COMPLETED');
  const complete = instruction.some((e) => e.status === 'TAUGHT');
  // Classroom requirement excludes independent learning (shortfall reductions and lost-period homework).
  const classroomTotal = Math.max(0, lesson.requiredPeriods - lesson.independentPeriods);
  const partialTaught = instruction.filter((e) => e.status === 'PARTIAL').reduce((s, e) => s + e.periodsTaught, 0);
  const taughtPeriods = complete ? classroomTotal : Math.min(partialTaught, classroomTotal);
  const incompleteEvents = instruction.filter((e) => e.status !== 'TAUGHT');
  const lastIncomplete = incompleteEvents[incompleteEvents.length - 1];
  const evidence = p.evidence.filter((e) => e.nodeId === lesson.nodeId);
  const lossHomework = lesson.lossHomeworkPeriods ?? 0;
  const homeworkAssigned = instruction.some((e) => e.status === 'HOMEWORK') || lesson.independentPeriods > 0;
  const homeworkSubmitted = homeworkAssigned && events.some((e) => e.status === 'HOMEWORK_COMPLETED');
  let state: LessonState;
  if (complete) state = evidence.length ? 'ASSESSED' : incompleteEvents.length ? 'COMPLETED_LATER' : 'TAUGHT';
  else if (lastIncomplete) {
    const movedLater = (lessonStart(lesson) ?? '') > lastIncomplete.date && currentVersion(p)!.version > lastIncomplete.scheduleVersion;
    state = movedLater ? 'RESCHEDULED' : (lastIncomplete.status as LessonState);
  } else if (lossHomework > 0) state = 'LOSS_HOMEWORK';
  else if ((lesson.lossNotes ?? []).some((n) => n.incomplete > 0)) state = 'LOSS_RESCHEDULED';
  else state = lesson.slots.length || lesson.requiredPeriods === 0 ? 'SCHEDULED' : 'UNSCHEDULED';
  return {
    state,
    taughtPeriods,
    remainingPeriods: Math.max(0, classroomTotal - taughtPeriods),
    classroomTotal,
    complete,
    homeworkAssigned,
    homeworkSubmitted,
    lastIncomplete,
    events,
    evidence,
  };
}

export interface ExecutionInput {
  nodeId: string;
  date: string;
  status: ExecStatus;
  periodsTaught?: number;
  note?: string;
}

/** Validates and appends an execution event. Throws with a user-facing message on any problem. */
export function recordExecution(p: Plan, input: ExecutionInput, actor: Actor, at = new Date().toISOString()): Plan {
  if (p.status !== 'APPROVED') throw new Error('Execution can only be recorded against an approved plan.');
  if (!['teacher', 'admin'].includes(actor.role)) throw new Error('Only a teacher can record classroom execution.');
  const version = currentVersion(p)!;
  const lesson = version.lessons.find((l) => l.nodeId === input.nodeId);
  if (!lesson) throw new Error('This unit is not part of the approved schedule.');
  const instructional = summarizeCalendar(p.config).instructionalDates;
  if (!instructional.includes(input.date)) throw new Error(`${input.date} is not an instructional day in this plan's academic calendar.`);
  const isSubmission = input.status === 'HOMEWORK_COMPLETED';
  // The latest same-day record of the same kind (classroom vs homework submission) is the one a new entry corrects.
  const sameDay = lessonProgress(p, lesson).events.filter((e) => e.date === input.date && (e.status === 'HOMEWORK_COMPLETED') === isSubmission);
  const prior = sameDay[sameDay.length - 1];
  // Validate against progress as it would be without the record being corrected.
  const progress = lessonProgress(prior ? { ...p, execution: p.execution.filter((e) => e.id !== prior.id) } : p, lesson);
  const periodsTaught = input.status === 'PARTIAL' ? Number(input.periodsTaught) : input.status === 'TAUGHT' ? progress.remainingPeriods : 0;
  if (prior && prior.status === input.status && prior.periodsTaught === periodsTaught && prior.note === (input.note ?? '').trim()) {
    throw new Error('Duplicate record: this exact execution status is already recorded for this unit on this date.');
  }
  if (input.status === 'TAUGHT' || input.status === 'PARTIAL') {
    if (progress.classroomTotal === 0) throw new Error('No classroom periods remain for this unit: its time was moved to homework / independent learning. Record homework submission instead.');
  }
  if (!isSubmission && progress.complete) {
    throw new Error('This unit is already recorded as taught on another date. Correct that record on its own date instead.');
  }
  if (input.status === 'PARTIAL') {
    const remaining = progress.remainingPeriods;
    if (!Number.isInteger(periodsTaught) || periodsTaught < 1 || periodsTaught >= remaining) {
      throw new Error(
        remaining <= 1
          ? 'Only one period remains; record "Completed as scheduled" or "Not completed" instead of partial completion.'
          : `Partial completion must be between 1 and ${remaining - 1} period(s); record "Completed" if all ${remaining} remaining period(s) were taught.`,
      );
    }
  }
  if (isSubmission && !progress.homeworkAssigned) throw new Error('Homework submission can only be recorded after homework was assigned.');
  const correcting = prior ?? null;
  const event: ExecutionEvent = {
    id: newId('exec'),
    nodeId: input.nodeId,
    date: input.date,
    status: input.status,
    periodsTaught,
    note: (input.note ?? '').trim(),
    recordedBy: actor,
    recordedAt: at,
    supersedes: correcting?.id ?? null,
    scheduleVersion: version.version,
  };
  return { ...p, execution: [...p.execution, event] };
}

export function recordEvidence(p: Plan, nodeId: string, kind: EvidenceRecord['kind'], reference: string, result: string, actor: Actor, at = new Date().toISOString()): Plan {
  const lesson = currentVersion(p)?.lessons.find((l) => l.nodeId === nodeId);
  if (!lesson) throw new Error('Unit not found in the approved schedule.');
  if (!lessonProgress(p, lesson).complete) throw new Error('Evidence of mastery can only be recorded after the unit has been taught; homework alone is not sufficient.');
  if (reference.trim().length < 3) throw new Error('An assessment or evidence reference is required.');
  if (!result.trim()) throw new Error('Record the assessment result or observation.');
  return { ...p, evidence: [...p.evidence, { id: newId('evidence'), nodeId, kind, reference: reference.trim(), result: result.trim(), recordedBy: actor, recordedAt: at }] };
}

/* ------------------------------------------------------------------ recovery -- */

function summarizeLesson(l: PlannedLesson) {
  return { start: lessonStart(l), end: lessonEnd(l), classroom: l.slots.length, unscheduled: l.unscheduledPeriods };
}

/**
 * A plan's working days are fixed once it is created. A configuration recalculation may change periods or the
 * horizon, but never the number of school working days; lost time is recorded in the Day Tracker instead.
 */
export function recalculationBlocked(p: Plan, config: AcademicConfig): string | null {
  if (currentVersion(p)?.lessons.some(isLegacyRequirement)) {
    return 'This plan has legacy total-period requirements without an approved Core/Non-Core split. Review and approve explicit period counts before recalculating or recovering it.';
  }
  const before = summarizeCalendar(p.config).workingDates.length;
  const after = summarizeCalendar(config).workingDates.length;
  return before === after
    ? null
    : `This plan was created with ${before} school working days; the current configuration has ${after}. Working days cannot change after a plan is created. Record lost periods in the Day Tracker, or generate a new plan.`;
}

const slotKey = (s: Slot) => `${s.date}#${s.period}`;

/**
 * Builds a recovery proposal from the current approved version. Returns null when nothing would change.
 * Step 1 absorbs recorded lost periods not yet applied (Day Tracker). Step 2 (execution / configuration triggers, or
 * when execution records show incomplete work) requeues every unit not yet complete, in textbook order, into the
 * usable slots after the latest recorded teaching date. Completed units keep their slots; lost slots are never reused.
 */
export function generateRecovery(
  p: Plan,
  ctx: EngineContext,
  opts: { trigger: RecoveryProposal['trigger']; config?: AcademicConfig; actor: Actor; at?: string; asOf?: string },
): RecoveryProposal | null {
  const version = currentVersion(p);
  if (!version || p.status !== 'APPROVED') return null;
  if (version.lessons.some(isLegacyRequirement)) return null;
  const config = opts.config ?? p.config;
  if (opts.config) {
    const locked = recalculationBlocked(p, opts.config);
    if (locked) throw new Error(locked);
  }
  const events = effectiveEvents(p).filter((e) => e.status !== 'HOMEWORK_COMPLETED');
  const latestExecution = events.length ? events.map((e) => e.date).sort().pop()! : null;
  const referenceDate = opts.trigger.kind === 'CONFIG_CHANGE' ? opts.asOf : undefined;
  const cutoff = [latestExecution, referenceDate].filter((d): d is string => !!d).sort().pop() ?? null;

  const progress = new Map(version.lessons.map((l) => [l.nodeId, lessonProgress(p, l)]));
  const completeIds = new Set(version.lessons.filter((l) => progress.get(l.nodeId)!.complete).map((l) => l.nodeId));

  // Step 1: recorded lost periods.
  const loss = applyLosses(p, version.lessons, version.lostSlots ?? [], completeIds, ctx, config);
  const lostKeys = new Set(loss.lostSlots.map(slotKey));
  const baseLessons = loss.lessons;

  const affected: RecoveryProposal['affected'] = [];
  for (const day of loss.days) {
    for (const h of day.homework) affected.push({ nodeId: h.nodeId, title: h.title, reason: `${h.periods} Non-Core period(s) moved to independent learning after the loss on ${day.date} (${day.reason}); the requirement is kept and tracked` });
    for (const x of day.incomplete) affected.push({ nodeId: x.nodeId, title: x.title, reason: `${x.periods} Core period(s) lost on ${day.date} (${day.reason}) are unresolved and await recovery` });
  }

  // Step 2: execution-driven requeue.
  const requeueAll = opts.trigger.kind !== 'LOST_PERIODS';
  const fixed = baseLessons.filter((l) => completeIds.has(l.nodeId));
  const occupied = new Set(fixed.flatMap((l) => l.slots.map(slotKey)));
  const free: Slot[] = requeueAll ? subjectSlots(config, p.subject, cutoff ?? undefined).filter((s) => !occupied.has(slotKey(s)) && !lostKeys.has(slotKey(s))) : [];
  const items: AllocItem[] = [];
  const homeworkById = new Map<string, number>();
  const incompleteIds = new Set<string>();
  if (requeueAll) {
    for (const l of baseLessons) {
      const pr = progress.get(l.nodeId)!;
      if (pr.complete) continue;
      const base = { ...l }; // Preserve the approved requirement snapshot, including shared instruction.
      const homework = l.lossHomeworkPeriods ?? 0;
      homeworkById.set(l.nodeId, homework);
      const req = lessonRequirement(l);
      const taughtCore = Math.min(req.core, pr.taughtPeriods);
      const needCore = Math.max(0, req.core - taughtCore);
      const needNonCore = Math.max(0, req.nonCore - l.independentPeriods - Math.max(0, pr.taughtPeriods - taughtCore));
      const required = needCore + needNonCore;
      const why: string[] = [];
      if (pr.lastIncomplete) {
        incompleteIds.add(l.nodeId);
        const reason =
          pr.lastIncomplete.status === 'HOMEWORK'
            ? `Assigned as homework on ${pr.lastIncomplete.date}; homework does not count as classroom teaching, so ${required} period(s) are requeued.`
            : pr.lastIncomplete.status === 'PARTIAL'
              ? `Partially taught (${pr.taughtPeriods} of ${base.requiredPeriods - homework} classroom period(s)); the remaining ${required} period(s) are requeued.`
              : `Deferred on ${pr.lastIncomplete.date}; ${required} period(s) are requeued.`;
        why.push(reason);
        affected.push({ nodeId: l.nodeId, title: l.title, reason: STATE_LABEL[pr.state] + (l.outcomeIds.length ? ` · outcome reference(s) ${l.outcomeIds.join(', ')} not yet covered` : '') });
      } else if (cutoff && (lessonStart(l) ?? '9999') <= cutoff) {
        incompleteIds.add(l.nodeId);
        why.push(`No execution was recorded for its scheduled date(s) up to ${cutoff}; it is treated as not yet taught. Record execution if it was taught.`);
        affected.push({ nodeId: l.nodeId, title: l.title, reason: 'Scheduled date passed without an execution record' });
      } else if (opts.trigger.kind === 'CONFIG_CHANGE') {
        why.push('Re-planned against the updated Academic Configuration.');
      } else {
        why.push('Shifted to follow earlier requeued work in textbook sequence.');
      }
      const lossText = (l.lossNotes ?? []).map((n) =>
        n.homework ? `${n.homework} period(s) lost on ${n.date} (${n.reason}) are homework / independent learning, not classroom teaching.` : `${n.incomplete} period(s) lost on ${n.date} (${n.reason}) were requeued.`,
      );
      items.push({ base: { ...base, independentPeriods: l.independentPeriods, explanation: [...why, ...lossText, ...base.explanation] }, needCore, needNonCore });
    }
  }

  // Dependent units: approved prerequisites and cross-curricular leads whose source is incomplete.
  for (const id of loss.days.flatMap((d) => d.incomplete.map((x) => x.nodeId))) incompleteIds.add(id);
  for (const r of ctx.relationships) {
    if (r.status !== 'APPROVED') continue;
    const source = r.type === 'PREREQUISITE' ? r.fromNodeId : r.leadNodeId;
    if (!source || !incompleteIds.has(source)) continue;
    const dependent = r.type === 'PREREQUISITE' ? r.toNodeId : r.fromNodeId === source ? r.toNodeId : r.fromNodeId;
    const node = findNode(ctx.datasets, dependent);
    const src = findNode(ctx.datasets, source);
    if (node && !affected.some((a) => a.nodeId === dependent)) {
      affected.push({
        nodeId: dependent,
        title: `${node.title} (Class ${GRADE_LABEL[node.grade]} ${node.subject})`,
        reason: r.type === 'PREREQUISITE' ? `Depends on incomplete prerequisite "${src?.title}"` : `Shares content taught in incomplete unit "${src?.title}"`,
      });
    }
  }

  const requeued = allocate(items, free, ctx).map((r) => {
    // Keep the full requirement on the unit: remaining classroom time lives in slots/unscheduled, and periods already
    // taught or moved to homework are accounted for separately (never as classroom teaching).
    const original = baseLessons.find((x) => x.nodeId === r.nodeId)!;
    const homework = homeworkById.get(r.nodeId) ?? 0;
    const pr = progress.get(r.nodeId)!;
    return {
      ...r,
      requiredPeriods: original.requiredPeriods,
      independentPeriods: r.independentPeriods,
      lossHomeworkPeriods: original.lossHomeworkPeriods,
      lossNotes: original.lossNotes,
    };
  });
  const byId = new Map(requeued.map((l) => [l.nodeId, l]));
  const lessons = baseLessons.map((l) => byId.get(l.nodeId) ?? l);
  const changes: ScheduleChange[] = [];
  for (const before of version.lessons) {
    const after = lessons.find((l) => l.nodeId === before.nodeId)!;
    const b = summarizeLesson(before);
    const a = summarizeLesson(after);
    const hwB = before.lossHomeworkPeriods ?? 0;
    const hwA = after.lossHomeworkPeriods ?? 0;
    const incB = (before.lossNotes ?? []).reduce((s, n) => s + n.incomplete, 0);
    const incA = (after.lossNotes ?? []).reduce((s, n) => s + n.incomplete, 0);
    if (JSON.stringify(before.slots) === JSON.stringify(after.slots) && JSON.stringify(b) === JSON.stringify(a) && before.independentPeriods === after.independentPeriods && hwA === hwB && incA === incB) continue;
    const kind: ScheduleChange['kind'] =
      hwA > hwB
        ? 'TO_HOMEWORK'
        : incA > incB
          ? 'INCOMPLETE_REQUEUED'
          : a.unscheduled > b.unscheduled
            ? 'NEWLY_UNSCHEDULED'
            : after.independentPeriods > before.independentPeriods
              ? 'REDUCED'
              : a.unscheduled < b.unscheduled
                ? 'RESTORED'
                : incompleteIds.has(before.nodeId)
                  ? 'REQUEUED'
                  : 'SHIFTED';
    changes.push({ nodeId: before.nodeId, title: before.title, kind, before: b, after: a });
  }
  if (!changes.length && opts.trigger.kind !== 'CONFIG_CHANGE') return null;
  if (!changes.length && opts.trigger.kind === 'CONFIG_CHANGE' && sameConfig(config, p.config)) return null;

  const available = subjectSlots(config, p.subject).length - loss.lostSlots.length;
  const lastLossDate = loss.days.length ? loss.days.map((d) => d.date).sort().pop()! : null;
  const remainingRequired = items.reduce((s, i) => s + (i.needCore ?? 0) + (i.needNonCore ?? 0), 0);
  const metrics = computeMetrics(lessons, available, config.periodMinutes);
  const conflicts = detectConflicts(lessons, ctx, available, p.subject);
  const explanation = [
    ...loss.days.map((d) =>
      d.released
        ? `${d.date}: a correction restored ${d.released} period(s); later work moves back into them. Homework already assigned is unchanged.`
        : `${d.date} (${d.reason}): ${d.lost} of ${d.scheduled} scheduled ${p.subject} period(s) lost. ` +
          `${(d.recovered ?? []).reduce((s, x) => s + x.periods, 0)} lost Core period(s) recovered in the next teaching days; ` +
          `${d.homework.reduce((s, x) => s + x.periods, 0)} Non-Core period(s) move to independent learning (requirements kept, not counted as taught); ` +
          `${d.incomplete.reduce((s, x) => s + x.periods, 0)} Core period(s) remain unresolved.`,
    ),
    ...loss.days.flatMap((d) => d.unresolved ?? []),
    ...(requeueAll
      ? [
          cutoff ? `Latest recorded teaching date: ${cutoff}. Requeued work starts on the next ${p.subject} slot after it.` : 'No execution has been recorded yet; all usable planning slots are available.',
          `${fixed.length} completed unit(s) keep their dates. ${items.length} unit(s) needing ${remainingRequired} classroom period(s) are placed into ${free.length} remaining period(s).`,
          remainingRequired > free.length
            ? `Shortfall of ${remainingRequired - free.length} period(s): only approved Non-Core units may lose classroom time; Core and pending units are never reduced.`
            : `The remaining time is sufficient for all requeued work.`,
        ]
      : []),
    'Lost-period recovery uses the approved topic-level Core and Non-Core counts, evaluates only the next three teaching days, holds unaffected sessions fixed and flags unresolved Core requirements. The academic calendar, working days and planning horizon are unchanged. Nothing changes in the approved schedule until an Admin or Principal approves this proposal.',
  ];
  return {
    id: newId('recovery'),
    createdAt: opts.at ?? new Date().toISOString(),
    createdBy: opts.actor,
    trigger: opts.trigger,
    baseVersion: version.version,
    cutoffDate: cutoff,
    config,
    lessons,
    metrics,
    conflicts,
    remainingAfter: requeueAll ? cutoff : lastLossDate,
    remainingAvailablePeriods: requeueAll ? free.length : subjectSlots(config, p.subject, lastLossDate ?? undefined).filter((s) => !lostKeys.has(slotKey(s))).length,
    remainingRequiredPeriods: requeueAll
      ? remainingRequired
      : lessons.filter((l) => !completeIds.has(l.nodeId)).reduce((s, l) => s + l.slots.filter((x) => !lastLossDate || x.date > lastLossDate).length + l.unscheduledPeriods, 0),
    affected,
    changes,
    explanation,
    status: 'PENDING',
    lostSlots: loss.lostSlots,
    lossDays: loss.days,
  };
}

/** Adds a proposal, superseding any earlier pending one (kept for history). */
export function attachProposal(p: Plan, proposal: RecoveryProposal | null): Plan {
  const proposals = p.proposals.map((x) => (x.status === 'PENDING' ? { ...x, status: 'SUPERSEDED' as const } : x));
  return { ...p, proposals: proposal ? [...proposals, proposal] : proposals };
}

export function approveRecovery(p: Plan, proposalId: string, actor: Actor, note: string, at = new Date().toISOString()): Plan {
  const proposal = p.proposals.find((x) => x.id === proposalId);
  if (!proposal || proposal.status !== 'PENDING') throw new Error('Only a pending proposal can be approved.');
  if (!['admin', 'principal'].includes(actor.role)) throw new Error('Only an Admin or Principal can approve a recovery proposal.');
  const version = currentVersion(p)!;
  if (proposal.baseVersion !== version.version) throw new Error('The approved schedule changed after this proposal was generated. Regenerate the proposal.');
  const next: ScheduleVersion = {
    version: version.version + 1,
    lessons: proposal.lessons,
    metrics: proposal.metrics,
    conflicts: proposal.conflicts,
    config: proposal.config,
    approvedBy: actor,
    approvedAt: at,
    reason:
      note.trim() ||
      (proposal.trigger.kind === 'CONFIG_CHANGE' ? 'Recalculated for updated Academic Configuration' : proposal.trigger.kind === 'LOST_PERIODS' ? 'Lost-period recovery approved' : 'Recovery proposal approved'),
    proposalId,
    lostSlots: proposal.lostSlots ?? version.lostSlots ?? [],
  };
  return {
    ...p,
    config: proposal.config,
    versions: [...p.versions, next],
    proposals: p.proposals.map((x) => (x.id === proposalId ? { ...x, status: 'APPROVED', review: { by: actor, at, note: note.trim() } } : x)),
  };
}

export function rejectRecovery(p: Plan, proposalId: string, actor: Actor, note: string, at = new Date().toISOString()): Plan {
  const proposal = p.proposals.find((x) => x.id === proposalId);
  if (!proposal || proposal.status !== 'PENDING') throw new Error('Only a pending proposal can be rejected.');
  if (!['admin', 'principal'].includes(actor.role)) throw new Error('Only an Admin or Principal can reject a recovery proposal.');
  if (note.trim().length < 5) throw new Error('A rejection reason is required.');
  return { ...p, proposals: p.proposals.map((x) => (x.id === proposalId ? { ...x, status: 'REJECTED', review: { by: actor, at, note: note.trim() } } : x)) };
}

/** Records execution and, for incomplete outcomes, generates the recovery proposal in the same step. */
export function recordAndPropose(p: Plan, input: ExecutionInput, actor: Actor, ctx: EngineContext, at = new Date().toISOString()): { plan: Plan; proposal: RecoveryProposal | null } {
  const recorded = recordExecution(p, input, actor, at);
  const event = recorded.execution[recorded.execution.length - 1];
  const hasIncomplete = currentVersion(recorded)!.lessons.some((l) => {
    const pr = lessonProgress(recorded, l);
    return !pr.complete && pr.lastIncomplete;
  });
  if (input.status === 'HOMEWORK_COMPLETED' || (!hasIncomplete && !pendingProposal(p))) return { plan: recorded, proposal: null };
  // Otherwise (re)generate: a stale pending proposal is superseded, or dropped if nothing remains to change.
  const proposal = generateRecovery(recorded, ctx, { trigger: { kind: 'EXECUTION', eventId: event.id, nodeId: event.nodeId, status: event.status }, actor, at });
  return { plan: attachProposal(recorded, proposal), proposal };
}

/** Records several selected lost periods in one submission and generates a single recovery proposal for them. */
export function recordLossBatchAndPropose(p: Plan, keys: string[], reason: string, note: string, actor: Actor, ctx: EngineContext, at = new Date().toISOString()): { plan: Plan; proposal: RecoveryProposal | null } {
  const recorded = recordLossBatch(p, keys, reason, note, actor, () => newId('loss'), at);
  const record = recorded.losses![recorded.losses!.length - 1];
  const proposal = generateRecovery(recorded, ctx, { trigger: { kind: 'LOST_PERIODS', lossId: record.id }, actor, at });
  return { plan: attachProposal(recorded, proposal), proposal };
}

/** Records lost periods (or a correction) and generates the recovery proposal in the same step. */
export function recordLossAndPropose(p: Plan, input: LossInput, actor: Actor, ctx: EngineContext, at = new Date().toISOString()): { plan: Plan; proposal: RecoveryProposal | null } {
  const recorded = recordLoss(p, input, actor, newId('loss'), at);
  const record = recorded.losses![recorded.losses!.length - 1];
  const proposal = generateRecovery(recorded, ctx, { trigger: { kind: 'LOST_PERIODS', lossId: record.id }, actor, at });
  return { plan: attachProposal(recorded, proposal), proposal };
}
