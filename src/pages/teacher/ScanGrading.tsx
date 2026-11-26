import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { marksLabel } from '../../lib/utils';
import { CheckCircle2, Circle, FileText, Loader2, Sparkles, UploadCloud, UserCheck } from 'lucide-react';
import { ApiError, AssignmentUploads, PublishedGrade, apiClient } from '../../lib/apiClient';
import { MathText } from '../../components/common/MathText';

type Student = AssignmentUploads['students'][number];
type Draft = { marks: Record<number, string>; feedback: Record<number, string>; overall: string; source: 'qwen' | 'gemini' | 'teacher' };
const DIM_NAMES: Record<string, string> = { LU: 'Language', CU: 'Concept', AU: 'Application', CT: 'Critical Thinking', overall: 'Overall' };

/**
 * Teacher view of one assignment: which students uploaded handwritten answers, the OCR text of each upload,
 * the evaluator's draft marks (Qwen by default, Gemini as fallback, or manual marking), and Publish grade -
 * which records the result, updates the student's LU/CU/AU/CT parameters and notifies the student and parents.
 */
export function ScanGrading({ assessmentId, onChanged }: { assessmentId: string; onChanged?: () => void }) {
  const [data, setData] = useState<AssignmentUploads | null>(null);
  const [error, setError] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const load = useCallback(async () => {
    try { setData(await apiClient.assessments.uploads(assessmentId)); setError(''); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not load submissions.'); }
  }, [assessmentId]);
  useEffect(() => { void load(); }, [load]);

  const students = data?.students ?? [];
  const firstPending = students.find(s => s.uploads.length && !s.grade);
  useEffect(() => { if (!selectedId && firstPending) setSelectedId(firstPending.student_id); }, [selectedId, firstPending]);
  const selected = students.find(s => s.student_id === selectedId);

  if (error) return <p role="alert" className="rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{error}</p>;
  if (!data) return <p role="status" className="text-sm text-content-secondary"><Loader2 className="mr-1 inline h-4 w-4 animate-spin" />Loading submissions…</p>;

  return (
    <section className="rounded-2xl border border-surface-border bg-white p-5 shadow-subtle" aria-label="Student submissions">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-navy-900">Student submissions</h2>
          <p className="text-xs text-content-secondary">{data.assessment.class_name} · {data.assessment.subject_name} · {data.assessment.total_marks} marks</p>
        </div>
        <div className="flex gap-2 text-xs">
          <span className="rounded-full bg-sky-50 px-3 py-1 font-semibold text-sky-800">{data.summary.uploaded}/{data.summary.students} uploaded</span>
          <span className="rounded-full bg-emerald-50 px-3 py-1 font-semibold text-emerald-800">{data.summary.graded} graded</span>
          <span className="rounded-full bg-amber-50 px-3 py-1 font-semibold text-amber-800">{students.filter(s => s.uploads.length && !s.grade).length} to evaluate</span>
        </div>
      </header>
      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <ul className="max-h-[38rem] space-y-1 overflow-y-auto pr-1" aria-label="Class roster">
          {students.map(s => {
            const status = s.grade ? 'graded' : s.uploads.length ? 'uploaded' : 'none';
            return (
              <li key={s.student_id}>
                <button type="button" onClick={() => setSelectedId(s.student_id)} disabled={status === 'none'}
                  className={'flex w-full items-center justify-between gap-2 rounded-xl border px-3 py-2 text-left text-sm transition '
                    + (s.student_id === selectedId ? 'border-teal-500 bg-teal-50' : 'border-surface-border bg-white hover:border-teal-300')
                    + (status === 'none' ? ' cursor-default opacity-60' : '')}>
                  <span className="min-w-0"><span className="text-xs text-content-secondary">#{s.roll_no}</span> <span className="font-medium">{s.name}</span></span>
                  {status === 'graded' ? <span className="flex items-center gap-1 text-xs font-semibold text-emerald-700"><CheckCircle2 className="h-4 w-4" />{s.grade!.marks_obtained}/{s.grade!.total_marks}</span>
                    : status === 'uploaded' ? <span className="flex items-center gap-1 text-xs font-semibold text-amber-700"><UploadCloud className="h-4 w-4" />Evaluate</span>
                      : <span className="flex items-center gap-1 text-xs text-content-muted"><Circle className="h-3 w-3" />Not submitted</span>}
                </button>
              </li>
            );
          })}
        </ul>
        <div>{selected ? <StudentGrader key={selected.student_id} data={data} student={selected}
          onPublished={async () => { await load(); onChanged?.(); }} />
          : <p className="rounded-xl border border-dashed border-surface-border p-6 text-center text-sm text-content-secondary">Choose a student who has uploaded their answers.</p>}</div>
      </div>
    </section>
  );
}

function StudentGrader({ data, student, onPublished }: { data: AssignmentUploads; student: Student; onPublished: () => Promise<void> }) {
  const questions = data.assessment.questions;
  const upload = student.uploads[0];
  const [text, setText] = useState(upload?.extracted_text ?? '');
  const [provider, setProvider] = useState<'qwen' | 'gemini'>('qwen');
  const [busy, setBusy] = useState<'' | 'evaluate' | 'publish'>('');
  const [error, setError] = useState('');
  const [aiNote, setAiNote] = useState('');
  const [draft, setDraft] = useState<Draft | null>(null);
  const [published, setPublished] = useState<PublishedGrade | null>(null);
  const total = useMemo(() => draft ? questions.reduce((n, q) => n + (Number(draft.marks[q.index]) || 0), 0) : 0, [draft, questions]);

  const manual = () => {
    setDraft({ marks: Object.fromEntries(questions.map(q => [q.index, ''])), feedback: {}, overall: '', source: 'teacher' });
    setAiNote('');
  };
  const evaluate = async () => {
    setBusy('evaluate'); setError(''); setAiNote('');
    try {
      const result = await apiClient.ocr.evaluateScan(data.assessment.id, text.trim(), provider, upload?.history_id);
      const byIndex = new Map(result.question_evaluations.map(q => [q.question_index, q]));
      setDraft({
        marks: Object.fromEntries(questions.map(q => [q.index, String(byIndex.get(q.index)?.awarded_marks ?? 0)])),
        feedback: Object.fromEntries(questions.map(q => [q.index, byIndex.get(q.index)?.feedback ?? ''])),
        overall: result.scoring_summary.overall_feedback ?? '', source: provider,
      });
      setAiNote(result.scoring_summary.needs_teacher_review
        ? `Draft from ${provider === 'qwen' ? 'Qwen' : 'Gemini'} - review required: ${result.scoring_summary.review_reasons.join('; ') || 'check flagged answers'}`
        : `Draft marks from ${provider === 'qwen' ? 'Qwen' : 'Gemini'}. Check them, adjust anything, then publish.`);
    } catch (e) {
      const message = e instanceof ApiError ? e.message : 'The evaluator is unavailable.';
      const paperProblem = /answer key or rubric|no questions to evaluate/i.test(message);
      setError(paperProblem ? message : message + (provider === 'qwen' ? ' Try Gemini (fallback), or mark manually.' : ' You can mark manually.'));
    } finally { setBusy(''); }
  };
  const publish = async () => {
    if (!draft) return;
    const items = questions.map(q => ({ question_index: q.index, awarded_marks: Number(draft.marks[q.index]), feedback: draft.feedback[q.index] || undefined }));
    const bad = items.find((it, i) => draft.marks[questions[i].index] === '' || !Number.isFinite(it.awarded_marks) || it.awarded_marks < 0 || it.awarded_marks > questions[i].marks);
    if (bad) { setError(`Question ${bad.question_index}: enter marks from 0 to ${questions.find(q => q.index === bad.question_index)?.marks}.`); return; }
    setBusy('publish'); setError('');
    try {
      setPublished(await apiClient.assessments.publishGrade(data.assessment.id, {
        student_id: student.student_id, history_id: upload?.history_id, items, overall_feedback: draft.overall || undefined, evaluated_by: draft.source,
      }));
      await onPublished();
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not publish the grade.'); }
    finally { setBusy(''); }
  };

  if (published) {
    return (
      <div className="space-y-3 rounded-xl border border-emerald-200 bg-emerald-50/50 p-4" role="status">
        <p className="flex items-center gap-2 font-semibold text-emerald-900"><UserCheck className="h-5 w-5" />Grade published for {published.student_name}: {published.marks_obtained}/{published.total_marks} ({published.percentage}%)</p>
        <p className="text-sm text-emerald-900/80">{published.regraded ? 'The earlier grade was corrected.' : 'Parameters updated from the competencies this work assessed. The student and their parents have been notified.'}</p>
        {!published.regraded && <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {['LU', 'CU', 'AU', 'CT', 'overall'].map(d => {
            const before = published.parameters_before[d]; const after = published.parameters_after[d];
            return <div key={d} className="rounded-lg bg-white p-2 text-center text-xs"><span className="block text-content-secondary">{DIM_NAMES[d]}</span>
              <span className="font-bold">{before} → {after}</span>
              <span className={'ml-1 ' + (after - before >= 0 ? 'text-emerald-700' : 'text-rose-700')}>{after - before >= 0 ? '+' : ''}{after - before}</span></div>;
          })}
        </div>}
      </div>
    );
  }

  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold text-navy-900">{student.name} <span className="text-xs font-normal text-content-secondary">· Roll {student.roll_no}</span></h3>
        {student.grade && <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800">Graded {student.grade.marks_obtained}/{student.grade.total_marks} · re-grading corrects it</span>}
      </div>
      {upload && <p className="flex items-center gap-1 text-xs text-content-secondary"><FileText className="h-3.5 w-3.5" />{upload.file_name} · {upload.pages_processed} page(s) · OCR text below (fix any recognition errors before evaluating)</p>}
      <textarea aria-label="Extracted answers" value={text} onChange={e => { setText(e.target.value); setDraft(null); }} rows={6}
        className="block w-full rounded-lg border border-surface-border p-2 font-mono text-xs" />
      <div className="flex flex-wrap items-center gap-2">
        <select aria-label="Evaluator model" value={provider} onChange={e => setProvider(e.target.value as 'qwen' | 'gemini')} disabled={!!busy}
          className="rounded-lg border border-surface-border bg-white px-2 py-2 text-sm">
          <option value="qwen">Qwen (default)</option><option value="gemini">Gemini (fallback)</option>
        </select>
        <button type="button" onClick={evaluate} disabled={!!busy || !text.trim()}
          className="inline-flex items-center gap-1.5 rounded-lg bg-navy-900 px-4 py-2 font-semibold text-white disabled:opacity-50">
          {busy === 'evaluate' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}{busy === 'evaluate' ? 'Evaluating…' : 'Evaluate with AI'}
        </button>
        <button type="button" onClick={manual} disabled={!!busy} className="rounded-lg border border-surface-border px-4 py-2 font-semibold text-navy-900 hover:bg-surface-bg">Mark manually</button>
      </div>
      {error && <p role="alert" className="rounded-lg bg-rose-50 p-2 text-rose-700">{error}</p>}
      {aiNote && <p className="rounded-lg bg-sky-50 p-2 text-sky-900">{aiNote}</p>}
      {draft && (
        <div className="space-y-2 rounded-xl border border-surface-border p-3">
          <div className="flex items-center justify-between"><h4 className="font-semibold">Marks</h4>
            <span className="font-semibold">{total} / {data.assessment.total_marks}</span></div>
          {questions.map(q => (
            <div key={q.index} className="grid gap-2 border-t border-surface-border pt-2 sm:grid-cols-[1fr_6rem]">
              <div>
                <p className="font-medium">Q{q.index}. <MathText text={q.text} /> <span className="text-xs text-content-secondary">({marksLabel(q.marks)} · {q.competency})</span></p>
                {q.correct_answer && <p className="text-xs text-content-secondary">Key: <MathText text={q.correct_answer} /></p>}
                <input aria-label={`Feedback for question ${q.index}`} value={draft.feedback[q.index] ?? ''} placeholder="Feedback (optional)"
                  onChange={e => setDraft({ ...draft, feedback: { ...draft.feedback, [q.index]: e.target.value } })}
                  className="mt-1 w-full rounded border border-surface-border px-2 py-1 text-xs" />
              </div>
              <label className="text-xs text-content-secondary">Marks / {q.marks}
                <input aria-label={`Marks for question ${q.index}`} type="number" min={0} max={q.marks} step={0.5} value={draft.marks[q.index] ?? ''}
                  onChange={e => setDraft({ ...draft, marks: { ...draft.marks, [q.index]: e.target.value } })}
                  className="mt-0.5 w-full rounded border border-surface-border px-2 py-1 text-sm text-content-primary" />
              </label>
            </div>
          ))}
          <textarea aria-label="Overall feedback" value={draft.overall} onChange={e => setDraft({ ...draft, overall: e.target.value })} rows={2}
            placeholder="Overall feedback for the student and parents" className="block w-full rounded-lg border border-surface-border p-2 text-sm" />
          <button type="button" onClick={publish} disabled={!!busy}
            className="inline-flex items-center gap-1.5 rounded-lg bg-teal-600 px-4 py-2 font-semibold text-white hover:bg-teal-700 disabled:opacity-50">
            {busy === 'publish' ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}Publish grade
          </button>
        </div>
      )}
    </div>
  );
}
