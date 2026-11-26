import React, { useState } from 'react';
import { apiClient } from '../../lib/apiClient';
import { Button } from '../../components/common/Button';
import { MathText } from '../../components/common/MathText';
import { BLOOM, COMPETENCY_NAMES, CompetencyTag, Empty, MATH_HINT, MathPreview, Messages, OptionsEditor, Section, inputClass, labelClass, useRunner } from './ui';
const TYPES: [string, string][] = [['mcq', 'Multiple choice (MCQ)'], ['short', 'Short answer'], ['descriptive', 'Long answer']];
const LANGUAGES = ['English', 'Hindi', 'Bengali', 'Marathi', 'Tamil', 'Telugu', 'Kannada', 'Gujarati', 'Punjabi'];

type Draft = { key: number; approved: boolean; q: any };
let nextKey = 1;

/** AI question generation (local Qwen or Gemini): parameters -> preview -> edit -> approve & save. Nothing is saved
 * until the teacher clicks "Save approved". Saved questions are flagged AI-generated in the bank. */
export const AiQuestionGenerator: React.FC<{ subjects: string[]; defaultSubject: string; onSaved: (savedSubject?: string) => Promise<void>; subjectName?: (id: string) => string }> =
  ({ subjects, defaultSubject, onSaved, subjectName = id => id }) => {
  const { busy, error, notice, run } = useRunner();
  const [params, setParams] = useState({
    subject_id: defaultSubject, grade: 8, topic: '', competency: 'AU', bloom_level: 'Apply', question_type: 'mcq',
    marks: 2, count: 3, language: 'English', instructions: '', provider: 'qwen' as 'qwen' | 'gemini',
  });
  const modelName = params.provider === 'qwen' ? 'Qwen' : 'Gemini';
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [meta, setMeta] = useState<any>(null);  // provenance summary of the last AI response
  const [savedCount, setSavedCount] = useState(0);  // questions from this AI response already saved
  const [regenerating, setRegenerating] = useState<number | null>(null);
  const subject = params.subject_id || defaultSubject;
  const set = (patch: Partial<typeof params>) => setParams(p => ({ ...p, ...patch }));
  const body = (count = params.count, avoid: string[] = []) =>
    ({ ...params, subject_id: subject, count, instructions: params.instructions.trim() || undefined, avoid_texts: avoid });

  const generate = () => run(async () => {
    setDrafts([]); setMeta(null); setSavedCount(0);  // never leave earlier results on screen if this request fails
    const res = await apiClient.assessments.aiGenerateQuestions(body());
    if (res.source !== 'ai_generated') throw new Error('Unexpected response: these are not AI-generated questions.');
    setDrafts(res.questions.map((q: any) => ({ key: nextKey++, approved: true, q })));
    setMeta(res);
    const usedModel = res.provider === 'qwen' ? 'Qwen' : res.provider === 'gemini' ? 'Gemini' : modelName;
    return `${usedModel} generated ${res.generated} new question(s)${res.generated < res.requested ? ` of ${res.requested} requested` : ''}. Review, edit and approve before saving.`;
  });
  const regenerateOne = (key: number) => { setRegenerating(key); run(async () => {
    try {
      // Questions still on screen are sent only for the server's duplicate check.
      const res = await apiClient.assessments.aiGenerateQuestions(body(1, drafts.map(d => d.q.text)));
      setDrafts(ds => ds.map(d => d.key === key ? { key: nextKey++, approved: true, q: res.questions[0] } : d));
      return `Question regenerated with a new one from ${modelName}.`;
    } finally { setRegenerating(null); }
  }); };
  const update = (key: number, patch: any) => setDrafts(ds => ds.map(d => d.key === key ? { ...d, q: { ...d.q, ...patch } } : d));
  const approved = drafts.filter(d => d.approved);

  return <Section title={<span>Generate questions with AI <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-semibold text-amber-800">{modelName} - teacher review required</span></span>}
    subtitle={params.provider === 'qwen'
      ? 'Qwen runs on this server, so no internet connection is needed. Only the teaching parameters below are used - never student names, IDs or scores. Nothing is saved until you approve it.'
      : 'Only the teaching parameters below are sent to the Gemini service - never student names, IDs or scores. Nothing is saved until you approve it.'}>
    <Messages error={error} notice={notice} />
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <label><span className={labelClass}>Model</span>
        <select aria-label="AI model" className={inputClass} value={params.provider} disabled={busy}
          onChange={e => set({ provider: e.target.value as 'qwen' | 'gemini' })}>
          <option value="qwen">Qwen (default, works offline)</option>
          <option value="gemini">Gemini (fallback)</option></select></label>
      <label><span className={labelClass}>Subject</span>
        <select aria-label="AI subject" className={inputClass} value={subject} disabled={busy} onChange={e => set({ subject_id: e.target.value })}>
          {subjects.map(s => <option key={s} value={s}>{subjectName(s)}</option>)}</select></label>
      <label><span className={labelClass}>Class / grade</span>
        <input aria-label="AI grade" type="number" min={1} max={12} className={inputClass} value={params.grade} disabled={busy} onChange={e => set({ grade: Number(e.target.value) })} /></label>
      <label className="sm:col-span-2 lg:col-span-3"><span className={labelClass}>Topic or chapter</span>
        <input aria-label="AI topic" className={inputClass} placeholder="e.g. Mensuration - volume of cuboids" value={params.topic} disabled={busy} onChange={e => set({ topic: e.target.value })} /></label>
      <label><span className={labelClass}>Competency</span>
        <select aria-label="AI competency" className={inputClass} value={params.competency} disabled={busy} onChange={e => set({ competency: e.target.value })}>
          {Object.entries(COMPETENCY_NAMES).map(([c, n]) => <option key={c} value={c}>{c} - {n}</option>)}</select></label>
      <label><span className={labelClass}>Bloom level</span>
        <select aria-label="AI Bloom level" className={inputClass} value={params.bloom_level} disabled={busy} onChange={e => set({ bloom_level: e.target.value })}>
          {BLOOM.map(b => <option key={b}>{b}</option>)}</select></label>
      <label><span className={labelClass}>Question type</span>
        <select aria-label="AI question type" className={inputClass} value={params.question_type} disabled={busy} onChange={e => set({ question_type: e.target.value })}>
          {TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      <label><span className={labelClass}>Marks per question</span>
        <input aria-label="AI marks" type="number" min={1} max={20} className={inputClass} value={params.marks} disabled={busy} onChange={e => set({ marks: Number(e.target.value) })} /></label>
      <label><span className={labelClass}>Number of questions (max 10)</span>
        <input aria-label="AI count" type="number" min={1} max={10} className={inputClass} value={params.count} disabled={busy} onChange={e => set({ count: Number(e.target.value) })} /></label>
      <label><span className={labelClass}>Language</span>
        <select aria-label="AI language" className={inputClass} value={params.language} disabled={busy} onChange={e => set({ language: e.target.value })}>
          {LANGUAGES.map(l => <option key={l}>{l}</option>)}</select></label>
      <label className="sm:col-span-2 lg:col-span-4"><span className={labelClass}>Teacher instructions (optional)</span>
        <input aria-label="AI instructions" className={inputClass} maxLength={1000} placeholder="e.g. Use Indian real-life contexts; avoid trigonometry" value={params.instructions}
          disabled={busy} onChange={e => set({ instructions: e.target.value })} /></label>
    </div>
    <p className="text-[11px] text-content-secondary">The AI writes formulas as LaTeX and they are shown typeset. {MATH_HINT}</p>
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="teal" disabled={busy || !subject || params.topic.trim().length < 2} loading={busy && regenerating === null} onClick={generate}>
        {busy && regenerating === null ? `Generating with ${modelName}...` : drafts.length ? 'Regenerate all' : 'Generate'}</Button>
      {busy && <span role="status" className="text-sm text-content-secondary">{params.provider === 'qwen' ? 'Qwen is writing the questions on this server - this can take a few minutes.' : 'Waiting for Gemini - this can take up to a minute.'}</span>}
    </div>

    {meta && <div className="space-y-1 rounded-lg border border-amber-200 bg-amber-50/50 px-3 py-2 text-xs text-content-secondary">
      <p data-testid="ai-provenance"><span className="font-semibold text-amber-800">New questions generated just now by {meta.provider} / {meta.model}</span>{' - '}
        {meta.generated} of {meta.requested} requested, from {meta.attempts} AI request(s). Checked against {meta.checked_against} existing
        {' '}{subjectName(subject)} bank question(s): none of the questions below are copies of them.
        {meta.discarded > 0 && ` Rejected: ${meta.rejected_duplicates} bank duplicate(s), ${meta.rejected_repeats} repeat(s), ${meta.rejected_invalid} invalid.`}</p>
      {meta.warnings.length > 0 && <ul className="ml-4 list-disc">{meta.warnings.map((w: string, i: number) => <li key={i}>{w}</li>)}</ul>}
    </div>}
    {meta && drafts.length === 0 && <Empty>{savedCount > 0 ? `All approved questions were saved to the question bank below. Generate again for more.` : 'All generated questions were rejected. Generate again to get new ones.'}</Empty>}
    <ol className="space-y-3">{drafts.map((d, index) => <li key={d.key}
      className={'rounded-lg border p-3 ' + (d.approved ? 'border-teal-400 bg-teal-50/30' : 'border-surface-border')}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label className="flex items-center gap-2 text-sm font-medium"><input type="checkbox" checked={d.approved}
          onChange={e => setDrafts(ds => ds.map(x => x.key === d.key ? { ...x, approved: e.target.checked } : x))} />
          Approve question {index + 1}</label>
        <span className="flex items-center gap-2 text-xs text-content-secondary"><CompetencyTag code={d.q.competency} />{d.q.bloom_level} - {d.q.question_type} -
          <span className="font-semibold text-amber-700">AI-generated</span></span>
        <span className="flex gap-1">
          <Button size="sm" variant="outline" disabled={busy} loading={regenerating === d.key} onClick={() => regenerateOne(d.key)}>Regenerate</Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => setDrafts(ds => ds.filter(x => x.key !== d.key))}>Reject</Button>
        </span>
      </div>
      <label className="mt-2 block"><span className={labelClass}>Question</span>
        <textarea aria-label={`AI question ${index + 1} text`} rows={2} className={inputClass} value={d.q.text} onChange={e => update(d.key, { text: e.target.value })} /></label>
      <MathPreview text={d.q.text} />
      {d.q.question_type === 'mcq' && <div className="mt-2">
        <OptionsEditor idPrefix={`ai-${d.key}`} labelPrefix={`AI question ${index + 1} option`} options={d.q.options} correct={d.q.correct_answer}
          onChange={(options, correct_answer) => update(d.key, { options, correct_answer })} />
        {d.q.options.some((o: string) => /\\[([a-zA-Z]/.test(o)) && <div className="mt-1 flex flex-wrap gap-2 text-sm">{d.q.options.map((o: string, i: number) =>
          <span key={i} className={'rounded border px-2 py-0.5 ' + (o === d.q.correct_answer ? 'border-emerald-300 bg-emerald-50' : 'border-surface-border')}>
            {String.fromCharCode(65 + i)}. <MathText text={o} /></span>)}</div>}
      </div>}
      <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_1fr_6rem]">
        {d.q.question_type !== 'mcq' && <label><span className={labelClass}>Correct answer</span>
          <textarea aria-label={`AI question ${index + 1} answer`} rows={2} className={inputClass} value={d.q.correct_answer} onChange={e => update(d.key, { correct_answer: e.target.value })} /></label>}
        <label className={d.q.question_type === 'mcq' ? 'sm:col-span-2' : ''}><span className={labelClass}>Marking rubric</span>
          <textarea aria-label={`AI question ${index + 1} rubric`} rows={2} className={inputClass} value={d.q.marking_rubric} onChange={e => update(d.key, { marking_rubric: e.target.value })} /></label>
        <label><span className={labelClass}>Marks</span>
          <input aria-label={`AI question ${index + 1} marks`} type="number" min={1} max={20} className={inputClass} value={d.q.marks} onChange={e => update(d.key, { marks: Number(e.target.value) })} /></label>
      </div>
      {d.q.explanation && <p className="mt-1 text-xs text-content-secondary">Explanation (saved with the rubric): <MathText text={d.q.explanation} /></p>}
    </li>)}</ol>
    {drafts.length > 0 && <div className="flex flex-wrap items-center gap-2 border-t border-surface-border pt-3">
      <Button variant="primary" disabled={busy || approved.length === 0} onClick={() => run(async () => {
        const unkeyed = approved.findIndex(d => d.q.question_type === 'mcq' && !d.q.options.includes(d.q.correct_answer));
        if (unkeyed >= 0) throw new Error(`Question ${drafts.indexOf(approved[unkeyed]) + 1}: choose its correct option before saving.`);
        const res = await apiClient.assessments.aiSaveQuestions(subject, approved.map(d => d.q), meta?.model, params.topic.trim());
        setDrafts(ds => ds.filter(d => !d.approved)); setSavedCount(c => c + res.saved_count); await onSaved(subject);
        return `${res.saved_count} approved question(s) saved to the ${subjectName(subject)} question bank under topic "${params.topic.trim()}".`;
      })}>Save {approved.length} approved to question bank</Button>
      <span className="text-xs text-content-secondary">Unapproved questions stay here and are not saved.</span>
    </div>}
  </Section>;
};
