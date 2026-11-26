import React, {useState} from 'react';
import {learnsphere} from '../../lib/learnsphere';
import {Button} from '../common/Button';
import type {CompetencyMapping} from '../../types/assessmentGuidance';

export function CompetencyReview({studentId,assessmentId,position,mapping,version,onSaved}:{
  studentId:string;assessmentId:string;position:number;mapping:CompetencyMapping;version:number;onSaved:()=>void
}){
  const [label,setLabel]=useState(mapping.label||'');
  const [reason,setReason]=useState(mapping.status==='pending'?'':mapping.reason);
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  const [requestKey,setRequestKey]=useState(()=>crypto.randomUUID());
  return <details><summary>Review primary competency</summary>
    <form className="space-y-2 py-2" onSubmit={async event=>{
      event.preventDefault();setBusy(true);setError('');
      try{
        await learnsphere.reviewCompetencies(studentId,assessmentId,{
          expected_version:version,request_key:requestKey,questions:[{position,label:label||null,reason:reason.trim()}],
        });
        onSaved();
      }catch(e){setError((e as Error).message);}finally{setBusy(false);}
    }}>
      <p>Competency classification is separate from Panchapadi stage evidence. Confirming it does not confirm marks or activity completion.</p>
      <label>Primary competency<select aria-label={`Q${position+1} primary competency`} className="block border rounded p-2" value={label} disabled={busy} onChange={e=>{setLabel(e.target.value);setRequestKey(crypto.randomUUID());}}>
        <option value="">Unmapped — needs review</option>
        <option value="LU">LU — Language Understanding</option><option value="CU">CU — Concept Understanding</option>
        <option value="AU">AU — Application</option><option value="CT">CT — Critical Thinking</option>
      </select></label>
      <label>Mapping reason<textarea required maxLength={2000} className="block border rounded p-2 w-full" value={reason} disabled={busy} onChange={e=>{setReason(e.target.value);setRequestKey(crypto.randomUUID());}} /></label>
      {error&&<p role="alert">{error}</p>}<Button type="submit" loading={busy} disabled={!reason.trim()}>Save competency review</Button>
    </form>
  </details>;
}
