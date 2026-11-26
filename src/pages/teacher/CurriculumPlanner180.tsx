import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Badge } from '../../components/common/Badge';
import { pendingProposal, planLabel } from '../../lib/planning/execution';
import { usePlanning } from '../../lib/planning/usePlanning';
import { PageHeader, selectCls, StoreBanner } from '../time-aware/planningUi';
import { PlanDetail } from '../time-aware/PlanDetail';

/** Daily Curriculum (route kept at /teacher/curriculum-180 for link compatibility). */
export const CurriculumPlanner180: React.FC = () => {
  const p = usePlanning();
  const approved = p.workspace.plans.filter((pl) => pl.status === 'APPROVED');
  const drafts = p.workspace.plans.filter((pl) => pl.status === 'DRAFT');
  const [selected, setSelected] = useState('');
  const plan = approved.find((pl) => pl.id === selected) ?? approved[0];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Daily Curriculum"
        subtitle="Approved teaching schedule, daily execution and approved changes. Homework assigned is never counted as teaching completed, and nothing counts as mastered without assessment evidence."
        badge={<Badge variant="teal" size="sm">Classes VI–VIII · Mathematics & Science</Badge>}
        actions={
          <Link className="text-xs font-semibold text-teal-700 underline" to="/teacher/time-aware">
            Open Time-Aware Engine →
          </Link>
        }
      />
      <StoreBanner mode={p.mode} notice={p.notice} error={p.error} revision={p.revision} legacyPlans={p.legacyPlans} onDismiss={p.clearError} onRetry={p.reload} />
      {drafts.length > 0 && (
        <p className="text-xs text-content-secondary bg-surface-bg border border-surface-border rounded-lg px-3 py-2">
          {drafts.length} draft schedule(s) await Principal/Admin approval: {drafts.map(planLabel).join(', ')}.
        </p>
      )}
      {plan ? (
        <>
          <label className="flex items-center gap-2 text-xs">
            <span className="font-semibold">Teaching plan</span>
            <select aria-label="Teaching plan" className={selectCls} value={plan.id} onChange={(e) => setSelected(e.target.value)}>
              {approved.map((pl) => (
                <option key={pl.id} value={pl.id}>
                  {planLabel(pl)} · {pl.config.year}
                  {pendingProposal(pl) ? ' · proposal pending' : ''}
                </option>
              ))}
            </select>
          </label>
          <PlanDetail plan={plan} mode="teacher" />
        </>
      ) : (
        <p className="text-xs text-content-secondary bg-white border border-surface-border rounded-xl p-5">
          No approved teaching schedule yet. Generate a draft in the Time-Aware Engine; it appears here once a Principal or Admin approves it.
        </p>
      )}
    </div>
  );
};
