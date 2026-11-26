import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  CalendarDays, Check, ChevronLeft, ChevronRight, CircleAlert, ListTodo, Pencil, Plus, Trash2, Flag,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../../components/common/Button';
import { Modal } from '../../components/common/Modal';
import { cn } from '../../lib/utils';
import {
  CATEGORY_META, CATEGORY_ORDER, calendarApi, eventsOn, fromIso, friendlyDate, monthGrid, monthStart, rangeLabel, sortForDay,
  toIso, todayIso, useCalendarFeed,
  type CalendarCategory, type CalendarEvent, type CalendarMeta, type PersonalInput,
} from './calendarModel';

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const ISO = /^\d{4}-\d{2}-\d{2}$/;

function dayKind(iso: string, meta?: CalendarMeta): string {
  if (!meta) return '';
  const d = fromIso(iso);
  if (meta.session_start && iso < meta.session_start) return 'Before the academic session';
  if (meta.session_end && iso > meta.session_end) return 'After the academic session';
  return meta.working_weekdays.includes(d.getDay()) ? 'School day' : 'Non-working day';
}

const Dot: React.FC<{ category: CalendarCategory; className?: string }> = ({ category, className }) => (
  <span aria-hidden="true" className={cn('inline-block h-2.5 w-2.5 shrink-0 rounded-full', className)} style={{ background: CATEGORY_META[category].color }} />
);

