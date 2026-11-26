import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import type { Coverage as LibCoverage, CoverageStatus } from '../../lib/planning/coverage';
import { invalidateRequirements } from './requirementsStore';
import { describeError, teacherPlanApi, type Coverage as ApiCoverage, type TeacherPlan } from '../../lib/teacherPlanApi';

/** Syllabus node ids (CH-<book>-S<n>) and relational topic keys (XW-<book>-S<n>) differ only by prefix. */
export const nodeIdOf = (topicKey: string) => (topicKey.startsWith('XW-') ? `CH-${topicKey.slice(3)}` : topicKey);
export const topicKeyOf = (nodeId: string) => (nodeId.startsWith('CH-') ? `XW-${nodeId.slice(3)}` : nodeId);

const TO_API: Record<CoverageStatus, ApiCoverage> = { DONE: 'done', IN_PROGRESS: 'in_progress', NOT_DONE: 'not_done' };
const FROM_API: Record<ApiCoverage, CoverageStatus> = { done: 'DONE', in_progress: 'IN_PROGRESS', not_done: 'NOT_DONE' };

/** Shapes a teacher's relational plan as the Coverage map the existing screens already render. */
export function coverageFromPlan(plan: TeacherPlan | null): LibCoverage {
  const out: LibCoverage = {};
  for (const t of plan?.topics ?? []) {
    const status = FROM_API[t.coverage];
    const by = { id: plan!.teacher_id, name: '', role: 'teacher' } as unknown as LibCoverage[string]['updatedBy'];
    out[nodeIdOf(t.topic_key)] = { status, source: t.coverage_source, updatedAt: t.coverage_updated_at ?? '', updatedBy: by, history: [] };
  }
  return out;
}

/**
 * The single read/write path for syllabus coverage. The teacher is the signed-in teacher, or ?teacher=<id> for a
 * Principal/Admin inspecting one teacher (read-only). Nothing is read from or written to the workspace document.
 */
export function useTeacherCoverage(grade: number, subject: string) {
  const { currentUser, currentSchoolId } = useAuth();
  const [params] = useSearchParams();
  const teacherId = params.get('teacher') || (currentUser?.role === 'teacher' ? currentUser.id : '');
  const own = !!currentUser && currentUser.role === 'teacher' && currentUser.id === teacherId;
  const [plan, setPlan] = useState<TeacherPlan | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(!!teacherId);

  const reload = useCallback(async () => {
    if (!teacherId) {
      setPlan(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      let p = await teacherPlanApi.plan(teacherId, grade, subject);
      if (own && p.topics.length === 0) {
        await teacherPlanApi.initialize(teacherId, grade, subject);
        p = await teacherPlanApi.plan(teacherId, grade, subject);
      }
      setPlan(p);
      setError('');
    } catch (e) {
      setPlan(null);
      setError(describeError(e).message);
    } finally {
      setLoading(false);
    }
  }, [teacherId, grade, subject, own, currentSchoolId]);
  useEffect(() => {
    void reload();
  }, [reload]);

  const coverage = useMemo(() => coverageFromPlan(plan), [plan]);
  const set = useCallback(
    async (nodeId: string, status: CoverageStatus, source: 'MANUAL' | 'EXECUTION' = 'MANUAL') => {
      await teacherPlanApi.setCoverage(teacherId, { grade, subject, topic_key: topicKeyOf(nodeId), status: TO_API[status], source });
      await reload();
    },
    [teacherId, grade, subject, reload],
  );
  /**
   * Persist a topic's Core / Non-Core / Mixed classification. The topic's saved total stays the same (capacity-neutral): Core
   * puts every period in Core, Non-Core every period in Non-Core, Mixed splits 2:1 (Core rounded up). The server re-validates.
   */
  const setClassification = useCallback(
    async (nodeId: string, value: 'core' | 'non_core' | 'mixed') => {
      const key = topicKeyOf(nodeId);
      const row = plan?.topics.find((t) => t.topic_key === key);
      if (!row) throw new Error('This topic has no saved configuration yet.');
      const total = row.core_periods + row.non_core_periods;
      const core = value === 'core' ? total : value === 'non_core' ? 0 : total >= 2 ? Math.min(Math.ceil((total * 2) / 3), total - 1) : total; // Mixed keeps at least one Non-Core period when it has two or more
      await teacherPlanApi.saveRequirements(teacherId, {
        grade,
        subject,
        reason: 'Teacher changed topic classification',
        items: [{ topic_key: key, core_periods: core, non_core_periods: total - core, classification: value }],
      });
      invalidateRequirements();
      await reload();
    },
    [plan, teacherId, grade, subject, reload],
  );
  return { teacherId, own, plan, coverage, loading, error, reload, set, setClassification, canEdit: own };
}
