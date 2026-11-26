import React from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRight, BookMarked, Eye, Library, ShieldCheck } from 'lucide-react';
import { useAuth } from '../../../../context/AuthContext';
import { hasPermission } from '../../../../lib/permissions';
import { cn } from '../../../../lib/utils';
import { Card, CardBody, CardHeader } from '../../../../components/common/Card';
import { useNcertApi } from '../../api/CatalogueServiceContext';
import { fetchAllPages } from '../../api/ncertApi';
import { codeLabel, missingTitleText, nodeTitle, verificationStatus } from '../../api/presentation';
import { useAsync } from '../../hooks/useAsync';
import { EmptyState, ErrorState, LoadingState, MissingValue, UnauthorizedState } from '../../components/StateViews';
import { StatusBadge, StatusLegend } from '../../components/StatusBadge';
import { ROMAN, parseGrade, type GradeNumber } from '../../types';
import { ApiSourceBanner, GradeSelector, LanguageSelector, ReleaseStatusPill, parseLanguage } from './ApiControls';

/** API-mode Screen 1: explicit release selection → subjects by class (contract "Frontend sequence"). */
export const ApiCatalogueDashboard: React.FC = () => {
  const { currentUser } = useAuth();
  const api = useNcertApi();
  const [search, setSearch] = useSearchParams();
  const releaseId = search.get('release');
  const grade: GradeNumber = parseGrade(search.get('grade') ?? undefined) ?? 6;
  const lang = parseLanguage(search.get('lang'));

  const releases = useAsync(() => fetchAllPages((offset) => api.listReleases({ limit: 100, offset })), [api]);
  const subjects = useAsync(
    () =>
      releaseId
        ? fetchAllPages((offset) => api.listSubjects({ releaseId, grade, language: lang, limit: 100, offset }))
        : Promise.resolve(null),
    [api, releaseId, grade, lang]
  );

  if (!currentUser || !hasPermission(currentUser.role, 'VIEW_CURRICULUM_CATALOGUE')) return <UnauthorizedState />;
  const canReview = hasPermission(currentUser.role, 'REVIEW_CURRICULUM_MAPPINGS');
  const selectedRelease = releases.data?.find((r) => r.id === releaseId) ?? null;

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(search);
    for (const [k, v] of Object.entries(patch)) (v === null ? next.delete(k) : next.set(k, v));
    setSearch(next);
  };

  return (
    <div className="space-y-6">
      <div className="bg-white p-5 rounded-2xl border border-surface-border shadow-subtle flex gap-3">
        <div className="p-2.5 rounded-xl bg-teal-50 text-teal-700 h-fit">
          <Library className="w-6 h-6" aria-hidden="true" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-navy-900 tracking-tight">Curriculum Catalogue</h1>
          <p className="text-xs text-content-secondary mt-0.5 max-w-2xl leading-relaxed">
            Check which official NCERT curriculum sources are recorded in the catalogue, which are provisional and which are still
            missing, before they are used for planning. Each record links to its source evidence.
          </p>
          <p className="mt-2 inline-flex items-center gap-1.5 text-[11px] font-semibold text-navy-800 bg-navy-50 border border-navy-100 rounded-full px-2.5 py-0.5">
            <BookMarked className="w-3 h-3" aria-hidden="true" /> Prototype scope: Classes VI–VIII · Mathematics and Science
          </p>
        </div>
      </div>

      <ApiSourceBanner release={selectedRelease} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 space-y-5">
          <Card>
            <CardHeader title="1. Choose a catalogue release" subtitle="A release must be chosen explicitly. The latest one is never picked for you." />
            <CardBody>
              {releases.status === 'loading' && <LoadingState label="Loading catalogue releases…" />}
              {releases.status === 'error' && <ErrorState error={releases.error} onRetry={releases.reload} />}
              {releases.status === 'success' &&
                (releases.data.length === 0 ? (
                  <EmptyState title="No catalogue releases are visible to your account">
                    <p>
                      The backend returned an empty release list. Teachers and principals can see published releases only;
                      administrators can also see drafts.
                    </p>
                    <p>No curriculum data is shown, and nothing is filled in to replace it.</p>
                  </EmptyState>
                ) : (
                  <div role="radiogroup" aria-label="Catalogue release" className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {releases.data.map((r) => (
                      <button
                        key={r.id}
                        type="button"
                        role="radio"
                        aria-checked={r.id === releaseId}
                        data-testid={`release-${r.id}`}
                        onClick={() => update({ release: r.id })}
                        className={cn(
                          'text-left rounded-xl border bg-white p-3.5 shadow-subtle focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400',
                          r.id === releaseId ? 'border-teal-500 ring-1 ring-teal-500' : 'border-surface-border hover:border-surface-borderHover'
                        )}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <p className="font-semibold text-sm text-navy-900">{r.release_key}</p>
                          <ReleaseStatusPill status={r.status} />
                        </div>
                        <p className="text-[11px] text-content-secondary mt-1">
                          {r.edition} · {r.academic_year ?? <MissingValue>academic year not recorded</MissingValue>}
                        </p>
                        <p className="text-[11px] text-content-muted mt-0.5">
                          {r.published_at ? `Published ${new Date(r.published_at).toLocaleDateString()}` : 'Not published'}
                        </p>
                      </button>
                    ))}
                  </div>
                ))}
            </CardBody>
          </Card>

          {releaseId && (
            <Card>
              <CardHeader title="2. Choose a class and subject" subtitle="Subjects are listed exactly as recorded in the selected release" />
              <CardBody className="space-y-4">
                <div className="flex flex-wrap items-end gap-4">
                  <GradeSelector value={grade} onChange={(g) => update({ grade: String(g) })} />
                  <LanguageSelector value={lang} onChange={(l) => update({ lang: l })} />
                </div>
                {subjects.status === 'loading' && <LoadingState label="Loading subjects…" />}
                {subjects.status === 'error' && <ErrorState error={subjects.error} onRetry={subjects.reload} />}
                {subjects.status === 'success' &&
                  (!subjects.data || subjects.data.length === 0 ? (
                    <EmptyState title={`No subjects are recorded for Class ${ROMAN[grade]} in this release`}>
                      <p>The backend returned no subject records. Mathematics and Science are not added unless they are stored in the catalogue.</p>
                    </EmptyState>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {subjects.data.map((node) => {
                        const title = nodeTitle(node);
                        return (
                          <Link
                            key={node.id}
                            data-testid={`subject-${node.id}`}
                            to={`/curriculum/catalogue/${grade}/${node.id}?release=${encodeURIComponent(releaseId)}&lang=${lang}`}
                            className="block rounded-xl border border-surface-border bg-white p-4 shadow-subtle hover:shadow-card hover:border-surface-borderHover focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400"
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div>
                                <p className="text-[10px] uppercase tracking-wider font-semibold text-content-muted">Class {ROMAN[grade]}</p>
                                <p className="font-semibold text-navy-900">{title ?? <MissingValue>{missingTitleText(node)}</MissingValue>}</p>
                              </div>
                              <ArrowRight className="w-4 h-4 text-content-muted shrink-0" aria-hidden="true" />
                            </div>
                            <div className="flex flex-wrap items-center gap-2 mt-2 text-[11px] text-content-secondary">
                              <StatusBadge status={verificationStatus(node.verification)} prefix="Verification" />
                              <span>Completeness: {codeLabel(node.completeness)}</span>
                            </div>
                          </Link>
                        );
                      })}
                    </div>
                  ))}
              </CardBody>
            </Card>
          )}
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader title="Your permissions" />
            <CardBody className="text-xs space-y-2">
              <p className="flex items-center gap-2" data-testid="permission-status">
                {canReview ? (
                  <ShieldCheck className="w-4 h-4 text-teal-600" aria-hidden="true" />
                ) : (
                  <Eye className="w-4 h-4 text-content-secondary" aria-hidden="true" />
                )}
                <span>
                  <strong className="capitalize">{currentUser.role}</strong>:{' '}
                  {canReview ? 'can view drafts and review candidate mappings' : 'view only (published releases)'}
                </span>
              </p>
              <p className="text-content-muted leading-relaxed">
                The backend checks your account role on every request. These labels only show or hide controls.
              </p>
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Status legend" />
            <CardBody>
              <StatusLegend statuses={['VERIFIED', 'UNVERIFIED', 'PLACEHOLDER', 'AWAITING_REVIEW', 'APPROVED', 'REJECTED', 'REVISION_REQUESTED']} />
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
};
