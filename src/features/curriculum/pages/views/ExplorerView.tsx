import React, { useEffect, useMemo, useState } from 'react';
import { BookOpen, GitBranch, Info } from 'lucide-react';
import { Card, CardBody, CardHeader } from '../../../../components/common/Card';
import { cn } from '../../../../lib/utils';
import { useCatalogueService } from '../../api/CatalogueServiceContext';
import { useAsync } from '../../hooks/useAsync';
import { EvidenceButton } from '../../components/EvidenceButton';
import { EmptyState, ErrorState, LoadingState, MissingValue } from '../../components/StateViews';
import { StatusBadge } from '../../components/StatusBadge';
import { languageLabel } from '../../labels';
import { LANGUAGES, type ChapterRecord, type GradeNumber, type SubjectKey, type TextbookEdition } from '../../types';
import type { OpenEvidence } from '../../types';

const editionName = (e: TextbookEdition) =>
  `${e.title ?? 'Untitled (not verified)'}${e.partLabel && !(e.title ?? '').includes(e.partLabel) ? `, ${e.partLabel}` : ''}`;

const ChapterCard: React.FC<{ chapter: ChapterRecord; openEvidence: OpenEvidence }> = ({ chapter, openEvidence }) => (
  <Card data-testid={`chapter-${chapter.id}`}>
    <CardHeader
      title={
        <span>
          <span className="text-content-muted font-medium">Chapter {chapter.number} · </span>
          {chapter.title}
        </span>
      }
      subtitle={`${chapter.textbookTitle}${chapter.textbookEdition ? ` · ${chapter.textbookEdition}` : ''}`}
      action={
        <div className="flex items-center gap-2">
          <StatusBadge status={chapter.status} />
          <EvidenceButton onClick={() => openEvidence(chapter.evidence, `Chapter ${chapter.number}: ${chapter.title}`)} label={`chapter ${chapter.number}`} />
        </div>
      }
    />
    <div className="relative overflow-x-auto">
      <table className="w-full min-w-[640px]">
        <caption className="sr-only">Topics in chapter {chapter.number}</caption>
        <thead className="bg-surface-bg/60">
          <tr className="text-left text-[10px] uppercase tracking-wider text-content-muted">
            <th className="px-5 py-2 font-semibold">Section</th>
            <th className="px-3 py-2 font-semibold">Topic</th>
            <th className="px-3 py-2 font-semibold">Source locator</th>
            <th className="px-3 py-2 font-semibold">Prerequisites</th>
            <th className="px-3 py-2 font-semibold">Status</th>
            <th className="px-3 py-2"><span className="sr-only">Evidence</span></th>
          </tr>
        </thead>
        <tbody>
          {chapter.topics.map((t) => (
            <tr key={t.id} className="border-t border-surface-border text-xs align-top" data-testid={`topic-${t.id}`}>
              <td className="px-5 py-2.5 font-mono text-content-secondary whitespace-nowrap">{t.section}</td>
              <td className="px-3 py-2.5 font-medium text-content-primary">{t.label}</td>
              <td className="px-3 py-2.5 text-[11px] text-content-secondary">{t.evidence.locator ?? <MissingValue>No locator</MissingValue>}</td>
              <td className="px-3 py-2.5 text-[11px]">
                {t.prerequisites.length ? (
                  <ul className="space-y-1">
                    {t.prerequisites.map((p) => (
                      <li key={p.id} className="flex items-center gap-1.5">
                        <GitBranch className="w-3 h-3" aria-hidden="true" /> {p.label} <StatusBadge status={p.status} />
                      </li>
                    ))}
                  </ul>
                ) : (
                  <MissingValue>None verified</MissingValue>
                )}
              </td>
              <td className="px-3 py-2.5">
                <StatusBadge status={t.status} />
              </td>
              <td className="px-3 py-2.5 text-right">
                <EvidenceButton onClick={() => openEvidence(t.evidence, `Section ${t.section}: ${t.label}`)} label={`section ${t.section}`} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </Card>
);

export const ExplorerView: React.FC<{ grade: GradeNumber; subject: SubjectKey; openEvidence: OpenEvidence }> = ({
  grade,
  subject,
  openEvidence,
}) => {
  const service = useCatalogueService();
  const state = useAsync(() => service.getChapterExplorer(grade, subject), [service, grade, subject]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const editions = useMemo(
    () =>
      state.status === 'success'
        ? [...state.data.editions]
            .filter((e) => !e.isGap)
            .sort(
              (a, b) =>
                LANGUAGES.indexOf(a.language as never) - LANGUAGES.indexOf(b.language as never) ||
                (a.partLabel ?? '').localeCompare(b.partLabel ?? '')
            )
        : [],
    [state]
  );
  const chaptersFor = (e: TextbookEdition) => (state.status === 'success' && e.evidence.sourceId ? state.data.chaptersBySource[e.evidence.sourceId] ?? [] : []);

  // Default to the first edition that has source-checked chapters.
  useEffect(() => {
    if (state.status !== 'success') return;
    setSelectedId((prev) => (prev && editions.some((e) => e.id === prev) ? prev : (editions.find((e) => chaptersFor(e).length) ?? editions[0])?.id ?? null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.status, editions]);

  if (state.status === 'loading') return <LoadingState label="Loading chapters and topics…" />;
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={state.reload} />;

  const selected = editions.find((e) => e.id === selectedId) ?? null;
  const chapters = selected ? chaptersFor(selected) : [];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-5">
      <Card className="h-fit">
        <CardHeader title="Textbook editions" subtitle="Choose an edition to explore" />
        <ul className="p-2 space-y-1" aria-label="Textbook editions">
          {editions.map((e) => {
            const count = chaptersFor(e).length;
            const active = e.id === selectedId;
            return (
              <li key={e.id}>
                <button
                  type="button"
                  aria-pressed={active}
                  onClick={() => setSelectedId(e.id)}
                  className={cn(
                    'w-full text-left rounded-lg px-3 py-2 text-xs border transition focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400',
                    active ? 'bg-teal-50 border-teal-300' : 'border-transparent hover:bg-surface-bg'
                  )}
                >
                  <span className="flex items-center gap-1.5 font-semibold text-content-primary">
                    <BookOpen className="w-3.5 h-3.5 text-content-muted" aria-hidden="true" />
                    {editionName(e)}
                  </span>
                  <span className="block text-[11px] text-content-secondary mt-0.5">
                    {languageLabel(e.language)} · {count ? `${count} chapter${count === 1 ? '' : 's'} checked` : 'no chapters checked'}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </Card>

      <div className="space-y-4 min-w-0">
        <div className="rounded-xl border border-sky-200 bg-sky-50/70 px-4 py-3 text-xs text-sky-900 flex gap-2.5" data-testid="explorer-completeness">
          <Info className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
          <p>{state.data.completenessNote}</p>
        </div>

        {selected && (
          <Card>
            <CardBody className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <p className="text-[10px] uppercase tracking-wider font-semibold text-content-muted">Selected textbook</p>
                <p className="font-semibold text-navy-900" data-testid="explorer-textbook-title">
                  {editionName(selected)}
                </p>
                <p className="text-xs text-content-secondary mt-0.5">
                  {languageLabel(selected.language)} · Edition: {selected.edition ?? <MissingValue>not verified</MissingValue>} · Reprint:{' '}
                  {selected.reprint ?? <MissingValue>not verified</MissingValue>}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={selected.status} prefix="Edition" />
                <EvidenceButton onClick={() => openEvidence(selected.evidence, `Textbook edition: ${editionName(selected)}`)} label="selected edition" />
              </div>
            </CardBody>
          </Card>
        )}

        {!selected ? (
          <EmptyState title="No textbook editions identified">
            <p>No textbook edition has been identified for this class and subject.</p>
          </EmptyState>
        ) : chapters.length ? (
          chapters.map((c) => <ChapterCard key={c.id} chapter={c} openEvidence={openEvidence} />)
        ) : (
          <EmptyState title="No chapters have been source-checked for this edition">
            <p>
              No chapter or topic records exist for this edition yet. Chapter equivalence with other language editions is{' '}
              <strong>{selected.translationEquivalence.toLowerCase()}</strong>, so chapters are not copied across from them.
            </p>
          </EmptyState>
        )}
      </div>
    </div>
  );
};
