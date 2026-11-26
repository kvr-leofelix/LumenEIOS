import React from 'react';
import { AlertTriangle, CheckCircle2, Clock, Hourglass } from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import { ProgressBar } from '../../components/common/ProgressBar';
import type { PlanProgress, WorkspaceProgress } from '../../lib/planning/progress';
import { SectionCard } from './planningUi';

type Tone = 'navy' | 'teal' | 'amber' | 'rose';

const bannerCls: Record<Tone, string> = {
  navy: 'bg-navy-50 border-navy-100 text-navy-900',
  teal: 'bg-teal-50 border-teal-100 text-teal-700',
  amber: 'bg-amber-50 border-amber-200 text-amber-900',
  rose: 'bg-rose-50 border-rose-200 text-rose-900',
};

function statusOf(p: { recoveryPending: boolean | number; unresolvedShortfall: number; unaccountedLostPeriods: number; classroomRequired: number; classroomTaught: number }) {
  const pending = typeof p.recoveryPending === 'boolean' ? (p.recoveryPending ? 1 : 0) : p.recoveryPending;
  if (pending > 0) {
    return { tone: 'amber' as Tone, icon: <Hourglass className="w-4 h-4 shrink-0" />, title: `${pending === 1 ? 'A recovery proposal is' : `${pending} recovery proposals are`} awaiting Principal/Admin approval`, detail: 'Proposed recovery is shown separately and is not counted as approved progress.' };
  }
  if (p.unresolvedShortfall > 0 || p.unaccountedLostPeriods > 0) {
    return {
      tone: 'rose' as Tone,
      icon: <AlertTriangle className="w-4 h-4 shrink-0" />,
      title: 'Instructional shortfall needs attention',
      detail: [p.unaccountedLostPeriods ? `${p.unaccountedLostPeriods} lost period(s) have no approved recovery` : '', p.unresolvedShortfall ? `${p.unresolvedShortfall} required classroom period(s) have no slot in the approved schedule` : ''].filter(Boolean).join(' · ') + '.',
    };
  }
  if (p.classroomRequired > 0 && p.classroomTaught >= p.classroomRequired) {
    return { tone: 'teal' as Tone, icon: <CheckCircle2 className="w-4 h-4 shrink-0" />, title: 'All required classroom periods are taught', detail: 'Independent learning remains tracked separately and is not counted as classroom teaching.' };
  }
  return { tone: 'navy' as Tone, icon: <Clock className="w-4 h-4 shrink-0" />, title: 'Instruction in progress', detail: 'Teaching days and classroom periods are measured separately.' };
}

const StatusBanner: React.FC<{ status: ReturnType<typeof statusOf>; testId: string }> = ({ status, testId }) => (
  <div className={`flex items-start gap-2.5 px-3 py-2.5 rounded-xl border text-xs ${bannerCls[status.tone]}`} data-testid={testId} role="status">
    {status.icon}
    <div>
      <p className="font-semibold">{status.title}</p>
      <p className="text-[11px] opacity-90 mt-0.5">{status.detail}</p>
    </div>
  </div>
);

/** Compact labelled figure used inside progress blocks. */
const Figure: React.FC<{ label: string; value: React.ReactNode; hint?: React.ReactNode; tone?: Tone | 'muted' }> = ({ label, value, hint, tone = 'navy' }) => {
  const color = { navy: 'text-navy-900', teal: 'text-teal-700', amber: 'text-amber-700', rose: 'text-rose-700', muted: 'text-content-secondary' }[tone];
  return (
    <div className="min-w-0">
      <dt className="text-[11px] text-content-secondary leading-tight">{label}</dt>
      <dd className={`text-lg font-bold tabular-nums leading-snug ${color}`}>{value}</dd>
      {hint && <dd className="text-[11px] text-content-muted leading-tight">{hint}</dd>}
    </div>
  );
};

const Block: React.FC<{ title: string; badge?: React.ReactNode; children: React.ReactNode; testId?: string }> = ({ title, badge, children, testId }) => (
  <div className="p-4 rounded-xl border border-surface-border bg-white space-y-3" data-testid={testId}>
    <div className="flex items-center justify-between gap-2">
      <h3 className="text-[11px] font-semibold uppercase tracking-wide text-content-secondary">{title}</h3>
      {badge}
    </div>
    {children}
  </div>
);

