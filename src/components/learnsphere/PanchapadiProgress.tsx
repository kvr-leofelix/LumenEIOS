import React,{useEffect,useState} from 'react';
import {LineChart,Line,XAxis,YAxis,CartesianGrid,Tooltip,ResponsiveContainer,Legend} from 'recharts';
import {learnsphere} from '../../lib/learnsphere';
import type {PanchapadiHistory,StageHistoryPoint} from '../../types/panchapadi';
import {PANCHAPADI_STAGES} from '../../types/panchapadi';
import {Card,CardBody,CardHeader} from '../common/Card';
const confirmed=(p:StageHistoryPoint)=>p.teacher_verified??p.status==='verified';
const pointDot=(verified:boolean)=>({cx,cy,payload,index}:{cx?:number;cy?:number;payload?:StageHistoryPoint;index?:number})=>{
  const key=`${payload?.result_id??'point'}-${index??0}`;
  if(cx==null||cy==null||!payload||payload.score_pct==null||confirmed(payload)!==verified)return <g key={key}/>;
  return <circle key={key} className="assessment-progress-dot" data-status={verified?'confirmed':'provisional'} cx={cx} cy={cy} r={5} fill={verified?'#16805D':'#B76B08'} stroke="white" strokeWidth={1}/>;
};
function AssessmentTooltip({active,payload}:{active?:boolean;payload?:{payload:StageHistoryPoint}[]}){
  if(!active||!payload?.length)return null;const p=payload[0].payload;
  return <div className="bg-white border rounded-lg p-3 shadow"><strong>{p.assessment_name}</strong><p>{new Date(p.assessed_at).toLocaleString()}</p><p>{p.score_pct}% {confirmed(p)?'teacher-confirmed':'provisional AI evidence'}</p><p>{p.evidence_count} questions · {p.earned_marks}/{p.maximum_marks} marks</p></div>;
}
export function PanchapadiProgress({studentId}:{studentId:string}){
  const [history,setHistory]=useState<PanchapadiHistory>();const [error,setError]=useState('');
  useEffect(()=>{let active=true;setHistory(undefined);setError('');if(studentId)learnsphere.panchapadi(studentId).then(h=>active&&setHistory(h)).catch(e=>active&&setError(e.message));return()=>{active=false;};},[studentId]);
  return <section aria-label="Panchapadi Progress" className="space-y-4"><h2 className="text-xl font-semibold">Panchapadi Progress</h2><p>Green shows teacher-confirmed assessment evidence. Amber shows provisional evidence separately. One point does not establish improvement or mastery. Insufficient evidence is not zero.</p>
    {error&&<p role="alert">{error}</p>}{!history&&!error&&<p role="status">Loading stage history…</p>}
    {PANCHAPADI_STAGES.map(stage=>{const points=history?.graphs.find(g=>g.stage===stage)?.points||[];const eligible=points.filter(p=>p.score_pct!=null);const verified=eligible.filter(confirmed).length;const provisional=eligible.length-verified;
      const plotted=points.map(p=>({...p,confirmed_pct:confirmed(p)?p.score_pct:null,provisional_pct:confirmed(p)?null:p.score_pct}));
      return <Card key={stage} aria-label={`${stage} Progress`}><CardHeader title={`${stage} Progress`}/><CardBody>
        {history&&eligible.length===0&&<p>No eligible evidence for {stage} yet. More assessed evidence is needed.</p>}{eligible.length===1&&<p>One recorded assessment point; more evidence is needed to assess change over time.</p>}
        <div role="img" aria-label={`${stage} assessment performance by date`} style={{height:260,width:'100%'}}><ResponsiveContainer width="100%" height="100%"><LineChart data={plotted} margin={{top:15,right:25,left:5,bottom:15}}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="assessed_at" tickFormatter={v=>new Date(v).toLocaleDateString()} label={{value:'Assessment date/time',position:'insideBottom',offset:-10}}/><YAxis domain={[0,100]} ticks={[0,25,50,75,100]} label={{value:'Performance %',angle:-90,position:'insideLeft'}}/><Tooltip content={<AssessmentTooltip/>}/><Legend verticalAlign="top"/>
          <Line type="linear" dataKey="confirmed_pct" name="Teacher-confirmed" stroke="#16805D" strokeWidth={verified>1?2:0} connectNulls={false} dot={pointDot(true)} isAnimationActive={false}/>
          <Line type="linear" dataKey="provisional_pct" name="Provisional" stroke="#B76B08" strokeWidth={provisional>1?2:0} strokeDasharray="5 4" connectNulls={false} dot={pointDot(false)} isAnimationActive={false}/>
        </LineChart></ResponsiveContainer></div>
        {!!points.length&&<details><summary>Recorded assessment evidence</summary><ul>{points.map(p=><li key={p.result_id}>{p.assessment_name} · {new Date(p.assessed_at).toLocaleString()} · {p.score_pct==null?'Insufficient evidence':`${p.score_pct}% ${confirmed(p)?'teacher-confirmed':'provisional'}`} · {p.explanation}</li>)}</ul></details>}
      </CardBody></Card>;
    })}
  </section>;
}
