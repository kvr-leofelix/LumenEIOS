/** Typed client for the teacher-scoped planning API. The backend is authoritative for every number shown. */
import { apiRequest } from './apiClient';

export type Coverage = 'done' | 'in_progress' | 'not_done';
export type Classification = 'core' | 'non_core' | 'mixed';

export interface PlanTopicRow {
  topic_key: string;
  chapter_number: string;
  chapter_title: string;
  section: string;
  classification: Classification;
  core_periods: number;
  non_core_periods: number;
  teaching_mode: 'SHARED' | 'INDEPENDENT';
  independent_periods: number;
  classroom_periods: number;
  origin: 'demo_default' | 'teacher' | 'approved_import';
  version: number;
  coverage: Coverage;
  coverage_source: 'MANUAL' | 'EXECUTION';
  coverage_updated_at: string | null;
  prerequisites: string[];
  /** Actually taught periods (classroom execution records of every plan of this teacher, class and subject). */
  taught_periods?: number;
  remaining_core?: number;
  remaining_non_core?: number;
}
export interface AllocationCheck {
  proposed_total: number;
  topic_capacity: number;
  remaining: number;
  deficit: number;
  valid: boolean;
  errors: string[];
}
export interface RequirementItem {
  topic_key: string; grade: number; subject: string; classification: Classification;
  core_periods: number; non_core_periods: number; independent_periods: number; teaching_mode: 'SHARED' | 'INDEPENDENT';
  origin: 'demo_default' | 'teacher' | 'approved_import'; version: number;
}
export interface LostRow {
  id: string; grade: number; subject: string; date: string; period: number; reason: string; topic_keys: string[];
  notes: string | null; batch_id: string | null; status: 'active' | 'withdrawn'; withdrawn_reason: string | null;
  recorded_by: string; recorded_at: string | null; schedule_version: number | null;
}
export interface CapacityFigures { available_periods: number; reserved_periods: number; topic_capacity: number }
export interface CalendarVersion {
  version: number; reason: string | null; created_by: string; created_by_name: string; created_by_role: string; created_at: string | null; config: Record<string, unknown>;
  capacity: Record<string, CapacityFigures>;
}
export interface CalendarImpactRow {
  teacher_id: string; teacher_name: string; grade: number; subject: string; capacity_before: CapacityFigures; capacity_after: CapacityFigures;
  saved_total: number; remaining_before: number; remaining_after: number; deficit_after: number; needs_teacher_review: boolean;
  periods_gained_or_lost: number; core_requirements_fit: boolean; core_shortfall: number; insufficient_capacity: boolean;
  topics: {
    topic_key: string; section: string; classification: Classification; teaching_mode: 'SHARED' | 'INDEPENDENT'; origin: string;
    original_allocation: number; revised_allocation: number; allocation_change: number;
    original_classroom: number; revised_classroom: number; classroom_change: number;
    original_independent: number; revised_independent: number; independent_change: number;
    saved: number; saved_core: number; default_before: number; default_after: number; is_affected: boolean; customization_conflict: boolean;
  }[];
  approved_schedule: { plan_id: string; calendar_differs: boolean; capacity_conflict: boolean; note: string } | null;
}
export interface CalendarPreview {
  current_version: number; proposed_version: number; unchanged: boolean; capacity_before: Record<string, CapacityFigures>;
  capacity_after: Record<string, CapacityFigures>; impact: CalendarImpactRow[]; teacher_configurations_changed: boolean;
}
export interface TeacherCalendarImpact {
  current_version: number; previous_version: number | null; changed_at: string | null; reason: string | null; has_previous: boolean; impact: CalendarImpactRow | null;
}
export interface RelationshipItem {
  id: string; kind: 'PREREQUISITE' | 'CROSS_CURRICULAR'; from_key: string; to_key: string; explanation: string | null;
  evidence: string | null; shared_periods: number; lead_key: string | null; status: 'active' | 'removed';
  origin: 'teacher' | 'approved_import'; created_by: string; created_at: string | null;
}
export interface CoverageStats { eligible: number; done: number; in_progress: number; not_done: number; percent: number }
export interface PlanSummary {
  periods_per_day: number; instructional_days: number; required_core: number; required_non_core: number; taught_periods: number;
  done_topics: number; open_topics: number; remaining_required_core: number; remaining_required_non_core: number;
  window: { after: string; days_left: number; periods_left: number; reserve_left: number; capacity_left: number };
  remaining_capacity: number; unallocated_capacity: number; core_shortfall: number; total_shortfall: number; fits: boolean;
  last_recalculation: { at: string; summary: string; previous: unknown; new: unknown; reason: string | null } | null;
}
export interface TeacherPlan {
  summary?: PlanSummary;
  teacher_id: string;
  teacher_name?: string | null;
  academic_year?: string;
  grade: number;
  subject: string;
  calendar_version: number;
  capacity: { available_periods: number; reserved_periods: number; topic_capacity: number };
  allocation: AllocationCheck;
  topics: PlanTopicRow[];
  topic_count: number;
  configured_topic_count: number;
  coverage: CoverageStats;
}
export interface LostOverview {
  total_days: number; completed_days: number; remaining_days: number; lost_days: number; lost_periods: number;
  log: { id: string; date: string; period: number; reason: string; topic_keys: string[]; notes: string | null }[];
  records: LostRow[];
}
export interface PlanLogEvent {
  id: string; occurred_at: string; actor_name: string; actor_role: string; school_id: string; teacher_id: string | null;
  grade: number | null; subject: string | null; topic_keys: string[]; category: string; status: string;
  previous_value: unknown; new_value: unknown; reason: string | null; schedule_version: number | null;
  related_event_id: string | null; related_proposal_id: string | null; summary: string;
}
export interface PlanningRow {
  teacher_id: string; teacher_name: string; grade: number; subject: string; config_status: string;
  teaching_days_completed: number; teaching_days_remaining: number; lost_days: number; lost_periods: number;
  required_periods: number; scheduled_periods: number | null; taught_periods: number | null; outstanding_core_periods: number | null;
  pending_proposals: number | null; pending_drafts: number; approval_status: string; schedule_version: number | null; plan_id: string | null;
  indicator: 'green' | 'amber' | 'red';
  capacity: { topic_capacity: number };
}
export interface CoverageRow extends CoverageStats {
  teacher_id: string; teacher_name: string; grade: number; subject: string;
  chapters: { chapter_number: string; chapter_title: string; stats: CoverageStats; topics: { topic_key: string; section: string; status: Coverage }[] }[];
}

