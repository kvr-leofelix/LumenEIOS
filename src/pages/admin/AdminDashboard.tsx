import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, Building2, MapPin, ShieldCheck } from 'lucide-react';
import { useData } from '../../context/DataContext';
import { useAuth } from '../../context/AuthContext';
import { apiClient } from '../../lib/apiClient';
import { Card, CardBody, CardHeader } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { SchoolOverview } from '../../components/school/SchoolOverview';
import { CalendarOverview } from '../../features/calendar/CalendarOverview';
import { AnnouncementsOverview } from '../../features/announcements/AnnouncementsOverview';
import { averageScores } from '../../lib/dashboard';

export const AdminDashboard: React.FC = () => {
  const navigate = useNavigate();
  const { currentUser } = useAuth();
  const { schools, students, workspace, workspaceLoading } = useData();
  const [scope, setScope] = useState('all');
  const [events, setEvents] = useState<any[]>([]);
  useEffect(() => {
    let active = true;
    apiClient.audit.getEvents().then((rows: any[]) => { if (active) setEvents(rows.slice(0, 8)); }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  if (workspaceLoading && !schools.length) return <p role="status" className="p-4 text-sm text-content-secondary">Loading the school network…</p>;
  const ids = scope === 'all' ? schools.map(s => s.id) : [scope];

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 rounded-2xl border border-surface-border bg-white p-5 shadow-subtle md:flex-row md:items-center">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-bold text-navy-900">Shiksha Bharati Education Society</h1>
            <Badge variant="teal" size="sm">Management</Badge>
          </div>
          <p className="mt-1 text-xs text-content-secondary">{currentUser?.name} · {currentUser?.designation} · {schools.length} CBSE schools · Session {schools[0]?.academicYear}</p>
        </div>
        <div role="tablist" aria-label="Schools" className="flex flex-wrap gap-2">
          {[{ id: 'all', name: 'All schools' }, ...schools].map(s => (
            <button key={s.id} role="tab" aria-selected={scope === s.id} onClick={() => setScope(s.id)}
              className={'rounded-lg border px-3 py-1.5 text-xs font-semibold ' + (scope === s.id ? 'border-navy-800 bg-navy-800 text-white' : 'border-surface-border bg-white hover:border-teal-300')}>{s.name}</button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {schools.map(s => {
          const learners = students.filter(x => x.schoolId === s.id);
          const now = averageScores(learners); const base = averageScores(learners, 'baselineCompetencies');
          const lost = (workspace?.disruptions ?? []).filter(d => d.schoolId === s.id).reduce((n, d) => n + d.daysLost, 0);
          return (
            <button key={s.id} onClick={() => setScope(s.id)} className={'rounded-2xl border bg-white p-5 text-left shadow-subtle transition hover:border-teal-400 ' + (scope === s.id ? 'border-teal-500' : 'border-surface-border')}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="flex items-center gap-2 text-lg font-bold text-navy-900"><Building2 className="h-5 w-5 text-teal-600" />{s.name}</p>
                  <p className="text-xs text-content-secondary"><MapPin className="mr-1 inline h-3 w-3" />{s.location}, {s.state} · Principal {s.principalName}</p>
                </div>
                <Badge variant={s.pacingRisk === 'low' ? 'success' : s.pacingRisk === 'medium' ? 'warning' : 'danger'} size="sm">{s.pacingRisk} pacing risk</Badge>
              </div>
              <div className="mt-4 grid grid-cols-4 gap-2 text-center text-xs">
                <div className="rounded-lg bg-surface-bg p-2"><span className="block text-content-secondary">Students</span><span className="text-base font-bold">{learners.length}</span></div>
                <div className="rounded-lg bg-surface-bg p-2"><span className="block text-content-secondary">Average</span><span className="text-base font-bold">{now.overall}%</span></div>
                <div className="rounded-lg bg-surface-bg p-2"><span className="block text-content-secondary">Growth</span><span className="text-base font-bold text-emerald-700">+{now.overall - base.overall}</span></div>
                <div className="rounded-lg bg-surface-bg p-2"><span className="block text-content-secondary">Lost days</span><span className="text-base font-bold text-rose-700">{lost}</span></div>
              </div>
            </button>
          );
        })}
      </div>

      <SchoolOverview key={scope} schoolIds={ids} />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <Card>
        <CardHeader title="Recent activity" subtitle="Audit trail across the network"
          action={<button onClick={() => navigate('/admin/audit-logs')} className="text-xs font-semibold text-teal-700 hover:underline">Full audit log</button>} />
        <CardBody className="space-y-1.5">
          {events.length === 0 ? <p className="text-sm text-content-secondary">No recent events.</p> : events.map((e, i) => (
            <div key={e.id ?? i} className="flex items-start justify-between gap-3 rounded-lg border border-surface-border px-3 py-2 text-sm">
              <span className="min-w-0"><span className="font-medium"><Activity className="mr-1 inline h-3.5 w-3.5 text-teal-600" />{e.action}</span>
                <span className="block truncate text-xs text-content-secondary">{e.details}</span></span>
              <span className="shrink-0 text-right text-xs text-content-secondary"><ShieldCheck className="mr-1 inline h-3 w-3" />{e.user_name ?? e.userName}<span className="block">{e.timestamp}</span></span>
            </div>
          ))}
        </CardBody>
      </Card>
      <div className="space-y-4"><AnnouncementsOverview /><CalendarOverview /></div>
      </div>
    </div>
  );
};
