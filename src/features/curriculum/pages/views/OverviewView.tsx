import React from 'react';
import { Lock } from 'lucide-react';
import { Card, CardBody, CardHeader } from '../../../../components/common/Card';
import { cn } from '../../../../lib/utils';
import { useCatalogueService } from '../../api/CatalogueServiceContext';
import { useAsync } from '../../hooks/useAsync';
import { DataSourceBanner } from '../../components/DataSourceBanner';
import { EvidenceButton } from '../../components/EvidenceButton';
import { ErrorState, LoadingState, MissingValue } from '../../components/StateViews';
import { StatusBadge } from '../../components/StatusBadge';
import { CountsBar } from '../../components/CountsBar';
import { eraLabel, languageLabel, RESOURCE_TYPE_LABEL } from '../../labels';
import {
  LANGUAGES,
  LANGUAGE_LABEL,
  type CatalogueResource,
  type CombinationDetail,
  type EvidenceRecord,
  type GradeNumber,
  type SubjectKey,
  type TextbookEdition,
} from '../../types';
import type { OpenEvidence } from '../../types';

const th = 'text-left text-[10px] uppercase tracking-wider font-semibold text-content-muted px-3 py-2 whitespace-nowrap';
const td = 'px-3 py-2.5 align-top text-xs';

/** Screen 6: provisional / placeholder rows are visually distinct (dashed, muted) in addition to their badge. */
const rowClass = (status: string) =>
  cn('border-t border-surface-border', (status === 'PLACEHOLDER' || status === 'UNVERIFIED') && 'bg-gray-50/70 text-content-secondary');

const firstNote = (e: EvidenceRecord) => e.notes[0];

