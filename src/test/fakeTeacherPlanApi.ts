/**
 * Stateful in-memory stand-in for the relational teacher-plan API, so UI tests exercise the real hooks and screens.
 * Coverage lives only here (per teacher), exactly like the backend: it is never mirrored into the workspace document.
 */
import type { Coverage, LostRow, RelationshipItem, RequirementItem, TeacherPlan } from '../lib/teacherPlanApi';

interface Cell { status: Coverage; source: 'MANUAL' | 'EXECUTION' }
export const fakeStore = {
  coverage: new Map<string, Map<string, Cell>>(),
  classes: new Map<string, Map<string, { classification: string; core: number; non: number }>>(),
  requirements: new Map<string, RequirementItem[]>(),
  relationships: new Map<string, RelationshipItem[]>(),
  calendar: [] as { version: number; config: any; reason: string; created_by: string; created_by_name: string; created_by_role: string; created_at: string; capacity: Record<string, never> }[],
  calendarCalls: [] as { op: string; body?: unknown }[],
  calendarFailures: [] as number[],
  logItems: [] as any[],
  plans: new Map<string, any>(),
  /** Synchronous view of what listPlans would return for a signed-in user. */
  plansFor(role: string, id: string): any[] {
    const all = [...this.plans.values()];
    return JSON.parse(JSON.stringify(role === 'teacher' ? all.filter((p) => p.teacherId === id) : all));
  },
  planCalls: [] as { op: string; planId?: string; body?: unknown }[],
  lost: new Map<string, LostRow[]>(),
  lostCalls: [] as { op: string; teacher: string; body?: unknown }[],
  relationshipCalls: [] as { op: string; teacher: string; body?: unknown }[],
  events: [] as { teacher: string; topic_key: string; from: Coverage; to: Coverage; source: string }[],
  reset() {
    this.coverage.clear();
    this.classes.clear();
    this.events.length = 0;
    this.requirements.clear();
    this.relationships.clear();
    this.lost.clear();
    this.plans.clear();
    this.logItems.length = 0;
    this.calendar.length = 0;
    this.calendarCalls.length = 0;
    this.calendarFailures.length = 0;
    this.planCalls.length = 0;
    this.lostCalls.length = 0;
    this.relationshipCalls.length = 0;
  },
  preloadRequirement(teacher: string, topic_key: string, grade: number, subject: string, core: number, non: number, origin: RequirementItem['origin'] = 'teacher') {
    const list = (this.requirements.get(teacher) ?? []).filter((r) => r.topic_key !== topic_key);
    list.push({ topic_key, grade, subject, classification: core && non ? 'mixed' : core ? 'core' : 'non_core', core_periods: core, non_core_periods: non, independent_periods: 0, teaching_mode: 'SHARED', origin, version: 1 });
    this.requirements.set(teacher, list);
  },
  preloadLost(teacher: string, grade: number, subject: string, date: string, period: number, reason = 'Health Drive', status: LostRow['status'] = 'active', batch: string | null = null) {
    const row: LostRow = { id: `lost-${this.lost.get(teacher)?.length ?? 0}-${date}-${period}`, grade, subject, date, period, reason, topic_keys: [], notes: null, batch_id: batch, status, withdrawn_reason: null, recorded_by: teacher, recorded_at: '2026-09-01T09:00:00', schedule_version: null };
    this.lost.set(teacher, [...(this.lost.get(teacher) ?? []), row]);
  },
  preload(teacher: string, topic_key: string, status: Coverage, source: Cell['source'] = 'MANUAL') {
    if (!this.coverage.has(teacher)) this.coverage.set(teacher, new Map());
    this.coverage.get(teacher)!.set(topic_key, { status, source });
  },
};