/** Full progress dashboard for one approved plan (Day tracker, Daily Curriculum, Curriculum Oversight). */
export const PlanningProgressPanel: React.FC<{ progress: PlanProgress; title?: string }> = ({ progress: p, title }) => {
  const status = statusOf(p);
  return (
    <SectionCard
      title={title ?? 'Instructional progress'}
      subtitle={`${p.label} · approved schedule v${p.version} · calculated from approved schedules and execution records`}
      action={p.recoveryPending ? <Badge size="sm" variant="warning" dot>Recovery pending</Badge> : undefined}
    >
      <StatusBanner status={status} testId="progress-status" />

      <div className="grid lg:grid-cols-2 gap-4" data-testid="progress-metrics">
        <Block title="Teaching days">
          <ProgressBar
            label="Teaching days completed"
            unit="days"
            total={p.teachingDaysTotal}
            testId="teaching-day-progress"
            segments={[
              { key: 'done', value: p.teachingDaysCompleted, label: 'Completed', className: 'bg-navy-800' },
              { key: 'lost', value: p.teachingDaysLost, label: 'All periods lost', className: 'bg-rose-400', striped: true },
            ]}
          />
          <dl className="grid grid-cols-3 gap-3">
            <Figure label="Completed" value={p.teachingDaysCompleted} hint="every period taught" />
            <Figure label="Remaining" value={p.teachingDaysRemaining} tone="teal" hint="days with untaught periods" />
            <Figure label="Scheduled" value={p.teachingDaysTotal} tone="muted" hint={`${p.subject} teaching days`} />
          </dl>
        </Block>
        <Block title="Classroom periods">
          <ProgressBar
            label="Classroom instruction taught"
            unit="periods"
            total={p.classroomRequired}
            doneKeys={['core', 'non']}
            testId="classroom-progress"
            segments={[
              { key: 'core', value: p.coreTaught, label: 'Core taught', className: 'bg-teal-600' },
              { key: 'non', value: p.nonCoreTaught, label: 'Non-Core taught', className: 'bg-amber-500' },
            ]}
          />
          <dl className="grid grid-cols-3 gap-3">
            <Figure label="Taught" value={`${p.classroomTaught}`} hint={`of ${p.classroomRequired} required`} />
            <Figure label="Remaining" value={p.classroomRemaining} tone="teal" hint="classroom periods" />
            <Figure label="Independent learning" value={p.independentPeriods} tone="amber" hint="not classroom teaching" />
          </dl>
        </Block>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        <Block title="Core requirement">
          <dl className="grid grid-cols-2 gap-3">
            <Figure label="Remaining Core" value={p.coreRemaining} />
            <Figure label="Taught / required" value={`${p.coreTaught} / ${p.coreRequired}`} tone="muted" />
          </dl>
        </Block>
        <Block title="Non-Core requirement">
          <dl className="grid grid-cols-2 gap-3">
            <Figure label="Remaining in class" value={p.nonCoreRemaining} tone="amber" />
            <Figure label="Taught / required" value={`${p.nonCoreTaught} / ${p.nonCoreRequired}`} tone="muted" hint={p.independentPeriods ? `${p.independentPeriods} as independent learning` : undefined} />
          </dl>
        </Block>
        <Block title="Unresolved shortfall" badge={p.unresolvedShortfall ? <Badge size="sm" variant="danger">Action needed</Badge> : <Badge size="sm" variant="success">None</Badge>}>
          <dl className="grid grid-cols-2 gap-3">
            <Figure label="Periods without a slot" value={p.unresolvedShortfall} tone={p.unresolvedShortfall ? 'rose' : 'navy'} />
            <Figure label="of which Core" value={p.coreUnscheduled} tone={p.coreUnscheduled ? 'rose' : 'muted'} />
          </dl>
          {p.unitsWithoutRequirement > 0 && <p className="text-[11px] text-rose-700">{p.unitsWithoutRequirement} topic(s) have no approved requirement and are not counted.</p>}
        </Block>
      </div>

      <Block title="Lost periods and recovery" testId="recovery-progress" badge={p.recoveryPending ? <Badge size="sm" variant="warning">Proposal pending</Badge> : undefined}>
        <dl className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <Figure label="Lost periods recorded" value={p.lostPeriodsRecorded} tone={p.lostPeriodsRecorded ? 'rose' : 'navy'} hint={`${p.lostCorePeriods} Core · ${p.lostNonCorePeriods} Non-Core`} />
          <Figure label="Lost, awaiting approval" value={p.unaccountedLostPeriods} tone={p.unaccountedLostPeriods ? 'amber' : 'muted'} hint={`${p.lostPeriodsApplied} in approved schedule`} />
          <Figure label="Core recovered (approved)" value={p.coreRecovered} tone="teal" hint={`of ${p.coreLostApplied} lost Core applied`} />
          <Figure label="Core awaiting recovery" value={p.coreAwaitingRecovery} tone={p.coreAwaitingRecovery ? 'rose' : 'muted'} hint="approved schedule" />
          <Figure label="Approved revisions" value={p.recoveryRevisions} tone="muted" hint={p.rejectedProposals ? `${p.rejectedProposals} rejected (kept)` : 'after original v1'} />
          <Figure label="Topics taught" value={`${p.unitsTaught} / ${p.unitsTotal}`} tone="muted" hint={`${p.unitsIncomplete} incomplete · ${p.homeworkOpen} homework open`} />
        </dl>
        {p.proposed && (
          <p className="text-[11px] rounded-lg border border-dashed border-amber-300 bg-amber-50/60 px-3 py-2 text-amber-900" data-testid="proposed-recovery">
            <b>Proposed, not yet approved:</b> {p.proposed.coreRecovered} Core period(s) recovered · {p.proposed.nonCoreToIndependent} Non-Core period(s) to independent learning · {p.proposed.coreUnresolved} Core period(s) still unresolved. These figures are not included above until approval.
          </p>
        )}
      </Block>
    </SectionCard>
  );
};