export const CalendarPage: React.FC = () => {
  const { currentUser } = useAuth();
  const [params, setParams] = useSearchParams();
  const asked = params.get('date');
  const initial = asked && ISO.test(asked) ? asked : todayIso();

  const [anchor, setAnchor] = useState(() => monthStart(fromIso(initial)));
  const [selected, setSelected] = useState(initial);
  const [view, setView] = useState<'month' | 'agenda'>('month');
  const [hidden, setHidden] = useState<Set<CalendarCategory>>(new Set());
  const [form, setForm] = useState<{ event?: CalendarEvent; date: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [actionError, setActionError] = useState('');

  const grid = useMemo(() => monthGrid(anchor), [anchor]);
  const { feed, loading, error, reload } = useCalendarFeed(toIso(grid[0]), toIso(grid[41]));
  const today = todayIso();

  // Opening /calendar?date=... (from the dashboard) jumps to that day.
  useEffect(() => {
    if (asked && ISO.test(asked)) {
      setSelected(asked);
      setAnchor(monthStart(fromIso(asked)));
    }
  }, [asked]);

  const all = feed?.events ?? [];
  const visible = useMemo(() => all.filter((e) => !hidden.has(e.category)), [all, hidden]);
  const counts = useMemo(() => {
    const out: Partial<Record<CalendarCategory, number>> = {};
    all.forEach((e) => { out[e.category] = (out[e.category] ?? 0) + 1; });
    return out;
  }, [all]);
  const selectedEvents = sortForDay(eventsOn(visible, selected));
  const monthLabel = anchor.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' });
  const schools = feed?.meta.schools.map((s) => s.name).join(' · ');

  function go(delta: number) {
    const next = new Date(anchor.getFullYear(), anchor.getMonth() + delta, 1);
    setAnchor(next);
    setSelected(toIso(new Date(next.getFullYear(), next.getMonth(), Math.min(fromIso(selected).getDate(), 28))));
    if (params.has('date')) setParams({}, { replace: true });
  }
  function goToday() {
    setAnchor(monthStart(new Date()));
    setSelected(today);
    if (params.has('date')) setParams({}, { replace: true });
  }
  function toggle(c: CalendarCategory) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c); else next.add(c);
      return next;
    });
  }

  async function toggleDone(e: CalendarEvent) {
    if (!e.personal_id) return;
    setActionError('');
    try {
      await calendarApi.update(e.personal_id, { is_done: !e.done });
      reload();
    } catch (err: any) {
      setActionError(err?.message || 'Could not update this task.');
    }
  }
  async function remove(e: CalendarEvent) {
    if (!e.personal_id) return;
    setActionError('');
    try {
      await calendarApi.remove(e.personal_id);
      setConfirmDelete(null);
      reload();
    } catch (err: any) {
      setActionError(err?.message || 'Could not delete this item.');
    }
  }

  // Agenda: every visible item of the shown month, grouped by the day it starts (or the first day shown).
  const agenda = useMemo(() => {
    const first = toIso(anchor);
    const last = toIso(new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0));
    const groups = new Map<string, CalendarEvent[]>();
    visible.forEach((e) => {
      if (e.end < first || e.start > last) return;
      const key = e.start < first ? first : e.start;
      groups.set(key, [...(groups.get(key) ?? []), e]);
    });
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([date, items]) => ({ date, items: sortForDay(items) }));
  }, [visible, anchor]);

  return (
    // bottom padding keeps the floating Ask LumenEIOS button from covering the last card
    <div className="space-y-5 pb-20">
      {/* Header */}
      <div className="flex flex-col gap-4 rounded-2xl border border-surface-border bg-gradient-to-r from-teal-50 to-white p-5 shadow-subtle md:flex-row md:items-center md:justify-between">
        <div className="flex items-start gap-3">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-teal-600 text-white"><CalendarDays className="h-6 w-6" /></span>
          <div>
            <h2 className="text-xl font-bold tracking-tight text-navy-900">Calendar</h2>
            <p className="mt-0.5 text-xs text-content-secondary">
              Holidays, exams, deadlines and your own tasks{feed?.meta.year ? ` · Session ${feed.meta.year}` : ''}{schools ? ` · ${schools}` : ''}
            </p>
          </div>
        </div>
        <Button variant="teal" icon={<Plus className="h-4 w-4" />} onClick={() => setForm({ date: selected })}>Add task or deadline</Button>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        {/* Main column */}
        <section aria-label="Calendar" className="rounded-2xl border border-surface-border bg-white shadow-subtle">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-border px-4 py-3">
            <div className="flex items-center gap-1.5">
              <button type="button" onClick={() => go(-1)} aria-label="Previous month" className="rounded-lg border border-surface-border p-1.5 text-content-secondary hover:border-teal-400 hover:text-navy-900"><ChevronLeft className="h-4 w-4" /></button>
              <button type="button" onClick={() => go(1)} aria-label="Next month" className="rounded-lg border border-surface-border p-1.5 text-content-secondary hover:border-teal-400 hover:text-navy-900"><ChevronRight className="h-4 w-4" /></button>
              <h2 className="ml-2 min-w-[9.5rem] text-base font-semibold text-navy-900" aria-live="polite">{monthLabel}</h2>
              <button type="button" onClick={goToday} className="ml-1 rounded-lg border border-surface-border px-2.5 py-1 text-xs font-semibold text-navy-900 hover:border-teal-400">Today</button>
            </div>
            <div role="tablist" aria-label="Calendar view" className="inline-flex rounded-lg border border-surface-border p-0.5 text-xs font-semibold">
              {(['month', 'agenda'] as const).map((v) => (
                <button key={v} type="button" role="tab" aria-selected={view === v} onClick={() => setView(v)}
                  className={cn('rounded-md px-3 py-1 capitalize', view === v ? 'bg-teal-600 text-white' : 'text-content-secondary hover:text-navy-900')}>{v}</button>
              ))}
            </div>
          </div>

          {error && (
            <div role="alert" className="m-4 flex items-center justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              <span className="flex items-center gap-2"><CircleAlert className="h-4 w-4" />{error}</span>
              <button type="button" onClick={reload} className="font-semibold underline">Retry</button>
            </div>
          )}

          {view === 'month' ? (
            <div className={cn('p-2 sm:p-3', loading && 'opacity-70')} aria-busy={loading}>
              <div className="grid grid-cols-7 text-center text-[11px] font-semibold uppercase tracking-wide text-content-muted">
                {WEEKDAYS.map((d) => <div key={d} className="py-1.5">{d}</div>)}
              </div>
              <div className="grid grid-cols-7 overflow-hidden rounded-xl border border-surface-border">
                {grid.map((day, index) => {
                  const iso = toIso(day);
                  const inMonth = day.getMonth() === anchor.getMonth();
                  const events = sortForDay(eventsOn(visible, iso));
                  const working = feed?.meta.working_weekdays.includes(day.getDay()) ?? true;
                  const isSelected = iso === selected;
                  const col = index % 7;
                  const label = `${day.toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}, ${
                    events.length ? `${events.length} item${events.length > 1 ? 's' : ''}` : 'nothing scheduled'}`;
                  return (
                    <button
                      key={iso}
                      type="button"
                      onClick={() => { setSelected(iso); if (!inMonth) setAnchor(monthStart(day)); }}
                      aria-label={label}
                      aria-pressed={isSelected}
                      aria-current={iso === today ? 'date' : undefined}
                      className={cn(
                        'relative flex min-h-[64px] flex-col items-stretch gap-0.5 border-b border-r border-surface-border p-1.5 text-left transition-colors sm:min-h-[104px]',
                        col === 6 && 'border-r-0',
                        index >= 35 && 'border-b-0',
                        !working && 'bg-surface-bg/70',
                        !inMonth && 'opacity-45',
                        isSelected ? 'z-10 ring-2 ring-inset ring-teal-500' : 'hover:bg-teal-50/60',
                      )}
                    >
                      <span className={cn(
                        'inline-flex h-6 w-6 items-center justify-center self-start rounded-full text-xs font-semibold',
                        iso === today ? 'bg-teal-600 text-white' : working ? 'text-navy-900' : 'text-content-muted',
                      )}>{day.getDate()}</span>
                      {/* wide screens: labelled chips */}
                      <span className="hidden flex-col gap-0.5 sm:flex">
                        {events.slice(0, 3).map((e) => {
                          const isStart = e.start === iso;
                          const isEnd = e.end === iso;
                          const showLabel = isStart || col === 0;
                          return (
                            <span key={e.id} title={e.title}
                              className={cn(
                                'block h-[18px] truncate px-1.5 text-[11px] font-medium leading-[18px] text-white',
                                isStart || col === 0 ? 'rounded-l' : '-ml-1.5 rounded-l-none',
                                isEnd || col === 6 ? 'rounded-r' : '-mr-1.5 rounded-r-none',
                                e.category === 'personal' && e.done && 'line-through opacity-60',
                              )}
                              style={{ background: CATEGORY_META[e.category].color }}>
                              {showLabel ? e.title : ' '}
                            </span>
                          );
                        })}
                        {events.length > 3 && <span className="px-1 text-[11px] font-semibold text-content-secondary">+{events.length - 3} more</span>}
                      </span>
                      {/* phones: just coloured dots */}
                      <span className="mt-auto flex flex-wrap gap-0.5 sm:hidden" aria-hidden="true">
                        {events.slice(0, 4).map((e) => <Dot key={e.id} category={e.category} className="h-1.5 w-1.5" />)}
                      </span>
                    </button>
                  );
                })}
              </div>
              <p className="mt-2 px-1 text-[11px] text-content-muted">Shaded days are non-working days from Academic Config. Click a day for details.</p>
            </div>
          ) : (
            <div className="divide-y divide-surface-border" aria-busy={loading}>
              {agenda.length === 0 && !loading && <p className="p-6 text-sm text-content-secondary">Nothing scheduled in {monthLabel}{hidden.size ? ' with the current filters' : ''}.</p>}
              {agenda.map(({ date, items }) => (
                <div key={date} className="flex gap-4 px-4 py-3">
                  <button type="button" onClick={() => { setSelected(date); setView('month'); }} className="w-16 shrink-0 text-left">
                    <span className="block text-2xl font-bold leading-none text-navy-900">{fromIso(date).getDate()}</span>
                    <span className="text-[11px] font-semibold uppercase text-content-muted">{fromIso(date).toLocaleDateString('en-IN', { weekday: 'short' })}</span>
                  </button>
                  <ul className="min-w-0 flex-1 space-y-1.5">
                    {items.map((e) => (
                      <li key={e.id} className="flex items-start gap-2 rounded-lg border border-surface-border px-3 py-2">
                        <Dot category={e.category} className="mt-1.5" />
                        <div className="min-w-0">
                          <p className={cn('text-sm font-semibold text-navy-900', e.done && 'line-through opacity-60')}>{e.title}</p>
                          <p className="text-xs text-content-secondary">{CATEGORY_META[e.category].label} · {rangeLabel(e)}{e.detail && e.category !== 'personal' ? ` · ${e.detail}` : ''}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Side column */}
        <aside className="space-y-5">
          <section aria-label="Selected day" className="rounded-2xl border border-surface-border bg-white p-4 shadow-subtle">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold text-navy-900">{friendlyDate(selected, today)}</h2>
                <p className="text-xs text-content-secondary">
                  {fromIso(selected).toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
                  {dayKind(selected, feed?.meta) ? ` · ${dayKind(selected, feed?.meta)}` : ''}
                </p>
              </div>
              <Button size="sm" variant="outline" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setForm({ date: selected })}>Add</Button>
            </div>
            {actionError && <p role="alert" className="mt-2 text-xs text-rose-700">{actionError}</p>}
            {selectedEvents.length === 0 ? (
              <p className="mt-4 rounded-lg bg-surface-bg px-3 py-4 text-center text-xs text-content-secondary">Nothing scheduled. Use Add to keep a task or deadline for this day.</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {selectedEvents.map((e) => (
                  <li key={e.id} className="overflow-hidden rounded-lg border border-surface-border">
                    <div className="flex">
                      <span aria-hidden="true" className="w-1.5 shrink-0" style={{ background: CATEGORY_META[e.category].color }} />
                      <div className="min-w-0 flex-1 px-3 py-2">
                        <p className={cn('break-words text-sm font-semibold text-navy-900', e.done && 'line-through opacity-60')}>{e.title}</p>
                        <p className="text-xs text-content-secondary">
                          {e.category === 'personal' ? (e.personal_kind === 'DEADLINE' ? 'My deadline' : 'My task') : CATEGORY_META[e.category].label}
                          {' · '}{rangeLabel(e)}{e.sender_name ? ` · from ${e.sender_name}` : ''}
                        </p>
                        {e.detail && <p className="mt-0.5 break-words text-xs text-content-muted">{e.detail}</p>}
                        {e.editable && (
                          <div className="mt-2 flex flex-wrap items-center gap-1.5">
                            <button type="button" onClick={() => toggleDone(e)} className="inline-flex items-center gap-1 rounded-md border border-surface-border px-2 py-1 text-[11px] font-semibold text-navy-900 hover:border-teal-400">
                              <Check className="h-3 w-3" />{e.done ? 'Mark not done' : 'Mark done'}
                            </button>
                            <button type="button" onClick={() => setForm({ event: e, date: e.start })} aria-label={`Edit ${e.title}`} className="inline-flex items-center gap-1 rounded-md border border-surface-border px-2 py-1 text-[11px] font-semibold text-navy-900 hover:border-teal-400"><Pencil className="h-3 w-3" />Edit</button>
                            {confirmDelete === e.id ? (
                              <span className="inline-flex items-center gap-1 text-[11px]">
                                <button type="button" onClick={() => remove(e)} className="rounded-md bg-rose-600 px-2 py-1 font-semibold text-white">Delete</button>
                                <button type="button" onClick={() => setConfirmDelete(null)} className="rounded-md border border-surface-border px-2 py-1 font-semibold">Keep</button>
                              </span>
                            ) : (
                              <button type="button" onClick={() => setConfirmDelete(e.id)} aria-label={`Delete ${e.title}`} className="inline-flex items-center gap-1 rounded-md border border-surface-border px-2 py-1 text-[11px] font-semibold text-rose-700 hover:border-rose-400"><Trash2 className="h-3 w-3" />Delete</button>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-label="Legend and filters" className="rounded-2xl border border-surface-border bg-white p-4 shadow-subtle">
            <h2 className="text-sm font-semibold text-navy-900">What you are seeing</h2>
            <p className="mb-3 text-xs text-content-secondary">Click a colour to show or hide it.</p>
            <ul className="space-y-1">
              {CATEGORY_ORDER.map((c) => {
                const off = hidden.has(c);
                return (
                  <li key={c}>
                    <button type="button" onClick={() => toggle(c)} aria-pressed={!off}
                      className={cn('flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-xs hover:bg-surface-bg', off && 'opacity-50')}>
                      <span aria-hidden="true" className="h-3 w-3 shrink-0 rounded-[4px]" style={{ background: off ? 'transparent' : CATEGORY_META[c].color, border: `2px solid ${CATEGORY_META[c].color}` }} />
                      <span className="min-w-0 flex-1">
                        <span className="block font-semibold text-navy-900">{CATEGORY_META[c].label}</span>
                        <span className="block text-[11px] text-content-muted">{CATEGORY_META[c].hint}</span>
                      </span>
                      <span className="rounded-full bg-surface-bg px-1.5 text-[11px] font-semibold text-content-secondary">{counts[c] ?? 0}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        </aside>
      </div>

      {form && (
        <PersonalForm
          key={form.event?.id ?? `new-${form.date}`}
          event={form.event}
          date={form.date}
          role={currentUser?.role}
          onClose={() => setForm(null)}
          onSaved={(saved) => { setForm(null); setSelected(saved.start); setAnchor(monthStart(fromIso(saved.start))); reload(); }}
        />
      )}
    </div>
  );
};

const PersonalForm: React.FC<{
  event?: CalendarEvent;
  date: string;
  role?: string;
  onClose: () => void;
  onSaved: (saved: CalendarEvent) => void;
}> = ({ event, date, onClose, onSaved }) => {
  const [title, setTitle] = useState(event?.title ?? '');
  const [kind, setKind] = useState<'TASK' | 'DEADLINE'>(event?.personal_kind ?? 'TASK');
  const [start, setStart] = useState(event?.start ?? date);
  const [end, setEnd] = useState(event && event.end !== event.start ? event.end : '');
  const [notes, setNotes] = useState(event?.detail ?? '');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const cleanTitle = title.trim();
    if (!cleanTitle) return setError('Enter a title.');
    if (!ISO.test(start)) return setError('Choose a date.');
    if (end && end < start) return setError('The end date is before the start date.');
    const body: PersonalInput = { title: cleanTitle, kind, start_date: start, end_date: end || null, notes: notes.trim() || null };
    setSaving(true);
    setError('');
    try {
      const saved = event?.personal_id ? await calendarApi.update(event.personal_id, body) : await calendarApi.add(body);
      onSaved(saved);
    } catch (err: any) {
      setError(err?.message || 'Could not save. Try again.');
      setSaving(false);
    }
  }

  const field = 'w-full rounded-lg border border-surface-border bg-white px-3 py-2 text-sm text-navy-900 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-200';
  return (
    <Modal
      isOpen
      onClose={onClose}
      title={event ? 'Edit my item' : 'Add a task or deadline'}
      subtitle="Only you can see what you add here."
      maxWidth="md"
      footer={(
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} type="button">Cancel</Button>
          <Button variant="teal" type="submit" form="calendar-personal-form" loading={saving}>{event ? 'Save changes' : 'Add to calendar'}</Button>
        </div>
      )}
    >
      <form id="calendar-personal-form" onSubmit={submit} className="space-y-4" noValidate>
        <div>
          <label htmlFor="cal-title" className="mb-1 block text-xs font-semibold text-navy-900">Title</label>
          <input id="cal-title" autoFocus maxLength={120} value={title} onChange={(e) => setTitle(e.target.value)} className={field} placeholder="e.g. Revise fractions, Submit science project" />
        </div>
        <fieldset>
          <legend className="mb-1 text-xs font-semibold text-navy-900">Type</legend>
          <div className="grid grid-cols-2 gap-2">
            {([['TASK', 'Task', ListTodo], ['DEADLINE', 'Deadline', Flag]] as const).map(([value, label, Icon]) => (
              <label key={value} className={cn('flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm font-semibold',
                kind === value ? 'border-teal-500 bg-teal-50 text-teal-800' : 'border-surface-border text-content-secondary')}>
                <input type="radio" name="kind" value={value} checked={kind === value} onChange={() => setKind(value)} className="sr-only" />
                <Icon className="h-4 w-4" />{label}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="cal-start" className="mb-1 block text-xs font-semibold text-navy-900">{kind === 'DEADLINE' ? 'Due date' : 'Date'}</label>
            <input id="cal-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} className={field} />
          </div>
          <div>
            <label htmlFor="cal-end" className="mb-1 block text-xs font-semibold text-navy-900">Until <span className="font-normal text-content-muted">(optional)</span></label>
            <input id="cal-end" type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} className={field} />
          </div>
        </div>
        <div>
          <label htmlFor="cal-notes" className="mb-1 block text-xs font-semibold text-navy-900">Notes <span className="font-normal text-content-muted">(optional)</span></label>
          <textarea id="cal-notes" rows={3} maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)} className={field} />
        </div>
        {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
      </form>
    </Modal>
  );
};

export default CalendarPage;
