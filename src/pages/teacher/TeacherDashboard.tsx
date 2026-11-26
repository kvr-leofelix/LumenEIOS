import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useData } from '../../context/DataContext';
import { useAuth } from '../../context/AuthContext';
import { KPICard } from '../../components/common/KPICard';
import { Card, CardHeader, CardBody } from '../../components/common/Card';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { CompetencyRadarChart } from '../../components/charts/CompetencyRadarChart';
import { ClassHeatmap } from '../../components/charts/ClassHeatmap';
import { DIM_LABEL, averageScores, examName, formatDay, summariseExams } from '../../lib/dashboard';
import { teacherClassIds } from '../../lib/workspace';
import { CalendarOverview } from '../../features/calendar/CalendarOverview';
import { AnnouncementsOverview } from '../../features/announcements/AnnouncementsOverview';
import {
  Users, BookOpen, Sparkles, ScanLine, ArrowRight, TrendingUp, FileCheck, Clock, AlertTriangle, ClipboardList,
} from 'lucide-react';

export const TeacherDashboard: React.FC = () => {
  const { classes, students, assessments, assessmentResults, workspace, workspaceLoading, teacherAssignments, subjects } = useData();
  const { currentUser } = useAuth();
  const navigate = useNavigate();

  const myClassIds = useMemo(() => teacherClassIds(workspace, currentUser?.id), [workspace, currentUser?.id]);
  const mine = teacherAssignments.filter(a => a.teacherId === currentUser?.id);
  const mySubjects = Array.from(new Set(mine.map(a => a.subjectId)));
  const myClasses = classes.filter(c => myClassIds.includes(c.id))
    .sort((a, b) => a.grade - b.grade || a.section.localeCompare(b.section));
  const homeroom = classes.find(c => c.classTeacherId === currentUser?.id);
  const [classId, setClassId] = useState('');
  useEffect(() => {
    if (!classId && myClasses.length) setClassId((homeroom && myClassIds.includes(homeroom.id) ? homeroom.id : myClasses[0].id));
  }, [classId, myClasses, homeroom, myClassIds]);

  const subjectName = (id: string) => subjects.find(s => s.id === id)?.name ?? id;
  const selected = classes.find(c => c.id === classId);
  const classStudents = students.filter(s => s.classId === classId).sort((a, b) => a.rollNo - b.rollNo);
  const current = averageScores(classStudents);
  const baseline = averageScores(classStudents, 'baselineCompetencies');
  const growth = current.overall - baseline.overall;
  const support = classStudents.filter(s => s.needsSupport).sort((a, b) => a.competencies.overall - b.competencies.overall);
  const subjectsHere = mine.filter(a => a.classId === classId).map(a => a.subjectId);
  const myAssessments = assessments.filter(a => a.classId === classId && (subjectsHere.length ? subjectsHere.includes(a.subjectId) : true));
  const exams = summariseExams(myAssessments.filter(a => a.status === 'graded'),
    assessmentResults.filter(r => myAssessments.some(a => a.id === r.assessmentId)));
  const latest = exams[exams.length - 1];
  const open = myAssessments.filter(a => a.status === 'scheduled').sort((a, b) => a.date.localeCompare(b.date));
  const pending = (workspace?.pendingUploads ?? {});
  const pendingTotal = assessments.filter(a => myClassIds.includes(a.classId)).reduce((n, a) => n + (pending[a.id] ?? 0), 0);

  if (workspaceLoading && !classes.length) return <p role="status" className="p-4 text-sm text-content-secondary">Loading your classes…</p>;

  return (
    <div className="space-y-6">
      <div className="bg-white p-5 rounded-2xl border border-surface-border shadow-subtle flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-bold text-navy-900 tracking-tight">Namaste, {currentUser?.name}</h1>
            {mySubjects.map(id => <Badge key={id} variant="teal" size="sm">{subjectName(id)}</Badge>)}
            {homeroom && <Badge variant="info" size="sm">Class teacher · {homeroom.name.replace('Class ', '')}</Badge>}
          </div>
          <p className="text-xs text-content-secondary mt-1">
            Teaches {myClasses.map(c => c.name.replace('Class ', '')).join(', ') || '—'} · {workspace?.schools[0]?.name} · Session {workspace?.schools[0]?.academicYear}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <Button variant="outline" size="sm" onClick={() => navigate('/upload')} icon={<ScanLine className="w-4 h-4 text-teal-600" />}>
            Evaluate uploads{pendingTotal ? ` (${pendingTotal})` : ''}
          </Button>
          <Button variant="primary" size="sm" onClick={() => navigate('/teacher/homework')} icon={<Sparkles className="w-4 h-4" />}>
            Differentiated homework
          </Button>
        </div>
      </div>

      {myClasses.length > 1 && (
        <div role="tablist" aria-label="Your classes" className="flex flex-wrap gap-2">
          {myClasses.map(c => (
            <button key={c.id} role="tab" aria-selected={c.id === classId} onClick={() => setClassId(c.id)}
              className={'rounded-xl border px-4 py-2 text-sm font-semibold transition ' + (c.id === classId ? 'border-navy-800 bg-navy-800 text-white' : 'border-surface-border bg-white text-content-primary hover:border-teal-300')}>
              {c.name}{c.classTeacherId === currentUser?.id ? ' ★' : ''}
            </button>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard title="Students" value={classStudents.length} subtitle={`${support.length} need extra support`}
          icon={<Users className="w-5 h-5 text-navy-800" />} iconBg="bg-navy-50" onClick={() => navigate('/teacher/classes')} />
        <KPICard title="Class average (LU/CU/AU/CT)" value={`${current.overall}%`} subtitle={`Baseline in April: ${baseline.overall}%`}
          icon={<TrendingUp className="w-5 h-5 text-teal-600" />} iconBg="bg-teal-50"
          trend={{ value: `${growth >= 0 ? '+' : ''}${growth}%`, isPositive: growth >= 0, label: 'since baseline' }} />
        <KPICard title={latest ? examName(latest.assessment.title) : 'Latest result'} value={latest ? `${latest.average}%` : '—'}
          subtitle={latest ? `${subjectName(latest.assessment.subjectId)} · highest ${latest.highest}% · lowest ${latest.lowest}%` : 'No graded work yet'}
          icon={<FileCheck className="w-5 h-5 text-amber-600" />} iconBg="bg-amber-50" />
        <KPICard title="To evaluate" value={pendingTotal} subtitle="Handwritten uploads waiting for marks"
          icon={<ScanLine className="w-5 h-5 text-indigo-600" />} iconBg="bg-indigo-50" onClick={() => navigate('/upload')} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card>
          <CardHeader title={`${selected?.name ?? 'Class'} competency profile`} subtitle="Class average now vs April baseline"
            action={<Badge variant="teal" size="sm">NEP 4-dimensional</Badge>} />
          <CardBody>
            <CompetencyRadarChart current={current} baseline={baseline} benchmarkName="April baseline" height={250} />
            <div className="mt-3 pt-3 border-t border-surface-border grid grid-cols-2 gap-2 text-xs text-center">
              {(['LU', 'CU', 'AU', 'CT'] as const).map(d => (
                <div key={d} className="p-2 bg-surface-bg rounded-lg">
                  <span className="text-content-secondary text-[11px] block">{DIM_LABEL[d]} ({d})</span>
                  <span className="font-bold text-navy-800">{current[d]}%</span>
                  <span className={'ml-1 text-[11px] ' + (current[d] - baseline[d] >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
                    {current[d] - baseline[d] >= 0 ? '+' : ''}{current[d] - baseline[d]}
                  </span>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>

        <div className="space-y-4"><AnnouncementsOverview /><CalendarOverview /></div>

        <div className="lg:col-span-2 lg:row-span-2 space-y-6">
          <Card>
            <CardHeader title={`Results · ${subjectsHere.map(subjectName).join(', ') || 'all subjects'}`} subtitle={`${selected?.name ?? ''} · 2026-27 session`}
              action={<Button variant="outline" size="sm" onClick={() => navigate('/teacher/classes')} icon={<ClipboardList className="w-3.5 h-3.5" />}>All results</Button>} />
            <CardBody>
              {exams.length === 0 ? <p className="text-sm text-content-secondary">No graded assessments yet.</p> : (
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-xs uppercase tracking-wide text-content-secondary">
                    <th className="py-2">Assessment</th><th>Date</th><th className="text-right">Class avg</th><th className="text-right">Highest</th><th className="text-right">Lowest</th></tr></thead>
                  <tbody className="divide-y divide-surface-border">
                    {exams.slice().reverse().map(e => (
                      <tr key={e.assessment.id}>
                        <td className="py-2 font-medium">{examName(e.assessment.title)} <span className="text-xs text-content-secondary">· {e.assessment.totalMarks} marks</span></td>
                        <td className="text-content-secondary">{formatDay(e.assessment.date)}</td>
                        <td className="text-right font-semibold">{e.average}%</td>
                        <td className="text-right text-emerald-700">{e.highest}%</td>
                        <td className="text-right text-rose-700">{e.lowest}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardBody>
          </Card>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader title="Open assignments" subtitle="Students upload handwritten answers" />
              <CardBody className="space-y-2">
                {open.length === 0 ? <p className="text-sm text-content-secondary">Nothing open.</p> : open.map(a => (
                  <button key={a.id} onClick={() => navigate(`/upload?assignment=${a.id}`)}
                    className="flex w-full items-center justify-between gap-3 rounded-xl border border-surface-border px-3 py-2 text-left text-sm hover:border-teal-400">
                    <span className="min-w-0"><span className="block truncate font-medium">{a.title}</span>
                      <span className="text-xs text-content-secondary"><Clock className="mr-1 inline h-3 w-3" />Due {formatDay(a.date)} · {workspace?.uploadedCounts?.[a.id] ?? 0} uploaded</span></span>
                    {(pending[a.id] ?? 0) > 0 ? <Badge variant="warning" size="sm">{pending[a.id]} to evaluate</Badge> : <ArrowRight className="h-4 w-4 text-content-muted" />}
                  </button>
                ))}
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Students needing support" subtitle="Lowest overall first" />
              <CardBody className="space-y-2">
                {support.length === 0 ? <p className="text-sm text-content-secondary">No one is flagged in this class.</p> : support.slice(0, 6).map(s => (
                  <div key={s.id} className="flex items-center justify-between gap-2 rounded-xl border border-surface-border px-3 py-2 text-sm">
                    <span className="min-w-0"><span className="font-medium">{s.name}</span>
                      <span className="block text-xs text-rose-700"><AlertTriangle className="mr-1 inline h-3 w-3" />{s.supportArea ?? 'Overall'} · {s.competencies.overall}%</span></span>
                    <Button size="sm" variant="outline" onClick={() => navigate(`/teacher/homework?classId=${classId}&studentId=${s.id}`)}>Assign homework</Button>
                  </div>
                ))}
              </CardBody>
            </Card>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {[{ to: '/teacher/assessments', title: 'AI Question Studio', text: 'Generate questions from a chapter PDF', icon: <BookOpen className="w-5 h-5" /> },
              { to: '/teacher/time-aware', title: 'Time-Aware Engine', text: 'Syllabus coverage and lost periods', icon: <Clock className="w-5 h-5" /> }].map(l => (
              <div key={l.to} onClick={() => navigate(l.to)} role="link" tabIndex={0} onKeyDown={e => e.key === 'Enter' && navigate(l.to)}
                className="p-4 bg-white rounded-xl border border-surface-border hover:border-teal-400 hover:shadow-card cursor-pointer transition-all flex items-center justify-between">
                <div className="flex items-center gap-3"><div className="p-2.5 bg-teal-50 text-teal-600 rounded-lg">{l.icon}</div>
                  <div><h4 className="font-semibold text-content-primary text-sm">{l.title}</h4><p className="text-xs text-content-secondary">{l.text}</p></div></div>
                <ArrowRight className="w-4 h-4 text-content-muted" />
              </div>
            ))}
          </div>
        </div>
      </div>

      <Card>
        <CardHeader title={`${selected?.name ?? 'Class'} competency heatmap`} subtitle="Every student's Language (LU), Concept (CU), Application (AU) and Critical Thinking (CT)" />
        <CardBody>
          <ClassHeatmap students={classStudents} onTriggerRemediation={(st) => navigate(`/teacher/homework?classId=${classId}&studentId=${st.id}`)} />
        </CardBody>
      </Card>
    </div>
  );
};
