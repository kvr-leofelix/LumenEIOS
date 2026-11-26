import React, { useMemo } from 'react';
import { AlertTriangle, BookOpen, Clock, School as SchoolIcon, TrendingUp, Users } from 'lucide-react';
import { useData } from '../../context/DataContext';
import { KPICard } from '../common/KPICard';
import { Card, CardBody, CardHeader } from '../common/Card';
import { Badge } from '../common/Badge';
import { CompetencyRadarChart } from '../charts/CompetencyRadarChart';
import { CompetencyBarChart } from '../charts/CompetencyBarChart';
import { DIM_LABEL, averageScores, examName, formatDay } from '../../lib/dashboard';

const mean = (xs: number[]) => (xs.length ? Math.round(xs.reduce((a, b) => a + b, 0) / xs.length) : 0);

/** Live analytics for one school (principal) or every school the account manages (management). */
export const SchoolOverview: React.FC<{ schoolIds: string[] }> = ({ schoolIds }) => {
  const { classes, students, assessments, assessmentResults, subjects, teachers, teacherAssignments, workspace } = useData();
  const inScope = (id: string) => schoolIds.includes(id);
  const myClasses = classes.filter(c => inScope(c.schoolId)).sort((a, b) => a.schoolId.localeCompare(b.schoolId) || a.grade - b.grade || a.section.localeCompare(b.section));
  const myStudents = students.filter(s => inScope(s.schoolId));
  const myTeachers = teachers.filter(t => inScope(t.schoolId));
  const current = averageScores(myStudents);
  const baseline = averageScores(myStudents, 'baselineCompetencies');
  const support = myStudents.filter(s => s.needsSupport).sort((a, b) => a.competencies.overall - b.competencies.overall);
  const lost = (workspace?.disruptions ?? []).filter(d => inScope(d.schoolId));
  const lostDays = lost.reduce((n, d) => n + d.daysLost, 0);
  const subjectName = (id: string) => subjects.find(s => s.id === id)?.name ?? id;
  const multi = schoolIds.length > 1;
  const schoolName = (id: string) => workspace?.schools.find(s => s.id === id)?.name ?? id;

  const classChart = myClasses.map(c => {
    const avg = averageScores(myStudents.filter(s => s.classId === c.id));
    return { name: (multi ? `${schoolName(c.schoolId).split(' ').map(w => w[0]).join('')} ` : '') + c.name.replace('Class ', ''), LU: avg.LU, CU: avg.CU, AU: avg.AU, CT: avg.CT };
  });

  // Average percentage per exam round and grade.
  const examTable = useMemo(() => {
    const byKey = new Map<string, number[]>();
    const assessmentById = new Map(assessments.filter(a => inScope(a.schoolId) && a.status === 'graded').map(a => [a.id, a]));
    const gradeOf = new Map(myClasses.map(c => [c.id, c.grade]));
    const roundDate = new Map<string, string>();
    for (const r of assessmentResults) {
      const a = assessmentById.get(r.assessmentId);
      if (!a) continue;
      const round = examName(a.title);
      const key = `${round}|${gradeOf.get(a.classId)}`;
      (byKey.get(key) ?? byKey.set(key, []).get(key)!).push(r.percentage);
      if (!roundDate.has(round) || a.date < roundDate.get(round)!) roundDate.set(round, a.date);
    }
    const rounds = Array.from(roundDate.keys()).sort((x, y) => roundDate.get(x)!.localeCompare(roundDate.get(y)!));
    const grades = Array.from(new Set(myClasses.map(c => c.grade))).sort();
    return { rounds, grades, roundDate, value: (round: string, g: number) => (byKey.get(`${round}|${g}`)?.length ? mean(byKey.get(`${round}|${g}`)!) : null) };
  }, [assessments, assessmentResults, myClasses]); // eslint-disable-line react-hooks/exhaustive-deps

  // Half-Yearly average by subject and grade.
  const subjectTable = useMemo(() => {
    const hy = assessments.filter(a => inScope(a.schoolId) && a.title.startsWith('Half-Yearly'));
    const gradeOf = new Map(myClasses.map(c => [c.id, c.grade]));
    const cells = new Map<string, number[]>();
    for (const r of assessmentResults) {
      const a = hy.find(x => x.id === r.assessmentId);
      if (!a) continue;
      const key = `${a.subjectId}|${gradeOf.get(a.classId)}`;
      (cells.get(key) ?? cells.set(key, []).get(key)!).push(r.percentage);
    }
    const subjectIds = Array.from(new Set(hy.map(a => a.subjectId))).sort((x, y) => subjectName(x).localeCompare(subjectName(y)));
    return { subjectIds, value: (sid: string, g: number) => mean(cells.get(`${sid}|${g}`) ?? []) };
  }, [assessments, assessmentResults, myClasses]); // eslint-disable-line react-hooks/exhaustive-deps

  const teacherRows = myTeachers.map(t => {
    const rows = teacherAssignments.filter(a => a.teacherId === t.id);
    const latest = assessments.filter(a => rows.some(r => r.classId === a.classId && r.subjectId === a.subjectId) && a.title.startsWith('Half-Yearly'));
    const pcts = assessmentResults.filter(r => latest.some(a => a.id === r.assessmentId)).map(r => r.percentage);
    return { t, subject: subjectName(rows[0]?.subjectId ?? ''), classes: rows.map(r => myClasses.find(c => c.id === r.classId)?.name.replace('Class ', '') ?? '').join(', '), avg: mean(pcts),
      homeroom: myClasses.find(c => c.classTeacherId === t.id)?.name.replace('Class ', '') };
  }).sort((a, b) => a.subject.localeCompare(b.subject) || a.t.name.localeCompare(b.t.name));

  if (!myStudents.length) return <p role="status" className="p-4 text-sm text-content-secondary">Loading school data…</p>;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KPICard title="Students" value={myStudents.length} subtitle={`${myClasses.length} sections · Classes ${Array.from(new Set(myClasses.map(c => c.grade))).join(', ')}`}
          icon={<Users className="h-5 w-5 text-navy-800" />} iconBg="bg-navy-50" />
        <KPICard title="Teachers" value={myTeachers.length} subtitle={`${teacherAssignments.filter(a => inScope(a.schoolId)).length} class-subject allocations`}
          icon={<BookOpen className="h-5 w-5 text-teal-600" />} iconBg="bg-teal-50" />
        <KPICard title="Average competency" value={`${current.overall}%`} subtitle={`April baseline ${baseline.overall}%`}
          icon={<TrendingUp className="h-5 w-5 text-emerald-600" />} iconBg="bg-emerald-50"
          trend={{ value: `${current.overall - baseline.overall >= 0 ? '+' : ''}${current.overall - baseline.overall}%`, isPositive: current.overall >= baseline.overall, label: 'since April' }} />
        <KPICard title="Lost teaching days" value={lostDays} subtitle={`${support.length} students need extra support`}
          icon={<Clock className="h-5 w-5 text-rose-600" />} iconBg="bg-rose-50" />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader title="Competency profile" subtitle="Average now vs April baseline" />
          <CardBody>
            <CompetencyRadarChart current={current} baseline={baseline} benchmarkName="April baseline" height={250} />
            <div className="mt-2 grid grid-cols-2 gap-2 text-center text-xs">
              {(['LU', 'CU', 'AU', 'CT'] as const).map(d => <div key={d} className="rounded-lg bg-surface-bg p-2">
                <span className="block text-[11px] text-content-secondary">{DIM_LABEL[d]}</span><span className="font-bold">{current[d]}%</span>
                <span className="ml-1 text-emerald-700">+{Math.max(0, current[d] - baseline[d])}</span></div>)}
            </div>
          </CardBody>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader title="Section-by-section comparison" subtitle="Average Language, Concept, Application and Critical Thinking by section" />
          <CardBody><CompetencyBarChart data={classChart} height={300} /></CardBody>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Assessment results by class" subtitle="Average percentage in each assessment round" />
          <CardBody className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs uppercase tracking-wide text-content-secondary"><th className="py-2">Assessment</th>
                {examTable.grades.map(g => <th key={g} className="text-right">Class {g}</th>)}</tr></thead>
              <tbody className="divide-y divide-surface-border">
                {examTable.rounds.map(r => <tr key={r}><td className="py-2"><span className="font-medium">{r}</span><span className="block text-xs text-content-secondary">{formatDay(examTable.roundDate.get(r))}</span></td>
                  {examTable.grades.map(g => { const v = examTable.value(r, g); return <td key={g} className="text-right font-semibold">{v == null ? '—' : `${v}%`}</td>; })}</tr>)}
              </tbody>
            </table>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Half-Yearly Examination by subject" subtitle="Average percentage, September 2026" />
          <CardBody className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs uppercase tracking-wide text-content-secondary"><th className="py-2">Subject</th>
                {examTable.grades.map(g => <th key={g} className="text-right">Class {g}</th>)}</tr></thead>
              <tbody className="divide-y divide-surface-border">
                {subjectTable.subjectIds.map(sid => <tr key={sid}><td className="py-2 font-medium">{subjectName(sid)}</td>
                  {examTable.grades.map(g => { const v = subjectTable.value(sid, g); return <td key={g} className={'text-right font-semibold ' + (v < 55 ? 'text-rose-700' : v >= 70 ? 'text-emerald-700' : '')}>{v}%</td>; })}</tr>)}
              </tbody>
            </table>
          </CardBody>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Teachers" subtitle="Allocation and Half-Yearly class average in their subject" />
          <CardBody className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs uppercase tracking-wide text-content-secondary"><th className="py-2">Teacher</th><th>Subject</th><th>Sections</th><th className="text-right">HY avg</th></tr></thead>
              <tbody className="divide-y divide-surface-border">
                {teacherRows.map(r => <tr key={r.t.id}><td className="py-2"><span className="font-medium">{r.t.name}</span>
                  {multi && <span className="block text-xs text-content-secondary">{schoolName(r.t.schoolId)}</span>}
                  {r.homeroom && <Badge variant="info" size="sm">Class teacher {r.homeroom}</Badge>}</td>
                  <td>{r.subject}</td><td className="text-xs text-content-secondary">{r.classes}</td><td className="text-right font-semibold">{r.avg}%</td></tr>)}
              </tbody>
            </table>
          </CardBody>
        </Card>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Students needing support" subtitle={`${support.length} flagged · lowest overall first`} />
            <CardBody className="max-h-80 space-y-1.5 overflow-y-auto">
              {support.slice(0, 15).map(s => <div key={s.id} className="flex items-center justify-between gap-2 rounded-lg border border-surface-border px-3 py-1.5 text-sm">
                <span className="min-w-0"><span className="font-medium">{s.name}</span> <span className="text-xs text-content-secondary">{s.className}{multi ? ` · ${schoolName(s.schoolId)}` : ''}</span></span>
                <span className="shrink-0 text-xs text-rose-700"><AlertTriangle className="mr-1 inline h-3 w-3" />{s.supportArea} · {s.competencies.overall}%</span></div>)}
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Lost teaching days" subtitle={`${lostDays} day(s) recorded this session`} />
            <CardBody className="space-y-1.5">
              {lost.length === 0 ? <p className="text-sm text-content-secondary">None recorded.</p> : lost.map(d => <div key={d.id} className="flex items-start justify-between gap-2 rounded-lg border border-surface-border px-3 py-1.5 text-sm">
                <span><span className="font-medium">{d.reason}</span><span className="block text-xs text-content-secondary">{d.notes}{multi ? ` · ${schoolName(d.schoolId)}` : ''}</span></span>
                <span className="shrink-0 text-right text-xs"><SchoolIcon className="mr-1 inline h-3 w-3" />{formatDay(d.date)}<span className="block font-semibold text-rose-700">{d.daysLost} day(s)</span></span></div>)}
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
};
