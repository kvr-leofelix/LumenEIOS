/**
 * The full available syllabus for one class and subject with teaching coverage, rendered inside the Curriculum Catalogue.
 *
 * One syllabus source of truth: the planning syllabus datasets (src/lib/planning/syllabus.ts), which the Time-Aware Engine
 * schedules from. Topic identities therefore match across both modules. One coverage state per teacher and topic, read and
 * written only through the relational teacher-plan API (useTeacherCoverage); the workspace document holds no coverage. Exactly three statuses; no source-quality, approval or publication UI.
 */
import React, { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import {
  COVERAGE_COLOR,
  COVERAGE_LABEL,
  COVERAGE_STATUSES,
  chapterStatus,
  executionEvidence,
  statusOf,
  summarizeStatuses,
  type CoverageStatus,
} from '../../../lib/planning/coverage';
import type { PlanningSubject } from '../../../lib/planning/calendar';
import { defaultDatasetFor, syllabusFor, SCHEDULABLE_KINDS, type SyllabusNode } from '../../../lib/planning/syllabus';
import { usePlanning } from '../../../lib/planning/usePlanning';
import { describeError } from '../../../lib/teacherPlanApi';
import { nodeIdOf, useTeacherCoverage } from '../../teacherPlan/useTeacherCoverage';
import { ROMAN, SUBJECT_LABEL, type GradeNumber, type SubjectKey } from '../types';

/** The catalogue's subject keys map onto the planning engine's subject names (same subjects, same topics). */
export const toPlanningSubject = (s: SubjectKey): PlanningSubject => (s === 'science' ? 'Science' : 'Mathematics');

type ClassValue = 'core' | 'mixed' | 'non_core';
const CLASS_VALUES: ClassValue[] = ['core', 'mixed', 'non_core'];
const CLASS_LABEL: Record<ClassValue, string> = { core: 'Core', mixed: 'Mixed', non_core: 'Non-Core' };

export const CoverageDot: React.FC<{ status: CoverageStatus; testId?: string }> = ({ status, testId }) => (
  <span aria-hidden="true" data-testid={testId} data-status={status} className="inline-block w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: COVERAGE_COLOR[status] }} />
);

export const CoverageSyllabus: React.FC<{ grade: GradeNumber; subject: SubjectKey }> = ({ grade, subject }) => {
  const p = usePlanning();
  const subjectName = toPlanningSubject(subject);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [error, setError] = useState('');
  const tc = useTeacherCoverage(grade, subjectName);
  const canEdit = tc.canEdit;

  const view = useMemo(() => syllabusFor(defaultDatasetFor(p.datasets, grade, subjectName), grade, subjectName), [p.datasets, grade, subjectName]);
  const coverage = tc.coverage;
  const evidence = useMemo(() => executionEvidence(p.workspace.plans), [p.workspace.plans]);

  const structure = useMemo(() => {
    const byId = new Map(view.nodes.map((n) => [n.id, n]));
    const unitIds = new Set(view.units.map((u) => u.id));
    const chapterOf = (n: SyllabusNode): string | null => {
      let cur: SyllabusNode | undefined = n;
      while (cur && cur.kind !== 'CHAPTER') cur = cur.parentId ? byId.get(cur.parentId) : undefined;
      return cur ? cur.id : null;
    };
    const depth = (n: SyllabusNode): number => {
      let d = 0;
      let cur = n.parentId ? byId.get(n.parentId) : undefined;
      while (cur && cur.kind !== 'CHAPTER') {
        d += 1;
        cur = cur.parentId ? byId.get(cur.parentId) : undefined;
      }
      return d;
    };
    return view.chapters.map((ch) => {
      const entries = view.nodes
        .filter((n) => SCHEDULABLE_KINDS.includes(n.kind) && chapterOf(n) === ch.id)
        .map((n) => ({ node: n, depth: depth(n), eligible: unitIds.has(n.id) }));
      return { chapter: ch, entries, units: entries.filter((e) => e.eligible).map((e) => e.node) };
    });
  }, [view]);

  const summary = useMemo(() => summarizeStatuses(view.units.map((u) => statusOf(coverage, u.id))), [view, coverage]);

  const planRows = useMemo(() => new Map((tc.plan?.topics ?? []).map((t) => [nodeIdOf(t.topic_key), t])), [tc.plan]);
  const [savedNote, setSavedNote] = useState('');
  const changeClassification = async (node: SyllabusNode, value: ClassValue) => {
    const current = planRows.get(node.id);
    if (!canEdit || saving[node.id] || !current || current.classification === value) return;
    setError('');
    setSavedNote('');
    setSaving((s) => ({ ...s, [node.id]: true }));
    try {
      await tc.setClassification(node.id, value);
      setSavedNote(`Saved: ${node.number ? node.number + ' ' : ''}${node.title} is now ${CLASS_LABEL[value]}.`);
    } catch (e) {
      setError(describeError(e).message);
    }
    setSaving((s) => ({ ...s, [node.id]: false }));
  };

  const change = async (node: SyllabusNode, status: CoverageStatus) => {
    if (!canEdit || saving[node.id] || statusOf(coverage, node.id) === status) return;
    setError('');
    setSavedNote('');
    setSaving((s) => ({ ...s, [node.id]: true }));
    try {
      await tc.set(node.id, status, 'MANUAL');
      setSavedNote(`Saved: ${node.number ? node.number + ' ' : ''}${node.title} is now ${COVERAGE_LABEL[status]}.`);
    } catch (e) {
      setError(describeError(e).message);
    }
    setSaving((s) => ({ ...s, [node.id]: false }));
  };

  return (
    <div className="space-y-4" data-testid="syllabus-view">
      {p.mode === 'loading' && <div className="text-xs text-content-secondary" role="status">Loading syllabus coverage…</div>}
      {p.mode === 'error' && (
        <div className="text-xs text-rose-800 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2" role="alert">
          {p.error} <button className="underline font-semibold" onClick={() => p.reload()}>Retry</button>
        </div>
      )}
      {tc.error && (
        <div className="text-xs text-rose-800 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2" role="alert">
          {tc.error} Coverage is stored on the LumenEIOS backend and cannot be changed while it is unreachable.
        </div>
      )}
      {!tc.teacherId && <p className="text-xs text-content-muted" data-testid="coverage-needs-teacher">Coverage belongs to a teacher. Open a teacher from Curriculum Oversight to see theirs.</p>}

      <div className="bg-white p-5 rounded-2xl border border-surface-border shadow-subtle space-y-3" data-testid="coverage-overview">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-base font-bold text-navy-900">Class {ROMAN[grade]} · {subjectName}</h2>
          <p className="text-sm text-navy-900"><span className="font-bold text-2xl" data-testid="coverage-percent">{summary.percent}%</span> covered</p>
        </div>
        {tc.plan && (
          <p className="text-xs text-content-secondary" data-testid="plan-context">
            Editing the plan of <b data-testid="plan-teacher">{tc.plan.teacher_name || tc.teacherId}</b> · Class {ROMAN[grade]} (grade {grade}) · {subjectName} · academic year {tc.plan.academic_year || '—'}. Every Core / Non-Core and coverage value below is the saved value.
          </p>
        )}
        <div className="h-2.5 rounded-full bg-gray-100 overflow-hidden" role="progressbar" aria-valuenow={summary.percent} aria-valuemin={0} aria-valuemax={100} aria-label="Syllabus coverage">
          <div className="h-full rounded-full" style={{ width: `${summary.percent}%`, backgroundColor: COVERAGE_COLOR.DONE }} />
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <span className="inline-flex items-center gap-2"><CoverageDot status="DONE" /> Done <b data-testid="coverage-done">{summary.done}</b></span>
          <span className="inline-flex items-center gap-2"><CoverageDot status="IN_PROGRESS" /> In progress <b data-testid="coverage-inprogress">{summary.inProgress}</b></span>
          <span className="inline-flex items-center gap-2"><CoverageDot status="NOT_DONE" /> Not done <b data-testid="coverage-notdone">{summary.notDone}</b></span>
          <span className="text-content-muted">of <b data-testid="coverage-total">{summary.total}</b> topics</span>
        </div>
        {!canEdit && <p className="text-[11px] text-content-muted">Coverage is read-only: only the owning teacher can change it.</p>}
      </div>

      {error && <p className="text-xs text-rose-700" role="alert">{error}</p>}
      {savedNote && <p className="text-xs text-teal-700" role="status" data-testid="saved-note">{savedNote}</p>}

      {structure.length === 0 ? (
        <div className="bg-white p-5 rounded-2xl border border-surface-border text-sm text-content-secondary" data-testid="empty-syllabus">
          No syllabus is available for Class {ROMAN[grade]} {subjectName}.
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex justify-end gap-3 text-[11px]">
            <button className="underline text-teal-700" onClick={() => setOpen(Object.fromEntries(structure.map((c) => [c.chapter.id, true])))}>Expand all</button>
            <button className="underline text-teal-700" onClick={() => setOpen({})}>Collapse all</button>
          </div>
          {structure.map(({ chapter, entries, units }) => {
            const statuses = units.map((u) => statusOf(coverage, u.id));
            const cs = chapterStatus(statuses);
            const done = statuses.filter((s) => s === 'DONE').length;
            const isOpen = !!open[chapter.id];
            return (
              <div key={chapter.id} className="bg-white rounded-xl border border-surface-border" data-testid={`chapter-${chapter.id}`}>
                <button type="button" className="w-full flex items-center gap-3 px-4 py-3 text-left" aria-expanded={isOpen} onClick={() => setOpen((o) => ({ ...o, [chapter.id]: !o[chapter.id] }))}>
                  {isOpen ? <ChevronDown className="w-4 h-4 shrink-0" /> : <ChevronRight className="w-4 h-4 shrink-0" />}
                  <span className="flex-1 min-w-0">
                    <span className="block font-semibold text-navy-900 break-words">{chapter.number ? `Chapter ${chapter.number}: ` : ''}{chapter.title}</span>
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-xs shrink-0" data-testid={`chapter-status-${chapter.id}`} data-status={cs ?? 'EMPTY'}>
                    {cs ? <><CoverageDot status={cs} /> {COVERAGE_LABEL[cs]}</> : <span className="text-content-muted">No topics</span>}
                  </span>
                  <span className="text-xs text-content-muted shrink-0" data-testid={`chapter-count-${chapter.id}`}>{done} of {units.length}</span>
                </button>
                {isOpen && (
                  <ul className="border-t border-surface-border divide-y divide-surface-border">
                    {entries.length === 0 && <li className="px-4 py-3 text-xs text-content-muted">No topics are listed for this chapter.</li>}
                    {entries.map(({ node, depth, eligible }) => {
                      const status = statusOf(coverage, node.id);
                      const rec = coverage[node.id];
                      const ev = evidence[node.id];
                      return (
                        <li key={node.id} className="px-4 py-2.5 flex flex-wrap items-center gap-x-4 gap-y-1" style={{ paddingLeft: `${1 + depth * 1.25}rem` }} data-testid={`topic-${node.id}`}>
                          <span className="flex-1 min-w-[180px]">
                            <span className={eligible ? 'text-sm text-navy-900' : 'text-sm font-semibold text-navy-900'}>{node.number ? `${node.number} ` : ''}{node.title}</span>
                            {eligible && rec?.source === 'EXECUTION' && <span className="block text-[11px] text-content-muted">Coverage from classroom teaching records.</span>}
                            {eligible && rec?.source === 'MANUAL' && <span className="block text-[11px] text-content-muted">Manual coverage{ev?.taughtPeriods ? ` · ${ev.taughtPeriods} classroom period(s) recorded` : ' · no classroom periods recorded'}.</span>}
                            {eligible && ev?.complete && status !== 'DONE' && <span className="block text-[11px] text-amber-800">Classroom records show this topic as taught.</span>}
                          </span>
                          {eligible && (
                            <span className="inline-flex items-center gap-2" data-testid={`class-${node.id}`} data-classification={planRows.get(node.id)?.classification ?? 'none'}>
                              {planRows.get(node.id) ? (
                                <select
                                  aria-label={`Core or Non-Core for ${node.number ? node.number + ' ' : ''}${node.title}`}
                                  className="text-xs rounded-lg border border-surface-border bg-white px-2 py-1.5 font-medium disabled:opacity-60"
                                  value={planRows.get(node.id)!.classification}
                                  disabled={!canEdit || !!saving[node.id]}
                                  title={canEdit ? 'Change the classification' : 'Only the owning teacher can change classifications.'}
                                  onChange={(e) => changeClassification(node, e.target.value as ClassValue)}
                                >
                                  {CLASS_VALUES.map((v) => (
                                    <option key={v} value={v}>{CLASS_LABEL[v]}</option>
                                  ))}
                                </select>
                              ) : tc.plan ? (
                                <span className="text-xs font-semibold text-rose-700" data-testid={`unconfigured-${node.id}`} title="No saved configuration exists for this topic in this teacher's plan.">Not configured</span>
                              ) : null}
                            </span>
                          )}
                          {eligible && (
                            <span className="inline-flex items-center gap-2" data-testid={`status-${node.id}`} data-status={status}>
                              <CoverageDot status={status} testId={`dot-${node.id}`} />
                              <select
                                aria-label={`Coverage status for ${node.number ? node.number + ' ' : ''}${node.title}`}
                                className="text-xs rounded-lg border bg-white px-2 py-1.5 font-medium disabled:opacity-60"
                                style={{ borderColor: COVERAGE_COLOR[status], color: status === 'NOT_DONE' ? '#4B5563' : COVERAGE_COLOR[status] }}
                                value={status}
                                disabled={!canEdit || !!saving[node.id]}
                                title={canEdit ? '' : 'Only a teacher or Admin can update coverage.'}
                                onChange={(e) => change(node, e.target.value as CoverageStatus)}
                              >
                                {COVERAGE_STATUSES.map((s) => (
                                  <option key={s} value={s}>{COVERAGE_LABEL[s]}</option>
                                ))}
                              </select>
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
