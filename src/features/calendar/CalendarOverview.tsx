import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, CalendarDays } from 'lucide-react';
import { cn } from '../../lib/utils';
import {
  CATEGORY_META, addDays, eventsOn, friendlyDate, fromIso, monthGrid, monthStart, sortForDay, toIso, todayIso, upcoming,
  useCalendarFeed,
} from './calendarModel';

/**
 * Small calendar for the opening dashboard of every role: this month with a colour dot per kind of item, and the next
 * few deadlines, holidays and exams. The whole card opens the full calendar (on the clicked day, when there is one).
 */
export const CalendarOverview: React.FC<{ className?: string }> = ({ className }) => {
  const navigate = useNavigate();
  const today = todayIso();
  const anchor = useMemo(() => monthStart(new Date()), []);
  const grid = useMemo(() => monthGrid(anchor), [anchor]);
  const start = toIso(grid[0]);
  const horizon = toIso(addDays(new Date(), 45));
  const end = horizon > toIso(grid[41]) ? horizon : toIso(grid[41]);
  const { feed, loading, error } = useCalendarFeed(start, end);
  const events = feed?.events ?? [];
  const next = upcoming(events, today, 5);
  const open = (date?: string) => navigate(date ? `/calendar?date=${date}` : '/calendar');

  return (
    <div
      role="link"
      tabIndex={0}
      aria-label="Open the full calendar"
      onClick={() => open()}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } }}
      className={cn(
        'group cursor-pointer rounded-2xl border border-surface-border bg-white p-4 shadow-subtle transition-shadow hover:border-teal-300 hover:shadow-card focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-500',
        className,
      )}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-navy-900">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-600 text-white"><CalendarDays className="h-4 w-4" /></span>
          {anchor.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })}
        </h2>
        <span className="inline-flex items-center gap-1 text-xs font-semibold text-teal-700 group-hover:underline">Open calendar<ArrowRight className="h-3.5 w-3.5" /></span>
      </div>

      <div className="grid grid-cols-7 text-center text-[10px] font-semibold uppercase text-content-muted" aria-hidden="true">
        {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((d, i) => <span key={i} className="py-0.5">{d}</span>)}
      </div>
      <div className={cn('grid grid-cols-7 gap-y-0.5', loading && 'opacity-60')} aria-busy={loading}>
        {grid.slice(0, grid[35].getMonth() === anchor.getMonth() ? 42 : 35).map((day) => {
          const iso = toIso(day);
          const inMonth = day.getMonth() === anchor.getMonth();
          const here = sortForDay(eventsOn(events, iso));
          const working = feed?.meta.working_weekdays.includes(day.getDay()) ?? true;
          const kinds = [...new Set(here.map((e) => e.category))].slice(0, 3);
          return (
            <button
              key={iso}
              type="button"
              tabIndex={-1}
              onClick={(e) => { e.stopPropagation(); open(iso); }}
              aria-label={`${fromIso(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'long' })}${here.length ? `, ${here.length} item${here.length > 1 ? 's' : ''}` : ''}`}
              className={cn('flex h-9 flex-col items-center justify-center rounded-md text-xs hover:bg-teal-50', !inMonth && 'opacity-30', !working && inMonth && 'bg-surface-bg/70')}
            >
              <span className={cn('flex h-5 w-5 items-center justify-center rounded-full font-medium',
                iso === today ? 'bg-teal-600 font-bold text-white' : working ? 'text-navy-900' : 'text-content-muted')}>{day.getDate()}</span>
              <span className="mt-0.5 flex h-1.5 gap-0.5" aria-hidden="true">
                {kinds.map((k) => <span key={k} className="h-1.5 w-1.5 rounded-full" style={{ background: CATEGORY_META[k].color }} />)}
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-3 border-t border-surface-border pt-3">
        <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-content-muted">Coming up</h3>
        {error ? (
          <p className="text-xs text-content-secondary">The calendar is unavailable right now.</p>
        ) : loading && !feed ? (
          <p role="status" className="text-xs text-content-secondary">Loading…</p>
        ) : next.length === 0 ? (
          <p className="text-xs text-content-secondary">Nothing scheduled in the next few weeks.</p>
        ) : (
          <ul className="space-y-1.5">
            {next.map((e) => {
              const when = e.start <= today ? 'Now' : friendlyDate(e.start, today);
              return (
                <li key={e.id}>
                  <button type="button" tabIndex={-1} onClick={(ev) => { ev.stopPropagation(); open(e.start < today ? today : e.start); }}
                    className="flex w-full items-center gap-2 rounded-md px-1 py-0.5 text-left hover:bg-teal-50">
                    <span aria-hidden="true" className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: CATEGORY_META[e.category].color }} />
                    <span className="min-w-0 flex-1 truncate text-xs font-medium text-navy-900">{e.title}</span>
                    <span className="shrink-0 text-[11px] font-semibold text-content-secondary">{when}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        <ul className="mt-3 flex flex-wrap gap-x-3 gap-y-1" aria-label="Colour key">
          {(['holiday', 'exam', 'deadline', 'personal'] as const).map((c) => (
            <li key={c} className="flex items-center gap-1 text-[10px] text-content-muted">
              <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full" style={{ background: CATEGORY_META[c].color }} />{CATEGORY_META[c].label}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};

export default CalendarOverview;
