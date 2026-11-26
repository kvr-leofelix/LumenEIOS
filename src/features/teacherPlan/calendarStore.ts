import { useEffect, useSyncExternalStore } from 'react';
import type { AcademicConfig } from '../../lib/planning/calendar';
import type { ConfigRecord } from '../../lib/planning/store';
import { teacherPlanApi, type CalendarVersion } from '../../lib/teacherPlanApi';

/**
 * The school's academic calendar, read from the backend's versioned `school_plan_calendars`. Version 0 means the school has no saved
 * calendar yet (the screens then show the workspace's historical/default configuration until the first version is saved or imported).
 * Nothing is stored in the browser; this is a read cache that refreshes on mount and after every save.
 */
interface Entry { version: number; config: AcademicConfig | null; versions: CalendarVersion[]; error: string }
const entries = new Map<string, Entry>();
const inflight = new Map<string, Promise<Entry>>();
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

function load(school: string): Promise<Entry> {
  const running = inflight.get(school);
  if (running) return running;
  const p = Promise.all([teacherPlanApi.calendar(), teacherPlanApi.calendarHistory()])
    .then(([cur, hist]): Entry => ({ version: cur.version, config: cur.version >= 1 ? (cur.config as unknown as AcademicConfig) : null, versions: hist.versions, error: '' }))
    .catch((e): Entry => ({ version: 0, config: null, versions: [], error: e instanceof Error ? e.message : 'The calendar could not be loaded.' }))
    .then((entry) => {
      entries.set(school, entry);
      inflight.delete(school);
      emit();
      return entry;
    });
  inflight.set(school, p);
  return p;
}

export const reloadCalendar = (school: string) => {
  inflight.delete(school);
  return load(school);
};
export const resetCalendarStore = () => {
  entries.clear();
  inflight.clear();
  emit();
};
/** Test hook: primes the cache so a screen can assert synchronously; the mount refresh still confirms it against the server. */
export const seedCalendarCache = (school: string, version: number, config: AcademicConfig | null, versions: CalendarVersion[] = []) => {
  entries.set(school, { version, config, versions, error: '' });
};

export function useSchoolCalendar(school: string, enabled: boolean): Entry & { loaded: boolean } {
  const snapshot = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => entries.get(school) ?? null,
    () => null,
  );
  if (enabled && !snapshot && !inflight.has(school)) queueMicrotask(() => void load(school));
  useEffect(() => {
    if (!enabled) return;
    if (entries.has(school)) void load(school);
    // Returning to the tab re-checks the server, so a reviewer sees another reviewer's newer calendar version.
    const onVisible = () => document.visibilityState === 'visible' && void load(school);
    const onFocus = () => void load(school);
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onFocus);
    return () => {
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onFocus);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [school, enabled]);
  return { version: snapshot?.version ?? 0, config: snapshot?.config ?? null, versions: snapshot?.versions ?? [], error: snapshot?.error ?? '', loaded: !!snapshot };
}

/** The relational versions as the save-history list the Academic Configuration screen already renders. */
export const historyRecords = (versions: CalendarVersion[]): ConfigRecord[] =>
  versions.map((v) => ({ config: v.config as unknown as AcademicConfig, savedBy: { id: v.created_by, name: v.created_by_name ?? v.created_by, role: v.created_by_role ?? 'system' } as ConfigRecord['savedBy'], savedAt: v.created_at ?? '' }));
