import React from 'react';
import { it,expect } from 'vitest';
import { render,screen,fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import { DataProvider } from '../context/DataContext';
import { initialUsers } from '../data/seedData';
import { App } from '../App';
function open(path:string,role:string){localStorage.setItem('lumeneios_auth_user',JSON.stringify(initialUsers.find(u=>u.role===role)));return render(<MemoryRouter initialEntries={[path]}><AuthProvider><DataProvider><App/></DataProvider></AuthProvider></MemoryRouter>);}
it('runs configuration → sample schedule → teacher homework → principal recovery approval across reloads',async()=>{
 let view=open('/principal/academic-config','principal');
 fireEvent.click(screen.getByRole('button',{name:'Save Academic Configuration'}));
 expect(JSON.parse(localStorage.getItem('lumeneios_academicWorkflow')!).config.year).toBe('2026-2027');view.unmount();
 view=open('/teacher/time-aware','teacher');
 fireEvent.click(screen.getByRole('button',{name:'Use sample research dataset'}));
 const generate=await screen.findByRole('button',{name:'Generate and approve new teaching schedule'});expect(generate).not.toBeDisabled();fireEvent.click(generate);
 expect(screen.getByRole('heading',{name:/Class 6 · Mathematics · Daily Curriculum/})).toBeInTheDocument();view.unmount();
 view=open('/teacher/curriculum-180','teacher');
 fireEvent.click(screen.getAllByRole('button',{name:'Not completed — moved to homework'})[0]);
 expect(screen.getByText('Incomplete — homework assigned')).toBeInTheDocument();expect(screen.getByText('Recovery Proposal — pending approval')).toBeInTheDocument();
 let state=JSON.parse(localStorage.getItem('lumeneios_academicWorkflow')!);const original=state.plans[0].original;expect(state.plans[0].approved).toEqual(original);view.unmount();
 view=open('/principal/curriculum','principal');fireEvent.click(screen.getByRole('button',{name:'Approve recovery schedule'}));
 state=JSON.parse(localStorage.getItem('lumeneios_academicWorkflow')!);expect(state.plans[0].versions).toHaveLength(1);expect(state.plans[0].original).toEqual(original);expect(state.plans[0].approved).not.toEqual(original);expect(state.plans[0].execution[0].status).toBe('homework');view.unmount();
 view=open('/teacher/curriculum-180','teacher');expect(screen.getByText('Incomplete — homework assigned')).toBeInTheDocument();expect(screen.queryByText('Recovery Proposal — pending approval')).toBeNull();
});
