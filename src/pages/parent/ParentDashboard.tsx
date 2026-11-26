import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell, CheckCircle2, Printer, Sparkles, Users } from 'lucide-react';
import { useData } from '../../context/DataContext';
import { useAuth } from '../../context/AuthContext';
import { apiClient } from '../../lib/apiClient';
import { Card, CardBody, CardHeader } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { LearnerOverview } from '../../components/learner/LearnerOverview';
import { CalendarOverview } from '../../features/calendar/CalendarOverview';
import { AnnouncementsOverview } from '../../features/announcements/AnnouncementsOverview';
import { DIM_LABEL } from '../../lib/dashboard';

// Everyday, low-cost activities families can do at home, by the competency that needs the most support.
const HOME_ACTIVITIES: Record<string, { title: string; text: string }[]> = {
  LU: [
    { title: 'Read the question aloud', text: 'Ask your child to read a homework question aloud and tell you, in their own words, what it is asking before they start.' },
    { title: 'Newspaper word hunt', text: 'Pick five new words from the newspaper each week and use each one in a sentence at dinner.' },
  ],
  CU: [
    { title: 'Explain it to me', text: 'Let your child teach you one idea from today\'s class - why it works, not just the answer.' },
    { title: 'Kitchen science', text: 'While cooking, talk about what changes when food is heated, mixed or frozen, and why.' },
  ],
  AU: [
    { title: 'Shopkeeper maths', text: 'Let your child total the bill, work out the change and compare prices per kilogram at the market.' },
    { title: 'Measure the home', text: 'Measure a room or the water tank together and work out its area or capacity.' },
  ],
  CT: [
    { title: 'Is that true?', text: 'Pick a claim from an advertisement or the news and ask how you could check it.' },
    { title: 'Two ways to solve', text: 'Ask your child to solve one homework problem two different ways and say which is better and why.' },
  ],
};

export const ParentDashboard: React.FC = () => {
  const navigate = useNavigate();
  const { students, classes, workspace, workspaceLoading } = useData();
  const { currentUser } = useAuth();
  const children = students;
  const [childId, setChildId] = useState('');
  const [notes, setNotes] = useState<{ id: string; title: string; message: string; created_at?: string; is_read?: boolean }[]>([]);
  useEffect(() => { if (!childId && children.length) setChildId(children[0].id); }, [childId, children]);
  useEffect(() => {
    let active = true;
    apiClient.notifications.getAll().then((rows: any[]) => { if (active) setNotes(rows.slice(0, 5)); }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  const child = children.find(c => c.id === childId);
  if (workspaceLoading && !child) return <p role="status" className="p-4 text-sm text-content-secondary">Loading your child's progress…</p>;
  if (!child) return <p className="p-4 text-sm text-content-secondary">No student is linked to this parent account. Please contact the school office.</p>;
  const cls = classes.find(c => c.id === child.classId);
  const weakest = (['LU', 'CU', 'AU', 'CT'] as const).reduce((w, d) => (child.competencies[d] < child.competencies[w] ? d : w), 'LU' as 'LU' | 'CU' | 'AU' | 'CT');

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 rounded-2xl border border-surface-border bg-white p-5 shadow-subtle md:flex-row md:items-center">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-bold text-navy-900">Namaste, {currentUser?.name}</h1>
            <Badge variant="teal" size="sm">Parent portal</Badge>
          </div>
          <p className="mt-1 text-xs text-content-secondary">
            {child.name} · {cls?.name ?? child.className} · Roll {child.rollNo}
            {cls?.classTeacherName ? ` · Class teacher ${cls.classTeacherName}` : ''} · {workspace?.schools[0]?.name} · Attendance {child.attendancePct}%
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {children.length > 1 && children.map(c => (
            <button key={c.id} onClick={() => setChildId(c.id)}
              className={'rounded-lg border px-3 py-1.5 text-xs font-semibold ' + (c.id === childId ? 'border-navy-800 bg-navy-800 text-white' : 'border-surface-border bg-white')}>
              <Users className="mr-1 inline h-3.5 w-3.5" />{c.name.split(' ')[0]}
            </button>
          ))}
          <button onClick={() => navigate('/parent/homework')} className="inline-flex items-center gap-1.5 rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-teal-700"><Sparkles className="h-3.5 w-3.5" />Homework results</button>
          <button onClick={() => window.print()} className="inline-flex items-center gap-1.5 rounded-lg border border-surface-border bg-white px-3 py-1.5 text-xs font-semibold"><Printer className="h-3.5 w-3.5" />Print report</button>
        </div>
      </div>

      {notes.length > 0 && (
        <Card>
          <CardHeader title="From the school" subtitle="Latest notifications" />
          <CardBody className="space-y-2">
            {notes.map(n => (
              <div key={n.id} className="flex items-start gap-2 rounded-xl border border-surface-border px-3 py-2 text-sm">
                <Bell className={'mt-0.5 h-4 w-4 shrink-0 ' + (n.is_read ? 'text-content-muted' : 'text-teal-600')} />
                <span><span className="font-semibold text-navy-900">{n.title}</span><span className="block text-content-secondary">{n.message}</span></span>
              </div>
            ))}
          </CardBody>
        </Card>
      )}

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_330px]">
        <LearnerOverview studentId={child.id} audience="parent" />
        <div className="space-y-4"><AnnouncementsOverview /><CalendarOverview /></div>
      </div>

      <Card>
        <CardHeader title="How you can help at home" subtitle={`${child.name.split(' ')[0]}'s parameter that needs the most support right now: ${DIM_LABEL[weakest]} (${child.competencies[weakest]}%)`} />
        <CardBody className="grid gap-3 md:grid-cols-2">
          {HOME_ACTIVITIES[weakest].map(a => (
            <div key={a.title} className="flex items-start gap-2 rounded-xl border border-teal-200/60 bg-teal-50/50 p-3 text-sm">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-teal-600" />
              <span><strong>{a.title}:</strong> {a.text}</span>
            </div>
          ))}
        </CardBody>
      </Card>
    </div>
  );
};
