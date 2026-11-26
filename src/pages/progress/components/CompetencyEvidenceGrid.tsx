import React from 'react';
import { Badge } from '../../../components/common/Badge';
import {
  COMPETENCY_DIMS,
  COMPETENCY_LABELS,
  CompetencyDim,
  EvidenceStatus,
  SubjectCompetencyProfile,
  evidenceStatusFromProfile,
  evidenceStatusLabel,
  evidenceStatusVariant,
  formatPercent,
} from '../../../lib/studentProgress';

export function CompetencyEvidenceGrid({
  profile,
  current,
}: {
  profile?: SubjectCompetencyProfile | null;
  current?: Partial<Record<CompetencyDim, number | null>> | null;
}) {
  const status = profile?.status || 'unavailable';
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {COMPETENCY_DIMS.map((dim) => {
        const score = profile?.scores?.[dim] ?? current?.[dim] ?? null;
        const evidence: EvidenceStatus = profile
          ? evidenceStatusFromProfile(status, dim, profile)
          : score == null
            ? 'insufficient'
            : 'demonstrated';
        const count = profile?.dimension_evidence_counts?.[dim] ?? null;
        return (
          <div
            key={dim}
            className="p-3.5 rounded-xl border border-surface-border bg-surface-bg space-y-2"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-[11px] font-bold uppercase tracking-wider text-content-secondary">
                  {dim}
                </p>
                <p className="text-sm font-semibold text-navy-900">{COMPETENCY_LABELS[dim]}</p>
              </div>
              <Badge variant={evidenceStatusVariant(evidence)} size="sm">
                {evidenceStatusLabel(evidence)}
              </Badge>
            </div>
            <p className="text-2xl font-bold text-navy-900 tabular-nums">{formatPercent(score)}</p>
            <p className="text-[11px] text-content-secondary">
              {count == null
                ? 'Score from the live competency record when subject evidence is not scoped.'
                : count === 0
                  ? 'No verified subject evidence for this dimension yet.'
                  : `${count} verified evidence point${count === 1 ? '' : 's'} for this dimension.`}
            </p>
          </div>
        );
      })}
    </div>
  );
}
