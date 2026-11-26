import React, { useState } from 'react';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { attachProposal, currentVersion, generateRecovery, planLabel } from '../../lib/planning/execution';
import { planProgress } from '../../lib/planning/progress';
import { periodNumberOf, periodNumbers } from '../../lib/planning/losses';
import type { PlanningSubject } from '../../lib/planning/calendar';
import { usePlanning } from '../../lib/planning/usePlanning';
import { useAuth } from '../../context/AuthContext';
import { describeError, teacherPlanApi, type LostRow } from '../../lib/teacherPlanApi';
import { reloadTeacherData, withLosses } from '../../features/teacherPlan/requirementsStore';

interface LogEntry {
  id: string;
  date: string;
  periods: number[];
  periodsLost: number;
  reason: string;
  note: string;
  recordedBy: { name: string };
  recordedAt: string;
  correctionReason?: string;
  withdrawn: boolean;
}

/** One log line per date/batch/reason and status, built from the teacher's relational lost-period rows (active and withdrawn). */
function logEntries(rows: LostRow[], grade: number, subject: string, me: { id: string; name: string } | null): LogEntry[] {
  const groups = new Map<string, LostRow[]>();
  for (const r of rows) {
    if (r.grade !== grade || r.subject !== subject) continue;
    const k = `${r.date}|${r.batch_id ?? r.id}|${r.reason}|${r.status}`;
    groups.set(k, [...(groups.get(k) ?? []), r]);
  }
  return [...groups.values()]
    .map((g) => ({
      id: `${g[0].batch_id ?? g[0].id}:${g[0].date}${g[0].status === 'withdrawn' ? ':w' : ''}`,
      date: g[0].date,
      periods: g.map((r) => r.period).sort((a, b) => a - b),
      periodsLost: g.length,
      reason: g[0].reason,
      note: g[0].notes ?? '',
      recordedBy: { name: me && g[0].recorded_by === me.id ? me.name : g[0].recorded_by },
      recordedAt: g[0].recorded_at ?? '',
      correctionReason: g[0].withdrawn_reason ?? undefined,
      withdrawn: g[0].status === 'withdrawn',
    }))
    .sort((a, b) => b.recordedAt.localeCompare(a.recordedAt) || b.date.localeCompare(a.date));
}
import { PlanningProgressPanel } from './PlanningProgressPanel';
import { inputCls, SectionCard, tdCls, thCls } from './planningUi';

