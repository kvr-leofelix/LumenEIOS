import React, { useEffect, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { Button } from '../../../../components/common/Button';
import { useNcertApi } from '../../api/CatalogueServiceContext';
import type { ApiLanguage, CatalogueNode } from '../../api/contract';
import { citationToEvidence, codeLabel, missingTitleText, nodeKindLabel, nodeTitle, verificationStatus } from '../../api/presentation';
import { useAsync } from '../../hooks/useAsync';
import { EvidenceButton } from '../../components/EvidenceButton';
import { EmptyState, ErrorState, LoadingState, MissingValue } from '../../components/StateViews';
import { StatusBadge } from '../../components/StatusBadge';
import type { OpenEvidence } from '../../types';

const Title: React.FC<{ node: CatalogueNode }> = ({ node }) => {
  const t = nodeTitle(node);
  return t ? <>{t}</> : <MissingValue>{missingTitleText(node)}</MissingValue>;
};

const Citations: React.FC<{ node: CatalogueNode; openEvidence: OpenEvidence }> = ({ node, openEvidence }) =>
  node.citations.length ? (
    <span className="inline-flex flex-wrap gap-1">
      {node.citations.map((c, i) => (
        <EvidenceButton
          key={c.evidence_id}
          onClick={() => openEvidence(citationToEvidence(c), `${nodeKindLabel(node.kind)} · ${nodeTitle(node) ?? node.id}`)}
          label={`${nodeKindLabel(node.kind)} ${nodeTitle(node) ?? node.id}${node.citations.length > 1 ? ` (${i + 1})` : ''}`}
        />
      ))}
    </span>
  ) : (
    <span className="text-[11px] italic text-content-muted">No citation recorded</span>
  );

/** API-mode Screen 3: hierarchy via GET /ncert/nodes/{id}; one level per request, nothing inferred. */
export const ApiExplorerView: React.FC<{ root: CatalogueNode; lang: ApiLanguage; openEvidence: OpenEvidence }> = ({
  root,
  lang,
  openEvidence,
}) => {
  const api = useNcertApi();
  const [trail, setTrail] = useState<{ id: string; label: string }[]>([{ id: root.id, label: nodeTitle(root) ?? 'Subject' }]);
  useEffect(() => setTrail([{ id: root.id, label: nodeTitle(root) ?? 'Subject' }]), [root]);
  const current = trail[trail.length - 1];
  const state = useAsync(
    () => (current.id === root.id && root.requested_language === lang ? Promise.resolve(root) : api.getNode(current.id, lang)),
    [api, current.id, lang, root]
  );

  return (
    <div className="space-y-4">
      <nav aria-label="Hierarchy" className="flex flex-wrap items-center gap-1 text-xs">
        {trail.map((t, i) => (
          <React.Fragment key={t.id}>
            {i > 0 && <ChevronRight className="w-3 h-3 text-content-muted" aria-hidden="true" />}
            {i === trail.length - 1 ? (
              <span aria-current="location" className="font-semibold text-content-primary">
                {t.label}
              </span>
            ) : (
              <button type="button" className="text-teal-700 hover:underline" onClick={() => setTrail(trail.slice(0, i + 1))}>
                {t.label}
              </button>
            )}
          </React.Fragment>
        ))}
      </nav>

      {state.status === 'loading' && <LoadingState label="Loading catalogue node…" />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={state.reload} />}
      {state.status === 'success' && (
        <>
          <div data-testid="explorer-current" className="rounded-xl border border-surface-border bg-white p-4 text-xs space-y-2">
            <p className="text-[10px] uppercase tracking-wider font-semibold text-content-muted">{nodeKindLabel(state.data.kind)}</p>
            <p className="text-sm font-semibold text-navy-900">
              <Title node={state.data} />
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={verificationStatus(state.data.verification)} prefix="Verification" />
              <span className="text-content-secondary">Completeness: {codeLabel(state.data.completeness)}</span>
              <span className="text-content-secondary">
                Text language: {state.data.resolved_language ?? <MissingValue>none in requested language</MissingValue>}
                {state.data.translation_origin && ` · ${codeLabel(state.data.translation_origin)}`}
              </span>
              <Citations node={state.data} openEvidence={openEvidence} />
            </div>
          </div>

          {state.data.children.length === 0 ? (
            <EmptyState title={`No records are stored under this ${nodeKindLabel(state.data.kind).toLowerCase()}`}>
              <p>The backend returned no child records. Chapters and topics are not inferred or filled in.</p>
            </EmptyState>
          ) : (
            <ol className="space-y-2" aria-label="Child records">
              {[...state.data.children]
                .sort((a, b) => a.sequence - b.sequence || a.id.localeCompare(b.id))
                .map((child) => (
                  <li
                    key={child.id}
                    data-testid={`node-${child.id}`}
                    className="rounded-lg border border-surface-border bg-white px-3 py-2.5 text-xs flex flex-wrap items-center justify-between gap-2"
                  >
                    <div>
                      <span className="text-[10px] uppercase tracking-wider font-semibold text-content-muted mr-2">
                        {nodeKindLabel(child.kind)} {child.sequence}
                      </span>
                      <span className="font-semibold text-content-primary">
                        <Title node={child} />
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={verificationStatus(child.verification)} prefix="Verification" />
                      <Citations node={child} openEvidence={openEvidence} />
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setTrail([...trail, { id: child.id, label: nodeTitle(child) ?? nodeKindLabel(child.kind) }])}
                        aria-label={`Open ${nodeKindLabel(child.kind)} ${nodeTitle(child) ?? child.sequence}`}
                      >
                        Open
                      </Button>
                    </div>
                  </li>
                ))}
            </ol>
          )}
        </>
      )}
    </div>
  );
};
