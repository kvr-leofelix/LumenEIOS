import React from 'react';
import { COVERAGE_STYLE, Coverage } from '../../lib/teacherPlanApi';

/** Translucent coloured coverage box. Colour plus an accessible name; no verbose label text. */
export const StatusBox: React.FC<{ status: Coverage; onClick?: () => void; title?: string }> = ({ status, onClick, title }) => {
  const s = COVERAGE_STYLE[status];
  const style = { background: s.bg, color: s.fg, borderColor: s.fg + '55' };
  const cls = 'inline-flex items-center justify-center w-6 h-6 rounded-md border text-[10px] font-bold';
  const mark = status === 'done' ? '✓' : status === 'in_progress' ? '◐' : '';
  if (onClick) {
    return (
      <button type="button" data-status={status} aria-label={s.label} title={title ?? s.label} style={style} className={`${cls} focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400`} onClick={onClick}>
        {mark}
      </button>
    );
  }
  return (
    <span role="img" data-status={status} aria-label={s.label} title={title ?? s.label} style={style} className={cls}>
      {mark}
    </span>
  );
};

export const CoverageBar: React.FC<{ done: number; in_progress: number; not_done: number }> = ({ done, in_progress, not_done }) => {
  const total = done + in_progress + not_done || 1;
  const seg = (n: number, c: Coverage) => <div style={{ width: `${(100 * n) / total}%`, background: COVERAGE_STYLE[c].fg, opacity: 0.55 }} />;
  return (
    <div className="flex h-2 w-full rounded-full overflow-hidden bg-gray-100" role="img" aria-label={`${done} done, ${in_progress} in progress, ${not_done} not done`}>
      {seg(done, 'done')}
      {seg(in_progress, 'in_progress')}
      {seg(not_done, 'not_done')}
    </div>
  );
};
