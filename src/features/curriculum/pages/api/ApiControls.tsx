import React from 'react';
import { Database } from 'lucide-react';
import { Segmented } from '../../components/CombinationSelector';
import { GRADES, ROMAN, type GradeNumber } from '../../types';
import { API_LANGUAGES, type ApiLanguage, type Release } from '../../api/contract';
import { API_LANGUAGE_LABEL, codeLabel } from '../../api/presentation';

export const parseLanguage = (v: string | null): ApiLanguage =>
  v === 'hi' || v === 'ur' ? v : 'en';

export const GradeSelector: React.FC<{ value: GradeNumber; onChange: (g: GradeNumber) => void }> = ({ value, onChange }) => (
  <Segmented label="Class" options={GRADES} value={value} onChange={onChange} render={(g) => `Class ${ROMAN[g]}`} />
);

export const LanguageSelector: React.FC<{ value: ApiLanguage; onChange: (l: ApiLanguage) => void }> = ({ value, onChange }) => (
  <Segmented label="Language" options={API_LANGUAGES} value={value} onChange={onChange} render={(l) => API_LANGUAGE_LABEL[l]} />
);

/** Always-visible disclosure that data comes from the live backend, and which release (if any) is selected. */
export const ApiSourceBanner: React.FC<{ release: Release | null }> = ({ release }) => (
  <div
    data-testid="data-source-banner"
    className="rounded-xl border border-teal-200 bg-teal-50/70 px-4 py-3 text-xs text-teal-900 flex gap-3 items-start"
  >
    <Database className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
    <div className="space-y-0.5">
      <p className="font-semibold">Data source: LumenEIOS backend API (/api/v1/ncert)</p>
      <p>
        Catalogue release:{' '}
        {release ? (
          <>
            <strong>{release.release_key}</strong> · {release.edition}
            {release.academic_year ? ` · ${release.academic_year}` : ''} · status <strong>{codeLabel(release.status)}</strong>
          </>
        ) : (
          <strong>none selected</strong>
        )}
      </p>
      <p>Only records stored in the backend catalogue are shown. Missing records are shown as missing, never filled in.</p>
    </div>
  </div>
);

export const ReleaseStatusPill: React.FC<{ status: string }> = ({ status }) => (
  <span
    data-release-status={status}
    className={
      'inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ' +
      (status === 'PUBLISHED'
        ? 'bg-teal-50 text-teal-800 border-teal-300'
        : status === 'DRAFT'
        ? 'bg-amber-50 text-amber-900 border-amber-300 border-dashed'
        : 'bg-gray-50 text-gray-700 border-gray-300')
    }
  >
    {status === 'DRAFT' ? 'Draft (not published)' : codeLabel(status)}
  </span>
);
