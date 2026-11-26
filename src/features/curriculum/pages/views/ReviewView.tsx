import React, { useState } from 'react';
import { ArrowRight, Bot, Check, Eye, RotateCcw, ShieldCheck, Sparkles, X } from 'lucide-react';
import { Button } from '../../../../components/common/Button';
import { Modal } from '../../../../components/common/Modal';
import { cn } from '../../../../lib/utils';
import type { Role } from '../../../../types';
import { useCatalogueService } from '../../api/CatalogueServiceContext';
import { MIN_RATIONALE_LENGTH, validateReviewInput } from '../../api/catalogueService';
import { allowedDecisions } from '../../api/contract';
import { describeApiError } from '../../api/ncertApi';
import { useAsync } from '../../hooks/useAsync';
import { EvidenceButton } from '../../components/EvidenceButton';
import { EmptyState, ErrorState, LoadingState } from '../../components/StateViews';
import { StatusBadge } from '../../components/StatusBadge';
import { humanize } from '../../labels';
import type { CandidateMapping, GradeNumber, ReviewDecision, SubjectKey } from '../../types';
import type { OpenEvidence } from '../../types';

const DECISIONS: { key: ReviewDecision; label: string; Icon: React.ElementType; variant: 'teal' | 'danger' | 'outline' }[] = [
  { key: 'APPROVED', label: 'Approve', Icon: Check, variant: 'teal' },
  { key: 'REVISION_REQUESTED', label: 'Request revision', Icon: RotateCcw, variant: 'outline' },
  { key: 'REJECTED', label: 'Reject', Icon: X, variant: 'danger' },
];
export const DECISION_LABEL: Record<ReviewDecision, string> = { APPROVED: 'Approve', REJECTED: 'Reject', REVISION_REQUESTED: 'Request revision' };

const Detail: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div>
    <dt className="text-[10px] uppercase tracking-wider font-semibold text-content-muted">{label}</dt>
    <dd className="text-xs text-content-primary mt-0.5 leading-relaxed">{children}</dd>
  </div>
);

