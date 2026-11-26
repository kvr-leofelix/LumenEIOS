import React from 'react';
import { Database, FlaskConical } from 'lucide-react';
import type { CatalogueMeta } from '../types';

/** Always-visible disclosure of where the data comes from and the release state. */
export const DataSourceBanner: React.FC<{ meta: CatalogueMeta }> = ({ meta }) => {
  const isMock = meta.dataSource === 'mock';
  return (
    <div
      data-testid="data-source-banner"
      className={
        isMock
          ? 'rounded-xl border border-violet-200 bg-violet-50/70 px-4 py-3 text-xs text-violet-900 flex gap-3 items-start'
          : 'rounded-xl border border-teal-200 bg-teal-50/70 px-4 py-3 text-xs text-teal-900 flex gap-3 items-start'
      }
    >
      {isMock ? (
        <FlaskConical className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
      ) : (
        <Database className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
      )}
      <div className="space-y-0.5">
        <p className="font-semibold">
          {isMock
            ? 'Data source: research snapshot (mock). Not connected to the backend API.'
            : 'Data source: LumenEIOS backend API'}
        </p>
        <p>
          {meta.snapshotLabel}
          {meta.researchAccessedOn && <> · sources accessed {meta.researchAccessedOn}</>}
          {' · '}Catalogue release: <strong>{meta.releaseId ?? 'none published'}</strong> ({meta.releaseStatus.replace(/_/g, ' ').toLowerCase()})
        </p>
        {isMock && (
          <p>Review decisions are kept in this browser session only. They are not saved to any server.</p>
        )}
      </div>
    </div>
  );
};
