/**
 * Academic calendar model.
 *
 * School working days and actual instructional days are derived, never typed in:
 *   working day       = a configured school weekday inside the calendar that is not a holiday/vacation
 *   instructional day = a working day that is not an examination period or school event
 * No fixed 180/220-day assumption exists anywhere in this module.
 */

export type PlanningSubject = 'Mathematics' | 'Science';
export const PLANNING_SUBJECTS: PlanningSubject[] = ['Mathematics', 'Science'];
export const PLANNING_GRADES = [6, 7, 8] as const;
export type PlanningGrade = (typeof PLANNING_GRADES)[number];
export const GRADE_LABEL: Record<number, string> = { 6: 'VI', 7: 'VII', 8: 'VIII' };

export type CalendarEntryType = 'HOLIDAY' | 'VACATION' | 'EXAM' | 'EVENT';

export const ENTRY_TYPE_LABEL: Record<CalendarEntryType, string> = {
  HOLIDAY: 'Holiday',
  VACATION: 'Vacation',
  EXAM: 'Examination period',
  EVENT: 'School event / non-instructional day',
};

/** HOLIDAY and VACATION remove school working days; EXAM and EVENT keep the school open but remove teaching. */
export const REMOVES_WORKING_DAY: Record<CalendarEntryType, boolean> = {
  HOLIDAY: true,
  VACATION: true,
  EXAM: false,
  EVENT: false,
};

export interface CalendarEntry {
  id: string;
  type: CalendarEntryType;
  label: string;
  start: string; // YYYY-MM-DD inclusive
  end: string; // YYYY-MM-DD inclusive
}

export interface AcademicConfig {
  year: string;
  start: string;
  end: string;
  /** School working weekdays, 0 = Sunday … 6 = Saturday. */
  weekdays: number[];
  entries: CalendarEntry[];
  /** Total timetable periods per school day. */
  periodsPerDay: number;
  periodMinutes: number;
  /** Periods per instructional day timetabled for each planning subject. */
  subjectPeriodsPerDay: Record<PlanningSubject, number>;
  /** Number of instructional days to plan; null = every instructional day in the calendar. */
  horizonDays: number | null;
}

export const DEFAULT_CONFIG: AcademicConfig = {
  year: '2026-2027',
  start: '2026-04-01',
  end: '2027-03-31',
  weekdays: [1, 2, 3, 4, 5],
  entries: [],
  periodsPerDay: 8,
  periodMinutes: 40,
  subjectPeriodsPerDay: { Mathematics: 2, Science: 2 }, // default timetable: two Maths and two Science periods per instructional day
  horizonDays: null,
};

export interface NonInstructionalDate {
  date: string;
  type: CalendarEntryType | 'WEEKEND';
  label: string;
}

export interface CalendarSummary {
  calendarDays: number;
  workingDates: string[];
  instructionalDates: string[];
  planningDates: string[];
  nonInstructional: NonInstructionalDate[];
  countsByType: Record<CalendarEntryType, number>;
  schoolInstructionalMinutes: number;
  subjectAvailableMinutes: Record<PlanningSubject, number>;
  subjectAvailablePeriods: Record<PlanningSubject, number>;
}

const ISO = /^\d{4}-\d{2}-\d{2}$/;

