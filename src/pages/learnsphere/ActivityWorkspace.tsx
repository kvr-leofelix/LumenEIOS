import React, { useEffect, useState } from 'react';
import { MathText } from '../../components/common/MathText';
import { useLearning } from './LearnSphereLayout';
import { learnsphere } from '../../lib/learnsphere';
import type { Activity, Assignment, Attempt, Topic, Kind, Competency, Stage } from '../../types/learnsphere';
import { Button } from '../../components/common/Button';
import { Card, CardBody } from '../../components/common/Card';

const field = 'block w-full border border-surface-border rounded-lg p-2 bg-white';
const stages: Stage[] = ['Adheeti','Bodh','Abhyas','Prayog','Prasar'];
const codes: Competency[] = ['LU','CU','AU','CT'];

function AttemptCard({attempt, educator, student, kind, refresh}: {attempt: Attempt; educator: boolean; student: boolean; kind: Kind; refresh: () => Promise<void>}) {
  const [feedback, setFeedback] = useState('');
  const [outcome, setOutcome] = useState('');
  const [completed, setCompleted] = useState(true);
  const [criteria, setCriteria] = useState<{key: string; score: string; maximum: string; correct: string}[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function run(action: () => Promise<unknown>) {
    setBusy(true); setError('');
    try {await action(); await refresh();} catch(e) {setError((e as Error).message); await refresh();} finally {setBusy(false);}
  }
  return <div className="border rounded-xl p-4 space-y-3 bg-slate-50">
    <h4 className="font-semibold">Response · {new Date(attempt.submitted_at).toLocaleString()}</h4><p className="whitespace-pre-wrap"><MathText text={attempt.response} /></p>
    <p className="text-sm">Hints reported: {attempt.hints ?? 'not recorded'} · {attempt.completed ? 'Teacher recorded completion' : 'Awaiting completion review'}</p>
    {attempt.evaluations.map((r, i) => <div key={i} className="bg-white border rounded-lg p-3"><strong>{r.kind === 'teacher' ? 'Teacher-verified feedback' : r.kind === 'ai' ? 'AI feedback — not teacher verified' : 'AI evaluation could not finish'}</strong><p className="text-xs">{new Date(r.date).toLocaleString()}</p>
      {typeof r.feedback === 'string' ? <p><MathText text={r.feedback} /></p> : r.feedback ? <>{[['Correctly understood',r.feedback.correctly_understood], ['Missing concepts',r.feedback.missing_concepts], ['Misconceptions',r.feedback.misconceptions], ['Strengths',r.feedback.strengths]].map(([label, items]) => <div key={label as string}><h5 className="font-medium">{label as string}</h5>{(items as string[]).length ? <ul className="list-disc ml-5">{(items as string[]).map((text, j) => <li key={j}><MathText text={text} /></li>)}</ul> : <p>None identified.</p>}</div>)}<p>Next step: <MathText text={r.feedback.next_step} /></p></> : null}
      {r.outcome && <p>Outcome: {r.outcome}</p>}{r.error && <p>{r.error} Your submitted response remains saved.</p>}
    </div>)}
    {kind === 'teach_back' && (student || educator) && <Button variant="secondary" disabled={busy} onClick={() => run(() => learnsphere.evaluate(attempt.id))}>{attempt.evaluations.some(r => r.kind === 'ai') ? 'View saved AI evaluation' : 'Evaluate with AI / retry'}</Button>}
    {educator && <details><summary>Review response and record outcome</summary><form className="space-y-3 mt-3" onSubmit={e => {e.preventDefault(); run(() => learnsphere.review(attempt.id, {
      expected_version: attempt.version, feedback, outcome, completed,
      observations: criteria.map(c => ({key:c.key, score:Number(c.score), maximum:Number(c.maximum), correct:c.correct === '' ? null : c.correct === 'yes'})),
    }));}}>
      <label>Teacher feedback<textarea required maxLength={12000} className={field} value={feedback} onChange={e => setFeedback(e.target.value)} /></label>
      <label>Learning outcome<textarea required maxLength={4000} className={field} value={outcome} onChange={e => setOutcome(e.target.value)} /></label>
      <label className="flex gap-2"><input type="checkbox" checked={completed} onChange={e => {setCompleted(e.target.checked); if (!e.target.checked) setCriteria([]);}} />Activity completed</label>
      <p className="text-sm">Optional scored observations must describe independently assessed criteria. Leave them absent when understanding has not been measured. A new review supersedes earlier scored observations while preserving history.</p>
      {criteria.map((c,i) => <div key={i} className="grid sm:grid-cols-4 gap-2">
        <label>Criterion<input required maxLength={60} className={field} value={c.key} onChange={e => setCriteria(rows => rows.map((r,j) => j===i ? {...r,key:e.target.value}:r))} /></label>
        <label>Score<input required type="number" min={0} step="any" className={field} value={c.score} onChange={e => setCriteria(rows => rows.map((r,j) => j===i ? {...r,score:e.target.value}:r))} /></label>
        <label>Maximum<input required type="number" min={0.01} step="any" className={field} value={c.maximum} onChange={e => setCriteria(rows => rows.map((r,j) => j===i ? {...r,maximum:e.target.value}:r))} /></label>
        <label>Correctness<select className={field} value={c.correct} onChange={e => setCriteria(rows => rows.map((r,j) => j===i ? {...r,correct:e.target.value}:r))}><option value="">Not recorded</option><option value="yes">Correct</option><option value="no">Incorrect</option></select></label>
      </div>)}
      <div className="flex flex-wrap gap-2"><Button type="button" variant="secondary" disabled={!completed || busy || criteria.length>=50} onClick={() => setCriteria([...criteria,{key:'',score:'',maximum:'',correct:''}])}>Add scored criterion</Button><Button type="button" variant="secondary" disabled={busy || !criteria.length} onClick={() => setCriteria(criteria.slice(0,-1))}>Remove last criterion</Button><Button type="submit" loading={busy}>Save teacher review</Button></div>
    </form></details>}
    {error && <p role="alert" className="text-rose-700">{error}</p>}
  </div>;
}

function AssignmentCard({assignment, refresh}: {assignment: Assignment; refresh: () => Promise<void>}) {
  const {educator, student} = useLearning();
  const [response, setResponse] = useState('');
  const [hints, setHints] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [key, setKey] = useState(crypto.randomUUID());
  const s = assignment.snapshot;
  return <Card><CardBody><div className="space-y-3"><h3 className="text-lg font-semibold">{s.title}</h3><p>{s.topic_title} · {s.competency} · {s.stage} · version {s.version}</p><p className="whitespace-pre-wrap">{s.instructions}</p><details><summary>Evaluation rubric</summary><p className="whitespace-pre-wrap">{s.rubric}</p></details>
    {s.assessment_result_id&&<p className="text-sm">{s.generation==='automatic_provisional'?'Automatically generated AI follow-up':'Teacher-approved follow-up'} to assessment question{s.evidence_positions?.length===1?'':'s'} {s.evidence_positions?.map(p=>p+1).join(', ')}{s.generation==='automatic_provisional'?' (not teacher-verified)':''}. The assessment result and this activity are recorded separately.</p>}
    <p className="text-sm">Assigned {new Date(assignment.assigned_at).toLocaleDateString()}{assignment.due_at && ` · Due ${new Date(assignment.due_at).toLocaleString()}`}{assignment.intervention_for && ' · Follow-up intervention'}</p>
    {assignment.attempts.map(at => <AttemptCard key={`${at.id}:${at.version}`} attempt={at} educator={educator} student={student} kind={s.kind} refresh={refresh} />)}
    {!assignment.attempts.length && <p>No responses submitted yet.</p>}
    {student && <form className="space-y-3" onSubmit={async e => {
      e.preventDefault(); setBusy(true); setError('');
      try {
        const saved = await learnsphere.submit(assignment.id,{response,hints:hints==='' ? null:Number(hints),request_key:key});
        setResponse(''); setHints(''); setKey(crypto.randomUUID());
        await refresh();
        if (s.kind === 'teach_back') {try {await learnsphere.evaluate(saved.id);} finally {await refresh();}}
      } catch(e) {setError((e as Error).message);} finally {setBusy(false);}
    }}><label>Your explanation or findings<textarea required minLength={1} maxLength={16000} className={field} value={response} onChange={e => {setResponse(e.target.value); setKey(crypto.randomUUID());}} /></label>
      <label>Hints used, if known<input type="number" min={0} max={1000} step={1} className={field} value={hints} onChange={e => {setHints(e.target.value); setKey(crypto.randomUUID());}} /></label>
      <Button type="submit" loading={busy}>{s.kind === 'teach_back' ? 'Save explanation and evaluate' : 'Submit response'}</Button>
    </form>}{error && <p role="alert" className="text-rose-700">{error}</p>}
  </div></CardBody></Card>;
}

export function ActivityWorkspace({kind, onEvidenceChange}: {kind: Kind; onEvidenceChange?: () => void}) {
  const {scope, classId, studentId, educator} = useLearning();
  const [topics,setTopics] = useState<Topic[]>([]);
  const [activities,setActivities] = useState<Activity[]>([]);
  const [assignments,setAssignments] = useState<Assignment[]>([]);
  const [topicId,setTopicId] = useState('');
  const [topicTitle,setTopicTitle] = useState('');
  const section = scope.classes.find(c => c.id===classId);
  const [subject,setSubject] = useState(section?.subjects[0]?.id || '');
  const [title,setTitle] = useState('');
  const [instructions,setInstructions] = useState('');
  const [rubric,setRubric] = useState('');
  const [competency,setCompetency] = useState<Competency>('CU');
  const [stage,setStage] = useState<Stage>('Bodh');
  const [editId,setEditId] = useState('');
  const [allClass,setAllClass] = useState(false);
  const [followup,setFollowup] = useState('');
  const [due,setDue] = useState('');
  const [error,setError] = useState('');
  const [message,setMessage] = useState('');
  const [busy,setBusy] = useState(false);
  const [loading,setLoading] = useState(true);
  async function refresh() {if (studentId) setAssignments(await learnsphere.assignments(studentId)); onEvidenceChange?.();}
  useEffect(() => {
    let active = true;
    setLoading(true);
    const requests = [studentId ? learnsphere.assignments(studentId).then(v => active && setAssignments(v)) : Promise.resolve()];
    if (educator && classId) requests.push(Promise.all([learnsphere.topics(classId),learnsphere.activities(classId)]).then(([t,a]) => {if(active){setTopics(t);setTopicId(t[0]?.id || '');setActivities(a);}}));
    Promise.all(requests).catch(e => active && setError(e.message)).finally(() => active && setLoading(false));
    return () => {active = false;};
  }, [classId,studentId,educator]);
  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true);setError('');setMessage('');
    try {await action();setMessage(success);} catch(e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  return <div className="space-y-4">
    {loading && <p role="status">Loading activities…</p>}{error && <p role="alert" className="text-rose-700">{error}</p>}{message && <p role="status" className="text-teal-700">{message}</p>}
    {educator && classId && <Card><CardBody><details><summary className="font-semibold cursor-pointer">Create or manage {kind === 'teach_back' ? 'teach-back challenges' : kind === 'mission' ? 'missions' : 'support interventions'}</summary><div className="space-y-4 mt-4">
      <form className="grid sm:grid-cols-3 gap-3 items-end" onSubmit={e => {e.preventDefault();run(async () => {const t=await learnsphere.createTopic({class_id:classId,subject_id:subject,title:topicTitle});setTopics([...topics,t]);setTopicId(t.id);setTopicTitle('');},'Topic saved.');}}>
        <label>Subject<select required className={field} value={subject} onChange={e=>setSubject(e.target.value)}><option value="">Choose subject</option>{section?.subjects.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
        <label>New topic/chapter<input required maxLength={255} className={field} value={topicTitle} onChange={e=>setTopicTitle(e.target.value)} /></label><Button loading={busy} type="submit">Add topic</Button>
      </form>
      <form className="space-y-3" onSubmit={e=>{e.preventDefault();run(async()=>{const body={topic_id:topicId,kind,title,instructions,rubric,competency,stage};const a=editId?await learnsphere.updateActivity(editId,body):await learnsphere.createActivity(body);setActivities([...activities.filter(x=>x.id!==a.id),a]);setEditId('');setTitle('');setInstructions('');setRubric('');},'Activity saved. Previously assigned versions are preserved.');}}>
        <label>Topic<select required className={field} value={topicId} onChange={e=>setTopicId(e.target.value)}><option value="">Choose topic</option>{topics.map(t=><option key={t.id} value={t.id}>{t.title}</option>)}</select></label>
        <label>Title<input required maxLength={255} className={field} value={title} onChange={e=>setTitle(e.target.value)} /></label>
        <label>{kind === 'teach_back' ? 'Concept and explanation prompt' : 'Instructions'}<textarea required maxLength={12000} className={field} value={instructions} onChange={e=>setInstructions(e.target.value)} /></label>
        <label>Evaluation rubric<textarea required maxLength={12000} className={field} value={rubric} onChange={e=>setRubric(e.target.value)} /></label>
        <div className="grid sm:grid-cols-2 gap-3"><label>Competency<select className={field} value={competency} onChange={e=>setCompetency(e.target.value as Competency)}>{codes.map(c=><option key={c}>{c}</option>)}</select></label><label>Panchapadi stage<select className={field} value={stage} onChange={e=>setStage(e.target.value as Stage)}>{stages.map(s=><option key={s}>{s}</option>)}</select></label></div>
        <Button loading={busy} type="submit">{editId ? 'Save revised activity' : 'Create activity'}</Button>
      </form>
      <div className="space-y-3"><h3 className="font-semibold">Assign an activity</h3>
        <label className="flex gap-2"><input type="checkbox" checked={allClass} onChange={e=>{setAllClass(e.target.checked);setFollowup('');}} />Assign to all authorized students in this class</label>
        <label>Due date (optional)<input type="datetime-local" className={field} value={due} onChange={e=>setDue(e.target.value)} /></label>
        {!allClass && <label>Follow up on an earlier activity (optional)<select className={field} value={followup} onChange={e=>setFollowup(e.target.value)}><option value="">No previous activity</option>{assignments.map(a=><option value={a.id} key={a.id}>{a.snapshot.title}</option>)}</select></label>}
        {activities.filter(a=>a.kind===kind).map(a=><div key={a.id} className="border rounded-lg p-3 space-y-2"><p>{a.title} · {a.competency} · {a.stage} · version {a.version}</p><div className="flex gap-2 flex-wrap"><Button variant="secondary" disabled={busy} onClick={()=>{setEditId(a.id);setTopicId(a.topic_id);setTitle(a.title);setInstructions(a.instructions);setRubric(a.rubric);setCompetency(a.competency);setStage(a.stage);}}>Edit template</Button><Button disabled={busy || (!studentId && !allClass)} onClick={()=>run(async()=>{await learnsphere.assign(a.id,{student_ids:allClass?scope.students.filter(s=>s.class_id===classId).map(s=>s.id):[studentId],request_key:crypto.randomUUID(),due_at:due?new Date(due).toISOString():null,intervention_for:followup||null});await refresh();},'Activity assigned.')}>Assign {allClass ? 'to class' : 'to selected student'}</Button></div></div>)}
        {!activities.some(a=>a.kind===kind) && <p>No activities of this type yet. Create one above.</p>}
      </div>
    </div></details></CardBody></Card>}
    <h3 className="font-semibold">Assigned activities and history</h3>
    {!studentId ? <p>Select a student to view assigned activities.</p> : !loading && !assignments.some(a=>a.snapshot.kind===kind) ? <p>No activities of this type have been assigned yet.</p> : null}
    {assignments.filter(a=>a.snapshot.kind===kind).map(a=><AssignmentCard key={a.id} assignment={a} refresh={refresh} />)}
  </div>;
}
