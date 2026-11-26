// Chrome UI test using synthetic intercepted API responses; no real student records.
import assert from 'node:assert/strict';
const origin=process.env.STUDIO_UI_ORIGIN||'http://127.0.0.1:5178';
const v=await(await fetch('http://127.0.0.1:9331/json/version')).json();
const ws=new WebSocket(v.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
let sequence=0,session,context,role='teacher',result,submittedBody,reviewBody,historyMode='multiple';
let mappingReviewed=false,failMapping=true,mappingBody,mappingAttempts=0;
const pending=new Map(),errors=[];
const stages=['Adheeti','Bodh','Abhyas','Prayog','Prasar'];
const draftItems=['support','teach_back','mission'].map(kind=>({kind,positions:[0],stage:'Bodh',title:'Number '+kind,explanation:'Q1 needs a clearer explanation.',learning_tip:'Explain how you recognized the number.',scenario:'Sort a small set of objects.',instructions:'Describe your grouping method.',expected_submission:'An explanation in your own words.',objective:'Explain the concept.',rubric:'Assess the explanation without giving the answer.'}));
function stageEvaluation(verified,score,mapping){return {status:verified?'teacher_verified':'complete',attempt_id:'stage-attempt-ui',teacher_verified:verified,review_revision_id:verified?'revision-ui':undefined,mapping:mapping||[{position:0,mappings:[{stage:'Bodh',reasoning:'Recognize the concept of even numbers.',prerequisite_test:false,procedural_practice:false,independent_extension:false}]}],stages:stages.map(stage=>({stage,score_pct:stage==='Bodh'?score:null,earned_marks:stage==='Bodh'?score/50:null,maximum_marks:stage==='Bodh'?2:null,evidence_count:stage==='Bodh'?1:0,status:stage==='Bodh'?(verified?'verified':'provisional'):'Insufficient evidence',explanation:'Actual assessment evidence only; no overall mastery claim.',teacher_verified:verified,contributions:[]}))};}
const q={position:0,id:'q-ui',text:'Choose the even number.',type:'mcq',options:['3','4','5','7'],marks:2,competency:'CU'};
result={id:'ui-result',assessment_id:'ui-assessment',assessment_title:'Assigned number assessment',student_id:'ui-pupil',school_id:'ui-school',class_id:'ui-class',subject_id:'math',submission_id:'ui-submission',version:1,status:'automatically_evaluated_unverified',answers:[{position:0,selected_option_index:1}],automatic_outcomes:[{position:0,competency:'CU',score:2,maximum:2,correct:true,provenance:'automatic_key_unverified'}],reviews:[],marks_obtained:2,total_marks:2,panchapadi:stageEvaluation(false,100)};
result.outcomes=result.automatic_outcomes;

const profile={id:'ui-pupil',school_id:'ui-school',class_id:'ui-class',class_name:'Test class',name:'Synthetic Student',roll_no:1,gender:'Other',attendance_pct:90,competencies:{LU:70,CU:70,AU:70,CT:70,overall:70},baseline_competencies:{LU:60,CU:60,AU:60,CT:60,overall:60},learning_modality:'Visual',homework_completion_rate:0,needs_support:false,subject_names:['Mathematics'],parent_names:[]};
function send(method,params={},sessionId){return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));});}
ws.onmessage=({data})=>{const m=JSON.parse(data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p?.reject(new Error(m.error.message)):p?.resolve(m.result);}else if(m.method==='Fetch.requestPaused')mock(m.params).catch(e=>errors.push(e.message));else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);};
async function mock({requestId,request}){
  const path=new URL(request.url).pathname.replace('/api/v1','');const body=request.postData?JSON.parse(request.postData):{};let payload=[],status=200;
  const publicResult=()=>({...result,learning_drafts:role==='teacher'?draftItems:[],questions:[role==='teacher'?{...q,correct_answer:'4',marking_rubric:'Credit the even number.'}:q]});
  if(request.method==='OPTIONS')payload={};
  else if(path==='/auth/me')payload={id:'ui-'+role,name:'Synthetic '+role,email:role+'@example.test',role,school_id:'ui-school'};
  else if(path==='/classes/students/me')payload=profile;
  else if(path==='/assessments/upload-assignments')payload=[{id:'ui-assessment',title:'Assigned number assessment',date:'2026-11-12',class_name:'Test class',subject_name:'Mathematics',total_marks:2,uploaded:false,questions:[q]}];
  else if(path==='/assessments/my-results')payload=result?[publicResult()]:[];
  else if(path==='/assessments/targets')payload=[{id:'ui-class',name:'Test class',subjects:[{id:'math',name:'Mathematics'}]}];
  else if(path==='/assessments/ui-assessment/answers'){
    submittedBody=body;result={id:'ui-result',assessment_id:'ui-assessment',assessment_title:'Assigned number assessment',student_id:'ui-pupil',school_id:'ui-school',class_id:'ui-class',subject_id:'math',submission_id:'ui-submission',version:1,status:'automatically_evaluated_unverified',answers:body.answers,automatic_outcomes:[{position:0,competency:'CU',score:2,maximum:2,correct:true,provenance:'automatic_key_unverified'}],reviews:[],marks_obtained:2,total_marks:2};result.outcomes=result.automatic_outcomes;payload=publicResult();
  }else if(path==='/assessments/results-for-review')payload=result?[publicResult()]:[];
  else if(path==='/assessments/results/ui-result')payload=publicResult();
  else if(path==='/learnsphere/students/ui-pupil/assessments/ui-assessment/competencies'){
    mappingAttempts++;mappingBody=body;
    if(failMapping){status=409;payload={detail:'Analysis changed; reload before confirming.'};}
    else{mappingReviewed=true;payload={};}
  }
  else if(path==='/assessments/results/ui-result/review'){
    reviewBody=body;result.version++;result.status='teacher_reviewed';result.marks_obtained=body.questions.reduce((n,q)=>n+q.score,0);result.outcomes=body.questions.map(r=>({...r,competency:'CU',maximum:2,provenance:'teacher_reviewed'}));result.reviews.push({revision_id:'revision-ui',reviewer_id:'ui-teacher',date:new Date().toISOString(),feedback:body.feedback,outcomes:result.outcomes});payload=publicResult();
    if(body.confirm_panchapadi)result.reviews.at(-1).panchapadi=stageEvaluation(true,100*result.marks_obtained/result.total_marks,body.panchapadi_mappings);
  }else if(path==='/learnsphere/scope')payload={schools:[{id:'ui-school',name:'Test school'}],classes:[{id:'ui-class',name:'Test class',school_id:'ui-school',subjects:[{id:'math',name:'Mathematics'}]}],students:[{id:'ui-pupil',name:'Synthetic Student',class_id:'ui-class',school_id:'ui-school'}]};
  else if(path==='/learnsphere/summary')payload={students:1,assignments:0,completed_assignments:0};
  else if(path==='/learnsphere/students/ui-pupil/assessments')payload=[{assessment_id:'ui-assessment-2',result_id:'ui-result-2',name:'Different fractions assessment',subject:'Mathematics',date:'2026-11-10'},{assessment_id:'ui-assessment',result_id:'ui-result',name:'Assigned number assessment',subject:'Mathematics',date:'2026-11-12'}];
  else if(path.endsWith('/guidance')){
    const other=path.includes('/ui-assessment-2/');const id=other?'ui-assessment-2':'ui-assessment';
    payload={assessment_id:id,result_id:other?'ui-result-2':'ui-result',student_id:'ui-pupil',name:other?'Different fractions assessment':'Assigned number assessment',subject:'Mathematics',date:'2026-11-12',evaluation_status:other?'provisional':'teacher_reviewed',guidance_status:'provisional',warnings:[],
      questions:[{position:0,text:other?'Explain a different fraction relationship.':q.text,answer:other?'Different actual fraction answer.':'4',score:1,maximum:2,status:'Partially correct',competency:'CU',stages:['Bodh'],correct_answer:null,feedback:'Topic unmapped',guidance:{expected_concept:other?'A fraction relationship.':'Even numbers form equal pairs.',misunderstanding:'The explanation needs a reason.',explanation:other?'Compare the actual numerator and denominator.':'Explain why the objects form equal pairs.',activity:'Group actual objects and explain each step.',practice_question:'How would you justify a new example?',status:'provisional'}}],
      performance:{result_id:other?'ui-result-2':'ui-result',assessment_id:id,assessment_name:other?'Different fractions assessment':'Assigned number assessment',subject_id:'math',assessed_at:'2026-11-12T10:00:00Z',evaluation:stageEvaluation(!other,other?25:50)}};
  }
  else if(path.endsWith('/panchapadi'))payload={student_id:'ui-pupil',graphs:stages.map(stage=>({stage,points:['2026-11-10T10:00:00Z','2026-11-11T10:00:00Z','2026-11-12T10:00:00Z'].map((date,i)=>({result_id:'history-'+i,assessment_id:'assessment-'+i,assessment_name:i===2?'Assigned number assessment':'Historical assessment '+i,subject_id:'math',assessed_at:date,score_pct:stage==='Bodh'&&i!==1?(i===0?100:50):null,earned_marks:stage==='Bodh'&&i!==1?1:null,maximum_marks:stage==='Bodh'&&i!==1?2:null,evidence_count:stage==='Bodh'&&i!==1?1:0,status:stage==='Bodh'&&i!==1?'verified':'Insufficient evidence',explanation:'Only reviewed assessment scores; gaps are not zero.',review_revision_id:'revision-ui'}))}))};
  else if(path.endsWith('/journey'))payload={student_id:'ui-pupil',participation:0,completed_assignments:0,verified_observations:0,stages:Object.fromEntries(stages.map(s=>[s,0])),timeline:[],trends:[],assessment_observations:[],panchapadi_assessments:[{result_id:'ui-result',assessment_id:'ui-assessment',assessment_name:'Assigned number assessment',subject_id:'math',assessed_at:'2026-11-12T10:00:00Z',evaluation:stageEvaluation(true,50)}]};
  else if(path.endsWith('/support'))payload={student_id:'ui-pupil',findings:[],empty_message:'More practice data needed',assessment_findings:[{subject_id:'math',topic_id:null,topic:null,competency:'CU',observations:1,assessments:1,score_pct:50,status:'Teacher-reviewed assessment evidence',reason:'Assessment questions are not activities.',suggestion:'Review partially credited answers.',sources:[{id:'obs-ui',assessment_title:'Assigned number assessment',score:1,maximum:2,correct:false,provenance:'teacher_reviewed'}]}]};
  if(request.method!=='OPTIONS'&&path.endsWith('/guidance')){
    payload.automation_version=mappingReviewed?1:0;
    payload.evaluation_status=result.reviews.length?'teacher_reviewed':'provisional';
    const item=payload.questions[0];item.competency=mappingReviewed?'AU':'Unmapped';
    item.competency_mapping={position:0,label:mappingReviewed?'AU':null,suggested_label:'CU',confidence:mappingReviewed?null:0.35,reason:mappingReviewed?'Teacher applied the learning objective.':'The wording is ambiguous and needs teacher review.',status:mappingReviewed?'teacher_confirmed':'requires_review'};
    item.score=result.outcomes[0].score;item.status=item.score===2?'Correct':'Partially correct';
    item.guidance.misunderstanding=item.score===2?null:'A supported response gap.';
    payload.performance.evaluation=result.reviews.at(-1)?.panchapadi||result.panchapadi;
    payload.concept_stages=[{stage:'Bodh',demonstrated:[],partial:[{position:0,concept:'Even numbers form equal pairs.'}],missing:[]}];
  }
  if(request.method!=='OPTIONS'&&path.endsWith('/panchapadi')&&historyMode==='single')payload.graphs.forEach(g=>{g.points=g.points.slice(-1);});
  await send('Fetch.fulfillRequest',{requestId,responseCode:status,responseHeaders:[{name:'Content-Type',value:'application/json'},{name:'Access-Control-Allow-Origin',value:origin},{name:'Access-Control-Allow-Headers',value:'*'},{name:'Access-Control-Allow-Methods',value:'*'}],body:Buffer.from(JSON.stringify(payload)).toString('base64')},session);
}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true},session);if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value;}
async function waitFor(expression){for(let i=0;i<150;i++){if(await evaluate(`document.body && !!(${expression})`))return;await new Promise(r=>setTimeout(r,100));}throw new Error('Timed out '+expression+' '+JSON.stringify(await evaluate(`({url:location.href,text:document.body?.textContent.slice(-1600)})`)));}
const button=t=>`[...document.querySelectorAll('button')].find(e=>e.textContent.trim().startsWith(${JSON.stringify(t)}))`;
async function fill(label,value){await evaluate(`(()=>{const e=[...document.querySelectorAll('label')].find(x=>x.textContent.startsWith(${JSON.stringify(label)})).querySelector('input,textarea,select');const p=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:e.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(p,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event(e.tagName==='SELECT'?'change':'input',{bubbles:true}));})()`);}

