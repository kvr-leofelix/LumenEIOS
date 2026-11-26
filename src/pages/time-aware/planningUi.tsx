import React from 'react';
import { AlertTriangle, CheckCircle2, CloudOff, Database, Info, XCircle } from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import { Card, CardBody, CardHeader } from '../../components/common/Card';
import type { Conflict, PlannedLesson } from '../../lib/planning/engine';
import { COVERAGE_COLOR, COVERAGE_LABEL, statusOf } from '../../lib/planning/coverage';
import { useTeacherCoverage } from '../../features/teacherPlan/useTeacherCoverage';
import { usePlanning } from '../../lib/planning/usePlanning';
import { isLegacyRequirement, lessonEnd, lessonStart } from '../../lib/planning/engine';
import type { LessonState } from '../../lib/planning/execution';
import { STATE_LABEL } from '../../lib/planning/execution';
import type { ReviewStatus, ClassValue } from '../../lib/planning/governance';
import type { StoreMode } from '../../lib/planning/store';
import { GRADE_LABEL } from '../../lib/planning/calendar';

export const inputCls = 'w-full px-3 py-2 bg-white border border-surface-border rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-teal-400';
export const selectCls = 'px-2.5 py-1.5 bg-surface-bg border border-surface-border rounded-lg text-xs';
export const labelCls = 'block font-semibold text-content-primary mb-1 text-xs';
export const thCls = 'px-3 py-2 text-left font-semibold text-content-secondary text-[11px] uppercase tracking-wide border-b border-surface-border bg-surface-bg';
export const tdCls = 'px-3 py-2 border-b border-surface-border align-top';

export const PageHeader: React.FC<{ title: string; subtitle: string; badge?: React.ReactNode; actions?: React.ReactNode }> = ({ title, subtitle, badge, actions }) => (
  <div className="bg-white p-5 rounded-2xl border border-surface-border shadow-subtle flex flex-col sm:flex-row sm:items-center justify-between gap-4">
    <div>
      <div className="flex items-center gap-2 flex-wrap">
        <h1 className="text-xl font-bold text-navy-900 tracking-tight">{title}</h1>
        {badge}
      </div>
      <p className="text-xs text-content-secondary mt-1">{subtitle}</p>
    </div>
    {actions && <div className="flex items-center gap-x-4 gap-y-2 flex-wrap shrink-0 whitespace-nowrap">{actions}</div>}
  </div>
);

export const StoreBanner: React.FC<{ mode: StoreMode; notice: string; error: string; revision: number; legacyPlans?: number; onDismiss?: () => void; onRetry?: () => void }> = ({ mode, notice, error, revision, legacyPlans, onDismiss, onRetry }) => (
  <div className="space-y-2">
    {mode === 'server' && !error && (
      <div className="flex items-center gap-2 text-[11px] text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
        <Database className="w-3.5 h-3.5" /> Shared planning store (backend) · revision {revision}. Admin, Principal and Teacher see the same records.
      </div>
    )}
    {mode === 'loading' && <div className="text-[11px] text-content-secondary bg-surface-bg border border-surface-border rounded-lg px-3 py-2">Connecting to the planning store…</div>}
    {mode === 'local' && (
      <div className="flex items-start gap-2 text-[11px] text-amber-900 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2" data-testid="local-mode-banner">
        <CloudOff className="w-3.5 h-3.5 mt-0.5 shrink-0" />
        <span>{notice || 'Browser-only mode: records are saved in this browser only and are not shared with other users or devices.'}</span>
      </div>
    )}
    {!!legacyPlans && (
      <div className="text-[11px] text-content-secondary bg-surface-bg border border-surface-border rounded-lg px-3 py-2">
        {legacyPlans} plan(s) from the earlier prototype remain untouched in browser storage (key lumeneios_academicWorkflow); they are not used by this workflow.
      </div>
    )}
    {error && (
      <div role="alert" className="flex items-start justify-between gap-2 text-xs text-rose-800 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
        <span className="flex items-start gap-2">
          <XCircle className="w-4 h-4 mt-0.5 shrink-0" />
          {error}
        </span>
        {mode === 'error' && onRetry ? (
          <button className="text-rose-700 underline shrink-0 font-semibold" onClick={onRetry}>
            Retry
          </button>
        ) : (
          onDismiss && (
            <button className="text-rose-700 underline shrink-0" onClick={onDismiss}>
              Dismiss
            </button>
          )
        )}
      </div>
    )}
  </div>
);

