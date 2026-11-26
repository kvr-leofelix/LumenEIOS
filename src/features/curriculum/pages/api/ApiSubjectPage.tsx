import React, { useCallback, useState } from 'react';
import { Link, Navigate, useParams, useSearchParams } from 'react-router-dom';
import { ChevronRight, LayoutList, ListTree, Scale } from 'lucide-react';
import { useAuth } from '../../../../context/AuthContext';
import { hasPermission } from '../../../../lib/permissions';
import { cn } from '../../../../lib/utils';
import { useNcertApi } from '../../api/CatalogueServiceContext';
import { missingTitleText, nodeTitle } from '../../api/presentation';
import { useAsync } from '../../hooks/useAsync';
import { EvidenceDrawer } from '../../components/EvidenceDrawer';
import { ErrorState, LoadingState, MissingValue, NotFoundState, UnauthorizedState } from '../../components/StateViews';
import { ROMAN, parseGrade, type EvidenceRecord } from '../../types';
import type { OpenEvidence } from '../../types';
import { LanguageSelector, parseLanguage } from './ApiControls';
import { ApiOverviewView } from './ApiOverviewView';
import { ApiExplorerView } from './ApiExplorerView';
import { ApiReviewView } from './ApiReviewView';

const TABS = [
  { key: 'overview', label: 'Curriculum overview', Icon: LayoutList },
  { key: 'explorer', label: 'Chapters & topics', Icon: ListTree },
  { key: 'review', label: 'Mapping review', Icon: Scale },
] as const;
type TabKey = (typeof TABS)[number]['key'];

/**
 * API-mode subject page. Route: /curriculum/catalogue/:grade/:subject?release=<release_id>
 * where :subject is the SUBJECT node id returned by GET /ncert/subjects (never matched by title).
 */
export const ApiSubjectPage: React.FC = () => {
  const params = useParams();
  const grade = parseGrade(params.grade);
  const subjectNodeId = params.subject ?? '';
  const [search, setSearch] = useSearchParams();
  const releaseId = search.get('release');
  const lang = parseLanguage(search.get('lang'));
  const { currentUser } = useAuth();
  const api = useNcertApi();
  const [evidence, setEvidence] = useState<{ record: EvidenceRecord; heading?: string } | null>(null);
  const openEvidence = useCallback<OpenEvidence>((record, heading) => setEvidence({ record, heading }), []);
  const closeEvidence = useCallback(() => setEvidence(null), []);
  const node = useAsync(() => api.getNode(subjectNodeId, lang), [api, subjectNodeId, lang]);

  if (!grade || !releaseId) return <Navigate to="/curriculum/catalogue" replace />;
  if (!currentUser || !hasPermission(currentUser.role, 'VIEW_CURRICULUM_CATALOGUE')) return <UnauthorizedState />;

  const tab: TabKey = (TABS.find((t) => t.key === search.get('view'))?.key ?? 'overview') as TabKey;
  const setParam = (k: string, v: string | null) => {
    const next = new URLSearchParams(search);
    v === null ? next.delete(k) : next.set(k, v);
    setSearch(next);
  };
  const dashboardLink = `/curriculum/catalogue?release=${encodeURIComponent(releaseId)}&grade=${grade}&lang=${lang}`;
  const subject = node.status === 'success' ? node.data : null;
  const title = subject ? nodeTitle(subject) : null;
  const mismatch = subject && (subject.kind !== 'SUBJECT' || subject.release_id !== releaseId);

  return (
    <div className="space-y-5">
      <div className="bg-white p-5 rounded-2xl border border-surface-border shadow-subtle space-y-4">
        <nav aria-label="Breadcrumb" className="text-xs text-content-secondary flex items-center gap-1">
          <Link to={dashboardLink} className="hover:text-teal-700 underline-offset-2 hover:underline">
            Curriculum Catalogue
          </Link>
          <ChevronRight className="w-3 h-3" aria-hidden="true" />
          <span aria-current="page" className="text-content-primary font-medium">
            Class {ROMAN[grade]} · {title ?? 'Subject'}
          </span>
        </nav>
        <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-navy-900 tracking-tight">
              Class {ROMAN[grade]} {title ?? (subject ? <MissingValue>{missingTitleText(subject)}</MissingValue> : '')}
            </h1>
            <p className="text-xs text-content-secondary mt-0.5">
              Catalogue records from the backend: source availability, chapter and topic hierarchy, and candidate outcome mappings
            </p>
          </div>
          <LanguageSelector value={lang} onChange={(l) => setParam('lang', l)} />
        </div>
        <div role="tablist" aria-label="Catalogue sections" className="flex gap-1 border-b border-surface-border -mb-5 overflow-x-auto">
          {TABS.map(({ key, label, Icon }) => (
            <button
              key={key}
              role="tab"
              id={`tab-${key}`}
              aria-selected={tab === key}
              aria-controls={`panel-${key}`}
              onClick={() => setParam('view', key === 'overview' ? null : key)}
              className={cn(
                'flex items-center gap-1.5 px-3.5 py-2.5 text-xs font-semibold border-b-2 -mb-px whitespace-nowrap focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 rounded-t',
                tab === key ? 'border-teal-500 text-teal-800' : 'border-transparent text-content-secondary hover:text-content-primary'
              )}
            >
              <Icon className="w-3.5 h-3.5" aria-hidden="true" />
              {label}
            </button>
          ))}
        </div>
      </div>

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="pt-2">
        {node.status === 'loading' && <LoadingState label="Loading subject…" />}
        {node.status === 'error' && <ErrorState error={node.error} onRetry={node.reload} />}
        {subject && mismatch && (
          <NotFoundState message="This record is not a subject in the selected release. Go back to the catalogue and choose the subject again." />
        )}
        {subject && !mismatch && (
          <>
            {tab === 'overview' && <ApiOverviewView grade={grade} releaseId={releaseId} subject={subject} lang={lang} openEvidence={openEvidence} />}
            {tab === 'explorer' && <ApiExplorerView root={subject} lang={lang} openEvidence={openEvidence} />}
            {tab === 'review' && (
              <ApiReviewView
                releaseId={releaseId}
                subjectNodeId={subject.id}
                lang={lang}
                openEvidence={openEvidence}
                canReview={hasPermission(currentUser.role, 'REVIEW_CURRICULUM_MAPPINGS')}
                role={currentUser.role}
              />
            )}
          </>
        )}
      </div>

      <EvidenceDrawer evidence={evidence?.record ?? null} heading={evidence?.heading} onClose={closeEvidence} />
    </div>
  );
};
