import { useEffect, useSyncExternalStore } from 'react';
import type { Plan } from '../../lib/planning/execution';
import { describeError, teacherPlanApi } from '../../lib/teacherPlanApi';

/**
 * Plans, schedule versions, proposals, execution and evidence are read from and written to the backend only.
 * A teacher loads their own plans; a Principal/Admin loads every teacher's plans in the school, each kept separate.
 * This module holds a read cache of the server's answer; nothing is persisted locally and nothing is reconciled.
 */
interface Entry { plans: Plan[]; error: string }
const NO_PLANS: Plan[] = [];
const entries = new Map<string, Entry>();
const inflight = new Map<string, Promise<Entry>>();
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());
const keyOf = (school: string, userId: string, role: string) => `${school}|${role}:${userId}`;

function load(key: string, role: string, userId: string): Promise<Entry> {
  const running = inflight.get(key);
  if (running) return running;
  const p = teacherPlanApi
    .listPlans(role === 'teacher' ? userId : undefined)
    .then((r): Entry => ({ plans: r.plans as Plan[], error: '' }))
    .catch((e): Entry => ({ plans: NO_PLANS, error: describeError(e).message }))
    .then((entry) => {
      entries.set(key, entry);
      inflight.delete(key);
      emit();
      return entry;
    });
  inflight.set(key, p);
  return p;
}

export function usePlans(school: string, userId: string, role: string): { plans: Plan[]; error: string; loaded: boolean } {
  const staff = ['teacher', 'principal', 'admin'].includes(role) && !!userId;
  const key = keyOf(school, userId, role);
  const snapshot = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => entries.get(key) ?? null,
    () => null,
  );
  if (staff && !snapshot && !inflight.has(key)) queueMicrotask(() => void load(key, role, userId));
  // Every mount re-checks the server in the background (the old answer stays on screen meanwhile), and so does returning to the tab,
  // so a reviewer sees a teacher's new draft or execution without a reload.
  useEffect(() => {
    if (!staff) return;
    const refresh = () => void load(key, role, userId);
    if (snapshotLoaded(key)) refresh();
    const onVisible = () => document.visibilityState === 'visible' && refresh();
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, staff]);
  return { plans: snapshot?.plans ?? NO_PLANS, error: snapshot?.error ?? '', loaded: !!snapshot };
}

const snapshotLoaded = (key: string) => entries.has(key);

export async function reloadPlans(school: string, userId: string, role: string): Promise<Plan[]> {
  const key = keyOf(school, userId, role);
  entries.delete(key);
  inflight.delete(key);
  return (await load(key, role, userId)).plans;
}
/** Test hook: primes the read cache so a screen can assert synchronously. The mount-time refresh still confirms it against the server. */
export function seedPlansCache(school: string, userId: string, role: string, plans: Plan[]) {
  entries.set(keyOf(school, userId, role), { plans, error: '' });
}
export function resetPlansStore() {
  entries.clear();
  inflight.clear();
  emit();
}

/* --------------------------------------------------------------- change -> server commands */

export type PlanCommand =
  | { kind: 'create'; teacherId: string; plan: Plan }
  | { kind: 'review-plan'; planId: string; decision: 'APPROVED' | 'REJECTED'; note: string }
  | { kind: 'execution'; planId: string; event: Plan['execution'][number] }
  | { kind: 'evidence'; planId: string; record: Plan['evidence'][number] }
  | { kind: 'proposal'; planId: string; proposal: Plan['proposals'][number] }
  | { kind: 'supersede'; planId: string }
  | { kind: 'review-proposal'; planId: string; proposalId: string; decision: 'APPROVED' | 'REJECTED'; note: string };

/**
 * Translates the result of the existing pure planning functions (createDraft, approveDraft, recordExecution, attachProposal,
 * approveRecovery ...) into the server commands that enact them. The server re-validates every command, builds approved
 * schedule versions itself, and decides who may do what; fields it derives (versions, SUPERSEDED statuses, losses) are ignored here.
 */
