import React from 'react';
import { Badge } from '../../../components/common/Badge';
import {
  SubjectTimeline,
  TimelineCheckpoint,
  evidenceStatusFromProfile,
  evidenceStatusLabel,
  evidenceStatusVariant,
  formatPercent,
} from '../../../lib/studentProgress';

function CheckpointCard({
  checkpoint,
  onSelect,
  selected,
}: {
  checkpoint: TimelineCheckpoint;
  onSelect?: (checkpoint: TimelineCheckpoint) => void;
  selected?: boolean;
}) {
  const evidence = evidenceStatusFromProfile(checkpoint.status);
  return (
    <button
      type="button"
      onClick={() => onSelect?.(checkpoint)}
      className={`text-left p-3 rounded-xl border transition-colors w-full min-w-[11rem] ${
        selected
          ? 'border-teal-500 bg-teal-50/60'
          : 'border-surface-border bg-white hover:border-surface-borderHover'
      }`}
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <p className="text-xs font-bold text-navy-900">{checkpoint.period_label}</p>
        <Badge variant={evidenceStatusVariant(evidence)} size="sm">
          {evidenceStatusLabel(evidence)}
        </Badge>
      </div>
      <p className="text-xl font-bold text-navy-900 tabular-nums">
        {formatPercent(checkpoint.scores?.overall ?? null)}
      </p>
      <p className="text-[11px] text-content-secondary mt-1">
        {checkpoint.evidence_count} evidence item{checkpoint.evidence_count === 1 ? '' : 's'}
        {checkpoint.coverage
          ? ` · ${checkpoint.coverage.dimensions_present}/${checkpoint.coverage.dimensions_total} dimensions`
          : ''}
      </p>
    </button>
  );
}

export function TimelinePanel({
  timeline,
  selectedId,
  onSelect,
}: {
  timeline: SubjectTimeline | null;
  selectedId?: string | null;
  onSelect?: (checkpoint: TimelineCheckpoint) => void;
}) {
  const months = timeline?.months || [];
  const terms = timeline?.terms || [];

  if (!months.length && !terms.length) {
    return (
      <div className="p-4 rounded-xl border border-dashed border-surface-border text-xs text-content-secondary">
        <p className="font-semibold text-navy-900 text-sm">No academic-period checkpoints yet</p>
        <p className="mt-1 leading-relaxed">
          Monthly and term timelines appear after verified subject evidence is dated into the school calendar.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {terms.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-bold uppercase tracking-wider text-content-secondary">Terms</h4>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {terms.map((checkpoint) => (
              <CheckpointCard
                key={`term-${checkpoint.period_id}`}
                checkpoint={checkpoint}
                selected={selectedId === checkpoint.period_id}
                onSelect={onSelect}
              />
            ))}
          </div>
        </div>
      )}
      {months.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-bold uppercase tracking-wider text-content-secondary">Months</h4>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {months.map((checkpoint) => (
              <CheckpointCard
                key={`month-${checkpoint.period_id}`}
                checkpoint={checkpoint}
                selected={selectedId === checkpoint.period_id}
                onSelect={onSelect}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