try{
  context=(await send('Target.createBrowserContext')).browserContextId;
  const {targetId}=await send('Target.createTarget',{url:'about:blank',browserContextId:context});
  session=(await send('Target.attachToTarget',{targetId,flatten:true})).sessionId;
  await send('Page.enable',{},session);await send('Runtime.enable',{},session);
  await send('Fetch.enable',{patterns:[{urlPattern:'*:8000/api/v1/*',requestStage:'Request'}]},session);
  await send('Page.addScriptToEvaluateOnNewDocument',{source:"localStorage.setItem('lumeneios_token','isolated-ui-test');"},session);
  await send('Page.navigate',{url:origin+'/learnsphere/support'},session);
  await waitFor("document.body.textContent.includes('The wording is ambiguous')");
  assert.equal(await evaluate("document.body.textContent.includes('Primary competency: Unmapped')"),true);
  assert.equal(await evaluate("document.body.textContent.includes('Optional enrichment')"),true);
  await evaluate("[...document.querySelectorAll('details')].find(d=>d.querySelector('summary')?.textContent==='Review primary competency').open=true");
  await fill('Primary competency','AU');
  await fill('Mapping reason','The learner applies a supplied rule to this problem.');
  await evaluate(button('Save competency review')+'.click()');
  await waitFor("document.body.textContent.includes('Analysis changed; reload before confirming.')");
  assert.equal(mappingReviewed,false);
  failMapping=false;
  await evaluate(button('Save competency review')+'.click()');
  await waitFor("document.body.textContent.includes('Primary competency: AU')");
  assert.equal(mappingAttempts,2);
  assert.equal(mappingBody.expected_version,0);
  assert.equal(mappingBody.questions[0].label,'AU');
  assert.equal(mappingBody.confirm_panchapadi,undefined);
  console.log('PASS uncertain mapping, explicit teacher confirmation, error feedback and separate taxonomy');
  await evaluate(button('Review and confirm assessment')+'.click()');
  await waitFor("document.body.textContent.includes('Confirm reviewed marks')");
  await fill('Q1 reviewed marks','1');
  await fill('Q1 feedback','Partial credit for the demonstrated part.');
  await fill('Overall teacher feedback','Reviewed the saved response and rubric.');
  await evaluate("[...document.querySelectorAll('label')].find(e=>e.textContent.startsWith('Confirm the displayed stage mappings')).querySelector('input').click()");
  await evaluate(button('Confirm reviewed marks')+'.click()');
  await waitFor("document.body.textContent.includes('Question marks are teacher-reviewed')");
  assert.equal(reviewBody.expected_version,1);
  assert.equal(reviewBody.questions[0].score,1);
  assert.equal(reviewBody.confirm_panchapadi,true);
  assert.equal(reviewBody.panchapadi_mappings[0].mappings[0].stage,'Bodh');
  await waitFor("document.body.textContent.includes('50%')");
  assert.equal(await evaluate("location.pathname"),'/learnsphere/support');
  assert.equal(await evaluate("document.querySelectorAll('nav[aria-label=\"LearnSphere sections\"] a').length"),4);
  console.log('PASS LearnSphere-scoped marks review, confirmed metrics and existing navigation');
  role='parent';
  await send('Page.navigate',{url:origin+'/learnsphere/support'},session);
  await waitFor("document.body.textContent.includes('Question marks are teacher-reviewed')");
  assert.equal(await evaluate('('+button('Review and confirm assessment')+')===undefined'),true);
  assert.equal(await evaluate("document.body.textContent.includes('Review primary competency')"),false);
  console.log('PASS parent read-only controls and persisted review display');
  assert.deepEqual(errors,[]);
}finally{if(context)await send('Target.disposeBrowserContext',{browserContextId:context});ws.close();}
