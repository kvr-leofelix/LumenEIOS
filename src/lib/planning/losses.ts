/**
 * Lost-period recording and Core-priority recovery. Recovery never changes the academic calendar, the plan's working
 * days or its planning horizon, and never edits the approved schedule directly: it only feeds a recovery proposal.
 *
 * Loss records are per scheduled period (identified by date + subject period index, shown to users as the plan-wide
 * period number). They are append-only; a correction is a new record that supersedes an earlier one.
 */
import type { Actor } from './governance';
import { summarizeCalendar } from './calendar';
import type { AcademicConfig } from './calendar';
import { slotKind, subjectSlots } from './engine';
import type { EngineContext, PeriodKind, PlannedLesson, Slot } from './engine';
import type { Plan } from './execution';

export const LOSS_REASONS = ['Election Duties', 'Census Duties', 'Teacher Training', 'Health Drive', 'Extreme Weather', 'Local Festival', 'Administrative Work', 'Unplanned school event', 'Other'] as const;

/** Number of teaching days after a loss that recovery evaluates. */
export const RECOVERY_WINDOW_DAYS = 3;

export interface LostPeriodRecord {
  id: string;
  date: string;
  periodsLost: number;
  periods?: number[];
  reason: string;
  note: string;
  recordedBy: Actor;
  recordedAt: string;
  supersedes: string | null;
  correctionReason?: string;
  /** Records submitted together share a batch id. */
  batchId?: string;
}

export interface LossDaySummary {
  date: string;
  reason: string;
  scheduled: number;
  lost: number;
  retained: { nodeId: string; title: string; periods: number; classification: string }[];
  homework: { nodeId: string; title: string; periods: number }[];
  incomplete: { nodeId: string; title: string; periods: number }[];
  released: number;
  /** Lost Core periods given a classroom slot in the recovery window. */
  recovered?: { nodeId: string; title: string; periods: number }[];
  /** Explanation of every Core period that could not be recovered. */
  unresolved?: string[];
  /** Period-level changes made for this loss. */
  moves?: PeriodMove[];
}

/** One changed period in a recovery proposal. */
export interface PeriodMove {
  date: string;
  period: number;
  number: number;
  kind: 'LOST' | 'CORE_RECOVERED' | 'NON_CORE_TO_INDEPENDENT';
  nodeId: string;
  title: string;
  /** For CORE_RECOVERED: the topic whose Non-Core session gave up the slot (null = the slot was unused). */
  displacedNodeId?: string | null;
  displacedTitle?: string | null;
  reason: string;
}

const key = (s: Pick<Slot, 'date' | 'period'>) => s.date + '#' + String(s.period).padStart(3, '0');
const versionOf = (p: Plan) => p.versions[p.versions.length - 1];

/**
 * Plan-wide scheduled period numbers (1, 2, 3 …) over every subject period in the plan's original approved calendar.
 * The calendar never changes after approval, so a period keeps its number across schedule versions.
 */
export function periodNumbers(p: Plan): Map<string, number> {
  const config = p.versions[0]?.config ?? p.config;
  return new Map(subjectSlots(config, p.subject).map((s, i) => [key(s), i + 1]));
}

export const periodNumberOf = (numbers: Map<string, number>, s: Pick<Slot, 'date' | 'period'>) => numbers.get(key(s)) ?? 0;

export function effectiveLosses(p: Plan): LostPeriodRecord[] {
  const superseded = new Set((p.losses ?? []).map((r) => r.supersedes));
  return (p.losses ?? []).filter((r) => !superseded.has(r.id));
}

/** Keys of every period recorded as lost (effective records) or already applied as lost in the approved schedule. */
export function lostKeys(p: Plan): Set<string> {
  const keys = new Set<string>();
  for (const r of effectiveLosses(p)) for (const period of r.periods ?? []) keys.add(key({ date: r.date, period }));
  for (const s of versionOf(p)?.lostSlots ?? []) keys.add(key(s));
  return keys;
}

export function lostByDate(p: Plan): Map<string, { lost: number; records: LostPeriodRecord[] }> {
  const m = new Map<string, { lost: number; records: LostPeriodRecord[] }>();
  for (const r of effectiveLosses(p)) {
    const x = m.get(r.date) ?? { lost: 0, records: [] };
    m.set(r.date, { lost: x.lost + r.periodsLost, records: [...x.records, r] });
  }
  return m;
}

