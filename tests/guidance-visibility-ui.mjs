// Isolated role rendering checks. API requests are intercepted; no real records.
import assert from 'node:assert/strict';
const origin=process.env.STUDIO_UI_ORIGIN||'http://127.0.0.1:5178';
const tip='Create a simple experiment where students can observe the attraction of various materials to a magnet. Materials such as iron, steel, and aluminum can be used. Discuss the results and relate them to the concept of magnetic materials.';
const question='Which of the following materials is most likely to be a magnetic material? A) Wood, B) Iron, C) Plastic, D) Copper. Explain your choice.';
const version=await(await fetch('http://127.0.0.1:9331/json/version')).json();
const ws=new WebSocket(version.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
let sequence=0,session,context,role='teacher',legacyPayload=false;const pending=new Map(),errors=[];
function send(method,params={},sessionId){return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));});}
ws.onmessage=({data})=>{const m=JSON.parse(data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p?.reject(new Error(m.error.message)):p?.resolve(m.result);}else if(m.method==='Fetch.requestPaused')mock(m.params).catch(e=>errors.push(e.message));else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);};
async function mock({requestId,request}){
  const path=new URL(request.url).pathname.replace('/api/v1','');let payload=[];
  if(request.method==='OPTIONS')payload={};
  else if(path==='/auth/me')payload={id:'ui-'+role,name:'Synthetic '+role,email:role+'@example.test',role,school_id:'ui-school'};
  else if(path==='/learnsphere/scope')payload={schools:[{id:'ui-school',name:'Test school'}],classes:[{id:'ui-class',name:'Test class',school_id:'ui-school',subjects:[{id:'science',name:'Science'}]}],students:[{id:'ui-pupil',name:'Synthetic learner',class_id:'ui-class',school_id:'ui-school'}]};
  else if(path==='/learnsphere/summary')payload={students:1,assignments:0,completed_assignments:0};
  else if(path.endsWith('/assessments'))payload=[{assessment_id:'science-paper',result_id:'science-result',name:'Saved Science assessment',subject:'Science',date:'2026-11-13'}];
  else if(path.endsWith('/support'))payload={student_id:'ui-pupil',findings:[],assessment_findings:[]};
  else if(path.endsWith('/guidance'))payload={assessment_id:'science-paper',result_id:'science-result',student_id:'ui-pupil',name:'Saved Science assessment',subject:'Science',date:'2026-11-13',evaluation_status:'teacher_reviewed',guidance_status:'provisional',warnings:[],
    questions:[{position:0,text:'Explain magnetic materials.',answer:'An actual saved explanation.',score:2,maximum:2,status:'Correct',competency:'LU',stages:['Adheeti'],correct_answer:null,feedback:null,guidance:{expected_concept:'Magnetic materials.',misunderstanding:null,explanation:'Unchanged existing improvement explanation.',activity:legacyPayload||['teacher','principal'].includes(role)?tip:null,practice_question:question,status:'provisional',activity_for_student:true,practice_for_student:true}}],
    performance:{result_id:'science-result',assessment_id:'science-paper',assessment_name:'Saved Science assessment',subject_id:'science',assessed_at:'2026-11-13T10:00:00Z',evaluation:{status:'teacher_verified',teacher_verified:true,mapping:[],stages:['Adheeti','Bodh','Abhyas','Prayog','Prasar'].map(stage=>({stage,score_pct:null,earned_marks:null,maximum_marks:null,evidence_count:0,status:'Insufficient evidence',explanation:'Actual evidence only.',teacher_verified:true,contributions:[]}))}}};
  await send('Fetch.fulfillRequest',{requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'application/json'},{name:'Access-Control-Allow-Origin',value:origin},{name:'Access-Control-Allow-Headers',value:'*'},{name:'Access-Control-Allow-Methods',value:'*'}],body:Buffer.from(JSON.stringify(payload)).toString('base64')},session);
}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true},session);if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value;}
async function waitFor(expression){for(let i=0;i<150;i++){if(await evaluate(`document.body&&!!(${expression})`))return;await new Promise(r=>setTimeout(r,100));}throw new Error('Timed out '+expression);}
try{
  context=(await send('Target.createBrowserContext')).browserContextId;
  const {targetId}=await send('Target.createTarget',{url:'about:blank',browserContextId:context});
  session=(await send('Target.attachToTarget',{targetId,flatten:true})).sessionId;
  await send('Page.enable',{},session);await send('Runtime.enable',{},session);
  await send('Fetch.enable',{patterns:[{urlPattern:'*:8000/api/v1/*',requestStage:'Request'}]},session);
  await send('Page.addScriptToEvaluateOnNewDocument',{source:"if(location.protocol==='http:'||location.protocol==='https:'){localStorage.setItem('lumeneios_token','isolated-ui-test');}"},session);
  for(role of ['teacher','principal','parent','student']){
    await send('Page.navigate',{url:origin+'/learnsphere/support'},session);
    await waitFor(`document.body.textContent.includes(${JSON.stringify('Practice question: '+question)})`);
    const body=await evaluate('document.body.textContent');
    assert.equal(body.split('Practice question: '+question).length-1,1);
    assert.equal(body.includes('Unchanged existing improvement explanation.'),true);
    if(['teacher','principal'].includes(role)){
      assert.equal(body.split('Try this: '+tip).length-1,1);
      assert.equal(body.includes('Student activity — intended for the student to perform'),true);
      assert.equal(body.includes('Practice question for the student'),true);
    }else{
      assert.equal(body.includes(tip),false);
      assert.equal(body.includes('Student activity — intended for the student to perform'),false);
      assert.equal(body.includes(role==='parent'?'Help your child practise with this question':'Your practice question'),true);
    }
    console.log('PASS '+role+' Learning Support: correct visibility, audience labels, unchanged wording and no duplicate items');
    // Ensure the next role cannot accidentally inspect the previous page DOM.
    await send('Page.navigate',{url:'about:blank'},session);await waitFor('location.href==="about:blank"');
  }
  role='student';legacyPayload=true;
  await send('Page.navigate',{url:origin+'/learnsphere/support'},session);
  await waitFor(`document.body.textContent.includes('Your practice question')`);
  assert.equal(await evaluate(`document.body.textContent.includes(${JSON.stringify(tip)})`),false);
  console.log('PASS student view also hides the teacher-only activity if an older response includes it');
  assert.deepEqual(errors,[]);
}finally{if(context)await send('Target.disposeBrowserContext',{browserContextId:context});ws.close();}
