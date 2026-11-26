import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Cpu, Send, RefreshCw, Pencil } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { AcademicConfig, GRADE_LABEL, PLANNING_GRADES, PLANNING_SUBJECTS, PlanningSubject, summarizeCalendar, validateConfig } from '../../lib/planning/calendar';
import { generateSchedule, lessonEnd, RecalcBasis, requirementSnapshot } from '../../lib/planning/engine';
import { configChangedSinceApproval, createDraft, currentVersion, pendingProposal, Plan, planLabel, recalculationBlocked } from '../../lib/planning/execution';
import { calendarCapacity, remainingScheduleInput, sameSlots, scheduleFingerprint } from '../../lib/planning/recalc';
import { effectiveAsOf, PACE_LABEL, paceReport } from '../../lib/planning/pace';
import { planProgress } from '../../lib/planning/progress';
import { defaultDatasetFor, syllabusFor } from '../../lib/planning/syllabus';
import { usePlanning } from '../../lib/planning/usePlanning';
import { ConflictList, dateRange, labelCls, PageHeader, SectionCard, selectCls, Stat, StoreBanner, tdCls, thCls } from './planningUi';
import { RecalculationResult } from './RecalculationResult';
import { SyllabusPanel } from './SyllabusPanel';
import { RelationshipsPanel } from './RelationshipsPanel';
import { DayTracker } from './DayTracker';
import { LostPeriodRecorder } from './LostPeriodRecorder';
import { TeacherLostDays } from '../../features/teacherPlan/TeacherLostDays';
import { PlanCapacitySummary } from '../../features/teacherPlan/PlanCapacitySummary';
import { classificationsFromRequirements, invalidateRequirements, relationshipsFromItems, useStoreVersion } from '../../features/teacherPlan/requirementsStore';
import { useRemote } from '../../features/teacherPlan/useRemote';
import { describeError, teacherPlanApi, type PlanTopicRow } from '../../lib/teacherPlanApi';

type Tab = 'planner' | 'tracker' | 'requirements' | 'relationships';

const PlanStatusBadge: React.FC<{ plan: Plan }> = ({ plan }) => {
  const variant = { DRAFT: 'info', APPROVED: 'success', SUPERSEDED: 'default', REJECTED: 'danger' }[plan.status] as 'info' | 'success' | 'default' | 'danger';
  return (
    <Badge size="sm" variant={variant}>
      {plan.status === 'DRAFT' ? 'Draft — awaiting approval' : plan.status.toLowerCase()}
    </Badge>
  );
};

const nodeIdOf = (topicKey: string) => (topicKey.startsWith('XW-') ? `CH-${topicKey.slice(3)}` : topicKey);