export function scheduledOnDate(p: Plan, date: string): number {
  const v = versionOf(p);
  return v ? v.lessons.reduce((n, l) => n + l.slots.filter((s) => s.date === date).length, 0) + (v.lostSlots ?? []).filter((s) => s.date === date).length : 0;
}

/** Whether a topic's classroom teaching is recorded as complete (execution corrections respected). */
function topicTaught(p: Plan, nodeId: string): boolean {
  const superseded = new Set(p.execution.map((e) => e.supersedes).filter(Boolean));
  return p.execution.some((e) => e.nodeId === nodeId && e.status === 'TAUGHT' && !superseded.has(e.id));
}

export type CandidateState = 'AVAILABLE' | 'LOST' | 'TAUGHT';

export interface LossCandidate {
  key: string;
  number: number;
  date: string;
  period: number;
  nodeId: string;
  title: string;
  kind: PeriodKind;
  state: CandidateState;
}

/** Every classroom period of the current approved schedule, with whether it can still be recorded as lost. */
export function lossCandidates(p: Plan): LossCandidate[] {
  const v = versionOf(p);
  if (!v) return [];
  const numbers = periodNumbers(p);
  const lost = lostKeys(p);
  return v.lessons
    .flatMap((l) =>
      l.slots.map((s) => ({
        key: key(s),
        number: periodNumberOf(numbers, s),
        date: s.date,
        period: s.period,
        nodeId: l.nodeId,
        title: `${l.number} ${l.title}`.trim(),
        kind: slotKind(l, s),
        state: (lost.has(key(s)) ? 'LOST' : topicTaught(p, l.nodeId) ? 'TAUGHT' : 'AVAILABLE') as CandidateState,
      })),
    )
    .sort((a, b) => a.key.localeCompare(b.key));
}

export interface LossInput {
  date: string;
  periodsLost: number;
  periods?: number[];
  reason: string;
  note?: string;
  correctsId?: string;
  correctionReason?: string;
  batchId?: string;
}

export function recordLoss(p: Plan, input: LossInput, actor: Actor, id: string, at = new Date().toISOString()): Plan {
  if (p.status !== 'APPROVED') throw new Error('Lost periods require an approved plan.');
  if (!['teacher', 'admin'].includes(actor.role)) throw new Error('Only a teacher or Admin can record lost periods.');
  const v = versionOf(p)!;
  const corrected = input.correctsId ? effectiveLosses(p).find((r) => r.id === input.correctsId) : undefined;
  if (input.correctsId && (!corrected || corrected.date !== input.date || (input.correctionReason ?? '').trim().length < 5)) throw new Error('Select a current record on this date and explain the correction.');
  if (corrected && (v.lostSlots ?? []).some((s) => s.date === corrected.date && (!corrected.periods || corrected.periods.includes(s.period)))) throw new Error('This loss already has an approved recovery. An approved version cannot be undone by editing a loss record.');
  const periods = input.periods;
  if (!periods || periods.length !== input.periodsLost || new Set(periods).size !== periods.length || (!corrected && !periods.length)) throw new Error('Select one or more scheduled period numbers explicitly. Each period can be selected only once.');
  if (corrected && periods.some((x) => !(corrected.periods ?? []).includes(x))) throw new Error('A correction can only keep or withdraw periods of the original record.');
  if (!(LOSS_REASONS as readonly string[]).includes(input.reason)) throw new Error('Choose a reason for the lost periods.');
  const other = effectiveLosses(p).filter((r) => r.id !== corrected?.id);
  if (other.some((r) => r.date === input.date && !r.periods && r.periodsLost > 0)) throw new Error('A legacy loss on this date lacks period numbers. Correct it first.');
  for (const period of periods) {
    if (other.some((r) => r.date === input.date && r.periods?.includes(period)) || (v.lostSlots ?? []).some((s) => s.date === input.date && s.period === period)) {
      throw new Error(`Duplicate loss: ${input.date} period ${period} is already recorded as lost.`);
    }
    const lesson = v.lessons.find((l) => l.slots.some((s) => s.date === input.date && s.period === period));
    if (!lesson) throw new Error('Each selected period must exist in the current approved schedule.');
    if (topicTaught(p, lesson.nodeId)) throw new Error(`"${lesson.title}" is recorded as taught. Correct the classroom execution record before recording a loss for it.`);
  }
  const record: LostPeriodRecord = {
    id,
    date: input.date,
    periodsLost: periods.length,
    periods: [...periods].sort((a, b) => a - b),
    reason: input.reason,
    note: (input.note ?? '').trim(),
    recordedBy: actor,
    recordedAt: at,
    supersedes: corrected?.id ?? null,
    ...(corrected ? { correctionReason: input.correctionReason!.trim() } : {}),
    ...(input.batchId ? { batchId: input.batchId } : {}),
  };
  return { ...p, losses: [...(p.losses ?? []), record] };
}

