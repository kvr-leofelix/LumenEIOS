import React from 'react';
import { Link } from 'react-router-dom';
import { teacherPlanApi } from '../../lib/teacherPlanApi';
import { tdCls, thCls } from '../../pages/time-aware/planningUi';
import { useRemote } from './useRemote';
import { useStoreVersion } from './requirementsStore';

const DOT = { green: '#16A34A', amber: '#F59E0B', red: '#DC2626' } as const;
const LABEL = { green: 'On track', amber: 'Needs attention', red: 'Critical' } as const;
const ROMAN: Record<number, string> = { 6: 'VI', 7: 'VII', 8: 'VIII' };
const APPROVAL: Record<string, string> = { APPROVED: 'Approved', DRAFT: 'Awaiting approval', REJECTED: 'Rejected', SUPERSEDED: 'Superseded', NO_PLAN: 'No plan' };

/** A figure with no approved schedule behind it is shown as a dash. It is unknown, not zero. */
const num = (n: number | null | undefined) => (n === null || n === undefined ? '—' : n);

/** Compact per-teacher planning table. Plans are never merged across teachers; every figure comes from the backend. */
export const PlanningTeacherTable: React.FC = () => {
  const version = useStoreVersion();
  const { data, error, loading } = useRemote(() => teacherPlanApi.planningOversight(), [version]);
  return (
    <section className="bg-white rounded-xl border border-surface-border overflow-x-auto" data-testid="planning-teacher-table">
      <div className="flex items-center justify-between px-3 py-2">
        <h2 className="text-sm font-bold text-navy-900">Teacher plans</h2>
        <Link className="text-xs font-semibold text-teal-700 underline" to="/logs">All planning history →</Link>
      </div>
      {error && <p role="status" className="px-3 pb-2 text-xs text-rose-700">{error}</p>}
      {loading && !data && <p className="px-3 pb-2 text-xs text-content-muted">Loading…</p>}
      {data && (
        <table className="w-full text-xs">
          <thead>
            <tr>
              {['', 'Teacher', 'Class', 'Subject', 'Config', 'Days done', 'Days left', 'Lost days', 'Lost periods', 'Required', 'Scheduled', 'Taught', 'Core outstanding', 'Proposals', 'Approval', 'Version', ''].map((h, i) => (
                <th key={i} className={thCls}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.length === 0 && <tr><td className={tdCls} colSpan={17}>No teacher plans in this school yet.</td></tr>}
            {data.rows.map((r) => (
              <tr key={`${r.teacher_id}${r.grade}${r.subject}`} className="hover:bg-surface-bg" data-testid="planning-row">
                <td className={tdCls}><span role="img" aria-label={LABEL[r.indicator]} title={LABEL[r.indicator]} className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: DOT[r.indicator] }} /></td>
                <td className={tdCls}><Link className="font-semibold text-teal-700 underline" to={`/curriculum/catalogue/${r.grade}/${r.subject.toLowerCase()}?teacher=${r.teacher_id}`}>{r.teacher_name}</Link></td>
                <td className={tdCls}>{ROMAN[r.grade]}</td>
                <td className={tdCls}>{r.subject}</td>
                <td className={tdCls}>{r.config_status === 'within_capacity' ? 'Within capacity' : 'Over capacity'}</td>
                <td className={tdCls}>{r.teaching_days_completed}</td>
                <td className={tdCls}>{r.teaching_days_remaining}</td>
                <td className={tdCls}>{r.lost_days}</td>
                <td className={tdCls}>{r.lost_periods}</td>
                <td className={tdCls}>{r.required_periods}</td>
                <td className={tdCls} data-testid="scheduled">{num(r.scheduled_periods)}</td>
                <td className={tdCls} data-testid="taught">{num(r.taught_periods)}</td>
                <td className={tdCls} data-testid="core-outstanding">{num(r.outstanding_core_periods)}</td>
                <td className={tdCls} data-testid="proposals">{num(r.pending_proposals)}{r.pending_drafts ? ` (+${r.pending_drafts} draft)` : ''}</td>
                <td className={tdCls}>{APPROVAL[r.approval_status] ?? r.approval_status}</td>
                <td className={tdCls} data-testid="version">{r.schedule_version === null ? '—' : `v${r.schedule_version}`}</td>
                <td className={tdCls}>
                  <Link className="text-teal-700 underline" aria-label={`History for ${r.teacher_name}`} to={`/logs?teacher_id=${r.teacher_id}&grade=${r.grade}&subject=${r.subject}`}>History</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
};