const q = (o: Record<string, string | number | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => v !== undefined && v !== null && v !== '' && p.set(k, String(v)));
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const teacherPlanApi = {
  plan: (teacher: string, grade: number, subject: string) => apiRequest<TeacherPlan>(`/teacher-plans/${teacher}${q({ grade, subject })}`),
  requirements: (teacher: string) => apiRequest<{ teacher_id: string; items: RequirementItem[] }>(`/teacher-plans/${teacher}/requirements`),
  relationships: (teacher: string) => apiRequest<{ teacher_id: string; items: RelationshipItem[] }>(`/teacher-plans/${teacher}/relationships`),
  addRelationship: (teacher: string, body: { kind: string; from_key: string; to_key: string; explanation: string; evidence: string; shared_periods?: number; lead_key?: string | null }) =>
    apiRequest<RelationshipItem>(`/teacher-plans/${teacher}/relationships`, { method: 'POST', body: JSON.stringify(body) }),
  removeRelationship: (teacher: string, id: string, reason?: string) =>
    apiRequest<RelationshipItem>(`/teacher-plans/${teacher}/relationships/${id}${q({ reason })}`, { method: 'DELETE' }),
  listPlans: (teacher?: string) => apiRequest<{ plans: unknown[] }>(`/plans${q({ teacher_id: teacher })}`),
  createPlan: (teacher: string, body: unknown) => apiRequest<{ id: string }>(`/teacher-plans/${teacher}/plans`, { method: 'POST', body: JSON.stringify(body) }),
  reviewPlan: (planId: string, body: { decision: 'APPROVED' | 'REJECTED'; note: string }) =>
    apiRequest<{ id: string; status: string }>(`/plans/${planId}/review`, { method: 'POST', body: JSON.stringify(body) }),
  recordExecution: (planId: string, body: unknown) => apiRequest(`/plans/${planId}/execution`, { method: 'POST', body: JSON.stringify(body) }),
  recordEvidence: (planId: string, body: unknown) => apiRequest(`/plans/${planId}/evidence`, { method: 'POST', body: JSON.stringify(body) }),
  createProposal: (planId: string, body: unknown) => apiRequest(`/plans/${planId}/proposals`, { method: 'POST', body: JSON.stringify(body) }),
  supersedeProposals: (planId: string, reason: string) =>
    apiRequest<{ superseded: string[] }>(`/plans/${planId}/proposals/supersede`, { method: 'POST', body: JSON.stringify({ reason }) }),
  reviewProposal: (planId: string, proposalId: string, body: { decision: 'APPROVED' | 'REJECTED'; note: string }) =>
    apiRequest<{ id: string; status: string }>(`/plans/${planId}/proposals/${proposalId}/review`, { method: 'POST', body: JSON.stringify(body) }),
  calendar: () => apiRequest<{ version: number; config: Record<string, unknown>; capacity: Record<string, CapacityFigures> }>(`/plan-calendar`),
  calendarHistory: () => apiRequest<{ versions: CalendarVersion[] }>(`/plan-calendar/history`),
  previewCalendar: (config: unknown) => apiRequest<CalendarPreview>(`/plan-calendar/preview`, { method: 'POST', body: JSON.stringify({ config }) }),
  saveCalendar: (body: { config: unknown; reason: string; expected_version?: number }) =>
    apiRequest<{ version: number; teachers_needing_review: number; plans_recalculated?: number; topics_changed?: number }>(`/plan-calendar`, { method: 'PUT', body: JSON.stringify(body) }),
  calendarImpact: (teacher: string, grade: number, subject: string) => apiRequest<TeacherCalendarImpact>(`/teacher-plans/${teacher}/calendar-impact${q({ grade, subject })}`),
  initialize: (teacher: string, grade: number, subject: string) => apiRequest<{ created: boolean }>(`/teacher-plans/${teacher}/initialize${q({ grade, subject })}`, { method: 'POST' }),
  saveRequirements: (teacher: string, body: { grade: number; subject: string; reason?: string; items: { topic_key: string; core_periods: number; non_core_periods: number; classification?: Classification }[] }) =>
    apiRequest<{ changed: string[] }>(`/teacher-plans/${teacher}/requirements`, { method: 'PUT', body: JSON.stringify(body) }),
  setCoverage: (teacher: string, body: { grade: number; subject: string; topic_key: string; status: Coverage; source?: 'MANUAL' | 'EXECUTION' }) =>
    apiRequest(`/teacher-plans/${teacher}/coverage`, { method: 'PUT', body: JSON.stringify(body) }),
  lost: (teacher: string, grade: number, subject: string) => apiRequest<LostOverview>(`/teacher-plans/${teacher}/lost-periods${q({ grade, subject })}`),
  recordLost: (teacher: string, body: { grade: number; subject: string; date: string; periods: number[]; topic_keys: string[]; reason_code: string; notes?: string }) =>
    apiRequest(`/teacher-plans/${teacher}/lost-periods`, { method: 'POST', body: JSON.stringify(body) }),
  recordLostBatch: (teacher: string, body: { grade: number; subject: string; entries: { date: string; periods: number[] }[]; topic_keys: string[]; reason_code: string; notes?: string }) =>
    apiRequest<{ batch_id: string; records: LostRow[] }>(`/teacher-plans/${teacher}/lost-periods/batch`, { method: 'POST', body: JSON.stringify(body) }),
  withdrawLost: (teacher: string, body: { grade: number; subject: string; date: string; periods: number[]; reason: string }) =>
    apiRequest<{ date: string; withdrawn: number[]; lost_day_remains: boolean }>(`/teacher-plans/${teacher}/lost-periods/withdraw`, { method: 'POST', body: JSON.stringify(body) }),
  lostAll: (teacher: string) => apiRequest<{ teacher_id: string; items: LostRow[] }>(`/teacher-plans/${teacher}/lost-periods/all`),
  planningOversight: (f: { grade?: number; subject?: string; teacher_id?: string } = {}) => apiRequest<{ rows: PlanningRow[] }>(`/plan-oversight/planning${q(f)}`),
  curriculumOversight: (f: { grade?: number; subject?: string; teacher_id?: string } = {}) => apiRequest<{ rows: CoverageRow[] }>(`/plan-oversight/curriculum${q(f)}`),
  logs: (f: Record<string, string | number | undefined>) => apiRequest<{ total: number; items: PlanLogEvent[] }>(`/plan-logs${q(f)}`),
};

