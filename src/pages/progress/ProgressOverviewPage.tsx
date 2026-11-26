import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, BookOpen, CalendarDays, Sparkles } from 'lucide-react';
import { Card, CardBody, CardHeader } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { CompetencyRadarChart } from '../../components/charts/CompetencyRadarChart';
import { apiClient } from '../../lib/apiClient';
import {
  StudentProgressOverview,
  evidenceStatusFromProfile,
  evidenceStatusLabel,
  evidenceStatusVariant,
  formatPercent,
  formatWhen,
  progressPaths,
} from '../../lib/studentProgress';
import { UnauthorizedPage } from '../shared/UnauthorizedPage';
import { CompetencyEvidenceGrid } from './components/CompetencyEvidenceGrid';
import { EvidenceList } from './components/EvidenceList';
import { ProgressEmpty, ProgressError, ProgressLoading } from './components/ProgressStates';
import { useProgressScope } from './useProgressScope';

export const StudentProgressOverviewPage: React.FC = () => (
  <ProgressOverview expected="self" />
);

export const EducatorProgressOverviewPage: React.FC = () => (
  <ProgressOverview expected="educator" />
);

export const ParentProgressOverviewPage: React.FC = () => (
  <ProgressOverview expected="parent" />
);

function ProgressOverview({ expected }: { expected: 'self' | 'educator' | 'parent' }) {
  const scope = useProgressScope(expected);
  const [data, setData] = useState<StudentProgressOverview | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    if (!scope.allowed) return;
    setLoading(true);
    setError(null);
    apiClient.progress
      .overview(scope.apiScope)
      .then(setData)
      .catch(setError)
      .finally(() => setLoading(false));
  }, [scope]);

  useEffect(() => {
    load();
  }, [load]);

  if (!scope.allowed) {
    if (scope.reason === 'unauthorized' || scope.reason === 'unauthenticated') {
      return <UnauthorizedPage />;
    }
    return (
      <ProgressEmpty
        title="Choose a student"
        detail="Open Unified Progress from a linked child or class roster student."
      />
    );
  }

  if (loading) return <ProgressLoading />;
  if (error) return <ProgressError error={error} onRetry={load} />;
  if (!data) {
    return (
      <ProgressEmpty
        title="No progress overview"
        detail="The progress API returned no overview for this student."
      />
    );
  }

  const paths = progressPaths(scope.role, scope.studentId || data.student.id);
  const subjectProfiles = data.subject_competencies?.length
    ? data.subject_competencies
    : data.subjects.map((subject) => subject.competencies).filter(Boolean);

  return (
    <div className="space-y-6">
      <div className="bg-white p-5 rounded-2xl border border-surface-border shadow-subtle flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-xl font-bold text-navy-900 tracking-tight">Unified Student Progress</h1>
            <Badge variant="teal" size="sm">
              Verified evidence
            </Badge>
          </div>
          <p className="text-xs text-content-secondary mt-1">
            {data.student.name} · Roll #{data.student.roll_no} · {data.student.class_name}
          </p>
          <p className="text-[11px] text-content-muted mt-1">
            Generated {formatWhen(data.generated_at)} · Audience: {data.audience.replace(/_/g, ' ')}
          </p>
        </div>
        <div className="grid grid-cols-3 gap-3 min-w-[16rem]">
          <SummaryStat
            icon={<Activity className="w-3.5 h-3.5" />}
            label="Verified events"
            value={String(data.overall.verified_event_count)}
          />
          <SummaryStat
            icon={<BookOpen className="w-3.5 h-3.5" />}
            label="Average"
            value={formatPercent(data.overall.average_percentage)}
          />
          <SummaryStat
            icon={<CalendarDays className="w-3.5 h-3.5" />}
            label="Latest activity"
            value={formatWhen(data.overall.latest_activity_at)}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Card>
          <CardHeader
            title="Competency profile (LU · CU · AU · CT)"
            subtitle="Live scores with evidence labels. Missing subject evidence stays blank — never zero-filled."
          />
          <CardBody className="space-y-4">
            <CompetencyRadarChart
              current={data.competencies.current}
              baseline={data.competencies.baseline}
              benchmarkName="Baseline"
              height={240}
            />
            <CompetencyEvidenceGrid current={data.competencies.current} />
            <p className="text-[11px] text-content-muted">Source: {data.competencies.source}</p>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Subject evidence status"
            subtitle="Demonstrated requires verified evidence in all four dimensions for that subject."
          />
          <CardBody>
            {!data.subjects.length ? (
              <ProgressEmpty
                title="No subject performance yet"
                detail="Subjects appear after verified homework or assessment evidence is linked to this student."
              />
            ) : (
              <ul className="space-y-2.5">
                {data.subjects.map((subject) => {
                  const profile =
                    subject.competencies ||
                    subjectProfiles.find((item) => item?.subject_id === subject.subject_id);
                  const evidence = evidenceStatusFromProfile(profile?.status || 'unavailable');
                  return (
                    <li key={subject.subject_id}>
                      <Link
                        to={paths.subject(subject.subject_id)}
                        className="block p-3.5 rounded-xl border border-surface-border hover:border-teal-400 hover:bg-teal-50/40 transition-colors"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-navy-900">
                              {subject.subject_name || subject.subject_id}
                            </p>
                            <p className="text-[11px] text-content-secondary mt-0.5">
                              {subject.event_count} event{subject.event_count === 1 ? '' : 's'}
                              {subject.comparable_event_count
                                ? ` · ${subject.comparable_event_count} comparable`
                                : ''}
                              {subject.latest_occurred_at
                                ? ` · latest ${formatWhen(subject.latest_occurred_at)}`
                                : ''}
                            </p>
                          </div>
                          <div className="text-right space-y-1">
                            <Badge variant={evidenceStatusVariant(evidence)} size="sm">
                              {evidenceStatusLabel(evidence)}
                            </Badge>
                            <p className="text-sm font-bold text-navy-900 tabular-nums">
                              {formatPercent(subject.average_percentage)}
                            </p>
                          </div>
                        </div>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Card>
          <CardHeader title="Recent verified activity" subtitle="Assessment studio, OCR publications, and reviewed homework." />
          <CardBody>
            <EvidenceList events={data.recent_activity} />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Recommendations"
            subtitle="Deterministic suggestions from verified patterns — not diagnoses."
            action={<Sparkles className="w-4 h-4 text-teal-600" />}
          />
          <CardBody>
            {!data.recommendations.length ? (
              <ProgressEmpty
                title="No recommendations yet"
                detail="Recommendations appear when verified evidence shows weak subjects, trends, or missing assessments."
              />
            ) : (
              <ul className="space-y-2.5">
                {data.recommendations.map((item, index) => (
                  <li
                    key={`${item.kind}-${index}`}
                    className="p-3.5 rounded-xl border border-surface-border bg-surface-bg"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant="outline" size="sm">
                        {item.kind.replace(/_/g, ' ')}
                      </Badge>
                      {item.competency && (
                        <Badge variant="teal" size="sm">
                          {item.competency}
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm text-navy-900 leading-relaxed">{item.summary}</p>
                    {item.evidence?.length > 0 && (
                      <p className="text-[11px] text-content-secondary mt-1">
                        Evidence refs: {item.evidence.slice(0, 4).join(', ')}
                        {item.evidence.length > 4 ? '…' : ''}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function SummaryStat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="p-3 rounded-xl bg-surface-bg border border-surface-border">
      <p className="text-[10px] uppercase tracking-wider text-content-secondary font-semibold flex items-center gap-1">
        {icon}
        {label}
      </p>
      <p className="text-sm font-bold text-navy-900 mt-1 truncate">{value}</p>
    </div>
  );
}
