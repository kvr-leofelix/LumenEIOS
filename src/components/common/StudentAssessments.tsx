import React, { useEffect, useState } from 'react';
import { marksLabel } from '../../lib/utils';
import { useAuth } from '../../context/AuthContext';
import { apiClient, UploadAssignment } from '../../lib/apiClient';
import { assessmentResults } from '../../lib/assessmentResults';
import type { AssessmentResult, AssessmentAnswer } from '../../types/assessmentResults';
import { Card, CardBody, CardHeader } from './Card';
import { Button } from './Button';
import { MathText } from './MathText';
import {PanchapadiEvaluation} from '../learnsphere/PanchapadiEvaluation';
import {AssessmentPerformanceSummary} from '../learnsphere/AssessmentPerformanceSummary';

function AnswerForm({assessment,onSaved}: {assessment: UploadAssignment; onSaved: (r: AssessmentResult)=>void}) {
  const [answers,setAnswers] = useState<Record<number,AssessmentAnswer>>({});
  const [key,setKey] = useState(crypto.randomUUID());
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const update=(position:number,answer:AssessmentAnswer)=>{setAnswers(current=>({...current,[position]:answer}));setKey(crypto.randomUUID());};
  return <form className="space-y-4" onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{onSaved(await assessmentResults.submit(assessment.id,Object.values(answers),key));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>
    <p>Submit your own answers. Responses lock after submission. Automatic marking is provisional until teacher confirmation.</p>
    {assessment.questions.map((q,i)=><fieldset key={i} disabled={busy} className="border rounded-xl p-3"><legend>{i+1}. <MathText text={q.text} /> ({marksLabel(q.marks)} · {q.competency})</legend>
      {q.type==='mcq' ? (q.options||[]).map((option,j)=><label key={j} className="block py-1"><input required type="radio" name={`answer-${assessment.id}-${i}`} checked={answers[i]?.selected_option_index===j} onChange={()=>update(i,{position:i,selected_option_index:j})} /> <MathText text={option} /></label>):<label>Your answer<textarea required maxLength={16000} className="block w-full border rounded-lg p-2" value={answers[i]?.answer_text||''} onChange={e=>update(i,{position:i,answer_text:e.target.value})} /></label>}
    </fieldset>)}
    {error&&<p role="alert" className="text-rose-700">{error}</p>}<Button type="submit" loading={busy}>Submit assessment answers</Button>
  </form>;
}

function Panel() {
  const [assigned,setAssigned] = useState<UploadAssignment[]>();
  const [results,setResults] = useState<AssessmentResult[]>([]);
  const [error,setError] = useState('');
  useEffect(()=>{let active=true;Promise.all([apiClient.assessments.uploadAssignments(),assessmentResults.mine()]).then(([a,r])=>{if(active){setAssigned(a);setResults(r);}}).catch(e=>active&&setError(e.message));return()=>{active=false;};},[]);
  const evaluating=results.some(r=>['pending','running'].includes(r.panchapadi?.status||''));
  useEffect(()=>{if(!evaluating)return;let active=true;const timer=setInterval(()=>assessmentResults.mine().then(r=>active&&setResults(r)).catch(e=>active&&setError(e.message)),5000);return()=>{active=false;clearInterval(timer);};},[evaluating]);
  return <Card><CardHeader title="My assigned assessments" subtitle="Answer the assessments assigned to your class in AI Question Studio."/><CardBody className="space-y-4">
    {error&&<p role="alert" className="text-rose-700">{error}</p>}{!assigned&&!error&&<p role="status">Loading assessments…</p>}
    {assigned?.length===0&&results.length===0&&<p>No assessments have been assigned yet.</p>}
    {assigned?.filter(a=>!results.some(r=>r.assessment_id===a.id)).map(a=><details key={a.id} className="border rounded-xl p-4"><summary className="font-semibold cursor-pointer">{a.title} · {a.subject_name}</summary><AnswerForm assessment={a} onSaved={r=>setResults(current=>[...current,r])}/></details>)}
    {results.map(r=><details key={r.id} className="border rounded-xl p-4"><summary className="font-semibold">{r.assessment_title} · {r.status.replace(/_/g,' ')}</summary>
      <p>{r.marks_obtained==null?'Overall marks await teacher review':`${r.marks_obtained}/${r.total_marks} marks`}{r.status!=='teacher_reviewed'&&' — not confirmed learning evidence'}</p>
      {r.questions.map(q=><div key={q.position} className="py-2 border-b"><p><MathText text={q.text} /></p><p><MathText text={r.answers.find(a=>a.position===q.position)?.answer_text ?? q.options[r.answers.find(a=>a.position===q.position)?.selected_option_index??-1]} /></p><p>{r.outcomes.find(o=>o.position===q.position)?.score??'Pending'}/{q.marks} · {r.outcomes.find(o=>o.position===q.position)?.provenance}</p></div>)}
      {r.reviews.map(review=><p key={review.revision_id}>Teacher feedback: {review.feedback}</p>)}
      <PanchapadiEvaluation evaluation={r.reviews[r.reviews.length-1]?.panchapadi||r.panchapadi}/>
      <AssessmentPerformanceSummary outcomes={r.outcomes} verified={r.status==='teacher_reviewed'}/>
    </details>)}
  </CardBody></Card>;
}
export function StudentAssessments(){const {currentUser}=useAuth();return <Panel key={`${currentUser?.id}:${currentUser?.schoolId}`}/>;}
