import React from 'react';
import { describe,it,expect } from 'vitest';
import { render,screen,fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { allocate,defaultConfig,teachingDates,validateConfig,recovery,Plan } from '../lib/academicWorkflow';
import { DataProvider } from '../context/DataContext';
import { AuthProvider } from '../context/AuthContext';
import { initialUsers } from '../data/seedData';
import { PlanSchedule } from '../pages/time-aware/PlanSchedule';
import { loadSampleTopics } from '../lib/planningSyllabus';
const config={...defaultConfig,start:'2026-04-01',end:'2027-03-31',days:3,horizon:3,holidays:'2026-04-02'};
const rows=allocate([{id:'a',topic:'Topic A',minutes:40},{id:'b',topic:'Topic B',minutes:40},{id:'c',topic:'Topic C',minutes:40}],config);
function plan():Plan{return {id:'p',grade:6,subject:'Mathematics',source:'SAMPLE DATA',config,original:rows,approved:rows,execution:[],versions:[],proposal:null};}
function show(p:Plan,role:'teacher'|'principal'){
 localStorage.setItem('lumeneios_auth_user',JSON.stringify(initialUsers.find(u=>u.role===role)));
 localStorage.setItem('lumeneios_academicWorkflow',JSON.stringify({config,plans:[p]}));
 return render(<MemoryRouter><AuthProvider><DataProvider><PlanSchedule plan={p} executionEnabled/></DataProvider></AuthProvider></MemoryRouter>);
}
const saved=()=>JSON.parse(localStorage.getItem('lumeneios_academicWorkflow')!).plans[0] as Plan;
describe('academic workflow calendar and recovery safety',()=>{
 it('excludes holidays and weekends and validates calendar capacity',()=>{expect(teachingDates(config)).toEqual(['2026-04-01','2026-04-03','2026-04-06']);expect(validateConfig(config)).toBeNull();expect(validateConfig({...config,days:365})).toBeTruthy();expect(validateConfig({...config,minutes:0})).toBeTruthy();});
 it('retains every topic during a time shortfall',()=>{const result=allocate(rows,{...config,days:1,horizon:1});expect(result).toHaveLength(3);expect(result.filter(l=>!l.date)).toHaveLength(2);});
 it('keeps homework incomplete and shifts future work without mutating the schedule',()=>{const p=plan();p.execution=[{lessonId:'a',status:'homework',at:'2026-04-01',note:''}];const proposed=recovery(p);expect(proposed[0].date).toBe('2026-04-03');expect(proposed[2].date).toBeNull();expect(p.original).toEqual(rows);expect(p.approved).toEqual(rows);});
 it('records execution persistently while preserving original and approved rows',()=>{show(plan(),'teacher');fireEvent.click(screen.getAllByRole('button',{name:'Not completed — moved to homework'})[0]);const p=saved();expect(p.execution[0].status).toBe('homework');expect(p.original).toEqual(rows);expect(p.approved).toEqual(rows);expect(p.proposal?.rows[0].date).toBe('2026-04-03');expect(screen.queryByRole('button',{name:'Approve recovery schedule'})).toBeNull();});
 it('approval saves the previous schedule and retains original dates',()=>{const p=plan();p.execution=[{lessonId:'a',status:'deferred',at:'2026-04-01',note:''}];p.proposal={base:0,rows:recovery(p)};show(p,'principal');fireEvent.click(screen.getByRole('button',{name:'Approve recovery schedule'}));const next=saved();expect(next.original).toEqual(rows);expect(next.versions).toEqual([rows]);expect(next.approved[0].date).toBe('2026-04-03');expect(next.proposal).toBeNull();});
 it.each([6,7,8])('uses existing sample topics for both subjects in class %s',async grade=>{for(const subject of ['Mathematics','Science']){const data=await loadSampleTopics(grade,subject);expect(data.source).toContain('SAMPLE DATA');expect(data.topics.length).toBeGreaterThan(0);}});
});
