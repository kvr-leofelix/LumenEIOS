/**
 * Course Curriculum coverage: exactly three statuses per teachable topic, one authoritative record per topic.
 *
 * Sources of change (never silent, always in the record's append-only history):
 *   MANUAL    - an authorised teacher/admin sets the status explicitly.
 *   EXECUTION - recording classroom execution in Daily Curriculum moves the topic when its required classroom teaching is
 *               genuinely complete (Done) or under way (In progress). Scheduling, opening a topic, homework, lost periods,
 *               recovery proposals and approved schedule versions never change coverage.
 */
import type { Actor } from './governance';
import { lessonProgress, currentVersion, type Plan } from './execution';
import type { SyllabusNode } from './syllabus';

export type CoverageStatus = 'DONE' | 'NOT_DONE' | 'IN_PROGRESS';
export const COVERAGE_STATUSES: CoverageStatus[] = ['DONE', 'NOT_DONE', 'IN_PROGRESS'];
export const COVERAGE_LABEL: Record<CoverageStatus, string> = { DONE: 'Done', NOT_DONE: 'Not done', IN_PROGRESS: 'In progress' };
export const COVERAGE_COLOR: Record<CoverageStatus, string> = { DONE: '#16A34A', NOT_DONE: '#9CA3AF', IN_PROGRESS: '#F59E0B' };

export type CoverageSource = 'MANUAL' | 'EXECUTION';

export interface CoverageEntry {
  at: string;
  by: Actor;
  status: CoverageStatus;
  source: CoverageSource;
  note?: string;
}

export interface CoverageRecord {
  status: CoverageStatus;
  source: CoverageSource;
  updatedAt: string;
  updatedBy: Actor;
  history: CoverageEntry[];
}

export type Coverage = Record<string, CoverageRecord>;

export const statusOf = (cov: Coverage | undefined, nodeId: string): CoverageStatus => cov?.[nodeId]?.status ?? 'NOT_DONE';

/** Returns the same object when nothing changes. */
export function setCoverage(cov: Coverage | undefined, nodeId: string, status: CoverageStatus, actor: Actor, source: CoverageSource, at = new Date().toISOString(), note?: string): Coverage {
  const base = cov ?? {};
  if (!COVERAGE_STATUSES.includes(status)) throw new Error('Unknown coverage status.');
  const current = base[nodeId];
  if (current && current.status === status) return base;
  if (!current && status === 'NOT_DONE' && source === 'EXECUTION') return base;
  const entry: CoverageEntry = { at, by: actor, status, source, ...(note ? { note } : {}) };
  return { ...base, [nodeId]: { status, source, updatedAt: at, updatedBy: actor, history: [...(current?.history ?? []), entry] } };
}

export interface CoverageSummary {
  total: number;
  done: number;
  inProgress: number;
  notDone: number;
  /** Done / total x 100, rounded to one decimal; 0 for an empty syllabus. In-progress topics do not count as done. */
  percent: number;
}

export function summarizeStatuses(statuses: CoverageStatus[]): CoverageSummary {
  const total = statuses.length;
  const done = statuses.filter((s) => s === 'DONE').length;
  const inProgress = statuses.filter((s) => s === 'IN_PROGRESS').length;
  return { total, done, inProgress, notDone: total - done - inProgress, percent: total ? Math.round((done / total) * 1000) / 10 : 0 };
}

export function summarizeCoverage(units: SyllabusNode[], cov: Coverage | undefined): CoverageSummary {
  return summarizeStatuses(units.map((u) => statusOf(cov, u.id)));
}

/** Calculated, never edited: all Done = Done; all Not done = Not done; any mixture = In progress; none = null (empty). */
export function chapterStatus(statuses: CoverageStatus[]): CoverageStatus | null {
  if (!statuses.length) return null;
  if (statuses.every((s) => s === 'DONE')) return 'DONE';
  if (statuses.every((s) => s === 'NOT_DONE')) return 'NOT_DONE';
  return 'IN_PROGRESS';
}

export interface ExecutionEvidence {
  complete: boolean;
  taughtPeriods: number;
}

/** What classroom execution records currently say about each topic, over every approved plan's current schedule. */
export function executionEvidence(plans: Plan[]): Record<string, ExecutionEvidence> {
  const out: Record<string, ExecutionEvidence> = {};
  for (const plan of plans) {
    if (plan.status !== 'APPROVED') continue;
    const version = currentVersion(plan);
    if (!version) continue;
    for (const lesson of version.lessons) {
      const pr = lessonProgress(plan, lesson);
      const prev = out[lesson.nodeId];
      out[lesson.nodeId] = { complete: pr.complete || !!prev?.complete, taughtPeriods: Math.max(pr.taughtPeriods, prev?.taughtPeriods ?? 0) };
    }
  }
  return out;
}

const RANK: Record<CoverageStatus, number> = { NOT_DONE: 0, IN_PROGRESS: 1, DONE: 2 };

/**
 * Coverage after classroom execution was recorded for one topic. Uses the plan's own completion rule: a topic with several
 * periods is Done only when its required classroom teaching is complete, not after the first period.
 * An execution-derived record follows the evidence (including a later correction); a manual record is only ever raised by
 * newer classroom evidence, never lowered by it.
 */
export function coverageAfterExecution(cov: Coverage | undefined, plan: Plan, nodeId: string, actor: Actor, at = new Date().toISOString()): Coverage {
  const version = currentVersion(plan);
  const lesson = version?.lessons.find((l) => l.nodeId === nodeId);
  if (!lesson) return cov ?? {};
  const pr = lessonProgress(plan, lesson);
  const desired: CoverageStatus = pr.complete ? 'DONE' : pr.taughtPeriods > 0 ? 'IN_PROGRESS' : 'NOT_DONE';
  const current = cov?.[nodeId];
  const note = pr.complete
    ? 'Classroom teaching recorded as complete'
    : desired === 'IN_PROGRESS'
      ? `Classroom teaching under way (${pr.taughtPeriods} of ${pr.classroomTotal} period(s))`
      : 'Classroom record corrected';
  if (!current || current.source === 'EXECUTION') return setCoverage(cov, nodeId, desired, actor, 'EXECUTION', at, note);
  if (RANK[desired] > RANK[current.status]) return setCoverage(cov, nodeId, desired, actor, 'EXECUTION', at, note);
  return cov ?? {};
}