export const Stat: React.FC<{ label: string; value: React.ReactNode; hint?: React.ReactNode; tone?: 'navy' | 'teal' | 'amber' | 'rose' | 'indigo' }> = ({ label, value, hint, tone = 'navy' }) => {
  const color = { navy: 'text-navy-900', teal: 'text-teal-700', amber: 'text-amber-700', rose: 'text-rose-700', indigo: 'text-indigo-700' }[tone];
  return (
    <div className="p-4 bg-white rounded-xl border border-surface-border text-xs">
      <span className="text-content-secondary uppercase font-semibold text-[11px]">{label}</span>
      <p className={`text-2xl font-bold mt-1 ${color}`}>{value}</p>
      {hint && <span className="text-content-muted text-[11px]">{hint}</span>}
    </div>
  );
};

// The same words Course Curriculum uses for the same persisted classification.
const classText = (value: ClassValue | 'PENDING' | null | undefined) => (value === 'CORE' ? 'Core' : value === 'MIXED' ? 'Mixed' : 'Non-Core');

export const ClassBadge: React.FC<{ value: ClassValue | 'PENDING' | null | undefined; status?: ReviewStatus }> = ({ value, status }) => {
  if (status === 'DEMO_DEFAULT') return <Badge size="sm" variant="teal">{classText(value)}</Badge>;
  if (status === 'TEACHER_CUSTOM') return <Badge size="sm" variant="teal">{classText(value)}</Badge>;
  if (status && status !== 'APPROVED') {
    return (
      <Badge size="sm" variant={status === 'REJECTED' ? 'danger' : status === 'PROPOSED' ? 'info' : 'default'}>
        {status === 'PENDING' ? 'Configuration required' : status === 'PROPOSED' ? `Proposed ${classText(value)} — awaiting review` : `Rejected ${classText(value)}`}
      </Badge>
    );
  }
  if (value === 'MIXED') return <Badge size="sm" variant="teal">Core + Non-Core (approved)</Badge>;
  if (value === 'CORE') return <Badge size="sm" variant="teal">Core (approved)</Badge>;
  if (value === 'NON_CORE') return <Badge size="sm" variant="warning">Non-Core (approved)</Badge>;
  return <Badge size="sm">Configuration required</Badge>;
};

const STATE_VARIANT: Record<LessonState, 'default' | 'success' | 'warning' | 'danger' | 'info' | 'teal'> = {
  SCHEDULED: 'default',
  UNSCHEDULED: 'danger',
  TAUGHT: 'success',
  PARTIAL: 'warning',
  HOMEWORK: 'warning',
  DEFERRED: 'warning',
  RESCHEDULED: 'info',
  COMPLETED_LATER: 'success',
  ASSESSED: 'teal',
  LOSS_HOMEWORK: 'default',
  LOSS_RESCHEDULED: 'danger',
};

export const StateBadge: React.FC<{ state: LessonState }> = ({ state }) => (
  <Badge size="sm" variant={STATE_VARIANT[state]} dot>
    {STATE_LABEL[state]}
  </Badge>
);

