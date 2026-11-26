import { describe, expect, it } from 'vitest';
import { calendarCapacity, diffLessons, fingerprint, remainingScheduleInput, sameSlots, scheduleFingerprint } from '../../lib/planning/recalc';
import { DEFAULT_CONFIG } from '../../lib/planning/calendar';
import type { EngineContext, PlannedLesson } from '../../lib/planning/engine';
import type { SyllabusNode } from '../../lib/planning/syllabus';

const unit = (id: string) => ({ id, number: id.toUpperCase(), title: `Topic ${id}`, kind: 'TOPIC' }) as unknown as SyllabusNode;
const cls = (id: string, core: number, non: number) => ({ nodeId: id, status: 'TEACHER_CUSTOM', value: 'MIXED', corePeriods: core, nonCorePeriods: non, independentPeriods: 0 });
const ctx = (): EngineContext => ({ datasets: [], relationships: [], classifications: { a: cls('a', 3, 1), b: cls('b', 4, 0), c: cls('c', 0, 4) } as unknown as EngineContext['classifications'] });
const lesson = (id: string, slots: [string, number][]) => ({ nodeId: id, number: id, title: `Topic ${id}`, corePeriods: 1, nonCorePeriods: 0, independentPeriods: 0, slots: slots.map(([date, period]) => ({ date, period, kind: 'CORE' })) }) as unknown as PlannedLesson;

describe('remainingScheduleInput', () => {
  const rows = [
    { topic_key: 'a', coverage: 'done' as const, core_periods: 3, non_core_periods: 1, taught_periods: 4, remaining_core: 0, remaining_non_core: 0 },
    { topic_key: 'b', coverage: 'in_progress' as const, core_periods: 4, non_core_periods: 0, taught_periods: 3, remaining_core: 1, remaining_non_core: 0 },
    { topic_key: 'c', coverage: 'not_done' as const, core_periods: 0, non_core_periods: 4, taught_periods: 0, remaining_core: 0, remaining_non_core: 4 },
  ];
  it('leaves Done topics out and schedules only what is still to be taught, keeping classifications', () => {
    const out = remainingScheduleInput([unit('a'), unit('b'), unit('c')], ctx(), rows);
    expect(out.units.map((u) => u.id)).toEqual(['b', 'c']);
    expect([...out.doneIds]).toEqual(['a']);
    expect(out.ctx.classifications.b).toMatchObject({ corePeriods: 1, nonCorePeriods: 0 }); // 4 required, 3 taught
    expect(out.ctx.classifications.c).toMatchObject({ corePeriods: 0, nonCorePeriods: 4 });
    expect(out.ctx.classifications.a).toMatchObject({ corePeriods: 3, nonCorePeriods: 1 }); // untouched record (not scheduled)
  });
  it('falls back to the full requirement when the backend sends no remaining figures, and never mutates the input', () => {
    const c = ctx();
    const out = remainingScheduleInput([unit('b')], c, [{ topic_key: 'b', coverage: 'not_done', core_periods: 4, non_core_periods: 0 }]);
    expect(out.ctx.classifications.b).toMatchObject({ corePeriods: 4 });
    expect(c.classifications.b.corePeriods).toBe(4);
    expect(remainingScheduleInput([unit('b')], c, null).units).toHaveLength(1);
  });
});

describe('comparison helpers', () => {
  it('diffLessons reports only real changes in scheduled periods or dates', () => {
    const prev = [lesson('a', [['2026-11-16', 1]]), lesson('b', [['2026-11-17', 1], ['2026-11-17', 2]])];
    const next = [lesson('a', [['2026-11-16', 1]]), lesson('b', [['2026-11-18', 1]]), lesson('c', [['2026-11-19', 1]])];
    const d = diffLessons(prev, next);
    expect(d.filter((x) => x.changed).map((x) => [x.nodeId, x.previous, x.revised])).toEqual([['b', 2, 1], ['c', 0, 1]]);
    expect(d.find((x) => x.nodeId === 'a')!.changed).toBe(false);
  });
  it('sameSlots ignores Done topics and detects any moved slot', () => {
    const cur = [lesson('a', [['2026-11-10', 1]]), lesson('b', [['2026-11-17', 1]])];
    expect(sameSlots(cur, [lesson('b', [['2026-11-17', 1]])], new Set(['a']))).toBe(true);
    expect(sameSlots(cur, [lesson('b', [['2026-11-18', 1]])], new Set(['a']))).toBe(false);
    expect(sameSlots(cur, [lesson('b', [['2026-11-17', 1]])], new Set())).toBe(false);
  });
  it('fingerprints are stable for identical input and change with the calendar', () => {
    const l = [lesson('a', [['2026-11-16', 1]])];
    expect(scheduleFingerprint(DEFAULT_CONFIG, '2026-11-15', l)).toBe(scheduleFingerprint({ ...DEFAULT_CONFIG }, '2026-11-15', l));
    const holiday = { ...DEFAULT_CONFIG, entries: [{ id: 'h', type: 'HOLIDAY' as const, label: 'x', start: '2026-12-01', end: '2026-12-02' }] };
    expect(scheduleFingerprint(holiday, '2026-11-15', l)).not.toBe(scheduleFingerprint(DEFAULT_CONFIG, '2026-11-15', l));
    expect(fingerprint({ a: 1 })).toBe(fingerprint({ a: 1 }));
  });
  it('calendarCapacity counts only instructional days after the planning date, with its own 10% reserve', () => {
    const cfg = { ...DEFAULT_CONFIG, start: '2026-04-01', end: '2026-04-30', entries: [] };
    const cap = calendarCapacity(cfg, 'Mathematics', '2026-04-10'); // weekdays 13..30 April = 14 days x 2 periods
    expect(cap).toMatchObject({ daysLeft: 14, periodsLeft: 28, reserveLeft: 3, capacityLeft: 25, perDay: 2 });
    const holiday = calendarCapacity({ ...cfg, entries: [{ id: 'h', type: 'HOLIDAY', label: 'x', start: '2026-04-20', end: '2026-04-22' }] }, 'Mathematics', '2026-04-10');
    expect(holiday.periodsLeft).toBe(22);
  });
});
