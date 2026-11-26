import React,{useState} from 'react';
import {BarChart,Bar,XAxis,YAxis,Tooltip,ResponsiveContainer} from 'recharts';
import type {StageEvaluation,AssessmentStages} from '../../types/panchapadi';
import {PANCHAPADI_STAGES} from '../../types/panchapadi';
export function PanchapadiEvaluation({evaluation}:{evaluation?:StageEvaluation}){
  return <div className="space-y-3"><p className="text-sm">{evaluation?.teacher_verified?'Teacher-verified assessment stages':'Provisional AI stage evaluation — not teacher verified'} · {evaluation?.status||'Not evaluated'}</p>
    {evaluation?.error&&<p role="status">{evaluation.error}</p>}
    <div className="grid sm:grid-cols-2 gap-3">{PANCHAPADI_STAGES.map(stage=>{const score=evaluation?.stages.find(s=>s.stage===stage);return <div key={stage} className="border rounded-lg p-3 bg-white"><h4 className="font-semibold">{stage}</h4><p>{score?.score_pct==null?'Insufficient evidence':`${score.score_pct}% · ${score.status}`}</p>
      {score&&<><p className="text-sm">{score.evidence_count} scored questions · {score.earned_marks??'Unknown'}/{score.maximum_marks??'Unknown'} available marks</p><p className="text-sm">{score.explanation}</p><details><summary>Supporting questions and reasoning</summary>{score.contributions.length?score.contributions.map(c=><p key={c.position} className="text-sm my-2">Q{c.position+1}: {c.reasoning} · {c.score??'Unknown'}/{c.maximum}{!c.eligible&&` · Excluded: ${c.exclusion_reason}`}</p>):<p>No relevant questions identified.</p>}</details></>}
    </div>;})}</div>
  </div>;
}
export function PanchapadiAssessmentList({assessments,hideSelector=false}:{assessments?:AssessmentStages[];hideSelector?:boolean}){
  const [selectedId,setSelectedId]=useState('');
  const selected=assessments?.find(a=>a.result_id===selectedId)||assessments?.[assessments.length-1];
  return <section aria-label="Panchapadi assessment performance" className="space-y-3"><h3 className="text-lg font-semibold">Panchapadi assessment performance</h3><p>Assessment scores and activity completion counts measure different things. Missing evidence is not zero; scores describe this assessment only.</p>
    {!selected?<p>No saved assessment evaluations are available yet.</p>:<>
      {!hideSelector&&<label>Assessment<select className="block border rounded p-2" value={selected.result_id} onChange={e=>setSelectedId(e.target.value)}>{assessments?.map(a=><option key={a.result_id} value={a.result_id}>{a.assessment_name} · {new Date(a.assessed_at).toLocaleString()}</option>)}</select></label>}
      <p>{selected.evaluation.teacher_verified?'Teacher-verified stage mappings and marks':'Provisional stage evaluation — teacher confirmation required'}</p>
      <div className="overflow-x-auto"><table className="w-full text-left border"><caption className="text-left">Five-stage performance distribution</caption><thead><tr>{['Stage','Score','Evidence','Status'].map(h=><th key={h} className="p-2">{h}</th>)}</tr></thead><tbody>{PANCHAPADI_STAGES.map(stage=>{const score=selected.evaluation.stages.find(s=>s.stage===stage);return <tr key={stage}><th className="p-2">{stage}</th><td className="p-2">{score?.score_pct==null?'Insufficient evidence':`${score.score_pct}%`}</td><td className="p-2">{score?.evidence_count?`${score.evidence_count} scored question(s): ${score.contributions.filter(c=>c.eligible).map(c=>`Q${c.position+1}`).join(', ')}`:'No eligible scored questions'}</td><td className="p-2">{score?.score_pct==null?'Insufficient evidence':selected.evaluation.teacher_verified?'Verified':'Provisional'}</td></tr>;})}</tbody></table></div>
      <div role="img" aria-label="Selected assessment five-stage score distribution" style={{height:240}}><ResponsiveContainer width="100%" height="100%"><BarChart data={selected.evaluation.stages}><XAxis dataKey="stage"/><YAxis domain={[0,100]}/><Tooltip formatter={(v:number)=>`${v}%`}/><Bar dataKey="score_pct" name={selected.evaluation.teacher_verified?'Verified score %':'Provisional score %'} fill="#16A085" isAnimationActive={false}/></BarChart></ResponsiveContainer></div>
      <p>The five scores are independent percentages, not shares that must total 100. Missing evidence has no bar.</p>
      <details><summary>Questions, reasoning and evidence limits</summary><PanchapadiEvaluation evaluation={selected.evaluation}/></details>
      {selected.learning_plan?.filter(p=>p.decision==='approved').map((p,i)=><article className="border rounded p-3" key={i}><h4 className="font-semibold">{p.title}</h4><p>{p.explanation}</p><p>{p.learning_tip}</p><p>{p.objective}</p><p>Teacher-approved {p.kind} · {p.stage} · Assessment questions {p.positions.map(n=>n+1).join(', ')}</p>{p.assignment_id?<p>Open the assigned activity in {p.kind==='teach_back'?'Teach-Back Challenge':p.kind==='mission'?'Real-Life Missions':'Learning Support'}.</p>:<p>Practice suggestion only; no activity completion has been recorded.</p>}</article>)}
    </>}
  </section>;
}
