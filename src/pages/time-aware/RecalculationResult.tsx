import React from 'react';
import { Badge } from '../../components/common/Badge';
import { diffLessons, scheduledPeriods } from '../../lib/planning/recalc';
import type { Plan } from '../../lib/planning/execution';
import { currentVersion } from '../../lib/planning/execution';
import { tdCls, thCls } from './planningUi';

const MAX_ROWS = 40;

/**
 * The visible, persisted result of "Recalculate with current configuration": a NEW DRAFT built from the current academic calendar,
 * the persisted Core/Non-Core requirements and the teaching already done. It stays on screen (it is read from the stored draft)
 * until a Principal/Admin approves or rejects it; the approved schedule is untouched in the meantime.
 */
export const RecalculationResult: React.FC<{ draft: Plan; approved: Plan | undefined }> = ({ draft, approved }) => {
  const basis = draft.draft.basis;
  if (!basis) return null;
  const prevVersion = approved ? currentVersion(approved) : undefined;
  const previous = prevVersion?.lessons ?? [];
  const diff = diffLessons(previous, draft.draft.lessons);
  const changed = diff.filter((d) => d.changed);
  const m = draft.draft.metrics;
  const prevScheduled = previous.reduce((s, l) => s + scheduledPeriods(l), 0);
  const newScheduled = draft.draft.lessons.reduce((s, l) => s + scheduledPeriods(l), 0);
  const coreShort = m.core.unscheduledPeriods;
  const totalShort = m.unscheduledPeriods;
  return (
    <div className="rounded-xl border border-teal-300 bg-teal-50/40 p-4 space-y-3 text-xs" data-testid="recalc-result">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-bold text-navy-900">New schedule draft generated from the current academic calendar</h3>
        <Badge size="sm" variant="warning">Awaiting principal approval</Badge>
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        <div className="rounded-lg border border-surface-border bg-white p-3 space-y-0.5" data-testid="recalc-previous">
          <p className="font-semibold text-navy-900">Previous approved schedule {prevVersion ? `v${prevVersion.version}` : '(none)'}</p>
          {prevVersion ? (
            <p>Approved {prevVersion.approvedAt.slice(0, 10)} on its own calendar snapshot · {previous.length} topics · {prevScheduled} periods scheduled. It stays in force until the new draft is approved.</p>
          ) : (
            <p>No approved schedule yet.</p>
          )}
        </div>
        <div className="rounded-lg border border-surface-border bg-white p-3 space-y-0.5" data-testid="recalc-new">
          <p className="font-semibold text-navy-900">New draft · generated {basis.generatedAt.slice(0, 10)}</p>
          <p>
            Current calendar{basis.calendarVersion ? ` (version ${basis.calendarVersion})` : ''}: {basis.calendarDays} instructional days, {basis.daysLeft} left after {basis.planningDate}; {basis.periodsLeft} periods left, reserve {basis.reserveLeft}, capacity for untaught work {basis.capacityLeft}.
          </p>
          <p>{draft.draft.lessons.length} topics to schedule · {newScheduled} periods scheduled · {basis.doneTopics} Done topic(s) and {basis.taughtPeriods} taught period(s) kept as they are.</p>
        </div>
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        <p data-testid="recalc-remaining">
          <b>Remaining Core:</b> {basis.remainingCore} period(s) still to teach ({m.core.scheduledPeriods} scheduled, {coreShort} unscheduled) · <b>Remaining Non-Core:</b> {basis.remainingNonCore}
        </p>
        <p data-testid="recalc-shortfall" className={totalShort || coreShort ? 'text-rose-700 font-semibold' : 'text-teal-800'}>
          <b>Shortfall:</b>{' '}
          {totalShort || coreShort ? `${coreShort} Core period(s) and ${totalShort} period(s) in total cannot be scheduled before the end of the year. Core requirements are kept and flagged, not dropped.` : 'None. All remaining required periods fit in the time left.'}
        </p>
      </div>
      <p className="text-navy-900">
        <b>Principal/Admin approval is required.</b> Review and approve this draft in Curriculum Oversight; approving it supersedes the previous approved schedule, which stays in the plan history together with its teaching records.
      </p>
      {changed.length === 0 ? (
        <p className="text-content-secondary">The revised topic allocations are identical to the previous approved schedule.</p>
      ) : (
        <div className="overflow-x-auto border border-surface-border rounded-lg bg-white">
          <table className="w-full text-xs" aria-label="Changed topic allocations">
            <thead>
              <tr>
                {['Topic', 'Previous scheduled', 'Previous dates', 'Revised scheduled', 'Revised dates'].map((h) => (
                  <th key={h} className={thCls}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {changed.slice(0, MAX_ROWS).map((d) => (
                <tr key={d.nodeId} data-testid="recalc-diff-row">
                  <td className={tdCls}>{d.title}</td>
                  <td className={tdCls}>{d.previous} period(s)</td>
                  <td className={`${tdCls} text-content-muted`}>{d.previousRange}</td>
                  <td className={`${tdCls} font-semibold`}>{d.revised} period(s)</td>
                  <td className={tdCls}>{d.revisedRange}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-3 py-2 text-[11px] text-content-muted">
            {changed.length} topic(s) changed{changed.length > MAX_ROWS ? `, first ${MAX_ROWS} shown` : ''} · {diff.length - changed.length} unchanged.
          </p>
        </div>
      )}
    </div>
  );
};
