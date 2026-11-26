import React, { useEffect, useState } from 'react';
import { describeError, teacherPlanApi, type CalendarPreview, type CapacityFigures, type TeacherCalendarImpact } from '../../lib/teacherPlanApi';
import { tdCls, thCls } from '../../pages/time-aware/planningUi';
import { useStoreVersion } from './requirementsStore';
import { useRemote } from './useRemote';

const ROMAN: Record<number, string> = { 6: 'VI', 7: 'VII', 8: 'VIII' };
const Fig: React.FC<{ a: CapacityFigures; b: CapacityFigures }> = ({ a, b }) => (
  <>
    <td className={tdCls}>{a.available_periods} -&gt; <b>{b.available_periods}</b> ({b.available_periods - a.available_periods > 0 ? '+' : ''}{b.available_periods - a.available_periods})</td>
    <td className={tdCls}>{a.reserved_periods} -&gt; <b>{b.reserved_periods}</b></td>
    <td className={tdCls}>{a.topic_capacity} -&gt; <b>{b.topic_capacity}</b> ({b.topic_capacity - a.topic_capacity > 0 ? '+' : ''}{b.topic_capacity - a.topic_capacity})</td>
  </>
);

/** Read-only preview of a pending calendar change. Preview values never update saved requirements or approved plans. */
export const CalendarPreviewPanel: React.FC<{ config: unknown; valid: boolean; dirty: boolean }> = ({ config, valid, dirty }) => {
  const [preview, setPreview] = useState<CalendarPreview | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!valid || !dirty) {
      setPreview(null);
      setError('');
      return;
    }
    let cancelled = false;
    const t = setTimeout(() => {
      teacherPlanApi.previewCalendar(config)
        .then((r) => !cancelled && (setPreview(r), setError('')))
        .catch((e) => !cancelled && (setPreview(null), setError(describeError(e).message)));
    }, 300);
    return () => { cancelled = true; clearTimeout(t); };
  }, [config, valid, dirty]);
  if (!valid || !dirty) return <p className="text-content-secondary text-xs">Edit a valid configuration to preview its effect on annual allocations.</p>;
  if (error) return <p role="status" className="text-xs text-rose-700">{error}</p>;
  if (!preview) return <p role="status" className="text-xs text-content-muted">Calculating the effect...</p>;
  const review = preview.impact.filter((i) => i.needs_teacher_review);
  return (
    <div className="space-y-3 text-xs" data-testid="calendar-preview">
      <p>Calendar version {preview.current_version || 'none'} -&gt; <b>{preview.proposed_version}</b> (proposal preview; nothing is saved or approved).</p>
      <table className="w-full" aria-label="Annual capacity before and after">
        <thead><tr><th className={thCls}>Subject</th><th className={thCls}>Original annual teaching periods</th><th className={thCls}>Reserve periods</th><th className={thCls}>Topic capacity and total change</th></tr></thead>
        <tbody>{Object.keys(preview.capacity_after).map((s) => (
          <tr key={s} data-testid={`capacity-${s}`}><td className={tdCls}>{s}</td><Fig a={preview.capacity_before[s]} b={preview.capacity_after[s]} /></tr>
        ))}</tbody>
      </table>
      {preview.impact.length === 0 ? <p className="text-content-muted">No teacher has an annual plan in this school yet.</p> : (
        <div className="space-y-3">
          {preview.impact.map((i) => (
            <section key={`${i.teacher_id}${i.grade}${i.subject}`} className="rounded-lg border border-surface-border p-2 space-y-2" data-testid="impact-row" data-review={i.needs_teacher_review}>
              <div className="flex flex-wrap gap-x-3 gap-y-1">
                <b>{i.teacher_name} - Class {ROMAN[i.grade]} {i.subject}</b>
                <span>Original topic capacity {i.capacity_before.topic_capacity}; revised {i.capacity_after.topic_capacity}; total change {i.periods_gained_or_lost > 0 ? '+' : ''}{i.periods_gained_or_lost}.</span>
                <span>Saved requirements {i.saved_total}; {i.needs_teacher_review ? `short by ${i.deficit_after}` : `${i.remaining_after} periods remain`}.</span>
              </div>
              {i.core_shortfall > 0 && <p role="alert" className="font-semibold text-rose-700">Core requirement shortfall: {i.core_shortfall} period(s).</p>}
              {i.insufficient_capacity && i.deficit_after > 0 && <p role="alert" className="font-semibold text-rose-700">Insufficient annual capacity. Existing requirements exceed revised topic capacity by {i.deficit_after} period(s); nothing has been dropped.</p>}
              {i.approved_schedule?.capacity_conflict && <p role="alert" className="font-semibold text-rose-700">The approved schedule conflicts with revised capacity. It remains unchanged pending an authorized proposal and approval.</p>}
              <div className="overflow-x-auto">
                <table className="w-full" aria-label={`Topic allocation comparison ${i.teacher_name} ${i.grade} ${i.subject}`}>
                  <thead><tr>{['Topic', 'Configuration', 'Total original -> proposed', 'Total +/-', 'Classroom original -> proposed', 'Classroom +/-', 'Independent original -> proposed', 'Independent +/-', 'Status'].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
                  <tbody>{i.topics.filter((t) => t.is_affected).map((t) => (
                    <tr key={t.topic_key} data-testid="topic-allocation-change">
                      <td className={tdCls}>{t.section}</td>
                      <td className={tdCls}>{t.origin === 'demo_default' ? 'Initial value' : t.origin === 'teacher' ? 'Teacher customized' : 'Approved import'} - {t.classification} - {t.teaching_mode}</td>
                      <td className={tdCls}>{t.original_allocation} -&gt; <b>{t.revised_allocation}</b></td>
                      <td className={tdCls}>{t.allocation_change > 0 ? '+' : ''}{t.allocation_change}</td>
                      <td className={tdCls}>{t.original_classroom} -&gt; <b>{t.revised_classroom}</b></td>
                      <td className={tdCls}>{t.classroom_change > 0 ? '+' : ''}{t.classroom_change}</td>
                      <td className={tdCls}>{t.original_independent} -&gt; <b>{t.revised_independent}</b></td>
                      <td className={tdCls}>{t.independent_change > 0 ? '+' : ''}{t.independent_change}</td>
                      <td className={tdCls}>{t.customization_conflict ? 'Conflicts with teacher customization' : 'Affected'}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
              <p className="text-content-secondary">Approved schedule: {i.approved_schedule ? (i.approved_schedule.calendar_differs ? i.approved_schedule.note : 'Unaffected') : 'No approved plan'} {i.approved_schedule?.capacity_conflict ? '(capacity conflict)' : ''}</p>
            </section>
          ))}
        </div>
      )}
      <p className="text-content-secondary">Saving creates calendar version {preview.proposed_version}. It does not apply proposed allocations or change teacher customizations or approved schedules{review.length ? `; ${review.length} plan(s) no longer fit` : ''}.</p>
    </div>
  );
};

/** Read-only comparison of the latest calendar change with this teacher's current requirements. */
export const TeacherCalendarImpactPanel: React.FC<{ teacherId: string; grade: number; subject: string }> = ({ teacherId, grade, subject }) => {
  const version = useStoreVersion();
  const { data, error, loading } = useRemote<TeacherCalendarImpact>(() => teacherPlanApi.calendarImpact(teacherId, grade, subject), [teacherId, grade, subject, version]);
  if (loading) return <p role="status" className="text-xs text-content-muted">Loading calendar impact...</p>;
  if (error) return <p role="alert" className="text-xs text-rose-700">{error}</p>;
  if (!data || !data.has_previous || !data.impact) return null;
  const i = data.impact;
  return (
    <details className="text-xs border border-surface-border rounded-lg px-3 py-2" data-testid="teacher-calendar-impact" open={i.needs_teacher_review || i.core_shortfall > 0}>
      <summary className="cursor-pointer font-semibold text-navy-900">
        Calendar changed (version {data.previous_version} -&gt; {data.current_version}){data.reason ? ` - ${data.reason}` : ''}
        {i.needs_teacher_review && <span className="ml-2 text-rose-700">- requirements exceed the revised capacity</span>}
      </summary>
      <div className="mt-2 space-y-2">
        <p>Annual teaching capacity: {i.capacity_before.available_periods} -&gt; {i.capacity_after.available_periods}; reserve {i.capacity_before.reserved_periods} -&gt; {i.capacity_after.reserved_periods}; topic capacity {i.capacity_before.topic_capacity} -&gt; <b>{i.capacity_after.topic_capacity}</b> ({i.periods_gained_or_lost > 0 ? '+' : ''}{i.periods_gained_or_lost}).</p>
        <p>Your saved requirements total {i.saved_total}; {i.needs_teacher_review ? `${i.deficit_after} period(s) exceed revised capacity` : `${i.remaining_after} periods remain`}.</p>
        {i.core_shortfall > 0 && <p role="alert" className="font-semibold text-rose-700">Core requirement shortfall: {i.core_shortfall} period(s).</p>}
        {i.insufficient_capacity && <p role="alert" className="font-semibold text-rose-700">Insufficient annual capacity: {i.deficit_after} period(s).</p>}
        <div className="overflow-x-auto">
          <table className="w-full" aria-label="Allocation comparison after the calendar change">
            <thead><tr>{['Topic', 'Total original -> proposed', 'Total +/-', 'Classroom original -> proposed', 'Classroom +/-', 'Independent original -> proposed', 'Independent +/-', 'State'].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>{i.topics.filter((t) => t.is_affected).map((t) => <tr key={t.topic_key}>
              <td className={tdCls}>{t.section} - {t.classification} - {t.teaching_mode}</td>
              <td className={tdCls}>{t.original_allocation} -&gt; {t.revised_allocation}</td><td className={tdCls}>{t.allocation_change > 0 ? '+' : ''}{t.allocation_change}</td>
              <td className={tdCls}>{t.original_classroom} -&gt; {t.revised_classroom}</td><td className={tdCls}>{t.classroom_change > 0 ? '+' : ''}{t.classroom_change}</td>
              <td className={tdCls}>{t.original_independent} -&gt; {t.revised_independent}</td><td className={tdCls}>{t.independent_change > 0 ? '+' : ''}{t.independent_change}</td>
              <td className={tdCls}>{t.customization_conflict ? 'Teacher customization conflict' : 'Proposed'}</td>
            </tr>)}</tbody>
          </table>
        </div>
        {i.approved_schedule?.capacity_conflict && <p role="alert" className="text-rose-700">Approved schedule conflict; approval is required before replacement.</p>}
        <p className="text-content-secondary">This is a proposal preview. Saved requirements and approved allocations remain unchanged. {i.approved_schedule?.calendar_differs ? i.approved_schedule.note : ''}</p>
      </div>
    </details>
  );
};
