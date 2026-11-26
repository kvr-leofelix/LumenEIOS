import { useCallback, useEffect, useState } from 'react';
import { apiRequest } from '../../lib/apiClient';
import { useAuth } from '../../context/AuthContext';

export type CalendarCategory = 'holiday' | 'vacation' | 'exam' | 'event' | 'session' | 'deadline' | 'lost' | 'personal' | 'announcement';

export interface CalendarEvent {
  id: string;
  category: CalendarCategory;
  title: string;
  /** ISO dates (YYYY-MM-DD), inclusive. */
  start: string;
  end: string;
  source: 'school' | 'assessment' | 'homework' | 'personal' | 'announcement';
  announcement_id?: string;
  sender_name?: string;
  detail: string;
  editable: boolean;
  personal_id?: string;
  personal_kind?: 'TASK' | 'DEADLINE';
  done?: boolean;
  status?: string;
  school_id?: string;
}

export interface CalendarMeta {
  schools: { id: string; name: string }[];
  session_start: string | null;
  session_end: string | null;
  /** 0 = Sunday ... 6 = Saturday, as set in Academic Config. */
  working_weekdays: number[];
  year?: string;
}

export interface CalendarFeed {
  start: string;
  end: string;
  events: CalendarEvent[];
  meta: CalendarMeta;
}

export interface PersonalInput {
  title: string;
  kind: 'TASK' | 'DEADLINE';
  start_date: string;
  end_date?: string | null;
  notes?: string | null;
}

/**
 * One solid colour per kind of item. White text on each fill is at least 4.5:1, which keeps chips readable in the
 * light and dark themes alike.
 */
export const CATEGORY_META: Record<CalendarCategory, { label: string; color: string; hint: string }> = {
  holiday: { label: 'Holiday', color: '#BE123C', hint: 'School closed' },
  vacation: { label: 'Vacation', color: '#0E7490', hint: 'Term break' },
  exam: { label: 'Exams & tests', color: '#6D28D9', hint: 'Exam periods and class assessments' },
  event: { label: 'School event', color: '#1D4ED8', hint: 'Sports day, functions, meetings' },
  deadline: { label: 'Deadlines', color: '#B45309', hint: 'Homework and assignment due dates' },
  session: { label: 'Session', color: '#0F766E', hint: 'Academic session start and end' },
  lost: { label: 'Lost teaching day', color: '#475569', hint: 'Teaching disrupted' },
  personal: { label: 'My tasks', color: '#047857', hint: 'Your own tasks and deadlines' },
  // Fixed on purpose: announcements always use this colour (magenta/fuchsia is used by no other kind) and it is not user-configurable.
  announcement: { label: 'Announcement event', color: '#A21CAF', hint: 'An event announced by the principal or a teacher' },
};
export const CATEGORY_ORDER: CalendarCategory[] = ['holiday', 'vacation', 'exam', 'deadline', 'event', 'announcement', 'session', 'lost', 'personal'];

// ---- dates (always local calendar days; never parsed through UTC) ---------------------------------------------------
export function toIso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
export function fromIso(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}
export function addDays(d: Date, n: number): Date {
  const next = new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
  return next;
}
export function todayIso(): string {
  return toIso(new Date());
}
export function monthStart(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

/** The 6-week, Monday-first grid that contains the month of `anchor`. */
export function monthGrid(anchor: Date): Date[] {
  const first = monthStart(anchor);
  const offset = (first.getDay() + 6) % 7; // Monday = 0
  const gridStart = addDays(first, -offset);
  return Array.from({ length: 42 }, (_, i) => addDays(gridStart, i));
}

export function eventsOn(events: CalendarEvent[], iso: string): CalendarEvent[] {
  return events.filter((e) => e.start <= iso && e.end >= iso);
}

const PRIORITY: Record<CalendarCategory, number> = { exam: 0, deadline: 1, announcement: 2, holiday: 3, vacation: 4, event: 5, personal: 6, session: 7, lost: 8 };
export function sortForDay(events: CalendarEvent[]): CalendarEvent[] {
  return [...events].sort((a, b) => PRIORITY[a.category] - PRIORITY[b.category] || a.title.localeCompare(b.title));
}

export function friendlyDate(iso: string, today = todayIso()): string {
  if (iso === today) return 'Today';
  if (iso === toIso(addDays(fromIso(today), 1))) return 'Tomorrow';
  return fromIso(iso).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });
}

export function rangeLabel(e: CalendarEvent): string {
  const fmt = (iso: string) => fromIso(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
  return e.start === e.end ? fmt(e.start) : `${fmt(e.start)} – ${fmt(e.end)}`;
}

const laterOf = (x: string, y: string) => (x > y ? x : y);

/** Upcoming first: items still running today or starting later, nearest first. */
export function upcoming(events: CalendarEvent[], today = todayIso(), limit = 6): CalendarEvent[] {
  return events
    .filter((e) => e.end >= today && e.category !== 'lost' && !(e.category === 'personal' && e.done))
    .sort((a, b) => laterOf(a.start, today).localeCompare(laterOf(b.start, today)) || PRIORITY[a.category] - PRIORITY[b.category])
    .slice(0, limit);
}

// ---- API ------------------------------------------------------------------------------------------------------------
export const calendarApi = {
  events: (start: string, end: string) => apiRequest<CalendarFeed>(`/calendar/events?start=${start}&end=${end}`),
  add: (body: PersonalInput) => apiRequest<CalendarEvent>('/calendar/personal', { method: 'POST', body: JSON.stringify(body) }),
  update: (id: string, body: Partial<PersonalInput> & { is_done?: boolean }) =>
    apiRequest<CalendarEvent>(`/calendar/personal/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  remove: (id: string) => apiRequest<void>(`/calendar/personal/${id}`, { method: 'DELETE' }),
};

export function useCalendarFeed(start: string, end: string) {
  // Reload when the account or the selected campus changes (management can switch campus on this page).
  const { currentUser, currentSchoolId } = useAuth();
  const [feed, setFeed] = useState<CalendarFeed | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    calendarApi
      .events(start, end)
      .then((data) => {
        if (!active) return;
        setFeed(data);
        setError('');
      })
      .catch((err: any) => {
        if (active) setError(err?.message || 'Could not load the calendar.');
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [start, end, nonce, currentUser?.id, currentSchoolId]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { feed, loading, error, reload };
}
