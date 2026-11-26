import { useCallback, useMemo } from 'react';
import { useInRouterContext, useLocation } from 'react-router-dom';
import { useData } from '../../context/DataContext';
import { useAuth } from '../../context/AuthContext';
import type { Actor } from './governance';
import type { EngineContext } from './engine';
import { WORKSPACE_ACTIONS, type CommitOptions, type CommitResult, type LegacyWorkspaceAction, type Workspace, type WorkspaceAction } from './store';
import { allDatasets } from './syllabus';
import { useTeacherClassifications, useTeacherLostRows, useTeacherRelationships, withLosses, invalidateRequirements } from '../../features/teacherPlan/requirementsStore';
import { applyPlanCommands, planCommands, reloadPlans, usePlans } from '../../features/teacherPlan/plansStore';
import { historyRecords, useSchoolCalendar } from '../../features/teacherPlan/calendarStore';

/**
 * The single planning hook. Requirements, relationships, lost periods and plans are the backend's relational records
 * (the signed-in teacher's own, or ?teacher=<id> / every teacher for a reviewer). `commit` keeps the existing call sites:
 * the mutator still produces the next state with the established pure planning functions, and the plan changes it makes are
 * sent to the server as commands. Only genuinely workspace-level changes (academic configuration, imports) are saved to the workspace.
 */
export function usePlanning() {
  const { planning } = useData();
  const { currentUser, currentSchoolId } = useAuth();
  const inRouter = useInRouterContext();
  const search = inRouter ? useLocation().search : ''; // eslint-disable-line react-hooks/rules-of-hooks -- constant per mount
  const requestedTeacher = new URLSearchParams(search).get('teacher') || '';
  const role = currentUser?.role ?? '';
  const teacherId = requestedTeacher || (currentUser?.role === 'teacher' ? currentUser.id : '');
  const ownsPlan = !!currentUser && currentUser.role === 'teacher' && currentUser.id === teacherId;

  const classifications = useTeacherClassifications(currentSchoolId, teacherId);
  const relationships = useTeacherRelationships(currentSchoolId, teacherId);
  const lostRows = useTeacherLostRows(currentSchoolId, teacherId);
  const { plans: served, error: plansError } = usePlans(currentSchoolId, currentUser?.id ?? '', role);

  // A teacher sees their own plans with their freshest lost-period rows; a reviewer sees each teacher's plan as served
  // (or only the chosen teacher's when ?teacher= is given). Plans are never merged across teachers.
  const plans = useMemo(() => {
    const scoped = requestedTeacher && role !== 'teacher' ? served.filter((pl) => pl.teacherId === requestedTeacher) : served;
    return ownsPlan ? scoped.map((pl) => withLosses(pl, lostRows, teacherId)) : scoped;
  }, [served, requestedTeacher, role, ownsPlan, lostRows, teacherId]);

  const staff = ['teacher', 'principal', 'admin'].includes(role);
  const calendar = useSchoolCalendar(currentSchoolId, staff);
  // The calendar is the school's versioned relational calendar. Only a school with no saved version yet falls back to the
  // workspace's historical/default configuration (read-only; the first save or the import creates version 1).
  const { workspace: stored } = planning;
  const workspace = useMemo(
    () => (calendar.version >= 1 && calendar.config ? { ...stored, config: calendar.config, configHistory: historyRecords(calendar.versions) } : stored),
    [stored, calendar.version, calendar.config, calendar.versions],
  );
  const datasets = useMemo(() => allDatasets(workspace.datasets), [workspace.datasets]);
  const ctx: EngineContext = useMemo(() => ({ datasets, classifications, relationships }), [datasets, classifications, relationships]);
  const actor: Actor | null = currentUser ? { id: currentUser.id, name: currentUser.name, role: currentUser.role } : null;
  const workspaceView = useMemo(() => ({ ...workspace, plans }), [workspace, plans]);

  const commit = useCallback(
    async (action: WorkspaceAction | LegacyWorkspaceAction, summary: string, update: (w: Workspace) => Workspace, options?: CommitOptions): Promise<CommitResult> => {
      const before: Workspace = { ...planning.workspace, plans };
      let next: Workspace;
      try {
        next = update(before);
      } catch (e) {
        return { ok: false, error: e instanceof Error ? e.message : 'Not saved.' };
      }
      if (next.plans !== before.plans) {
        const done = await applyPlanCommands(planCommands(before.plans, next.plans, currentUser?.id ?? ''));
        // Reload whatever the server decided, success or not, so the screen always shows the server's records.
        await reloadPlans(currentSchoolId, currentUser?.id ?? '', role);
        invalidateRequirements();
        if (!done.ok) return { ok: false, error: done.error };
      }
      const touchesWorkspace = (Object.keys(next) as (keyof Workspace)[]).some((k) => k !== 'plans' && next[k] !== before[k]);
      if (!touchesWorkspace) return { ok: true };
      if (!(WORKSPACE_ACTIONS as string[]).includes(action)) {
        // A label that names a migrated responsibility must never reach the workspace document.
        return { ok: false, error: `'${action}' is stored in the relational planning records, not the workspace document.` };
      }
      return planning.commit(action as WorkspaceAction, summary, (w) => ({ ...update({ ...w, plans }), plans: w.plans }), options);
    },
    [planning, plans, currentUser?.id, currentSchoolId, role],
  );

  return {
    ...planning,
    workspace: workspaceView,
    commit,
    plansError,
    calendarVersion: calendar.version,
    calendarError: calendar.error,
    lostRows,
    datasets,
    ctx,
    teacherId,
    ownsPlan,
    actor,
    role,
    isReviewer: role === 'admin' || role === 'principal',
    isTeacher: role === 'teacher',
  };
}
