import React, { useCallback, useEffect, useState } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { Badge } from '../../components/common/Badge';
import { MathText } from '../../components/common/MathText';
import { apiClient } from '../../lib/apiClient';
import { sameAnswer } from '../../lib/mathText';

// Shared helpers for the live homework workspaces. All data comes from the live API;
// nothing here is synthetic.

export const enc = encodeURIComponent;
export const errorText = (error: unknown) => error instanceof Error ? error.message : 'Request failed.';
export const inputClass = 'w-full rounded-lg border border-surface-border bg-white px-3 py-2 text-sm shadow-sm transition focus:border-teal-400 focus:outline-none focus:ring-2 focus:ring-teal-400/40 disabled:bg-gray-50 disabled:text-content-secondary';
export const labelClass = 'block text-xs font-semibold uppercase tracking-wide text-content-secondary mb-1';

export function formatDate(value?: string | null): string {
  if (!value) return 'No due date';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

/** Runs one request at a time, exposing busy/error/notice state for a panel. */
export function useRunner() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const run = useCallback(async (operation: () => Promise<void | string>) => {
    setBusy(true); setError(''); setNotice('');
    try { const message = await operation(); if (typeof message === 'string') setNotice(message); }
    catch (ex) { setError(errorText(ex)); }
    finally { setBusy(false); }
  }, []);
  return { busy, error, notice, run, setError, setNotice };
}

/** Subject id -> display name for educators (from the school's class/subject targets). */
export function useSubjectNames() {
  const [names, setNames] = useState<Record<string, string>>({});
  useEffect(() => {
    let active = true;
    apiClient.assessments.targets().then(rows => {
      if (!active) return;
      const map: Record<string, string> = {};
      rows.forEach((c: any) => (c.subjects || []).forEach((s: any) => { map[s.id] = s.name; }));
      setNames(map);
    }).catch(() => undefined);
    return () => { active = false; };
  }, []);
  return useCallback((id?: string | null) => (id ? names[id] ?? id : ''), [names]);
}

export const Messages: React.FC<{ error?: string; notice?: string }> = ({ error, notice }) => <>
  {error ? <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}
  {notice ? <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{notice}</p> : null}
</>;

export const Section: React.FC<{ title: React.ReactNode; subtitle?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode; className?: string }> =
  ({ title, subtitle, action, children, className }) => <section className={'rounded-2xl border border-surface-border bg-white shadow-subtle ' + (className ?? '')}>
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-border px-5 py-3.5">
      <div className="min-w-0"><h2 className="text-base font-semibold text-content-primary">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-content-secondary">{subtitle}</p>}</div>
      {action}
    </header>
    <div className="space-y-4 p-5">{children}</div>
  </section>;

export const Empty: React.FC<{ children: React.ReactNode; icon?: React.ReactNode }> = ({ children, icon }) =>
  <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-surface-border bg-surface-bg/40 px-4 py-8 text-center text-sm text-content-secondary">
    {icon && <span className="text-content-secondary/70">{icon}</span>}
    <div>{children}</div>
  </div>;

const STATUS_VARIANTS: Record<string, 'default' | 'success' | 'warning' | 'danger' | 'info' | 'teal'> = {
  draft: 'warning', approved: 'info', rejected: 'danger', assigned: 'teal',
  not_started: 'default', in_progress: 'warning', submitted: 'success',
  pending: 'warning', marked: 'info', released: 'success',
};
const STATUS_LABELS: Record<string, string> = {
  draft: 'Needs review', not_started: 'Not started', in_progress: 'In progress', marked: 'Marked', pending: 'Marking',
};

export const StatusBadge: React.FC<{ status: string }> = ({ status }) =>
  <Badge variant={STATUS_VARIANTS[status] ?? 'default'} size="sm" dot>{STATUS_LABELS[status] ?? status[0].toUpperCase() + status.slice(1)}</Badge>;

// Same names as components/common/CompetencyScoreBadge.tsx.
export const COMPETENCY_NAMES: Record<string, string> = {
  LU: 'Language Understanding', CU: 'Concept Understanding', AU: 'Application Understanding', CT: 'Critical Thinking',
};
const COMPETENCY_COLOURS: Record<string, string> = {
  LU: 'bg-sky-50 text-sky-800 ring-sky-200', CU: 'bg-violet-50 text-violet-800 ring-violet-200',
  AU: 'bg-amber-50 text-amber-800 ring-amber-200', CT: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
};
export const CompetencyTag: React.FC<{ code: string; long?: boolean }> = ({ code, long }) =>
  <span title={COMPETENCY_NAMES[code] ?? code}
    className={'inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-semibold ring-1 ring-inset ' + (COMPETENCY_COLOURS[code] ?? 'bg-navy-50 text-navy-800 ring-navy-100')}>
    {long ? `${code} · ${COMPETENCY_NAMES[code] ?? code}` : code}</span>;

