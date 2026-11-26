import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowRight, Check, Eye, History, Lock, RotateCcw, ShieldCheck, Sparkles, X } from 'lucide-react';
import { Button } from '../../../../components/common/Button';
import { Modal } from '../../../../components/common/Modal';
import { cn } from '../../../../lib/utils';
import type { Role } from '../../../../types';
import { useNcertApi } from '../../api/CatalogueServiceContext';
import {
  REVIEW_RATIONALE_MAX,
  REVIEW_RATIONALE_MIN,
  allowedDecisions,
  type ApiLanguage,
  type ApiReviewDecision,
  type CatalogueNode,
  type Mapping,
  type Review,
} from '../../api/contract';
import { describeApiError, fetchAllPages, validateReviewRequest } from '../../api/ncertApi';
import {
  citationToEvidence,
  codeLabel,
  missingTitleText,
  nodeKindLabel,
  nodeTitle,
  reviewStateStatus,
  verificationStatus,
} from '../../api/presentation';
import { EvidenceButton } from '../../components/EvidenceButton';
import { EmptyState, ErrorState, LoadingState, MissingValue } from '../../components/StateViews';
import { StatusBadge } from '../../components/StatusBadge';
import type { OpenEvidence } from '../../types';

const PAGE_SIZE = 50;

const DECISIONS: { key: ApiReviewDecision; label: string; Icon: React.ElementType; variant: 'teal' | 'danger' | 'outline' }[] = [
  { key: 'APPROVED', label: 'Approve', Icon: Check, variant: 'teal' },
  { key: 'REVISION_REQUESTED', label: 'Request revision', Icon: RotateCcw, variant: 'outline' },
  { key: 'REJECTED', label: 'Reject', Icon: X, variant: 'danger' },
];
const DECISION_LABEL: Record<string, string> = { APPROVED: 'Approve', REJECTED: 'Reject', REVISION_REQUESTED: 'Request revision' };
const DECISION_PAST: Record<string, string> = { APPROVED: 'Approved', REJECTED: 'Rejected', REVISION_REQUESTED: 'Revision requested' };

const ROLE_LABEL: Record<string, string> = {
  SOURCE_ENDPOINT: 'Topic endpoint',
  DESTINATION_ENDPOINT: 'Outcome endpoint',
  RELATIONSHIP: 'Relationship',
};

const Detail: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div>
    <dt className="text-[10px] uppercase tracking-wider font-semibold text-content-muted">{label}</dt>
    <dd className="text-xs text-content-primary mt-0.5 leading-relaxed">{children}</dd>
  </div>
);

const REDACTED = 'Not shown. Free text stays hidden until all evidence is cleared for metadata, or none was recorded.';
const Text: React.FC<{ value: string | null }> = ({ value }) => (value ? <>{value}</> : <MissingValue>{REDACTED}</MissingValue>);

const Endpoint: React.FC<{ node: CatalogueNode; label: string; dashed?: boolean; openEvidence: OpenEvidence }> = ({
  node,
  label,
  dashed,
  openEvidence,
}) => {
  const title = nodeTitle(node);
  return (
    <div className={cn('rounded-lg border p-3', dashed ? 'border-dashed border-gray-300' : 'border-surface-border')}>
      <p className="text-[10px] uppercase tracking-wider font-semibold text-content-muted">
        {label} · {nodeKindLabel(node.kind)}
      </p>
      <p className="text-sm font-semibold text-navy-900 mt-0.5">{title ?? <MissingValue>{missingTitleText(node)}</MissingValue>}</p>
      <div className="flex flex-wrap items-center gap-2 mt-2">
        <StatusBadge status={verificationStatus(node.verification)} prefix="Verification" />
        {node.citations.length ? (
          node.citations.map((c) => (
            <EvidenceButton
              key={c.evidence_id}
              onClick={() => openEvidence(citationToEvidence(c), `${label} · ${title ?? node.id}`)}
              label={`${label.toLowerCase()} ${c.evidence_id}`}
            />
          ))
        ) : (
          <span className="text-[11px] italic text-content-muted">No endpoint citation</span>
        )}
      </div>
    </div>
  );
};

