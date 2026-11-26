import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { marksLabel } from '../../lib/utils';
import { Link, useSearchParams } from 'react-router-dom';
import {
  BookOpen, CheckCircle2, ClipboardCheck, FilePlus2, Library, PenLine, Plus, Search, Send, Sparkles, Users, UserRound,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { apiClient } from '../../lib/apiClient';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { MathText } from '../../components/common/MathText';
import { AiQuestionGenerator } from './AiQuestionGenerator';
import { KcHomeworkAnalysis } from './KcHomeworkAnalysis';
import {
  BLOOM, COMPETENCY_NAMES, CompetencyTag, Empty, MATH_HINT, MathPreview, Messages, OptionList, OptionsEditor, QUESTION_TYPES,
  ReleasedResult, Section, Segmented, StatCard, StatusBadge, Tabs, answerText, enc, errorText, formatDate, inputClass,
  labelClass, typeLabel, useRunner, useSubjectNames,
} from './ui';

const hw = apiClient.homework;
type Tab = 'create' | 'drafts' | 'assignments' | 'bank';
const TABS: Tab[] = ['create', 'drafts', 'assignments', 'bank'];

/** Teacher / principal / admin homework workspace. Every action calls the live backend. */
export const TeacherWorkspace: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const tab = (TABS.includes(params.get('tab') as Tab) ? params.get('tab') : 'create') as Tab;
  const setTab = useCallback((next: Tab) => setParams(p => { const n = new URLSearchParams(p); n.set('tab', next); return n; }), [setParams]);
  const [openDraftId, setOpenDraftId] = useState('');
  const [openAssignmentId, setOpenAssignmentId] = useState('');
  const [counts, setCounts] = useState({ review: 0, ready: 0, assigned: 0 });
  const subjectName = useSubjectNames();

  const refreshCounts = useCallback(async () => {
    try {
      const [drafts, assignments] = await Promise.all([hw.call<any[]>('/homework/drafts'), hw.call<any[]>('/homework/assignments')]);
      setCounts({
        review: drafts.filter(d => d.status === 'draft').length,
        ready: drafts.filter(d => d.status === 'approved').length,
        assigned: assignments.length,
      });
    } catch { /* counts are a convenience; the panels report their own errors */ }
  }, []);
  useEffect(() => { refreshCounts(); }, [refreshCounts, tab]);

  return <div className="space-y-5">
    <div className="grid gap-3 sm:grid-cols-3">
      <StatCard label="Drafts to review" value={counts.review} tone="amber" icon={<PenLine className="h-4 w-4" />} onClick={() => setTab('drafts')} />
      <StatCard label="Approved, not yet assigned" value={counts.ready} tone="violet" icon={<Send className="h-4 w-4" />} onClick={() => setTab('drafts')} />
      <StatCard label="Homework assigned" value={counts.assigned} tone="emerald" icon={<ClipboardCheck className="h-4 w-4" />} onClick={() => setTab('assignments')} />
    </div>
    <Tabs active={tab} onChange={id => setTab(id as Tab)} tabs={[
      { id: 'create', label: '1. Create homework', hint: 'Personalised from each student’s scores', icon: <FilePlus2 className="h-4 w-4" /> },
      { id: 'drafts', label: '2. Review & assign', hint: 'Check, edit, approve, send', icon: <PenLine className="h-4 w-4" />, count: counts.review + counts.ready },
      { id: 'assignments', label: '3. Submissions & marking', hint: 'Mark answers, release results', icon: <ClipboardCheck className="h-4 w-4" /> },
      { id: 'bank', label: 'Question bank', hint: 'Write, edit or generate questions', icon: <Library className="h-4 w-4" /> },
    ]} />
    {tab === 'create' && <CreateHomework subjectName={subjectName}
      onSaved={id => { setOpenDraftId(id); setTab('drafts'); refreshCounts(); }}
      onGoToBank={() => setTab('bank')} />}
    {tab === 'drafts' && <Drafts subjectName={subjectName} openId={openDraftId} setOpenId={setOpenDraftId} onChanged={refreshCounts}
      onAssigned={id => { setOpenAssignmentId(id); setTab('assignments'); refreshCounts(); }} />}
    {tab === 'assignments' && <Assignments subjectName={subjectName} openId={openAssignmentId} setOpenId={setOpenAssignmentId} />}
    {tab === 'bank' && <QuestionBank subjectName={subjectName} />}
  </div>;
};

type NameFn = (id?: string | null) => string;

function weakest(student: any): string | null {
  const c = student?.competencies;
  if (!c) return null;
  const entries = (['LU', 'CU', 'AU', 'CT'] as const).filter(k => typeof c[k] === 'number').map(k => [k, c[k]] as const);
  if (!entries.length) return null;
  return entries.reduce((a, b) => (b[1] < a[1] ? b : a))[0];
}

// --- 1. Create: one student or a whole class --------------------------------------------------

