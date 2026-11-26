import React, { createContext, useContext, useMemo, useRef } from 'react';
import { useAuth } from '../../../context/AuthContext';
import type { CatalogueActor, CurriculumCatalogueService } from './catalogueService';
import { createNcertApi, type NcertApi } from './ncertApi';

/** Mock fixtures are loaded via dynamic import so they live in a separate chunk, never in API mode. */
function createLazyMockService(getActor: () => CatalogueActor | null): CurriculumCatalogueService {
  let loaded: Promise<CurriculumCatalogueService> | null = null;
  const get = () =>
    (loaded ??= import('../mocks/mockCatalogueService').then((m) => m.createMockCatalogueService({ getActor })));
  return {
    kind: 'mock',
    getDashboard: () => get().then((s) => s.getDashboard()),
    getCombination: (g, s) => get().then((svc) => svc.getCombination(g, s)),
    getChapterExplorer: (g, s) => get().then((svc) => svc.getChapterExplorer(g, s)),
    listCandidateMappings: (g, s) => get().then((svc) => svc.listCandidateMappings(g, s)),
    submitReview: (id, input) => get().then((svc) => svc.submitReview(id, input)),
  };
}

export type CatalogueDataSource = 'mock' | 'api';

/**
 * Data source selection. `mock` (default) = metadata-only research snapshot for demos.
 * `api` = the real backend (CURRICULUM_API_INTEGRATION_CONTRACT.md) via the authenticated API client.
 * There is never an automatic fallback from API to mock.
 */
export function configuredDataSource(): CatalogueDataSource {
  const value = (import.meta as any).env?.VITE_CURRICULUM_DATA_SOURCE;
  return value === 'api' ? 'api' : 'mock';
}

type CatalogueContextValue =
  | { mode: 'mock'; service: CurriculumCatalogueService }
  | { mode: 'api'; api: NcertApi };

const CatalogueServiceContext = createContext<CatalogueContextValue | null>(null);

export const CatalogueServiceProvider: React.FC<{
  children: React.ReactNode;
  /** Inject a mock-mode service (tests). */
  service?: CurriculumCatalogueService;
  /** Inject an API adapter (tests); selects API mode. */
  api?: NcertApi;
}> = ({ children, service, api }) => {
  const { currentUser } = useAuth();
  const actorRef = useRef<CatalogueActor | null>(null);
  actorRef.current = currentUser ? { name: currentUser.name, role: currentUser.role } : null;

  const value = useMemo<CatalogueContextValue>(() => {
    if (api) return { mode: 'api', api };
    if (service) return { mode: 'mock', service };
    return configuredDataSource() === 'api'
      ? { mode: 'api', api: createNcertApi() }
      : { mode: 'mock', service: createLazyMockService(() => actorRef.current) };
  }, [service, api]);

  return <CatalogueServiceContext.Provider value={value}>{children}</CatalogueServiceContext.Provider>;
};

function useCatalogueContext(): CatalogueContextValue {
  const ctx = useContext(CatalogueServiceContext);
  if (!ctx) throw new Error('Curriculum catalogue hooks must be used within CatalogueServiceProvider');
  return ctx;
}

export function useCatalogueMode(): CatalogueDataSource {
  return useCatalogueContext().mode;
}

/** Mock-mode service (research snapshot screens). */
export function useCatalogueService(): CurriculumCatalogueService {
  const ctx = useCatalogueContext();
  if (ctx.mode !== 'mock') throw new Error('useCatalogueService is only available in mock mode');
  return ctx.service;
}

/** API-mode adapter (backend contract screens). */
export function useNcertApi(): NcertApi {
  const ctx = useCatalogueContext();
  if (ctx.mode !== 'api') throw new Error('useNcertApi is only available in API mode');
  return ctx.api;
}
