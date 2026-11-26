import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { DEMO_MODE } from '../../lib/runtime';
import { ApiError, DevAccount, apiClient } from '../../lib/apiClient';
import { Role } from '../../types';
import { getDefaultDashboardPath } from '../../lib/permissions';
import { ThemeMenu } from '../../components/layout/ThemeMenu';
import {
  Shield, School, BookOpen, GraduationCap, Users, ArrowRight, Sparkles, Lock, Mail, Code2, Search, ChevronDown,
} from 'lucide-react';

const ROLE_META: Record<string, { icon: React.ReactNode; title: string; tint: string }> = {
  admin: { icon: <Shield className="w-5 h-5 text-indigo-600" />, title: 'Management', tint: 'hover:border-indigo-400' },
  principal: { icon: <School className="w-5 h-5 text-teal-600" />, title: 'Principal', tint: 'hover:border-teal-400' },
  teacher: { icon: <BookOpen className="w-5 h-5 text-emerald-600" />, title: 'Teacher', tint: 'hover:border-emerald-400' },
  student: { icon: <GraduationCap className="w-5 h-5 text-sky-600" />, title: 'Student', tint: 'hover:border-sky-400' },
  parent: { icon: <Users className="w-5 h-5 text-amber-600" />, title: 'Parent', tint: 'hover:border-amber-400' },
};
const ROLE_ORDER = ['admin', 'principal', 'teacher', 'student', 'parent'];

// Offline demonstration personas (VITE_DEMO_MODE=true only; no backend).
const OFFLINE_PERSONAS: { role: Role; name: string; email: string; description: string }[] = [
  { role: 'admin', name: 'IIT Mandi', email: 'admin@lumeneios.demo', description: 'Offline administrator' },
  { role: 'principal', name: 'Principal', email: 'principal@lumeneios.demo', description: 'Offline principal' },
  { role: 'teacher', name: 'Teacher', email: 'teacher@lumeneios.demo', description: 'Offline teacher' },
  { role: 'student', name: 'Student', email: 'student@lumeneios.demo', description: 'Offline student' },
  { role: 'parent', name: 'Parent', email: 'parent@lumeneios.demo', description: 'Offline parent' },
];

