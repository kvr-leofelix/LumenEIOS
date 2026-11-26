import React, { useState } from 'react';
import { ClipboardCheck, History } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { Card, CardBody, CardHeader } from '../../components/common/Card';
import { summarizeCalendar } from '../../lib/planning/calendar';
import { lessonStart, PlannedLesson, slotKind } from '../../lib/planning/engine';
import {
  approveRecovery,
  currentVersion,
  EXEC_LABEL,
  isIncomplete,
  ExecStatus,
  lessonProgress,
  originalVersion,
  pendingProposal,
  Plan,
  planLabel,
  recordAndPropose,
  recordEvidence,
  rejectRecovery,
  RecoveryProposal,
} from '../../lib/planning/execution';
import { findNode, VERIFIED_DATASET } from '../../lib/planning/syllabus';
import { coverageAfterExecution } from '../../lib/planning/coverage';
import { coverageFromPlan, topicKeyOf } from '../../features/teacherPlan/useTeacherCoverage';
import { cachedLostRows, withLosses } from '../../features/teacherPlan/requirementsStore';
import { useAuth } from '../../context/AuthContext';
import { describeError, teacherPlanApi, type Coverage as ApiCoverage } from '../../lib/teacherPlanApi';

const toApi = (s: 'DONE' | 'IN_PROGRESS' | 'NOT_DONE'): ApiCoverage => (s === 'DONE' ? 'done' : s === 'IN_PROGRESS' ? 'in_progress' : 'not_done');
import { effectiveLosses, LossDaySummary, periodNumberOf, periodNumbers, type PeriodMove } from '../../lib/planning/losses';
import { usePlanning } from '../../lib/planning/usePlanning';
import { PERIOD_STATUS_LABEL, periodLedger, planProgress, type PeriodStatus } from '../../lib/planning/progress';
import { PlanningProgressPanel } from './PlanningProgressPanel';
import { ConflictList, CoverageTag, dateRange, inputCls, LegacyRequirementNote, ScheduleComparison, selectCls, StateBadge, tdCls, thCls } from './planningUi';

