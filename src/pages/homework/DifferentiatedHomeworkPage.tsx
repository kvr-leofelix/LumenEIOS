import React from 'react';
import { Sparkles } from 'lucide-react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { DEMO_MODE } from '../../lib/runtime';
import { TeacherWorkspace } from './TeacherWorkspace';
import { StudentWorkspace } from './StudentWorkspace';
import { ParentWorkspace } from './ParentWorkspace';
import { RemediationManager } from '../teacher/RemediationManager';

const EDUCATOR_ROLES = ['developer', 'admin', 'principal', 'teacher'];

/**
 * Host-app Differentiated Homework tab.
 * Reuses the main layout/auth; loads the live homework workspaces by role.
 * Offline demo mode keeps the legacy RemediationManager (no backend).
 */
export const DifferentiatedHomeworkPage: React.FC = () => {
  const { currentUser, isLoading, currentSchoolId } = useAuth();
  if (isLoading) return <p role="status" className="p-2 text-sm text-content-secondary">Checking session…</p>;
  if (!currentUser) return <Navigate to="/login" replace />;

  if (DEMO_MODE) {
    return (
      <div className="space-y-4">
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Offline demonstration mode: showing the legacy remediation board. Sign in with the live API
          (<code className="font-mono text-xs">VITE_DEMO_MODE=false</code>) to use Differentiated Homework
          assignment, submission, evaluation and Gemini question generation.
        </p>
        <RemediationManager />
      </div>
    );
  }

  const body = EDUCATOR_ROLES.includes(currentUser.role)
    ? <TeacherWorkspace />
    : currentUser.role === 'student'
      ? <StudentWorkspace />
      : currentUser.role === 'parent'
        ? <ParentWorkspace />
        : <p className="text-sm text-content-secondary">This account cannot access Differentiated Homework.</p>;

  return (
    <div className="space-y-4" key={`${currentUser.id}:${currentSchoolId}`}>
      <header className="flex items-start gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-navy-700 text-white shadow-md">
          <Sparkles className="h-5 w-5" />
        </span>
        <div>
          <h1 className="text-xl font-bold text-navy-800">Differentiated Homework</h1>
          <p className="text-sm text-content-secondary">
            {EDUCATOR_ROLES.includes(currentUser.role)
              ? 'Homework personalised to each student’s weakest competencies. Create, review, assign and mark it here.'
              : currentUser.role === 'student'
                ? 'Homework your teacher chose for you. Save as you go and submit when you are done.'
                : 'Homework assigned to your child and the results their teacher has released.'}
          </p>
        </div>
      </header>
      {body}
    </div>
  );
};