const CLASS_STYLE: Record<string, { label: string; cls: string }> = {
  core: { label: 'Core', cls: 'bg-indigo-100 text-indigo-900' },
  non_core: { label: 'Non-Core', cls: 'bg-teal-100 text-teal-900' },
  mixed: { label: 'Mixed', cls: 'bg-indigo-100 text-indigo-900 ring-1 ring-teal-400' },
};
const ClassPill: React.FC<{ value: string | null | undefined }> = ({ value }) => {
  const st = value ? CLASS_STYLE[value] : undefined;
  return st ? <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-semibold ${st.cls}`}>{st.label}</span> : <span className="text-[11px] font-semibold text-amber-700">Configuration required</span>;
};

const requiredText = (t: { core_periods: number; non_core_periods: number }) =>
  t.core_periods && t.non_core_periods ? `${t.core_periods} Core + ${t.non_core_periods} Non-Core` : t.core_periods ? `${t.core_periods} Core` : t.non_core_periods ? `${t.non_core_periods} Non-Core` : '—';

/** Status colours: Done green, In progress blue, Not started grey, Missed red, Needs attention orange, Independent learning teal. */
function topicStatus(t: PlanTopicRow | undefined, lesson: { slots: { date: string }[]; unscheduledPeriods?: number } | undefined, today: string | null): { label: string; color: string } {
  if (!t) return { label: 'Not started', color: '#9CA3AF' };
  const taught = t.taught_periods ?? 0;
  if (t.coverage === 'done') return { label: 'Done', color: '#16A34A' };
  if (taught > 0 || t.coverage === 'in_progress') return { label: 'In progress', color: '#2563EB' };
  if ((lesson?.unscheduledPeriods ?? 0) > 0) return { label: 'Needs attention', color: '#F59E0B' };
  const last = lesson?.slots.length ? lesson.slots[lesson.slots.length - 1].date : null;
  if (today && last && last < today) return { label: 'Missed', color: '#DC2626' };
  if (t.core_periods + t.non_core_periods - t.independent_periods <= 0 && t.non_core_periods > 0) return { label: 'Independent learning', color: '#0D9488' };
  return { label: 'Not started', color: '#9CA3AF' };
}

export const TimeAwareEngine: React.FC = () => {
  const p = usePlanning();
  const { workspace } = p;
  const [tab, setTab] = useState<Tab>('planner');
  // The selected class and subject live in the URL (?class=8&subject=Science), so a refresh returns to the same plan.
  const [search, setSearch] = useSearchParams();
  const grade: number = (PLANNING_GRADES as readonly number[]).includes(Number(search.get('class'))) ? Number(search.get('class')) : 7;
  const subject = (PLANNING_SUBJECTS as readonly string[]).includes(search.get('subject') ?? '') ? (search.get('subject') as PlanningSubject) : 'Mathematics';
  const patchSearch = (changes: Record<string, string | null>) =>
    setSearch((prev) => {
      const next = new URLSearchParams(prev);
      for (const [k, v] of Object.entries(changes)) (v === null ? next.delete(k) : next.set(k, v));
      return next;
    }, { replace: true });
  const setGrade = (g: number) => patchSearch({ class: String(g) });
  const setSubject = (sub: PlanningSubject) => patchSearch({ subject: sub });
  // null = follow the default dataset for the chosen class and subject (the same one Course Curriculum shows).
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [recalcBusy, setRecalcBusy] = useState(false);
  const [recalcMsg, setRecalcMsg] = useState<{ tone: 'ok' | 'info' | 'err'; text: string } | null>(null);

  const dataset = defaultDatasetFor(p.datasets, grade, subject);
  const view = useMemo(() => syllabusFor(dataset, grade, subject), [dataset, grade, subject]);
  const configErrors = validateConfig(workspace.config);
  const calendar = configErrors.length ? null : summarizeCalendar(workspace.config);
  const referenceDate = effectiveAsOf(workspace);
  const calendarDay = calendar?.planningDates.filter((d) => d <= referenceDate).length ?? 0;
  const daysLeft = calendar?.planningDates.filter((d) => d > referenceDate).length ?? 0;
  const storeVersion = useStoreVersion();
  const capacityPlan = useRemote(() => (p.teacherId ? teacherPlanApi.plan(p.teacherId, grade, subject) : Promise.resolve(null)), [p.teacherId, grade, subject, storeVersion]);
  // What still has to be scheduled: Done topics get nothing, a partly taught topic only its remaining periods.
  const planInput = useMemo(() => remainingScheduleInput(view.units, p.ctx, capacityPlan.data?.topics), [view.units, p.ctx, capacityPlan.data]);
  const result = useMemo(
    () => (configErrors.length ? null : generateSchedule({ dataset, units: planInput.units, grade, subject, config: workspace.config, after: effectiveAsOf(workspace) }, planInput.ctx)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [dataset, planInput, grade, subject, workspace.config, workspace.asOf, configErrors.length],
  );
  const plans = workspace.plans.filter((pl) => pl.grade === grade && pl.subject === subject);
  const approved = plans.find((pl) => pl.status === 'APPROVED');
  const pace = approved ? paceReport(approved, effectiveAsOf(workspace)) : null;
  const completion = approved ? planProgress(approved) : null;
  const snapshotDiffers = !!approved && configChangedSinceApproval(approved, workspace.config);
  const approvedVersionNo = approved ? approved.versions[approved.versions.length - 1]?.version : undefined;
  const requirementGaps = pace?.topicsWithoutRequirement ?? result?.metrics.pending.units ?? 0;
  const canSubmit = !!result && !!view.units.length && !result.conflicts.some((c) => c.code === 'REQUIREMENT_MISSING' || c.code === 'PREREQUISITE_ORDER') && p.mode !== 'loading';

  // A Principal/Admin has no plan of their own: the page needs a teacher context, exactly like Course Curriculum (?teacher=<id>).
  const teachersForCombo = useRemote(() => (p.isReviewer ? teacherPlanApi.planningOversight({ grade, subject }) : Promise.resolve({ rows: [] })), [p.isReviewer, grade, subject]);
  const comboTeachers = useMemo(() => (teachersForCombo.data?.rows ?? []).map((r) => ({ id: r.teacher_id, name: r.teacher_name })), [teachersForCombo.data]);
  useEffect(() => {
    if (!p.isReviewer || teachersForCombo.loading) return;
    if (!comboTeachers.some((t) => t.id === p.teacherId)) {
      patchSearch({ teacher: comboTeachers.length ? comboTeachers[0].id : null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.isReviewer, teachersForCombo.loading, comboTeachers, p.teacherId]);
  const needsTeacher = p.isReviewer && !p.teacherId;
  // A teacher opening a class/subject for the first time gets their own persisted copy of the deterministic defaults (as Course Curriculum does).
  const initialised = useRef('');
  useEffect(() => {
    const key = `${p.teacherId}|${grade}|${subject}`;
    const covered = view.units.filter((u) => p.ctx.classifications[u.id]).length;
    if (p.ownsPlan && view.units.length > 0 && covered < view.units.length && initialised.current !== key) {
      initialised.current = key;
      teacherPlanApi.initialize(p.teacherId, grade, subject).then(() => invalidateRequirements()).catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.ownsPlan, p.teacherId, grade, subject, view.units, p.ctx.classifications]);

  if (!['admin', 'principal', 'teacher'].includes(p.role)) return <PageHeader title="Time-Aware Engine" subtitle="Curriculum planning requires school staff access." />;

  const submitDraft = async () => {
    if (!result || !p.actor) return;
    setBusy(true);
    setMessage('');
    const draft = createDraft({
      grade,
      subject,
      datasetId: dataset.id,
      datasetLabel: dataset.label,
      datasetKind: dataset.kind,
      createdBy: p.actor,
      config: workspace.config,
      estimates: requirementSnapshot(result.lessons),
      draft: result,
    });
    const res = await p.commit('PLAN_DRAFT', `Draft schedule generated for ${planLabel(draft)} (${result.lessons.length} units)`, (w) => ({ ...w, plans: [draft, ...w.plans] }));
    setBusy(false);
    setMessage(res.ok ? `Draft saved for ${planLabel(draft)}. It does not replace any approved schedule until an Admin or Principal approves it in Curriculum Oversight.` : `Draft not saved: ${res.error}`);
  };

  /**
   * "Recalculate with current configuration": builds a NEW DRAFT from the latest saved calendar, daily subject periods, persisted
   * Core/Non-Core requirements and the teaching already recorded (all re-read from the backend now, never from a cached copy).
   * The approved schedule is untouched until a Principal/Admin approves the draft. Every outcome is shown, including failures.
   */
  const recalculateDraft = async () => {
    if (!approved || !p.actor || !p.teacherId) return;
    setRecalcBusy(true);
    setRecalcMsg(null);
    try {
      const [cal, req, rel, fresh] = await Promise.all([
        teacherPlanApi.calendar(),
        teacherPlanApi.requirements(p.teacherId),
        teacherPlanApi.relationships(p.teacherId),
        teacherPlanApi.plan(p.teacherId, grade, subject),
      ]);
      const config = cal.config as unknown as AcademicConfig;
      const problems = validateConfig(config);
      if (problems.length) throw new Error(`The saved Academic Configuration is not valid: ${problems[0]}`);
      const after = effectiveAsOf(workspace);
      const input = remainingScheduleInput(view.units, { datasets: p.datasets, classifications: classificationsFromRequirements(req.items, p.teacherId), relationships: relationshipsFromItems(rel.items, p.teacherId) }, fresh.topics);
      const next = generateSchedule({ dataset, units: input.units, grade, subject, config, after }, input.ctx);
      const fp = scheduleFingerprint(config, after, next.lessons);
      const existing = plans.find((x) => x.status === 'DRAFT' && x.draft.basis?.fingerprint === fp);
      if (existing) {
        setRecalcMsg({ tone: 'info', text: `Nothing new to generate: a draft for exactly this calendar, these requirements and this teaching record was already generated on ${existing.createdAt.slice(0, 10)} and is awaiting principal approval. No duplicate draft was created.` });
        return;
      }
      const current = currentVersion(approved);
      if (current && sameSlots(current.lessons, next.lessons, input.doneIds)) {
        setRecalcMsg({ tone: 'info', text: 'Nothing changed: the approved schedule already matches the current academic calendar, requirements and teaching record, so no new draft was generated.' });
        return;
      }
      const open = fresh.topics.filter((t) => t.coverage !== 'done');
      const cap = calendarCapacity(config, subject, after);
      const basis: RecalcBasis = {
        kind: 'RECALCULATION',
        fromPlanId: approved.id,
        fromVersion: current?.version ?? 1,
        calendarVersion: cal.version,
        planningDate: after,
        calendarDays: cap.calendarDays,
        daysLeft: cap.daysLeft,
        periodsLeft: cap.periodsLeft,
        reserveLeft: cap.reserveLeft,
        capacityLeft: cap.capacityLeft,
        remainingCore: open.reduce((n, t: PlanTopicRow) => n + (t.remaining_core ?? t.core_periods), 0),
        remainingNonCore: open.reduce((n, t: PlanTopicRow) => n + (t.remaining_non_core ?? t.non_core_periods), 0),
        doneTopics: fresh.topics.length - open.length,
        taughtPeriods: fresh.topics.reduce((n, t) => n + (t.taught_periods ?? 0), 0),
        fingerprint: fp,
        generatedAt: new Date().toISOString(),
      };
      const draft = createDraft({
        grade,
        subject,
        datasetId: dataset.id,
        datasetLabel: dataset.label,
        datasetKind: dataset.kind,
        createdBy: p.actor,
        config,
        estimates: requirementSnapshot(next.lessons),
        draft: { ...next, basis },
      });
      const res = await p.commit('PLAN_DRAFT', `Recalculated draft schedule generated for ${planLabel(draft)} (${next.lessons.length} topics, calendar version ${cal.version})`, (w) => ({ ...w, plans: [draft, ...w.plans] }));
      if (!res.ok) throw new Error(res.error);
      setRecalcMsg({ tone: 'ok', text: 'New schedule generated using the updated academic calendar. Awaiting principal approval.' });
    } catch (e) {
      setRecalcMsg({ tone: 'err', text: `Recalculation failed: ${describeError(e).message}` });
    } finally {
      setRecalcBusy(false);
    }
  };

  // Requirements table: persisted classification and periods (required), the schedule's placed periods (scheduled) and recorded teaching (taught).
  const scheduleLessons = (approved ? currentVersion(approved)?.lessons : undefined) ?? result?.lessons ?? [];
  const lessonOf = new Map(scheduleLessons.map((l) => [l.nodeId, l]));
  const rowOf = new Map((capacityPlan.data?.topics ?? []).map((t) => [nodeIdOf(t.topic_key), t]));
  const draftWithBasis = [...plans].reverse().find((x) => x.status === 'DRAFT' && x.draft.basis);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Time-Aware Engine"
        subtitle="Plan the classroom periods still needed across the teaching days left. Scheduled periods count as taught only after classroom execution is recorded."
        badge={<Badge variant="teal" size="sm">Classes VI–VIII · Mathematics & Science</Badge>}
        actions={
          <>
            {p.isReviewer && (
              <Link className="text-xs font-semibold text-teal-700 underline" to={p.role === 'principal' ? '/principal/academic-config' : '/admin/academic-config'}>
                Academic Configuration
              </Link>
            )}
            <Link className="text-xs font-semibold text-teal-700 underline" to={p.isTeacher ? '/teacher/curriculum-180' : '/principal/curriculum'}>
              {p.isTeacher ? 'Daily Curriculum →' : 'Curriculum Oversight →'}
            </Link>
          </>
        }
      />
      <StoreBanner mode={p.mode} notice={p.notice} error={p.error} revision={p.revision} legacyPlans={p.legacyPlans} onDismiss={p.clearError} onRetry={p.reload} />

      <div className="bg-white p-4 rounded-xl border border-surface-border shadow-subtle flex flex-wrap items-end gap-4 text-xs">
        <label>
          <span className={labelCls}>Class</span>
          <select aria-label="Class" className={selectCls} value={grade} onChange={(e) => setGrade(Number(e.target.value))}>
            {PLANNING_GRADES.map((g) => (
              <option key={g} value={g}>
                Class {GRADE_LABEL[g]}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className={labelCls}>Subject</span>
          <select aria-label="Subject" className={selectCls} value={subject} onChange={(e) => setSubject(e.target.value as PlanningSubject)}>
            {PLANNING_SUBJECTS.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        {p.isReviewer && (
          <label>
            <span className={labelCls}>Teacher</span>
            <select aria-label="Teacher" className={selectCls} value={p.teacherId} onChange={(e) => patchSearch({ teacher: e.target.value })} disabled={!comboTeachers.length}>
              {!comboTeachers.length && <option value="">No teacher has a plan for this class and subject</option>}
              {comboTeachers.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </label>
        )}
        <div className="flex flex-wrap gap-1 lg:ml-auto p-1 rounded-lg bg-surface-bg border border-surface-border" role="tablist" aria-label="Time-Aware Engine sections">
          {(
            [
              ['planner', 'Schedule planner'],
              ['tracker', 'Day tracker'],
              ['requirements', 'Requirements'],
              ['relationships', 'Relationships'],
            ] as [Tab, string][]
          ).map(([k, label]) => (
            <button key={k} role="tab" aria-selected={tab === k} className={`px-3 py-1.5 rounded-md font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 ${tab === k ? 'bg-white text-navy-900 shadow-subtle' : 'text-content-secondary hover:text-content-primary'}`} onClick={() => setTab(k)}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {needsTeacher && (
        <div className="bg-white p-4 rounded-xl border border-surface-border text-xs text-content-secondary" data-testid="select-teacher-notice">
          {teachersForCombo.loading ? 'Loading teachers…' : 'No teacher has a plan for this class and subject yet, so there are no requirements to show.'}
        </div>
      )}
      {capacityPlan.data && !needsTeacher && (
        <SectionCard title={`Current academic calendar${p.calendarVersion ? ` (version ${p.calendarVersion})` : ''}: capacity and remaining syllabus`} subtitle="Uses the school's current calendar. Persisted required, taught and remaining periods for this teacher's plan.">
          <PlanCapacitySummary plan={capacityPlan.data} />
        </SectionCard>
      )}

      {p.isTeacher && <TeacherLostDays grade={grade} subject={subject} calendarVersion={p.calendarVersion} />}

      {tab === 'requirements' && <SyllabusPanel dataset={dataset} grade={grade} subject={subject} />}
      {tab === 'relationships' && <RelationshipsPanel grade={grade} />}
      {tab === 'tracker' && <DayTracker grade={grade} subject={subject} />}

      {tab === 'planner' && !needsTeacher && (
        <>
          {configErrors.length > 0 ? (
            <SectionCard title="Academic Configuration is not valid">
              <ConflictList conflicts={configErrors.map((m) => ({ severity: 'error', code: 'CONFIG', message: m }))} />
              <p>Schedules cannot be generated until an Admin or Principal fixes the configuration.</p>
            </SectionCard>
          ) : (
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-3" data-testid="engine-metrics">
              <Stat label={pace ? `Approved schedule v${approvedVersionNo}: days left` : 'Teaching days left'} value={pace?.daysRemaining ?? daysLeft} hint={pace ? `Academic day ${pace.academicDay} of ${pace.academicDaysTotal} · calendar snapshot${snapshotDiffers ? ' (earlier than the current calendar)' : ''}` : `Academic day ${calendarDay} of ${calendar!.planningDates.length} · current calendar`} />
              <Stat label="Core periods" value={`${pace?.core.required ?? result!.metrics.core.requiredPeriods} ${pace ? 'approved' : 'configured'}`} hint={`${pace?.core.scheduled ?? result!.metrics.core.scheduledPeriods} scheduled · ${pace?.core.taught ?? 0} taught · ${pace?.core.remaining ?? result!.metrics.core.requiredPeriods} remaining${requirementGaps ? ` · ${requirementGaps} topic(s) missing counts` : ''}`} tone={requirementGaps ? 'rose' : 'teal'} />
              <Stat label="Non-Core periods" value={`${pace?.nonCore.required ?? result!.metrics.nonCore.requiredPeriods} ${pace ? 'approved' : 'configured'}`} hint={`${pace?.nonCore.scheduled ?? result!.metrics.nonCore.scheduledPeriods} scheduled · ${pace?.nonCore.taught ?? 0} taught · ${pace?.nonCore.remaining ?? result!.metrics.nonCore.requiredPeriods} remaining${requirementGaps ? ` · ${requirementGaps} topic(s) missing counts` : ''}`} tone={requirementGaps ? 'rose' : 'amber'} />
              <Stat label="Independent learning" value={`${pace?.nonCore.independent ?? result!.metrics.independentPeriods} periods`} hint="Never counted as classroom teaching" />
              <Stat label="Topics completed" value={`${completion?.unitsTaught ?? 0} / ${completion?.unitsTotal ?? view.units.length}`} hint={pace ? PACE_LABEL[pace.state] : 'No approved plan yet'} tone={pace?.state === 'BEHIND_CORE' || pace?.state === 'REQUIREMENTS_MISSING' ? 'rose' : 'teal'} />
              {snapshotDiffers && pace && approved && (
                <div className="col-span-full rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 space-y-1" data-testid="calendar-snapshot-notice" role="status">
                  <p className="font-semibold">Two calendars are shown, on purpose.</p>
                  <p>
                    <b>Current academic calendar{p.calendarVersion ? ` (version ${p.calendarVersion})` : ''}:</b> {calendar!.planningDates.length} instructional days, {daysLeft} left. It drives the capacity card above and the recalculated requirements.{' '}
                    <b>Approved schedule v{approvedVersionNo}:</b> approved on an earlier calendar snapshot with {pace.academicDaysTotal} instructional days, {pace.daysRemaining} left. The schedule figures in this row are that historical snapshot until the schedule is recalculated and approved again.
                  </p>
                  {(() => {
                    const blocked = recalculationBlocked(approved, workspace.config);
                    return (
                      <p data-testid="calendar-snapshot-status">
                        Status:{' '}
                        <b>
                          {pendingProposal(approved)
                            ? 'Recalculation proposal is waiting for Principal/Admin approval.'
                            : blocked
                              ? 'School working days changed, so the approved schedule cannot be edited in place. Recalculating generates a new draft from the current calendar, which a Principal/Admin must approve.'
                              : 'The approved schedule needs recalculation with the current calendar, then Principal/Admin approval.'}
                        </b>{' '}
                        The approved schedule stays in force until the new draft is approved.
                        {p.isTeacher && !pendingProposal(approved) && (
                          <Button size="sm" variant="outline" className="ml-2" icon={<RefreshCw className="w-3.5 h-3.5" />} disabled={recalcBusy} onClick={recalculateDraft}>
                            Recalculate with current configuration
                          </Button>
                        )}
                      </p>
                    );
                  })()}
                </div>
              )}
              {pace && <p className={`col-span-full rounded-lg border px-3 py-2 text-xs ${pace.state === 'BEHIND_CORE' || pace.state === 'REQUIREMENTS_MISSING' ? 'border-rose-200 bg-rose-50 text-rose-800' : 'border-surface-border bg-white text-content-secondary'}`} data-testid="pace-status">{pace.headline}</p>}
            </div>
          )}

          <SectionCard title="Topic requirements" subtitle={`${view.units.length} teachable topic(s) for this subject`} action={<Cpu className="w-4 h-4 text-teal-600" />}>
            <p>Required periods come from each topic's saved classification. Scheduled periods are placed on the calendar; taught periods are recorded in Daily Curriculum.</p>
            {!view.units.length && <p className="text-rose-700 font-semibold">No teachable topics are available for Class {GRADE_LABEL[grade]} {subject}. View the Curriculum Catalogue or request curriculum data to be added there.</p>}
            {view.units.length > 0 && !capacityPlan.data && <p className="text-content-secondary" role="status">Loading requirements…</p>}
            {view.units.length > 0 && capacityPlan.data && (
              <div className="overflow-x-auto border border-surface-border rounded-xl">
                <table className="w-full" aria-label="Topic requirements">
                  <thead>
                    <tr>
                      {['Topic', 'Classification', 'Required', 'Scheduled', 'Taught', 'Status'].map((h) => (
                        <th key={h} className={thCls}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {view.units.map((u) => {
                      const t = rowOf.get(u.id);
                      const lesson = lessonOf.get(u.id);
                      const st = topicStatus(t, lesson, approved ? referenceDate : null);
                      return (
                        <tr key={u.id} data-testid={`req-row-${u.id}`}>
                          <td className={tdCls}><span className="font-semibold text-navy-900">{`${u.number} ${u.title}`.trim()}</span></td>
                          <td className={`${tdCls} whitespace-nowrap`}>
                            <span className="inline-flex items-center gap-1.5" title={t?.origin === 'demo_default' ? 'Can be changed in Course Curriculum' : undefined}>
                              <ClassPill value={t?.classification} />
                              {t?.origin === 'demo_default' && <Pencil className="w-3 h-3 text-content-muted" aria-label="Editable" />}
                            </span>
                          </td>
                          <td className={`${tdCls} whitespace-nowrap`} data-testid={`req-required-${u.id}`}>{t ? requiredText(t) : '—'}</td>
                          <td className={tdCls}>
                            {lesson ? lesson.slots.length : t?.coverage === 'done' ? '—' : 0}
                            {!!lesson?.slots.length && <span className="block text-[11px] text-content-muted">{dateRange(lesson)}</span>}
                          </td>
                          <td className={tdCls}>{t?.taught_periods ?? 0}</td>
                          <td className={`${tdCls} whitespace-nowrap`}>
                            <span className="inline-flex items-center gap-1.5 font-medium" data-testid={`req-status-${u.id}`} style={{ color: st.color }}>
                              <span aria-hidden="true" className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: st.color }} />
                              {st.label}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {result && <ConflictList conflicts={result.conflicts} />}
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="teal" icon={<Send className="w-4 h-4" />} disabled={!canSubmit || busy} loading={busy} onClick={submitDraft}>
                Generate draft schedule for approval
              </Button>
              <span role="status" className="text-teal-800">
                {message}
              </span>
            </div>
          </SectionCard>

          <SectionCard title={`Plans for Class ${GRADE_LABEL[grade]} ${subject}`} subtitle="Every draft and approved plan is retained">
            {recalcMsg && (
              <p role={recalcMsg.tone === 'err' ? 'alert' : 'status'} data-testid="recalc-message" className={`rounded-lg border px-3 py-2 text-xs font-medium ${recalcMsg.tone === 'err' ? 'border-rose-300 bg-rose-50 text-rose-800' : recalcMsg.tone === 'ok' ? 'border-teal-300 bg-teal-50 text-teal-900' : 'border-amber-300 bg-amber-50 text-amber-900'}`}>
                {recalcMsg.text}
              </p>
            )}
            {draftWithBasis && <RecalculationResult draft={draftWithBasis} approved={approved} />}
            {!plans.length && <p className="text-content-secondary">No plans yet for this class and subject.</p>}
            <ul className="space-y-2">
              {plans.map((pl) => (
                <li key={pl.id} className="p-3 rounded-lg border border-surface-border flex flex-wrap items-center gap-3">
                  <PlanStatusBadge plan={pl} />
                  <span>
                  Created {pl.createdAt.slice(0, 10)} by {pl.createdBy.name} · {pl.draft.lessons.length} topics
                    {pl.versions.length > 1 && ` · ${pl.versions.length - 1} approved revision(s)`}
                  </span>
                  {pendingProposal(pl) && <Badge size="sm" variant="warning">Proposal pending</Badge>}
                  {pl.status === 'APPROVED' && configChangedSinceApproval(pl, workspace.config) && <span className="text-amber-800">Calendar changed since approval.</span>}
                  {pl.status === 'APPROVED' && p.isTeacher && (
                    <Button size="sm" variant="outline" icon={<RefreshCw className="w-3.5 h-3.5" />} disabled={recalcBusy} loading={recalcBusy} onClick={recalculateDraft}>
                      Recalculate with current configuration
                    </Button>
                  )}
                </li>
              ))}
            </ul>
            {approved && <p className="text-[11px] text-content-muted">Current approved plan: first schedule {dateRange(approved.versions[0]?.lessons[0])} … Approvals and comparisons are in Curriculum Oversight.</p>}
          </SectionCard>
        </>
      )}

      <LostPeriodRecorder grade={grade} subject={subject} />
    </div>
  );
};
