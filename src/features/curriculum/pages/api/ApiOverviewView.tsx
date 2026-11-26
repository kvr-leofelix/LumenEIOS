import React from 'react';
import { Info } from 'lucide-react';
import { Card, CardBody, CardHeader } from '../../../../components/common/Card';
import { useNcertApi } from '../../api/CatalogueServiceContext';
import type { ApiLanguage, CatalogueNode, Resource } from '../../api/contract';
import { citationToEvidence, codeLabel, docTypeLabel } from '../../api/presentation';
import { useAsync } from '../../hooks/useAsync';
import { EvidenceButton } from '../../components/EvidenceButton';
import { ErrorState, LoadingState, MissingValue } from '../../components/StateViews';
import { StatusBadge } from '../../components/StatusBadge';
import { toDisplayStatus } from '../../status';
import type { OpenEvidence } from '../../types';

const REQUIRED_TYPES = ['FRAMEWORK', 'SYLLABUS', 'LEARNING_OUTCOMES', 'TEXTBOOK'];

const STATUS_TEXT: Record<string, string> = {
  NO_RELEASE_SELECTED: 'No release selected.',
  SUBJECT_NOT_SELECTED: 'No subject selected.',
  SUBJECT_NOT_FOUND: 'This subject was not found for this class in the selected release.',
  AVAILABLE: 'Evidence is registered for all four resource types.',
  PARTIAL: 'Partial: some resource types have no registered evidence, or some evidence is not yet cleared for metadata.',
};

const ResourceRow: React.FC<{ r: Resource; openEvidence: OpenEvidence }> = ({ r, openEvidence }) => (
  <li data-testid={`resource-${r.source_id}`} className="rounded-lg border border-surface-border p-3 text-xs space-y-1.5">
    <div className="flex flex-wrap items-center gap-2 justify-between">
      <code className="text-[11px] text-content-secondary">Source {r.source_id}</code>
      <span className="flex flex-wrap gap-1.5">
        <StatusBadge status={toDisplayStatus(r.source_verification)} prefix="Source check" />
        {r.citations.some((c) => !c.metadata_visible) && <StatusBadge status="BLOCKED" prefix="Metadata" />}
      </span>
    </div>
    <p className="text-content-secondary">
      Language: {r.language ?? <MissingValue>not recorded</MissingValue>} · Rights: {codeLabel(r.rights_status)}
    </p>
    <ul className="space-y-1">
      {r.citations.map((c) => (
        <li key={c.evidence_id} className="flex items-center justify-between gap-2">
          <span>
            {c.title ?? <MissingValue>{c.metadata_visible ? 'Title not recorded' : 'Title redacted pending rights clearance'}</MissingValue>}
            {c.locator && <span className="text-content-muted"> · {c.locator}</span>}
          </span>
          <EvidenceButton
            onClick={() => openEvidence(citationToEvidence(c), `${docTypeLabel(r.document_type)} · source ${r.source_id}`)}
            label={`${docTypeLabel(r.document_type)} ${c.evidence_id}`}
          />
        </li>
      ))}
    </ul>
  </li>
);

/** API-mode Screens 2 and 6: GET /ncert/availability for the selected subject identity. */
export const ApiOverviewView: React.FC<{
  grade: number;
  releaseId: string;
  subject: CatalogueNode;
  lang: ApiLanguage;
  openEvidence: OpenEvidence;
}> = ({ grade, releaseId, subject, lang, openEvidence }) => {
  const api = useNcertApi();
  const state = useAsync(
    () => api.getAvailability({ grade, releaseId, subjectIdentityId: subject.identity_id, language: lang }),
    [api, grade, releaseId, subject.identity_id, lang]
  );

  if (state.status === 'loading') return <LoadingState label="Loading source availability…" />;
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={state.reload} />;
  const a = state.data;
  const types = [...REQUIRED_TYPES, ...Array.from(new Set(a.resources.map((r) => r.document_type))).filter((t) => !REQUIRED_TYPES.includes(t))];

  return (
    <div className="space-y-5">
      <div data-testid="availability-status" className="rounded-xl border border-surface-border bg-white px-4 py-3 text-xs space-y-1.5">
        <p className="font-semibold text-content-primary">
          Availability status: <span data-availability={a.status}>{codeLabel(a.status)}</span>
        </p>
        <p className="text-content-secondary">{STATUS_TEXT[a.status] ?? 'Status not recognised; treat as unverified.'}</p>
        <p className="text-content-secondary">
          Metadata permissions: <strong>{codeLabel(a.permissions_status)}</strong> · Current-curriculum applicability:{' '}
          <strong>{codeLabel(a.applicability)}</strong>
        </p>
        <p className="flex items-start gap-1.5 text-content-muted">
          <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" aria-hidden="true" />
          These figures describe evidence registered in this release. They do not show whether the official publication is complete.
          A missing type does not mean the document is officially unavailable, unpublished or not applicable.
        </p>
      </div>

      {types.map((t) => {
        const resources = a.resources.filter((r) => r.document_type === t);
        const missing = a.missing_resource_types.includes(t) || resources.length === 0;
        return (
          <Card key={t}>
            <CardHeader title={`${docTypeLabel(t)} sources`} subtitle={`Requested language: ${lang}`} />
            <CardBody>
              {missing ? (
                <div data-testid={`missing-${t}`} className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-gray-300 p-3 text-xs">
                  <StatusBadge status="PLACEHOLDER" />
                  <span className="text-content-secondary">
                    No registered evidence in this release. This does not mean the document is officially unavailable.
                  </span>
                </div>
              ) : (
                <ul className="space-y-2">
                  {resources.map((r) => (
                    <ResourceRow key={r.source_id} r={r} openEvidence={openEvidence} />
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>
        );
      })}
    </div>
  );
};
