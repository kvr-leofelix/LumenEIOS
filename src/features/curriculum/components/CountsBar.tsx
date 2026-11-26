import React from 'react';
import type { StatusCounts } from '../types';

/** Stacked bar with text labels underneath, so meaning never depends on colour alone. */
export const CountsBar: React.FC<{ counts: StatusCounts }> = ({ counts }) => {
  const parts = [
    { key: 'verified', n: counts.verified, cls: 'bg-emerald-500', label: 'verified' },
    { key: 'partial', n: counts.partiallyVerified, cls: 'bg-sky-400', label: 'partial' },
    { key: 'unverified', n: counts.unverified, cls: 'bg-gray-400', label: 'unverified' },
    { key: 'placeholder', n: counts.placeholder, cls: 'bg-[repeating-linear-gradient(45deg,#d1d5db_0,#d1d5db_3px,#fff_3px,#fff_6px)]', label: 'placeholder' },
  ];
  return (
    <div>
      <div className="flex h-2 w-full rounded-full overflow-hidden bg-surface-bg border border-surface-border" aria-hidden="true">
        {parts.map((p) => (p.n ? <div key={p.key} className={p.cls} style={{ width: `${(p.n / Math.max(counts.total, 1)) * 100}%` }} /> : null))}
      </div>
      <p className="text-[11px] text-content-secondary mt-1.5">
        {parts.map((p, i) => (
          <span key={p.key}>
            {i > 0 && ' · '}
            <strong className="text-content-primary tabular-nums">{p.n}</strong> {p.label}
          </span>
        ))}
      </p>
    </div>
  );
};
