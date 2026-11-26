import { describe, expect, it } from 'vitest';
import { DEFAULT_CONFIG, migrateLegacyConfig, summarizeCalendar, validateConfig } from '../../lib/planning/calendar';
import { smallConfig } from './fixtures';

describe('academic calendar', () => {
  it('distinguishes school working days from instructional days', () => {
    const s = summarizeCalendar(smallConfig);
    // 1–14 April 2026 weekdays: 1,2,3,6,7,8,9,10,13,14 → holiday removes 3 Apr; exam keeps 6 Apr as a working day.
    expect(s.workingDates.slice(0, 4)).toEqual(['2026-04-01', '2026-04-02', '2026-04-06', '2026-04-07']);
    expect(s.instructionalDates.slice(0, 3)).toEqual(['2026-04-01', '2026-04-02', '2026-04-07']);
    expect(s.workingDates.length - s.instructionalDates.length).toBe(1);
    expect(s.countsByType).toMatchObject({ HOLIDAY: 1, EXAM: 1 });
    expect(s.planningDates).toHaveLength(10);
    expect(s.subjectAvailablePeriods.Mathematics).toBe(10);
  });

  it('derives instructional days from the calendar, with no fixed 180/220 assumption', () => {
    const s = summarizeCalendar(DEFAULT_CONFIG);
    expect(s.instructionalDates.length).toBe(s.workingDates.length);
    expect(s.instructionalDates.length).not.toBe(180);
    const withVacation = summarizeCalendar({ ...DEFAULT_CONFIG, entries: [{ id: 'v', type: 'VACATION', label: 'Summer', start: '2026-05-01', end: '2026-06-30' }] });
    expect(withVacation.instructionalDates.length).toBeLessThan(s.instructionalDates.length);
  });

  it('recalculates available time when periods or duration change', () => {
    const a = summarizeCalendar(smallConfig);
    const b = summarizeCalendar({ ...smallConfig, periodMinutes: 45, subjectPeriodsPerDay: { Mathematics: 2, Science: 1 } });
    expect(b.subjectAvailableMinutes.Mathematics).toBe(a.subjectAvailableMinutes.Mathematics * 2 * (45 / 40));
  });

  it('validates dates, periods and conflicting entries', () => {
    expect(validateConfig(smallConfig)).toEqual([]);
    expect(validateConfig({ ...smallConfig, year: '2026-2028' }).join()).toMatch(/consecutive/);
    expect(validateConfig({ ...smallConfig, periodsPerDay: 1, subjectPeriodsPerDay: { Mathematics: 1, Science: 1 } }).join()).toMatch(/exceed/);
    expect(validateConfig({ ...smallConfig, periodMinutes: 5 }).join()).toMatch(/duration/);
    expect(validateConfig({ ...smallConfig, horizonDays: 5000 }).join()).toMatch(/exceeds/);
    const conflicting = {
      ...smallConfig,
      entries: [...smallConfig.entries, { id: 'e2', type: 'EVENT' as const, label: 'Sports day', start: '2026-04-03', end: '2026-04-03' }],
    };
    expect(validateConfig(conflicting).join()).toMatch(/Conflict: "Holiday".*overlaps "Sports day"/);
    expect(validateConfig({ ...smallConfig, entries: [{ id: 'z', type: 'HOLIDAY', label: 'Out', start: '2028-01-01', end: '2028-01-01' }] }).join()).toMatch(/outside/);
    expect(validateConfig({ ...smallConfig, entries: [{ id: 'z', type: 'HOLIDAY', label: 'Bad', start: '2026-04-09', end: '2026-04-02' }] }).join()).toMatch(/ends before/);
    expect(validateConfig({ ...smallConfig, weekdays: [] }).join()).toMatch(/weekday/);
  });

  it('migrates the earlier prototype configuration without losing non-teaching dates', () => {
    const c = migrateLegacyConfig({ year: '2026-2027', start: '2026-04-01', end: '2027-03-31', days: 180, horizon: 180, periods: 2, minutes: 45, holidays: '2026-04-02, bad', weekdays: [1, 2, 3, 4, 5] })!;
    expect(c.entries).toEqual([expect.objectContaining({ type: 'HOLIDAY', start: '2026-04-02' })]);
    expect(c.periodMinutes).toBe(45);
    expect(c.subjectPeriodsPerDay.Mathematics).toBe(2);
    expect(validateConfig(c)).toEqual([]);
  });
});
