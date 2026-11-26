import React from 'react';
import type {LearningDecision} from '../../types/assessmentResults';
import type {Topic} from '../../types/learnsphere';
import {PANCHAPADI_STAGES} from '../../types/panchapadi';
export function AssessmentLearningEditor({value,onChange,topics,positions}:{value:LearningDecision[];onChange:(v:LearningDecision[])=>void;topics:Topic[];positions:number[]}){
  const update=(i:number,patch:Partial<LearningDecision>)=>onChange(value.map((v,j)=>i===j?{...v,...patch}:v));
  return <section className="space-y-3"><h3 className="font-semibold">Personalised support, Teach-Back and mission drafts</h3><p>AI suggestions are not diagnoses. Edit and approve each item. Challenges and missions need an existing verified topic before assignment. Draft and rejected content remains teacher-only. Approval creates an assignment, never a completion.</p>
    {value.map((item,i)=><details key={i} className="border rounded p-3"><summary>{item.kind}: {item.title} · {item.decision}</summary>
      <label>Decision<select className="block border p-2" value={item.decision} onChange={e=>update(i,{decision:e.target.value as LearningDecision['decision']})}>{['draft','approved','rejected'].map(v=><option key={v}>{v}</option>)}</select></label>
      <label>Verified topic<select className="block border p-2" value={item.topic_id||''} onChange={e=>update(i,{topic_id:e.target.value||null})}><option value="">Unmapped</option>{topics.map(t=><option key={t.id} value={t.id}>{t.title}</option>)}</select></label>
      <label>Stage<select className="block border p-2" value={item.stage} onChange={e=>update(i,{stage:e.target.value as LearningDecision['stage']})}>{PANCHAPADI_STAGES.map(s=><option key={s}>{s}</option>)}</select></label>
      <label>Evidence question numbers<input required className="block border p-2" value={item.positions.map(p=>p+1).join(',')} onChange={e=>update(i,{positions:e.target.value.split(',').map(v=>Number(v.trim())-1)})}/></label>
      {(['title','explanation','learning_tip','scenario','instructions','expected_submission','objective','rubric'] as const).map(key=><label key={key} className="block">{key.replace(/_/g,' ')}<textarea required maxLength={key==='title'?255:key==='instructions'?8000:2000} className="block border p-2 w-full" value={item[key]} onChange={e=>update(i,{[key]:e.target.value})}/></label>)}
      {item.assignment_id&&<p>Previously approved assignment: {item.assignment_id}. Saving unchanged content reuses it; edited approved content creates a new assignment.</p>}
    </details>)}
    <div className="flex flex-wrap gap-2">{(['support','teach_back','mission'] as const).map(kind=><button type="button" className="border rounded p-2" key={kind} onClick={()=>onChange([...value,{kind,positions:positions.slice(0,1),stage:'Bodh',title:'',explanation:'',learning_tip:'',scenario:'',instructions:'',expected_submission:'',objective:'',rubric:'',decision:'draft',topic_id:null}])}>Add teacher-authored {kind}</button>)}</div>
  </section>;
}
