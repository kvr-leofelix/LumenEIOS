import { Role } from '../types';

export const PERMISSIONS = {
  VIEW_LEARNSPHERE: ['admin', 'principal', 'teacher', 'parent', 'student'],
  MANAGE_LEARNSPHERE: ['admin', 'principal', 'teacher'],
  MANAGE_SCHOOLS: ['admin'],
  MANAGE_USERS: ['admin'],
  VIEW_GLOBAL_ANALYTICS: ['admin'],
  AUDIT_LOGS: ['admin'],
  ASSIGN_TEACHERS: ['admin', 'principal'],
  REVIEW_LESSON_PLANS: ['admin', 'principal'],
  VIEW_SCHOOL_METRICS: ['admin', 'principal'],
  SEND_ANNOUNCEMENTS: ['admin', 'principal', 'teacher'],
  MANAGE_CLASSES: ['admin', 'principal', 'teacher'],
  CREATE_ASSESSMENT: ['admin', 'principal', 'teacher'],
  GRADE_ASSESSMENT: ['teacher'],
  RECORD_LOST_DAYS: ['admin', 'principal', 'teacher'],
  PREVIEW_COMPRESSION: ['admin', 'principal', 'teacher'],
  APPROVE_COMPRESSION: ['admin', 'principal', 'teacher'],
  ASSIGN_REMEDIATION: ['teacher'],
  SUBMIT_ASSIGNMENTS: ['student'],
  REVIEW_STUDENT_SHEETS: ['admin', 'principal', 'teacher'],
  VIEW_CHILD_PROGRESS: ['parent'],
  ADD_STUDENT: ['admin', 'principal', 'teacher'],
  ADD_TEACHER: ['admin', 'principal'],
  // Curriculum catalogue (UI gating only — the backend must enforce authorization).
  VIEW_CURRICULUM_CATALOGUE: ['admin', 'principal', 'teacher'],
  REVIEW_CURRICULUM_MAPPINGS: ['admin'], // contract v1: global catalogue review is admin-only
} as const;

export function hasPermission(role: Role, permission: keyof typeof PERMISSIONS): boolean {
  if (role === 'developer') return true;
  const allowedRoles = PERMISSIONS[permission] as readonly string[];
  return allowedRoles.includes(role);
}

export function getRoleLabel(role: string | undefined): string {
  if (role === 'admin') return 'Management';
  if (!role) return '';
  return role.charAt(0).toUpperCase() + role.slice(1);
}

export function getDefaultDashboardPath(role: Role): string {
  switch (role) {
    case 'developer':
      return '/developer';
    case 'admin':
      return '/admin/dashboard';
    case 'principal':
      return '/principal/dashboard';
    case 'teacher':
      return '/teacher/dashboard';
    case 'student':
      return '/student/dashboard';
    case 'parent':
      return '/parent/dashboard';
    default:
      return '/login';
  }
}
