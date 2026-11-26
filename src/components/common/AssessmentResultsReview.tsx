import React, {useEffect,useState} from 'react';
import { MathText } from './MathText';
import {useAuth} from '../../context/AuthContext';
import {useData} from '../../context/DataContext';
import {assessmentResults} from '../../lib/assessmentResults';
import {learnsphere} from '../../lib/learnsphere';
import type {AssessmentResult} from '../../types/assessmentResults';
import type {Topic} from '../../types/learnsphere';
import {Card,CardHeader,CardBody} from './Card';
import {Button} from './Button';
import {PanchapadiMappingEditor} from '../learnsphere/PanchapadiMappingEditor';
import type {QuestionStageMapping} from '../../types/panchapadi';
import type {LearningDecision} from '../../types/assessmentResults';
import {AssessmentLearningEditor} from '../learnsphere/AssessmentLearningEditor';
import {AssessmentPerformanceSummary,performanceSummary} from '../learnsphere/AssessmentPerformanceSummary';

function Review({result,onSaved}:{result:AssessmentResult;onSaved:(r:AssessmentResult)=>void}){
  const [stageMappings,setStageMappings]=useState<QuestionStageMapping[]>(result.questions.map(q=>({position:q.position,mappings:[]})));
  const [stageDirty,setStageDirty]=useState(false);
  const [confirmStages,setConfirmStages]=useState(false);
  const [verifiedKeys,setVerifiedKeys]=useState<number[]>(result.outcomes.filter(o=>o.key_verified).map(o=>o.position));
  const [plan,setPlan]=useState<LearningDecision[]>([]);
  const [planDirty,setPlanDirty]=useState(false);
  useEffect(()=>{if(!planDirty)setPlan(result.reviews[result.reviews.length-1]?.learning_plan||result.learning_drafts?.map(d=>({...d,decision:'draft' as const,topic_id:null}))||[]);},[result.panchapadi?.attempt_id,result.panchapadi?.status,planDirty]);
  useEffect(()=>{if(!stageDirty){const mappings=result.reviews[result.reviews.length-1]?.panchapadi?.mapping||result.panchapadi?.mapping;if(mappings?.length)setStageMappings(mappings);}},[result.panchapadi?.attempt_id,result.panchapadi?.status,stageDirty]);
  const [topics,setTopics]=useState<Topic[]>([]);
  const initialRows=()=>result.questions.map(q=>({position:q.position,score:String(result.outcomes.find(o=>o.position===q.position)?.score??''),correct:result.outcomes.find(o=>o.position===q.position)?.correct==null?'':String(result.outcomes.find(o=>o.position===q.position)?.correct),feedback:result.outcomes.find(o=>o.position===q.position)?.feedback||'',topic_id:result.outcomes.find(o=>o.position===q.position)?.topic_id||'',explanation:result.outcomes.find(o=>o.position===q.position)?.explanation||''}));
  const [rows,setRows]=useState(initialRows);
  const [rowsDirty,setRowsDirty]=useState(false);
  useEffect(()=>{if(!rowsDirty)setRows(initialRows());},[result.panchapadi?.attempt_id,result.panchapadi?.status,rowsDirty]);
  const [feedback,setFeedback]=useState(()=>performanceSummary(result.outcomes));const [feedbackDirty,setFeedbackDirty]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  useEffect(()=>{if(!feedbackDirty)setFeedback(performanceSummary(result.outcomes));},[result.panchapadi?.attempt_id,result.panchapadi?.status,feedbackDirty]);
  useEffect(()=>{let active=true;learnsphere.topics(result.class_id).then(t=>active&&setTopics(t.filter(x=>x.subject_id===result.subject_id))).catch(e=>active&&setError(e.message));return()=>{active=false;};},[result.class_id,result.subject_id]);
  const update=(i:number,key:string,value:string)=>{setRowsDirty(true);setRows(current=>current.map((r,j)=>i===j?{...r,[key]:value}:r));};
  return <form className="space-y-4" onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{onSaved(await assessmentResults.review(result.id,{expected_version:result.version,feedback,confirm_panchapadi:confirmStages,panchapadi_mappings:confirmStages?stageMappings:null,learning_plan:plan.map(({activity_id,assignment_id,...item})=>item),questions:rows.map(r=>({...r,score:Number(r.score),correct:r.correct===''?null:r.correct==='true',topic_id:r.topic_id||null,verify_key:verifiedKeys.includes(r.position)}))}));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>
    <p>Student: {result.student_id} · {result.status.replace(/_/g,' ')}. Check actual responses and every score before confirming. Topic mapping is optional.</p>
    {result.evaluation_warnings?.map(w=><p key={w} role="status">{w}</p>)}
    <p>Automatic marks and feedback are provisional. Correct marks and mappings to recalculate stage percentages; a stage score is derived from eligible marks and cannot be replaced by an unsupported percentage.</p>
    <AssessmentPerformanceSummary outcomes={result.outcomes} verified={result.status==='teacher_reviewed'}/>
    {result.questions.map((q,i)=><fieldset key={i} disabled={busy} className="border rounded-lg p-3 space-y-2"><legend>{i+1}. <MathText text={q.text} /> · {q.competency}</legend><p>Response: <MathText text={result.answers[i]?.answer_text??q.options[result.answers[i]?.selected_option_index??-1]} /></p><p>Stored key: <MathText text={q.correct_answer||'No key'} /> · Rubric: <MathText text={q.marking_rubric||'No rubric'} /></p>
      <label>Verified marks (maximum {q.marks})<input required className="block border rounded p-2" type="number" min={0} max={q.marks} step={1} value={rows[i].score} onChange={e=>update(i,'score',e.target.value)}/></label>
      <label>Correctness<select className="block border rounded p-2" value={rows[i].correct} onChange={e=>update(i,'correct',e.target.value)}><option value="">Not recorded</option><option value="true">Correct</option><option value="false">Incorrect</option></select></label>
      <label>Question feedback<textarea required className="block border rounded p-2 w-full" value={rows[i].feedback} onChange={e=>update(i,'feedback',e.target.value)}/></label>
      <label>Teacher-only scoring explanation<textarea maxLength={4000} className="block border rounded p-2 w-full" value={rows[i].explanation} onChange={e=>update(i,'explanation',e.target.value)}/></label>
      {q.type==='mcq'&&q.correct_answer&&<label className="flex gap-2"><input type="checkbox" checked={verifiedKeys.includes(q.position)} onChange={e=>setVerifiedKeys(v=>e.target.checked?[...v,q.position]:v.filter(p=>p!==q.position))}/>Verify this stored MCQ key for deterministic marking of later submissions to this assessment</label>}
      <label>Verified topic<select className="block border rounded p-2" value={rows[i].topic_id} onChange={e=>update(i,'topic_id',e.target.value)}><option value="">Unmapped — do not infer a topic</option>{topics.map(t=><option key={t.id} value={t.id}>{t.title}</option>)}</select></label>
    </fieldset>)}
    <PanchapadiMappingEditor result={result} value={stageMappings} onChange={m=>{setStageDirty(true);setStageMappings(m);}}/>
    <label className="flex gap-2"><input type="checkbox" checked={confirmStages} onChange={e=>setConfirmStages(e.target.checked)}/>Confirm the corrected Panchapadi mappings and exclusions with this review</label>
    <AssessmentLearningEditor value={plan} onChange={p=>{setPlanDirty(true);setPlan(p);}} topics={topics} positions={result.questions.map(q=>q.position)}/>
    {!!result.learning_drafts?.length&&<Button type="button" variant="secondary" onClick={()=>{setPlanDirty(true);setPlan(result.learning_drafts!.map(d=>({...d,decision:'draft',topic_id:null})));}}>Load refreshed AI suggestions as drafts</Button>}
    <Button type="button" variant="secondary" disabled={busy||result.panchapadi?.status==='running'} onClick={async()=>{setBusy(true);setError('');try{const r=await assessmentResults.retryStages(result.id);onSaved({...r,panchapadi:r.panchapadi?{...r.panchapadi,status:'running'}:undefined});}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>Retry automatic stage evaluation</Button>
    <label>Overall teacher feedback<textarea required maxLength={12000} className="block border rounded p-2 w-full" value={feedback} onChange={e=>{setFeedbackDirty(true);setFeedback(e.target.value);}}/></label>
    {error&&<p role="alert" className="text-rose-700">{error}</p>}<Button type="submit" loading={busy}>Confirm reviewed assessment results</Button>
    <p className="text-sm">Only the latest teacher-reviewed outcomes contribute to LearnSphere. Automatic scores and earlier revisions remain preserved.</p>
  </form>;
}
function Panel(){
  const [results,setResults]=useState<AssessmentResult[]>();const [error,setError]=useState('');
  // Results carry only the student ID; the reviewer's workspace roster supplies the name.
  const {students}=useData();const studentName=(id:string)=>students.find(s=>s.id===id)?.name??id;
  useEffect(()=>{let active=true;assessmentResults.forReview().then(r=>active&&setResults(r)).catch(e=>active&&setError(e.message));return()=>{active=false;};},[]);
  const evaluating=results?.some(r=>['pending','running'].includes(r.panchapadi?.status||''));
  useEffect(()=>{if(!evaluating)return;let active=true;const timer=setInterval(()=>assessmentResults.forReview().then(r=>active&&setResults(r)).catch(e=>active&&setError(e.message)),5000);return()=>{active=false;clearInterval(timer);};},[evaluating]);
  return <Card><CardHeader title="Review submitted assessment answers"/><CardBody className="space-y-4">{error&&<p role="alert">{error}</p>}{!results&&!error&&<p role="status">Loading submitted answers…</p>}{results?.length===0&&<p>No student assessment responses are awaiting review.</p>}{results?.map(r=><details key={r.id} className="border rounded-xl p-3"><summary className="font-semibold">{r.assessment_title} · {studentName(r.student_id)}</summary><Review key={`${r.id}:${r.version}`} result={r} onSaved={saved=>setResults(current=>current?.map(x=>x.id===saved.id?saved:x))}/></details>)}</CardBody></Card>;
}
export function AssessmentResultsReview(){const {currentUser}=useAuth();return <Panel key={`${currentUser?.id}:${currentUser?.schoolId}`}/>;}