const ResourceTable: React.FC<{
  resources: CatalogueResource[];
  openEvidence: OpenEvidence;
  missingTitle: string;
  caption: string;
}> = ({ resources, openEvidence, missingTitle, caption }) => {
  if (!resources.length) {
    return (
      <p className="text-xs">
        <MissingValue>No records in this category.</MissingValue>
      </p>
    );
  }
  const sorted = [...resources].sort(
    (a, b) => LANGUAGES.indexOf(a.language as never) - LANGUAGES.indexOf(b.language as never) || a.era.localeCompare(b.era)
  );
  return (
    <div className="relative overflow-x-auto -mx-5">
      <table className="w-full min-w-[640px]">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th className={th}>Language</th>
            <th className={th}>Version</th>
            <th className={th}>Official title</th>
            <th className={th}>Status</th>
            <th className={th}>What remains open</th>
            <th className={th}><span className="sr-only">Evidence</span></th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.id} className={rowClass(r.status)} data-testid={`resource-${r.id}`}>
              <td className={cn(td, 'font-medium whitespace-nowrap')}>{languageLabel(r.language)}</td>
              <td className={cn(td, 'whitespace-nowrap')}>{eraLabel(r.era)}</td>
              <td className={td}>
                {r.title ?? <MissingValue>{missingTitle}</MissingValue>}
                {r.edition && <span className="block text-[11px] text-content-muted mt-0.5">{r.edition}</span>}
              </td>
              <td className={td}>
                <StatusBadge status={r.status} />
              </td>
              <td className={cn(td, 'text-[11px] text-content-secondary max-w-xs')}>
                <span className="line-clamp-2">{firstNote(r.evidence) ?? '—'}</span>
              </td>
              <td className={cn(td, 'text-right')}>
                <EvidenceButton onClick={() => openEvidence(r.evidence, `${RESOURCE_TYPE_LABEL[r.resourceType] ?? r.resourceType} · ${languageLabel(r.language)}`)} label={`${r.resourceType} ${r.language}`} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const EditionsTable: React.FC<{ editions: TextbookEdition[]; openEvidence: OpenEvidence }> = ({ editions, openEvidence }) => {
  const sorted = [...editions].sort(
    (a, b) => LANGUAGES.indexOf(a.language as never) - LANGUAGES.indexOf(b.language as never) || (a.partLabel ?? '').localeCompare(b.partLabel ?? '')
  );
  return (
    <div className="relative overflow-x-auto -mx-5">
      <table className="w-full min-w-[720px]">
        <caption className="sr-only">Textbook language editions</caption>
        <thead>
          <tr>
            <th className={th}>Language</th>
            <th className={th}>Textbook title</th>
            <th className={th}>Part</th>
            <th className={th}>Edition</th>
            <th className={th}>Reprint</th>
            <th className={th}>Status</th>
            <th className={th}><span className="sr-only">Evidence</span></th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((e) => (
            <tr key={e.id} className={rowClass(e.status)} data-testid={`edition-${e.id}`}>
              <td className={cn(td, 'font-medium whitespace-nowrap')}>{languageLabel(e.language)}</td>
              <td className={td}>
                {e.isGap ? (
                  <MissingValue>Expected part not identified on the official portal</MissingValue>
                ) : (
                  <>
                    {e.title ?? <MissingValue>Title not verified</MissingValue>}
                    {e.originalScriptTitle && e.originalScriptTitle !== e.title && (
                      <span className="block text-[11px] text-content-muted" lang={e.language}>
                        {e.originalScriptTitle}
                      </span>
                    )}
                    {e.code && <span className="block text-[10px] text-content-muted font-mono">{e.code}</span>}
                  </>
                )}
              </td>
              <td className={cn(td, 'whitespace-nowrap')}>{e.partLabel ?? <span className="text-content-muted">Single volume</span>}</td>
              <td className={td}>{e.edition ?? <MissingValue>Not verified</MissingValue>}</td>
              <td className={cn(td, 'whitespace-nowrap')}>{e.reprint ?? <MissingValue>Not verified</MissingValue>}</td>
              <td className={td}>
                <StatusBadge status={e.status} />
              </td>
              <td className={cn(td, 'text-right')}>
                <EvidenceButton
                  onClick={() => openEvidence(e.evidence, `Textbook edition · ${languageLabel(e.language)}${e.partLabel ? ` · ${e.partLabel}` : ''}`)}
                  label={`edition ${e.id}`}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const LanguageMatrix: React.FC<{ detail: CombinationDetail; openEvidence: OpenEvidence }> = ({ detail, openEvidence }) => {
  const lookup = (id: string) =>
    detail.editions.find((e) => e.id === id)?.evidence ??
    [...detail.frameworks, ...detail.syllabi, ...detail.learningOutcomes].find((r) => r.id === id)?.evidence;
  return (
    <div className="relative overflow-x-auto -mx-5">
      <table className="w-full min-w-[560px]" data-testid="language-matrix">
        <caption className="sr-only">Language availability by resource</caption>
        <thead>
          <tr>
            <th className={th}>Resource</th>
            {LANGUAGES.map((l) => (
              <th key={l} className={th} scope="col">
                {LANGUAGE_LABEL[l]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {detail.languageMatrix.map((row) => (
            <tr key={row.key} className="border-t border-surface-border">
              <th scope="row" className={cn(td, 'text-left font-medium text-content-primary')}>
                {row.label}
              </th>
              {LANGUAGES.map((l) => {
                const c = row.cells[l];
                const ev = c.recordIds[0] ? lookup(c.recordIds[0]) : undefined;
                return (
                  <td key={l} className={td} data-testid={`lang-${row.key}-${l}`}>
                    <div className="flex flex-col items-start gap-1">
                      {ev ? (
                        <button
                          type="button"
                          onClick={() => openEvidence(ev, `${row.label} · ${LANGUAGE_LABEL[l]}`)}
                          className="rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400"
                          aria-label={`${row.label}, ${LANGUAGE_LABEL[l]}: view evidence`}
                        >
                          <StatusBadge status={c.status} />
                        </button>
                      ) : (
                        <StatusBadge status={c.status} />
                      )}
                      {c.label && <span className="text-[10px] text-content-muted">{c.label}</span>}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export const OverviewView: React.FC<{ grade: GradeNumber; subject: SubjectKey; openEvidence: OpenEvidence }> = ({
  grade,
  subject,
  openEvidence,
}) => {
  const service = useCatalogueService();
  const state = useAsync(() => service.getCombination(grade, subject), [service, grade, subject]);

  if (state.status === 'loading') return <LoadingState label="Loading curriculum overview…" />;
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={state.reload} />;
  const d = state.data;

  return (
    <div className="space-y-5">
      <DataSourceBanner meta={d.meta} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Card className="lg:col-span-2">
          <CardHeader title="Source verification" subtitle={`${d.summary.counts.total} curriculum resource records tracked`} />
          <CardBody>
            <CountsBar counts={d.summary.counts} />
          </CardBody>
        </Card>
        <div className="rounded-xl border border-rose-200 bg-rose-50/60 p-4 text-xs text-rose-900 flex gap-3" data-testid="rights-note">
          <Lock className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
          <div>
            <p className="font-semibold flex items-center gap-2">
              Content rights <StatusBadge status="BLOCKED" />
            </p>
            <p className="mt-1 leading-relaxed">{d.rightsNote}</p>
          </div>
        </div>
      </div>

      <Card>
        <CardHeader title="Language availability" subtitle="Each cell shows the weakest status among that language's records. Select a status to see its evidence." />
        <CardBody>
          <LanguageMatrix detail={d} openEvidence={openEvidence} />
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Curriculum framework" subtitle="Stage-level framework. This is not a class-specific syllabus." />
        <CardBody>
          <ResourceTable resources={[...d.frameworks, ...d.guidance]} openEvidence={openEvidence} missingTitle="Language version not verified" caption="Curriculum framework sources" />
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Syllabus availability"
          subtitle="Syllabus documents only. Textbook titles are never shown in place of a syllabus title."
        />
        <CardBody>
          <ResourceTable resources={d.syllabi} openEvidence={openEvidence} missingTitle="No syllabus found in checked NCERT channels" caption="Syllabus availability" />
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Learning-outcome availability"
          subtitle="Official outcome documents. Their wording is not stored or shown because rights are pending."
        />
        <CardBody>
          <ResourceTable resources={d.learningOutcomes} openEvidence={openEvidence} missingTitle="Current class-specific outcomes document not verified" caption="Learning-outcome availability" />
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Textbook editions" subtitle="Language editions and parts. Equivalence between language editions has not been established." />
        <CardBody>
          <EditionsTable editions={d.editions} openEvidence={openEvidence} />
        </CardBody>
      </Card>
    </div>
  );
};
