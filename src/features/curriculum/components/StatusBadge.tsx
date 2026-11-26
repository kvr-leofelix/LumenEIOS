import React from 'react';
import {
  CheckCircle2,
  CircleDashed,
  HelpCircle,
  FileQuestion,
  Hourglass,
  Lock,
  BadgeCheck,
  XCircle,
  RotateCcw,
} from 'lucide-react';
import { cn } from '../../../lib/utils';
import { STATUS_DESCRIPTION, STATUS_LABEL } from '../status';
import type { DisplayStatus } from '../types';

const STYLES: Record<DisplayStatus, { cls: string; Icon: React.ElementType }> = {
  VERIFIED: { cls: 'bg-emerald-50 text-emerald-800 border-emerald-300', Icon: CheckCircle2 },
  PARTIALLY_VERIFIED: { cls: 'bg-sky-50 text-sky-800 border-sky-300', Icon: CircleDashed },
  UNVERIFIED: { cls: 'bg-gray-50 text-gray-700 border-gray-300', Icon: HelpCircle },
  PLACEHOLDER: { cls: 'bg-white text-gray-600 border-gray-400 border-dashed', Icon: FileQuestion },
  AWAITING_REVIEW: { cls: 'bg-amber-50 text-amber-900 border-amber-300', Icon: Hourglass },
  BLOCKED: { cls: 'bg-rose-50 text-rose-800 border-rose-300', Icon: Lock },
  APPROVED: { cls: 'bg-teal-50 text-teal-800 border-teal-400', Icon: BadgeCheck },
  REJECTED: { cls: 'bg-rose-50 text-rose-800 border-rose-300', Icon: XCircle },
  REVISION_REQUESTED: { cls: 'bg-violet-50 text-violet-800 border-violet-300', Icon: RotateCcw },
};

export const StatusBadge: React.FC<{
  status: DisplayStatus;
  size?: 'sm' | 'md';
  /** Optional prefix, e.g. "Source" or "Reviewer". */
  prefix?: string;
  className?: string;
}> = ({ status, size = 'sm', prefix, className }) => {
  const { cls, Icon } = STYLES[status];
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md border font-semibold uppercase tracking-wide whitespace-nowrap',
        size === 'sm' ? 'text-[10px] px-1.5 py-0.5' : 'text-[11px] px-2 py-1',
        cls,
        className
      )}
      title={STATUS_DESCRIPTION[status]}
      data-status={status}
    >
      <Icon className={size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5'} aria-hidden="true" />
      {prefix && <span className="font-medium normal-case tracking-normal opacity-80">{prefix}:</span>}
      {STATUS_LABEL[status]}
    </span>
  );
};

/** Legend so the meaning of each status is visible during a demo. */
export const StatusLegend: React.FC<{ statuses?: DisplayStatus[] }> = ({
  statuses = ['VERIFIED', 'PARTIALLY_VERIFIED', 'UNVERIFIED', 'PLACEHOLDER', 'AWAITING_REVIEW'],
}) => (
  <dl className="flex flex-wrap gap-x-4 gap-y-2 text-[11px] text-content-secondary">
    {statuses.map((s) => (
      <div key={s} className="flex items-center gap-1.5">
        <dt>
          <StatusBadge status={s} />
        </dt>
        <dd>{STATUS_DESCRIPTION[s]}</dd>
      </div>
    ))}
  </dl>
);
