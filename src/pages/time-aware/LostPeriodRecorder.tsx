import React, { useMemo, useRef, useState } from 'react';
import { CalendarX2, X } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { Modal } from '../../components/common/Modal';
import { GRADE_LABEL, PlanningSubject } from '../../lib/planning/calendar';
import { attachProposal, generateRecovery, planLabel } from '../../lib/planning/execution';
import { LOSS_REASONS, lossCandidates, type LossCandidate } from '../../lib/planning/losses';
import { usePlanning } from '../../lib/planning/usePlanning';
import { useAuth } from '../../context/AuthContext';
import { describeError, teacherPlanApi } from '../../lib/teacherPlanApi';
import { reloadTeacherData, withLosses } from '../../features/teacherPlan/requirementsStore';
import { topicKeyOf } from '../../features/teacherPlan/useTeacherCoverage';
import { inputCls, labelCls, SectionCard, selectCls, tdCls, thCls } from './planningUi';

const STATE_TEXT: Record<LossCandidate['state'], string> = { AVAILABLE: 'Scheduled', LOST: 'Already recorded lost', TAUGHT: 'Topic taught' };

/**
 * "Record a Lost Day" — records individual scheduled periods (one or many, across dates) as lost. It never cancels a
 * whole day: only the selected periods become incomplete, and a recovery proposal is generated for approval.
 */
