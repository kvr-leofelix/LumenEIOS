import { useState } from 'react';
export interface AcademicConfigData { year: string; start: string; end: string; days: number; horizon: number; periods: number; minutes: number; holidays: string; weekdays: number[] }
export const defaultConfig: AcademicConfigData = { year: '2026-2027', start: '2026-04-01', end: '2027-03-31', days: 180, horizon: 180, periods: 1, minutes: 40, holidays: '', weekdays: [1,2,3,4,5] };
export function teachingDates(c: AcademicConfigData): string[] {
 const dates: string[] = []; const excluded = new Set(c.holidays.split(/[\s,]+/));
 for(let d = new Date(c.start+'T00:00:00Z'); d.toISOString().slice(0,10)<=c.end && dates.length<Math.min(c.days,c.horizon); d.setUTCDate(d.getUTCDate()+1)) {
 const s=d.toISOString().slice(0,10); if(c.weekdays.includes(d.getUTCDay())&&!excluded.has(s)) dates.push(s);
 } return dates;
}
export function validateConfig(c: AcademicConfigData): string | null {
 if(!/^\d{4}-\d{4}$/.test(c.year)||Number(c.year.slice(5))!==Number(c.year.slice(0,4))+1) return 'Use consecutive academic years, e.g. 2026-2027.';
 if(!c.start||!c.end||c.start>c.end||!c.start.startsWith(c.year.slice(0,4))||!c.end.startsWith(c.year.slice(5))) return 'Calendar dates must fit the academic year.';
 if(![c.days,c.horizon,c.periods,c.minutes].every(Number.isInteger)||c.days<1||c.days>366||c.horizon<1||c.horizon>c.days||c.periods<1||c.periods>12||c.minutes<10||c.minutes>180||!c.weekdays.length) return 'Check days, horizon, periods (1–12), duration (10–180), and teaching weekdays.';
 if(c.holidays.split(/[\s,]+/).filter(Boolean).some(s=>!/^\d{4}-\d{2}-\d{2}$/.test(s)||isNaN(Date.parse(s))||new Date(s).toISOString().slice(0,10)!==s||s<c.start||s>c.end)) return 'Non-teaching dates must be valid dates within the calendar.';
 if(teachingDates({...c,horizon:c.days}).length<c.days) return 'The calendar has fewer teaching dates than the actual instructional days.';
 return null;
}
export interface Lesson { id: string; topic: string; minutes: number; date: string | null; period: number | null }
export interface Execution { lessonId: string; status: 'completed'|'homework'|'deferred'; at: string; note: string }
export interface Plan { id: string; grade: number; subject: string; source: string; config: AcademicConfigData; original: Lesson[]; approved: Lesson[]; versions: Lesson[][]; execution: Execution[]; proposal: { base: number; rows: Lesson[] } | null }
export interface Workflow { config: AcademicConfigData; plans: Plan[] }
export function allocate(items: Pick<Lesson,'id'|'topic'|'minutes'>[], c: AcademicConfigData, offset=0): Lesson[] {
 const dates=teachingDates(c); let slot=offset;
 return items.map(item=>{ const start=slot; slot+=Math.ceil(item.minutes/c.minutes); const fits=slot<=dates.length*c.periods; return {...item,date:fits?dates[Math.floor(start/c.periods)]:null,period:fits?start%c.periods+1:null}; });
}
export function recovery(p: Plan): Lesson[] {
 const incomplete=p.approved.filter(l=>p.execution.find(e=>e.lessonId===l.id)?.status!=='completed');
 const recorded=p.approved.filter(l=>p.execution.some(e=>e.lessonId===l.id)&&l.date);
 const dates=teachingDates(p.config);
 const last=Math.max(-1,...recorded.map(l=>Math.floor((dates.indexOf(l.date!)*p.config.periods+(l.period||1)-1+Math.ceil(l.minutes/p.config.minutes)-1)/p.config.periods)));
 const rows=allocate(incomplete,p.config,(last+1)*p.config.periods);
 return p.approved.map(l=>rows.find(r=>r.id===l.id)??l);
}
export function useAcademicWorkflow() {
 const [workflow,setState]=useState<Workflow>(()=>{try { return JSON.parse(localStorage.getItem('lumeneios_academicWorkflow')||'null')??{config:defaultConfig,plans:[]}; }catch{return {config:defaultConfig,plans:[]};}});
 const [storageError,setStorageError]=useState('');
 const setWorkflow=(update: (w:Workflow)=>Workflow)=>{ const next=update(workflow); try{localStorage.setItem('lumeneios_academicWorkflow',JSON.stringify(next));setStorageError('');setState(next);}catch{setStorageError('Saving failed. Browser storage is unavailable or full; changes were not saved.');} };
 return {workflow,setWorkflow,storageError};
}
