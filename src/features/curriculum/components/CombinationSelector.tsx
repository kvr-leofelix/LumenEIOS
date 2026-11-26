import React from 'react';
import { cn } from '../../../lib/utils';
import { GRADES, ROMAN, SUBJECTS, SUBJECT_LABEL, type GradeNumber, type SubjectKey } from '../types';

export function Segmented<T extends string | number>({
  label,
  options,
  value,
  onChange,
  render,
}: {
  label: string;
  options: readonly T[];
  value: T;
  onChange: (v: T) => void;
  render: (v: T) => string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-col gap-1.5">
      <span className="text-[10px] uppercase tracking-wider font-semibold text-content-muted">{label}</span>
      <div className="inline-flex rounded-lg border border-surface-border bg-surface-bg p-0.5">
        {options.map((o) => {
          const selected = o === value;
          return (
            <button
              key={String(o)}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onChange(o)}
              className={cn(
                'px-3.5 py-1.5 text-xs font-semibold rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400',
                selected ? 'bg-navy-800 text-white shadow-sm' : 'text-content-secondary hover:text-content-primary'
              )}
            >
              {render(o)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export const CombinationSelector: React.FC<{
  grade: GradeNumber;
  subject: SubjectKey;
  onChange: (grade: GradeNumber, subject: SubjectKey) => void;
}> = ({ grade, subject, onChange }) => (
  <div className="flex flex-wrap items-end gap-4">
    <Segmented label="Class" options={GRADES} value={grade} onChange={(g) => onChange(g, subject)} render={(g) => `Class ${ROMAN[g]}`} />
    <Segmented label="Subject" options={SUBJECTS} value={subject} onChange={(s) => onChange(grade, s)} render={(s) => SUBJECT_LABEL[s]} />
  </div>
);
