import { useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Role } from '../../types';

const EDUCATOR_ROLES: Role[] = ['admin', 'principal', 'teacher'];

export function useProgressScope(expected: 'self' | 'educator' | 'parent') {
  const { currentUser } = useAuth();
  const params = useParams<{ studentId?: string; subjectId?: string }>();

  return useMemo(() => {
    const role = currentUser?.role;
    const studentId = params.studentId;
    const subjectId = params.subjectId;
    if (!role) {
      return { allowed: false as const, reason: 'unauthenticated' as const };
    }
    if (expected === 'self') {
      if (role !== 'student') return { allowed: false as const, reason: 'unauthorized' as const };
      return {
        allowed: true as const,
        role,
        studentId: undefined as string | undefined,
        subjectId,
        apiScope: { role: 'student' as const },
      };
    }
    if (expected === 'parent') {
      if (role !== 'parent') return { allowed: false as const, reason: 'unauthorized' as const };
      if (!studentId) return { allowed: false as const, reason: 'missing-student' as const };
      return {
        allowed: true as const,
        role,
        studentId,
        subjectId,
        apiScope: { role: 'parent' as const, studentId },
      };
    }
    if (!EDUCATOR_ROLES.includes(role)) {
      return { allowed: false as const, reason: 'unauthorized' as const };
    }
    if (!studentId) return { allowed: false as const, reason: 'missing-student' as const };
    return {
      allowed: true as const,
      role,
      studentId,
      subjectId,
      apiScope: { role, studentId },
    };
  }, [currentUser?.role, expected, params.studentId, params.subjectId]);
}
