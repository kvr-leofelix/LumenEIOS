import React from 'react';
import type {AssessmentOutcome} from '../../types/assessmentResults';
export function performanceSummary(outcomes:AssessmentOutcome[]){
  return outcomes.map(o=>`Q${o.position+1}: ${o.score==null?'Unassessed':o.score===o.maximum?'Strength demonstrated':o.score===0?'Needs review':'Partial understanding'} (${o.score??'unknown'}/${o.maximum}).`).join(' ');
}
export function AssessmentPerformanceSummary({outcomes,verified}:{outcomes:AssessmentOutcome[];verified:boolean}){
  return <section className="space-y-2"><h3 className="font-semibold">Assessment performance summary</h3><p>{verified?'Teacher-confirmed outcomes':'Provisional outcomes — not teacher confirmed'}</p><p>{performanceSummary(outcomes)}</p><div className="flex flex-wrap gap-4">{['LU','CU','AU','CT'].map(code=>{const eligible=outcomes.filter(o=>o.competency===code&&o.score!=null);const max=eligible.reduce((sum,o)=>sum+o.maximum,0);return <p key={code}>{code}: {max?`${Math.round(100*eligible.reduce((sum,o)=>sum+o.score!,0)/max)}% from ${eligible.length} scored questions`:'Insufficient evidence'}</p>;})}</div></section>;
}
