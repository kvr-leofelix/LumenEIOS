/**
 * Planning workspace persistence — one authoritative document per school.
 *
 * SERVER mode (backend reachable): GET/PUT /api/v1/planning/workspace. The backend stores every revision append-only,
 * enforces roles, rejects stale writes (409) and stamps the authenticated actor on audit entries. The browser keeps
 * no authoritative copy in this mode.
 * LOCAL mode (backend unreachable): the workspace is kept in this browser only under a separate key, and the UI says so.
 * The two stores are never merged, so localStorage and backend state cannot silently contradict each other.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient, apiRequest, ApiError } from '../apiClient';
import { AcademicConfig, DEFAULT_CONFIG, migrateLegacyConfig } from './calendar';
import type { Actor, Classifications, Relationship } from './governance';
import type { Plan } from './execution';
import type { Coverage } from './coverage';
import type { SyllabusDataset } from './syllabus';

export interface AuditEntry {
  id: string;
  at: string;
  action: WorkspaceAction | LegacyWorkspaceAction;
  summary: string;
  actor: Actor;
}

export interface ConfigRecord {
  config: AcademicConfig;
  savedBy: Actor;
  savedAt: string;
}

export interface Workspace {
  schemaVersion: 2;
  config: AcademicConfig;
  configHistory: ConfigRecord[];
  datasets: SyllabusDataset[];
  classifications: Classifications;
  relationships: Relationship[];
  plans: Plan[];
  /** One authoritative syllabus-coverage record per topic id (Course Curriculum). Optional in older documents. */
  coverage: Coverage;
  /** Reference date the plans are judged against ("today" in this workspace). null = the real current date. */
  asOf?: string | null;
  audit: AuditEntry[];
}

/**
 * The only actions that still write the workspace document: syllabus dataset imports and the reviewer-set planning date.
 * Everything else that used to live here (calendar, requirements/classifications, relationships, coverage, lost periods, plans,
 * versions, proposals, execution, evidence, audit) is stored in relational, teacher-scoped records; the server refuses the old
 * action names with 410 and freezes those fields in the document, which keeps its history readable only.
 */
export type WorkspaceAction = 'SYLLABUS_IMPORT' | 'PLANNING_DATE';
export const WORKSPACE_ACTIONS: WorkspaceAction[] = ['SYLLABUS_IMPORT', 'PLANNING_DATE'];

/** Action names found in historical workspace audit entries (read-only history). */
export type LegacyWorkspaceAction =
  | 'CONFIG_SAVE' | 'CLASSIFICATION_PROPOSE' | 'CLASSIFICATION_REVIEW' | 'RELATIONSHIP_PROPOSE' | 'RELATIONSHIP_REVIEW' | 'PLAN_DRAFT'
  | 'PLAN_REVIEW' | 'EXECUTION_RECORD' | 'LOSS_RECORD' | 'EVIDENCE_RECORD' | 'RECOVERY_PROPOSE' | 'RECOVERY_REVIEW' | 'COVERAGE_UPDATE';

export const ACTION_ROLES: Record<WorkspaceAction, string[]> = {
  SYLLABUS_IMPORT: ['admin'],
  PLANNING_DATE: ['admin', 'principal'],
};

export const EMPTY_WORKSPACE: Workspace = {
  schemaVersion: 2,
  config: DEFAULT_CONFIG,
  configHistory: [],
  datasets: [],
  classifications: {},
  relationships: [],
  plans: [],
  coverage: {},
  asOf: null,
  audit: [],
};

export const LOCAL_KEY = 'lumeneios_planning_workspace_v2';
/** Earlier prototype key; read once to migrate configuration, never written or deleted. */
export const LEGACY_KEY = 'lumeneios_academicWorkflow';

export function normalizeWorkspace(raw: unknown): Workspace {
  if (!raw || typeof raw !== 'object') return EMPTY_WORKSPACE;
  const r = raw as Partial<Workspace>;
  if (r.schemaVersion !== 2) return EMPTY_WORKSPACE;
  return {
    ...EMPTY_WORKSPACE,
    ...r,
    config: migrateLegacyConfig(r.config) ?? DEFAULT_CONFIG,
    configHistory: Array.isArray(r.configHistory) ? r.configHistory : [],
    datasets: Array.isArray(r.datasets) ? r.datasets : [],
    classifications: r.classifications && typeof r.classifications === 'object' ? r.classifications : {},
    relationships: Array.isArray(r.relationships) ? r.relationships : [],
    plans: Array.isArray(r.plans) ? r.plans : [],
    coverage: r.coverage && typeof r.coverage === 'object' && !Array.isArray(r.coverage) ? r.coverage : {},
    asOf: typeof r.asOf === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(r.asOf) ? r.asOf : null,
    audit: Array.isArray(r.audit) ? r.audit : [],
  };
}

