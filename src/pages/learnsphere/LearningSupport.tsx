import React, { useEffect, useState } from 'react';
import { useLearning } from './LearnSphereLayout';
import { learnsphere } from '../../lib/learnsphere';
import type { Support } from '../../types/learnsphere';
import { Card, CardBody } from '../../components/common/Card';
import { ActivityWorkspace } from './ActivityWorkspace';
import {AssessmentQuestionSupport} from '../../components/learnsphere/AssessmentQuestionSupport';
export function LearningSupport() {
  const { studentId } = useLearning();
  const [data, setData] = useState<Support>();
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setData(undefined); setError('');
    if (studentId) learnsphere.support(studentId).then(d => active && setData(d)).catch(e => active && setError(e.message));
    return () => {active = false;};
  }, [studentId, revision]);
  return <div className="space-y-4"><h2 className="text-xl font-semibold">Learning Support</h2>
    <AssessmentQuestionSupport key={studentId}/>
    <details><summary>General activity-based learning support</summary>
    {error && <p role="alert">{error}</p>}
    {!studentId ? <p>Select a student to view support.</p> : !data && !error ? <p role="status">Loading evidence…</p> : null}
    {data && !data.findings.length && <p>More practice data needed for activity-based recommendations. Reviewed assessment outcomes are shown separately when available.</p>}
    {data?.findings.map(f => <Card key={`${f.topic_id}:${f.competency}`}><CardBody>
      <h3 className="font-semibold">{f.topic} · {f.competency}</h3><p>{f.status}</p><p>{f.reason}</p><p className="text-sm text-content-secondary">Rule: {f.rule}</p><p className="mt-2">Suggested next step: {f.suggestion}</p>
      <details className="mt-3"><summary>Evidence sources ({f.observations})</summary>{f.sources.map(s => <p key={s.id} className="text-sm">{new Date(s.recorded_at).toLocaleDateString()} · {s.source} · {s.score}/{s.maximum} · {s.correct == null ? 'Correctness not recorded' : s.correct ? 'Correct' : 'Incorrect'} · hints: {s.hints ?? 'not recorded'} · attempt {s.attempt_id}</p>)}</details>
    </CardBody></Card>)}
    </details>
    <ActivityWorkspace kind="support" onEvidenceChange={() => setRevision(n => n + 1)} />
  </div>;
}