/** Records several selected periods (any dates) in one submission: one record per date, sharing a batch id. */
export function recordLossBatch(p: Plan, keys: string[], reason: string, note: string, actor: Actor, newRecordId: () => string, at = new Date().toISOString()): Plan {
  if (!keys.length) throw new Error('Select at least one scheduled period.');
  if (new Set(keys).size !== keys.length) throw new Error('Each period can be selected only once.');
  if (!(LOSS_REASONS as readonly string[]).includes(reason)) throw new Error('Choose a reason for the lost periods.');
  const byKey = new Map(lossCandidates(p).map((c) => [c.key, c]));
  const chosen = keys.map((k) => byKey.get(k));
  if (chosen.some((c) => !c)) throw new Error('Each selected period must exist in the current approved schedule.');
  const dup = chosen.find((c) => c!.state === 'LOST');
  if (dup) throw new Error(`Duplicate loss: period ${dup.number} (${dup.date}) is already recorded as lost.`);
  const batchId = newRecordId();
  let next = p;
  for (const date of [...new Set(chosen.map((c) => c!.date))].sort()) {
    const periods = chosen.filter((c) => c!.date === date).map((c) => c!.period);
    next = recordLoss(next, { date, periodsLost: periods.length, periods, reason, note, batchId }, actor, newRecordId(), at);
  }
  return next;
}

/**
 * Applies recorded, not-yet-approved lost periods to a schedule:
 *  - each lost slot is removed (the original approved version keeps it);
 *  - a lost Non-Core period becomes tracked independent learning (its requirement is preserved, never counted as taught);
 *  - a lost Core period is recovered, if possible, within the next RECOVERY_WINDOW_DAYS teaching days, into (in order of
 *    preference) the same topic's own later Non-Core session, an unused period, or a later topic's approved Non-Core
 *    session; a displaced Non-Core session moves to independent learning. A slot is never taken from a completed topic,
 *    another Core session, or before the lost topic's approved prerequisites have finished.
 *  - Core that cannot be recovered stays on the topic as `coreUnscheduled` and is reported as unresolved, with reasons.
 * Unaffected sessions are held fixed: topics are never pushed forward wholesale.
 */