/* eslint-disable @typescript-eslint/no-explicit-any */
const authUser = (): { id: string; name: string; role: string } => {
  try {
    const u = JSON.parse(localStorage.getItem('lumeneios_test_user') ?? 'null');
    return { id: u.id, name: u.name, role: u.role };
  } catch {
    return { id: 'anonymous', name: 'anonymous', role: 'student' };
  }
};
const refuse = (status: number, detail: string): never => {
  throw Object.assign(new Error(detail), { status, data: { detail } });
};
const ownerPlan = (id: string, who = authUser()) => {
  const p = fakeStore.plans.get(id) ?? refuse(404, 'Plan not found.');
  if (who.role !== 'teacher' || who.id !== p.teacherId) refuse(403, 'Only the teacher who owns this plan can do that.');
  return p;
};
const reviewerPlan = (id: string, who = authUser()) => {
  if (!['admin', 'principal'].includes(who.role)) refuse(403, 'Only an Admin or Principal can approve or reject.');
  return fakeStore.plans.get(id) ?? refuse(404, 'Plan not found.');
};
const calendarApi = {
  calendar: async () => {
    const failure = fakeStore.calendarFailures.shift();
    if (failure) refuse(failure, 'Calendar service error');
    const last = fakeStore.calendar[fakeStore.calendar.length - 1];
    return { version: last?.version ?? 0, config: last?.config ?? {}, capacity: {} };
  },
  calendarHistory: async () => ({ versions: JSON.parse(JSON.stringify(fakeStore.calendar)) }),
  previewCalendar: async (config: any) => {
    fakeStore.calendarCalls.push({ op: 'preview', body: config });
    const v = fakeStore.calendar.length;
    return { current_version: v, proposed_version: v + 1, unchanged: false, capacity_before: {}, capacity_after: {}, impact: [], teacher_configurations_changed: false };
  },
  saveCalendar: async (body: { config: any; reason: string; expected_version?: number }) => {
    fakeStore.calendarCalls.push({ op: 'save', body });
    if (!['admin', 'principal'].includes(authUser().role)) refuse(403, 'Only an Admin or Principal can change the academic calendar.');
    const v = fakeStore.calendar.length;
    if (body.expected_version !== undefined && body.expected_version !== v) refuse(409, 'A different Academic Configuration was saved while you were editing. Review it, then save again.');
    if (v && JSON.stringify(fakeStore.calendar[v - 1].config) === JSON.stringify(body.config)) refuse(422, 'The calendar is unchanged; there is nothing to save.');
    if (v && (body.reason ?? '').trim().length < 3) refuse(422, 'A reason for the calendar change is required.');
    fakeStore.calendar.push({ version: v + 1, config: JSON.parse(JSON.stringify(body.config)), reason: body.reason, created_by: authUser().id, created_by_name: authUser().name, created_by_role: authUser().role, created_at: new Date().toISOString(), capacity: {} });
    return { version: v + 1, teachers_needing_review: 0 };
  },
  calendarImpact: async () => ({ current_version: fakeStore.calendar.length, previous_version: null, changed_at: null, reason: null, has_previous: false, impact: null }),
};
const currentOf = (p: any) => p.versions[p.versions.length - 1];