export function isValidDate(s: string): boolean {
  if (!ISO.test(s)) return false;
  const d = new Date(`${s}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === s;
}

/** Inclusive list of ISO dates between start and end (UTC, no time-zone drift). */
export function datesBetween(start: string, end: string): string[] {
  const out: string[] = [];
  if (!isValidDate(start) || !isValidDate(end) || start > end) return out;
  for (let d = new Date(`${start}T00:00:00Z`); d.toISOString().slice(0, 10) <= end; d.setUTCDate(d.getUTCDate() + 1)) {
    out.push(d.toISOString().slice(0, 10));
    if (out.length > 800) break; // guard against absurd ranges
  }
  return out;
}

function weekday(date: string): number {
  return new Date(`${date}T00:00:00Z`).getUTCDay();
}

export function summarizeCalendar(c: AcademicConfig): CalendarSummary {
  const all = datesBetween(c.start, c.end);
  const byDate = new Map<string, CalendarEntry[]>();
  for (const e of c.entries) {
    for (const d of datesBetween(e.start, e.end)) {
      byDate.set(d, [...(byDate.get(d) ?? []), e]);
    }
  }
  const countsByType: Record<CalendarEntryType, number> = { HOLIDAY: 0, VACATION: 0, EXAM: 0, EVENT: 0 };
  const workingDates: string[] = [];
  const instructionalDates: string[] = [];
  const nonInstructional: NonInstructionalDate[] = [];
  for (const d of all) {
    if (!c.weekdays.includes(weekday(d))) continue;
    const entries = byDate.get(d) ?? [];
    const closing = entries.find((e) => REMOVES_WORKING_DAY[e.type]);
    if (closing) {
      countsByType[closing.type] += 1;
      nonInstructional.push({ date: d, type: closing.type, label: closing.label });
      continue;
    }
    workingDates.push(d);
    const blocking = entries.find((e) => !REMOVES_WORKING_DAY[e.type]);
    if (blocking) {
      countsByType[blocking.type] += 1;
      nonInstructional.push({ date: d, type: blocking.type, label: blocking.label });
      continue;
    }
    instructionalDates.push(d);
  }
  const horizon = c.horizonDays == null ? instructionalDates.length : Math.min(c.horizonDays, instructionalDates.length);
  const planningDates = instructionalDates.slice(0, horizon);
  const subjectAvailablePeriods = {
    Mathematics: planningDates.length * (c.subjectPeriodsPerDay.Mathematics || 0),
    Science: planningDates.length * (c.subjectPeriodsPerDay.Science || 0),
  };
  return {
    calendarDays: all.length,
    workingDates,
    instructionalDates,
    planningDates,
    nonInstructional,
    countsByType,
    schoolInstructionalMinutes: instructionalDates.length * c.periodsPerDay * c.periodMinutes,
    subjectAvailablePeriods,
    subjectAvailableMinutes: {
      Mathematics: subjectAvailablePeriods.Mathematics * c.periodMinutes,
      Science: subjectAvailablePeriods.Science * c.periodMinutes,
    },
  };
}

function overlaps(a: CalendarEntry, b: CalendarEntry): boolean {
  return a.start <= b.end && b.start <= a.end;
}

/** Returns every validation problem (empty array = valid). */
export function validateConfig(c: AcademicConfig): string[] {
  const errors: string[] = [];
  const m = /^(\d{4})-(\d{4})$/.exec(c.year);
  if (!m || Number(m[2]) !== Number(m[1]) + 1) errors.push('Academic year must be two consecutive years, e.g. 2026-2027.');
  if (!isValidDate(c.start) || !isValidDate(c.end)) errors.push('Calendar start and end must be valid dates.');
  else {
    if (c.start >= c.end) errors.push('Calendar end must be after calendar start.');
    if (m && (!c.start.startsWith(m[1]) || !c.end.startsWith(m[2]))) errors.push(`Calendar must start in ${m[1]} and end in ${m[2]}.`);
    if (datesBetween(c.start, c.end).length > 366) errors.push('Calendar cannot exceed 366 days.');
  }
  if (!c.weekdays.length) errors.push('Select at least one school working weekday.');
  const int = (n: number) => Number.isInteger(n);
  if (!int(c.periodsPerDay) || c.periodsPerDay < 1 || c.periodsPerDay > 12) errors.push('Periods per day must be a whole number from 1 to 12.');
  if (!int(c.periodMinutes) || c.periodMinutes < 10 || c.periodMinutes > 180) errors.push('Period duration must be a whole number of minutes from 10 to 180.');
  let subjectTotal = 0;
  for (const s of PLANNING_SUBJECTS) {
    const p = c.subjectPeriodsPerDay[s];
    if (!int(p) || p < 0) errors.push(`${s} periods per day must be a whole number of 0 or more.`);
    else subjectTotal += p;
  }
  if (subjectTotal > c.periodsPerDay) errors.push(`Mathematics and Science periods (${subjectTotal}) exceed the ${c.periodsPerDay} periods in a school day.`);

  const ids = new Set<string>();
  c.entries.forEach((e, i) => {
    const name = e.label.trim() || `Entry ${i + 1}`;
    if (!e.label.trim()) errors.push(`Calendar entry ${i + 1} needs a description.`);
    if (ids.has(e.id)) errors.push(`Calendar entry "${name}" is duplicated.`);
    ids.add(e.id);
    if (!isValidDate(e.start) || !isValidDate(e.end)) {
      errors.push(`"${name}" has an invalid date.`);
      return;
    }
    if (e.start > e.end) errors.push(`"${name}" ends before it starts.`);
    if (isValidDate(c.start) && isValidDate(c.end) && (e.start < c.start || e.end > c.end)) errors.push(`"${name}" falls outside the academic calendar.`);
  });
  // Conflicting entries: any two overlapping entries are reported, so a closure never silently hides an exam or event.
  for (let i = 0; i < c.entries.length; i++) {
    for (let j = i + 1; j < c.entries.length; j++) {
      const a = c.entries[i];
      const b = c.entries[j];
      if (!isValidDate(a.start) || !isValidDate(a.end) || !isValidDate(b.start) || !isValidDate(b.end)) continue;
      if (overlaps(a, b)) {
        errors.push(`Conflict: "${a.label || ENTRY_TYPE_LABEL[a.type]}" (${ENTRY_TYPE_LABEL[a.type]}) overlaps "${b.label || ENTRY_TYPE_LABEL[b.type]}" (${ENTRY_TYPE_LABEL[b.type]}).`);
      }
    }
  }
  if (!errors.length) {
    const s = summarizeCalendar(c);
    if (!s.instructionalDates.length) errors.push('The calendar has no instructional days.');
    if (c.horizonDays != null && (!int(c.horizonDays) || c.horizonDays < 1)) errors.push('Planning horizon must be at least 1 instructional day.');
    else if (c.horizonDays != null && c.horizonDays > s.instructionalDates.length) {
      errors.push(`Planning horizon (${c.horizonDays}) exceeds the ${s.instructionalDates.length} instructional days in this calendar.`);
    }
  }
  return errors;
}

/** Converts the earlier prototype configuration (single holiday string, typed day counts) without losing entries. */
export function migrateLegacyConfig(raw: unknown): AcademicConfig | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  if (Array.isArray(r.entries) && r.subjectPeriodsPerDay) return { ...DEFAULT_CONFIG, ...(r as unknown as AcademicConfig) };
  if (typeof r.year !== 'string' || typeof r.start !== 'string') return null;
  const holidays = String(r.holidays ?? '')
    .split(/[\s,]+/)
    .filter(Boolean)
    .filter(isValidDate);
  const periods = Number(r.periods) || 1;
  return {
    ...DEFAULT_CONFIG,
    year: r.year,
    start: r.start,
    end: String(r.end ?? DEFAULT_CONFIG.end),
    weekdays: Array.isArray(r.weekdays) ? (r.weekdays as number[]) : DEFAULT_CONFIG.weekdays,
    periodMinutes: Number(r.minutes) || DEFAULT_CONFIG.periodMinutes,
    periodsPerDay: Math.max(DEFAULT_CONFIG.periodsPerDay, periods * 2),
    subjectPeriodsPerDay: { Mathematics: periods, Science: periods },
    horizonDays: null,
    entries: holidays.map((d, i) => ({ id: `legacy-holiday-${i}`, type: 'HOLIDAY', label: 'Non-teaching date (migrated)', start: d, end: d })),
  };
}

export function sameConfig(a: AcademicConfig, b: AcademicConfig): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

const CONFIG_FIELD_LABEL: Record<keyof AcademicConfig, string> = {
  year: 'academic year',
  start: 'calendar start',
  end: 'calendar end',
  weekdays: 'working weekdays',
  entries: 'holidays / vacations / exams / events',
  periodsPerDay: 'periods per day',
  periodMinutes: 'period duration',
  subjectPeriodsPerDay: 'subject periods per day',
  horizonDays: 'planning horizon',
};

/** Human-readable list of fields that differ between two configurations (for conflict review). */
export function configDifferences(a: AcademicConfig, b: AcademicConfig): string[] {
  return (Object.keys(CONFIG_FIELD_LABEL) as (keyof AcademicConfig)[]).filter((k) => JSON.stringify(a[k]) !== JSON.stringify(b[k])).map((k) => CONFIG_FIELD_LABEL[k]);
}
