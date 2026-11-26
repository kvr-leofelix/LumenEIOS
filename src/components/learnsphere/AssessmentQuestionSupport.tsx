import React,{useEffect,useState} from 'react';
import { MathText } from '../common/MathText';
import {useAuth} from '../../context/AuthContext';
import {learnsphere} from '../../lib/learnsphere';
import {assessmentResults} from '../../lib/assessmentResults';
import type {AssessmentOption,AssessmentGuidance} from '../../types/assessmentGuidance';
import {useLearning} from '../../pages/learnsphere/LearnSphereLayout';
import {PanchapadiAssessmentList} from './PanchapadiEvaluation';
import {Button} from '../common/Button';
import {GuidanceAudienceItems} from './GuidanceAudienceItems';
import {CompetencyReview} from './CompetencyReview';
import {LearnSphereResultReview} from './LearnSphereResultReview';
export function AssessmentQuestionSupport(){
  const {studentId,educator}=useLearning();
  const {currentUser}=useAuth();const answerLabel=currentUser?.role==='student'?'Your answer':'Student answer';
  const [reviewOpen,setReviewOpen]=useState(false);
  useEffect(()=>setReviewOpen(false),[studentId]);
  const [options,setOptions]=useState<AssessmentOption[]>();const [selected,setSelected]=useState('');
  const [data,setData]=useState<AssessmentGuidance>();const [error,setError]=useState('');const [refresh,setRefresh]=useState(0);const [busy,setBusy]=useState(false);
  useEffect(()=>{let active=true;setOptions(undefined);setData(undefined);setSelected('');setError('');if(studentId)learnsphere.assessmentOptions(studentId).then(list=>{if(active){setOptions(list);setSelected(list[list.length-1]?.assessment_id||'');}}).catch(e=>active&&setError(e.message));return()=>{active=false;};},[studentId]);
  useEffect(()=>{let active=true;setData(undefined);setError('');if(selected)learnsphere.assessmentGuidance(studentId,selected).then(v=>active&&setData(v)).catch(e=>active&&setError(e.message));return()=>{active=false;};},[studentId,selected,refresh]);
  const pending=data?.guidance_status==='running'||data?.guidance_status==='pending';
  useEffect(()=>{if(!pending)return;let active=true;const timer=setInterval(()=>learnsphere.assessmentGuidance(studentId,selected).then(v=>active&&setData(v)).catch(e=>active&&setError(e.message)),5000);return()=>{active=false;clearInterval(timer);};},[pending,studentId,selected]);
  return <section aria-label="Question-wise assessment support" className="space-y-4"><label className="font-semibold">Assessment<select aria-label="Learning Support assessment" className="block border rounded p-2 w-full" disabled={!options?.length} value={selected} onChange={e=>{setSelected(e.target.value);setReviewOpen(false);}}><option value="">Select a submitted assessment</option>{options?.map(a=><option key={a.assessment_id} value={a.assessment_id}>{a.name} · {a.subject} · {a.date}</option>)}</select></label>
    {error&&<p role="alert">{error}</p>}{studentId&&!options&&!error&&<p role="status">Loading assessments…</p>}{options?.length===0&&<p>No submitted assessments are available for this student yet.</p>}{selected&&!data&&!error&&<p role="status">Loading question-wise guidance…</p>}
    {data&&<><h3 className="text-lg font-semibold">{data.name} · {data.subject}</h3><p>{data.evaluation_status==='teacher_reviewed'?'Question marks are teacher-reviewed.':'Question marks are provisional; teacher review is pending.'} Generated advice is provisional AI guidance, not a diagnosis.</p>
      {educator&&<div className="flex gap-3"><Button disabled={busy||data.guidance_status==='running'} onClick={async()=>{setBusy(true);setError('');try{await assessmentResults.retryStages(data.result_id,true);setRefresh(v=>v+1);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>Refresh assessment guidance</Button><Button variant="secondary" onClick={()=>setReviewOpen(open=>!open)}>{reviewOpen?'Close assessment review':'Review and confirm assessment'}</Button></div>}
      {educator&&reviewOpen&&<LearnSphereResultReview key={data.result_id} resultId={data.result_id} onSaved={()=>{setReviewOpen(false);setRefresh(v=>v+1);}}/>}
      {pending&&<p role="status">Automatic guidance is being evaluated. Your saved answers are preserved.</p>}{data.warnings.map(w=><p key={w}>{w}</p>)}
      {data.questions.map(q=><article key={q.position} className="border rounded-xl bg-white p-4 space-y-2"><h4 className="font-semibold">Q{q.position+1}. <MathText text={q.text} /></h4><p className="whitespace-pre-wrap">{answerLabel}: <MathText text={q.answer??'No saved answer available'} /></p><p>{q.status} · {q.score??'Unknown'}/{q.maximum} marks · {q.competency} · {q.stages.length?q.stages.join(', '):'Stage unmapped'}</p>
        {q.competency_mapping&&<div className="text-sm"><p>Primary competency: {q.competency_mapping.label||'Unmapped'} | {q.competency_mapping.status.startsWith('teacher_')?'Teacher-reviewed':'Provisional AI analysis'}{q.competency_mapping.confidence!=null&&(' | model confidence '+Math.round(q.competency_mapping.confidence*100)+'%')}</p><p>{q.competency_mapping.reason}</p>{educator&&<CompetencyReview key={data.result_id+':'+q.position+':'+(data.automation_version||0)} studentId={studentId} assessmentId={selected} position={q.position} mapping={q.competency_mapping} version={data.automation_version||0} onSaved={()=>setRefresh(v=>v+1)}/>}</div>}
        {q.concept_evidence&&<p className="text-sm">Provisional semantic evidence | Demonstrated: {q.concept_evidence.demonstrated.join('; ')||'Not identified'} | Partial: {q.concept_evidence.partial.join('; ')||'Not identified'} | Missing: {q.concept_evidence.missing.join('; ')||'Not identified'}</p>}
        <p>Expected concept: <MathText text={q.guidance?.expected_concept||'Not available; further teacher guidance is needed.'} /></p>{q.correct_answer&&<p>Available answer: <MathText text={q.correct_answer} /></p>}{q.feedback&&<p>Evaluation feedback: <MathText text={q.feedback} /></p>}
        {q.guidance?<><p>{q.guidance.misunderstanding&&`What to improve: ${q.guidance.misunderstanding}`}</p><p>How to improve: <MathText text={q.guidance.explanation} /></p>{q.score===q.maximum?<details><summary>Optional enrichment</summary><GuidanceAudienceItems guidance={q.guidance}/></details>:<GuidanceAudienceItems guidance={q.guidance}/>}</>:<p>{q.missing_information}</p>}
      </article>)}
      <PanchapadiAssessmentList assessments={[data.performance]} hideSelector/>
      {!!data.concept_stages?.length&&<details><summary>Concept evidence by stage</summary><p className="text-sm">Concept descriptions are provisional AI guidance. Correct, partial and missing classifications follow the saved marks; stage confirmation is shown above. Missing evidence is excluded, never scored as zero.</p>{data.concept_stages.map(stage=><div className="py-2" key={stage.stage}><h4 className="font-semibold">{stage.stage}</h4>{(['demonstrated','partial','missing'] as const).map(kind=><p key={kind}>{kind} ({stage[kind].length}): {stage[kind].map(item=>'Q'+(item.position+1)+': '+item.concept).join('; ')||'No supporting concept evidence'}</p>)}</div>)}</details>}
    </>}
  </section>;
}
