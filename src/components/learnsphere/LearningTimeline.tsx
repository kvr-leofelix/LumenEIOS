import React from 'react';
import type { Journey } from '../../types/learnsphere';
import { useLearning } from '../../pages/learnsphere/LearnSphereLayout';
export function LearningTimeline({data}: {data: Journey}) {
  const {scope} = useLearning();
  const subjectName = (id: string) => scope.classes.flatMap(c => c.subjects).find(s => s.id === id)?.name || id;
  const [subject, setSubject] = React.useState('');
  const [topic, setTopic] = React.useState('');
  const [competency, setCompetency] = React.useState('');
  const subjects = [...new Set(data.timeline.map(e => e.subject_id).filter(Boolean))];
  const topics = [...new Set(data.timeline.map(e => e.topic).filter(Boolean))];
  return <div className="space-y-4">
    <p>{data.participation} responses · {data.completed_assignments} completed assignments · {data.verified_observations} verified activity observations ? {data.assessment_observations?.length || 0} reviewed assessment observations</p>
    <h3 className="font-semibold">Panchapadi activity completion</h3><p>These counts include actual completed LearnSphere activities only. Assessment performance is shown separately above. A reviewed assessment does not complete an activity.</p>
    <div className="grid sm:grid-cols-5 gap-2">{Object.entries(data.stages).map(([stage, count]) => <div key={stage} className="bg-white border rounded-xl p-3"><strong>{stage}</strong><p>{count} completed activities</p></div>)}</div>
    <div className="flex flex-wrap gap-3">
      <label>Subject<select className="block border p-2 rounded" value={subject} onChange={e => setSubject(e.target.value)}><option value="">All subjects</option>{subjects.map(s => <option key={s!} value={s!}>{subjectName(s!)}</option>)}</select></label>
      <label>Topic<select className="block border p-2 rounded" value={topic} onChange={e => setTopic(e.target.value)}><option value="">All topics</option>{topics.map(t => <option key={t!}>{t}</option>)}</select></label>
      <label>Competency<select className="block border p-2 rounded" value={competency} onChange={e => setCompetency(e.target.value)}><option value="">All competencies</option>{['LU','CU','AU','CT'].map(c => <option key={c}>{c}</option>)}</select></label>
    </div>
    {!!data.assessment_observations?.length && <><h3 className="font-semibold">Teacher-reviewed assessment observations</h3><p>These are question competency outcomes, separate from stage scores and activity completions.</p>
      {data.assessment_observations.filter(o=>(!subject||o.subject_id===subject)&&(!topic||o.topic===topic)&&(!competency||o.competency===competency)).map(o=><div key={o.id} className="bg-white border p-3 rounded-xl"><strong>{o.assessment_title} · {o.competency}</strong><p>{subjectName(o.subject_id)} · {o.topic||'Topic unmapped'} · {o.score}/{o.maximum} · {o.provenance}</p></div>)}</>}
    <h3 className="font-semibold">Comparable learning outcomes</h3>
    {!data.trends.length && <p>No comparable teacher-verified scores yet. Missing scores are not zero.</p>}
    {data.trends.filter(t => (!subject || t.subject_id === subject) && (!topic || t.topic === topic) && (!competency || t.competency === competency)).map(t => <div className="bg-white border p-3 rounded-xl" key={`${t.topic_id}:${t.competency}:${t.scoring_basis}`}><strong>{subjectName(t.subject_id)} · {t.topic} · {t.competency}</strong><p>{t.change == null ? 'More comparable evidence needed' : `${t.change > 0 ? '+' : ''}${t.change} percentage points between comparable attempts`}</p><ul>{t.points.map((p, i) => <li key={i}>{new Date(p.date).toLocaleDateString()}: {p.score_pct}%</li>)}</ul></div>)}
    <h3 className="font-semibold">Learning history</h3>
    {!data.timeline.length && <p>No recorded assessments or learning activities yet.</p>}
    <ol className="space-y-3">{data.timeline.filter(e => (!subject || e.subject_id === subject) && (!topic || e.topic === topic) && (!competency || e.competency === competency)).map((e, i) => <li key={i} className="border-l-4 border-teal-600 bg-white rounded-r-xl p-4"><time className="text-sm">{new Date(e.date).toLocaleString()}</time><h4 className="font-semibold">{e.title}</h4><p>{e.topic} {e.competency} {e.stage && `· ${e.stage}`}</p><p>{e.detail}</p><span className="text-sm text-content-secondary">Source: {e.kind}</span></li>)}</ol>
  </div>;
}