export const LostPeriodRecorder: React.FC<{ grade: number; subject: PlanningSubject }> = ({ grade, subject }) => {
  const p = usePlanning();
  const plan = p.workspace.plans.find((x) => x.status === 'APPROVED' && x.grade === grade && x.subject === subject);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [reason, setReason] = useState('');
  const [note, setNote] = useState('');
  const [filter, setFilter] = useState<'available' | 'all'>('available');
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);

  const candidates = useMemo(() => (plan ? lossCandidates(plan) : []), [plan]);
  const byKey = useMemo(() => new Map(candidates.map((c) => [c.key, c])), [candidates]);
  const { currentSchoolId } = useAuth();
  const canRecord = p.ownsPlan; // only the owning teacher records their own lost periods
  const visible = candidates.filter((c) => (filter === 'all' || c.state === 'AVAILABLE') && (!query.trim() || `${c.number} ${c.date} ${c.title}`.toLowerCase().includes(query.trim().toLowerCase())));
  const chosen = selected.map((k) => byKey.get(k)).filter((c): c is LossCandidate => !!c).sort((a, b) => a.number - b.number);

  const reset = () => {
    setSelected([]);
    setReason('');
    setNote('');
    setError('');
    setQuery('');
  };
  const toggle = (k: string) => setSelected((s) => (s.includes(k) ? s.filter((x) => x !== k) : [...s, k]));

  const submit = async () => {
    if (submitting.current || !plan) return; // guards double clicks / repeated submissions
    setError('');
    if (!chosen.length) return setError('Select at least one scheduled period.');
    if (!reason) return setError('A reason is required.');
    submitting.current = true;
    setBusy(true);
    const numbers = chosen.map((c) => `#${c.number}`).join(', ');
    // 1. The lost periods are written to the relational store (atomic across dates). That is the only place they live.
    const dates = [...new Set(chosen.map((c) => c.date))].sort();
    let batchId = '';
    try {
      const res = await teacherPlanApi.recordLostBatch(p.teacherId, {
        grade,
        subject,
        entries: dates.map((date) => ({ date, periods: chosen.filter((c) => c.date === date).map((c) => c.period).sort((a, b) => a - b) })),
        topic_keys: [...new Set(chosen.map((c) => topicKeyOf(c.nodeId)))],
        reason_code: reason,
        notes: note.trim() || undefined,
      });
      batchId = res.batch_id;
    } catch (e) {
      submitting.current = false;
      setBusy(false);
      return setError(describeError(e).message);
    }
    // 2. The deterministic recovery engine runs on the plan with the teacher's relational losses, and its proposal is stored
    //    for approval. The approved schedule is not changed.
    const fresh = await reloadTeacherData(currentSchoolId, p.teacherId);
    const proposal = generateRecovery(withLosses(plan, fresh.lost, p.teacherId), p.ctx, { trigger: { kind: 'LOST_PERIODS', lossId: batchId }, actor: p.actor! });
    const res = await p.commit('RECOVERY_PROPOSE', `Recovery proposed for ${chosen.length} lost period(s) ${numbers} of ${planLabel(plan)} (${reason})`, (w) => ({
      ...w,
      plans: w.plans.map((x) => (x.id === plan.id ? attachProposal(x, proposal) : x)),
    }));
    submitting.current = false;
    setBusy(false);
    if (res.ok) {
      setMessage(`Recorded period(s) ${numbers} as lost (${reason}). Only these periods are incomplete. A recovery proposal now awaits Principal/Admin approval; the approved schedule and academic calendar are unchanged.`);
      reset();
      setOpen(false);
    } else {
      setMessage(`Recorded period(s) ${numbers} as lost (${reason}), but the recovery proposal could not be saved (${res.error ?? 'not saved'}). The lost periods are kept; a proposal is regenerated on the next change.`);
      reset();
      setOpen(false);
    }
  };

  return (
    <SectionCard
      title="Lost periods"
      subtitle={plan ? `${planLabel(plan)} · approved schedule` : `Class ${GRADE_LABEL[grade]} ${subject}`}
      action={<CalendarX2 className="w-4 h-4 text-rose-600" />}
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3" data-testid="lost-period-recorder">
        <p className="text-content-secondary max-w-2xl">
          Record individual scheduled periods that could not be taught. Only the selected periods become incomplete — this is not a whole-day cancellation. Core recovery is proposed for Principal/Admin approval.
        </p>
        <Button
          variant="danger"
          icon={<CalendarX2 className="w-4 h-4" />}
          disabled={!plan || !canRecord}
          onClick={() => {
            setMessage('');
            setOpen(true);
          }}
        >
          Record a Lost Day
        </Button>
      </div>
      {!plan && <p className="text-content-muted">Available once a schedule for Class {GRADE_LABEL[grade]} {subject} is approved.</p>}
      {plan && !canRecord && <p className="text-content-muted">Only a teacher or Admin can record lost periods. Principals review the resulting recovery proposals.</p>}
      {message && (
        <p role="status" className="rounded-lg border border-teal-100 bg-teal-50 px-3 py-2 text-teal-700">
          {message}
        </p>
      )}

      {plan && (
        <Modal
          isOpen={open}
          onClose={() => !busy && setOpen(false)}
          maxWidth="4xl"
          title="Record a Lost Day"
          subtitle={`${planLabel(plan)} · select the individual scheduled periods that were lost`}
          footer={
            <>
              <span className="mr-auto text-xs text-content-secondary">{chosen.length ? `${chosen.length} period(s) selected` : 'No periods selected'}</span>
              <Button variant="outline" disabled={busy} onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button variant="danger" loading={busy} disabled={busy || !chosen.length || !reason} onClick={submit}>
                {chosen.length ? `Record ${chosen.length} lost period(s)` : 'Record lost periods'}
              </Button>
            </>
          }
        >
          <div className="space-y-4 text-xs">
            <div className="flex flex-wrap items-end gap-3">
              <label>
                <span className={labelCls}>Show</span>
                <select aria-label="Period filter" className={selectCls} value={filter} onChange={(e) => setFilter(e.target.value as 'available' | 'all')}>
                  <option value="available">Periods that can be recorded</option>
                  <option value="all">All scheduled periods</option>
                </select>
              </label>
              <label className="flex-1 min-w-[180px]">
                <span className={labelCls}>Find</span>
                <input aria-label="Find period" className={inputCls} placeholder="Period number, date (YYYY-MM-DD) or topic" value={query} onChange={(e) => setQuery(e.target.value)} />
              </label>
            </div>

            <div className="border border-surface-border rounded-xl max-h-72 overflow-auto">
              <table className="w-full" aria-label="Scheduled periods">
                <thead className="sticky top-0 z-10">
                  <tr>
                    {['', 'Period', 'Date', 'Class', 'Subject', 'Topic', 'Type', 'Status'].map((h, i) => (
                      <th key={i} className={thCls}>
                        {h || <span className="sr-only">Select</span>}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visible.map((c) => {
                    const disabled = c.state !== 'AVAILABLE' || !canRecord;
                    const checked = selected.includes(c.key);
                    return (
                      <tr key={c.key} className={checked ? 'bg-rose-50/60' : disabled ? 'text-content-muted' : 'hover:bg-surface-bg cursor-pointer'} onClick={() => !disabled && toggle(c.key)}>
                        <td className={tdCls}>
                          <input
                            type="checkbox"
                            className="w-4 h-4 accent-rose-600"
                            aria-label={`Period ${c.number}: ${c.date}, ${c.title}`}
                            disabled={disabled}
                            checked={checked}
                            onClick={(e) => e.stopPropagation()}
                            onChange={() => toggle(c.key)}
                          />
                        </td>
                        <td className={`${tdCls} font-semibold tabular-nums`}>#{c.number}</td>
                        <td className={`${tdCls} whitespace-nowrap`}>
                          {c.date}
                          <span className="block text-[11px] text-content-muted">day period {c.period}</span>
                        </td>
                        <td className={tdCls}>{GRADE_LABEL[grade]}</td>
                        <td className={tdCls}>{subject}</td>
                        <td className={`${tdCls} min-w-[180px]`}>{c.title}</td>
                        <td className={tdCls}>
                          <Badge size="sm" variant={c.kind === 'CORE' ? 'teal' : 'warning'}>
                            {c.kind === 'CORE' ? 'Core' : 'Non-Core'}
                          </Badge>
                        </td>
                        <td className={`${tdCls} whitespace-nowrap`}>{STATE_TEXT[c.state]}</td>
                      </tr>
                    );
                  })}
                  {!visible.length && (
                    <tr>
                      <td className={`${tdCls} text-content-secondary`} colSpan={8}>
                        No scheduled periods match. {filter === 'available' ? 'Periods of taught topics and periods already recorded lost cannot be selected.' : ''}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div>
              <p className={labelCls}>Selected periods</p>
              {chosen.length ? (
                <ul className="flex flex-wrap gap-1.5" aria-label="Selected periods">
                  {chosen.map((c) => (
                    <li key={c.key} className="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 pl-2.5 pr-1 py-0.5 text-rose-800">
                      #{c.number} · {c.date} · {c.title}
                      <button type="button" className="p-0.5 rounded-full hover:bg-rose-100" aria-label={`Remove period ${c.number}`} onClick={() => toggle(c.key)}>
                        <X className="w-3 h-3" />
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-content-muted">Tick one or more periods above. Several periods (for example #110, #111 and #112) can be submitted together.</p>
              )}
            </div>

            <div className="grid sm:grid-cols-2 gap-3">
              <label>
                <span className={labelCls}>
                  Reason <span className="text-rose-600">*</span>
                </span>
                <select aria-label="Loss reason" aria-required="true" className={`${selectCls} w-full`} value={reason} onChange={(e) => setReason(e.target.value)}>
                  <option value="">Choose a reason</option>
                  {LOSS_REASONS.map((r) => (
                    <option key={r}>{r}</option>
                  ))}
                </select>
              </label>
              <label>
                <span className={labelCls}>Notes (optional)</span>
                <input aria-label="Loss note" className={inputCls} placeholder="What happened" value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
            </div>
            {error && (
              <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-rose-800">
                {error}
              </p>
            )}
          </div>
        </Modal>
      )}
    </SectionCard>
  );
};
