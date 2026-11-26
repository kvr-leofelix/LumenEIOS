/**
 * Recalculation of a teacher's schedule from the CURRENT academic configuration, persisted Core/Non-Core requirements and actual teaching.
 *
 * - Done topics get no new periods; a partly taught topic is scheduled only for what is still to be taught.
 * - Required, scheduled and taught stay separate: this module only decides what must still be scheduled and compares schedules.
 * - A recalculation is a NEW DRAFT (never an overwrite): the approved schedule stays in force until a Principal/Admin approves the draft.
 */
import { nodeIdOf } from '../../features/teacherPlan/useTeacherCoverage';
import type { PlanTopicRow } from '../teacherPlanApi';
import { summarizeCalendar, type AcademicConfig } from './calendar';
import type { EngineContext, PlannedLesson, RecalcBasis, Slot } from './engine';
import type { SyllabusNode } from './syllabus';

type RowLike = Pick<PlanTopicRow, 'topic_key' | 'coverage' | 'core_periods' | 'non_core_periods'> & Partial<Pick<PlanTopicRow, 'taught_periods' | 'remaining_core' | 'remaining_non_core'>>;

export interface RemainingInput {
  units: SyllabusNode[];
  ctx: EngineContext;
  doneIds: Set<string>;
}

/** The engine input for work that is still to be done: Done topics are left out, open topics carry only their remaining Core/Non-Core periods. */
export function remainingScheduleInput(units: SyllabusNode[], ctx: EngineContext, rows: RowLike[] | undefined | null): RemainingInput {
  const byNode = new Map((rows ?? []).map((r) => [nodeIdOf(r.topic_key), r]));
  const doneIds = new Set<string>();
  const classifications = { ...ctx.classifications };
  const open: SyllabusNode[] = [];
  for (const u of units) {
    const row = byNode.get(u.id);
    if (row?.coverage === 'done') {
      doneIds.add(u.id);
      continue;
    }
    open.push(u);
    const c = classifications[u.id];
    if (row && c && row.remaining_core !== undefined && row.remaining_non_core !== undefined) {
      classifications[u.id] = { ...c, corePeriods: row.remaining_core, nonCorePeriods: row.remaining_non_core, independentPeriods: Math.min(c.independentPeriods ?? 0, row.remaining_non_core) };
    }
  }
  return { units: open, ctx: { ...ctx, classifications }, doneIds };
}

const slotKey = (s: Slot) => `${s.date}#${s.period}`;
export const scheduledPeriods = (l: PlannedLesson | undefined) => l?.slots.length ?? 0;

/** Small deterministic hash (djb2) of any JSON-able value, used to recognise "exactly the same calendar, requirements and schedule". */
export function fingerprint(value: unknown): string {
  const s = JSON.stringify(value);
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return `fp${(h >>> 0).toString(16)}`;
}

export function scheduleFingerprint(config: AcademicConfig, after: string, lessons: PlannedLesson[]): string {
  return fingerprint({ config, after, lessons: lessons.map((l) => [l.nodeId, l.corePeriods, l.nonCorePeriods, l.independentPeriods, l.slots.map(slotKey)]) });
}

/** Do the open topics of an approved schedule already have exactly these slots? (Nothing to recalculate.) */
export function sameSlots(current: PlannedLesson[], next: PlannedLesson[], doneIds: Set<string>): boolean {
  const cur = new Map(current.map((l) => [l.nodeId, l.slots.map(slotKey).join('|')]));
  const nxt = new Map(next.map((l) => [l.nodeId, l.slots.map(slotKey).join('|')]));
  for (const [id, k] of nxt) if ((cur.get(id) ?? '') !== k) return false;
  for (const [id, k] of cur) if (!doneIds.has(id) && !nxt.has(id) && k !== '') return false;
  return true;
}

export interface LessonDiff {
  nodeId: string;
  title: string;
  previous: number;
  revised: number;
  previousRange: string;
  revisedRange: string;
  changed: boolean;
}
const range = (l: PlannedLesson | undefined) => (l && l.slots.length ? `${l.slots[0].date} → ${l.slots[l.slots.length - 1].date}` : '—');

export function diffLessons(previous: PlannedLesson[], revised: PlannedLesson[]): LessonDiff[] {
  const p = new Map(previous.map((l) => [l.nodeId, l]));
  const r = new Map(revised.map((l) => [l.nodeId, l]));
  const ids = [...new Set([...previous.map((l) => l.nodeId), ...revised.map((l) => l.nodeId)])];
  return ids.map((id) => {
    const a = p.get(id);
    const b = r.get(id);
    const prevKey = a?.slots.map(slotKey).join('|') ?? '';
    const newKey = b?.slots.map(slotKey).join('|') ?? '';
    return { nodeId: id, title: `${(b ?? a)!.number} ${(b ?? a)!.title}`.trim(), previous: scheduledPeriods(a), revised: scheduledPeriods(b), previousRange: range(a), revisedRange: range(b), changed: prevKey !== newKey };
  });
}

/** Instructional capacity of the current calendar: the whole year and the part after the planning date. */
export function calendarCapacity(config: AcademicConfig, subject: 'Mathematics' | 'Science', after: string) {
  const cal = summarizeCalendar(config);
  const perDay = config.subjectPeriodsPerDay[subject] || 0;
  const daysLeft = cal.instructionalDates.filter((d) => d > after).length;
  const periodsLeft = daysLeft * perDay;
  const reserveLeft = Math.ceil(periodsLeft / 10);
  return { calendarDays: cal.instructionalDates.length, daysLeft, periodsLeft, reserveLeft, capacityLeft: periodsLeft - reserveLeft, perDay };
}

export type { RecalcBasis };