function CreateHomework({ onSaved, onGoToBank, subjectName }: { onSaved: (draftId: string) => void; onGoToBank: () => void; subjectName: NameFn }) {
  const { currentSchoolId, currentUser } = useAuth();
  const [searchParams] = useSearchParams();
  const { busy, error, notice, run } = useRunner();
  const [mode, setMode] = useState<'student' | 'class'>('student');
  const [classes, setClasses] = useState<any[]>([]); const [classId, setClassId] = useState('');
  const [rosterLoaded, setRosterLoaded] = useState(false);
  // The teacher's own classes (class_teacher_id) first; access itself is school-wide on the server.
  const sortedClasses = useMemo(() => [...classes].sort((a, b) =>
    Number(b.class_teacher_id === currentUser?.id) - Number(a.class_teacher_id === currentUser?.id) || a.name.localeCompare(b.name)),
  [classes, currentUser?.id]);
  const [students, setStudents] = useState<any[]>([]); const [studentId, setStudentId] = useState('');
  const [subjectId, setSubjectId] = useState('');
  const [gap, setGap] = useState<any>(null);
  const [count, setCount] = useState(5); const [maxMarks, setMaxMarks] = useState('');
  const [includeAI, setIncludeAI] = useState(false);
  const [preview, setPreview] = useState<any>(null);
  const [prefillDone, setPrefillDone] = useState(false);
  const [topics, setTopics] = useState<string[]>([]);           // chosen; empty = all topics
  const [bankTopics, setBankTopics] = useState<{ topic: string; count: number; by_competency: Record<string, number> }[]>([]);
  const [untagged, setUntagged] = useState(0);

  // Topics offered for the chosen subject come from the school's question bank.
  useEffect(() => {
    let active = true;
    setTopics([]); setBankTopics([]); setUntagged(0);
    if (!subjectId) return;
    apiClient.assessments.bankTopics(subjectId).then(res => {
      if (!active) return;
      setBankTopics(res.topics); setUntagged(res.untagged);
    }).catch(() => undefined);
    return () => { active = false; };
  }, [subjectId]);

  useEffect(() => { let active = true;
    hw.call<any[]>(`/schools/${enc(currentSchoolId)}/classes`).then(rows => { if (active) setClasses(rows); })
      .catch(() => { if (active) setClasses([]); });
    return () => { active = false; }; }, [currentSchoolId]);

  // Deep-link from My Classes: /teacher/homework?classId=…&studentId=…
  useEffect(() => {
    if (prefillDone || classes.length === 0) return;
    const wantedClass = searchParams.get('classId') || '';
    const wantedStudent = searchParams.get('studentId') || '';
    if (!wantedClass && !wantedStudent) { setPrefillDone(true); return; }
    const targetClass = wantedClass || classes.find(c => (c.subject_ids_json || []).length)?.id || classes[0]?.id || '';
    if (!targetClass) { setPrefillDone(true); return; }
    let active = true;
    run(async () => {
      setClassId(targetClass); setStudentId(''); setStudents([]); setGap(null); setPreview(null); setRosterLoaded(false);
      setSubjectId(classes.find(c => c.id === targetClass)?.subject_ids_json?.[0] ?? '');
      const roster = await hw.call<any[]>(`/classes/${enc(targetClass)}/students`);
      if (!active) return;
      setStudents(roster); setRosterLoaded(true);
      if (wantedStudent && roster.some((s: any) => s.id === wantedStudent)) {
        setStudentId(wantedStudent);
        setGap(await hw.call(`/students/${enc(wantedStudent)}/homework/gap-analysis`));
      } else if (!wantedStudent) setMode('class');
      setPrefillDone(true);
    });
    return () => { active = false; };
  }, [classes, searchParams, prefillDone, run]);

  const selectedClass = classes.find(c => c.id === classId);
  const chooseClass = (id: string) => run(async () => {
    setClassId(id); setStudentId(''); setStudents([]); setGap(null); setPreview(null); setRosterLoaded(false);
    setSubjectId(classes.find(c => c.id === id)?.subject_ids_json?.[0] ?? '');
    if (id) { setStudents(await hw.call<any[]>(`/classes/${enc(id)}/students`)); setRosterLoaded(true); }
  });
  const chooseStudent = (id: string) => run(async () => {
    setStudentId(id); setGap(null); setPreview(null);
    if (id) setGap(await hw.call(`/students/${enc(id)}/homework/gap-analysis`));
  });
  const request = () => ({
    subject_id: subjectId, max_questions: count, include_ai_generated: includeAI,
    ...(maxMarks ? { max_total_marks: Number(maxMarks) } : {}),
    ...(topics.length ? { topics } : {}),
  });
  const student = students.find(s => s.id === studentId);

  const settings = <>
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="block"><span className={labelClass}>Class</span>
        <select aria-label="Class" className={inputClass} value={classId} disabled={busy} onChange={e => chooseClass(e.target.value)}>
          <option value="">Choose a class</option>
          {sortedClasses.map(c => <option key={c.id} value={c.id}>
            {c.name} ({c.student_count} {c.student_count === 1 ? 'student' : 'students'}){c.class_teacher_id === currentUser?.id ? ' - your class' : ''}</option>)}
        </select></label>
      <label className="block"><span className={labelClass}>Subject</span>
        <select aria-label="Subject" className={inputClass} value={subjectId} disabled={busy || !selectedClass}
          onChange={e => { setSubjectId(e.target.value); setPreview(null); }}>
          {!selectedClass && <option value="">Choose a class first</option>}
          {(selectedClass?.subject_ids_json ?? []).map((id: string) => <option key={id} value={id}>{subjectName(id)}</option>)}
        </select></label>
    </div>
    {subjectId && <TopicPicker available={bankTopics} untagged={untagged} chosen={topics} disabled={busy}
      onChange={next => { setTopics(next); setPreview(null); }} onGoToBank={onGoToBank} />}
    {mode === 'student' && <label className="block"><span className={labelClass}>Student</span>
      <select aria-label="Student" className={inputClass} value={studentId} disabled={busy || !classId || students.length === 0} onChange={e => chooseStudent(e.target.value)}>
        <option value="">{!classId ? 'Choose a class first' : rosterLoaded && students.length === 0 ? 'No students enrolled' : 'Choose a student'}</option>
        {students.map(s => <option key={s.id} value={s.id}>{s.roll_no}. {s.name}</option>)}
      </select></label>}
    {classId && rosterLoaded && students.length === 0 &&
      <p role="note" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">No students are enrolled in {selectedClass?.name}. Choose another class.</p>}
    <div className="grid grid-cols-2 gap-3">
      <label className="block"><span className={labelClass}>Questions per student</span>
        <input aria-label="Question count" type="number" min={1} max={50} className={inputClass} value={count} disabled={busy}
          onChange={e => { setCount(Math.max(1, Number(e.target.value) || 1)); setPreview(null); }} /></label>
      <label className="block"><span className={labelClass}>Max total marks <span className="normal-case">(optional)</span></span>
        <input aria-label="Max total marks" type="number" min={1} className={inputClass} value={maxMarks} disabled={busy} placeholder="No limit"
          onChange={e => { setMaxMarks(e.target.value); setPreview(null); }} /></label>
    </div>
    <label className="flex items-start gap-2 rounded-lg bg-surface-bg/60 px-3 py-2 text-sm"><input type="checkbox" className="mt-0.5" checked={includeAI} disabled={busy}
      onChange={e => { setIncludeAI(e.target.checked); setPreview(null); }} />
      <span>Include AI-generated questions <span className="text-content-secondary">(only ones a teacher already approved into the bank)</span></span></label>
  </>;

  return <div className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-teal-100 bg-gradient-to-r from-teal-50 to-white px-5 py-4">
      <div>
        <p className="text-sm font-semibold text-navy-900">How it works</p>
        <p className="text-sm text-content-secondary">We read each student’s competency scores, find their weakest areas and pick matching questions from your school’s question bank. You review every draft before anything reaches a student.</p>
      </div>
      <Segmented label="Create for" value={mode} onChange={v => { setMode(v as 'student' | 'class'); setPreview(null); }}
        options={[['student', 'One student'], ['class', 'Whole class']]} />
    </div>

    {mode === 'class'
      ? <ClassBatch settings={settings} classId={classId} className={selectedClass?.name} students={students} subjectId={subjectId}
          studentId={studentId} subjectName={subjectName} request={request} onDone={onSaved} busyOuter={busy} error={error} notice={notice} />
      : <div className="space-y-5">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <Section title={<span className="flex items-center gap-2"><UserRound className="h-4 w-4 text-teal-600" />Student and settings</span>}
            subtitle="Questions come from the school question bank, aimed at this student’s weakest competencies.">
            <Messages error={error} notice={notice} />
            {classes.length === 0 ? <Empty>No classes are visible in school {currentSchoolId}.</Empty> : <>
              {settings}
              <Button variant="teal" className="w-full" disabled={busy || !(studentId && subjectId && count >= 1)} loading={busy && !!studentId} onClick={() => run(async () => {
                setPreview(await hw.call(`/students/${enc(studentId)}/homework/preview`, 'POST', request()));
              })}>Preview homework</Button>
            </>}
            {gap && <GapPanel gap={gap} name={student?.name} />}
          </Section>

          <Section title="Homework preview" subtitle="Existing bank questions chosen for this student. Nothing is saved until you save the draft.">
            {!preview ? <Empty icon={<BookOpen className="h-6 w-6" />}>Choose a student and subject, then press <strong>Preview homework</strong>.</Empty> : <>
              <p className="rounded-lg bg-navy-50 px-3 py-2 text-sm text-navy-800">{preview.rationale.summary}</p>
              <div className="flex flex-wrap items-center gap-2 text-sm text-content-secondary">
                <Badge variant="outline" size="sm">{preview.question_count} questions</Badge>
                <Badge variant="outline" size="sm">{preview.total_marks} marks</Badge>
                {(preview.rationale.targeted_competencies ?? []).map((c: string) => <CompetencyTag key={c} code={c} long />)}
                {preview.shortfall > 0 && <span className="text-amber-700">{preview.shortfall} fewer than requested - the bank needs more matching questions.</span>}
              </div>
              {preview.items.length === 0
                ? <Empty>The question bank has no matching {subjectName(subjectId)} questions in this school.{' '}
                    <button type="button" className="font-medium text-teal-700 underline" onClick={onGoToBank}>Add questions to the bank</button></Empty>
                : <QuestionTable items={preview.items} />}
              {preview.notes?.length > 0 && <details className="text-xs text-content-secondary"><summary className="cursor-pointer">Why these questions?</summary>
                <ul className="ml-4 mt-1 list-disc">{preview.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul></details>}
              <Button variant="primary" disabled={busy || preview.items.length === 0} onClick={() => run(async () => {
                const saved = await hw.call(`/students/${enc(studentId)}/homework/drafts`, 'POST',
                  { ...request(), expected_question_ids: preview.items.map((q: any) => q.question_id) });
                setPreview(null); onSaved(saved.id);
              })}>Save draft for review</Button>
            </>}
          </Section>
        </div>
        {classId && subjectId && (
          <KcHomeworkAnalysis classId={classId} subjectId={subjectId} studentId={studentId} />
        )}
      </div>}
  </div>;
}

/** Whole-class mode: one personalised draft per selected student, saved in one go. */
function ClassBatch({ settings, classId, className, students, subjectId, studentId, subjectName, request, onDone, busyOuter, error, notice }: {
  settings: React.ReactNode; classId: string; className?: string; students: any[]; subjectId: string; studentId: string; subjectName: NameFn;
  request: () => any; onDone: (draftId: string) => void; busyOuter: boolean; error: string; notice: string;
}) {
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [results, setResults] = useState<Record<string, { ok: boolean; text: string; draftId?: string }>>({});
  const [running, setRunning] = useState(false);
  useEffect(() => { setPicked(Object.fromEntries(students.map(s => [s.id, true]))); setResults({}); }, [students]);
  const chosen = students.filter(s => picked[s.id]);
  const done = Object.keys(results).length;

  const build = async () => {
    setRunning(true); setResults({});
    for (const s of chosen) {
      try {
        const saved = await hw.call<any>(`/students/${enc(s.id)}/homework/drafts`, 'POST', request());
        setResults(r => ({ ...r, [s.id]: { ok: true, draftId: saved.id, text: `${saved.question_count} questions · ${saved.total_marks} marks` } }));
      } catch (ex) {
        setResults(r => ({ ...r, [s.id]: { ok: false, text: errorText(ex) } }));
      }
    }
    setRunning(false);
  };
  const okCount = Object.values(results).filter(r => r.ok).length;
  const firstDraft = Object.values(results).find(r => r.draftId)?.draftId;

  return <div className="space-y-5">
  <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
    <Section title={<span className="flex items-center gap-2"><Users className="h-4 w-4 text-teal-600" />Class and settings</span>}
      subtitle="Every student gets their own set of questions, picked for their own weakest competencies.">
      <Messages error={error} notice={notice} />
      {settings}
    </Section>
    <Section title={className ? `${className} roster` : 'Roster'}
      subtitle={subjectId ? `Personalised ${subjectName(subjectId)} homework` : 'Choose a class and subject'}
      action={students.length > 0 && <div className="flex gap-2 text-xs">
        <button type="button" className="font-medium text-teal-700 hover:underline" onClick={() => setPicked(Object.fromEntries(students.map(s => [s.id, true])))}>Select all</button>
        <button type="button" className="font-medium text-content-secondary hover:underline" onClick={() => setPicked({})}>Clear</button>
      </div>}>
      {!classId ? <Empty icon={<Users className="h-6 w-6" />}>Choose a class to see its students.</Empty>
        : students.length === 0 ? <Empty>No students enrolled.</Empty> : <>
          <div className="max-h-[26rem] overflow-y-auto rounded-xl border border-surface-border">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface-bg text-left text-xs uppercase tracking-wide text-content-secondary">
                <tr><th className="w-8 px-3 py-2"></th><th className="px-3 py-2">Student</th><th className="px-3 py-2">Overall</th><th className="px-3 py-2">Focus area</th><th className="px-3 py-2">Draft</th></tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                {students.map(s => {
                  const w = weakest(s); const r = results[s.id];
                  return <tr key={s.id} className={picked[s.id] ? '' : 'opacity-60'}>
                    <td className="px-3 py-2"><input type="checkbox" aria-label={`Include ${s.name}`} checked={!!picked[s.id]} disabled={running}
                      onChange={e => setPicked(p => ({ ...p, [s.id]: e.target.checked }))} /></td>
                    <td className="px-3 py-2"><span className="font-medium">{s.name}</span> <span className="text-xs text-content-secondary">#{s.roll_no}</span></td>
                    <td className="px-3 py-2 tabular-nums">{s.competencies?.overall ?? '-'}</td>
                    <td className="px-3 py-2">{w ? <CompetencyTag code={w} long /> : <span className="text-xs text-content-secondary">No scores yet</span>}</td>
                    <td className="px-3 py-2 text-xs">{r ? <span className={r.ok ? 'text-emerald-700' : 'text-rose-700'}>{r.ok ? '✓ ' : '✗ '}{r.text}</span>
                      : running && picked[s.id] ? <span className="text-content-secondary">Waiting…</span> : null}</td>
                  </tr>;
                })}
              </tbody>
            </table>
          </div>
          {running && <div role="status" className="space-y-1">
            <p className="text-sm text-content-secondary">Building drafts… {done} of {chosen.length}</p>
            <div className="h-2 rounded-full bg-gray-100"><div className="h-2 rounded-full bg-teal-500 transition-all" style={{ width: `${chosen.length ? (done / chosen.length) * 100 : 0}%` }} /></div>
          </div>}
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="teal" icon={<Sparkles className="h-4 w-4" />} disabled={running || busyOuter || !subjectId || chosen.length === 0} loading={running} onClick={build}>
              Build personalised homework for {chosen.length} student{chosen.length === 1 ? '' : 's'}</Button>
            {!running && okCount > 0 && firstDraft && <Button variant="primary" onClick={() => onDone(firstDraft)}>Review {okCount} draft{okCount === 1 ? '' : 's'}</Button>}
          </div>
          <p className="text-xs text-content-secondary">Drafts are saved for your review - nothing is sent to students until you approve and assign.</p>
        </>}
    </Section>
  </div>
  {classId && subjectId && (
    <KcHomeworkAnalysis classId={classId} subjectId={subjectId} studentId={studentId} />
  )}
  </div>;
}

/** Choose which chapter(s)/topic(s) the homework is drawn from. No selection = the whole subject. */
function TopicPicker({ available, untagged, chosen, disabled, onChange, onGoToBank }: {
  available: { topic: string; count: number; by_competency: Record<string, number> }[]; untagged: number;
  chosen: string[]; disabled?: boolean; onChange: (topics: string[]) => void; onGoToBank: () => void;
}) {
  const toggle = (t: string) => onChange(chosen.includes(t) ? chosen.filter(x => x !== t) : [...chosen, t]);
  const total = available.filter(t => chosen.includes(t.topic)).reduce((n, t) => n + t.count, 0);
  return <fieldset className="space-y-2" aria-label="Topics">
    <legend className={labelClass}>Topic / chapter</legend>
    {available.length === 0
      ? <p className="rounded-lg border border-dashed border-surface-border px-3 py-2 text-sm text-content-secondary">
          No topics are tagged in this subject’s question bank yet, so homework can come from any question.{' '}
          <button type="button" className="font-medium text-teal-700 underline" onClick={onGoToBank}>Tag questions with a topic</button>
        </p>
      : <>
        <div className="flex flex-wrap gap-1.5">
          <button type="button" disabled={disabled} aria-pressed={chosen.length === 0} onClick={() => onChange([])}
            className={'rounded-full border px-3 py-1 text-sm transition ' + (chosen.length === 0 ? 'border-navy-800 bg-navy-800 text-white' : 'border-surface-border bg-white hover:border-teal-300')}>
            All topics</button>
          {available.map(t => {
            const on = chosen.includes(t.topic);
            return <button key={t.topic} type="button" disabled={disabled} aria-pressed={on} onClick={() => toggle(t.topic)}
              title={Object.entries(t.by_competency).map(([c, n]) => `${c}: ${n}`).join(' · ')}
              className={'rounded-full border px-3 py-1 text-sm transition ' + (on ? 'border-teal-600 bg-teal-600 text-white' : 'border-surface-border bg-white hover:border-teal-300')}>
              {t.topic} <span className={on ? 'text-white/80' : 'text-content-secondary'}>({t.count})</span></button>;
          })}
        </div>
        <p className="text-xs text-content-secondary">
          {chosen.length === 0
            ? `Questions can come from any topic${untagged ? `, including ${untagged} untagged question${untagged === 1 ? '' : 's'}` : ''}.`
            : `${total} question${total === 1 ? '' : 's'} in ${chosen.length} topic${chosen.length === 1 ? '' : 's'}; each student still gets the ones that target their weakest competencies.`}
        </p>
      </>}
  </fieldset>;
}

function GapPanel({ gap, name }: { gap: any; name?: string }) {
  return <div className="rounded-xl border border-surface-border bg-surface-bg/30 p-3">
    <h3 className="text-sm font-semibold">Competency gap analysis{name ? ` - ${name}` : ''}</h3>
    <p className="text-xs text-content-secondary">Lowest score first · source: {gap.source}</p>
    <ul className="mt-2 space-y-2">
      {gap.ranked.map((g: any) => {
        const weak = gap.weakest.includes(g.competency);
        return <li key={g.competency} className="text-sm">
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5"><CompetencyTag code={g.competency} /> {COMPETENCY_NAMES[g.competency]}
              {weak && <span className="rounded bg-rose-100 px-1.5 text-[10px] font-bold uppercase text-rose-700">focus</span>}</span>
            <span className="tabular-nums font-medium">{g.score}{g.change_from_baseline != null &&
              <span className={'ml-1 text-xs ' + (g.change_from_baseline >= 0 ? 'text-emerald-700' : 'text-rose-700')}>({g.change_from_baseline >= 0 ? '+' : ''}{g.change_from_baseline})</span>}</span>
          </div>
          <div className="mt-1 h-1.5 rounded-full bg-gray-100"><div className={'h-1.5 rounded-full ' + (weak ? 'bg-rose-400' : 'bg-teal-500')} style={{ width: `${Math.max(0, Math.min(100, g.score))}%` }} /></div>
        </li>;
      })}
    </ul>
    {gap.notes?.length > 0 && <ul className="mt-2 ml-4 list-disc text-xs text-content-secondary">{gap.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul>}
  </div>;
}

function QuestionTable({ items, onRemove, disabled, showKey }: { items: any[]; onRemove?: (position: number) => void; disabled?: boolean; showKey?: boolean }) {
  return <ol className="space-y-2">
    {items.map(q => <li key={q.position} className="rounded-xl border border-surface-border bg-white p-3">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm"><span className="mr-1 font-semibold text-navy-800">{q.position}.</span><MathText text={q.text} /></p>
        {onRemove && <Button size="sm" variant="ghost" disabled={disabled} onClick={() => onRemove(q.position)}>Remove</Button>}
      </div>
      <p className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-content-secondary">
        <CompetencyTag code={q.competency} /> <span>{q.bloom_level}</span> <span>·</span> <span>{typeLabel(q.type)}</span> <span>·</span> <span>{marksLabel(q.marks)}</span>
        {q.is_ai_generated && <Badge variant="warning" size="sm">AI-generated</Badge>}
      </p>
      {q.options?.length > 0 && <OptionList options={q.options} correct={showKey ? q.correct_answer : undefined} />}
    </li>)}
  </ol>;
}

// --- 2. Drafts: review, edit (remove items), approve / reject / reopen, assign -------------

function Drafts({ openId, setOpenId, onAssigned, onChanged, subjectName }: {
  openId: string; setOpenId: (id: string) => void; onAssigned: (id: string) => void; onChanged: () => void; subjectName: NameFn;
}) {
  const { busy, error, notice, run } = useRunner();
  const [drafts, setDrafts] = useState<any[]>([]);
  const [filter, setFilter] = useState('');
  const [query, setQuery] = useState('');
  const [draft, setDraft] = useState<any>(null);
  const [note, setNote] = useState(''); const [due, setDue] = useState(''); const [bulkDue, setBulkDue] = useState('');

  const refresh = async () => { setDrafts(await hw.call<any[]>('/homework/drafts')); onChanged(); };
  useEffect(() => { run(refresh); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (openId) run(async () => setDraft(await hw.call(`/homework/drafts/${enc(openId)}`))); else setDraft(null); }, [openId]); // eslint-disable-line react-hooks/exhaustive-deps

  const label = (d: any) => `${d.student_name ?? d.student_id} - ${d.subject_name ?? subjectName(d.subject_id)}`;
  const shown = drafts.filter(d => (!filter || d.status === filter) && (!query || label(d).toLowerCase().includes(query.toLowerCase())));
  const toReview = drafts.filter(d => d.status === 'draft');
  const approved = drafts.filter(d => d.status === 'approved');

  const act = (path: string, method = 'POST', body?: unknown, message?: string) => run(async () => {
    setDraft(await hw.call(`/homework/drafts/${enc(draft.id)}${path}`, method, body)); setNote(''); await refresh(); return message;
  });
  const bulk = (rows: any[], path: string, body: (d: any) => unknown, verb: string) => run(async () => {
    let ok = 0; const failed: string[] = [];
    for (const d of rows) {
      try { await hw.call(`/homework/drafts/${enc(d.id)}${path}`, 'POST', body(d)); ok++; }
      catch (ex) { failed.push(`${d.student_name ?? d.student_id}: ${errorText(ex)}`); }
    }
    await refresh();
    if (draft) setDraft(await hw.call(`/homework/drafts/${enc(draft.id)}`));
    if (failed.length) throw new Error(`${verb} ${ok}; ${failed.length} failed - ${failed.join('; ')}`);
    return `${verb} ${ok} draft${ok === 1 ? '' : 's'}.`;
  });

  return <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
    <Section title="Homework drafts" subtitle={`${toReview.length} to review · ${approved.length} ready to assign`}>
      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-[10rem] flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-content-secondary" />
          <input aria-label="Search drafts" placeholder="Search student or subject" className={inputClass + ' pl-8'} value={query} onChange={e => setQuery(e.target.value)} />
        </div>
        <select aria-label="Draft status filter" className={inputClass + ' w-auto'} value={filter} onChange={e => setFilter(e.target.value)}>
          <option value="">All statuses</option>
          {[['draft', 'Needs review'], ['approved', 'Approved'], ['rejected', 'Rejected'], ['assigned', 'Assigned']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      {(toReview.length > 1 || approved.length > 1) && <div className="space-y-2 rounded-xl border border-violet-100 bg-violet-50/40 p-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-violet-900">Bulk actions</p>
        {toReview.length > 1 && <Button size="sm" variant="outline" disabled={busy} onClick={() => {
          if (window.confirm(`Approve all ${toReview.length} drafts that need review? Open a draft first if you want to check it.`))
            bulk(toReview, '/approve', () => undefined, 'Approved');
        }}>Approve all {toReview.length} drafts</Button>}
        {approved.length > 1 && <div className="flex flex-wrap items-end gap-2">
          <label><span className={labelClass}>Due date for all</span>
            <input aria-label="Bulk due date" type="datetime-local" className={inputClass} value={bulkDue} onChange={e => setBulkDue(e.target.value)} /></label>
          <Button size="sm" variant="primary" disabled={busy} onClick={() => {
            if (window.confirm(`Assign all ${approved.length} approved drafts to their students?`))
              bulk(approved, '/assign', () => (bulkDue ? { due_at: new Date(bulkDue).toISOString() } : undefined), 'Assigned');
          }}>Assign all {approved.length} approved</Button>
        </div>}
      </div>}
      {shown.length === 0 ? <Empty>{drafts.length === 0 ? 'No drafts yet. Create one in step 1.' : 'No drafts match.'}</Empty> :
        <ul className="max-h-[32rem] space-y-1.5 overflow-y-auto">{shown.map(d => <li key={d.id}>
          <button className={'w-full rounded-xl border px-3 py-2.5 text-left transition hover:border-teal-300 ' + (d.id === openId ? 'border-teal-400 bg-teal-50' : 'border-surface-border bg-white')} onClick={() => setOpenId(d.id)}>
            <div className="flex items-center justify-between gap-2"><span className="text-sm font-medium">{label(d)}</span><StatusBadge status={d.status} /></div>
            <p className="text-xs text-content-secondary">{d.question_count} questions · {d.total_marks} marks · updated {formatDate(d.updated_at)}</p>
          </button></li>)}</ul>}
    </Section>

    <Section title={draft ? <span className="flex items-center gap-2">Review draft <StatusBadge status={draft.status} /></span> : 'Review draft'}
      subtitle={draft ? `${drafts.find(d => d.id === draft.id)?.student_name ?? draft.student_id} · ${subjectName(draft.subject_id)} · ${draft.question_count} questions, ${draft.total_marks} marks` : undefined}>
      <Messages error={error} notice={notice} />
      {!draft ? <Empty icon={<PenLine className="h-6 w-6" />}>Select a draft on the left to review it.</Empty> : <>
        <p className="rounded-lg bg-navy-50 px-3 py-2 text-sm text-navy-800">{draft.rationale.summary}</p>
        {draft.review_note && <p className="text-sm">Review note: <em>{draft.review_note}</em></p>}
        <QuestionTable items={draft.items} disabled={busy} showKey
          onRemove={draft.status === 'draft' && draft.items.length > 1 ? position => {
            if (window.confirm(`Remove question ${position} from this draft?`)) act(`/items/${position}`, 'DELETE', undefined, `Question ${position} removed.`);
          } : undefined} />
        {draft.status === 'draft' && <div className="space-y-2 border-t border-surface-border pt-3">
          <label className="block"><span className={labelClass}>Review note (optional)</span>
            <textarea aria-label="Review note" className={inputClass} maxLength={2000} value={note} onChange={e => setNote(e.target.value)} /></label>
          <div className="flex flex-wrap gap-2">
            <Button variant="teal" icon={<CheckCircle2 className="h-4 w-4" />} disabled={busy} onClick={() => act('/approve', 'POST', note ? { note } : undefined, 'Draft approved. You can now assign it.')}>Approve</Button>
            <Button variant="outline" disabled={busy} onClick={() => act('/reject', 'POST', note ? { note } : undefined, 'Draft rejected.')}>Reject</Button>
          </div></div>}
        {draft.status === 'rejected' && <Button variant="outline" disabled={busy} onClick={() => act('/reopen', 'POST', undefined, 'Draft reopened for editing.')}>Reopen for editing</Button>}
        {draft.status === 'approved' && <div className="flex flex-wrap items-end gap-2 border-t border-surface-border pt-3">
          <label className="block"><span className={labelClass}>Due date (optional)</span>
            <input aria-label="Due date" type="datetime-local" className={inputClass} value={due} onChange={e => setDue(e.target.value)} /></label>
          <Button variant="primary" icon={<Send className="h-4 w-4" />} disabled={busy} onClick={() => run(async () => {
            const body = due ? { due_at: new Date(due).toISOString() } : undefined;
            const assignment = await hw.call(`/homework/drafts/${enc(draft.id)}/assign`, 'POST', body);
            setDue(''); await refresh(); onAssigned(assignment.id);
          })}>Assign to student</Button></div>}
        {draft.status === 'assigned' && <p className="text-sm text-content-secondary">This draft has been assigned. See step 3 for submissions.</p>}
      </>}
    </Section>
  </div>;
}

// --- 3. Assignments: submission overview, answers, manual evaluation, release --------------

function Assignments({ openId, setOpenId, subjectName }: { openId: string; setOpenId: (id: string) => void; subjectName: NameFn }) {
  const { busy, error, run } = useRunner();
  const [assignments, setAssignments] = useState<any[]>([]);
  const [query, setQuery] = useState('');
  const refresh = async () => setAssignments(await hw.call<any[]>('/homework/assignments'));
  useEffect(() => { run(refresh); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const selected = assignments.find(a => a.id === openId);
  const label = (a: any) => `${a.student_name ?? a.student_id} - ${a.subject_name ?? subjectName(a.subject_id)}`;
  const shown = assignments.filter(a => !query || label(a).toLowerCase().includes(query.toLowerCase()));

  return <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
    <Section title="Assigned homework" subtitle={`${assignments.length} assignment${assignments.length === 1 ? '' : 's'}`}
      action={<Button size="sm" variant="outline" disabled={busy} onClick={() => run(refresh)}>Refresh</Button>}>
      <Messages error={error} />
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-content-secondary" />
        <input aria-label="Search assignments" placeholder="Search student or subject" className={inputClass + ' pl-8'} value={query} onChange={e => setQuery(e.target.value)} />
      </div>
      {shown.length === 0 ? <Empty>{assignments.length === 0 ? 'No homework has been assigned yet.' : 'No assignments match.'}</Empty> :
        <ul className="max-h-[32rem] space-y-1.5 overflow-y-auto">{shown.map(a => <li key={a.id}>
          <button className={'w-full rounded-xl border px-3 py-2.5 text-left transition hover:border-teal-300 ' + (a.id === openId ? 'border-teal-400 bg-teal-50' : 'border-surface-border bg-white')} onClick={() => setOpenId(a.id)}>
            <p className="text-sm font-medium">{label(a)}</p>
            <p className="text-xs text-content-secondary">{a.question_count} questions · {a.total_marks} marks · due {formatDate(a.due_at)}</p>
          </button></li>)}</ul>}
    </Section>
    {selected ? <AssignmentDetail key={selected.id} assignment={selected} subjectName={subjectName} /> :
      <Section title="Submission and marking"><Empty icon={<ClipboardCheck className="h-6 w-6" />}>Select an assignment to see the student’s answers.</Empty></Section>}
  </div>;
}

function AssignmentDetail({ assignment, subjectName }: { assignment: any; subjectName: NameFn }) {
  const { busy, error, notice, run } = useRunner();
  const [overview, setOverview] = useState<any>(null);
  const [submission, setSubmission] = useState<any>(null);
  const [evaluation, setEvaluation] = useState<any>(null);
  const base = `/homework/assignments/${enc(assignment.id)}`;
  const load = async () => {
    const o = await hw.call(`${base}/submissions`); setOverview(o);
    const row = o.students[0];
    if (row && row.status !== 'not_started') setSubmission(await hw.call(`${base}/submissions/${enc(row.student_id)}`));
    if (row?.status === 'submitted') {
      try { setEvaluation(await hw.call(`${base}/evaluation`)); } catch { setEvaluation(null); }
    }
  };
  useEffect(() => { run(load); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const row = overview?.students?.[0];

  return <Section title={`${row?.student_name ?? assignment.student_name ?? assignment.student_id} - ${overview?.subject_name ?? subjectName(assignment.subject_id)}`}
    subtitle={<>Due {formatDate(assignment.due_at)} · <span className="text-content-secondary/80">ID <code className="select-all">{assignment.id}</code></span></>}
    action={<Button size="sm" variant="outline" disabled={busy} onClick={() => run(load)}>Reload</Button>}>
    <Messages error={error} notice={notice} />
    {row && <div className="flex flex-wrap items-center gap-3 rounded-lg bg-surface-bg/60 px-3 py-2 text-sm">
      <StatusBadge status={row.status} /> <span>{row.answered_count} / {row.question_count} answered</span>
      {row.submitted_at && <span>Submitted {formatDate(row.submitted_at)}</span>}
      {row.is_late && <Badge variant="warning" size="sm">Late</Badge>}
    </div>}
    {row?.status !== 'submitted' && <Empty>Marking opens after the student submits. {submission ? 'Their saved progress is shown below.' : ''}</Empty>}
    {submission && !evaluation && <ol className="space-y-2">{submission.questions.map((q: any) => <li key={q.position} className="rounded-xl border border-surface-border p-3 text-sm">
      <p className="font-medium">{q.position}. <MathText text={q.text} /></p><p className="mt-1 text-content-secondary">Answer: <MathText text={answerText(q)} /></p></li>)}</ol>}
    {row?.status === 'submitted' && !evaluation &&
      <Button variant="teal" disabled={busy} onClick={() => run(async () => setEvaluation(await hw.call(`${base}/evaluation`, 'POST')))}>Start marking</Button>}
    {evaluation && <Evaluation assignmentId={assignment.id} base={base} evaluation={evaluation} setEvaluation={setEvaluation} />}
  </Section>;
}

type SuggestionDecision = 'accepted' | 'rejected' | null;

function suggestionMap(payload: any | null): Record<number, any> {
  if (!payload?.items) return {};
  return Object.fromEntries(payload.items.map((item: any) => [item.position, item]));
}

function Evaluation({
  assignmentId, base, evaluation, setEvaluation,
}: {
  assignmentId: string; base: string; evaluation: any; setEvaluation: (e: any) => void;
}) {
  const { busy, error, notice, run, setError, setNotice } = useRunner();
  const fromEvaluation = (e: any) => ({
    marks: Object.fromEntries(e.items.map((q: any) => [q.position, q.awarded_marks == null ? '' : String(q.awarded_marks)])) as Record<number, string>,
    feedback: Object.fromEntries(e.items.map((q: any) => [q.position, q.feedback ?? ''])) as Record<number, string>,
  });
  const [form, setForm] = useState(() => fromEvaluation(evaluation));
  const [suggestions, setSuggestions] = useState<Record<number, any>>({});
  const [decisions, setDecisions] = useState<Record<number, SuggestionDecision>>({});
  const [aiBusy, setAiBusy] = useState(false);
  // Open-ended answers are marked by the local Qwen model (works offline) or Gemini; MCQs use the answer key.
  const [aiModel, setAiModel] = useState<'qwen' | 'gemini'>('qwen');
  const aiModelName = aiModel === 'qwen' ? 'Qwen' : 'Gemini';
  const [aiError, setAiError] = useState('');
  const [aiNotice, setAiNotice] = useState('');
  const update = (e: any) => { setEvaluation(e); setForm(fromEvaluation(e)); };
  const editable = evaluation.status === 'pending';
  const runningTotal = useMemo(() => Object.values(form.marks).reduce((sum, v) => sum + (v === '' ? 0 : Number(v) || 0), 0), [form]);
  const dirty = evaluation.items.some((q: any) => (form.marks[q.position] ?? '') !== (q.awarded_marks == null ? '' : String(q.awarded_marks))
    || (form.feedback[q.position] ?? '') !== (q.feedback ?? ''));
  const hasSuggestions = Object.keys(suggestions).length > 0;
  const attentionCount = Object.values(suggestions).filter((s: any) => s.needs_teacher_attention || s.confidence === 'low').length;
  const pendingSuggestions = evaluation.items.filter((q: any) => suggestions[q.position] && !decisions[q.position]);

  useEffect(() => {
    if (!editable) return;
    let active = true;
    hw.aiSuggestions(assignmentId).then(payload => {
      if (!active) return;
      setSuggestions(suggestionMap(payload));
      setDecisions({});
    }).catch(() => { /* no stored suggestions yet — manual marking still works */ });
    return () => { active = false; };
  }, [assignmentId, editable, evaluation.id]);

  const setMarkField = (position: number, marks: string, feedback: string) => {
    setForm(prev => ({
      marks: { ...prev.marks, [position]: marks },
      feedback: { ...prev.feedback, [position]: feedback },
    }));
  };

  const acceptSuggestion = (position: number) => {
    const suggestion = suggestions[position];
    if (!suggestion) return;
    setMarkField(position, String(suggestion.suggested_marks), suggestion.feedback ?? '');
    setDecisions(prev => ({ ...prev, [position]: 'accepted' }));
    setAiNotice(`Accepted AI suggestion for question ${position}. Review and save when ready.`);
    setAiError('');
  };
  const acceptConfident = () => {
    const confident = pendingSuggestions.filter((q: any) => !suggestions[q.position].needs_teacher_attention && suggestions[q.position].confidence !== 'low');
    confident.forEach((q: any) => {
      const s = suggestions[q.position];
      setMarkField(q.position, String(s.suggested_marks), s.feedback ?? '');
    });
    setDecisions(prev => ({ ...prev, ...Object.fromEntries(confident.map((q: any) => [q.position, 'accepted'])) }));
    setAiNotice(`Accepted ${confident.length} confident suggestion(s). Check the flagged ones yourself, then save.`);
  };

  const rejectSuggestion = (position: number) => {
    setDecisions(prev => ({ ...prev, [position]: 'rejected' }));
    setAiNotice(`Rejected AI suggestion for question ${position}. Enter marks manually.`);
    setAiError('');
  };

  const runAi = async (mode: 'generate' | 'rerun') => {
    setAiBusy(true); setAiError(''); setAiNotice('');
    try {
      const payload = mode === 'rerun'
        ? await hw.rerunAiSuggestions(assignmentId, { provider: aiModel })
        : await hw.generateAiSuggestions(assignmentId, hasSuggestions ? { replace: true, provider: aiModel } : { provider: aiModel });
      setSuggestions(suggestionMap(payload));
      setDecisions({});
      setAiNotice(mode === 'rerun'
        ? `AI suggestions regenerated with ${aiModelName}. Accept, edit or reject each one before saving.`
        : `AI suggestions from ${aiModelName} ready. They are not saved marks until you accept and save.`);
    } catch (ex) {
      setAiError(errorText(ex));
    } finally {
      setAiBusy(false);
    }
  };

  const save = async () => {
    const items = evaluation.items.map((q: any) => {
      const raw = form.marks[q.position] ?? '';
      if (raw !== '' && (!Number.isInteger(Number(raw)) || Number(raw) < 0 || Number(raw) > q.max_marks))
        throw new Error(`Question ${q.position}: marks must be a whole number from 0 to ${q.max_marks}.`);
      return { position: q.position, feedback: form.feedback[q.position] ?? '', ...(raw === '' ? {} : { awarded_marks: Number(raw) }) };
    });
    const saved = await hw.call(`${base}/evaluation/items`, 'PATCH', { expected_version: evaluation.version, items });
    update(saved); return saved;
  };
  const totalMax = evaluation.total_max || 1;
  const shownTotal = evaluation.total_awarded ?? runningTotal;

  return <div className="space-y-3 border-t border-surface-border pt-3">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="flex items-center gap-2 font-semibold">Evaluation <StatusBadge status={evaluation.status} /></h3>
      <div className="min-w-[12rem] text-right">
        <p className="text-sm font-medium">{shownTotal} / {evaluation.total_max} marks · {evaluation.marked_count} / {evaluation.question_count} marked</p>
        <div className="mt-1 h-1.5 rounded-full bg-gray-100"><div className="h-1.5 rounded-full bg-teal-500" style={{ width: `${Math.min(100, (shownTotal / totalMax) * 100)}%` }} /></div>
      </div>
    </div>

    {editable && <div className="space-y-2 rounded-xl border border-sky-200 bg-sky-50/60 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="flex items-center gap-1.5 text-sm font-medium text-sky-950"><Sparkles className="h-4 w-4" />AI-assisted suggestions</p>
          <p className="text-xs text-sky-900/80">Optional. Suggestions never finalize or release results. You keep full control of marks and feedback.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="AI marking model" className="rounded-lg border border-sky-200 bg-white px-2 py-1 text-sm" value={aiModel}
            disabled={busy || aiBusy} onChange={e => setAiModel(e.target.value as 'qwen' | 'gemini')}>
            <option value="qwen">Qwen (default, works offline)</option>
            <option value="gemini">Gemini (fallback)</option>
          </select>
          {!hasSuggestions && <Button variant="teal" size="sm" loading={aiBusy} disabled={busy || aiBusy}
            onClick={() => runAi('generate')}>Evaluate with AI</Button>}
          {hasSuggestions && pendingSuggestions.length > 0 && <Button variant="teal" size="sm" disabled={busy || aiBusy} onClick={acceptConfident}>Accept confident suggestions</Button>}
          {hasSuggestions && <Button variant="outline" size="sm" loading={aiBusy} disabled={busy || aiBusy}
            onClick={() => runAi('rerun')}>Regenerate suggestions</Button>}
        </div>
      </div>
      {aiBusy && <p role="status" className="text-sm text-sky-900">{aiModel === 'qwen'
        ? 'Qwen is evaluating the answers against keys and rubrics on this server - this can take a few minutes…'
        : 'Gemini is evaluating the answers against keys and rubrics…'}</p>}
      {hasSuggestions && !aiBusy && <p className="text-xs text-content-secondary">
        {Object.keys(suggestions).length} suggestion{Object.keys(suggestions).length === 1 ? '' : 's'} loaded
        {attentionCount > 0 ? ` · ${attentionCount} need teacher attention` : ''}.
        Purple panels are AI proposals; the mark fields below are your working marks.
      </p>}
      <Messages error={aiError} notice={aiNotice} />
    </div>}

    <Messages error={error} notice={notice} />
    {evaluation.items.map((q: any) => {
      const suggestion = suggestions[q.position];
      const decision = decisions[q.position] ?? null;
      const showSuggestion = Boolean(suggestion) && decision !== 'rejected';
      const uncertain = Boolean(suggestion?.needs_teacher_attention || suggestion?.confidence === 'low');
      const formMatchesSuggestion = suggestion
        && (form.marks[q.position] ?? '') === String(suggestion.suggested_marks)
        && (form.feedback[q.position] ?? '') === (suggestion.feedback ?? '');
      const editedAfterAccept = decision === 'accepted' && suggestion && !formMatchesSuggestion;
      const isMcq = Array.isArray(q.options) && q.options.length > 0;

      return <article key={q.position}
        className={'rounded-xl border p-3 ' + (uncertain && showSuggestion ? 'border-amber-300 bg-amber-50/30' : 'border-surface-border')}>
        <p className="text-sm font-medium">{q.position}. <MathText text={q.text} /> <span className="text-content-secondary">({marksLabel(q.max_marks)})</span></p>
        {isMcq
          ? <OptionList options={q.options} correct={q.correct_answer} selected={q.selected_option_index} />
          : <p className="mt-1 rounded-lg bg-gray-50 px-2 py-1 text-sm">Student answer: <MathText text={answerText(q)} /></p>}
        {isMcq && <p className="mt-1 text-sm">Student answer: <MathText text={answerText(q)} /></p>}
        <div className="mt-1 grid gap-1 text-xs text-content-secondary sm:grid-cols-2">
          <p>Answer key (teacher only): <MathText text={q.correct_answer ?? 'Unavailable'} /></p>
          <p>Rubric (teacher only): <MathText text={q.marking_rubric ?? 'Unavailable'} /></p>
        </div>

        {showSuggestion && <div className="mt-2 space-y-2 rounded-lg border border-violet-200 bg-violet-50/70 p-3" data-testid={`ai-suggestion-${q.position}`}>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info" size="sm">AI suggestion</Badge>
            <span title="Heuristic certainty label from the model or scorer — not a calibrated probability">
              <Badge variant={suggestion.confidence === 'high' ? 'success' : suggestion.confidence === 'low' ? 'warning' : 'default'} size="sm">
                Certainty (heuristic): {suggestion.confidence}
              </Badge>
            </span>
            {suggestion.needs_teacher_attention && <Badge variant="warning" size="sm">Needs attention</Badge>}
            <Badge variant="outline" size="sm">{
              suggestion.source === 'deterministic_mcq' ? 'Answer-key match'
                : suggestion.source === 'teacher_required' ? 'Teacher review required'
                  : suggestion.source === 'qwen' ? 'Qwen' : 'Gemini'}</Badge>
            {decision === 'accepted' && !editedAfterAccept && <Badge variant="teal" size="sm">Accepted into form</Badge>}
            {editedAfterAccept && <Badge variant="warning" size="sm">Edited after accept</Badge>}
          </div>
          <p className="text-sm"><span className="font-medium">Suggested marks:</span> {suggestion.suggested_marks} / {suggestion.max_marks}
            {' · '}<span className="font-medium">Assessment:</span> {String(suggestion.correctness).replace(/_/g, ' ')}</p>
          <p className="text-xs text-content-secondary"><span className="font-medium text-content-primary">Why (teacher only):</span> <MathText text={suggestion.explanation} /></p>
          <p className="text-xs"><span className="font-medium">Proposed student feedback:</span> <MathText text={suggestion.feedback} /></p>
          {Array.isArray(suggestion.rubric_criteria) && suggestion.rubric_criteria.length > 0 && (
            <ul className="space-y-1 border-t border-violet-100 pt-2 text-xs text-content-secondary">
              {suggestion.rubric_criteria.map((c: any, idx: number) => (
                <li key={idx}><span className="font-medium text-content-primary">{c.criterion}</span>
                  {' — '}{c.awarded_marks}/{c.max_marks}{c.comment ? <>: <MathText text={c.comment} /></> : null}</li>
              ))}
            </ul>
          )}
          {editable && <div className="flex flex-wrap gap-2 pt-1">
            <Button size="sm" variant="teal" disabled={busy || aiBusy} onClick={() => acceptSuggestion(q.position)}>Accept suggestion</Button>
            <Button size="sm" variant="outline" disabled={busy || aiBusy} onClick={() => rejectSuggestion(q.position)}>Reject</Button>
          </div>}
        </div>}

        {decision === 'rejected' && editable && suggestion && (
          <p className="mt-2 text-xs text-content-secondary">AI suggestion rejected for this question.
            <button type="button" className="ml-1 text-teal-700 underline" onClick={() => setDecisions(prev => ({ ...prev, [q.position]: null }))}>Show again</button>
          </p>
        )}

        <div className="mt-2 grid gap-2 sm:grid-cols-[8rem_1fr]">
          <label className="block"><span className={labelClass}>Your marks / {q.max_marks}</span>
            <input aria-label={`Marks for question ${q.position}`} className={inputClass} type="number" min={0} max={q.max_marks} step={1}
              value={form.marks[q.position] ?? ''} disabled={busy || !editable}
              onChange={e => setForm({ ...form, marks: { ...form.marks, [q.position]: e.target.value } })} /></label>
          <label className="block"><span className={labelClass}>Your feedback</span>
            <textarea aria-label={`Feedback for question ${q.position}`} className={inputClass} rows={2} maxLength={2000}
              value={form.feedback[q.position] ?? ''} disabled={busy || !editable}
              onChange={e => setForm({ ...form, feedback: { ...form.feedback, [q.position]: e.target.value } })} /></label>
        </div>
      </article>;
    })}
    <div className="sticky bottom-0 flex flex-wrap gap-2 border-t border-surface-border bg-white/95 py-3 backdrop-blur">
      {editable && <>
        <Button variant="outline" disabled={busy || aiBusy || !dirty} onClick={() => run(async () => { await save(); return 'Marks and feedback saved.'; })}>Save marking</Button>
        <Button variant="primary" disabled={busy || aiBusy} onClick={() => run(async () => {
          setError(''); setNotice('');
          let current = evaluation; if (dirty) current = await save();
          if (current.marked_count < current.question_count) throw new Error('Mark every question (0 is allowed) before finalizing.');
          update(await hw.call(`${base}/evaluation/finalize`, 'POST', { expected_version: current.version }));
          return 'Marks finalized. Release them to share with the student and parent.';
        })}>Save and finalize</Button>
      </>}
      {evaluation.status === 'marked' && <Button variant="teal" disabled={busy} onClick={() => run(async () => {
        if (!window.confirm('Release these results to the student and their linked parents?')) return;
        update(await hw.call(`${base}/evaluation/release`, 'POST', { expected_version: evaluation.version }));
        return 'Results released.';
      })}>Release results</Button>}
    </div>
    {evaluation.status === 'released' && <ReleasedNote at={evaluation.released_at} />}
  </div>;
}

const ReleasedNote: React.FC<{ at?: string }> = ({ at }) =>
  <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">Released {formatDate(at)}. The student and linked parents can now view this result.</p>;

// --- Question bank ----------------------------------------------------------------------

type BankForm = {
  text: string; type: string; options: string[]; correctAnswer: string; markingRubric: string;
  marks: number; competency: string; bloomLevel: string; topic: string;
};
const blankForm = (): BankForm => ({
  text: '', type: 'mcq', options: ['', '', '', ''], correctAnswer: '', markingRubric: '', marks: 1, competency: 'CU', bloomLevel: 'Understand', topic: '',
});

function formProblem(f: BankForm): string | null {
  if (!f.text.trim()) return 'Write the question.';
  if (f.type === 'mcq') {
    const opts = f.options.map(o => o.trim()).filter(Boolean);
    if (opts.length < 2) return 'Add at least two options.';
    if (new Set(opts.map(o => o.toLowerCase())).size !== opts.length) return 'Options must be different from each other.';
    if (!opts.includes(f.correctAnswer.trim())) return 'Choose the correct option.';
  }
  if (!Number.isInteger(f.marks) || f.marks < 1) return 'Marks must be a whole number of at least 1.';
  return null;
}

function QuestionBank({ subjectName }: { subjectName: NameFn }) {
  const { currentSchoolId, currentUser } = useAuth();
  const { busy, error, notice, run } = useRunner();
  const [subjects, setSubjects] = useState<string[]>([]);
  const [subject, setSubject] = useState('');
  const [questions, setQuestions] = useState<any[]>([]);
  const [filters, setFilters] = useState({ competency: '', bloom: '', type: '', text: '', source: '', topic: '' });
  const [selected, setSelected] = useState<any>(null);   // null = nothing open; {id:''} = new question
  const [edit, setEdit] = useState<BankForm>(blankForm());
  const [showAi, setShowAi] = useState(false);

  useEffect(() => { let active = true;
    hw.call<any[]>(`/schools/${enc(currentSchoolId)}/classes`).then(rows => {
      if (!active) return;
      const ids = Array.from(new Set(rows.flatMap(c => c.subject_ids_json ?? []))) as string[];
      // Open on the teacher's own subject (a Science teacher should not land in the Mathematics bank).
      const own = (currentUser?.assignedSubjectIds ?? []).find(id => ids.includes(id));
      setSubjects(ids); setSubject(s => s || own || ids[0] || '');
    }).catch(() => undefined);
    return () => { active = false; }; }, [currentSchoolId]);
  const reload = async () => setQuestions(await apiClient.assessments.getQuestionBank(subject || undefined));
  useEffect(() => { if (subject) run(reload); }, [subject]); // eslint-disable-line react-hooks/exhaustive-deps

  const shown = questions.filter(q => (!filters.competency || q.competency === filters.competency) && (!filters.bloom || q.bloomLevel === filters.bloom)
    && (!filters.type || q.type === filters.type) && (!filters.text || q.text.toLowerCase().includes(filters.text.toLowerCase()))
    && (!filters.source || (filters.source === 'ai') === Boolean(q.isAiGenerated))
    && (!filters.topic || (filters.topic === '__none' ? !q.topic : (q.topic || '').toLowerCase() === filters.topic.toLowerCase())));
  const topicNames = useMemo(() => Array.from(new Set(questions.map(q => q.topic).filter(Boolean) as string[])).sort((a, b) => a.localeCompare(b)), [questions]);
  const byCompetency = useMemo(() => Object.fromEntries(['LU', 'CU', 'AU', 'CT'].map(c => [c, questions.filter(q => q.competency === c).length])), [questions]);
  const open = (q: any) => {
    setSelected(q);
    const opts = q.options?.length ? [...q.options] : ['', '', '', ''];
    setEdit({ text: q.text, type: q.type, options: opts, correctAnswer: q.correctAnswer ?? '', markingRubric: q.markingRubric ?? '',
      marks: q.marks, competency: q.competency, bloomLevel: q.bloomLevel || 'Understand', topic: q.topic ?? '' });
  };
  // New questions start in the topic currently filtered on, which is what teachers usually want.
  const startNew = () => { setSelected({ id: '' }); setEdit({ ...blankForm(), topic: filters.topic && filters.topic !== '__none' ? filters.topic : '' }); };
  const isNew = selected && !selected.id;
  const problem = selected ? formProblem(edit) : null;
  const payload = () => ({ ...edit, options: edit.type === 'mcq' ? edit.options.map(o => o.trim()).filter(Boolean) : [],
    correctAnswer: edit.correctAnswer.trim(), topic: edit.topic.trim() });

  return <div className="space-y-5">
    <div className="grid gap-3 sm:grid-cols-4">
      {(['LU', 'CU', 'AU', 'CT'] as const).map(c => <button key={c} type="button" onClick={() => setFilters(f => ({ ...f, competency: f.competency === c ? '' : c }))}
        className={'rounded-xl border p-3 text-left transition hover:shadow-sm ' + (filters.competency === c ? 'border-teal-400 bg-teal-50' : 'border-surface-border bg-white')}>
        <CompetencyTag code={c} /><p className="mt-1 text-xs text-content-secondary">{COMPETENCY_NAMES[c]}</p>
        <p className="text-xl font-bold">{byCompetency[c] ?? 0} <span className="text-xs font-normal text-content-secondary">questions</span></p>
        {(byCompetency[c] ?? 0) < 3 && questions.length > 0 && <p className="text-[11px] font-medium text-amber-700">Low - add more so homework can target this</p>}
      </button>)}
    </div>

    <div className="flex flex-wrap items-center gap-2">
      <Button variant="primary" icon={<Plus className="h-4 w-4" />} disabled={!subject} onClick={startNew}>Write a question</Button>
      <Link to="/teacher/assessments"
        className="inline-flex items-center gap-2 rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-teal-700">
        <BookOpen className="h-4 w-4" />Generate from a chapter PDF (AI Question Studio)</Link>
      <Button variant={showAi ? 'secondary' : 'outline'} icon={<Sparkles className="h-4 w-4" />} onClick={() => setShowAi(v => !v)}>
        {showAi ? 'Hide quick generator' : 'Quick generate from a topic (Qwen or Gemini)'}</Button>
      <Button variant="ghost" disabled={busy || !subject} onClick={() => run(async () => {
        await apiClient.assessments.createTemplateQuestion({ subjectId: subject, bloomLevel: 'Apply', competency: 'CU' });
        await reload(); return 'Template question (no AI) added to the bank. Review and edit it before use.';
      })}>Add template question (no AI)</Button>
    </div>

    {showAi && <AiQuestionGenerator subjects={subjects} subjectName={subjectName} defaultSubject={subject} onSaved={async (savedSubject) => {
      // Show the bank the questions were saved to, so the teacher sees them straight away.
      if (savedSubject && savedSubject !== subject) { setSubject(savedSubject); setSelected(null); } else await reload();
    }} />}

    <div className="grid gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <Section title="Question bank" subtitle={`Answer keys and rubrics are visible to educators only.`}>
        <Messages error={error} notice={notice} />
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <select aria-label="Bank subject" className={inputClass} value={subject} onChange={e => { setSubject(e.target.value); setSelected(null); }}>
            {subjects.length === 0 && <option value="">No subjects</option>}{subjects.map(s => <option key={s} value={s}>{subjectName(s)}</option>)}</select>
          <select aria-label="Bloom filter" className={inputClass} value={filters.bloom} onChange={e => setFilters({ ...filters, bloom: e.target.value })}>
            <option value="">All Bloom levels</option>{BLOOM.map(b => <option key={b}>{b}</option>)}</select>
          <select aria-label="Type filter" className={inputClass} value={filters.type} onChange={e => setFilters({ ...filters, type: e.target.value })}>
            <option value="">All types</option>{QUESTION_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          <select aria-label="Competency filter" className={inputClass} value={filters.competency} onChange={e => setFilters({ ...filters, competency: e.target.value })}>
            <option value="">All competencies</option>{Object.keys(COMPETENCY_NAMES).map(c => <option key={c} value={c}>{c} - {COMPETENCY_NAMES[c]}</option>)}</select>
          <select aria-label="Topic filter" className={inputClass} value={filters.topic} onChange={e => setFilters({ ...filters, topic: e.target.value })}>
            <option value="">All topics</option>{topicNames.map(t => <option key={t} value={t}>{t}</option>)}<option value="__none">No topic yet</option></select>
          <select aria-label="Source filter" className={inputClass} value={filters.source} onChange={e => setFilters({ ...filters, source: e.target.value })}>
            <option value="">Teacher and AI</option><option value="teacher">Teacher-written</option><option value="ai">AI-generated</option></select>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-content-secondary" />
            <input aria-label="Search questions" placeholder="Search" className={inputClass + ' pl-8'} value={filters.text} onChange={e => setFilters({ ...filters, text: e.target.value })} />
          </div>
        </div>
        <p className="text-xs text-content-secondary">{shown.length} of {questions.length} questions</p>
        {shown.length === 0 ? <Empty icon={<Library className="h-6 w-6" />}>{questions.length === 0 ? 'This subject has no questions yet. Write one or generate some with AI.' : 'No questions match the filters.'}</Empty> :
          <ul className="max-h-[36rem] space-y-1.5 overflow-y-auto pr-1">{shown.map(q => <li key={q.id}>
            <button aria-label={q.text} className={'w-full rounded-xl border px-3 py-2.5 text-left transition hover:border-teal-300 ' + (selected?.id === q.id ? 'border-teal-400 bg-teal-50' : 'border-surface-border bg-white')} onClick={() => open(q)}>
              <p className="text-sm"><MathText text={q.text} /></p>
              <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-content-secondary"><CompetencyTag code={q.competency} /><span>{q.bloomLevel}</span><span>·</span><span>{typeLabel(q.type)}</span><span>·</span><span>{marksLabel(q.marks)}</span>
                {q.topic ? <Badge variant="outline" size="sm">{q.topic}</Badge> : <span className="italic">no topic</span>}
                {q.isAiGenerated && <Badge variant="warning" size="sm">AI-generated</Badge>}</p>
            </button></li>)}</ul>}
      </Section>

      <Section title={isNew ? 'Write a new question' : 'Edit question'} subtitle={isNew ? `${subjectName(subject)} · saved to your school’s bank` : undefined} className="lg:sticky lg:top-4 lg:self-start">
        {!selected ? <Empty icon={<PenLine className="h-6 w-6" />}>Select a question to edit it, or press <strong>Write a question</strong>.</Empty> : <>
          <label className="block"><span className={labelClass}>Question</span>
            <textarea aria-label="Question" rows={3} className={inputClass} value={edit.text} onChange={e => setEdit({ ...edit, text: e.target.value })} /></label>
          <MathPreview text={edit.text} />
          <p className="text-[11px] text-content-secondary">{MATH_HINT}</p>
          <label className="block"><span className={labelClass}>Topic / chapter</span>
            <input aria-label="Topic" list="bank-topics" className={inputClass} placeholder="e.g. Mensuration" value={edit.topic}
              onChange={e => setEdit({ ...edit, topic: e.target.value })} />
            <datalist id="bank-topics">{topicNames.map(t => <option key={t} value={t} />)}</datalist></label>
          <div className="grid grid-cols-2 gap-2">
            <label><span className={labelClass}>Type</span><select aria-label="Question type" className={inputClass} value={edit.type}
              onChange={e => setEdit({ ...edit, type: e.target.value, ...(e.target.value === 'mcq' && edit.options.length < 2 ? { options: ['', '', '', ''] } : {}) })}>
              {QUESTION_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
            <label><span className={labelClass}>Marks</span><input aria-label="Marks" type="number" min={1} className={inputClass} value={edit.marks}
              onChange={e => setEdit({ ...edit, marks: Number(e.target.value) })} /></label>
            <label><span className={labelClass}>Competency</span><select aria-label="Competency" className={inputClass} value={edit.competency}
              onChange={e => setEdit({ ...edit, competency: e.target.value })}>{Object.keys(COMPETENCY_NAMES).map(c => <option key={c} value={c}>{c} - {COMPETENCY_NAMES[c]}</option>)}</select></label>
            <label><span className={labelClass}>Bloom</span><select aria-label="Bloom level" className={inputClass} value={edit.bloomLevel}
              onChange={e => setEdit({ ...edit, bloomLevel: e.target.value })}>{BLOOM.map(b => <option key={b}>{b}</option>)}</select></label>
          </div>
          {edit.type === 'mcq'
            ? <OptionsEditor idPrefix="bank" options={edit.options} correct={edit.correctAnswer}
                onChange={(options, correctAnswer) => setEdit({ ...edit, options, correctAnswer })} />
            : <label className="block"><span className={labelClass}>Correct answer</span>
                <textarea aria-label="Correct answer" className={inputClass} value={edit.correctAnswer} onChange={e => setEdit({ ...edit, correctAnswer: e.target.value })} /></label>}
          {edit.type !== 'mcq' && <MathPreview text={edit.correctAnswer} />}
          <label className="block"><span className={labelClass}>Rubric</span>
            <textarea aria-label="Rubric" className={inputClass} placeholder="How marks are awarded, e.g. 1 mark for the formula, 1 for the answer" value={edit.markingRubric} onChange={e => setEdit({ ...edit, markingRubric: e.target.value })} /></label>
          {problem && <p className="text-xs font-medium text-amber-700">{problem}</p>}
          <div className="flex flex-wrap gap-2">
            {isNew
              ? <Button variant="primary" disabled={busy || !!problem} onClick={() => run(async () => {
                  const q = await apiClient.assessments.createQuestion({ subjectId: subject, ...payload() });
                  await reload(); open(q); return 'Question added to the bank.';
                })}>Add to bank</Button>
              : <>
                <Button variant="primary" disabled={busy || !!problem} onClick={() => run(async () => { await apiClient.assessments.updateQuestion(selected.id, payload()); setSelected(null); await reload(); return 'Question saved.'; })}>Save edits</Button>
                <Button variant="danger" disabled={busy} onClick={() => run(async () => { if (!window.confirm('Delete this bank question? Existing homework keeps its frozen copy.')) return;
                  await apiClient.assessments.deleteQuestion(selected.id); setSelected(null); await reload(); return 'Question deleted.'; })}>Delete</Button>
              </>}
            <Button variant="ghost" disabled={busy} onClick={() => setSelected(null)}>Cancel</Button>
          </div>
        </>}
      </Section>
    </div>
  </div>;
}