/** Compact multi-plan progress for dashboards and oversight. */
export const WorkspaceProgressSummary: React.FC<{ progress: WorkspaceProgress; emptyHint?: string }> = ({ progress: w, emptyHint }) => {
  if (!w.plans.length) {
    return (
      <SectionCard title="Instructional progress">
        <p className="text-content-secondary">{emptyHint ?? 'No approved teaching plans yet. Generate a schedule in the Time-Aware Engine and have it approved in Curriculum Oversight.'}</p>
      </SectionCard>
    );
  }
  return (
    <SectionCard title="Instructional progress" subtitle={`${w.plans.length} approved plan(s) · teaching days and classroom periods are measured separately`}>
      <StatusBanner status={statusOf(w)} testId="workspace-progress-status" />
      <div className="grid lg:grid-cols-2 gap-4" data-testid="workspace-progress-metrics">
        <ProgressBar
          label="Subject teaching days completed (all plans)"
          unit="days"
          total={w.teachingDaysTotal}
          segments={[
            { key: 'done', value: w.teachingDaysCompleted, label: 'Completed', className: 'bg-navy-800' },
            { key: 'lost', value: w.teachingDaysLost, label: 'All periods lost', className: 'bg-rose-400', striped: true },
          ]}
        />
        <ProgressBar
          label="Classroom periods taught (all plans)"
          unit="periods"
          total={w.classroomRequired}
          segments={[{ key: 'done', value: w.classroomTaught, label: 'Taught', className: 'bg-teal-600' }]}
        />
      </div>
      <dl className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <Figure label="Teaching days remaining" value={w.teachingDaysRemaining} tone="teal" />
        <Figure label="Core remaining" value={w.coreRemaining} />
        <Figure label="Non-Core remaining" value={w.nonCoreRemaining} tone="amber" hint={w.independentPeriods ? `${w.independentPeriods} independent` : undefined} />
        <Figure label="Lost periods" value={w.lostPeriodsRecorded} tone={w.lostPeriodsRecorded ? 'rose' : 'muted'} hint={w.unaccountedLostPeriods ? `${w.unaccountedLostPeriods} awaiting approval` : undefined} />
        <Figure label="Core recovered" value={w.coreRecovered} tone="teal" hint={`${w.coreAwaitingRecovery} awaiting`} />
        <Figure label="Unresolved shortfall" value={w.unresolvedShortfall} tone={w.unresolvedShortfall ? 'rose' : 'muted'} hint="periods without a slot" />
      </dl>
    </SectionCard>
  );
};