/** The server's plan rules, in miniature, so UI tests exercise the real screens against the same lifecycle. */
const fakePlanApi = {
  listPlans: async (teacher?: string) => {
    const who = authUser();
    const all = [...fakeStore.plans.values()];
    const mine = who.role === 'teacher' ? all.filter((p) => p.teacherId === who.id) : teacher ? all.filter((p) => p.teacherId === teacher) : all;
    return { plans: JSON.parse(JSON.stringify(mine)) };
  },
  createPlan: async (teacher: string, body: any) => {
    const who = authUser();
    fakeStore.planCalls.push({ op: 'create', planId: body.id, body });
    if (who.role !== 'teacher' || who.id !== teacher) refuse(403, 'Only the owning teacher can create their plan.');
    if (fakeStore.plans.has(body.id)) refuse(409, 'A plan with this id already exists.');
    fakeStore.plans.set(body.id, { ...body, teacherId: teacher, schoolId: 'school-1', createdBy: who, createdAt: new Date().toISOString(), status: 'DRAFT', versions: [], execution: [], evidence: [], proposals: [], losses: [] });
    return { id: body.id };
  },
  reviewPlan: async (id: string, body: { decision: string; note: string }) => {
    fakeStore.planCalls.push({ op: 'review-plan', planId: id, body });
    const who = authUser();
    const p = reviewerPlan(id, who);
    if (p.status !== 'DRAFT') refuse(409, 'Only a draft plan can be approved or rejected.');
    const note = (body.note ?? '').trim();
    const review = { by: who, at: new Date().toISOString(), note, decision: body.decision };
    if (body.decision === 'REJECTED') {
      if (note.length < 5) refuse(422, 'A rejection reason is required.');
      Object.assign(p, { status: 'REJECTED', review });
      return { id, status: p.status };
    }
    if (!p.draft.lessons.length) refuse(422, 'A plan without syllabus units cannot be approved.');
    if ((p.draft.conflicts ?? []).some((c: any) => ['REQUIREMENT_MISSING', 'PREREQUISITE_ORDER'].includes(c.code))) refuse(422, 'Resolve missing approved requirements and prerequisite order before approval.');
    for (const o of fakeStore.plans.values()) if (o.status === 'APPROVED' && o.teacherId === p.teacherId && o.grade === p.grade && o.subject === p.subject) {
      o.status = 'SUPERSEDED';
      o.supersededBy = id;
      for (const x of o.proposals) if (x.status === 'PENDING') x.status = 'SUPERSEDED';
    }
    p.versions = [{ version: 1, lessons: p.draft.lessons, metrics: p.draft.metrics, conflicts: p.draft.conflicts, config: p.config, approvedBy: who, approvedAt: review.at, reason: note || 'Initial schedule approved', proposalId: null, lostSlots: [] }];
    Object.assign(p, { status: 'APPROVED', review });
    return { id, status: p.status, version: 1 };
  },
  recordExecution: async (id: string, body: any) => {
    fakeStore.planCalls.push({ op: 'execution', planId: id, body });
    const p = ownerPlan(id);
    if (p.status !== 'APPROVED') refuse(409, 'Execution can only be recorded against an approved plan.');
    p.execution.push({ ...body, recordedBy: authUser(), recordedAt: new Date().toISOString(), scheduleVersion: currentOf(p).version });
    return {};
  },
  recordEvidence: async (id: string, body: any) => {
    fakeStore.planCalls.push({ op: 'evidence', planId: id, body });
    const p = ownerPlan(id);
    p.evidence.push({ ...body, recordedBy: authUser(), recordedAt: new Date().toISOString() });
    return {};
  },
  createProposal: async (id: string, body: any) => {
    fakeStore.planCalls.push({ op: 'proposal', planId: id, body });
    const who = authUser();
    const p = fakeStore.plans.get(id) ?? refuse(404, 'Plan not found.');
    if (!(who.role === 'teacher' && who.id === p.teacherId) && !['admin', 'principal'].includes(who.role)) refuse(403, 'Not permitted.');
    if (body.baseVersion !== currentOf(p).version) refuse(409, 'The approved schedule changed after this proposal was generated. Regenerate the proposal.');
    for (const x of p.proposals) if (x.status === 'PENDING') x.status = 'SUPERSEDED';
    p.proposals.push({ ...body, status: 'PENDING', createdBy: who });
    return {};
  },
  supersedeProposals: async (id: string) => {
    fakeStore.planCalls.push({ op: 'supersede', planId: id });
    const p = fakeStore.plans.get(id) ?? refuse(404, 'Plan not found.');
    for (const x of p.proposals) if (x.status === 'PENDING') x.status = 'SUPERSEDED';
    return { superseded: [] };
  },
  reviewProposal: async (id: string, proposalId: string, body: { decision: string; note: string }) => {
    fakeStore.planCalls.push({ op: 'review-proposal', planId: id, body: { proposalId, ...body } });
    const who = authUser();
    const p = reviewerPlan(id, who);
    const x = p.proposals.find((y: any) => y.id === proposalId) ?? refuse(404, 'Proposal not found.');
    if (x.status !== 'PENDING') refuse(409, 'Only a pending proposal can be approved or rejected.');
    const note = (body.note ?? '').trim();
    const review = { by: who, at: new Date().toISOString(), note };
    if (body.decision === 'REJECTED') {
      if (note.length < 5) refuse(422, 'A rejection reason is required.');
      Object.assign(x, { status: 'REJECTED', review });
      return { id: proposalId, status: 'REJECTED' };
    }
    const cur = currentOf(p);
    if (x.baseVersion !== cur.version) refuse(409, 'The approved schedule changed after this proposal was generated. Regenerate the proposal.');
    p.versions.push({ version: cur.version + 1, lessons: x.lessons, metrics: x.metrics, conflicts: x.conflicts, config: x.config, approvedBy: who, approvedAt: review.at,
      reason: note || (x.trigger.kind === 'CONFIG_CHANGE' ? 'Recalculated for updated Academic Configuration' : x.trigger.kind === 'LOST_PERIODS' ? 'Lost-period recovery approved' : 'Recovery proposal approved'),
      proposalId, lostSlots: x.lostSlots ?? cur.lostSlots ?? [] });
    p.config = x.config;
    Object.assign(x, { status: 'APPROVED', review });
    return { id: proposalId, status: 'APPROVED', version: cur.version + 1 };
  },
};