export const ConflictList: React.FC<{ conflicts: Conflict[] }> = ({ conflicts }) => {
  if (!conflicts.length)
    return (
      <p className="flex items-center gap-2 text-xs text-emerald-700">
        <CheckCircle2 className="w-4 h-4" /> No scheduling conflicts.
      </p>
    );
  return (
    <ul className="space-y-1.5 text-xs" aria-label="Scheduling conflicts">
      {conflicts.map((c, i) => (
        <li key={i} className={`flex items-start gap-2 rounded-lg px-3 py-2 border ${c.severity === 'error' ? 'bg-rose-50 border-rose-200 text-rose-800' : 'bg-amber-50 border-amber-200 text-amber-900'}`}>
          {c.severity === 'error' ? <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" /> : <Info className="w-4 h-4 shrink-0 mt-0.5" />}
          <span>{c.message}</span>
        </li>
      ))}
    </ul>
  );
};

/** Visible warning for a historical lesson that only has a legacy single total (no approved Core/Non-Core split). */
export const LegacyRequirementNote: React.FC<{ lesson: PlannedLesson }> = ({ lesson }) =>
  isLegacyRequirement(lesson) ? (
    <span className="block text-[11px] font-medium text-rose-700" data-testid={`legacy-${lesson.nodeId}`} role="note">
      Legacy requirement — total only, no approved Core/Non-Core split. Unverified: it cannot be used as an approved requirement in new planning until reviewed and approved.
    </span>
  ) : null;

/**
 * Read-only syllabus coverage of a topic (the Curriculum Catalogue's one coverage state), shown beside the schedule so a
 * scheduled period is never mistaken for covered teaching. Scheduling never changes it; only classroom execution or an
 * authorised manual update does.
 */
export const CoverageTag: React.FC<{ nodeId: string; grade: number; subject: string }> = ({ nodeId, grade, subject }) => {
  const { coverage } = useTeacherCoverage(grade, subject);
  const status = statusOf(coverage, nodeId);
  return (
    <span className="block text-[11px] text-content-muted" data-testid={`ta-coverage-${nodeId}`} data-status={status}>
      <span aria-hidden="true" className="inline-block w-2 h-2 rounded-full mr-1.5 align-middle" style={{ backgroundColor: COVERAGE_COLOR[status] }} />
      Syllabus coverage: {COVERAGE_LABEL[status]}
    </span>
  );
};

export function dateRange(l: PlannedLesson | undefined): string {
  if (!l) return '—';
  const s = lessonStart(l);
  const e = lessonEnd(l);
  if (!s) {
    if (l.requiredPeriods === 0) return 'Shared (taught in lead unit)';
    if (l.requiredPeriods - l.independentPeriods <= 0) return 'No classroom time — homework / independent learning';
    return 'Unscheduled';
  }
  const range = s === e ? s : `${s} → ${e}`;
  return l.unscheduledPeriods ? `${range} (+${l.unscheduledPeriods} unscheduled)` : range;
}

/** Side-by-side comparison of schedule versions for each unit. */
export const ScheduleComparison: React.FC<{ columns: { label: string; lessons: PlannedLesson[]; highlight?: boolean }[]; caption?: string }> = ({ columns, caption }) => {
  const base = columns[0]?.lessons ?? [];
  return (
    <div className="overflow-x-auto border border-surface-border rounded-xl">
      <table className="w-full text-xs">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr>
            <th className={thCls}>Unit</th>
            {columns.map((c) => (
              <th key={c.label} className={`${thCls} ${c.highlight ? 'text-amber-800 bg-amber-50' : ''}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {base.map((l) => {
            const cells = columns.map((c) => c.lessons.find((x) => x.nodeId === l.nodeId));
            const changed = cells.some((x) => dateRange(x) !== dateRange(cells[0]));
            return (
              <tr key={l.nodeId} className={changed ? 'bg-amber-50/40' : ''}>
                <td className={tdCls}>
                  <span className="font-semibold text-navy-900">
                    {l.number} {l.title}
                  </span>
                  <LegacyRequirementNote lesson={l} />
                  <span className="block text-[11px] text-content-muted">Ch {l.chapterNumber} · {l.chapterTitle}</span>
                </td>
                {cells.map((x, i) => (
                  <td key={i} className={`${tdCls} ${columns[i].highlight ? 'font-semibold text-amber-900' : ''}`}>
                    {dateRange(x)}
                    {x && <span className="block text-[11px] text-content-muted">{x.slots.length} classroom{x.independentPeriods ? ` · ${x.independentPeriods} independent` : ''}</span>}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export const SectionCard: React.FC<{ title: string; subtitle?: string; action?: React.ReactNode; children: React.ReactNode }> = ({ title, subtitle, action, children }) => (
  <Card>
    <CardHeader title={title} subtitle={subtitle} action={action} />
    <CardBody className="space-y-4 text-xs">{children}</CardBody>
  </Card>
);

export const gradeLabel = (g: number) => `Class ${GRADE_LABEL[g]}`;
