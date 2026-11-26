import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { GRADE_LABEL, PLANNING_GRADES, PLANNING_SUBJECTS } from '../../lib/planning/calendar';
import { approveDraft, currentVersion, pendingProposal, Plan, planLabel, rejectDraft } from '../../lib/planning/execution';
import { planProgress, workspaceProgress } from '../../lib/planning/progress';
import { usePlanning } from '../../lib/planning/usePlanning';
import { ConflictList, inputCls, PageHeader, ScheduleComparison, SectionCard, StoreBanner, tdCls, thCls } from '../time-aware/planningUi';
import { PlanDetail } from '../time-aware/PlanDetail';
import { PlanningTeacherTable } from '../../features/teacherPlan/PlanningTeacherTable';
import { RecentPlanEvents } from '../../features/teacherPlan/RecentPlanEvents';
import { WorkspaceProgressSummary } from '../time-aware/PlanningProgressPanel';

const DraftReview: React.FC<{ plan: Plan }> = ({ plan }) => {
  const p = usePlanning();
  const [note, setNote] = useState('');
  const replacing = p.workspace.plans.find((x) => x.status === 'APPROVED' && x.grade === plan.grade && x.subject === plan.subject && x.teacherId === plan.teacherId);
  const decide = (approve: boolean) =>
    p.commit('PLAN_REVIEW', `${approve ? 'Approved' : 'Rejected'} draft schedule for ${planLabel(plan)}`, (w) => ({
      ...w,
      plans: approve ? approveDraft(w.plans, plan.id, p.actor!, note) : rejectDraft(w.plans, plan.id, p.actor!, note),
    }));
  return (
    <div className="border border-sky-200 bg-sky-50/50 rounded-xl p-4 space-y-3 text-xs" data-testid="draft-review">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-bold text-navy-900">{planLabel(plan)} — draft schedule</h3>
        <Badge size="sm" variant="info">
          Awaiting approval
        </Badge>
        <span className="text-content-muted">
          by {plan.createdBy.name} · {plan.createdAt.slice(0, 10)} · {plan.datasetLabel}
        </span>
      </div>
      <p>
        {plan.draft.lessons.length} units · {plan.draft.metrics.requiredPeriods} periods required of {plan.draft.metrics.availablePeriods} available · {plan.draft.metrics.unscheduledPeriods} unscheduled
      </p>
      <ConflictList conflicts={plan.draft.conflicts} />
      <ScheduleComparison
        columns={[
          ...(replacing ? [{ label: `Current approved (${planLabel(replacing)} v${currentVersion(replacing)!.version})`, lessons: currentVersion(replacing)!.lessons }] : []),
          { label: 'Proposed draft', lessons: plan.draft.lessons, highlight: true },
        ]}
      />
      {replacing && <p className="text-amber-800">Approving replaces the current approved plan for this class and subject. The current plan, its execution records and history are preserved as superseded.</p>}
      {p.isReviewer ? (
        <div className="flex flex-wrap items-center gap-2">
          <input aria-label={`Plan review note ${plan.id}`} className={`${inputCls} max-w-sm`} placeholder="Note (required to reject)" value={note} onChange={(e) => setNote(e.target.value)} />
          <Button size="sm" variant="teal" onClick={() => decide(true)}>
            Approve teaching schedule
          </Button>
          <Button size="sm" variant="outline" onClick={() => decide(false)}>
            Reject draft
          </Button>
        </div>
      ) : (
        <p>Admin or Principal approval required.</p>
      )}
    </div>
  );
};