const ExecutionForm: React.FC<{ plan: Plan; lesson: PlannedLesson; onDone: () => void }> = ({ plan, lesson, onDone }) => {
  const p = usePlanning();
  const { currentSchoolId } = useAuth();
  const progress = lessonProgress(plan, lesson);
  const dates = summarizeCalendar(plan.config).instructionalDates;
  const [date, setDate] = useState(lessonStart(lesson) ?? progress.lastIncomplete?.date ?? dates[0]);
  const [note, setNote] = useState('');
  const [periods, setPeriods] = useState(1);
  const [error, setError] = useState('');
  const [evRef, setEvRef] = useState('');
  const [evResult, setEvResult] = useState('');
  const [saving, setSaving] = useState(false);

  const record = async (status: ExecStatus) => {
    if (saving) return;
    setError('');
    setSaving(true);
    let captured: Plan | null = null;
    const res = await p.commit('EXECUTION_RECORD', `${EXEC_LABEL[status]}: ${lesson.number} ${lesson.title} (${planLabel(plan)}, ${date})`, (w) => {
      const updated: Plan[] = [];
      const plans = w.plans.map((x) => {
        if (x.id !== plan.id) return x;
        // The engine runs on the plan with the teacher's relational lost periods; the stored plan keeps its own (frozen) history.
        const proposed = recordAndPropose(withLosses(x, cachedLostRows(currentSchoolId, p.teacherId), p.teacherId), { nodeId: lesson.nodeId, date, status, periodsTaught: periods, note }, p.actor!, p.ctx).plan;
        const next = { ...proposed, losses: x.losses };
        updated.push(next);
        return next;
      });
      captured = updated[0] ?? null;
      return { ...w, plans };
    });
    if (res.ok && captured && p.actor && p.role === 'teacher') {
      // Course Curriculum coverage follows genuine classroom completion only (rules in lib/planning/coverage.ts), and is
      // stored in the relational teacher-plan record, the only coverage store.
      try {
        const current = coverageFromPlan(await teacherPlanApi.plan(p.actor.id, plan.grade, plan.subject));
        const next = coverageAfterExecution(current, captured, lesson.nodeId, p.actor);
        if (next[lesson.nodeId] && next[lesson.nodeId].status !== current[lesson.nodeId]?.status) {
          await teacherPlanApi.setCoverage(p.actor.id, { grade: plan.grade, subject: plan.subject, topic_key: topicKeyOf(lesson.nodeId), status: toApi(next[lesson.nodeId].status), source: 'EXECUTION' });
        }
      } catch (e) {
        setSaving(false);
        setError(`Execution was saved, but coverage could not be updated: ${describeError(e).message}`);
        return;
      }
    }
    setSaving(false);
    if (res.ok) onDone();
    else setError(res.error ?? 'Not saved.');
  };
  const evidence = async () => {
    setError('');
    const res = await p.commit('EVIDENCE_RECORD', `Assessment evidence recorded for ${lesson.title}`, (w) => ({
      ...w,
      plans: w.plans.map((x) => (x.id === plan.id ? recordEvidence(x, lesson.nodeId, 'ASSESSMENT', evRef, evResult, p.actor!) : x)),
    }));
    if (res.ok) onDone();
    else setError(res.error ?? 'Not saved.');
  };

  return (
    <div className="p-3 rounded-lg bg-surface-bg border border-surface-border space-y-2 min-w-[280px]">
      <div className="flex flex-wrap gap-2">
        <label className="text-[11px]">
          Teaching date{' '}
          <select aria-label={`Date for ${lesson.title}`} className={selectCls} value={date} onChange={(e) => setDate(e.target.value)}>
            {dates.map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
        </label>
        <input aria-label="Execution note" className={`${inputCls} flex-1`} placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
      </div>
      {!progress.complete && (
        <div className="flex flex-col gap-1.5">
          <Button size="sm" variant="teal" disabled={saving} onClick={() => record('TAUGHT')}>
            Completed as scheduled
          </Button>
          <Button size="sm" variant="outline" disabled={saving} onClick={() => record('HOMEWORK')}>
            Not completed — assigned as homework
          </Button>
          <Button size="sm" variant="outline" disabled={saving} onClick={() => record('DEFERRED')}>
            Not completed — deferred/rescheduled
          </Button>
          {progress.remainingPeriods > 1 && (
            <div className="flex items-center gap-2">
              <input aria-label="Periods taught" type="number" min={1} className={`${inputCls} w-16`} value={periods} onChange={(e) => setPeriods(Number(e.target.value))} />
              <Button size="sm" variant="outline" disabled={saving} onClick={() => record('PARTIAL')}>
                Partially completed
              </Button>
              <span className="text-[11px] text-content-muted">of {progress.remainingPeriods} remaining</span>
            </div>
          )}
        </div>
      )}
      {progress.homeworkAssigned && !progress.homeworkSubmitted && (
        <Button size="sm" variant="secondary" disabled={saving} onClick={() => record('HOMEWORK_COMPLETED')}>
          Record homework submitted
        </Button>
      )}
      {progress.complete && (
        <div className="space-y-1.5">
          <p className="text-[11px] text-content-secondary">Mastery requires assessment evidence; teaching or homework alone does not establish it.</p>
          <input aria-label="Assessment reference" className={inputCls} placeholder="Assessment / evidence reference" value={evRef} onChange={(e) => setEvRef(e.target.value)} />
          <input aria-label="Assessment result" className={inputCls} placeholder="Result or observation" value={evResult} onChange={(e) => setEvResult(e.target.value)} />
          <Button size="sm" variant="secondary" icon={<ClipboardCheck className="w-3.5 h-3.5" />} onClick={evidence}>
            Record assessment evidence
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-[11px] text-rose-700">
          {error}
        </p>
      )}
    </div>
  );
};

const CHANGE_LABEL: Record<string, string> = {
  REQUEUED: 'Requeued (incomplete work)',
  SHIFTED: 'Shifted later',
  REDUCED: 'Classroom time reduced (approved Non-Core to independent learning)',
  NEWLY_UNSCHEDULED: 'No longer fits — unscheduled time',
  RESTORED: 'Time restored',
  TO_HOMEWORK: 'Recovery applied (Non-Core moved to independent learning)',
  INCOMPLETE_REQUEUED: 'Core awaiting recovery',
};

const MOVE_LABEL: Record<PeriodMove['kind'], { text: string; variant: 'danger' | 'teal' | 'warning' }> = {
  LOST: { text: 'Lost', variant: 'danger' },
  CORE_RECOVERED: { text: 'Core recovered', variant: 'teal' },
  NON_CORE_TO_INDEPENDENT: { text: 'Non-Core → independent learning', variant: 'warning' },
};

const LossDayCard: React.FC<{ day: LossDaySummary; subject: string }> = ({ day, subject }) => (
  <div className="bg-white rounded-xl border border-rose-200 p-3 space-y-2" data-testid="loss-day">
    <p className="font-semibold text-rose-900">
      Lost periods on {day.date} ({day.reason}): {day.lost} of {day.scheduled} scheduled {subject} period(s)
    </p>
    <ul className="grid sm:grid-cols-2 gap-x-6 gap-y-0.5">
      <li>
        <b>Retained in classroom:</b> {day.retained.map((r) => `${r.title} (${r.periods})`).join('; ') || 'none'}
      </li>
      <li>
        <b>Core recovered:</b> {(day.recovered ?? []).map((r) => `${r.title} (${r.periods})`).join('; ') || 'none'}
      </li>
      <li>
        <b>Moved to independent learning:</b> {day.homework.map((r) => `${r.title} (${r.periods})`).join('; ') || 'none'}
      </li>
      <li>
        <b>Core still outstanding:</b> {day.incomplete.map((r) => `${r.title} (${r.periods})`).join('; ') || 'none'}
      </li>
    </ul>
    {(day.unresolved ?? []).map((u, i) => (
      <p key={i} className="text-rose-800">
        {u}
      </p>
    ))}
  </div>
);

const ProposalPanel: React.FC<{ plan: Plan; proposal: RecoveryProposal }> = ({ plan, proposal }) => {
  const p = usePlanning();
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const original = originalVersion(plan)!;
  const current = currentVersion(plan)!;
  const moves = (proposal.lossDays ?? []).flatMap((d) => d.moves ?? []).sort((a, b) => a.number - b.number || a.kind.localeCompare(b.kind));
  const sum = (f: (d: LossDaySummary) => { periods: number }[] | undefined) => (proposal.lossDays ?? []).reduce((s, d) => s + (f(d) ?? []).reduce((a, x) => a + x.periods, 0), 0);
  const recovered = sum((d) => d.recovered);
  const toIndependent = sum((d) => d.homework);
  const outstanding = sum((d) => d.incomplete);
  const decide = async (approve: boolean) => {
    if (busy) return;
    setError('');
    if (!approve && note.trim().length < 5) return setError('A rejection reason is required (at least 5 characters).');
    setBusy(true);
    const res = await p.commit('RECOVERY_REVIEW', `${approve ? 'Approved' : 'Rejected'} ${proposal.trigger.kind === 'CONFIG_CHANGE' ? 'recalculation' : 'recovery'} proposal for ${planLabel(plan)}`, (w) => ({
      ...w,
      plans: w.plans.map((x) => (x.id === plan.id ? (approve ? approveRecovery(x, proposal.id, p.actor!, note) : rejectRecovery(x, proposal.id, p.actor!, note)) : x)),
    }));
    setBusy(false);
    if (!res.ok) setError(res.error ?? 'Not saved.');
  };
  const tiles: [string, React.ReactNode, string][] = [
    ['Core periods recovered', recovered, 'text-teal-700 text-lg'],
    ['Non-Core → independent learning', toIndependent, 'text-amber-700 text-lg'],
    ['Core still outstanding', outstanding, `${outstanding ? 'text-rose-700' : 'text-navy-900'} text-lg`],
    ['Unscheduled after recovery', proposal.metrics.unscheduledPeriods, `${proposal.metrics.unscheduledPeriods ? 'text-rose-700' : 'text-navy-900'} text-lg`],
    [`Remaining ${plan.subject} periods`, `${proposal.remainingAvailablePeriods} available · ${proposal.remainingRequiredPeriods} required`, 'text-navy-900 text-xs pt-1'],
  ];
  return (
    <section className="border border-amber-300 bg-amber-50/50 rounded-2xl p-4 space-y-4 text-xs" data-testid="recovery-proposal" aria-label="Recovery proposal">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-bold text-navy-900">{proposal.trigger.kind === 'CONFIG_CHANGE' ? 'Recalculation proposal' : 'Recovery proposal'}</h3>
        <Badge size="sm" variant="warning" dot>
          Pending approval
        </Badge>
        <Badge size="sm" variant="outline">
          Based on approved v{proposal.baseVersion}
        </Badge>
        <span className="text-[11px] text-content-muted">
          Generated {proposal.createdAt.slice(0, 16).replace('T', ' ')} after a record by {proposal.createdBy.name}
        </span>
      </div>

      <dl className="grid grid-cols-2 lg:grid-cols-5 gap-2">
        {tiles.map(([label, value, cls]) => (
          <div key={label} className="bg-white rounded-lg border border-surface-border p-2.5">
            <dt className="text-[11px] text-content-secondary">{label}</dt>
            <dd className={`font-bold tabular-nums ${cls}`}>{value}</dd>
          </div>
        ))}
      </dl>

      <ul className="list-disc ml-5 space-y-0.5 text-content-primary">
        {proposal.explanation.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>

      {(proposal.lossDays ?? []).map((d) => (
        <LossDayCard key={d.date} day={d} subject={plan.subject} />
      ))}

      {moves.length > 0 && (
        <div>
          <p className="font-semibold mb-1">Every changed period</p>
          <div className="overflow-x-auto border border-surface-border rounded-xl bg-white">
            <table className="w-full" aria-label="Changed periods">
              <thead>
                <tr>
                  {['Period', 'Date', 'Change', 'Topic', 'Original schedule', 'Reason'].map((h) => (
                    <th key={h} className={thCls}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {moves.map((m, i) => {
                  const orig = original.lessons.find((l) => l.slots.some((s) => s.date === m.date && s.period === m.period));
                  const origSlot = orig?.slots.find((s) => s.date === m.date && s.period === m.period);
                  return (
                    <tr key={i}>
                      <td className={`${tdCls} font-semibold tabular-nums`}>#{m.number}</td>
                      <td className={`${tdCls} whitespace-nowrap`}>{m.date}</td>
                      <td className={tdCls}>
                        <Badge size="sm" variant={MOVE_LABEL[m.kind].variant}>
                          {MOVE_LABEL[m.kind].text}
                        </Badge>
                      </td>
                      <td className={tdCls}>{m.title}</td>
                      <td className={`${tdCls} text-content-secondary`}>{orig && origSlot ? `${orig.title} (${slotKind(orig, origSlot) === 'CORE' ? 'Core' : 'Non-Core'})` : 'Unused period'}</td>
                      <td className={`${tdCls} text-content-secondary`}>{m.reason}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {proposal.changes.length > 0 && (
        <div>
          <p className="font-semibold mb-1">Topic-level changes</p>
          <ul className="space-y-1.5" aria-label="Proposed changes">
            {proposal.changes.map((c) => {
              const lesson = proposal.lessons.find((l) => l.nodeId === c.nodeId);
              return (
                <li key={c.nodeId} className="bg-white rounded-lg border border-surface-border p-2.5">
                  <b>{c.title}</b> — {CHANGE_LABEL[c.kind]}: {c.before.start ?? 'unscheduled'}
                  {c.before.end && c.before.end !== c.before.start ? ` → ${c.before.end}` : ''} ⇒ {c.after.start ?? 'unscheduled'}
                  {c.after.end && c.after.end !== c.after.start ? ` → ${c.after.end}` : ''}
                  {c.after.unscheduled > 0 && ` (${c.after.unscheduled} period(s) unscheduled)`}
                  {lesson && <span className="block text-[11px] text-content-secondary mt-0.5">{lesson.explanation.join(' ')}</span>}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {proposal.affected.length > 0 && (
        <div>
          <p className="font-semibold">Affected topics and dependents</p>
          <ul className="list-disc ml-5">
            {proposal.affected.map((a, i) => (
              <li key={`${a.nodeId}-${i}`}>
                {a.title}: {a.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <p className="font-semibold mb-1">Original vs current approved vs proposed</p>
        <ScheduleComparison
          caption="Recovery comparison"
          columns={[
            { label: 'Original (v1)', lessons: original.lessons },
            { label: `Current approved (v${current.version})`, lessons: current.lessons },
            { label: 'Proposed', lessons: proposal.lessons, highlight: true },
          ]}
        />
      </div>
      <div>
        <p className="font-semibold mb-1">Remaining capacity conflicts</p>
        <ConflictList conflicts={proposal.conflicts.filter((c) => c.severity === 'error')} />
      </div>
      {p.isReviewer ? (
        <div className="flex flex-wrap items-center gap-2 pt-3 border-t border-amber-200">
          <input aria-label="Recovery review note" className={`${inputCls} max-w-sm`} placeholder="Review note (required to reject)" value={note} onChange={(e) => setNote(e.target.value)} />
          <Button variant="teal" size="sm" loading={busy} disabled={busy} onClick={() => decide(true)}>
            Approve recovery schedule
          </Button>
          <Button variant="outline" size="sm" disabled={busy} onClick={() => decide(false)}>
            Reject proposal
          </Button>
          {error && (
            <p role="alert" className="w-full text-rose-700">
              {error}
            </p>
          )}
        </div>
      ) : (
        <p className="font-semibold text-amber-900 pt-3 border-t border-amber-200">Awaiting Principal/Admin approval. The approved schedule has not changed.</p>
      )}
    </section>
  );
};

const PERIOD_VARIANT: Record<PeriodStatus, 'default' | 'success' | 'warning' | 'danger' | 'info' | 'teal'> = {
  TAUGHT: 'success',
  SCHEDULED: 'default',
  LOST: 'danger',
  LOST_PENDING: 'danger',
  RECOVERED_CORE: 'teal',
  MOVED_TO_INDEPENDENT: 'warning',
};

const KindTag: React.FC<{ kind: 'CORE' | 'NON_CORE' }> = ({ kind }) => <span className={`text-[11px] font-semibold ${kind === 'CORE' ? 'text-teal-700' : 'text-amber-700'}`}>{kind === 'CORE' ? 'Core' : 'Non-Core'}</span>;

/** Period-by-period Daily Curriculum: original approved schedule, current approved schedule, execution and losses. */
const PeriodLedgerTable: React.FC<{ plan: Plan }> = ({ plan }) => {
  const [show, setShow] = useState<'all' | 'changed'>('all');
  const rows = periodLedger(plan, periodNumbers(plan));
  const visible = show === 'all' ? rows : rows.filter((r) => r.status !== 'SCHEDULED' && r.status !== 'TAUGHT');
  return (
    <div className="space-y-2">
      <label className="inline-flex items-center gap-2">
        <span className="font-semibold">Show</span>
        <select aria-label="Period view filter" className={selectCls} value={show} onChange={(e) => setShow(e.target.value as 'all' | 'changed')}>
          <option value="all">All periods ({rows.length})</option>
          <option value="changed">Lost, recovered or moved only</option>
        </select>
      </label>
      <div className="overflow-auto max-h-[480px] border border-surface-border rounded-xl">
        <table className="w-full" aria-label="Daily curriculum by period">
          <thead className="sticky top-0 z-10">
            <tr>
              {['Period', 'Date', 'Original approved', 'Current approved', 'Status'].map((h) => (
                <th key={h} className={thCls}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => (
              <tr key={r.key}>
                <td className={`${tdCls} font-semibold tabular-nums`}>#{r.number}</td>
                <td className={`${tdCls} whitespace-nowrap`}>
                  {r.date}
                  <span className="block text-[11px] text-content-muted">day period {r.period}</span>
                </td>
                <td className={tdCls}>
                  {r.original ? (
                    <>
                      {r.original.title} <KindTag kind={r.original.kind} />
                    </>
                  ) : (
                    <span className="text-content-muted">Unused</span>
                  )}
                </td>
                <td className={tdCls}>
                  {r.current ? (
                    <>
                      {r.current.title} <KindTag kind={r.current.kind} />
                    </>
                  ) : (
                    <span className="text-content-muted">—</span>
                  )}
                </td>
                <td className={tdCls}>
                  <Badge size="sm" variant={PERIOD_VARIANT[r.status]} dot>
                    {PERIOD_STATUS_LABEL[r.status]}
                  </Badge>
                  {r.lossReason && (
                    <span className="block text-[11px] text-rose-800 mt-0.5">
                      {r.lossReason}
                      {r.lossNote ? ` — “${r.lossNote}”` : ''}
                    </span>
                  )}
                </td>
              </tr>
            ))}
            {!visible.length && (
              <tr>
                <td colSpan={5} className={`${tdCls} text-content-secondary`}>
                  No lost, recovered or moved periods.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export const PlanDetail: React.FC<{ plan: Plan; mode: 'teacher' | 'review' }> = ({ plan, mode }) => {
  const p = usePlanning();
  const [openRow, setOpenRow] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [view, setView] = useState<'topic' | 'period'>('topic');
  const version = currentVersion(plan);
  const original = originalVersion(plan);
  const proposal = pendingProposal(plan);
  const cal = summarizeCalendar(plan.config);
  if (!version || !original) return null;
  const previous = plan.versions[plan.versions.length - 2];
  const changedInLatest = previous ? version.lessons.filter((l) => dateRange(l) !== dateRange(previous.lessons.find((x) => x.nodeId === l.nodeId))) : [];
  const superseded = new Set(plan.execution.map((e) => e.supersedes).filter(Boolean));
  const canExecute = mode === 'teacher' && (p.role === 'teacher' || p.role === 'admin') && plan.status === 'APPROVED';
  const progressList = version.lessons.map((l) => lessonProgress(plan, l));
  const overall = planProgress(plan);
  const losses = plan.losses ?? [];
  const effective = effectiveLosses(plan);
  const effectiveIds = new Set(effective.map((r) => r.id));
  const numbers = periodNumbers(plan);
  const lostFor = (l: PlannedLesson) => {
    const orig = original.lessons.find((x) => x.nodeId === l.nodeId);
    const here = [...(orig?.slots ?? []), ...l.slots];
    return effective.flatMap((r) =>
      (r.periods ?? []).filter((period) => here.some((s) => s.date === r.date && s.period === period)).map((period) => ({ number: periodNumberOf(numbers, { date: r.date, period }), reason: r.reason })),
    );
  };

  return (
    <div className="space-y-4">
      {overall && <PlanningProgressPanel progress={overall} />}
      {proposal && <ProposalPanel plan={plan} proposal={proposal} />}
      <Card>
        <CardHeader
          title={<span>{planLabel(plan)} · Daily Curriculum</span>}
          subtitle={`${plan.datasetLabel} · approved schedule v${version.version} (${version.approvedBy.name}, ${version.approvedAt.slice(0, 10)}) · ${cal.planningDates.length} instructional days · ${plan.config.subjectPeriodsPerDay[plan.subject]} period(s)/day × ${plan.config.periodMinutes} min`}
          action={
            <Badge size="sm" variant={plan.status === 'APPROVED' ? 'success' : 'default'}>
              {plan.status === 'APPROVED' ? 'Approved' : plan.status.toLowerCase()}
            </Badge>
          }
        />
        <CardBody className="space-y-4 text-xs">
          <h2 className="sr-only">
            Class {plan.grade} · {plan.subject} · Daily Curriculum
          </h2>
          {plan.datasetKind !== VERIFIED_DATASET.kind && <p className="text-amber-800">Syllabus source: {plan.datasetLabel} — not verified by LumenEIOS.</p>}
          <div className="flex flex-wrap gap-x-5 gap-y-1 text-content-secondary">
            <span>
              Units taught: <b className="text-content-primary">{progressList.filter((x) => x.complete).length}</b> / {version.lessons.length}
            </span>
            <span>
              Incomplete units: <b className="text-content-primary">{progressList.filter(isIncomplete).length}</b>
            </span>
            <span>
              Homework open: <b className="text-content-primary">{progressList.filter((x) => x.homeworkAssigned && !x.complete).length}</b>
            </span>
            <span>
              Lost periods recorded: <b className="text-content-primary">{effective.reduce((s, r) => s + r.periodsLost, 0)}</b> · in approved schedule: <b className="text-content-primary">{(version.lostSlots ?? []).length}</b>
            </span>
            {overall && (
              <span>
                Remaining Core / Non-Core: <b className="text-content-primary">{overall.coreRemaining}</b> / <b className="text-content-primary">{overall.nonCoreRemaining}</b>
              </span>
            )}
          </div>

          {mode === 'teacher' && previous && (
            <div className="p-3 rounded-lg bg-sky-50 border border-sky-200 text-sky-900" data-testid="schedule-change-notice">
              <b>Approved schedule change:</b> v{version.version} approved by {version.approvedBy.name} on {version.approvedAt.slice(0, 10)} — {version.reason}.{' '}
              {changedInLatest.length ? `${changedInLatest.length} unit(s) have new dates: ${changedInLatest.map((l) => `${l.title} → ${dateRange(l)}`).join('; ')}.` : 'Topic date ranges are unchanged; see "By period" for the changed periods.'}
            </div>
          )}

          <div className="flex flex-wrap gap-1 p-1 w-fit rounded-lg bg-surface-bg border border-surface-border" role="tablist" aria-label="Daily Curriculum view">
            {(
              [
                ['topic', 'By topic'],
                ['period', 'By period'],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                role="tab"
                aria-selected={view === k}
                className={`px-3 py-1.5 rounded-md font-semibold focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 ${view === k ? 'bg-white text-navy-900 shadow-subtle' : 'text-content-secondary hover:text-content-primary'}`}
                onClick={() => setView(k)}
              >
                {label}
              </button>
            ))}
          </div>

          {view === 'period' ? (
            <PeriodLedgerTable plan={plan} />
          ) : (
            <div className="overflow-x-auto border border-surface-border rounded-xl">
              <table className="w-full" aria-label="Daily curriculum schedule">
                <thead>
                  <tr>
                    {['Dates (approved / original)', 'Topic / subtopic', 'Learning outcome', 'Requirement and time', 'Execution status', ...(canExecute ? ['Teacher action'] : [])].map((h) => (
                      <th key={h} className={thCls}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {version.lessons.map((l, i) => {
                    const pr = progressList[i];
                    const orig = original.lessons.find((x) => x.nodeId === l.nodeId);
                    const outcomes = l.outcomeIds.map((id) => p.datasets.flatMap((d) => d.outcomes).find((o) => o.id === id)).filter(Boolean);
                    const lost = lostFor(l);
                    const recovered = (l.lossNotes ?? []).reduce((s, n) => s + (n.recovered ?? 0), 0);
                    return (
                      <tr key={l.nodeId}>
                        <td className={`${tdCls} min-w-[150px]`}>
                          <span className={dateRange(orig) !== dateRange(l) ? 'font-semibold text-sky-800' : ''}>{dateRange(l)}</span>
                          <span className="block text-[11px] text-content-muted">{dateRange(orig) !== dateRange(l) ? `originally ${dateRange(orig)}` : 'as originally approved'}</span>
                        </td>
                        <td className={`${tdCls} min-w-[180px]`}>
                          <span className="font-semibold text-navy-900">
                            {l.number} {l.title}
                          </span>
                          <LegacyRequirementNote lesson={l} />
                          <CoverageTag nodeId={l.nodeId} grade={plan.grade} subject={plan.subject} />
                          <span className="block text-[11px] text-content-muted">
                            Ch {l.chapterNumber}: {l.chapterTitle}
                          </span>
                          {l.sharedReduction > 0 && <span className="block text-[11px] text-indigo-800">Shares {l.sharedReduction} period(s) with a linked unit</span>}
                          {findNode(p.datasets, l.nodeId) === undefined && <span className="block text-[11px] text-rose-700">Source record no longer available</span>}
                        </td>
                        <td className={`${tdCls} text-[11px] min-w-[150px] max-w-[220px]`}>
                          {outcomes.length ? (
                            outcomes.map((o) => (
                              <span key={o!.id} className="block">
                                “{o!.researchLabel}” <span className="text-content-muted">({o!.inferred ? 'inferred link, awaiting review' : o!.linkVerification})</span>
                              </span>
                            ))
                          ) : (
                            <span className="text-content-muted">Not available</span>
                          )}
                        </td>
                        <td className={`${tdCls} min-w-[220px]`}>
                          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
                            <dt className="text-content-secondary">Required</dt>
                            <dd>
                              {l.requirementStatus === 'MISSING' ? (
                                <span className="text-rose-700 font-semibold">Not approved</span>
                              ) : (
                                <>
                                  <b>{l.corePeriods ?? '—'}</b> Core · <b>{l.nonCorePeriods ?? '—'}</b> Non-Core
                                </>
                              )}
                            </dd>
                                                        <dt className="text-content-secondary">Classroom</dt>
                            <dd>
                              {orig?.slots.length ?? 0} original → {l.slots.length} approved × {plan.config.periodMinutes} min
                            </dd>
                            <dt className="text-content-secondary">Taught</dt>
                            <dd>{pr.taughtPeriods} period(s)</dd>
                            {l.independentPeriods > 0 && (
                              <>
                                <dt className="text-amber-800">Independent</dt>
                                <dd className="text-amber-800">{l.independentPeriods} Non-Core (tracked, not taught)</dd>
                              </>
                            )}
                            {(l.coreUnscheduled ?? 0) > 0 && !pr.complete && (
                              <>
                                <dt className="text-rose-700">Awaiting</dt>
                                <dd className="text-rose-700">{l.coreUnscheduled} Core period(s) without a slot</dd>
                              </>
                            )}
                            {recovered > 0 && (
                              <>
                                <dt className="text-teal-700">Recovered</dt>
                                <dd className="text-teal-700">{recovered} Core period(s)</dd>
                              </>
                            )}
                          </dl>
                        </td>
                        <td className={`${tdCls} min-w-[200px]`}>
                          <StateBadge state={pr.state} />
                          {lost.length > 0 && <span className="block text-[11px] text-rose-800 mt-1">Lost: {lost.map((x) => `#${x.number} (${x.reason})`).join(', ')}</span>}
                          {pr.taughtPeriods > 0 && !pr.complete && <span className="block text-[11px]">{pr.taughtPeriods} period(s) taught</span>}
                          {pr.events.some((e) => e.status === 'HOMEWORK') && <span className="block text-[11px] text-amber-800">{pr.homeworkSubmitted ? 'Homework submitted — not counted as teaching or mastery' : 'Homework assigned — not counted as completed'}</span>}
                          {l.independentPeriods > 0 && <span className="block text-[11px] text-amber-800">{l.independentPeriods} Non-Core period(s) as independent learning — not classroom teaching</span>}
                          {pr.events.slice(-1).map((e) => (
                            <span key={e.id} className="block text-[11px] text-content-muted">
                              Last record {e.date} by {e.recordedBy.name}
                            </span>
                          ))}
                        </td>
                        {canExecute && (
                          <td className={tdCls}>
                            {openRow === l.nodeId ? (
                              <ExecutionForm plan={plan} lesson={l} onDone={() => setOpenRow(null)} />
                            ) : (
                              <Button size="sm" variant="outline" onClick={() => setOpenRow(l.nodeId)}>
                                Record execution
                              </Button>
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {losses.length > 0 && (
            <div className="p-3 rounded-xl border border-rose-200 bg-rose-50/40" data-testid="disruption-log">
              <p className="font-semibold text-rose-900 mb-1">Lost periods recorded</p>
              <ul className="space-y-0.5">
                {losses.map((r) => (
                  <li key={r.id} className={effectiveIds.has(r.id) ? '' : 'line-through text-content-muted'}>
                    {r.date} · {r.periodsLost} period(s) lost{r.periods?.length ? ` (${r.periods.map((x) => `#${periodNumberOf(numbers, { date: r.date, period: x })}`).join(', ')})` : ''} · {r.reason}
                    {r.note && ` — “${r.note}”`} · recorded by {r.recordedBy.name}
                    {r.supersedes && ` · correction: ${r.correctionReason}`}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" icon={<History className="w-3.5 h-3.5" />} onClick={() => setShowHistory(!showHistory)} aria-expanded={showHistory}>
              {showHistory ? 'Hide' : 'Show'} history ({plan.versions.length} approved version(s), {plan.execution.length} execution record(s), {plan.proposals.length} proposal(s))
            </Button>
          </div>
          {showHistory && (
            <div className="space-y-4">
              <ScheduleComparison caption="Approved versions" columns={plan.versions.map((v) => ({ label: v.version === 1 ? 'Original (v1)' : `v${v.version}`, lessons: v.lessons }))} />
              <ul className="space-y-1">
                {plan.versions.map((v) => (
                  <li key={v.version}>
                    v{v.version} approved {v.approvedAt.slice(0, 16).replace('T', ' ')} by {v.approvedBy.name} ({v.approvedBy.role}) — {v.reason}
                  </li>
                ))}
              </ul>
              <div>
                <p className="font-semibold mb-1">Execution log (append-only)</p>
                {plan.execution.length ? (
                  <ul className="space-y-0.5" aria-label="Execution log">
                    {plan.execution.map((e) => (
                      <li key={e.id} className={superseded.has(e.id) ? 'line-through text-content-muted' : ''}>
                        {e.date} · {findNode(p.datasets, e.nodeId)?.title ?? e.nodeId} · {EXEC_LABEL[e.status]}
                        {e.status === 'PARTIAL' ? ` (${e.periodsTaught} period(s))` : ''} · {e.recordedBy.name} at {e.recordedAt.slice(0, 16).replace('T', ' ')}
                        {e.note && ` — “${e.note}”`}
                        {e.supersedes && ' (correction)'}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-content-secondary">No execution recorded.</p>
                )}
              </div>
              {plan.evidence.length > 0 && (
                <div>
                  <p className="font-semibold mb-1">Assessment evidence</p>
                  <ul>
                    {plan.evidence.map((e) => (
                      <li key={e.id}>
                        {findNode(p.datasets, e.nodeId)?.title}: {e.reference} — {e.result} ({e.recordedBy.name}, {e.recordedAt.slice(0, 10)})
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div>
                <p className="font-semibold mb-1">Proposal history</p>
                {plan.proposals.length ? (
                  <ul className="space-y-0.5" aria-label="Proposal history">
                    {plan.proposals.map((x) => (
                      <li key={x.id}>
                        {x.createdAt.slice(0, 16).replace('T', ' ')} · {x.trigger.kind === 'CONFIG_CHANGE' ? 'Recalculation' : x.trigger.kind === 'LOST_PERIODS' ? 'Lost-period recovery' : 'Recovery'} · {x.changes.length} change(s) · <b>{x.status.toLowerCase()}</b>
                        {x.review && ` by ${x.review.by.name} at ${x.review.at.slice(0, 16).replace('T', ' ')}${x.review.note ? ` — “${x.review.note}”` : ''}`}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-content-secondary">No proposals.</p>
                )}
              </div>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
};