export function planCommands(before: Plan[], after: Plan[], actorId: string): PlanCommand[] {
  const old = new Map(before.map((p) => [p.id, p]));
  const out: PlanCommand[] = [];
  const reviews: PlanCommand[] = [];
  const tail: PlanCommand[] = [];
  for (const plan of [...after].reverse()) {
    const prev = old.get(plan.id);
    if (!prev) {
      out.push({ kind: 'create', teacherId: plan.teacherId ?? actorId, plan });
      continue;
    }
    if (prev.status === 'DRAFT' && (plan.status === 'APPROVED' || plan.status === 'REJECTED')) {
      reviews.push({ kind: 'review-plan', planId: plan.id, decision: plan.status, note: plan.review?.note ?? '' });
    }
    const knownExec = new Set(prev.execution.map((e) => e.id));
    for (const event of plan.execution) if (!knownExec.has(event.id)) out.push({ kind: 'execution', planId: plan.id, event });
    const knownEv = new Set(prev.evidence.map((e) => e.id));
    for (const record of plan.evidence) if (!knownEv.has(record.id)) out.push({ kind: 'evidence', planId: plan.id, record });
    const knownProp = new Map(prev.proposals.map((x) => [x.id, x]));
    const created = plan.proposals.filter((x) => !knownProp.has(x.id));
    for (const proposal of created) out.push({ kind: 'proposal', planId: plan.id, proposal });
    const supersededOnly = !created.length && plan.proposals.some((x) => knownProp.get(x.id)?.status === 'PENDING' && x.status === 'SUPERSEDED');
    if (supersededOnly) out.push({ kind: 'supersede', planId: plan.id });
    for (const x of plan.proposals) {
      const was = knownProp.get(x.id);
      if (was?.status === 'PENDING' && (x.status === 'APPROVED' || x.status === 'REJECTED')) {
        tail.push({ kind: 'review-proposal', planId: plan.id, proposalId: x.id, decision: x.status, note: x.review?.note ?? '' });
      }
    }
  }
  return [...out.filter((c) => c.kind === 'create'), ...reviews, ...out.filter((c) => c.kind !== 'create'), ...tail];
}

export async function runPlanCommand(c: PlanCommand): Promise<void> {
  switch (c.kind) {
    case 'create': {
      const { teacherId, plan } = c;
      await teacherPlanApi.createPlan(teacherId, {
        id: plan.id, grade: plan.grade, subject: plan.subject, datasetId: plan.datasetId, datasetLabel: plan.datasetLabel, datasetKind: plan.datasetKind,
        config: plan.config, estimates: plan.estimates, draft: plan.draft,
      });
      return;
    }
    case 'review-plan':
      await teacherPlanApi.reviewPlan(c.planId, { decision: c.decision, note: c.note });
      return;
    case 'execution':
      await teacherPlanApi.recordExecution(c.planId, c.event);
      return;
    case 'evidence':
      await teacherPlanApi.recordEvidence(c.planId, c.record);
      return;
    case 'proposal':
      await teacherPlanApi.createProposal(c.planId, c.proposal);
      return;
    case 'supersede':
      await teacherPlanApi.supersedeProposals(c.planId, 'No change remains after the latest records');
      return;
    case 'review-proposal':
      await teacherPlanApi.reviewProposal(c.planId, c.proposalId, { decision: c.decision, note: c.note });
  }
}

/** Runs the commands in order; stops at the first refusal and reports the server's message. */
export async function applyPlanCommands(commands: PlanCommand[]): Promise<{ ok: boolean; error?: string }> {
  for (const c of commands) {
    try {
      await runPlanCommand(c);
    } catch (e) {
      const d = describeError(e);
      const errors = (e as { data?: { detail?: { errors?: string[] } } })?.data?.detail?.errors;
      return { ok: false, error: errors?.length ? errors.join(' ') : d.message };
    }
  }
  return { ok: true };
}