export function makeFakeTeacherPlanApi() {
  const plan = async (teacher: string, grade: number, subject: string): Promise<TeacherPlan> => {
    // Coverage rows and saved requirements are both rows of the teacher's plan (as in the backend).
    const cover = fakeStore.coverage.get(teacher) ?? new Map<string, Cell>();
    const reqs = new Map((fakeStore.requirements.get(teacher) ?? []).filter((r) => r.grade === grade && r.subject === subject).map((r) => [r.topic_key, r]));
    const keys = [...new Set([...cover.keys(), ...reqs.keys()])];
    const topics = keys.map((k) => {
      const c = cover.get(k) ?? { status: 'not_done' as Coverage, source: 'MANUAL' as const };
      const r = reqs.get(k);
      const o = fakeStore.classes.get(teacher)?.get(k);
      const core = o?.core ?? r?.core_periods ?? 1;
      const non = o?.non ?? r?.non_core_periods ?? 1;
      return {
        topic_key: k, chapter_number: '1', chapter_title: 't', section: k, classification: (o?.classification ?? r?.classification ?? 'mixed') as 'core' | 'mixed' | 'non_core',
        core_periods: core, non_core_periods: non, teaching_mode: (r?.teaching_mode ?? 'INDEPENDENT') as 'SHARED' | 'INDEPENDENT', independent_periods: r?.independent_periods ?? 0,
        classroom_periods: core + non - (r?.independent_periods ?? 0), origin: (r?.origin ?? 'demo_default') as 'demo_default' | 'teacher', version: 1, coverage: c.status, coverage_source: c.source,
        coverage_updated_at: null, prerequisites: [], taught_periods: 0, remaining_core: core, remaining_non_core: non,
      };
    });
    return {
      teacher_id: teacher, grade, subject, calendar_version: 1,
      capacity: { available_periods: 100, reserved_periods: 10, topic_capacity: 90 },
      allocation: { proposed_total: 0, topic_capacity: 90, remaining: 90, deficit: 0, valid: true, errors: [] },
      topic_count: topics.length, configured_topic_count: topics.length, topics,
      coverage: { eligible: topics.length, done: 0, in_progress: 0, not_done: 0, percent: 0 },
    };
  };
  return {
    ...fakePlanApi,
    ...calendarApi,
    plan,
    initialize: async () => ({ created: false }),
    relationships: async (teacher: string) => ({ teacher_id: teacher, items: fakeStore.relationships.get(teacher) ?? [] }),
    addRelationship: async (teacher: string, body: { kind: string; from_key: string; to_key: string; explanation: string; evidence: string; shared_periods?: number; lead_key?: string | null }) => {
      fakeStore.relationshipCalls.push({ op: 'add', teacher, body });
      const item: RelationshipItem = { id: `rel-${fakeStore.relationshipCalls.length}`, kind: body.kind as RelationshipItem['kind'], from_key: body.from_key, to_key: body.to_key, explanation: body.explanation, evidence: body.evidence, shared_periods: body.shared_periods ?? 0, lead_key: body.lead_key ?? null, status: 'active', origin: 'teacher', created_by: teacher, created_at: null };
      fakeStore.relationships.set(teacher, [...(fakeStore.relationships.get(teacher) ?? []), item]);
      return item;
    },
    removeRelationship: async (teacher: string, id: string) => {
      fakeStore.relationshipCalls.push({ op: 'remove', teacher, body: id });
      fakeStore.relationships.set(teacher, (fakeStore.relationships.get(teacher) ?? []).map((r) => (r.id === id ? { ...r, status: 'removed' as const } : r)));
      return {} as RelationshipItem;
    },
    requirements: async (teacher: string) => ({ teacher_id: teacher, items: fakeStore.requirements.get(teacher) ?? [] }),
    setCoverage: async (teacher: string, body: { topic_key: string; status: Coverage; source?: 'MANUAL' | 'EXECUTION' }) => {
      const before = fakeStore.coverage.get(teacher)?.get(body.topic_key)?.status ?? 'not_done';
      fakeStore.preload(teacher, body.topic_key, body.status, body.source ?? 'MANUAL');
      if (before !== body.status) fakeStore.events.push({ teacher, topic_key: body.topic_key, from: before, to: body.status, source: body.source ?? 'MANUAL' });
      return {};
    },
    saveRequirements: async (teacher: string, body: { items: { topic_key: string; core_periods: number; non_core_periods: number; classification?: 'core' | 'mixed' | 'non_core' }[] }) => {
      const m = fakeStore.classes.get(teacher) ?? new Map();
      for (const i of body.items) m.set(i.topic_key, { classification: i.classification ?? 'mixed', core: i.core_periods, non: i.non_core_periods });
      fakeStore.classes.set(teacher, m);
      return { changed: body.items.map((i) => i.topic_key) };
    },
    lost: async (teacher: string, grade: number, subject: string) => {
      const records = (fakeStore.lost.get(teacher) ?? []).filter((r) => r.grade === grade && r.subject === subject);
      const active = records.filter((r) => r.status === 'active');
      return { total_days: 100, completed_days: 10, remaining_days: 90, lost_days: new Set(active.map((r) => r.date)).size, lost_periods: active.length, log: [], records };
    },
    lostAll: async (teacher: string) => ({ teacher_id: teacher, items: fakeStore.lost.get(teacher) ?? [] }),
    recordLostBatch: async (teacher: string, body: { grade: number; subject: string; entries: { date: string; periods: number[] }[]; reason_code: string; notes?: string }) => {
      fakeStore.lostCalls.push({ op: 'batch', teacher, body });
      const batch = `batch-${fakeStore.lostCalls.length}`;
      const rows: LostRow[] = [];
      for (const e of body.entries) for (const n of e.periods) {
        fakeStore.preloadLost(teacher, body.grade, body.subject, e.date, n, body.reason_code, 'active', batch);
        const row = fakeStore.lost.get(teacher)!.slice(-1)[0];
        row.notes = body.notes ?? null;
        rows.push(row);
      }
      return { batch_id: batch, records: rows };
    },
    withdrawLost: async (teacher: string, body: { grade: number; subject: string; date: string; periods: number[]; reason: string }) => {
      fakeStore.lostCalls.push({ op: 'withdraw', teacher, body });
      fakeStore.lost.set(teacher, (fakeStore.lost.get(teacher) ?? []).map((r) => (r.grade === body.grade && r.subject === body.subject && r.date === body.date && body.periods.includes(r.period) ? { ...r, status: 'withdrawn' as const, withdrawn_reason: body.reason } : r)));
      return { date: body.date, withdrawn: body.periods, lost_day_remains: false };
    },
    recordLost: async () => ({}),
    planningOversight: async () => ({ rows: [] }),
    curriculumOversight: async () => ({ rows: [] }),
    logs: async () => ({ total: fakeStore.logItems.length, items: fakeStore.logItems }),
  };
}