export const CurriculumOversight: React.FC = () => {
  const p = usePlanning();
  const plans = p.workspace.plans;
  const drafts = plans.filter((x) => x.status === 'DRAFT');
  const approved = plans.filter((x) => x.status === 'APPROVED');
  const [focus, setFocus] = useState('');
  const focused = approved.find((x) => x.id === focus) ?? approved.find((x) => pendingProposal(x)) ?? approved[0];

  if (!p.isReviewer) return <PageHeader title="Curriculum Oversight" subtitle="Requires Admin or Principal access." />;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Planning Oversight"
        subtitle="Class and subject progress, draft schedules and recovery proposals for Mathematics and Science, Classes VI–VIII. Nothing changes an approved plan without your approval."
        actions={
          <>
            <Link className="text-xs font-semibold text-teal-700 underline" to={p.role === 'principal' ? '/principal/academic-config' : '/admin/academic-config'}>
              Academic Configuration
            </Link>
            <Link className="text-xs font-semibold text-teal-700 underline" to="/teacher/time-aware">
              Time-Aware Engine
            </Link>
          </>
        }
      />
      <StoreBanner mode={p.mode} notice={p.notice} error={p.error} revision={p.revision} legacyPlans={p.legacyPlans} onDismiss={p.clearError} onRetry={p.reload} />

      <PlanningTeacherTable />

      <WorkspaceProgressSummary progress={workspaceProgress(approved)} />

      <SectionCard title="Progress by class and subject" subtitle="Approved plans only — teaching days kept separate from classroom periods">
        <div className="overflow-x-auto border border-surface-border rounded-xl">
          <table className="w-full" aria-label="Class and subject progress">
            <thead>
              <tr>
                {['Class', 'Subject', 'Plan', 'Teaching days', 'Classroom %', 'Core / Non-Core left', 'Lost periods', 'Pending'].map((h) => (
                  <th key={h} className={thCls}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {PLANNING_GRADES.flatMap((g) =>
                PLANNING_SUBJECTS.map((s) => {
                  const pl = approved.find((x) => x.grade === g && x.subject === s);
                  const v = pl && currentVersion(pl);
                  const prog = pl ? planProgress(pl) : null;
                  const draftCount = drafts.filter((x) => x.grade === g && x.subject === s).length;
                  return (
                    <tr key={`${g}-${s}`} className={pl && pl.id === focused?.id ? 'bg-teal-50/40' : ''}>
                      <td className={tdCls}>Class {GRADE_LABEL[g]}</td>
                      <td className={tdCls}>{s}</td>
                      <td className={tdCls}>
                        {pl ? (
                          <button className="text-teal-700 underline" onClick={() => setFocus(pl.id)}>
                            v{v!.version} · {pl.config.year}
                          </button>
                        ) : (
                          <span className="text-content-muted">No approved plan</span>
                        )}
                      </td>
                      <td className={tdCls}>{prog ? `${prog.teachingDaysCompleted} / ${prog.teachingDaysTotal}` : '—'}</td>
                      <td className={tdCls}>{prog ? `${prog.classroomPct}% (${prog.classroomTaught}/${prog.classroomRequired})` : '—'}</td>
                      <td className={tdCls}>{prog ? `${prog.coreRemaining} / ${prog.nonCoreRemaining}` : '—'}</td>
                      <td className={tdCls}>{prog ? `${prog.lostPeriodsRecorded}${prog.unaccountedLostPeriods ? ` (${prog.unaccountedLostPeriods} unaccounted)` : ''}` : '—'}</td>
                      <td className={tdCls}>
                        {pl && pendingProposal(pl) && (
                          <Badge size="sm" variant="warning">
                            Recovery proposal
                          </Badge>
                        )}{' '}
                        {draftCount > 0 && (
                          <Badge size="sm" variant="info">
                            {draftCount} draft
                          </Badge>
                        )}
                      </td>
                    </tr>
                  );
                }),
              )}
            </tbody>
          </table>
        </div>
      </SectionCard>

      {drafts.length > 0 && (
        <SectionCard title="Draft schedules awaiting approval">
          {drafts.map((d) => (
            <DraftReview key={d.id} plan={d} />
          ))}
        </SectionCard>
      )}

      {focused ? <PlanDetail plan={focused} mode="review" /> : <p className="text-xs text-content-secondary bg-white border border-surface-border rounded-xl p-5">No approved teaching plans yet.</p>}

      <SectionCard title="Planning audit trail" subtitle="Newest first · the same records as Central Logs">
        <RecentPlanEvents limit={10} />
      </SectionCard>
    </div>
  );
};
