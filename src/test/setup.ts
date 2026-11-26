import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import * as demoSeed from '../data/seedData';

afterEach(() => {
  cleanup();
  localStorage.clear();
});

// jsdom lacks these browser APIs used by existing chart components.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as any).ResizeObserver ??= ResizeObserverStub;

// Existing contexts fire background API syncs; keep tests offline and deterministic.
(globalThis as any).fetch = vi.fn(() => Promise.reject(new TypeError('Network disabled in tests')));

// Feature tests mount modules without the app-level ThemeProvider; fall back to a static default theme there.
vi.mock('../context/ThemeContext', async (importOriginal) => {
  const real = await importOriginal<typeof import('../context/ThemeContext')>();
  return {
    ...real,
    useTheme: () => {
      try {
        return real.useTheme();
      } catch {
        return { theme: 'light', uiMode: 'classic', setTheme: () => {}, setUiMode: () => {} } as ReturnType<typeof real.useTheme>;
      }
    },
  };
});

// Live auth restores a session from a token via /auth/me; tests have no backend, so restore the stored test user.
function demoWorkspace() {
  const seed = demoSeed;
  return {
    role: 'admin', schools: seed.initialSchools, classes: seed.initialClasses, subjects: seed.initialSubjects,
    students: seed.initialStudents, teachers: [], teacherAssignments: [], assessments: seed.initialAssessments,
    assessmentResults: seed.initialAssessmentResults, snapshots: [], classAverages: {}, assessmentAverages: {},
    pendingUploads: {}, uploadedCounts: {}, disruptions: [],
  };
}

vi.mock('../lib/apiClient', async (importOriginal) => {
  const real = await importOriginal<typeof import('../lib/apiClient')>();
  return {
    ...real,
    apiClient: {
      ...real.apiClient,
      // Live dashboards read the role-scoped /workspace; tests serve the offline demonstration records instead.
      workspace: () => {
        const settle = (value: unknown): any => ({
          then: (onOk?: (v: any) => unknown) => { onOk?.(value); return settle(value); },
          catch: () => settle(value),
          finally: (fn?: () => void) => { fn?.(); return settle(value); },
        });
        return settle(demoWorkspace());
      },
      auth: {
        ...real.apiClient.auth,
        // Resolves synchronously (a thenable) so tests that render and assert immediately see the restored session.
        switchSchool: async (schoolId: string) => {
          const user = { ...JSON.parse(localStorage.getItem('lumeneios_test_user') ?? '{}'), school_id: schoolId };
          localStorage.setItem('lumeneios_test_user', JSON.stringify(user));
          return { access_token: 'test-token', user };
        },
        me: () => {
          const saved = localStorage.getItem('lumeneios_test_user');
          const settle = (ok: boolean, value: unknown): any => ({
            then: (onOk?: (v: any) => unknown) => { if (ok) onOk?.(value); return settle(ok, value); },
            catch: (onErr?: (e: any) => unknown) => { if (!ok) onErr?.(value); return settle(true, undefined); },
            finally: (fn?: () => void) => { fn?.(); return settle(ok, value); },
          });
          return saved ? settle(true, JSON.parse(saved)) : settle(false, new real.ApiError(401, 'No session'));
        },
      },
    },
  };
});
