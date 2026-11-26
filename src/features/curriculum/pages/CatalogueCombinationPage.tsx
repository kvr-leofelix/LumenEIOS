import React from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { useAuth } from '../../../context/AuthContext';
import { hasPermission } from '../../../lib/permissions';
import { CombinationSelector } from '../components/CombinationSelector';
import { CoverageSyllabus } from '../components/CoverageSyllabus';
import { TeacherPlanPanel } from '../../teacherPlan/TeacherPlanPanel';
import { UnauthorizedState } from '../components/StateViews';
import { ROMAN, SUBJECT_LABEL, parseGrade, parseSubject } from '../types';

/** The full available syllabus and teaching coverage for the selected class and subject. */
export const CatalogueCombinationPage: React.FC = () => {
  const params = useParams();
  const grade = parseGrade(params.grade);
  const subject = parseSubject(params.subject);
  const navigate = useNavigate();
  const { currentUser } = useAuth();

  if (!grade || !subject) return <Navigate to="/curriculum/catalogue" replace />;
  if (!currentUser || !hasPermission(currentUser.role, 'VIEW_CURRICULUM_CATALOGUE')) return <UnauthorizedState />;

  return (
    <div className="space-y-5 max-w-5xl mx-auto" data-testid="curriculum-catalogue">
      <div className="bg-white p-5 rounded-2xl border border-surface-border shadow-subtle space-y-3">
        <nav aria-label="Breadcrumb" className="text-xs text-content-secondary flex items-center gap-1">
          <Link to="/curriculum/catalogue" className="hover:text-teal-700 underline-offset-2 hover:underline">
            Curriculum Catalogue
          </Link>
          <ChevronRight className="w-3 h-3" aria-hidden="true" />
          <span aria-current="page" className="text-content-primary font-medium">
            Class {ROMAN[grade]} · {SUBJECT_LABEL[subject]}
          </span>
        </nav>
        <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-navy-900 tracking-tight">Curriculum Catalogue</h1>
            <p className="text-xs text-content-secondary mt-0.5">Explore the syllabus and track teaching coverage.</p>
            <p className="text-[11px] text-content-muted mt-1" data-testid="demo-notice">Demonstration syllabus and coverage data.</p>
          </div>
          <CombinationSelector grade={grade} subject={subject} onChange={(g, s) => navigate(`/curriculum/catalogue/${g}/${s}`)} />
        </div>
      </div>
      <TeacherPlanPanel grade={Number(grade)} subject={subject} />
      <CoverageSyllabus grade={grade} subject={subject} />
    </div>
  );
};
