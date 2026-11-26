import React from 'react';
import type { TeacherPlan } from '../../lib/teacherPlanApi';

/**
 * Annual capacity and remaining-work summary of one teacher's plan, straight from the backend's persisted records.
 * Required, taught and remaining periods are different things and are shown separately; a Core shortfall is stated, never hidden.
 * (Scheduled periods are shown by the schedule planner itself; a scheduled period is not a taught period.)
 */
export const PlanCapacitySummary: React.FC<{ plan: TeacherPlan }> = ({ plan }) => {
  const s = plan.summary;
  if (!s) return null;
  const cap = plan.capacity;
  const w = s.window;
  // [id, label, value, sub]
  const cells: [string, string, string | number, string?][] = [
    ['periods-per-day', 'Periods per day', s.periods_per_day, `${s.instructional_days} instructional days in the year`],
    ['available', 'Available periods in the year (P)', cap.available_periods],
    ['reserve', 'Reserve (R = ⌈10% of P⌉)', cap.reserved_periods],
    ['topic', 'Topic capacity (T = P − R)', cap.topic_capacity],
    ['core', 'Core required', s.required_core],
    ['non-core', 'Non-Core required', s.required_non_core],
    ['taught', 'Actually taught', s.taught_periods, `${s.done_topics} topic(s) done`],
    ['left-days', `Teaching days left (after ${w.after})`, w.days_left],
    ['left-periods', 'Periods left', w.periods_left],
    ['left-reserve', 'Reserve of periods left', w.reserve_left],
    ['left-capacity', 'Capacity for untaught work', w.capacity_left, `${s.open_topics} topic(s) not done`],
    ['left-core', 'Core still to teach', s.remaining_required_core, `${s.remaining_required_non_core} Non-Core still to teach`],
  ];
  const last = s.last_recalculation;
  return (
    <div className="space-y-2" data-testid="plan-capacity-summary">
      <dl className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
        {cells.map(([id, k, v, sub]) => (
          <div key={id} className="rounded-lg border border-surface-border bg-surface-bg px-2 py-1">
            <dt className="text-content-muted">{k}</dt>
            <dd className="font-bold" data-testid={`cap-${id}`}>{v}</dd>
            {sub && <dd className="text-[11px] text-content-muted">{sub}</dd>}
          </div>
        ))}
      </dl>
      {!s.fits && (
        <p role="alert" className="text-xs rounded-lg border border-rose-300 bg-rose-50 text-rose-800 px-3 py-2" data-testid="capacity-shortfall">
          Not enough teaching time left for the untaught syllabus: {s.core_shortfall} Core topic(s) cannot be given a Core period and {s.total_shortfall} period(s)/topic(s) are short in total. Core requirements are not dropped; they are listed as unresolved.
        </p>
      )}
      {last && (
        <p className="text-[11px] text-content-muted" data-testid="last-recalculation">
          Last calendar recalculation: {last.at.slice(0, 16).replace('T', ' ')} UTC · {last.summary}
        </p>
      )}
    </div>
  );
};