export const LoginPage: React.FC = () => {
  const { login, loginAsRole, loginAsAccount, loginWithPassword, isLoading, isRestoringSession } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState(DEMO_MODE ? 'teacher@lumeneios.demo' : '');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isSigningIn, setIsSigningIn] = useState(false);
  // Developer bypass (backend APP_ENV=development): every account, featured personas first.
  const [accounts, setAccounts] = useState<DevAccount[] | null>(null);
  const [devOpen, setDevOpen] = useState(false);
  const [devQuery, setDevQuery] = useState('');
  const [devRole, setDevRole] = useState('');
  const [devSchool, setDevSchool] = useState('');

  useEffect(() => {
    if (DEMO_MODE) return;
    let active = true;
    apiClient.auth.devAccounts().then(res => { if (active) setAccounts(res.accounts); }).catch(() => { if (active) setAccounts([]); });
    return () => { active = false; };
  }, []);

  const featured = useMemo(() => ROLE_ORDER.map(role => accounts?.find(a => a.featured && a.role === role)).filter(Boolean) as DevAccount[], [accounts]);
  const schools = useMemo(() => Array.from(new Set((accounts ?? []).map(a => a.school_name).filter(Boolean))) as string[], [accounts]);
  const filtered = useMemo(() => {
    const q = devQuery.trim().toLowerCase();
    return (accounts ?? []).filter(a => (!devRole || a.role === devRole) && (!devSchool || a.school_name === devSchool)
      && (!q || [a.name, a.email, a.username, a.designation].some(v => (v || '').toLowerCase().includes(q))));
  }, [accounts, devQuery, devRole, devSchool]);
  const bypass = !DEMO_MODE && (accounts?.length ?? 0) > 0;

  type AuthResult = boolean | { role: Role };
  const signIn = async (authenticate: () => AuthResult | Promise<AuthResult>) => {
    if (isSigningIn || isLoading || isRestoringSession) return;
    setError('');
    setIsSigningIn(true);
    try {
      const result = await authenticate();
      if (result === false) {
        setError('Invalid credentials.');
        return;
      }
      const role = result === true ? (OFFLINE_PERSONAS.find(a => a.email === email)?.role || 'teacher') : result.role;
      navigate(getDefaultDashboardPath(role), { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError && [401, 422].includes(err.status)
          ? 'Incorrect username/email or password. Students: admission number and date of birth (DDMMYYYY). Parents: registered mobile number.'
          : err instanceof Error ? err.message : 'Could not sign in. Check that the backend is running and try again.'
      );
    } finally {
      setIsSigningIn(false);
    }
  };

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void signIn(async (): Promise<AuthResult> => (DEMO_MODE ? login(email) : loginWithPassword(email.trim(), password)));
  };

  if (isLoading || isRestoringSession) {
    return <p role="status" className="p-6">Checking your session…</p>;
  }

  return (
    <div className="relative min-h-screen bg-surface-bg flex flex-col justify-center py-10 px-4 sm:px-6 lg:px-8 font-sans">
      <ThemeMenu className="absolute top-4 right-4 z-20" />
      <div className="sm:mx-auto sm:w-full sm:max-w-2xl text-center">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-teal-500 text-navy-950 font-black text-2xl shadow-card mb-4">L</div>
        <h1 className="text-3xl font-extrabold text-navy-800 tracking-tight">Lumen<span className="text-teal-600">EIOS</span></h1>
        <p className="mt-1 text-sm font-medium text-content-secondary">Adaptive EdTech Ecosystem • Aligned with NEP 2020 Competency Standards</p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-2xl">
        <div className="bg-white py-8 px-6 sm:px-10 rounded-2xl shadow-card border border-surface-border">
          <form onSubmit={handleManualSubmit} className="space-y-4">
            <div>
              <label htmlFor="login-email" className="block text-xs font-semibold text-content-primary mb-1">
                {DEMO_MODE ? 'Demo Account Email' : 'Email or username'}
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-content-muted absolute left-3 top-3 pointer-events-none" />
                <input id="login-email" type="text" aria-label="Email" autoComplete="username" value={email}
                  onChange={(e) => setEmail(e.target.value)} required
                  className="w-full pl-9 pr-3 py-2 bg-surface-bg/40 border border-surface-border rounded-lg text-sm text-content-primary focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500"
                  placeholder="Email, staff code, admission number or mobile number" />
              </div>
            </div>
            <div>
              <label htmlFor="login-password" className="block text-xs font-semibold text-content-primary mb-1">Password</label>
              <div className="relative">
                <Lock className="w-4 h-4 text-content-muted absolute left-3 top-3 pointer-events-none" />
                <input id="login-password" type="password" aria-label="Password" autoComplete="current-password" value={password}
                  onChange={(e) => setPassword(e.target.value)} required={!DEMO_MODE}
                  className="w-full pl-9 pr-3 py-2 bg-surface-bg/40 border border-surface-border rounded-lg text-sm text-content-primary focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500"
                  placeholder={DEMO_MODE ? 'Not needed offline' : 'Password'} />
              </div>
            </div>

            {!DEMO_MODE && (
              <div className="grid gap-2 rounded-lg border border-surface-border bg-surface-bg/50 px-3 py-2.5 text-xs text-content-secondary sm:grid-cols-3">
                <p><span className="font-semibold text-navy-800">Staff</span><br />School email or staff code</p>
                <p><span className="font-semibold text-navy-800">Students</span><br />Admission no. · password = date of birth (DDMMYYYY)</p>
                <p><span className="font-semibold text-navy-800">Parents</span><br />Registered mobile number</p>
              </div>
            )}

            {error && <p role="alert" className="text-xs text-rose-600 font-medium bg-rose-50 p-2.5 rounded-lg border border-rose-200">{error}</p>}

            <button type="submit" disabled={isSigningIn || isRestoringSession}
              className="w-full py-2.5 px-4 bg-navy-800 hover:bg-navy-900 active:bg-navy-950 disabled:opacity-60 text-white rounded-lg text-sm font-semibold shadow-sm transition-colors flex items-center justify-center gap-2">
              <span>{isSigningIn ? 'Signing in…' : 'Sign in'}</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </form>

          {(DEMO_MODE || featured.length > 0) && (
            <div className="mt-8 pt-6 border-t border-surface-border">
              <div className="flex items-center justify-between mb-3.5">
                <span className="text-xs font-bold text-navy-800 uppercase tracking-wider flex items-center gap-1.5">
                  <Sparkles className="w-4 h-4 text-teal-600" /><span>1-Click Stakeholder Demonstrations</span>
                </span>
                <span className="text-[11px] text-content-muted">{DEMO_MODE ? 'Offline seed' : 'Developer mode · no password'}</span>
              </div>
              <div className="space-y-2.5">
                {(DEMO_MODE ? OFFLINE_PERSONAS.map(p => ({ id: p.email, name: p.name, role: p.role, email: p.email, designation: p.description, school_name: null })) : featured).map((acc) => (
                  <div key={acc.id} className={`p-3 rounded-xl border border-surface-border transition-all flex items-center justify-between gap-3 group ${ROLE_META[acc.role]?.tint ?? ''}`}>
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="p-2 bg-white rounded-lg border border-surface-border shadow-xs">{ROLE_META[acc.role]?.icon}</div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-content-primary">{acc.name}</span>
                          <span className="text-[10px] font-bold uppercase tracking-wider text-teal-700 bg-teal-50 px-1.5 py-0.5 rounded border border-teal-200">{ROLE_META[acc.role]?.title ?? acc.role}</span>
                        </div>
                        <p className="text-xs text-content-secondary line-clamp-1">{acc.designation}{acc.school_name ? ` · ${acc.school_name}` : ''}</p>
                        <p className="text-[10px] text-content-muted font-mono mt-0.5 truncate">{acc.email}</p>
                      </div>
                    </div>
                    <button type="button" disabled={isSigningIn || isRestoringSession}
                      onClick={() => void signIn(async () => (DEMO_MODE ? loginAsRole(acc.role as Role) : loginAsAccount(acc.id)))}
                      className="px-3 py-1.5 text-xs font-semibold text-navy-800 bg-white border border-surface-border rounded-lg group-hover:bg-navy-800 group-hover:text-white transition-colors shrink-0 shadow-xs disabled:opacity-60">
                      Login as {(ROLE_META[acc.role]?.title ?? acc.role).toLowerCase()}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {bypass && (
            <div className="mt-6 rounded-xl border border-violet-200 bg-violet-50/40">
              <button type="button" onClick={() => setDevOpen(o => !o)} aria-expanded={devOpen}
                className="flex w-full items-center justify-between px-4 py-3 text-left">
                <span className="flex items-center gap-2 text-sm font-semibold text-violet-900"><Code2 className="h-4 w-4" />Developer mode: sign in as any account</span>
                <ChevronDown className={'h-4 w-4 text-violet-700 transition ' + (devOpen ? 'rotate-180' : '')} />
              </button>
              {devOpen && <div className="space-y-3 border-t border-violet-200 px-4 py-3">
                <p className="text-xs text-violet-900/80">Password bypass for demonstrations. Available only when the backend runs with APP_ENV=development. Team root login LEOFELIX / KVR also works.</p>
                <div className="grid gap-2 sm:grid-cols-3">
                  <div className="relative sm:col-span-3">
                    <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-content-muted" />
                    <input aria-label="Search accounts" value={devQuery} onChange={e => setDevQuery(e.target.value)} placeholder="Search name, email, admission no., class…"
                      className="w-full rounded-lg border border-surface-border bg-white py-2 pl-8 pr-3 text-sm" />
                  </div>
                  <select aria-label="Role" value={devRole} onChange={e => setDevRole(e.target.value)} className="rounded-lg border border-surface-border bg-white px-2 py-2 text-sm">
                    <option value="">All roles</option>{ROLE_ORDER.map(r => <option key={r} value={r}>{ROLE_META[r].title}</option>)}
                  </select>
                  <select aria-label="School" value={devSchool} onChange={e => setDevSchool(e.target.value)} className="rounded-lg border border-surface-border bg-white px-2 py-2 text-sm sm:col-span-2">
                    <option value="">All schools</option>{schools.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <p className="text-[11px] text-content-muted">{filtered.length} account{filtered.length === 1 ? '' : 's'}</p>
                <ul className="max-h-72 space-y-1 overflow-y-auto pr-1">
                  {filtered.slice(0, 200).map(a => (
                    <li key={a.id}>
                      <button type="button" disabled={isSigningIn} onClick={() => void signIn(() => loginAsAccount(a.id))}
                        className="flex w-full items-center justify-between gap-3 rounded-lg border border-surface-border bg-white px-3 py-2 text-left text-sm transition hover:border-violet-400">
                        <span className="min-w-0">
                          <span className="font-medium text-content-primary">{a.name}</span>
                          <span className="block truncate text-[11px] text-content-secondary">{a.designation}{a.school_name ? ` · ${a.school_name}` : ''}</span>
                        </span>
                        <span className="shrink-0 text-right">
                          <span className="block text-[10px] font-bold uppercase text-violet-700">{ROLE_META[a.role]?.title ?? a.role}</span>
                          <span className="block font-mono text-[10px] text-content-muted">{a.username}</span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>}
            </div>
          )}
        </div>

        <div className="mt-6 text-center text-xs text-content-secondary">
          <p>LumenEIOS incorporates Time-Aware Syllabus Compacting, protecting foundational concept mastery when teaching days are lost to public duties.</p>
        </div>
      </div>
    </div>
  );
};