const ReviewHistory: React.FC<{ mappingId: string; version: number }> = ({ mappingId, version }) => {
  const api = useNcertApi();
  const [state, setState] = useState<{ status: 'loading' | 'error' | 'success'; items: Review[]; error?: unknown }>({
    status: 'loading',
    items: [],
  });
  useEffect(() => {
    let live = true;
    setState({ status: 'loading', items: [] });
    fetchAllPages((offset) => api.listReviews(mappingId, { limit: 100, offset })).then(
      (items) => live && setState({ status: 'success', items }),
      (error) => live && setState({ status: 'error', items: [], error })
    );
    return () => {
      live = false;
    };
  }, [api, mappingId, version]);

  if (state.status === 'loading') return <LoadingState label="Loading review history…" />;
  if (state.status === 'error') return <ErrorState error={state.error} />;
  if (!state.items.length) return <p className="text-[11px] italic text-content-muted">No review decisions recorded yet.</p>;
  return (
    <ol className="space-y-1.5" data-testid={`history-${mappingId}`}>
      {state.items.map((r) => (
        <li key={r.id} className="rounded-lg border border-surface-border px-3 py-2">
          <strong>
            Revision {r.revision}: {DECISION_PAST[r.decision] ?? codeLabel(r.decision)}
          </strong>{' '}
          by reviewer <code className="text-[10px]">{r.reviewer_id}</code> · {new Date(r.reviewed_at).toLocaleString()}
          <p className="text-content-secondary mt-0.5">“{r.rationale}”</p>
        </li>
      ))}
    </ol>
  );
};

