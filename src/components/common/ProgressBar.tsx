import React from 'react';
import { cn } from '../../lib/utils';

export interface ProgressSegment {
  key: string;
  value: number;
  label: string;
  /** Tailwind background class for the segment and its legend swatch. */
  className: string;
  /** Optional pattern for segments that must not be read from colour alone. */
  striped?: boolean;
}

const stripe = { backgroundImage: 'repeating-linear-gradient(45deg, rgba(255,255,255,.45) 0 4px, transparent 4px 8px)' };

/**
 * Segmented progress bar with a unit-labelled header and a text legend (status is never conveyed by colour alone).
 * `total` is the denominator; any shortfall between the segment sum and the total renders as the empty track.
 */
export const ProgressBar: React.FC<{
  label: string;
  unit: string;
  total: number;
  segments: ProgressSegment[];
  /** Index of the segment that counts as "done" for the headline figure. Defaults to the first. */
  doneKeys?: string[];
  size?: 'sm' | 'md';
  className?: string;
  testId?: string;
}> = ({ label, unit, total, segments, doneKeys, size = 'md', className, testId }) => {
  const done = segments.filter((s) => (doneKeys ?? [segments[0]?.key]).includes(s.key)).reduce((a, s) => a + s.value, 0);
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <div className={cn('space-y-2', className)} data-testid={testId}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs font-semibold text-content-primary">{label}</span>
        <span className="text-xs text-content-secondary tabular-nums">
          <b className="text-content-primary">{done}</b> of {total} {unit} · {pct}%
        </span>
      </div>
      <div
        className={cn('w-full bg-surface-bg border border-surface-border rounded-full overflow-hidden flex', size === 'sm' ? 'h-2' : 'h-3')}
        role="progressbar"
        aria-label={`${label} (${unit})`}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
        aria-valuetext={`${done} of ${total} ${unit}`}
      >
        {segments.map((s) =>
          s.value > 0 && total > 0 ? (
            <div key={s.key} className={cn('h-full transition-all', s.className)} style={{ width: `${Math.min(100, (s.value / total) * 100)}%`, ...(s.striped ? stripe : {}) }} title={`${s.label}: ${s.value} ${unit}`} />
          ) : null,
        )}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-content-secondary">
        {segments.map((s) => (
          <li key={s.key} className="inline-flex items-center gap-1.5">
            <span className={cn('w-2.5 h-2.5 rounded-sm', s.className)} style={s.striped ? stripe : undefined} aria-hidden />
            {s.label}: <b className="text-content-primary tabular-nums">{s.value}</b>
          </li>
        ))}
        {total - segments.reduce((a, s) => a + s.value, 0) > 0 && (
          <li className="inline-flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-surface-bg border border-surface-border" aria-hidden />
            Not yet done: <b className="text-content-primary tabular-nums">{total - segments.reduce((a, s) => a + s.value, 0)}</b>
          </li>
        )}
      </ul>
    </div>
  );
};
