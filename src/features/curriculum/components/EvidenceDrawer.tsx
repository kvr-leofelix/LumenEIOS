import React, { useEffect, useRef } from 'react';
import { ExternalLink, FileSearch, X } from 'lucide-react';
import type { EvidenceRecord } from '../types';
import { StatusBadge } from './StatusBadge';
import { MissingValue } from './StateViews';

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="py-2.5 border-b border-surface-border last:border-0">
    <dt className="text-[10px] uppercase tracking-wider font-semibold text-content-muted">{label}</dt>
    <dd className="text-xs text-content-primary mt-0.5 break-words">{children}</dd>
  </div>
);

const Link: React.FC<{ href: string; children: React.ReactNode }> = ({ href, children }) => (
  <a
    href={href}
    target="_blank"
    rel="noopener noreferrer"
    className="inline-flex items-center gap-1 text-teal-700 hover:text-teal-800 underline underline-offset-2 break-all"
  >
    {children}
    <ExternalLink className="w-3 h-3 shrink-0" aria-hidden="true" />
    <span className="sr-only">(opens in new tab)</span>
  </a>
);

/** Screen 4: evidence / source panel. Slide-over dialog, closes on Escape or backdrop click. */
export const EvidenceDrawer: React.FC<{
  evidence: EvidenceRecord | null;
  heading?: string;
  onClose: () => void;
}> = ({ evidence, heading, onClose }) => {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!evidence) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    closeRef.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [evidence, onClose]);

  if (!evidence) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-navy-950/40 backdrop-blur-[1px]" onClick={onClose} aria-hidden="true" />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-title"
        className="relative w-full max-w-md h-full bg-white shadow-modal border-l border-surface-border flex flex-col animate-fade-in"
      >
        <header className="px-5 py-4 border-b border-surface-border flex items-start justify-between gap-3 bg-surface-bg/60">
          <div className="flex gap-2.5">
            <FileSearch className="w-5 h-5 text-teal-600 mt-0.5 shrink-0" aria-hidden="true" />
            <div>
              <h2 id="evidence-title" className="font-semibold text-sm text-content-primary">
                Source evidence
              </h2>
              {heading && <p className="text-xs text-content-secondary mt-0.5">{heading}</p>}
            </div>
          </div>
          <button
            ref={closeRef}
            onClick={onClose}
            className="p-1.5 rounded-lg text-content-secondary hover:bg-gray-200/70 focus:outline-none focus:ring-2 focus:ring-teal-400"
            aria-label="Close evidence panel"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-3">
          <div className="flex flex-wrap items-center gap-2 pb-3">
            <StatusBadge status={evidence.status} size="md" prefix="Verification" />
          </div>
          <dl>
            {evidence.redacted && (
              <p data-testid="evidence-redacted" className="text-[11px] text-rose-800 bg-rose-50 border border-rose-200 rounded-lg px-2.5 py-2 mb-1">
                Title, URL, edition and locator are withheld by the backend until a scoped metadata rights decision is recorded.
              </p>
            )}
            <Field label="Source title">
              {evidence.sourceTitle ?? <MissingValue>{evidence.redacted ? 'Redacted pending rights clearance' : 'Title not verified'}</MissingValue>}
            </Field>
            <Field label="Official source URL">
              {evidence.officialUrl ? (
                <Link href={evidence.officialUrl}>{evidence.officialUrl}</Link>
              ) : (
                <MissingValue>{evidence.redacted ? 'Redacted pending rights clearance' : 'No official source identified'}</MissingValue>
              )}
            </Field>
            {evidence.secondaryUrl && (
              <Field label={evidence.secondaryUrl.label}>
                <Link href={evidence.secondaryUrl.url}>{evidence.secondaryUrl.url}</Link>
              </Field>
            )}
            <Field label="Edition / version">{evidence.edition ?? <MissingValue>Edition not verified</MissingValue>}</Field>
            <Field label="Reprint">{evidence.reprint ?? <MissingValue>Not verified</MissingValue>}</Field>
            <Field label="Page / section locator">{evidence.locator ?? <MissingValue>No locator recorded</MissingValue>}</Field>
            <Field label="Research status code">
              <code className="text-[11px] bg-surface-bg px-1.5 py-0.5 rounded border border-surface-border">{evidence.rawStatus}</code>
            </Field>
            <Field label="Rights / permission">{evidence.rightsStatus ?? <MissingValue>Not recorded</MissingValue>}</Field>
            <Field label="Accessed">{evidence.accessedOn ?? <MissingValue>Not recorded</MissingValue>}</Field>
            <Field label="Record ID">
              <code className="text-[11px]">{evidence.id}</code>
              {evidence.sourceId && <span className="text-content-muted"> · source {evidence.sourceId}</span>}
            </Field>
          </dl>

          <section className="mt-4">
            <h3 className="text-[10px] uppercase tracking-wider font-semibold text-content-muted">Evidence notes and open issues</h3>
            {evidence.notes.length ? (
              <ul className="mt-2 space-y-2">
                {evidence.notes.map((n, i) => (
                  <li key={i} className="text-xs text-content-secondary leading-relaxed bg-surface-bg rounded-lg border border-surface-border p-2.5">
                    {n}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs mt-2">
                <MissingValue>No notes recorded.</MissingValue>
              </p>
            )}
          </section>
        </div>
      </aside>
    </div>
  );
};
