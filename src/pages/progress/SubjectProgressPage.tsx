import React, { useCallback, useEffect, useState } from 'react';
import { Card, CardBody, CardHeader } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { CompetencyRadarChart } from '../../components/charts/CompetencyRadarChart';
import { apiClient } from '../../lib/apiClient';
import {
  ProgressExplanations,
  SubjectProgress,
  SubjectTimeline,
  TimelineCheckpoint,
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
import {
  ProgressBackLink,
  ProgressEmpty,
  ProgressError,
  ProgressLoading,
} from './components/ProgressStates';
import { TimelinePanel } from './components/TimelinePanel';
import { useProgressScope } from './useProgressScope';

export const StudentSubjectProgressPage: React.FC = () => (
  <SubjectProgressView expected="self" />
);

export const EducatorSubjectProgressPage: React.FC = () => (
  <SubjectProgressView expected="educator" />
);

export const ParentSubjectProgressPage: React.FC = () => (
  <SubjectProgressView expected="parent" />
);

function SubjectProgressView({ expected }: { expected: 'self' | 'educator' | 'parent' }) {
  const scope = useProgressScope(expected);
  const [data, setData] = useState<SubjectProgress | null>(null);
  const [timeline, setTimeline] = useState<SubjectTimeline | null>(null);
  const [explanations, setExplanations] = useState<ProgressExplanations | null>(null);
  const [selectedPeriod, setSelectedPeriod] = useState<TimelineCheckpoint | null>(null);
  const [periodDetail, setPeriodDetail] = useState<Record<string, unknown> | null>(null);
  const [periodError, setPeriodError] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    if (!scope.allowed || !scope.subjectId) return;
    setLoading(true);
    setError(null);
    Promise.all([
      apiClient.progress.subject(scope.apiScope, scope.subjectId),
      apiClient.progress.subjectTimeline(scope.apiScope, scope.subjectId),
      apiClient.progress.subjectExplanations(scope.apiScope, scope.subjectId),
    ])
      .then(([subject, subjectTimeline, subjectExplanations]) => {
        setData(subject);
        setTimeline(subjectTimeline);
        setExplanations(subjectExplanations);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, [scope]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setSelectedPeriod(null);
    setPeriodDetail(null);
    setPeriodError(null);
  }, [scope.subjectId, scope.studentId]);

  const onSelectPeriod = async (checkpoint: TimelineCheckpoint) => {
    setSelectedPeriod(checkpoint);
    setPeriodDetail(null);
    setPeriodError(null);
    if (expected !== 'educator' || !scope.studentId) return;
    try {
      const detail = await apiClient.progress.periodEvidence(
        scope.studentId,
        checkpoint.subject_id,
        checkpoint.period_kind,
        checkpoint.period_id,
      );
      setPeriodDetail(detail);
    } catch (err) {
      setPeriodError(err instanceof Error ? err.message : 'Could not load period evidence.');
    }
  };

  if (!scope.allowed) {
    if (scope.reason === 'unauthorized' || scope.reason === 'unauthenticated') {
      return <UnauthorizedPage />;
    }
    return (
      <ProgressEmpty
        title="Choose a student"
        detail="Open a subject progress page from a student overview."
      />
    );
  }
  if (!scope.subjectId) {
    return (
      <ProgressEmpty
        title="Subject required"
        detail="Select a subject from the Unified Progress overview."
      />
    );
  }
  if (loading) return <ProgressLoading label="Loading subject progress…" />;
  if (error) return <ProgressError error={error} onRetry={load} />;
  if (!data) {
    return (
      <ProgressEmpty
        title="Subject progress unavailable"
        detail="No subject progress payload was returned for this student and subject."
      />
    );
  }

  const paths = progressPaths(scope.role, scope.studentId);
  const evidence = evidenceStatusFromProfile(data.competencies.status);
  const scores = data.competencies.scores;
  const radarReady =
    scores &&
    scores.LU != null &&
    scores.CU != null &&
    scores.AU != null &&
    scores.CT != null &&
    scores.overall != null;

  return (
    <div className="space-y-6">
      <div className="bg-white p-5 rounded-2xl border border-surface-border shadow-subtle space-y-3">
        <ProgressBackLink to={paths.overview} label="Back to Unified Progress" />
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold text-navy-900 tracking-tight">
                {data.subject_name || data.subject_id}
              </h1>
              <Badge variant={evidenceStatusVariant(evidence)} size="sm">
                {evidenceStatusLabel(evidence)}
              </Badge>
            </div>
            <p className="text-xs text-content-secondary mt-1">
              Subject progress · {data.performance.event_count} verified event
              {data.performance.event_count === 1 ? '' : 's'} · Generated {formatWhen(data.generated_at)}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[11px] uppercase tracking-wider text-content-secondary font-semibold">
              Average (comparable)
            </p>
            <p className="text-2xl font-bold text-navy-900 tabular-nums">
              {formatPercent(data.performance.average_percentage)}
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Card>
          <CardHeader
            title="Subject competencies"
            subtitle={data.competencies.methodology}
          />
          <CardBody className="space-y-4">
            {radarReady ? (
              <CompetencyRadarChart
                current={{
                  LU: scores!.LU as number,
                  CU: scores!.CU as number,
                  AU: scores!.AU as number,
                  CT: scores!.CT as number,
                  overall: scores!.overall as number,
                }}
                height={220}
              />
            ) : (
              <ProgressEmpty
                title="Radar unavailable"
                detail="A full LU/CU/AU/CT vector is required before the radar can render. Missing dimensions stay blank."
              />
            )}
            <CompetencyEvidenceGrid profile={data.competencies} />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Longitudinal timeline"
            subtitle="Academic-period checkpoints from verified subject evidence."
          />
          <CardBody className="space-y-4">
            <TimelinePanel
              timeline={timeline}
              selectedId={selectedPeriod?.period_id}
              onSelect={onSelectPeriod}
            />
            {selectedPeriod && (
              <div className="p-3.5 rounded-xl border border-surface-border bg-surface-bg space-y-2">
                <p className="text-sm font-semibold text-navy-900">
                  {selectedPeriod.period_label} ({selectedPeriod.period_kind})
                </p>
                <p className="text-xs text-content-secondary">
                  Status: {evidenceStatusLabel(evidenceStatusFromProfile(selectedPeriod.status))} ·{' '}
                  {selectedPeriod.evidence_count} evidence item
                  {selectedPeriod.evidence_count === 1 ? '' : 's'}
                </p>
                {expected === 'educator' && periodError && (
                  <p role="alert" className="text-xs text-rose-700">
                    {periodError}
                  </p>
                )}
                {expected === 'educator' && periodDetail && (
                  <EvidenceList
                    events={((periodDetail.observations as Array<Record<string, unknown>>) || []).map(
                      (obs) => ({
                        source_type: String(obs.source_type || ''),
                        source_id: String(obs.source_id || ''),
                        title: (obs.title as string) || `${obs.competency} observation`,
                        occurred_at: obs.assessed_on as string | undefined,
                        awarded_marks: obs.awarded_marks as number | null | undefined,
                        max_marks: obs.max_marks as number | null | undefined,
                        dimension: obs.competency as 'LU' | 'CU' | 'AU' | 'CT' | undefined,
                        dimension_value: obs.normalized_score as number | null | undefined,
                      }),
                    )}
                    emptyTitle="No observations in this period"
                    emptyDetail="This checkpoint has no dated verified observations."
                  />
                )}
                {expected !== 'educator' && (
                  <p className="text-[11px] text-content-secondary leading-relaxed">
                    Period detail drill-down is available to educators. Learners see checkpoint summaries only.
                  </p>
                )}
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Card>
          <CardHeader title="Subject evidence" subtitle="Verified homework and assessment outcomes for this subject." />
          <CardBody>
            <EvidenceList events={data.events} />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Evidence-backed findings"
            subtitle={explanations?.methodology || 'progress_explanation.v1.deterministic'}
          />
          <CardBody>
            {!explanations?.findings?.length ? (
              <ProgressEmpty
                title="No findings yet"
                detail="Deterministic findings appear once verified subject evidence can support strengths, concerns, or trends."
              />
            ) : (
              <ul className="space-y-2.5">
                {explanations.findings.map((finding, index) => (
                  <li
                    key={`${finding.kind}-${index}`}
                    className="p-3.5 rounded-xl border border-surface-border bg-surface-bg space-y-1"
                  >
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="outline" size="sm">
                        {finding.kind.replace(/_/g, ' ')}
                      </Badge>
                      {finding.competency && (
                        <Badge variant="teal" size="sm">
                          {finding.competency}
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm text-navy-900 leading-relaxed">{finding.summary}</p>
                    {finding.caveat && (
                      <p className="text-[11px] text-content-muted leading-relaxed">{finding.caveat}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>

      {data.competencies.evidence?.length > 0 && (
        <Card>
          <CardHeader
            title="Competency evidence items"
            subtitle={`${data.competencies.evidence_count} verified observation${data.competencies.evidence_count === 1 ? '' : 's'}`}
          />
          <CardBody>
            <EvidenceList events={data.competencies.evidence} />
          </CardBody>
        </Card>
      )}
    </div>
  );
}