/** Surface the backend's capacity explanation (422 detail object) as readable text. */
export function describeError(e: unknown): { message: string; allocation?: AllocationCheck } {
  const body = (e as { data?: { detail?: unknown } })?.data;
  const d = body?.detail as Partial<AllocationCheck> & { message?: string } | string | undefined;
  if (d && typeof d === 'object' && 'errors' in d && Array.isArray(d.errors)) return { message: (d.errors ?? []).join(' ') || d.message || 'Rejected.', allocation: d as AllocationCheck };
  return { message: typeof d === 'string' ? d : e instanceof Error ? e.message : 'Request failed.' };
}

export const CATEGORY_LABEL: Record<string, string> = {
  lost_period: 'Lost period', lost_day: 'Lost day', period_requirement: 'Period requirement', topic_classification: 'Classification',
  topic_relationship: 'Relationship', coverage_status: 'Coverage', calendar_change: 'Calendar', recovery_proposal: 'Recovery proposal',
  plan_draft: 'Plan submitted', plan_approval: 'Plan approval', plan_rejection: 'Plan rejection',
  recovery_approval: 'Recovery approval', recovery_rejection: 'Recovery rejection', schedule_change: 'Schedule change', teaching_execution: 'Teaching execution',
};
export const COVERAGE_STYLE: Record<Coverage, { bg: string; fg: string; label: string }> = {
  done: { bg: 'rgba(22,163,74,0.16)', fg: '#166534', label: 'Done' },
  in_progress: { bg: 'rgba(245,158,11,0.18)', fg: '#92400E', label: 'In progress' },
  not_done: { bg: 'rgba(156,163,175,0.22)', fg: '#4B5563', label: 'Not done' },
};
