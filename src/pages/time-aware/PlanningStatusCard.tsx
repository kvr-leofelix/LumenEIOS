import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Calendar } from 'lucide-react';
import { Card, CardBody, CardHeader } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { ProgressBar } from '../../components/common/ProgressBar';
import { workspaceProgress } from '../../lib/planning/progress';
import { usePlanning } from '../../lib/planning/usePlanning';

/** Compact planning summary for dashboards — the same progress model as the Day tracker and Daily Curriculum. */
export const PlanningStatusCard: React.FC<{ link: string; linkLabel: string }> = ({ link, linkLabel }) => {
  const p = usePlanning();
  const approved = p.workspace.plans.filter((x) => x.status === 'APPROVED');
  const drafts = p.workspace.plans.filter((x) => x.status === 'DRAFT').length;
  const progress = workspaceProgress(approved);
  const pending = progress.recoveryPending;
  return (
    <Card>
      <CardHeader
        title="Curriculum progress"
        subtitle={
          p.mode === 'loading'
            ? 'Loading the planning workspace…'
            : approved.length
              ? `${approved.length} approved plan(s) · Classes VI–VIII Mathematics & Science · ${p.workspace.config.year}`
              : 'No approved teaching plan yet — generate one in the Time-Aware Engine'
        }
        action={
          <Link to={link} className="text-xs font-semibold text-teal-700 hover:text-teal-600 inline-flex items-center gap-1 focus:outline-none focus-visible:underline">
            <Calendar className="w-3.5 h-3.5" /> {linkLabel} <ArrowRight className="w-3 h-3" />
          </Link>
        }
      />
      <CardBody className="space-y-4 text-xs">
        {(drafts > 0 || pending > 0 || p.mode === 'local' || p.mode === 'error') && (
          <div className="flex flex-wrap gap-2">
            {drafts > 0 && <Badge size="sm" variant="info">{drafts} draft schedule(s) awaiting approval</Badge>}
            {pending > 0 && (
              <Badge size="sm" variant="warning" dot>
                {pending} recovery proposal(s) awaiting approval
              </Badge>
            )}
            {p.mode === 'local' && <Badge size="sm" variant="outline">Browser-only records</Badge>}
            {p.mode === 'error' && <Badge size="sm" variant="danger">Planning workspace not loaded</Badge>}
          </div>
        )}
        {approved.length > 0 ? (
          <div data-testid="dashboard-progress-metrics" className="grid md:grid-cols-2 gap-4">
            <ProgressBar
              label="Subject teaching days completed"
              unit="days"
              total={progress.teachingDaysTotal}
              size="sm"
              segments={[
                { key: 'done', value: progress.teachingDaysCompleted, label: 'Completed', className: 'bg-navy-800' },
                { key: 'lost', value: progress.teachingDaysLost, label: 'All periods lost', className: 'bg-rose-400', striped: true },
              ]}
            />
            <ProgressBar
              label="Classroom periods taught"
              unit="periods"
              total={progress.classroomRequired}
              size="sm"
              segments={[{ key: 'done', value: progress.classroomTaught, label: 'Taught', className: 'bg-teal-600' }]}
            />
            <p className="md:col-span-2 text-[11px] text-content-secondary">
              Core remaining <b className="text-content-primary">{progress.coreRemaining}</b> · Non-Core remaining <b className="text-content-primary">{progress.nonCoreRemaining}</b> · Lost periods{' '}
              <b className="text-content-primary">{progress.lostPeriodsRecorded}</b>
              {progress.unaccountedLostPeriods ? ` (${progress.unaccountedLostPeriods} awaiting approved recovery)` : ''} · Unresolved shortfall <b className="text-content-primary">{progress.unresolvedShortfall}</b> period(s)
            </p>
          </div>
        ) : (
          p.mode !== 'loading' && <p className="text-content-secondary">Progress appears here once a teaching schedule is approved.</p>
        )}
        {progress.plans.length > 0 && (
          <ul className="divide-y divide-surface-border border border-surface-border rounded-lg">
            {progress.plans.map((pl) => (
              <li key={pl.planId} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                <span className="font-semibold text-navy-900">{pl.label}</span>
                <span className="text-content-secondary tabular-nums">
                  {pl.classroomTaught}/{pl.classroomRequired} periods · {pl.teachingDaysCompleted}/{pl.teachingDaysTotal} days · v{pl.version}
                  {pl.recoveryPending ? ' · recovery pending' : ''}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
};
