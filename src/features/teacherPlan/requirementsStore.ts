import { useEffect, useSyncExternalStore } from 'react';
import type { Classification, Classifications, Relationship } from '../../lib/planning/governance';
import type { LostPeriodRecord } from '../../lib/planning/losses';
import type { Plan } from '../../lib/planning/execution';
import { teacherPlanApi, type LostRow, type RelationshipItem, type RequirementItem } from '../../lib/teacherPlanApi';
import { nodeIdOf } from './useTeacherCoverage';

/**
 * One cached, shared read of a teacher's relational planning inputs: requirements, relationships and lost periods.
 * Every screen and the scheduling/recovery engine read these same rows; nothing here is written to the workspace document.
 */
const VALUE = { core: 'CORE', non_core: 'NON_CORE', mixed: 'MIXED' } as const;

/**
 * Requirement rows -> the Classifications shape the scheduling engine already consumes.
 * teacher/approved_import rows are the owner's saved requirement (APPROVED); a demo_default row keeps a PROPOSED status and
 * origin 'demo_default', so it can feed the engine but is never displayed or recorded as approved.
 */
export function classificationsFromRequirements(items: RequirementItem[], teacherId: string): Classifications {
  const out: Classifications = {};
  const by = { id: teacherId, name: '', role: 'teacher' } as Classification['proposedBy'];
  for (const r of items) {
    const id = nodeIdOf(r.topic_key);
    out[id] = {
      nodeId: id,
      status: r.origin === 'demo_default' ? 'DEMO_DEFAULT' : r.origin === 'teacher' ? 'TEACHER_CUSTOM' : 'APPROVED',
      origin: r.origin,
      value: VALUE[r.classification],
      corePeriods: r.core_periods,
      nonCorePeriods: r.non_core_periods,
      independentPeriods: r.independent_periods,
      teachingMode: r.teaching_mode,
      criteria: [],
      rationale: '',
      evidence: '',
      proposedBy: by,
      proposedAt: '',
      history: [],
    };
  }
  return out;
}

/** Active relationships -> the Relationship[] the engine consumes. A teacher's saved link is approved by its owner. */
export function relationshipsFromItems(items: RelationshipItem[], teacherId: string): Relationship[] {
  const by = { id: teacherId, name: '', role: 'teacher' } as Relationship['proposedBy'];
  return items
    .filter((i) => i.status === 'active')
    .map((i) => ({
      id: i.id,
      type: i.kind,
      fromNodeId: nodeIdOf(i.from_key),
      toNodeId: nodeIdOf(i.to_key),
      explanation: i.explanation ?? '',
      evidence: i.evidence ?? '',
      sharedPeriods: i.shared_periods,
      leadNodeId: i.lead_key ? nodeIdOf(i.lead_key) : null,
      status: 'APPROVED' as const,
      proposedBy: by,
      proposedAt: i.created_at ?? '',
    }));
}

/**
 * Lost-period rows -> the engine's LostPeriodRecord[] (active rows only, one record per date/batch/reason), for one class and subject.
 * Withdrawn rows are history, not losses, and never reach the engine.
 */
export function lossRecordsFor(rows: LostRow[], teacherId: string, grade: number, subject: string): LostPeriodRecord[] {
  const groups = new Map<string, LostRow[]>();
  for (const r of rows) {
    if (r.status !== 'active' || r.grade !== grade || r.subject !== subject) continue;
    const k = `${r.date}|${r.batch_id ?? r.id}|${r.reason}`;
    groups.set(k, [...(groups.get(k) ?? []), r]);
  }
  const by = { id: teacherId, name: '', role: 'teacher' } as LostPeriodRecord['recordedBy'];
  return [...groups.values()]
    .map((g) => {
      const periods = g.map((r) => r.period).sort((a, b) => a - b);
      return {
        id: `${g[0].batch_id ?? g[0].id}:${g[0].date}`,
        date: g[0].date,
        periodsLost: periods.length,
        periods,
        reason: g[0].reason,
        note: g[0].notes ?? '',
        recordedBy: { ...by, id: g[0].recorded_by },
        recordedAt: g[0].recorded_at ?? '',
        supersedes: null,
        ...(g[0].batch_id ? { batchId: g[0].batch_id } : {}),
      };
    })
    .sort((a, b) => a.date.localeCompare(b.date) || a.recordedAt.localeCompare(b.recordedAt));
}

/** A plan seen with its teacher's relational losses. The stored plan (workspace) is never written back with them. */
export const withLosses = (plan: Plan, rows: LostRow[], teacherId: string): Plan => ({ ...plan, losses: lossRecordsFor(rows, teacherId, plan.grade, plan.subject) });