function readLocal(): { workspace: Workspace; legacyPlans: number; corrupt: boolean } {
  let corrupt = false;
  let legacyPlans = 0;
  try {
    const raw = localStorage.getItem(LOCAL_KEY);
    if (raw) return { workspace: normalizeWorkspace(JSON.parse(raw)), legacyPlans, corrupt };
  } catch {
    corrupt = true;
  }
  try {
    const legacy = JSON.parse(localStorage.getItem(LEGACY_KEY) || 'null');
    if (legacy) {
      legacyPlans = Array.isArray(legacy.plans) ? legacy.plans.length : 0;
      const config = migrateLegacyConfig(legacy.config);
      if (config) return { workspace: { ...EMPTY_WORKSPACE, config }, legacyPlans, corrupt };
    }
  } catch {
    /* unreadable legacy data is ignored and left untouched */
  }
  return { workspace: EMPTY_WORKSPACE, legacyPlans, corrupt };
}

/** 'error' = the backend answered but the workspace could not be loaded; saving is blocked until a reload succeeds. */
export type StoreMode = 'loading' | 'server' | 'local' | 'error';

interface ServerWorkspace {
  revision: number;
  state: unknown;
  updated_at: string | null;
  updated_by: string | null;
}

export interface Transport {
  load(): Promise<ServerWorkspace>;
  /** Ensures the backend session belongs to the signed-in user before a write (prevents demo-mode admin fallback). */
  ensureIdentity?(email: string): Promise<void>;
  /** True when no backend session token exists yet, so the first request would be rejected with 401. */
  needsLogin?(): boolean;
  save(body: { expected_revision: number; action: WorkspaceAction; summary: string; state: Workspace }): Promise<ServerWorkspace>;
}

const sameEmail = (a?: string, b?: string) => !!a && !!b && a.toLowerCase() === b.toLowerCase();

export const httpTransport: Transport = {
  load: () => apiRequest<ServerWorkspace>('/planning/workspace'),
  needsLogin: () => !localStorage.getItem('lumeneios_token'),
  async ensureIdentity(email: string) {
    if (localStorage.getItem('lumeneios_token')) {
      try {
        const me = await apiRequest<{ email?: string }>('/auth/me');
        if (sameEmail(me.email, email)) return;
      } catch {
        /* expired token: sign in below */
      }
    }
    // Upstream auth requires a password: a passwordless re-login is no longer possible, so the user must sign in again.
    throw new Error('Your session has expired. Please sign in again.');
  },
  save: (body) => apiRequest<ServerWorkspace>('/planning/workspace', { method: 'PUT', body: JSON.stringify(body) }),
};

let transportOverride: Transport | null | undefined;
/** Test hook: null forces local mode, a Transport forces server mode, undefined restores the default. */
export function setPlanningTransport(t: Transport | null | undefined) {
  transportOverride = t;
}

function activeTransport(): Transport | null {
  if (transportOverride !== undefined) return transportOverride;
  const env = (import.meta as unknown as { env?: Record<string, string> }).env ?? {};
  if (env.VITE_PLANNING_STORE === 'local') return null;
  if (env.MODE === 'test') return null;
  return httpTransport;
}

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new ApiError(0, 'Planning store timed out')), ms);
    p.then(
      (v) => {
        clearTimeout(t);
        resolve(v);
      },
      (e) => {
        clearTimeout(t);
        reject(e);
      },
    );
  });
}

export interface CommitResult {
  ok: boolean;
  error?: string;
  /** true when the save was refused because the stored workspace changed (409 or a failed guard). */
  conflict?: boolean;
}

export interface CommitOptions {
  /**
   * Checked against the latest stored workspace immediately before the change is applied. Return a message to refuse
   * the save as a conflict. Used where an edit replaces a value wholesale (the Academic Configuration), so a stale
   * draft can never overwrite someone else's newer value even when the revision is current.
   */
  guard?: (latest: Workspace) => string | null;
}

export interface SaveInfo {
  revision: number;
  by: string | null;
  at: string | null;
}

export interface PlanningStore {
  workspace: Workspace;
  mode: StoreMode;
  revision: number;
  lastSaved: SaveInfo;
  error: string;
  notice: string;
  legacyPlans: number;
  commit: (action: WorkspaceAction, summary: string, update: (w: Workspace) => Workspace, options?: CommitOptions) => Promise<CommitResult>;
  reload: () => Promise<void>;
  clearError: () => void;
}