const CandidateCard: React.FC<{
  m: CandidateMapping;
  canReview: boolean;
  openEvidence: OpenEvidence;
  onDecide: (m: CandidateMapping, d: ReviewDecision) => void;
}> = ({ m, canReview, openEvidence, onDecide }) => {
  const decided = m.reviewerStatus !== 'AWAITING_REVIEW';
  return (
    <article
      data-testid={`mapping-${m.id}`}
      aria-labelledby={`mapping-title-${m.id}`}
      className={cn(
        'rounded-xl bg-white shadow-subtle overflow-hidden border-2',
        decided ? 'border-surface-border' : 'border-dashed border-amber-300'
      )}
    >
      <div className={cn('px-5 py-2 text-[11px] font-semibold flex flex-wrap items-center gap-2 justify-between', decided ? 'bg-surface-bg' : 'bg-amber-50 text-amber-900')}>
        <span className="flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />
          {decided ? 'AI-suggested candidate: human review recorded' : 'AI-suggested candidate. Not approved.'}
        </span>
        <span className="flex flex-wrap gap-1.5">
          <StatusBadge status={m.verification} prefix="Verification" />
          <StatusBadge status={m.reviewerStatus} prefix="Reviewer" />
        </span>
      </div>

      <div className="p-5 space-y-4">
        <h3 id={`mapping-title-${m.id}`} className="sr-only">
          Candidate mapping {m.topicSection} {m.topicLabel} to {m.outcomeResearchLabel}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] gap-3 items-stretch">
          <div className="rounded-lg border border-surface-border p-3">
            <p className="text-[10px] uppercase tracking-wider font-semibold text-content-muted">Topic</p>
            <p className="text-sm font-semibold text-navy-900 mt-0.5">
              <span className="font-mono text-content-secondary">{m.topicSection}</span> {m.topicLabel}
            </p>
            <p className="text-[11px] text-content-secondary">
              Chapter {m.chapterNumber}: {m.chapterTitle}
            </p>
            <div className="flex items-center gap-2 mt-2">
              <StatusBadge status={m.topicEvidence.status} prefix="Source" />
              <EvidenceButton onClick={() => openEvidence(m.topicEvidence, `Topic endpoint · ${m.topicSection} ${m.topicLabel}`)} label={`topic ${m.topicSection}`} />
            </div>
          </div>
          <div className="flex md:flex-col items-center justify-center text-content-muted text-[10px] gap-1">
            <ArrowRight className="w-4 h-4 rotate-90 md:rotate-0" aria-hidden="true" />
            <span>proposed</span>
          </div>
          <div className="rounded-lg border border-dashed border-gray-300 p-3">
            <p className="text-[10px] uppercase tracking-wider font-semibold text-content-muted">Proposed learning outcome</p>
            <p className="text-sm font-semibold text-navy-900 mt-0.5">{m.outcomeResearchLabel}</p>
            <p className="text-[11px] text-content-secondary">
              Ref <code className="text-[10px]">{m.outcomeReferenceId}</code>
              {!m.outcomeReferenceIsOfficialCode && ' (local research reference, not an official NCERT code)'}
            </p>
            {!m.outcomeWordingStored && (
              <p className="text-[11px] text-content-muted italic mt-1">Research label only. The official wording is not shown because rights are pending.</p>
            )}
            <div className="flex items-center gap-2 mt-2">
              <StatusBadge status={m.outcomeEvidence.status} prefix="Source" />
              <EvidenceButton onClick={() => openEvidence(m.outcomeEvidence, `Outcome endpoint · ${m.outcomeReferenceId}`)} label={`outcome ${m.outcomeReferenceId}`} />
            </div>
          </div>
        </div>

        <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 rounded-lg bg-surface-bg/70 border border-surface-border p-4">
          <Detail label="AI-generated rationale">
            <span className="inline-flex items-start gap-1.5">
              <Bot className="w-3.5 h-3.5 mt-0.5 shrink-0 text-content-muted" aria-hidden="true" />
              {m.aiRationale}
            </span>
          </Detail>
          <Detail label="Not covered by this topic">{m.uncoveredScope}</Detail>
          <Detail label="Relationship basis">{humanize(m.relationshipBasis)}</Detail>
          <Detail label="Coverage and applicability">
            {m.fullOutcomeCoverage ? 'Full coverage claimed' : 'Partial coverage only'}. {m.applicability}
          </Detail>
          <Detail label="Created by">
            {humanize(m.creationMethod)}
            {m.aiCheckedBy && ` · source-checked by ${m.aiCheckedBy}${m.aiCheckedOn ? ` on ${m.aiCheckedOn}` : ''}`}
          </Detail>
          <Detail label="Recovery eligible">{m.recoveryEligible ? 'Yes' : 'No. This needs verified status set by the backend.'}</Detail>
        </dl>

        {m.reviews.length > 0 && (
          <div className="text-xs">
            <p className="text-[10px] uppercase tracking-wider font-semibold text-content-muted mb-1.5">Review history</p>
            <ol className="space-y-1.5">
              {m.reviews.map((r, i) => (
                <li key={i} className="rounded-lg border border-surface-border px-3 py-2">
                  <strong>{DECISION_LABEL[r.decision]}</strong> by {r.reviewer} · {new Date(r.reviewedAt).toLocaleString()}
                  <p className="text-content-secondary mt-0.5">“{r.rationale}”</p>
                </li>
              ))}
            </ol>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          {canReview ? (
            <div className="flex flex-wrap gap-2" role="group" aria-label={`Review ${m.topicSection} ${m.topicLabel}`}>
              {DECISIONS.filter(({ key }) => allowedDecisions(m.reviewerStatus).includes(key)).map(({ key, label, Icon, variant }) => (
                <Button key={key} size="sm" variant={variant} icon={<Icon className="w-3.5 h-3.5" />} onClick={() => onDecide(m, key)}>
                  {label}
                </Button>
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-content-secondary flex items-center gap-1.5">
              <Eye className="w-3.5 h-3.5" aria-hidden="true" /> View only. Only an administrator can record global catalogue review decisions.
            </p>
          )}
        </div>
      </div>
    </article>
  );
};

export const ReviewView: React.FC<{
  grade: GradeNumber;
  subject: SubjectKey;
  openEvidence: OpenEvidence;
  canReview: boolean;
  role: Role;
}> = ({ grade, subject, openEvidence, canReview, role }) => {
  const service = useCatalogueService();
  const state = useAsync(() => service.listCandidateMappings(grade, subject), [service, grade, subject]);
  const [pending, setPending] = useState<{ mapping: CandidateMapping; decision: ReviewDecision } | null>(null);
  const [rationale, setRationale] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [announcement, setAnnouncement] = useState('');

  const openDecision = (mapping: CandidateMapping, decision: ReviewDecision) => {
    setPending({ mapping, decision });
    setRationale('');
    setFormError(null);
  };
  const close = () => !submitting && setPending(null);

  const submit = async () => {
    if (!pending) return;
    const input = { decision: pending.decision, rationale, expectedRevision: pending.mapping.revision };
    const problem = validateReviewInput(input);
    if (problem) {
      setFormError(problem);
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const updated = await service.submitReview(pending.mapping.id, input);
      state.setData((list) => list.map((m) => (m.id === updated.id ? updated : m)));
      setAnnouncement(`${DECISION_LABEL[pending.decision]} recorded for ${updated.topicSection} ${updated.topicLabel}.`);
      setPending(null);
    } catch (err) {
      const e = describeApiError(err);
      setFormError(`${e.status === 403 ? 'Not permitted: ' : ''}${e.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  if (state.status === 'loading') return <LoadingState label="Loading candidate mappings…" />;
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={state.reload} />;
  const awaiting = state.data.filter((m) => m.reviewerStatus === 'AWAITING_REVIEW').length;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-amber-200 bg-amber-50/70 px-4 py-3 text-xs text-amber-950 space-y-1" data-testid="review-intro">
        <p className="font-semibold flex items-center gap-1.5">
          <Sparkles className="w-4 h-4" aria-hidden="true" /> {state.data.length} AI-suggested topic-to-outcome candidate{state.data.length === 1 ? '' : 's'} · {awaiting} awaiting review
        </p>
        <p>
          These links are proposals only. None of them has been approved as official, and none is used for planning or recovery until
          a reviewer approves it and the backend publishes it. Check the evidence for both ends of each link before you decide.
        </p>
      </div>

      <p className="text-[11px] text-content-secondary flex items-center gap-1.5" data-testid="review-permission">
        {canReview ? <ShieldCheck className="w-3.5 h-3.5 text-teal-600" aria-hidden="true" /> : <Eye className="w-3.5 h-3.5" aria-hidden="true" />}
        Signed in as <strong className="capitalize">{role}</strong>.{' '}
        {canReview ? 'You can record review decisions.' : 'You can view candidates but not review them.'}
      </p>

      <div role="status" aria-live="polite" className="sr-only">
        {announcement}
      </div>
      {announcement && (
        <p className="text-xs rounded-lg border border-teal-200 bg-teal-50 text-teal-900 px-3 py-2" data-testid="review-announcement">
          {announcement}
        </p>
      )}

      {state.data.length === 0 ? (
        <EmptyState title="No candidate mappings for this class and subject">
          <p>No topic-to-outcome candidates have been proposed yet. Nothing has been generated to fill the gap.</p>
        </EmptyState>
      ) : (
        state.data.map((m) => <CandidateCard key={m.id} m={m} canReview={canReview} openEvidence={openEvidence} onDecide={openDecision} />)
      )}

      <Modal
        isOpen={!!pending}
        onClose={close}
        title={pending ? `${DECISION_LABEL[pending.decision]} candidate mapping` : ''}
        subtitle={pending ? `${pending.mapping.topicSection} ${pending.mapping.topicLabel} → ${pending.mapping.outcomeResearchLabel}` : undefined}
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={close} disabled={submitting}>
              Cancel
            </Button>
            <Button
              size="sm"
              variant={pending?.decision === 'REJECTED' ? 'danger' : 'teal'}
              loading={submitting}
              onClick={submit}
            >
              Record decision
            </Button>
          </>
        }
      >
        <div className="space-y-3 text-xs">
          <label htmlFor="review-rationale" className="block font-semibold text-content-primary">
            Decision rationale <span className="text-rose-600">(required)</span>
          </label>
          <textarea
            id="review-rationale"
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            rows={4}
            aria-invalid={!!formError}
            aria-describedby="review-rationale-help review-rationale-error"
            className="w-full rounded-lg border border-surface-border p-2.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal-400"
            placeholder="Explain the evidence that supports this decision, and what is still missing."
          />
          <p id="review-rationale-help" className="text-content-muted">
            At least {MIN_RATIONALE_LENGTH} characters. The decision is recorded with your name and the time.
            {pending?.decision === 'APPROVED' && ' Approving records your review only. It does not publish the mapping or make it eligible for recovery.'}
          </p>
          {formError && (
            <p id="review-rationale-error" role="alert" className="text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
              {formError}
            </p>
          )}
        </div>
      </Modal>
    </div>
  );
};
