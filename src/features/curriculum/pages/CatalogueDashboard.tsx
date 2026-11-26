import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Library } from 'lucide-react';
import { useAuth } from '../../../context/AuthContext';
import { hasPermission } from '../../../lib/permissions';
import { defaultDatasetFor, syllabusFor } from '../../../lib/planning/syllabus';
import { usePlanning } from '../../../lib/planning/usePlanning';
import { toPlanningSubject } from '../components/CoverageSyllabus';
import { UnauthorizedState } from '../components/StateViews';
import { GRADES, ROMAN, SUBJECTS, SUBJECT_LABEL, type GradeNumber } from '../types';

const Choice: React.FC<{ selected?: boolean; disabled?: boolean; onClick: () => void; title: string; sub?: string; testId?: string }> = ({ selected, disabled, onClick, title, sub, testId }) => (
  <button
    type="button"
    data-testid={testId}
    onClick={onClick}
    disabled={disabled}
    aria-pressed={!!selected}
    className={`text-left rounded-xl border px-4 py-3 min-w-[140px] transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 ${selected ? 'border-teal-600 bg-teal-50 ring-1 ring-teal-600' : 'border-surface-border bg-white hover:border-teal-400'} ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
  >
    <span className="block font-semibold text-navy-900">{title}</span>
    {sub && <span className="block text-[11px] text-content-muted mt-0.5">{sub}</span>}
  </button>
);

/** Curriculum Catalogue: SELECT CLASS -> SELECT SUBJECT -> the full syllabus and coverage (CatalogueCombinationPage). */
export const CatalogueDashboard: React.FC = () => {
  const { currentUser } = useAuth();
  const navigate = useNavigate();
  const p = usePlanning();
  const [grade, setGrade] = useState<GradeNumber | null>(null);

  const available = useMemo(() => {
    const out = new Set<string>();
    for (const g of GRADES) for (const s of SUBJECTS) if (syllabusFor(defaultDatasetFor(p.datasets, g, toPlanningSubject(s)), g, toPlanningSubject(s)).units.length > 0) out.add(`${g}-${s}`);
    return out;
  }, [p.datasets]);

  if (!currentUser || !hasPermission(currentUser.role, 'VIEW_CURRICULUM_CATALOGUE')) return <UnauthorizedState />;

  return (
    <div className="space-y-6 max-w-5xl mx-auto" data-testid="curriculum-catalogue">
      <div className="bg-white p-5 rounded-2xl border border-surface-border shadow-subtle">
        <div className="flex items-center gap-2">
          <Library className="w-5 h-5 text-teal-600" aria-hidden="true" />
          <h1 className="text-xl font-bold text-navy-900 tracking-tight">Curriculum Catalogue</h1>
        </div>
        <p className="text-xs text-content-secondary mt-1">Explore the syllabus and track teaching coverage.</p>
        <p className="text-[11px] text-content-muted mt-2" data-testid="demo-notice">Demonstration syllabus and coverage data.</p>
      </div>

      <section aria-labelledby="pick-class" className="space-y-2">
        <h2 id="pick-class" className="text-sm font-semibold text-navy-900">1. Select class</h2>
        <div className="flex flex-wrap gap-3" role="group" aria-label="Class">
          {GRADES.map((g) => (
            <Choice key={g} title={`Class ${ROMAN[g]}`} selected={grade === g} onClick={() => setGrade(g)} />
          ))}
        </div>
      </section>

      <section aria-labelledby="pick-subject" className="space-y-2">
        <h2 id="pick-subject" className="text-sm font-semibold text-navy-900">2. Select subject</h2>
        {grade === null ? (
          <p className="text-xs text-content-muted">Choose a class first.</p>
        ) : (
          <div className="flex flex-wrap gap-3" role="group" aria-label="Subject">
            {SUBJECTS.map((s) => (
              <Choice
                key={s}
                testId={`combo-${grade}-${s}`}
                title={SUBJECT_LABEL[s]}
                disabled={!available.has(`${grade}-${s}`)}
                sub={available.has(`${grade}-${s}`) ? undefined : 'No syllabus available'}
                onClick={() => navigate(`/curriculum/catalogue/${grade}/${s}`)}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
};