export function applyLosses(
  p: Plan,
  lessonsIn: PlannedLesson[],
  lostSlotsIn: Slot[],
  completeIds: Set<string>,
  ctx: EngineContext,
  config: AcademicConfig,
): { lessons: PlannedLesson[]; lostSlots: Slot[]; days: LossDaySummary[]; changed: boolean } {
  const lessons = lessonsIn.map((l) => ({ ...l, slots: [...l.slots], explanation: [...l.explanation], lossNotes: (l.lossNotes ?? []).map((n) => ({ ...n })) }));
  const numbers = periodNumbers(p);
  const lostSlots = [...lostSlotsIn];
  const appliedKeys = new Set(lostSlots.map(key));
  const records = effectiveLosses(p);
  if (records.some((r) => r.periodsLost > 0 && !r.periods)) throw new Error('Legacy lost-period records need explicit period numbers before recovery. No periods were guessed.');
  const allLost = new Set([...appliedKeys, ...records.flatMap((r) => (r.periods ?? []).map((period) => key({ date: r.date, period })))]);
  const days: LossDaySummary[] = [];
  const removed = new Map<string, { l: (typeof lessons)[number]; s: Slot }>();
  for (const l of lessons) {
    for (const s of l.slots) if (allLost.has(key(s)) && !appliedKeys.has(key(s))) removed.set(key(s), { l, s });
    l.slots = l.slots.filter((s) => !removed.has(key(s)));
  }
  const indexOf = new Map(lessons.map((l, i) => [l.nodeId, i]));
  const prereqsOf = (nodeId: string) => ctx.relationships.filter((r) => r.status === 'APPROVED' && r.type === 'PREREQUISITE' && r.toNodeId === nodeId).map((r) => r.fromNodeId);
  const dependentsOf = (nodeId: string) => ctx.relationships.filter((r) => r.status === 'APPROVED' && r.type === 'PREREQUISITE' && r.fromNodeId === nodeId).map((r) => r.toNodeId);
  const ownerOf = (k: string) => lessons.find((x) => x.slots.some((v) => key(v) === k));

  for (const record of [...records].sort((a, b) => a.date.localeCompare(b.date) || a.recordedAt.localeCompare(b.recordedAt))) {
    const selected = (record.periods ?? []).filter((period) => !appliedKeys.has(key({ date: record.date, period })));
    if (!selected.length) continue;
    const day: LossDaySummary = { date: record.date, reason: record.reason, scheduled: scheduledOnDate(p, record.date), lost: selected.length, retained: [], homework: [], incomplete: [], released: 0, recovered: [], unresolved: [], moves: [] };
    const carry = new Map<string, { core: number; nonCore: number }>();
    for (const period of selected.sort((a, b) => a - b)) {
      const entry = removed.get(key({ date: record.date, period }));
      if (!entry || completeIds.has(entry.l.nodeId)) throw new Error('A selected lost period no longer matches an incomplete classroom session.');
      lostSlots.push(entry.s);
      appliedKeys.add(key(entry.s));
      const kind = slotKind(entry.l, entry.s);
      const need = carry.get(entry.l.nodeId) ?? { core: 0, nonCore: 0 };
      if (kind === 'CORE') need.core++;
      else need.nonCore++;
      carry.set(entry.l.nodeId, need);
      day.moves!.push({ date: entry.s.date, period: entry.s.period, number: periodNumberOf(numbers, entry.s), kind: 'LOST', nodeId: entry.l.nodeId, title: entry.l.title, reason: `${kind === 'CORE' ? 'Core' : 'Non-Core'} period lost (${record.reason}).` });
    }
    const windowDates = summarizeCalendar(config).planningDates.filter((d) => d > record.date).slice(0, RECOVERY_WINDOW_DAYS);
    const windowSlots = subjectSlots(config, p.subject).filter((s) => windowDates.includes(s.date) && !allLost.has(key(s)));

    for (const l of lessons) {
      const need = carry.get(l.nodeId);
      if (!need) continue;
      const note = { date: record.date, reason: record.reason, homework: need.nonCore, incomplete: 0, recovered: 0, periods: selected, detail: '' };
      if (need.nonCore) {
        l.independentPeriods += need.nonCore;
        l.lossHomeworkPeriods = (l.lossHomeworkPeriods ?? 0) + need.nonCore;
        day.homework.push({ nodeId: l.nodeId, title: l.title, periods: need.nonCore });
      }
      const idx = indexOf.get(l.nodeId)!;
      // Recovered Core may not be taught before an approved prerequisite of this topic has finished in class.
      const prereqEnd = prereqsOf(l.nodeId)
        .map((id) => lessons.find((x) => x.nodeId === id))
        .filter((x): x is (typeof lessons)[number] => !!x && !completeIds.has(x.nodeId))
        .flatMap((x) => x.slots.map(key))
        .sort()
        .pop();
      const dependents = new Set(dependentsOf(l.nodeId));
      const ranked: { s: Slot; rank: number; owner: (typeof lessons)[number] | undefined }[] = [];
      for (const s of windowSlots) {
        const k = key(s);
        if (prereqEnd && k <= prereqEnd) continue;
        const owner = ownerOf(k);
        if (!owner) {
          ranked.push({ s, rank: 1, owner });
          continue;
        }
        const ownSlot = owner.slots.find((v) => key(v) === k)!;
        if (completeIds.has(owner.nodeId) || slotKind(owner, ownSlot) !== 'NON_CORE' || !['APPROVED', 'DEMO_DEFAULT', 'TEACHER_CUSTOM'].includes(owner.requirementStatus ?? '')) continue;
        // An approved dependent's session is only usable if the dependent has not started Core teaching before it.
        if (dependents.has(owner.nodeId) && owner.slots.some((v) => slotKind(owner, v) === 'CORE' && key(v) < k)) continue;
        if (owner.nodeId === l.nodeId) ranked.push({ s, rank: 0, owner });
        else if ((indexOf.get(owner.nodeId) ?? -1) > idx) ranked.push({ s, rank: 2, owner });
        // An earlier topic's Non-Core session is left in place: recovery does not reorder earlier work.
      }
      ranked.sort((a, b) => a.rank - b.rank || key(a.s).localeCompare(key(b.s)));
      const picks = ranked.slice(0, need.core);
      for (const { s, owner } of picks) {
        const k = key(s);
        if (owner) {
          owner.slots = owner.slots.filter((v) => key(v) !== k);
          owner.independentPeriods++;
          owner.lossHomeworkPeriods = (owner.lossHomeworkPeriods ?? 0) + 1;
          owner.explanation.push(`Non-Core session ${s.date} period ${s.period} (#${periodNumberOf(numbers, s)}) moves to independent learning so that ${owner.nodeId === l.nodeId ? 'this topic' : `"${l.title}"`} can recover a lost Core period. The Non-Core requirement is kept and tracked; it is not classroom teaching.`);
          day.homework.push({ nodeId: owner.nodeId, title: owner.title, periods: 1 });
          day.moves!.push({ date: s.date, period: s.period, number: periodNumberOf(numbers, s), kind: 'NON_CORE_TO_INDEPENDENT', nodeId: owner.nodeId, title: owner.title, reason: `Released for Core recovery of "${l.title}" (lost ${record.date}).` });
        }
        l.slots.push({ date: s.date, period: s.period, kind: 'CORE' });
        day.moves!.push({
          date: s.date,
          period: s.period,
          number: periodNumberOf(numbers, s),
          kind: 'CORE_RECOVERED',
          nodeId: l.nodeId,
          title: l.title,
          displacedNodeId: owner?.nodeId ?? null,
          displacedTitle: owner?.title ?? null,
          reason: owner ? `Lost Core period recovered in place of a Non-Core session of "${owner.title}".` : 'Lost Core period recovered in an unused period.',
        });
      }
      note.recovered = picks.length;
      note.incomplete = need.core - picks.length;
      if (note.incomplete > 0) {
        l.unscheduledPeriods += note.incomplete;
        l.coreUnscheduled = (l.coreUnscheduled ?? 0) + note.incomplete;
        const why = windowDates.length
          ? `no eligible Non-Core or unused ${p.subject} period remains in the next ${windowDates.length} teaching day(s) (${windowDates[0]} – ${windowDates[windowDates.length - 1]})${prereqEnd ? ' after its approved prerequisite finishes' : ''}`
          : 'no teaching days remain in the planning horizon after the loss';
        day.unresolved!.push(`"${l.title}": ${note.incomplete} Core period(s) unresolved — ${why}. Approve additional time or a later recovery.`);
        day.incomplete.push({ nodeId: l.nodeId, title: l.title, periods: note.incomplete });
      }
      if (picks.length) day.recovered!.push({ nodeId: l.nodeId, title: l.title, periods: picks.length });
      note.detail = `${need.core} Core and ${need.nonCore} Non-Core period(s) lost; ${picks.length} Core recovered, ${note.incomplete} Core awaiting recovery.`;
      l.lossNotes.push(note);
      l.explanation.push(
        `${record.date} (${record.reason}): ${need.core} Core period(s) lost — ${picks.length} recovered within the next ${RECOVERY_WINDOW_DAYS} teaching days, ${note.incomplete} awaiting recovery. ` +
          `${need.nonCore} lost Non-Core period(s) are tracked as independent learning, never as classroom teaching.`,
      );
    }
    for (const l of lessons) {
      const retained = l.slots.filter((s) => s.date === record.date).length;
      if (retained) day.retained.push({ nodeId: l.nodeId, title: l.title, periods: retained, classification: l.classification });
    }
    days.push(day);
  }
  for (const l of lessons) {
    l.slots.sort((a, b) => a.date.localeCompare(b.date) || a.period - b.period);
    l.classroomPeriods = l.slots.length + l.unscheduledPeriods;
  }
  return { lessons, lostSlots, days, changed: days.length > 0 };
}
