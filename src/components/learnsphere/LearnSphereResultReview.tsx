import { MathText } from '../common/MathText';
import React,{useEffect,useState} from 'react';
import type {AssessmentResult} from '../../types/assessmentResults';
import type {QuestionStageMapping} from '../../types/panchapadi';
import {assessmentResults} from '../../lib/assessmentResults';
import {learnsphere} from '../../lib/learnsphere';
import {PanchapadiMappingEditor} from './PanchapadiMappingEditor';
import {Button} from '../common/Button';

export function LearnSphereResultReview({resultId,onSaved}:{resultId:string;onSaved:()=>void}){
  const [result,setResult]=useState<AssessmentResult>();
  const [rows,setRows]=useState<{position:number;score:string;feedback:string;verify_key:boolean}[]>([]);
  const [mappings,setMappings]=useState<QuestionStageMapping[]>([]);
  const [confirmStages,setConfirmStages]=useState(false);
  const [feedback,setFeedback]=useState('');const [error,setError]=useState('');const [busy,setBusy]=useState(false);
  useEffect(()=>{
    let active=true;setError('');setResult(undefined);
    learnsphere.assessmentResult(resultId).then(value=>{
      if(!active)return;setResult(value);
      setRows(value.questions.map(q=>{const outcome=value.outcomes.find(o=>o.position===q.position);return {
        position:q.position,score:outcome?.score==null?'':String(outcome.score),
        feedback:outcome?.feedback||'',verify_key:!!outcome?.key_verified,
      };}));
      setMappings(value.questions.map(q=>value.panchapadi?.mapping.find(m=>m.position===q.position)||{position:q.position,mappings:[]}));
    }).catch(e=>active&&setError(e.message));return()=>{active=false;};
  },[resultId]);
  return <div className="space-y-3">
    {!result&&!error&&<p role="status">Loading saved answers and review evidence…</p>}
    {result&&<form className="space-y-3" onSubmit={async event=>{
      event.preventDefault();setBusy(true);setError('');
      try{
        await assessmentResults.review(result.id,{
          expected_version:result.version,feedback,confirm_panchapadi:confirmStages,
          panchapadi_mappings:confirmStages?mappings:null,
          questions:rows.map(row=>({...row,score:Number(row.score),
            correct:Number(row.score)===result.questions.find(q=>q.position===row.position)!.marks,
            topic_id:result.outcomes.find(o=>o.position===row.position)?.topic_id||null})),
        });
        onSaved();
      }catch(e){setError((e as Error).message);}finally{setBusy(false);}
    }}>
      <p>AI marks are suggestions. Unknown marks remain blank until you assess the saved response. Confirmation appends a teacher review; earlier answers and reviews remain unchanged.</p>
      <fieldset disabled={busy} className="space-y-3">
        {result.questions.map((q,index)=><div key={q.position} className="border rounded p-3 space-y-2">
          <p className="font-semibold">Q{q.position+1}. <MathText text={q.text} /></p>
          <p>Saved response: <MathText text={result.answers.find(a=>a.position===q.position)?.answer_text ?? q.options[result.answers.find(a=>a.position===q.position)?.selected_option_index ?? -1] ?? 'Not available'} /></p>
          <p>Expected answer: <MathText text={q.correct_answer||'Not provided'} /></p><p>Rubric: <MathText text={q.marking_rubric||'Not provided'} /></p>
          <label>Q{q.position+1} reviewed marks<input aria-label={`Q${q.position+1} reviewed marks`} className="block border rounded p-2" type="number" required min={0} max={q.marks} step={1} value={rows[index]?.score||''} onChange={e=>setRows(current=>current.map((row,i)=>i===index?{...row,score:e.target.value}:row))}/></label>
          <label>Q{q.position+1} feedback<textarea required maxLength={4000} className="block border rounded p-2 w-full" value={rows[index]?.feedback||''} onChange={e=>setRows(current=>current.map((row,i)=>i===index?{...row,feedback:e.target.value}:row))}/></label>
          {q.type==='mcq'&&<label className="flex gap-2"><input type="checkbox" checked={rows[index]?.verify_key||false} onChange={e=>setRows(current=>current.map((row,i)=>i===index?{...row,verify_key:e.target.checked}:row))}/>I verified this stored MCQ answer key</label>}
        </div>)}
        <details><summary>Review Panchapadi stage mappings</summary><PanchapadiMappingEditor result={result} value={mappings} onChange={setMappings}/></details>
        <label className="flex gap-2"><input type="checkbox" checked={confirmStages} onChange={e=>setConfirmStages(e.target.checked)}/>Confirm the displayed stage mappings with these reviewed marks</label>
        <label>Overall teacher feedback<textarea required maxLength={12000} className="block border rounded p-2 w-full" value={feedback} onChange={e=>setFeedback(e.target.value)}/></label>
      </fieldset>
      <Button type="submit" loading={busy}>Confirm reviewed marks</Button>
    </form>}
    {error&&<p role="alert">{error}</p>}
  </div>;
}