/** Day tracker tab: progress for the approved plan and the append-only lost-period log with corrections. */
export const DayTracker: React.FC<{ grade: number; subject: PlanningSubject }> = ({ grade, subject }) => {
  const p = usePlanning();
  const { currentUser, currentSchoolId } = useAuth();
  const plan = p.workspace.plans.find((x) => x.status === 'APPROVED' && x.grade === grade && x.subject === subject);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [correctingId, setCorrectingId] = useState<string | null>(null);
  const [keep, setKeep] = useState<number[]>([]);
  const [correctionReason, setCorrectionReason] = useState('');

  if (!plan) {
    return (
      <SectionCard title="Progress and lost periods">
        <p className="text-content-secondary">No approved plan for this class and subject yet. Generate a draft in the Schedule planner and have it approved in Curriculum Oversight.</p>
      </SectionCard>
    );
  }

  const progress = planProgress(plan)!;
  const numbers = periodNumbers(plan);
  const log = logEntries(p.lostRows, grade, subject, currentUser ? { id: currentUser.id, name: currentUser.name } : null);
  const effective = new Set(log.filter((r) => !r.withdrawn).map((r) => r.id));
  const applied = new Set((currentVersion(plan)!.lostSlots ?? []).map((s) => `${s.date}#${s.period}`));
  const canRecord = p.ownsPlan; // corrections belong to the owning teacher

  const correct = async (lossId: string) => {
    const prior = log.find((r) => r.id === lossId && !r.withdrawn);
    if (!prior) return;
    if (correctionReason.trim().length < 5) return setMessage({ text: 'Explain the correction (at least 5 characters).', error: true });
    const withdrawn = prior.periods.filter((x) => !keep.includes(x));
    if (!withdrawn.length) return setMessage({ text: 'Untick at least one period that was not lost after all.', error: true });
    setBusy(true);
    setMessage(null);
    try {
      await teacherPlanApi.withdrawLost(p.teacherId, { grade, subject, date: prior.date, periods: withdrawn, reason: correctionReason.trim() });
    } catch (e) {
      setBusy(false);
      return setMessage({ text: describeError(e).message, error: true });
    }
    // The relational rows changed; the deterministic engine re-plans from them and the proposal replaces any pending one.
    const fresh = await reloadTeacherData(currentSchoolId, p.teacherId);
    const proposal = generateRecovery(withLosses(plan, fresh.lost, p.teacherId), p.ctx, { trigger: { kind: 'LOST_PERIODS', lossId: prior.id }, actor: p.actor! });
    const res = await p.commit('RECOVERY_PROPOSE', `Recovery re-proposed after correcting lost periods for ${planLabel(plan)} on ${prior.date}`, (w) => ({
      ...w,
      plans: w.plans.map((current) => (current.id === plan.id ? attachProposal(current, proposal) : current)),
    }));
    setBusy(false);
    setCorrectingId(null);
    setCorrectionReason('');
    setMessage(
      res.ok
        ? { text: keep.length ? 'Correction recorded. The recovery proposal was regenerated for approval.' : 'Loss withdrawn. The original record stays in the log as withdrawn.', error: false }
        : { text: `Correction recorded, but the regenerated recovery proposal could not be saved (${res.error ?? 'not saved'}).`, error: true },
    );
  };

  return (
    <div className="space-y-6">
      <PlanningProgressPanel progress={progress} title="Progress and lost periods" />

      <SectionCard title="Lost-period log" subtitle="Kept in the teacher's relational record. A correction withdraws periods with a reason; nothing is deleted.">
        <p className="text-content-secondary">To record new lost periods use <b>Record a Lost Day</b> at the bottom of the Time-Aware Engine.</p>
        {message && (
          <p role={message.error ? 'alert' : 'status'} className={`rounded-lg border px-3 py-2 ${message.error ? 'border-rose-200 bg-rose-50 text-rose-800' : 'border-teal-100 bg-teal-50 text-teal-700'}`}>
            {message.text}
          </p>
        )}
        {log.length === 0 ? (
          <p className="text-content-muted">No lost periods recorded for {planLabel(plan)}.</p>
        ) : (
          <div className="overflow-x-auto border border-surface-border rounded-xl">
            <table className="w-full" aria-label="Lost-period log">
              <thead>
                <tr>
                  {['Date', 'Periods', 'Reason and notes', 'Recorded by', 'Status', ''].map((h, i) => (
                    <th key={i} className={thCls}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {log.map((r) => {
                  const isEffective = effective.has(r.id);
                  const isApplied = (r.periods ?? []).some((x) => applied.has(`${r.date}#${x}`));
                  return (
                    <React.Fragment key={r.id}>
                      <tr className={isEffective ? '' : 'text-content-muted'}>
                        <td className={`${tdCls} whitespace-nowrap`}>{r.date}</td>
                        <td className={tdCls}>
                          {r.periods?.length ? r.periods.map((x) => `#${periodNumberOf(numbers, { date: r.date, period: x })}`).join(', ') : r.periods ? 'none (withdrawn)' : 'legacy record — period numbers missing'}
                        </td>
                        <td className={tdCls}>
                          <b>{r.reason}</b>
                          {r.note && <span className="block text-content-secondary">“{r.note}”</span>}
                          {r.correctionReason && <span className="block text-[11px]">correction: {r.correctionReason}</span>}
                        </td>
                        <td className={tdCls}>
                          {r.recordedBy.name}
                          <span className="block text-[11px] text-content-muted">{r.recordedAt.slice(0, 16).replace('T', ' ')}</span>
                        </td>
                        <td className={tdCls}>
                          {r.withdrawn ? <Badge size="sm">Withdrawn</Badge> : !isEffective ? <Badge size="sm">Superseded</Badge> : isApplied ? <Badge size="sm" variant="success">Recovery approved</Badge> : r.periodsLost ? <Badge size="sm" variant="warning">Awaiting approval</Badge> : <Badge size="sm">Withdrawn</Badge>}
                        </td>
                        <td className={tdCls}>
                          {canRecord && isEffective && !isApplied && r.periodsLost > 0 && correctingId !== r.id && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => {
                                setCorrectingId(r.id);
                                setKeep([]);
                                setCorrectionReason('');
                                setMessage(null);
                              }}
                            >
                              Correct
                            </Button>
                          )}
                        </td>
                      </tr>
                      {correctingId === r.id && (
                        <tr>
                          <td colSpan={6} className={`${tdCls} bg-surface-bg`}>
                            <div className="flex flex-wrap items-end gap-3">
                              <fieldset className="flex flex-wrap gap-3">
                                <legend className="text-[11px] font-semibold mb-1">Keep as lost (untick periods that were taught after all)</legend>
                                {(r.periods ?? []).map((x) => (
                                  <label key={x} className="inline-flex items-center gap-1.5">
                                    <input type="checkbox" checked={keep.includes(x)} onChange={(e) => setKeep(e.target.checked ? [...keep, x] : keep.filter((k) => k !== x))} />#{periodNumberOf(numbers, { date: r.date, period: x })}
                                  </label>
                                ))}
                              </fieldset>
                              <label className="text-[11px] flex-1 min-w-[200px]">
                                Reason for correction <span className="text-rose-600">*</span>
                                <input aria-label="Reason for correction" className={inputCls} value={correctionReason} onChange={(e) => setCorrectionReason(e.target.value)} />
                              </label>
                              <Button size="sm" variant="teal" loading={busy} disabled={busy} onClick={() => correct(r.id)}>
                                Record correction
                              </Button>
                              <Button size="sm" variant="outline" disabled={busy} onClick={() => setCorrectingId(null)}>
                                Cancel
                              </Button>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  );
};