export const BLOOM = ['Remember', 'Understand', 'Apply', 'Analyze', 'Evaluate', 'Create'];
export const QUESTION_TYPES: [string, string][] = [
  ['mcq', 'Multiple choice'], ['short', 'Short answer'], ['descriptive', 'Long answer'], ['practical', 'Practical / problem'],
];
export const typeLabel = (type: string) => QUESTION_TYPES.find(([v]) => v === type)?.[1] ?? type;
export const letter = (i: number) => String.fromCharCode(65 + i);

export function answerText(q: { answer_text?: string | null; selected_option_index?: number | null; options?: unknown[] }): string {
  if (q.answer_text) return q.answer_text;
  if (q.selected_option_index != null) return String(q.options?.[q.selected_option_index] ?? `Option ${q.selected_option_index + 1}`);
  return 'Not answered';
}

/** Read-only MCQ options, with the keyed option highlighted when `correct` is given (teachers only). */
export const OptionList: React.FC<{ options: unknown[]; correct?: string | null; selected?: number | null }> = ({ options, correct, selected }) =>
  <ul className="mt-2 grid gap-1.5 sm:grid-cols-2">
    {options.map((o, i) => {
      const text = String(o);
      const isKey = correct != null && sameAnswer(text, String(correct));
      const isPicked = selected === i;
      return <li key={i} className={'flex items-start gap-2 rounded-lg border px-2.5 py-1.5 text-sm ' +
        (isKey ? 'border-emerald-300 bg-emerald-50/70 text-emerald-950' : isPicked ? 'border-sky-300 bg-sky-50' : 'border-surface-border bg-surface-bg/40')}>
        <span className="font-semibold text-content-secondary">{letter(i)}.</span>
        <MathText text={text} className="min-w-0 flex-1" />
        {isKey && <CheckCircle2 aria-label="Correct answer" className="h-4 w-4 shrink-0 text-emerald-600" />}
      </li>;
    })}
  </ul>;

/** Released result. Shared by the student and parent views (same server serializer). */
export const ReleasedResult: React.FC<{ result: any }> = ({ result }) => {
  const pct = result.total_max ? Math.round((result.total_awarded / result.total_max) * 100) : 0;
  const tone = pct >= 75 ? 'text-emerald-700' : pct >= 50 ? 'text-amber-700' : 'text-rose-700';
  return <div className="rounded-2xl border border-emerald-200 bg-gradient-to-br from-emerald-50/70 to-white p-4">
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <h3 className="font-semibold text-content-primary">Released teacher evaluation</h3>
      <p className="text-sm text-content-secondary">Released {formatDate(result.released_at)}</p>
    </div>
    <div className="mt-2 flex items-center gap-4">
      <p className={'text-3xl font-bold ' + tone}>{pct}%</p>
      <div className="flex-1">
        <p className="text-sm font-medium">{result.total_awarded} / {result.total_max} marks</p>
        <div className="mt-1 h-2 rounded-full bg-gray-100"><div className="h-2 rounded-full bg-emerald-500" style={{ width: `${pct}%` }} /></div>
      </div>
    </div>
    <ol className="mt-4 space-y-3">
      {result.items.map((q: any) => <li key={q.position} className="rounded-xl border border-surface-border bg-white p-3">
        <div className="flex justify-between gap-3"><p className="text-sm font-medium">{q.position}. <MathText text={q.text} /></p>
          <span className="shrink-0 rounded-md bg-surface-bg px-2 py-0.5 text-sm font-semibold">{q.awarded_marks} / {q.max_marks}</span></div>
        <p className="mt-1 text-sm text-content-secondary">Answer: <MathText text={answerText(q)} /></p>
        {q.feedback && <p className="mt-1 rounded-lg bg-teal-50 px-2 py-1 text-sm text-teal-900">Teacher feedback: <MathText text={q.feedback} /></p>}
      </li>)}
    </ol>
  </div>;
};

export type TabDef = { id: string; label: string; icon?: React.ReactNode; count?: number; hint?: string };

/** Step navigation. Keeps role="tab" so screen readers (and tests) can address each step by name. */
export const Tabs: React.FC<{ tabs: TabDef[] | [string, string][]; active: string; onChange: (id: string) => void }> = ({ tabs, active, onChange }) => {
  const defs: TabDef[] = (tabs as any[]).map(t => Array.isArray(t) ? { id: t[0], label: t[1] } : t);
  return <nav className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4" role="tablist" aria-label="Homework steps">
    {defs.map(t => {
      const on = active === t.id;
      return <button key={t.id} role="tab" aria-selected={on} onClick={() => onChange(t.id)}
        className={'group flex items-center gap-3 rounded-xl border px-3.5 py-2.5 text-left transition ' +
          (on ? 'border-navy-800 bg-navy-800 text-white shadow-md' : 'border-surface-border bg-white text-content-primary hover:border-teal-300 hover:bg-teal-50/40')}>
        {t.icon && <span className={'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ' + (on ? 'bg-white/15' : 'bg-surface-bg text-navy-700')}>{t.icon}</span>}
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold">{t.label}</span>
          {t.hint && <span className={'block truncate text-[11px] ' + (on ? 'text-white/75' : 'text-content-secondary')}>{t.hint}</span>}
        </span>
        {t.count != null && t.count > 0 && <span className={'rounded-full px-2 py-0.5 text-xs font-bold ' + (on ? 'bg-white text-navy-800' : 'bg-amber-100 text-amber-800')}>{t.count}</span>}
      </button>;
    })}
  </nav>;
};

