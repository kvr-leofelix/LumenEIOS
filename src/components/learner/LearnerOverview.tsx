import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { CalendarClock, CheckCircle2, FileText, Sparkles, UploadCloud } from 'lucide-react';
import { useData } from '../../context/DataContext';
import { Card, CardBody, CardHeader } from '../common/Card';
import { Badge } from '../common/Badge';
import { CompetencyRadarChart } from '../charts/CompetencyRadarChart';
import { DIM_LABEL, examName, formatDay, grade } from '../../lib/dashboard';
import { useChartInk } from '../../lib/themeColor';

const DIM_COLOURS: Record<string, string> = { LU: '#2563EB', CU: '#7C3AED', AU: '#D97706', CT: '#059669' };

/** Everything a student (or their parent) needs about one learner, from the live workspace. */
export const LearnerOverview: React.FC<{ studentId: string; audience: 'student' | 'parent' }> = ({ studentId, audience }) => {
  const navigate = useNavigate();
  const ink = useChartInk();
  const { students, assessments, assessmentResults, subjects, workspace, snapshots } = useData();
  const student = students.find(s => s.id === studentId);
  const subjectName = (id: string) => subjects.find(s => s.id === id)?.name ?? id;
  const classAvg = workspace?.classAverages?.[student?.classId ?? ''];
  const examAvg = workspace?.assessmentAverages ?? {};
  const mine = assessments.filter(a => a.classId === student?.classId);
  const results = assessmentResults.filter(r => r.studentId === studentId);
  const resultFor = (assessmentId: string) => results.find(r => r.assessmentId === assessmentId);

  const due = mine.filter(a => a.status === 'scheduled').sort((a, b) => a.date.localeCompare(b.date));
  const graded = mine.filter(a => resultFor(a.id)).sort((a, b) => a.date.localeCompare(b.date));

  // Report card: rows = subjects, columns = exam rounds (by exam name), cells = percentage.
  const rounds = useMemo(() => Array.from(new Set(graded.map(a => examName(a.title)))), [graded]);
  const reportSubjects = useMemo(() => Array.from(new Set(graded.map(a => a.subjectId))).sort((a, b) => subjectName(a).localeCompare(subjectName(b))), [graded]); // eslint-disable-line react-hooks/exhaustive-deps
  const cell = (subjectId: string, round: string) => {
    const a = graded.find(x => x.subjectId === subjectId && examName(x.title) === round);
    return a ? { a, r: resultFor(a.id)! } : null;
  };

  const timeline = snapshots.filter(s => s.studentId === studentId).map(s => ({
    label: s.recordedAt ? new Date(s.recordedAt).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : '',
    LU: s.scores.LU, CU: s.scores.CU, AU: s.scores.AU, CT: s.scores.CT, overall: s.scores.overall,
  }));
  const recentFeedback = [...results].filter(r => r.feedback).sort((a, b) => b.submissionDate.localeCompare(a.submissionDate)).slice(0, 4);

  if (!student) return <p role="status" className="text-sm text-content-secondary">Loading…</p>;
  const c = student.competencies;
  const b = student.baselineCompetencies;
  const who = audience === 'student' ? 'your' : `${student.name.split(' ')[0]}'s`;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title="Work due" subtitle={audience === 'student' ? 'Write your answers on paper, take a photo and upload it' : `Assignments ${student.name.split(' ')[0]} needs to submit`}
          action={audience === 'student' ? <button onClick={() => navigate('/student/homework')} className="inline-flex items-center gap-1.5 rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-teal-700"><Sparkles className="h-3.5 w-3.5" />Differentiated homework</button> : undefined} />
        <CardBody className="space-y-2">
          {due.length === 0 ? <p className="text-sm text-content-secondary">Nothing due right now.</p> : due.map(a => {
            const done = resultFor(a.id);
            const uploaded = (workspace?.uploadedCounts?.[a.id] ?? 0) > 0;
            return (
              <div key={a.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-surface-border px-4 py-3">
                <div className="min-w-0">
                  <p className="font-semibold text-navy-900">{examName(a.title)} <span className="font-normal text-content-secondary">· {subjectName(a.subjectId)}</span></p>
                  <p className="text-xs text-content-secondary"><CalendarClock className="mr-1 inline h-3.5 w-3.5" />Due {formatDay(a.date)} · {a.totalMarks} marks · {a.questions.length} questions</p>
                </div>
                {done ? <Badge variant="success" size="sm"><CheckCircle2 className="mr-1 inline h-3 w-3" />Graded {done.marksObtained}/{done.totalMarks}</Badge>
                  : uploaded ? <Badge variant="info" size="sm">Uploaded · awaiting teacher</Badge>
                    : audience === 'student'
                      ? <button onClick={() => navigate(`/upload?assignment=${a.id}`)} className="inline-flex items-center gap-1.5 rounded-lg bg-navy-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-navy-900"><UploadCloud className="h-3.5 w-3.5" />Upload handwritten answers</button>
                      : <Badge variant="warning" size="sm">Not submitted yet</Badge>}
              </div>
            );
          })}
        </CardBody>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader title={audience === 'student' ? 'My competency parameters' : 'Competency parameters'} subtitle="Now vs April baseline" action={<Badge variant="teal" size="sm">Overall {c.overall}%</Badge>} />
          <CardBody>
            <CompetencyRadarChart current={c} baseline={b} benchmarkName="April baseline" height={240} />
          </CardBody>
        </Card>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:col-span-2">
          {(['LU', 'CU', 'AU', 'CT'] as const).map(d => {
            const change = c[d] - b[d];
            const vsClass = classAvg ? c[d] - classAvg[d] : null;
            return (
              <div key={d} className="rounded-2xl border border-surface-border bg-white p-4 shadow-subtle">
                <div className="flex items-baseline justify-between"><p className="text-sm font-semibold" style={{ color: DIM_COLOURS[d] }}>{DIM_LABEL[d]} ({d})</p>
                  <p className="text-2xl font-bold text-navy-900">{c[d]}%</p></div>
                <div className="mt-2 h-2 rounded-full bg-gray-100"><div className="h-2 rounded-full" style={{ width: `${c[d]}%`, background: DIM_COLOURS[d] }} /></div>
                <p className="mt-2 text-xs"><span className={change >= 0 ? 'text-emerald-700' : 'text-rose-700'}>{change >= 0 ? '+' : ''}{change} since April</span>
                  {vsClass != null && <span className="text-content-secondary"> · class average {classAvg![d]}%</span>}</p>
                {student.needsSupport && student.supportArea?.startsWith(DIM_LABEL[d]) && <p className="mt-1 text-xs font-medium text-rose-700">Focus area - extra practice assigned</p>}
              </div>
            );
          })}
        </div>
      </div>

      {timeline.length > 1 && (
        <Card>
          <CardHeader title="Progress over the year" subtitle="Parameters after each assessment round, 2026-27 session" />
          <CardBody>
            <div style={{ width: '100%', height: 260 }}>
              <ResponsiveContainer>
                <LineChart data={timeline} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={ink.grid} />
                  <XAxis dataKey="label" tick={{ fontSize: 11, fill: ink.muted }} stroke={ink.grid} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: ink.muted }} stroke={ink.grid} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  {(['overall', 'LU', 'CU', 'AU', 'CT'] as const).map(k => (
                    <Line key={k} type="monotone" dataKey={k} name={k === 'overall' ? 'Overall' : k} stroke={k === 'overall' ? ink.text : DIM_COLOURS[k]} strokeWidth={k === 'overall' ? 3 : 1.5} dot={k === 'overall'} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader title="Report card" subtitle={`Percentage and CBSE grade in each assessment · class average in grey`} />
        <CardBody className="overflow-x-auto">
          {reportSubjects.length === 0 ? <p className="text-sm text-content-secondary">No graded work yet.</p> : (
            <table className="w-full min-w-[640px] text-sm">
              <thead><tr className="text-left text-xs uppercase tracking-wide text-content-secondary">
                <th className="py-2 pr-3">Subject</th>{rounds.map(r => <th key={r} className="px-2 py-2 text-center">{r}</th>)}</tr></thead>
              <tbody className="divide-y divide-surface-border">
                {reportSubjects.map(sid => (
                  <tr key={sid}>
                    <td className="py-2 pr-3 font-medium">{subjectName(sid)}</td>
                    {rounds.map(round => {
                      const x = cell(sid, round);
                      return <td key={round} className="px-2 py-2 text-center">{x ? <>
                        <span className={'font-semibold ' + (x.r.percentage >= 75 ? 'text-emerald-700' : x.r.percentage >= 50 ? 'text-navy-900' : 'text-rose-700')}>{x.r.percentage}%</span>
                        <span className="ml-1 rounded bg-surface-bg px-1 text-[10px] font-bold">{grade(x.r.percentage)}</span>
                        {examAvg[x.a.id] != null && <span className="block text-[10px] text-content-muted">class {examAvg[x.a.id]}%</span>}
                      </> : <span className="text-content-muted">—</span>}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>

      {recentFeedback.length > 0 && (
        <Card>
          <CardHeader title="Teacher feedback" subtitle={`Latest comments on ${who} work`} />
          <CardBody className="space-y-2">
            {recentFeedback.map(r => {
              const a = mine.find(x => x.id === r.assessmentId);
              return (
                <div key={r.id} className="rounded-xl border border-surface-border px-4 py-3 text-sm">
                  <p className="flex flex-wrap items-center gap-2 font-medium text-navy-900"><FileText className="h-4 w-4 text-content-muted" />{a ? `${examName(a.title)} · ${subjectName(a.subjectId)}` : 'Assessment'}
                    <span className="text-xs font-normal text-content-secondary">{formatDay(r.submissionDate)} · {r.marksObtained}/{r.totalMarks}</span>
                    {r.isScanned && <Badge variant="outline" size="sm">Handwritten</Badge>}</p>
                  <p className="mt-1 text-content-secondary">{r.feedback}</p>
                </div>
              );
            })}
          </CardBody>
        </Card>
      )}
    </div>
  );
};
