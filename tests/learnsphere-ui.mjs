// Isolated Chrome context with synthetic API fixtures. No database or live AI calls.
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
const origin=process.env.STUDIO_UI_ORIGIN || 'http://127.0.0.1:5178';
const version=await (await fetch('http://127.0.0.1:9331/json/version')).json();
const socket=new WebSocket(version.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
let seq=0,session,context;
const pending=new Map(),errors=[];
let role='teacher',aiUnavailable=true;
const topics=[],activities=[],assignments=[];
function send(method,params={},sessionId) {return new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));});}
socket.onmessage=({data})=>{const m=JSON.parse(data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p?.reject(new Error(m.error.message)):p?.resolve(m.result);}else if(m.method==='Fetch.requestPaused')handle(m.params).catch(e=>errors.push(e.message));else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);};
async function handle({requestId,request}) {
  const url=new URL(request.url),path=url.pathname.replace('/api/v1',''),body=request.postData?JSON.parse(request.postData):{};
  let payload=[],status=200;
  const cls={id:'ui-class',name:'Grade 8 A',school_id:'ui-school',subjects:[{id:'science',name:'Science'}]};
  if(request.method==='OPTIONS')payload={};
  else if(path==='/auth/me')payload={id:'ui-'+role,school_id:'ui-school',role,name:'UI '+role,email:role+'@example.test'};
  else if(path==='/learnsphere/scope')payload={classes:[cls],students:[{id:'ui-pupil',name:'Test Student',class_id:cls.id,school_id:cls.school_id}]};
  else if(path==='/learnsphere/summary')payload={students:1,assignments:assignments.length,completed_assignments:0};
  else if(path.endsWith('/support'))payload={student_id:'ui-pupil',findings:[],empty_message:'More practice data needed'};
  else if(path.endsWith('/journey'))payload={student_id:'ui-pupil',participation:assignments.reduce((n,a)=>n+a.attempts.length,0),completed_assignments:0,verified_observations:0,stages:{Adheeti:0,Bodh:0,Abhyas:0,Prayog:0,Prasar:0},timeline:[],trends:[]};
  else if(path.endsWith('/panchapadi'))payload={student_id:'ui-pupil',graphs:['Adheeti','Bodh','Abhyas','Prayog','Prasar'].map(stage=>({stage,points:[]}))};
  else if(path==='/learnsphere/topics') {if(request.method==='POST'){payload={...body,id:'topic-'+topics.length};topics.push(payload);status=201;}else payload=topics;}
  else if(path==='/learnsphere/activities') {if(request.method==='POST'){payload={...body,id:'activity-'+activities.length,version:1};activities.push(payload);status=201;}else payload=activities;}
  else if(/\/activities\/.+\/assignments$/.test(path)) {const a=activities.find(a=>a.id===path.split('/')[3]);const assignment={id:'assignment-'+assignments.length,student_id:'ui-pupil',snapshot:{...a,topic_title:topics.find(t=>t.id===a.topic_id).title,subject_id:'science',class_id:'ui-class'},assigned_at:new Date().toISOString(),due_at:null,intervention_for:null,attempts:[]};assignments.push(assignment);payload={assignment_ids:[assignment.id]};status=201;}
  else if(path==='/learnsphere/assignments')payload=assignments;
  else if(/\/assignments\/.+\/attempts$/.test(path)){const a=assignments.find(a=>a.id===path.split('/')[3]);payload={...body,id:'attempt-'+a.id,assignment_id:a.id,submitted_at:new Date().toISOString(),evaluations:[],completed:false,version:1};a.attempts.push(payload);status=201;}
  else if(/\/attempts\/.+\/evaluate$/.test(path)) {const at=assignments.flatMap(a=>a.attempts).find(at=>at.id===path.split('/')[3]);if(aiUnavailable){status=503;payload={detail:'Your response is saved. Ollama unavailable.'};at.evaluations.push({kind:'ai_failure',date:new Date().toISOString(),error:'Ollama unavailable'});}else{at.evaluations.push({kind:'ai',date:new Date().toISOString(),feedback:{correctly_understood:['Evaporation'],missing_concepts:['Energy transfer'],misconceptions:[],strengths:['Clear wording'],next_step:'Explain energy transfer.'}});payload=at;}}
  else if(/\/attempts\/.+\/review$/.test(path)){const at=assignments.flatMap(a=>a.attempts).find(at=>at.id===path.split('/')[3]);at.version++;at.completed=body.completed;at.evaluations.push({kind:'teacher',date:new Date().toISOString(),feedback:body.feedback,outcome:body.outcome});payload=at;}
  else if(path==='/auth/logout')payload={};
  await send('Fetch.fulfillRequest',{requestId,responseCode:status,responseHeaders:[{name:'Content-Type',value:'application/json'},{name:'Access-Control-Allow-Origin',value:origin},{name:'Access-Control-Allow-Headers',value:'*'},{name:'Access-Control-Allow-Methods',value:'*'}],body:Buffer.from(JSON.stringify(payload)).toString('base64')},session);
}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true},session);if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value;}
async function waitFor(expression){for(let n=0;n<150;n++){if(await evaluate(`!!(${expression})`))return;await new Promise(r=>setTimeout(r,100));}throw new Error('Timed out '+expression);}
const button=text=>`[...document.querySelectorAll('button')].find(e=>e.textContent.trim().startsWith(${JSON.stringify(text)}))`;
const control=text=>`[...document.querySelectorAll('label')].find(e=>e.textContent.trim().startsWith(${JSON.stringify(text)}))?.querySelector('input,textarea,select')`;
async function fill(text,value){await evaluate(`(()=>{const e=${control(text)};const p=e.tagName==='SELECT'?HTMLSelectElement.prototype:e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(p,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event(e.tagName==='SELECT'?'change':'input',{bubbles:true}));})()`);}
async function click(text){await evaluate(`${button(text)}.click()`);}
async function navigate(path){await send('Page.navigate',{url:origin+path},session);await waitFor(`document.querySelector('[aria-label="Student"]')?.value==='ui-pupil'`);}
try {
  context=(await send('Target.createBrowserContext')).browserContextId;
  const {targetId}=await send('Target.createTarget',{url:'about:blank',browserContextId:context});
  session=(await send('Target.attachToTarget',{targetId,flatten:true})).sessionId;
  await send('Page.enable',{},session);await send('Runtime.enable',{},session);
  await send('Fetch.enable',{patterns:[{urlPattern:'*:8000/api/v1/*',requestStage:'Request'}]},session);
  await send('Page.addScriptToEvaluateOnNewDocument',{source:"localStorage.setItem('lumeneios_token','ui-test');"},session);
  await navigate('/learnsphere');
  await waitFor(`document.body.textContent.includes('More practice data needed')`);
  assert.equal(await evaluate(`document.querySelectorAll('nav[aria-label="LearnSphere sections"] a').length`),4);
  await navigate('/learnsphere/journey');await waitFor(`document.body.textContent.includes('More assessed evidence is needed')`);
  console.log('PASS LearnSphere navigation, authorized selectors, honest support and journey empty states');
  await navigate('/learnsphere/teach-back');
  await evaluate(`document.querySelector('main details').open=true`);
  await fill('New topic/chapter','Evaporation');await click('Add topic');await waitFor(`document.body.textContent.includes('Topic saved.')`);
  await fill('Title','Explain evaporation');await fill('Concept and explanation prompt','Explain evaporation in your own words.');await fill('Evaluation rubric','Explain energy and change of state.');await click('Create activity');
  await waitFor(`document.body.textContent.includes('Activity saved.')`);await click('Assign to selected student');await waitFor(`document.body.textContent.includes('Activity assigned.')`);
  assert.equal(assignments.length,1);
  console.log('PASS educator topic creation, teach-back authoring and assignment');
  role='student';await navigate('/learnsphere/teach-back');
  assert.equal(await evaluate(`!!${button('Create activity')}`),false,'student cannot see educator controls');
  await fill('Your explanation or findings','Evaporation is liquid changing to vapour.');await click('Save explanation and evaluate');
  await waitFor(`document.body.textContent.includes('Ollama unavailable')`);
  assert.equal(assignments[0].attempts.length,1,'AI failure retains one response');
  aiUnavailable=false;await click('Evaluate with AI');await waitFor(`document.body.textContent.includes('Explain energy transfer.')`);
  assert.equal(assignments[0].attempts.length,1,'retry does not duplicate attempts');
  console.log('PASS student response persistence, visible AI failure, retry and structured feedback');
  role='teacher';await navigate('/learnsphere/teach-back');
  await waitFor(`document.body.textContent.includes('Review response and record outcome')`);
  await evaluate(`[...document.querySelectorAll('details')].find(e=>e.querySelector('summary')?.textContent.startsWith('Review response')).open=true`);
  await fill('Teacher feedback','Explain the energy source next.');await fill('Learning outcome','Concept explained; follow-up recommended.');await click('Save teacher review');
  await waitFor(`document.body.textContent.includes('Teacher-verified feedback')`);
  assert.equal(assignments[0].attempts[0].completed,true);
  role='parent';await navigate('/learnsphere/teach-back');
  assert.equal(await evaluate(`!!${button('Evaluate with AI')}`),false,'parent has read-only feedback');
  assert.equal(await evaluate(`!!${control('Your explanation or findings')}`),false,'parent cannot submit');
  await navigate('/learnsphere/missions');await waitFor(`document.body.textContent.includes('No activities of this type have been assigned yet.')`);
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true},session);
  assert.equal(await evaluate(`document.documentElement.scrollWidth<=window.innerWidth`),true,'mobile layout fits viewport');
  const shot=await send('Page.captureScreenshot',{format:'png'},session);
  await writeFile('.browser-tests/learnsphere-mobile.png',Buffer.from(shot.data,'base64'));
  console.log('PASS teacher review, parent read-only view, mission empty state and mobile layout');
  assert.deepEqual(errors,[]);
} finally {if(context)await send('Target.disposeBrowserContext',{browserContextId:context});socket.close();}
