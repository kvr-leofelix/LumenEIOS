import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GraduationCap, Sparkles, UploadCloud } from 'lucide-react';
import { StudentAssessments } from '../../components/common/StudentAssessments';
import { useData } from '../../context/DataContext';
import { demoMode, useAuth } from '../../context/AuthContext';
import { ApiError, apiClient } from '../../lib/apiClient';
import type { Student } from '../../types';
import { UnauthorizedPage } from '../shared/UnauthorizedPage';
import { Badge } from '../../components/common/Badge';
import { LearnerOverview } from '../../components/learner/LearnerOverview';
import { KnowledgeComponentGraph } from './KnowledgeComponentGraph';
import { CalendarOverview } from '../../features/calendar/CalendarOverview';
import { AnnouncementsOverview } from '../../features/announcements/AnnouncementsOverview';

export const StudentDashboard: React.FC = () => {
  const { currentUser } = useAuth();
  if (currentUser?.role !== 'student') return <UnauthorizedPage />;
  return <StudentProfile key={currentUser.id} showDemo={(demoMode || !!currentUser.demoRoot) && currentUser.id === 'user-student-1'} />;
};

function StudentProfile({ showDemo }: { showDemo: boolean }) {
  const { students } = useData();
  const [student, setStudent] = useState<Student | null>(null);
  const [error, setError] = useState('');
  const [unlinked, setUnlinked] = useState(false);

  useEffect(() => {
    let active = true;
    apiClient.student.profile().then((profile) => {
      if (active) setStudent(profile);
    }).catch((err) => {
      if (!active) return;
      if (err instanceof ApiError && err.status === 404) setUnlinked(true);
      else setError('Could not load your student profile. Refresh the page to try again.');
    });
    return () => { active = false; };
  }, []);

  const profile = student || (showDemo && unlinked ? students.find((s) => s.id === 'user-student-1') : null);
  if (profile) return <StudentDashboardContent student={profile} />;
  if (error || unlinked) return <p role="alert">{error || 'Your login has no linked student profile. Contact your school.'}</p>;
  return <p role="status">Loading your student profile…</p>;
}

function StudentDashboardContent({ student }: { student: Student }) {
  const navigate = useNavigate();
  const { classes, workspace, teachers, teacherAssignments, subjects, students } = useData();
  const live = students.find(s => s.id === student.id);
  const cls = classes.find(c => c.id === student.classId);
  const school = workspace?.schools[0];
  const myTeachers = teacherAssignments.filter(a => a.classId === student.classId)
    .map(a => ({ subject: subjects.find(s => s.id === a.subjectId)?.name ?? a.subjectId, name: teachers.find(t => t.id === a.teacherId)?.name ?? '' }))
    .sort((a, b) => a.subject.localeCompare(b.subject));

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-surface-border bg-gradient-to-r from-teal-50 to-white p-5 shadow-subtle">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
          <div className="flex items-start gap-3">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-teal-600 text-white"><GraduationCap className="h-6 w-6" /></span>
            <div>
              <h1 className="text-xl font-bold text-navy-900">Hello, {student.name}!</h1>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-content-secondary">
                <Badge variant="teal" size="sm">{cls?.name ?? student.className}</Badge>
                <span>Roll {student.rollNo}</span>
                {(live as any)?.admissionNo && <span>· Admission no. {(live as any).admissionNo}</span>}
                {cls?.classTeacherName && <span>· Class teacher {cls.classTeacherName}</span>}
                {school && <span>· {school.name}</span>}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => navigate('/upload')} className="inline-flex items-center gap-1.5 rounded-lg border border-surface-border bg-white px-3 py-2 text-sm font-semibold text-navy-900 hover:border-teal-400"><UploadCloud className="h-4 w-4" />Upload answers</button>
            <button onClick={() => navigate('/student/homework')} className="inline-flex items-center gap-1.5 rounded-lg bg-teal-600 px-3 py-2 text-sm font-semibold text-white hover:bg-teal-700"><Sparkles className="h-4 w-4" />My homework</button>
          </div>
        </div>
        {myTeachers.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2 border-t border-teal-100 pt-3 text-xs">
            {myTeachers.map(t => <span key={t.subject} className="rounded-lg bg-white px-2.5 py-1 shadow-sm"><span className="font-semibold">{t.subject}</span> · {t.name}</span>)}
          </div>
        )}
      </div>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_330px]">
        {live ? <LearnerOverview studentId={student.id} audience="student" /> : <p role="status" className="text-sm text-content-secondary">Loading your results…</p>}
        <div className="space-y-4"><AnnouncementsOverview /><CalendarOverview /></div>
      </div>

      <details className="rounded-2xl border border-surface-border bg-white p-4 shadow-subtle">
        <summary className="cursor-pointer text-sm font-semibold text-navy-900">Answer an assignment online instead of on paper</summary>
        <div className="mt-4"><StudentAssessments /></div>
      </details>
      <details className="rounded-2xl border border-surface-border bg-white p-4 shadow-subtle">
        <summary className="cursor-pointer text-sm font-semibold text-navy-900">Concept map (Knowledge Components)</summary>
        <div className="mt-4"><KnowledgeComponentGraph /></div>
      </details>
    </div>
  );
}