interface Entry { data: Classifications; relationships: Relationship[]; lost: LostRow[]; loaded: boolean; error: string }
const EMPTY: Classifications = {};
const NO_RELATIONSHIPS: Relationship[] = [];
const NO_LOST: LostRow[] = [];
const entries = new Map<string, Entry>();
const listeners = new Set<() => void>();
const inflight = new Map<string, Promise<Entry>>();
let version = 0;
const emit = () => {
  version += 1;
  listeners.forEach((l) => l());
};
const keyOf = (school: string, teacher: string) => `${school}|${teacher}`;

const generation = new Map<string, number>();

function load(school: string, teacher: string): Promise<Entry> {
  const k = keyOf(school, teacher);
  const running = inflight.get(k);
  if (running) return running;
  const started = generation.get(k) ?? 0;
  const p = Promise.all([teacherPlanApi.requirements(teacher), teacherPlanApi.relationships(teacher), teacherPlanApi.lostAll(teacher)])
    .then(([r, rel, lost]): Entry => ({ data: classificationsFromRequirements(r.items, teacher), relationships: relationshipsFromItems(rel.items, teacher), lost: lost.items, loaded: true, error: '' }))
    .catch((e): Entry => ({ data: EMPTY, relationships: NO_RELATIONSHIPS, lost: NO_LOST, loaded: true, error: e instanceof Error ? e.message : 'Planning data could not be loaded.' }))
    .then(async (entry) => {
      if ((generation.get(k) ?? 0) !== started) {
        // Something was saved while this request was in flight: its answer may predate the save, so discard it and ask again.
        inflight.delete(k);
        return load(school, teacher);
      }
      entries.set(k, entry);
      inflight.delete(k);
      emit();
      return entry;
    });
  inflight.set(k, p);
  return p;
}

/**
 * Call after any save. Every cached teacher is re-read in the background; the previous rows stay on screen until the fresh ones
 * arrive (no empty flash), and any request already in flight is discarded because it may predate the save.
 */
export function invalidateRequirements() {
  for (const k of new Set([...entries.keys(), ...inflight.keys()])) {
    generation.set(k, (generation.get(k) ?? 0) + 1);
    const [school, teacher] = k.split('|');
    inflight.delete(k);
    void load(school, teacher);
  }
  emit();
}
export const resetRequirementsStore = () => {
  for (const k of new Set([...entries.keys(), ...inflight.keys()])) generation.set(k, (generation.get(k) ?? 0) + 1);
  entries.clear();
  inflight.clear();
  emit();
};

/** Drops the cache and waits for a fresh load, so a caller can act on the rows it has just written. */
export async function reloadTeacherData(school: string, teacher: string): Promise<{ lost: LostRow[]; error: string }> {
  const k = keyOf(school, teacher);
  generation.set(k, (generation.get(k) ?? 0) + 1);
  entries.delete(k);
  inflight.delete(k);
  const entry = await load(school, teacher);
  return { lost: entry.lost, error: entry.error };
}

/** Synchronous read for code running inside a workspace commit (the cache is already warm there). */
export const cachedLostRows = (school: string, teacher: string): LostRow[] => entries.get(keyOf(school, teacher))?.lost ?? NO_LOST;

function useEntry(school: string, teacher: string): Entry | null {
  const k = keyOf(school, teacher);
  const snapshot = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => entries.get(k) ?? null,
    () => null,
  );
  if (teacher && !snapshot && !inflight.has(k)) queueMicrotask(() => void load(school, teacher));
  // A mount re-checks the server in the background (cached rows stay on screen), so a reviewer never sees a stale teacher plan.
  useEffect(() => {
    if (teacher && entries.has(k)) void load(school, teacher);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [k]);
  return snapshot;
}

/** The engine's classification input for one teacher in one school. Empty (everything 'pending, protected') without a teacher. */
export function useTeacherClassifications(school: string, teacher: string): Classifications {
  return useEntry(school, teacher)?.data ?? EMPTY;
}
/** The engine's relationship input for the same teacher (same fetch, same cache entry). */
export function useTeacherRelationships(school: string, teacher: string): Relationship[] {
  return useEntry(school, teacher)?.relationships ?? NO_RELATIONSHIPS;
}
/** Every lost-period row (active and withdrawn) for the same teacher. */
export function useTeacherLostRows(school: string, teacher: string): LostRow[] {
  return useEntry(school, teacher)?.lost ?? NO_LOST;
}
/** Increments whenever any planning input is invalidated or loaded; lets independent cards refetch in step. */
export function useStoreVersion(): number {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => version,
    () => 0,
  );
}
