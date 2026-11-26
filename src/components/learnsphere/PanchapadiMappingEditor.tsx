import React from 'react';
import { MathText } from '../common/MathText';
import type {AssessmentResult} from '../../types/assessmentResults';
import type {QuestionStageMapping,StageMapping} from '../../types/panchapadi';
import {PANCHAPADI_STAGES} from '../../types/panchapadi';
import {PanchapadiEvaluation} from './PanchapadiEvaluation';

export function PanchapadiMappingEditor({result,value,onChange}:{result:AssessmentResult;value:QuestionStageMapping[];onChange:(v:QuestionStageMapping[])=>void}){
  const update=(position:number,stage:string,patch:Partial<StageMapping>)=>onChange(value.map(q=>q.position===position?{...q,mappings:q.mappings.map(m=>m.stage===stage?{...m,...patch}:m)}:q));
  return <section className="space-y-4"><h3 className="font-semibold">Verify all five Panchapadi stages</h3>
    <PanchapadiEvaluation evaluation={result.panchapadi}/>
    <p>Correct the proposed mappings below. Exclude a question by clearing its stages. Each selected stage needs content-specific reasoning. Verified scores will use your confirmed marks, not AI marks.</p>
    {result.questions.map(question=>{const selected=value.find(q=>q.position===question.position)?.mappings||[];return <fieldset key={question.position} className="border rounded-lg p-3"><legend>Q{question.position+1} stage evidence</legend>
      <p><MathText text={question.text} /></p>{PANCHAPADI_STAGES.map(stage=>{const mapping=selected.find(m=>m.stage===stage);return <div key={stage} className="py-2">
        <label className="flex gap-2"><input type="checkbox" aria-label={`Q${question.position+1} ${stage}`} checked={!!mapping} onChange={e=>onChange(value.map(q=>q.position===question.position?{...q,mappings:e.target.checked?[...q.mappings,{stage,reasoning:'',prerequisite_test:false,procedural_practice:false,independent_extension:false}]:q.mappings.filter(m=>m.stage!==stage)}:q))}/>{stage}</label>
        {mapping&&<><label>Q{question.position+1} {stage} reasoning<textarea required maxLength={3000} className="block border rounded p-2 w-full" value={mapping.reasoning} onChange={e=>update(question.position,stage,{reasoning:e.target.value})}/></label>
          {stage==='Adheeti'&&<label className="flex gap-2"><input type="checkbox" checked={mapping.prerequisite_test} onChange={e=>update(question.position,stage,{prerequisite_test:e.target.checked})}/>This question explicitly tests prior/prerequisite knowledge or readiness</label>}
          {stage==='Abhyas'&&<label className="flex gap-2"><input type="checkbox" checked={mapping.procedural_practice} onChange={e=>update(question.position,stage,{procedural_practice:e.target.checked})}/>This question requires performing a learned procedure (at least two scored practice questions are needed)</label>}
          {stage==='Prasar'&&<label className="flex gap-2"><input type="checkbox" checked={mapping.independent_extension} onChange={e=>update(question.position,stage,{independent_extension:e.target.checked})}/>This question requires independent extension or new connections beyond routine application</label>}
        </>}
      </div>;})}
    </fieldset>;})}
  </section>;
}