const MappingCard: React.FC<{
  m: Mapping;
  canReview: boolean;
  historyVersion: number;
  openEvidence: OpenEvidence;
  onDecide: (m: Mapping, d: ApiReviewDecision) => void;
}> = ({ m, canReview, historyVersion, openEvidence, onDecide }) => {
  const [showHistory, setShowHistory] = useState(false);
  const approved = m.human_review_state === 'APPROVED';
  const aiSuggested = m.creation_method === 'AI_SUGGESTED';
  const editable = m.publication_status === 'DRAFT';
  const options = DECISIONS.filter((d) => allowedDecisions(m.human_review_state).includes(d.key));
  const srcTitle = nodeTitle(m.source) ?? 'untitled topic';
  const dstTitle = nodeTitle(m.destination) ?? 'untitled outcome';

  return (
    <article
      data-testid={`api-mapping-${m.id}`}
      aria-label={`Mapping ${srcTitle} to ${dstTitle}`}
      className={cn('rounded-xl bg-white shadow-subtle overflow-hidden border-2', approved ? 'border-surface-border' : 'border-dashed border-amber-300')}
    >
      <div className={cn('px-5 py-2 text-[11px] font-semibold flex flex-wrap items-center gap-2 justify-between', approved ? 'bg-surface-bg' : 'bg-amber-50 text-amber-900')}>
        <span className="flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />
          {aiSuggested ? 'AI-suggested mapping' : `Mapping (${codeLabel(m.creation_method)})`}
          {approved ? ' · approved by an editor (does not verify, publish or clear rights)' : '. Not approved.'}
        </span>
        <span className="flex flex-wrap gap-1.5">
          <StatusBadge status={verificationStatus(m.verification)} prefix="Verification" />
          <StatusBadge status={reviewStateStatus(m.human_review_state)} prefix="Review" />
        </span>
      </div>

      <div className="p-5 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] gap-3 items-stretch">
          <Endpoint node={m.source} label="Topic" openEvidence={openEvidence} />
          <div className="flex md:flex-col items-center justify-center text-content-muted text-[10px] gap-1">
            <ArrowRight className="w-4 h-4 rotate-90 md:rotate-0" aria-hidden="true" />
            <span>{codeLabel(m.relationship_type)}</span>
          </div>
          <Endpoint node={m.destination} label="Learning outcome" dashed openEvidence={openEvidence} />
        </div>
        <p className="text-[11px] text-content-muted italic">Official outcome wording is never returned by the API. Only catalogue titles are shown.</p>

        <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 rounded-lg bg-surface-bg/70 border border-surface-border p-4">
          <Detail label="Stored rationale">
            <Text value={m.rationale} />
          </Detail>
          <Detail label="Coverage assessment">
            <Text value={m.coverage_assessment} />
          </Detail>
          <Detail label="Overlapping outcomes">
            <Text value={m.overlapping_outcomes} />
          </Detail>
          <Detail label="Uncovered outcomes">
            <Text value={m.uncovered_outcomes} />
          </Detail>
          <Detail label="Release and permissions">
            Release {codeLabel(m.publication_status)} · metadata permissions {codeLabel(m.permissions_status)}
          </Detail>
          <Detail label="Applicability and recovery">
            Current-curriculum applicability {codeLabel(m.curriculum_applicability)} · recovery eligible: no
          </Detail>
          <Detail label="Relationship evidence">
            {m.evidence.length ? (
              <span className="flex flex-wrap gap-1">
                {m.evidence.map((e) => (
                  <EvidenceButton
                    key={`${e.role}-${e.citation.evidence_id}`}
                    onClick={() => openEvidence(citationToEvidence(e.citation), `${ROLE_LABEL[e.role] ?? codeLabel(e.role)} evidence`)}
                    label={`${ROLE_LABEL[e.role] ?? codeLabel(e.role)} ${e.citation.evidence_id}`}
                  />
                ))}
              </span>
            ) : (
              <MissingValue>No relationship evidence recorded</MissingValue>
            )}
          </Detail>
          <Detail label="Review revision">
            {m.revision}
            {m.latest_review && (
              <>
                {' '}
                · last: {DECISION_PAST[m.latest_review.decision] ?? codeLabel(m.latest_review.decision)} on{' '}
                {new Date(m.latest_review.reviewed_at).toLocaleString()}
              </>
            )}
          </Detail>
        </dl>

        <div className="text-xs">
          <button
            type="button"
            aria-expanded={showHistory}
            onClick={() => setShowHistory((s) => !s)}
            className="inline-flex items-center gap-1 text-[11px] font-semibold text-teal-700 hover:text-teal-900"
          >
            <History className="w-3.5 h-3.5" aria-hidden="true" />
            {showHistory ? 'Hide review history' : 'Show review history'}
          </button>
          {showHistory && (
            <div className="mt-2">
              <ReviewHistory mappingId={m.id} version={historyVersion} />
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3 pt-1">
          {!canReview ? (
            <p className="text-[11px] text-content-secondary flex items-center gap-1.5">
              <Eye className="w-3.5 h-3.5" aria-hidden="true" /> View only. Only an administrator can record global catalogue review decisions.
            </p>
          ) : !editable ? (
            <p className="text-[11px] text-content-secondary flex items-center gap-1.5">
              <Lock className="w-3.5 h-3.5" aria-hidden="true" /> Read-only: decisions can only be recorded on a draft release.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2" role="group" aria-label={`Review ${srcTitle}`}>
              {options.map(({ key, label, Icon, variant }) => (
                <Button key={key} size="sm" variant={variant} icon={<Icon className="w-3.5 h-3.5" />} onClick={() => onDecide(m, key)}>
                  {label}
                </Button>
              ))}
            </div>
          )}
        </div>
      </div>
    </article>
  );
};

/** API-mode Screen 5: GET /ncert/mappings, persistent POST /ncert/mappings/{id}/reviews with expected_revision. */
export const ApiReviewView: React.FC<{
  releaseId: string;
  subjectNodeId: string;
  lang: ApiLanguage;
  openEvidence: OpenEvidence;
  canReview: boolean;
  role: Role;
}> = ({ releaseId, subjectNodeId, lang, openEvidence, canReview, role }) => {
  const api = useNcertApi();
  const [items, setItems] = useState<Mapping[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [load, setLoad] = useState<{ status: 'loading' | 'error' | 'success' | 'more'; error?: unknown }>({ status: 'loading' });
  const [historyVersion, setHistoryVersion] = useState<Record<string, number>>({});
  const [pending, setPending] = useState<{ mapping: Mapping; decision: ApiReviewDecision } | null>(null);
  const [rationale, setRationale] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [announcement, setAnnouncement] = useState('');
  const requestId = useRef(0);

  const loadPage = useCallback(
    (offset: number) => {
      const id = ++requestId.current;
      setLoad({ status: offset === 0 ? 'loading' : 'more' });
      api.listMappings({ releaseId, subjectNodeId, language: lang, limit: PAGE_SIZE, offset }).then(
        (page) => {
          if (id !== requestId.current) return;
          setItems((prev) => (offset === 0 ? page.items : [...prev, ...page.items]));
          setNextOffset(page.next_offset);
          setLoad({ status: 'success' });
        },
        (error) => id === requestId.current && setLoad({ status: 'error', error })
      );
    },
    [api, releaseId, subjectNodeId, lang]
  );

  useEffect(() => loadPage(0), [loadPage]);

  const replace = (m: Mapping) => setItems((list) => list.map((x) => (x.id === m.id ? m : x)));
  const bumpHistory = (id: string) => setHistoryVersion((v) => ({ ...v, [id]: (v[id] ?? 0) + 1 }));

  const openDecision = (mapping: Mapping, decision: ApiReviewDecision) => {
    setPending({ mapping, decision });
    setRationale('');
    setFormError(null);
  };
  const close = () => !submitting && setPending(null);

  const submit = async () => {
    if (!pending) return;
    const body = { decision: pending.decision, rationale, expected_revision: pending.mapping.revision };
    const problem = validateReviewRequest(body);
    if (problem) {
      setFormError(problem);
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const review = await api.submitReview(pending.mapping.id, body);
      // Contract: refetch mapping and history after a write.
      const fresh = await api.getMapping(pending.mapping.id, lang);
      replace(fresh);
      bumpHistory(fresh.id);
      setAnnouncement(
        `${DECISION_PAST[review.decision]} recorded as revision ${review.revision} for ${nodeTitle(fresh.source) ?? 'this mapping'}.`
      );
      setPending(null);
    } catch (err) {
      const e = describeApiError(err);
      if (e.code === 'STALE_REVISION') {
        try {
          const fresh = await api.getMapping(pending.mapping.id, lang);
          replace(fresh);
          bumpHistory(fresh.id);
          setPending({ mapping: fresh, decision: pending.decision });
        } catch {
          /* keep original error message */
        }
      }
      setFormError(`${e.status === 403 ? 'Not permitted: ' : ''}${e.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  if (load.status === 'loading') return <LoadingState label="Loading candidate mappings…" />;
  if (load.status === 'error' && items.length === 0) return <ErrorState error={load.error} onRetry={() => loadPage(0)} />;
  const awaiting = items.filter((m) => m.human_review_state === 'AWAITING_REVIEW').length;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-amber-200 bg-amber-50/70 px-4 py-3 text-xs text-amber-950 space-y-1" data-testid="review-intro">
        <p className="font-semibold flex items-center gap-1.5">
          <Sparkles className="w-4 h-4" aria-hidden="true" /> {items.length} topic-to-outcome mapping{items.length === 1 ? '' : 's'} loaded ·{' '}
          {awaiting} awaiting review
        </p>
        <p>
          Approving a mapping is an editorial decision only. It does not verify sources, clear rights, publish the release or make the
          mapping applicable to the current curriculum. Check the evidence for both ends before you decide.
        </p>
      </div>

      <p className="text-[11px] text-content-secondary flex items-center gap-1.5" data-testid="review-permission">
        {canReview ? <ShieldCheck className="w-3.5 h-3.5 text-teal-600" aria-hidden="true" /> : <Eye className="w-3.5 h-3.5" aria-hidden="true" />}
        Signed in as <strong className="capitalize">{role}</strong>.{' '}
        {canReview ? 'You can record decisions on draft releases. The backend checks your role on every request.' : 'You can view mappings but not review them.'}
      </p>

      <div role="status" aria-live="polite" className="sr-only">
        {announcement}
      </div>
      {announcement && (
        <p className="text-xs rounded-lg border border-teal-200 bg-teal-50 text-teal-900 px-3 py-2" data-testid="review-announcement">
          {announcement}
        </p>
      )}

      {items.length === 0 ? (
        <EmptyState title="No topic-to-outcome mappings are recorded for this subject in this release">
          <p>The backend returned no mappings. Nothing is generated to fill the gap.</p>
        </EmptyState>
      ) : (
        items.map((m) => (
          <MappingCard
            key={m.id}
            m={m}
            canReview={canReview}
            historyVersion={historyVersion[m.id] ?? 0}
            openEvidence={openEvidence}
            onDecide={openDecision}
          />
        ))
      )}

      {load.status === 'error' && items.length > 0 && <ErrorState error={load.error} onRetry={() => loadPage(items.length)} />}
      {nextOffset !== null && load.status !== 'error' && (
        <Button variant="outline" size="sm" loading={load.status === 'more'} onClick={() => loadPage(nextOffset)}>
          Load more mappings
        </Button>
      )}

      <Modal
        isOpen={!!pending}
        onClose={close}
        title={pending ? `${DECISION_LABEL[pending.decision]} candidate mapping` : ''}
        subtitle={
          pending
            ? `${nodeTitle(pending.mapping.source) ?? 'Untitled topic'} → ${nodeTitle(pending.mapping.destination) ?? 'untitled outcome'} · revision ${pending.mapping.revision}`
            : undefined
        }
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={close} disabled={submitting}>
              Cancel
            </Button>
            <Button size="sm" variant={pending?.decision === 'REJECTED' ? 'danger' : 'teal'} loading={submitting} onClick={submit}>
              Record decision
            </Button>
          </>
        }
      >
        <div className="space-y-3 text-xs">
          <label htmlFor="api-review-rationale" className="block font-semibold text-content-primary">
            Decision rationale <span className="text-rose-600">(required)</span>
          </label>
          <textarea
            id="api-review-rationale"
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            rows={4}
            maxLength={REVIEW_RATIONALE_MAX}
            aria-invalid={!!formError}
            aria-describedby="api-review-rationale-help api-review-rationale-error"
            className="w-full rounded-lg border border-surface-border p-2.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal-400"
            placeholder="Explain the evidence that supports this decision, and what is still missing."
          />
          <p id="api-review-rationale-help" className="text-content-muted">
            {REVIEW_RATIONALE_MIN}–{REVIEW_RATIONALE_MAX} characters. The backend records your account ID and the server time, and
            refuses the decision if the mapping changed since you loaded it.
            {pending?.decision === 'APPROVED' &&
              ' Approval also needs complete endpoint and relationship evidence with metadata rights cleared.'}
          </p>
          {formError && (
            <p id="api-review-rationale-error" role="alert" className="text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
              {formError}
            </p>
          )}
        </div>
      </Modal>
    </div>
  );
};
