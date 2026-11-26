import React, { createContext, useContext, useEffect, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { learnsphere } from '../../lib/learnsphere';
import type { Scope } from '../../types/learnsphere';
import { StudentScopeSelector } from '../../components/learnsphere/StudentScopeSelector';
type LearningContext = { scope: Scope; classId: string; studentId: string; educator: boolean; student: boolean };
const Context = createContext<LearningContext | null>(null);
export const useLearning = () => useContext(Context)!;
function Content() {
  const { currentUser } = useAuth();
  const [scope, setScope] = useState<Scope>();
  const [error, setError] = useState('');
  const [classId, setClassId] = useState('');
  const [studentId, setStudentId] = useState('');
  const [summary, setSummary] = useState<{students: number; assignments: number; completed_assignments: number}>();
  const educator = ['admin', 'principal', 'teacher', 'developer'].includes(currentUser?.role || '');
  useEffect(() => {
    let active = true;
    learnsphere.scope().then(value => {
      if (!active) return;
      setScope(value); setClassId(value.classes[0]?.id || '');
      setStudentId(value.students.find(s => s.class_id === value.classes[0]?.id)?.id || '');
    }).catch(e => active && setError(e.message));
    if (educator) learnsphere.summary().then(v => active && setSummary(v)).catch(e => active && setError(e.message));
    return () => {active = false;};
  }, []);
  return <div className="space-y-5">
    <div><h1 className="text-2xl font-bold text-navy-900">LearnSphere</h1><p className="text-content-secondary">Learning evidence, constructive support and practical exploration.</p></div>
    <nav aria-label="LearnSphere sections" className="flex flex-wrap gap-2">{[['support', 'Learning Support'], ['journey', 'Learning Journey'], ['teach-back', 'Teach-Back Challenge'], ['missions', 'Real-Life Missions']].map(([path, label]) => <NavLink key={path} to={`/learnsphere/${path}`} className={({isActive}) => `px-4 py-2 rounded-xl border ${isActive ? 'bg-navy-900 text-white' : 'bg-white'}`}>{label}</NavLink>)}</nav>
    {error && <p role="alert" className="text-rose-700">{error}</p>}
    {!scope && !error && <p role="status">Loading authorized learning records…</p>}
    {summary && <p className="text-sm">Authorized scope: {summary.students} students · {summary.assignments} activities assigned · {summary.completed_assignments} completed. Completion is separate from demonstrated understanding.</p>}
    {scope && <><StudentScopeSelector scope={scope} classId={classId} studentId={studentId} onClass={id => {setClassId(id); setStudentId(scope.students.find(s => s.class_id === id)?.id || '');}} onStudent={setStudentId} />
      {!scope.classes.length && <p>No authorized class or linked student is available. Teachers require a class-teacher assignment; student accounts require an explicit profile link.</p>}
      <Context.Provider value={{scope, classId, studentId, educator, student: currentUser?.role === 'student'}}>
        <div key={`${classId}:${studentId}`}><Outlet /></div>
      </Context.Provider></>}
  </div>;
}
export function LearnSphereLayout() {
  const { currentUser } = useAuth();
  // Remount discards all records and in-flight UI state across account or school changes.
  return <Content key={`${currentUser?.id}:${currentUser?.schoolId}:${currentUser?.role}`} />;
}
