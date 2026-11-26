import React from 'react';
import type { PlanningSubject } from '../../lib/planning/calendar';
import type { SyllabusDataset } from '../../lib/planning/syllabus';
import { TeacherPlanPanel } from '../../features/teacherPlan/TeacherPlanPanel';

/**
 * Requirements tab. Core and Non-Core periods are the teacher's relational plan, the same rows the Catalogue shows and the
 * scheduling engine consumes. There is no separate workspace classification here any more; Principals/Admins inspect only.
 * `dataset` is kept for the existing call site.
 */
export const SyllabusPanel: React.FC<{ dataset: SyllabusDataset; grade: number; subject: PlanningSubject }> = ({ grade, subject }) => (
  <div className="space-y-3" data-testid="approved-requirements-list">
    <p className="text-[11px] text-content-muted">
      Each topic has a saved Core / Non-Core classification and period requirement for this teacher. Change them in Course Curriculum; the Time-Aware Engine reads the same saved values.
    </p>
    <TeacherPlanPanel grade={grade} subject={subject === 'Science' ? 'science' : 'mathematics'} showOrigin />
  </div>
);
