import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Button } from '../../components/common/Button';
import { useAuth } from '../../context/AuthContext';
import { describeError, teacherPlanApi } from '../../lib/teacherPlanApi';
import { inputCls, tdCls, thCls } from '../../pages/time-aware/planningUi';
import { invalidateRequirements } from './requirementsStore';
import { useRemote } from './useRemote';
import { TeacherCalendarImpactPanel } from './CalendarImpact';
import { PlanCapacitySummary } from './PlanCapacitySummary';

const SUBJECT_NAME = { mathematics: 'Mathematics', science: 'Science' } as const;

/**
 * Teacher-owned annual plan inside the Course Curriculum: Core/Non-Core period requirements and capacity.
 * (Coverage status is edited in the syllabus list below it; both read the same relational record.)
 * Totals shown here are previews; the backend recalculates capacity and rejects over-capacity saves.
 * A Principal/Admin opening ?teacher=<id> sees the same plan read-only.
 */
export const TeacherPlanPanel: React.FC<{ grade: number; subject: 'mathematics' | 'science'; showOrigin?: boolean }> = ({ grade, subject, showOrigin }) => {
  const { currentUser } = useAuth();
  const [params] = useSearchParams();
  const subjectName = SUBJECT_NAME[subject];
  const teacherId = params.get('teacher') || (currentUser?.role === 'teacher' ? currentUser.id : '');
  const own = !!currentUser && currentUser.role === 'teacher' && currentUser.id === teacherId;
  const { data: plan, error, reload } = useRemote(() => (teacherId ? teacherPlanApi.plan(teacherId, grade, subjectName) : Promise.reject(new Error('Select a teacher from Curriculum Oversight to view their plan.'))), [teacherId, grade, subject]);
  const [draft, setDraft] = useState<Record<string, { core: number; non: number }>>({});
  const [msg, setMsg] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null);

  useEffect(() => {
    setDraft({});
    setMsg(null);
  }, [plan]);

  // A teacher opening a combination for the first time gets their own copy of the deterministic defaults.
  const initialised = useRef('');
  useEffect(() => {
    const key = `${teacherId}|${grade}|${subjectName}`;
    if (own && plan && plan.configured_topic_count < plan.topic_count && initialised.current !== key) {
      initialised.current = key; // once per plan, so an empty syllabus can never loop
      teacherPlanApi.initialize(teacherId, grade, subjectName).then(reload).catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan]);

  const proposed = useMemo(() => (plan ? plan.topics.reduce((s, t) => s + (draft[t.topic_key]?.core ?? t.core_periods) + (draft[t.topic_key]?.non ?? t.non_core_periods), 0) : 0), [plan, draft]);
  if (!teacherId) return <p className="text-xs text-content-muted" data-testid="plan-panel-empty">Teaching plans are owned by teachers. Open a teacher from Curriculum Oversight to inspect theirs.</p>;
  if (error) return <p role="alert" className="text-xs text-rose-700">{error}</p>;
  if (!plan) return <p className="text-xs text-content-muted">Loading plan…</p>;

  const cap = plan.capacity.topic_capacity;
  const remaining = cap - proposed;
  const dirty = Object.keys(draft).length > 0;
  const setField = (key: string, field: 'core' | 'non', raw: string, t: (typeof plan.topics)[number]) => {
    const n = Math.max(0, Math.floor(Number(raw) || 0));
    setDraft((d) => ({ ...d, [key]: { core: d[key]?.core ?? t.core_periods, non: d[key]?.non ?? t.non_core_periods, [field]: n } }));
  };
  const save = async () => {
    setMsg(null);
    try {
      const res = await teacherPlanApi.saveRequirements(teacherId, {
        grade,
        subject: subjectName,
        reason: 'Teacher adjusted period requirements',
        items: Object.entries(draft).map(([topic_key, v]) => ({ topic_key, core_periods: v.core, non_core_periods: v.non })),
      });
      setMsg({ tone: 'ok', text: res.changed.length ? 'Requirements saved.' : 'No changes to save.' });
      invalidateRequirements(); // the scheduling engine and every other screen reload the same rows
      reload();
    } catch (e) {
      setMsg({ tone: 'err', text: describeError(e).message });
    }
  };
  return (
    <section className="bg-white rounded-2xl border border-surface-border shadow-subtle p-4 space-y-3" data-testid="teacher-plan-panel">
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <h2 className="text-sm font-bold text-navy-900">{own ? 'My teaching plan' : 'Teacher plan (read-only)'}</h2>
        <Link className="ml-auto font-semibold text-teal-700 underline" to={`/logs?teacher_id=${teacherId}&grade=${grade}&subject=${subjectName}`}>History →</Link>
      </div>
      <dl className="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs" data-testid="capacity-summary">
        {([['Available periods', plan.capacity.available_periods], ['10% reserve', plan.capacity.reserved_periods], ['Topic capacity', cap], ['Proposed total', proposed], [remaining < 0 ? 'Deficit' : 'Remaining', Math.abs(remaining)]] as [string, number][]).map(([k, v], i) => (
          <div key={k} className={`rounded-lg border px-2 py-1 ${i === 4 && remaining < 0 ? 'border-rose-300 bg-rose-50 text-rose-800' : 'border-surface-border bg-surface-bg'}`}>
            <dt className="text-content-muted">{k}</dt>
            <dd className="font-bold">{v}</dd>
          </div>
        ))}
      </dl>
      <PlanCapacitySummary plan={plan} />
      <TeacherCalendarImpactPanel teacherId={teacherId} grade={grade} subject={subjectName} />
      {remaining < 0 && (
        <p role="alert" className="text-xs text-rose-700" data-testid="capacity-error">
          Saving is blocked: these requirements need {proposed} periods but only {cap} are available after the 10% reserve (deficit {-remaining}). Reduce a requirement to continue.
        </p>
      )}
      {msg && <p role={msg.tone === 'err' ? 'alert' : 'status'} className={`text-xs ${msg.tone === 'err' ? 'text-rose-700' : 'text-teal-700'}`}>{msg.text}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className={thCls}>Chapter · Section</th>
              <th className={thCls}>Core</th>
              <th className={thCls}>Non-Core</th>
              <th className={thCls}>Classification</th>
              <th className={thCls}>Teaching mode</th>
              <th className={thCls}>Independent</th>
              {showOrigin && <th className={thCls}>Basis</th>}
            </tr>
          </thead>
          <tbody>
            {plan.topics.map((t) => (
              <tr key={t.topic_key} data-testid="plan-topic-row">
                <td className={tdCls}>{t.chapter_number}. {t.chapter_title} · {t.section}</td>
                <td className={tdCls}>
                  <input aria-label={`Core periods ${t.section}`} type="number" min={0} className={`${inputCls} w-20`} disabled={!own} value={draft[t.topic_key]?.core ?? t.core_periods} onChange={(e) => setField(t.topic_key, 'core', e.target.value, t)} />
                </td>
                <td className={tdCls}>
                  <input aria-label={`Non-Core periods ${t.section}`} type="number" min={0} className={`${inputCls} w-20`} disabled={!own} value={draft[t.topic_key]?.non ?? t.non_core_periods} onChange={(e) => setField(t.topic_key, 'non', e.target.value, t)} />
                </td>
                <td className={tdCls}>{t.classification.replace('_', '-')}</td>
                <td className={tdCls}>{t.teaching_mode === 'SHARED' ? 'Shared suggestion (approved lead link required)' : 'Independent learning'}</td>
                <td className={tdCls}>{t.independent_periods} period(s)</td>
                {showOrigin && (
                  <td className={tdCls} data-testid={`origin-${t.topic_key}`} data-origin={t.origin}>
                    {t.origin === 'demo_default' ? 'Initial value (editable)' : t.origin === 'teacher' ? 'Set by teacher' : 'Imported approved requirement'}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {own && (
        <Button size="sm" variant="teal" disabled={!dirty || remaining < 0} onClick={save}>
          Save requirements
        </Button>
      )}
    </section>
  );
};