/** Toggle button group (segmented control). */
export const Segmented: React.FC<{ value: string; onChange: (v: string) => void; options: [string, string][]; label: string }> =
  ({ value, onChange, options, label }) => <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg border border-surface-border bg-surface-bg p-0.5">
    {options.map(([v, l]) => <button key={v} type="button" role="radio" aria-checked={value === v} onClick={() => onChange(v)}
      className={'rounded-md px-3 py-1.5 text-sm font-medium transition ' + (value === v ? 'bg-white text-navy-900 shadow-sm' : 'text-content-secondary hover:text-content-primary')}>{l}</button>)}
  </div>;

/** Live typeset preview for teacher-entered text containing \( … \) formulas. */
export const MathPreview: React.FC<{ text?: string | null }> = ({ text }) =>
  text && /\\[([a-zA-Z]|\$/.test(text)
    ? <div className="rounded-lg border border-dashed border-teal-200 bg-teal-50/40 px-3 py-2 text-sm" aria-label="Formatted preview">
        <span className="mr-1 text-[11px] font-semibold uppercase tracking-wide text-teal-700">Preview</span><MathText text={text} />
      </div>
    : null;

export const MATH_HINT = <>Formulas: wrap them in <code className="rounded bg-gray-100 px-1">\( … \)</code>, e.g. <code className="rounded bg-gray-100 px-1">{'\\( \\frac{a}{b} \\)'}</code> or <code className="rounded bg-gray-100 px-1">{'\\( x^2 + 3x \\)'}</code>.</>;

/**
 * Editable MCQ options with one radio for the correct answer. Editing the keyed option keeps it keyed,
 * so the answer key can never drift away from the options.
 */
export const OptionsEditor: React.FC<{
  options: string[]; correct: string; disabled?: boolean; idPrefix: string; labelPrefix?: string;
  onChange: (options: string[], correct: string) => void;
}> = ({ options, correct, disabled, idPrefix, labelPrefix = 'Option', onChange }) => {
  const keyIndex = options.findIndex(o => o === correct);
  return <fieldset className="space-y-2">
    <legend className={labelClass}>Options - select the correct one</legend>
    {options.map((o, i) => <div key={i} className={'flex items-center gap-2 rounded-lg border p-1.5 ' + (i === keyIndex ? 'border-emerald-300 bg-emerald-50/50' : 'border-surface-border')}>
      <input type="radio" name={`${idPrefix}-correct`} aria-label={`${labelPrefix} ${letter(i)} is correct`} checked={i === keyIndex} disabled={disabled}
        onChange={() => onChange(options, o)} className="h-4 w-4 accent-emerald-600" />
      <span className="w-4 text-sm font-semibold text-content-secondary">{letter(i)}</span>
      <input aria-label={`${labelPrefix} ${letter(i)}`} className={inputClass} value={o} disabled={disabled}
        onChange={e => { const next = [...options]; next[i] = e.target.value; onChange(next, i === keyIndex ? e.target.value : correct); }} />
      {options.length > 2 && <button type="button" disabled={disabled} aria-label={`Remove ${labelPrefix.toLowerCase()} ${letter(i)}`}
        className="rounded px-2 text-lg leading-none text-content-secondary hover:bg-rose-50 hover:text-rose-700"
        onClick={() => { const next = options.filter((_, j) => j !== i); onChange(next, i === keyIndex ? '' : correct); }}>×</button>}
    </div>)}
    <div className="flex flex-wrap items-center gap-3">
      {options.length < 6 && <button type="button" disabled={disabled} className="text-sm font-medium text-teal-700 hover:underline"
        onClick={() => onChange([...options, ''], correct)}>+ Add option</button>}
      {keyIndex < 0 && <span className="text-xs font-medium text-amber-700">Choose the correct option.</span>}
    </div>
  </fieldset>;
};

export const StatCard: React.FC<{ label: string; value: React.ReactNode; tone?: 'amber' | 'sky' | 'violet' | 'emerald'; icon?: React.ReactNode; onClick?: () => void }> =
  ({ label, value, tone = 'sky', icon, onClick }) => {
    const tones = { amber: 'from-amber-50 text-amber-800', sky: 'from-sky-50 text-sky-800', violet: 'from-violet-50 text-violet-800', emerald: 'from-emerald-50 text-emerald-800' };
    const body = <>
      <span className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide opacity-80">{label}{icon}</span>
      <span className="mt-1 block text-2xl font-bold text-content-primary">{value}</span>
    </>;
    const cls = 'block w-full rounded-xl border border-surface-border bg-gradient-to-br to-white p-3 text-left ' + tones[tone];
    return onClick ? <button type="button" onClick={onClick} className={cls + ' transition hover:shadow-md'}>{body}</button> : <div className={cls}>{body}</div>;
  };
