import React, { useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { apiClient } from '../../lib/apiClient';
import { Button } from '../../components/common/Button';
import { Messages, errorText, inputClass, labelClass } from './ui';
import { TeacherWorkspace } from './TeacherWorkspace';
import { StudentWorkspace } from './StudentWorkspace';
import { ParentWorkspace } from './ParentWorkspace';

const EDUCATOR_ROLES = ['admin', 'principal', 'teacher'];

/**
 * Standalone homework shell (login + workspace). Kept for focused e2e/manual tests.
 * The main host app embeds Teacher/Student/ParentWorkspace via DifferentiatedHomeworkPage.
 */
export const LiveApp: React.FC = () => {
  const { currentUser, isLoading, logout, currentSchoolId } = useAuth();
  if (isLoading) return <p className="p-6">Checking session...</p>;
  if (!currentUser) return <Login />;
  return <div className="min-h-screen bg-surface-bg">
    <header className="border-b border-surface-border bg-white">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-5 py-3">
        <div><h1 className="text-lg font-bold text-navy-800">LumenEIOS <span className="font-medium text-teal-600">Differentiated Homework</span></h1>
          <p className="text-xs text-content-secondary">{currentUser.name} - {currentUser.role} - school {currentSchoolId}</p></div>
        <div className="flex flex-wrap items-center gap-2">
          {EDUCATOR_ROLES.includes(currentUser.role) && <SchoolSwitcher />}
          <Button variant="outline" size="sm" onClick={logout}>Sign out</Button>
        </div>
      </div>
    </header>
    <main className="mx-auto max-w-7xl px-5 py-6">
      <Workspace key={currentUser.id + ':' + currentSchoolId} role={currentUser.role} />
    </main>
  </div>;
};

function Login() {
  const { loginWithPassword } = useAuth();
  const [email, setEmail] = useState(''); const [password, setPassword] = useState('');
  const [error, setError] = useState(''); const [pending, setPending] = useState(false);
  return <main className="flex min-h-screen items-center justify-center bg-surface-bg p-6">
    <form className="w-full max-w-sm space-y-4 rounded-xl border border-surface-border bg-white p-6 shadow-card"
      onSubmit={async e => { e.preventDefault(); setError(''); setPending(true);
        try { await loginWithPassword(email, password); setPassword(''); } catch (ex) { setError(errorText(ex)); }
        finally { setPending(false); } }}>
      <div><h1 className="text-xl font-bold text-navy-800">Sign in to LumenEIOS</h1>
        <p className="text-sm text-content-secondary">Differentiated Homework</p></div>
      <label className="block"><span className={labelClass}>Email</span>
        <input aria-label="Email" className={inputClass} type="email" required autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} /></label>
      <label className="block"><span className={labelClass}>Password</span>
        <input aria-label="Password" className={inputClass} type="password" required autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} /></label>
      <Button className="w-full" variant="primary" disabled={pending}>Sign in</Button>
      <Messages error={error} />
    </form>
  </main>;
}

function SchoolSwitcher() {
  const { currentSchoolId, switchSchool } = useAuth();
  const [schools, setSchools] = useState<string[]>([]);
  const [error, setError] = useState(''); const [pending, setPending] = useState(false);
  useEffect(() => { let active = true;
    apiClient.homework.call<any[]>('/auth/memberships').then(rows => {
      if (active) setSchools(Array.from(new Set([currentSchoolId, ...rows.map(r => r.school_id)])));
    }).catch(() => { if (active) setSchools([currentSchoolId]); });
    return () => { active = false; }; }, [currentSchoolId]);
  if (schools.length < 2) return null;
  return <label className="flex items-center gap-2 text-sm">School
    <select aria-label="School" className="rounded border px-2 py-1" disabled={pending} value={currentSchoolId} onChange={async e => {
      setError(''); setPending(true);
      try { await switchSchool(e.target.value); } catch (ex) { setError(errorText(ex)); } finally { setPending(false); }
    }}>{schools.map(s => <option key={s} value={s}>{s}</option>)}</select>
    {error && <span role="alert" className="text-xs text-rose-700">{error}</span>}
  </label>;
}

function Workspace({ role }: { role: string }) {
  if (role === 'student') return <StudentWorkspace />;
  if (role === 'parent') return <ParentWorkspace />;
  if (EDUCATOR_ROLES.includes(role)) return <TeacherWorkspace />;
  return <p>This account cannot access homework.</p>;
}
