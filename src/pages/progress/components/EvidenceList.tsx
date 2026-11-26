import React from 'react';
import { Badge } from '../../../components/common/Badge';
import {
  ProgressEvent,
  CompetencyEvidence,
  formatPercent,
  formatWhen,
  sourceTypeLabel,
} from '../../../lib/studentProgress';

export function EvidenceList({
  events,
  emptyTitle = 'No verified evidence yet',
  emptyDetail = 'Progress appears here after assessments or reviewed homework are recorded for this student.',
}: {
  events: Array<ProgressEvent | CompetencyEvidence>;
  emptyTitle?: string;
  emptyDetail?: string;
}) {
  if (!events.length) {
    return (
      <div className="p-4 rounded-xl border border-dashed border-surface-border text-xs text-content-secondary">
        <p className="font-semibold text-navy-900 text-sm">{emptyTitle}</p>
        <p className="mt-1 leading-relaxed">{emptyDetail}</p>
      </div>
    );
  }

  return (
    <ul className="space-y-2.5">
      {events.map((event, index) => {
        const key = 'id' in event && event.id ? event.id : `${event.source_type}-${event.source_id}-${index}`;
        const percentage =
          'percentage' in event
            ? event.percentage
            : event.awarded_marks != null && event.max_marks
              ? (100 * event.awarded_marks) / event.max_marks
              : 'dimension_value' in event
                ? event.dimension_value ?? null
                : null;
        return (
          <li
            key={key}
            className="p-3.5 rounded-xl border border-surface-border bg-white flex flex-col sm:flex-row sm:items-center justify-between gap-2"
          >
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" size="sm">
                  {sourceTypeLabel(event.source_type)}
                </Badge>
                {'evaluation_status' in event && event.evaluation_status && (
                  <Badge variant="info" size="sm">
                    {event.evaluation_status}
                  </Badge>
                )}
                {'dimension' in event && event.dimension && (
                  <Badge variant="teal" size="sm">
                    {event.dimension}
                  </Badge>
                )}
              </div>
              <p className="text-sm font-semibold text-navy-900 truncate">
                {event.title || 'Verified learning evidence'}
              </p>
              <p className="text-[11px] text-content-secondary">
                {formatWhen(event.occurred_at)}
                {'subject_name' in event && event.subject_name ? ` · ${event.subject_name}` : ''}
              </p>
            </div>
            <div className="text-right shrink-0">
              <p className="text-lg font-bold text-navy-900 tabular-nums">{formatPercent(percentage)}</p>
              {event.awarded_marks != null && event.max_marks != null && (
                <p className="text-[11px] text-content-secondary">
                  {event.awarded_marks}/{event.max_marks} marks
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
