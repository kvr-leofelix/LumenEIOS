import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { teacherPlanApi } from '../../lib/teacherPlanApi';
import { Stat } from '../../pages/time-aware/planningUi';
import { useStoreVersion } from './requirementsStore';
import { useRemote } from './useRemote';

/**
 * Teaching days and lost periods for the signed-in teacher, counted by the backend from the same relational rows the
 * "Record a Lost Day" recorder writes (it refetches whenever those rows change). Recording itself happens in that recorder only.
 */
export const TeacherLostDays: React.FC<{ grade: number; subject: string; calendarVersion?: number }> = ({ grade, subject, calendarVersion }) => {
  const { currentUser } = useAuth();
  const teacher = currentUser?.role === 'teacher' ? currentUser.id : '';
  const version = useStoreVersion();
  const { data, error } = useRemote(() => (teacher ? teacherPlanApi.lost(teacher, grade, subject) : Promise.reject(new Error(''))), [teacher, grade, subject, version]);
  if (!teacher) return null;
  return (
    <section className="bg-white rounded-xl border border-surface-border p-4 space-y-3" data-testid="teacher-lost-days">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-navy-900">Teaching days and lost periods <span className="font-normal text-content-muted">· current academic calendar{calendarVersion ? ` (version ${calendarVersion})` : ''}</span></h2>
        <Link className="text-xs font-semibold text-teal-700 underline" to={`/logs?teacher_id=${teacher}&grade=${grade}&subject=${subject}&category=lost_period`}>History →</Link>
      </div>
      {error && <p role="alert" className="text-xs text-rose-700">{error}</p>}
      {data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Days completed" value={data.completed_days} />
          <Stat label="Days remaining" value={data.remaining_days} />
          <Stat label="Lost days" value={data.lost_days} tone="amber" />
          <Stat label="Lost periods" value={data.lost_periods} tone="rose" />
        </div>
      )}
    </section>
  );
};