/** How often an idle, visible page re-checks the shared workspace for other users' saves. */
export const REFRESH_INTERVAL_MS = 30_000;

/** `identityKey` changes when a different user signs in, so their view of the workspace is (re)loaded. */
export function usePlanningStore(getActor: () => (Actor & { email?: string }) | null, identityKey = ''): PlanningStore {
  const initial = useRef(readLocal());
  const [workspace, setWorkspace] = useState<Workspace>(() => (activeTransport() ? EMPTY_WORKSPACE : initial.current.workspace));
  const [mode, setMode] = useState<StoreMode>(() => (activeTransport() ? 'loading' : 'local'));
  const [revision, setRevision] = useState(0);
  const [lastSaved, setLastSaved] = useState<SaveInfo>({ revision: 0, by: null, at: null });
  const [error, setError] = useState(initial.current.corrupt ? 'Saved browser workspace was unreadable; starting from defaults. The unreadable data was not deleted.' : '');
  const [notice, setNotice] = useState('');
  // The base revision for the next save. Updated synchronously only when a load or save succeeds, so a save can never
  // be sent against a revision this client has not actually loaded.
  const latest = useRef<{ workspace: Workspace; revision: number; mode: StoreMode }>({ workspace, revision, mode });
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const inFlight = useRef(0);

  const adopt = useCallback((res: ServerWorkspace) => {
    const ws = res.state ? normalizeWorkspace(res.state) : { ...EMPTY_WORKSPACE, config: initial.current.workspace.config };
    latest.current = { workspace: ws, revision: res.revision, mode: 'server' };
    setWorkspace(ws);
    setRevision(res.revision);
    setLastSaved({ revision: res.revision, by: res.updated_by, at: res.updated_at });
    setMode('server');
    setNotice('');
  }, []);

  /**
   * Loads the authoritative workspace. quiet = background refresh: state is only updated when the revision changed, and
   * an already-loaded session is never downgraded to an error or browser-only mode.
   */
  const loadServer = useCallback(
    async (opts: { quiet?: boolean } = {}): Promise<ServerWorkspace | null> => {
      const transport = activeTransport();
      if (!transport) return null;
      // The planning workspace is staff-only on the backend; students and parents never request it (avoids 403 noise).
      const who = getActor();
      if (who && !['admin', 'principal', 'teacher'].includes(who.role)) return null;
      // Signed out (e.g. the login page): nothing to load, and an anonymous request is certain to be refused. The
      // identityKey effect below reloads as soon as someone signs in.
      if (!who) return null;
      const loaded = latest.current.mode === 'server';
      const attempt = () => withTimeout(transport.load(), 5000);
      try {
        let res: ServerWorkspace;
        // No session token yet (the sign-in is still completing): sign in first rather than send a request that is certain to 401.
        const first = getActor();
        if (transport.needsLogin?.() && transport.ensureIdentity && first?.email) await withTimeout(transport.ensureIdentity(first.email), 8000);
        try {
          res = await attempt();
        } catch (e) {
          // An expired or foreign token (401/403) is re-established once for the signed-in user, then retried.
          const actor = getActor();
          if (e instanceof ApiError && (e.status === 401 || e.status === 403) && transport.ensureIdentity && actor?.email) {
            await withTimeout(transport.ensureIdentity(actor.email), 8000);
            res = await attempt();
          } else throw e;
        }
        if (!(opts.quiet && loaded && res.revision === latest.current.revision)) adopt(res);
        return res;
      } catch (e) {
        if (opts.quiet && loaded) return null; // keep the loaded workspace; the next save reports any real problem
        const err = e as ApiError;
        if (err instanceof ApiError && err.status === 0) {
          latest.current = { workspace: initial.current.workspace, revision: 0, mode: 'local' };
          setWorkspace(initial.current.workspace);
          setMode('local');
          setNotice('LumenEIOS backend is unreachable. Working in browser-only mode: records are saved in this browser only and are not shared with other users or devices.');
          return null;
        }
        // The backend answered but refused: block saving instead of writing against an unknown revision.
        latest.current = { ...latest.current, mode: 'error' };
        setMode('error');
        setError(
          `The shared planning workspace could not be loaded (${err instanceof ApiError ? err.status : 'error'}: ${err?.message ?? 'unknown'}). Saving is disabled until it loads. Use Retry.`,
        );
        return null;
      }
    },
    [adopt, getActor],
  );

  useEffect(() => {
    loadServer();
  }, [loadServer, identityKey]);

  // Server mode: pick up other users' saves when the page regains attention and periodically while visible, so
  // sessions edit the latest revision instead of discovering it through a conflict. Skipped while a save is running.
  useEffect(() => {
    if (mode !== 'server') return;
    const refresh = () => {
      if (inFlight.current === 0 && document.visibilityState !== 'hidden') loadServer({ quiet: true });
    };
    const timer = window.setInterval(refresh, REFRESH_INTERVAL_MS);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [mode, loadServer]);

  // Keep other tabs of the same browser consistent in local mode.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== LOCAL_KEY || latest.current.mode !== 'local' || !e.newValue) return;
      try {
        const ws = normalizeWorkspace(JSON.parse(e.newValue));
        latest.current = { ...latest.current, workspace: ws };
        setWorkspace(ws);
      } catch {
        /* ignore */
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const commit = useCallback(
    (action: WorkspaceAction, summary: string, update: (w: Workspace) => Workspace, options: CommitOptions = {}): Promise<CommitResult> => {
      const fail = (message: string, conflict = false): CommitResult => {
        setError(message);
        return { ok: false, error: message, conflict };
      };
      const run = async (): Promise<CommitResult> => {
        const actor = getActor();
        if (!actor) return fail('You must be signed in to save changes.');
        if (!ACTION_ROLES[action].includes(actor.role)) return fail(`Your role (${actor.role}) cannot perform this action.`);
        const { workspace: current, revision: rev, mode: m } = latest.current;
        if (m === 'loading') return fail('The planning store is still loading. Try again in a moment.');
        if (m === 'error') return fail('The shared workspace is not loaded, so nothing can be saved yet. Use Retry; your input is still on screen.');
        const guardProblem = options.guard?.(current);
        if (guardProblem) return fail(guardProblem, true);
        let next: Workspace;
        try {
          next = update(current);
        } catch (e) {
          return fail(e instanceof Error ? e.message : 'The change could not be applied.');
        }
        const entry: AuditEntry = {
          id: `audit-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
          at: new Date().toISOString(),
          action,
          summary,
          actor: { id: actor.id, name: actor.name, role: actor.role },
        };
        next = { ...next, audit: [...current.audit, entry] };
        if (m === 'server') {
          const transport = activeTransport();
          if (!transport) return fail('Planning store unavailable.');
          if (transport.ensureIdentity && actor.email) {
            try {
              await withTimeout(transport.ensureIdentity(actor.email), 8000);
            } catch (e) {
              return fail(`Could not verify your backend session as ${actor.name} (${e instanceof Error ? e.message : 'sign-in failed'}). Your change was NOT saved; sign in again.`);
            }
          }
          try {
            const res = await withTimeout(transport.save({ expected_revision: rev, action, summary, state: next }), 8000);
            adopt({ ...res, state: res.state ?? next });
            setError('');
            return { ok: true };
          } catch (e) {
            const err = e as ApiError;
            if (err instanceof ApiError && err.status === 409) {
              const fresh = await loadServer();
              const who = fresh?.updated_by;
              const by = who ? (who === actor.name ? 'you, in another tab or window' : who) : 'another session';
              return fail(
                `Not saved: the workspace changed before your save arrived (now revision ${fresh?.revision ?? '?'}, saved by ${by}). ` +
                  'The latest version is loaded and your input is kept on screen. Review it and save again.',
                true,
              );
            }
            return fail(`Save failed${err instanceof ApiError && err.status ? ` (${err.status})` : ''}: ${err?.message || 'network error'}. Your change was NOT saved; your input is kept.`);
          }
        }
        try {
          localStorage.setItem(LOCAL_KEY, JSON.stringify(next));
        } catch {
          return fail('Saving failed: browser storage is unavailable or full. Your change was NOT saved.');
        }
        latest.current = { workspace: next, revision: rev + 1, mode: 'local' };
        setWorkspace(next);
        setRevision(rev + 1);
        setError('');
        return { ok: true };
      };
      const tracked = async () => {
        inFlight.current += 1;
        try {
          return await run();
        } finally {
          inFlight.current -= 1;
        }
      };
      const p = queue.current.then(tracked, tracked);
      queue.current = p;
      return p;
    },
    [getActor, loadServer, adopt],
  );

  const reload = useCallback(async () => {
    setError('');
    await loadServer();
  }, [loadServer]);

  return {
    workspace,
    mode,
    revision,
    lastSaved,
    error,
    notice,
    legacyPlans: initial.current.legacyPlans,
    commit,
    reload,
    clearError: () => setError(''),
  };
}
