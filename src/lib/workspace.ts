import type { Assessment, AssessmentResult, ClassSection, CompetencyScores, School, Student, Subject } from '../types';

/** Role-scoped database snapshot from GET /workspace (see backend/app/api/v1/workspace.py). */
export interface WorkspaceTeacher { id: string; name: string; email: string; schoolId: string; designation: string; role: 'teacher' }
export interface WorkspaceAssignment { teacherId: string; classId: string; subjectId: string; schoolId: string }
export interface WorkspaceSnapshot { studentId: string; recordedAt: string | null; cycleNumber: number; scores: CompetencyScores; notes?: string | null }

export interface Workspace {
  role: string;
  schools: School[];
  classes: ClassSection[];
  subjects: Subject[];
  students: (Student & { admissionNo?: string; dateOfBirth?: string })[];
  teachers: WorkspaceTeacher[];
  teacherAssignments: WorkspaceAssignment[];
  assessments: Assessment[];
  assessmentResults: AssessmentResult[];
  snapshots: WorkspaceSnapshot[];
  /** classId -> average LU/CU/AU/CT/overall of that class. */
  classAverages: Record<string, CompetencyScores>;
  /** assessmentId -> class average percentage (students and parents only). */
  assessmentAverages: Record<string, number>;
  /** assessmentId -> uploaded handwritten work not yet graded (educators). */
  pendingUploads: Record<string, number>;
  /** assessmentId -> students who uploaded (educators) / 1 if this learner uploaded (students, parents). */
  uploadedCounts: Record<string, number>;
  /** Lost teaching days recorded by the school(s) (educators). */
  disruptions: { id: string; schoolId: string; date: string; reason: string; daysLost: number; recordedBy: string; notes?: string | null }[];
}

/** Classes a teacher teaches (from teacherAssignments), falling back to every class in the workspace. */
export function teacherClassIds(ws: Workspace | null, teacherId?: string): string[] {
  if (!ws || !teacherId) return [];
  const ids = Array.from(new Set(ws.teacherAssignments.filter(a => a.teacherId === teacherId).map(a => a.classId)));
  return ids.length ? ids : ws.classes.map(c => c.id);
}

export function subjectName(ws: Workspace | null, id?: string): string {
  return ws?.subjects.find(s => s.id === id)?.name ?? id ?? '';
}
