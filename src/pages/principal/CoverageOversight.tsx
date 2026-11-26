import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { CoverageBar, StatusBox } from '../../features/teacherPlan/StatusBox';
import { useRemote } from '../../features/teacherPlan/useRemote';
import { teacherPlanApi } from '../../lib/teacherPlanApi';
import { PageHeader, selectCls, tdCls, thCls } from '../time-aware/planningUi';

const ROMAN: Record<number, string> = { 6: 'VI', 7: 'VII', 8: 'VIII' };

/** Curriculum Oversight: each teacher's own coverage, never merged. Rows open that teacher in the Catalogue. */
export const CoverageOversight: React.FC = () => {
  const [grade, setGrade] = useState('');
  const [subject, setSubject] = useState('');
  const [teacher, setTeacher] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const { data, error, loading } = useRemote(
    () => teacherPlanApi.curriculumOversight({ grade: grade ? Number(grade) : undefined, subject: subject || undefined, teacher_id: teacher || undefined }),
    [grade, subject, teacher],
  );
  const teachers = data ? Array.from(new Map(data.rows.map((r) => [r.teacher_id, r.teacher_name]))) : [];
  return (
    <div className="space-y-4" data-testid="coverage-oversight">
      <PageHeader title="Curriculum Oversight" subtitle="Actual syllabus coverage, one row per teacher." />
      <div className="bg-white p-3 rounded-xl border border-surface-border flex flex-wrap gap-3 text-xs">
        <select aria-label="Class" className={selectCls} value={grade} onChange={(e) => setGrade(e.target.value)}>
          <option value="">All classes</option>
          {[6, 7, 8].map((g) => (
            <option key={g} value={g}>
              Class {ROMAN[g]}
            </option>
          ))}
        </select>
        <select aria-label="Subject" className={selectCls} value={subject} onChange={(e) => setSubject(e.target.value)}>
          <option value="">All subjects</option>
          <option>Mathematics</option>
          <option>Science</option>
        </select>
        <select aria-label="Teacher" className={selectCls} value={teacher} onChange={(e) => setTeacher(e.target.value)}>
          <option value="">All teachers</option>
          {teachers.map(([id, n]) => (
            <option key={id} value={id}>
              {n}
            </option>
          ))}
        </select>
      </div>
      {error && (
        <p role="alert" className="text-xs text-rose-700">
          {error}
        </p>
      )}
      {loading && <p className="text-xs text-content-muted">Loading…</p>}
      {data && (
        <div className="bg-white rounded-xl border border-surface-border overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr>
                {['Teacher', 'Class', 'Subject', 'Eligible', 'Done', 'In progress', 'Not done', 'Coverage'].map((h) => (
                  <th key={h} className={thCls}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.length === 0 && (
                <tr>
                  <td className={tdCls} colSpan={8}>
                    No teacher plans in this school yet.
                  </td>
                </tr>
              )}
              {data.rows.map((r) => {
                const k = `${r.teacher_id}|${r.grade}|${r.subject}`;
                return (
                  <React.Fragment key={k}>
                    <tr className="hover:bg-surface-bg" data-testid="coverage-row">
                      <td className={tdCls}>
                        <button type="button" className="mr-2 text-content-muted" aria-expanded={open === k} aria-label={`Toggle chapters for ${r.teacher_name}`} onClick={() => setOpen(open === k ? null : k)}>
                          {open === k ? '▾' : '▸'}
                        </button>
                        <Link className="font-semibold text-teal-700 underline" to={`/curriculum/catalogue/${r.grade}/${r.subject.toLowerCase()}?teacher=${r.teacher_id}`}>
                          {r.teacher_name}
                        </Link>
                      </td>
                      <td className={tdCls}>{ROMAN[r.grade]}</td>
                      <td className={tdCls}>{r.subject}</td>
                      <td className={tdCls}>{r.eligible}</td>
                      <td className={tdCls}>{r.done}</td>
                      <td className={tdCls}>{r.in_progress}</td>
                      <td className={tdCls}>{r.not_done}</td>
                      <td className={`${tdCls} w-40`}>
                        <div className="flex items-center gap-2">
                          <span className="w-10 text-right">{r.percent}%</span>
                          <CoverageBar {...r} />
                        </div>
                      </td>
                    </tr>
                    {open === k &&
                      r.chapters.map((c) => (
                        <tr key={c.chapter_number} className="bg-surface-bg" data-testid="chapter-row">
                          <td className={tdCls} colSpan={3}>
                            Ch. {c.chapter_number} · {c.chapter_title}
                          </td>
                          <td className={tdCls} colSpan={4}>
                            <div className="flex flex-wrap gap-1">
                              {c.topics.map((t) => (
                                <StatusBox key={t.topic_key} status={t.status} title={t.section} />
                              ))}
                            </div>
                          </td>
                          <td className={tdCls}>
                            <CoverageBar {...c.stats} />
                          </td>
                        </tr>
                      ))}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <Link className="text-xs font-semibold text-teal-700 underline" to="/logs?category=coverage_status">
        Coverage history →
      </Link>
    </div>
  );
};
