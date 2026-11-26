/**
 * MOCK implementation of CurriculumCatalogueService backed by the research snapshot fixture.
 * Simulates latency, backend authorization (403) and validation (422) so UI states are realistic.
 * Review decisions are held in memory only — nothing is persisted or sent to a server.
 */
import { ApiError } from '../../../lib/apiClient';
import { hasPermission } from '../../../lib/permissions';
import {
  validateReviewInput,
  type CatalogueActor,
  type CurriculumCatalogueService,
  type ReviewInput,
} from '../api/catalogueService';
import { allowedDecisions } from '../api/contract';
import {
  GRADES,
  SUBJECTS,
  combinationId,
  type CandidateMapping,
  type GradeNumber,
  type ReviewRecord,
  type SubjectKey,
} from '../types';
import {
  buildChapters,
  buildLanguageMatrix,
  mapCandidate,
  mapEdition,
  mapResource,
  snapshotMeta,
  summarise,
  type ResearchSnapshot,
} from './mapResearchSnapshot';
import snapshotJson from './researchSnapshot.json';

export type ReviewStore = Map<string, ReviewRecord[]>;

export interface MockServiceOptions {
  snapshot?: ResearchSnapshot;
  getActor: () => CatalogueActor | null;
  latencyMs?: number;
  /** Shared store so decisions survive navigation within a session. */
  store?: ReviewStore;
  /** Force every call to fail (used to demonstrate/test error states). */
  failWith?: Error;
}

const sessionStore: ReviewStore = new Map();

export function createMockCatalogueService(options: MockServiceOptions): CurriculumCatalogueService {
  const snapshot = options.snapshot ?? (snapshotJson as ResearchSnapshot);
  const store = options.store ?? sessionStore;
  const latency = options.latencyMs ?? 250;
  const meta = snapshotMeta(snapshot);

  const delay = async <T>(fn: () => T): Promise<T> => {
    if (latency > 0) await new Promise((r) => setTimeout(r, latency));
    if (options.failWith) throw options.failWith;
    return fn();
  };

  const requireViewer = () => {
    const actor = options.getActor();
    if (!actor) throw new ApiError(401, 'Not signed in.');
    if (!hasPermission(actor.role, 'VIEW_CURRICULUM_CATALOGUE')) {
      throw new ApiError(403, 'Your role does not have access to the curriculum catalogue.');
    }
    return actor;
  };

  const forCombo = (grade: GradeNumber, subject: SubjectKey) => {
    const id = combinationId(grade, subject);
    const resources = snapshot.coverage.filter((r) => r.combinationId === id).map(mapResource);
    const editions = snapshot.editions.filter((e) => e.combinationId === id).map(mapEdition);
    const crosswalk = snapshot.crosswalk.filter((m) => m.combinationId === id);
    const candidates: CandidateMapping[] = crosswalk.map((m) => mapCandidate(m, store.get(m.mappingId) ?? []));
    return { id, resources, editions, crosswalk, candidates };
  };

  return {
    kind: 'mock',

    getDashboard: () =>
      delay(() => {
        requireViewer();
        const combinations = GRADES.flatMap((g) =>
          SUBJECTS.map((s) => {
            const c = forCombo(g, s);
            return summarise(g, s, c.id, c.resources, c.editions, c.candidates);
          })
        );
        return { meta, combinations };
      }),

    getCombination: (grade, subject) =>
      delay(() => {
        requireViewer();
        const c = forCombo(grade, subject);
        const ofType = (t: string) => c.resources.filter((r) => r.resourceType === t);
        return {
          meta,
          summary: summarise(grade, subject, c.id, c.resources, c.editions, c.candidates),
          frameworks: ofType('CURRICULUM_FRAMEWORK'),
          syllabi: ofType('SYLLABUS'),
          learningOutcomes: ofType('LEARNING_OUTCOMES_DOCUMENT'),
          textbookWorks: [...ofType('PRESCRIBED_TEXTBOOK_WORK'), ...ofType('TEXTBOOK_PART')],
          guidance: ofType('COURSE_IMPLEMENTATION_GUIDANCE'),
          editions: c.editions,
          languageMatrix: buildLanguageMatrix(c.resources, c.editions),
          rightsNote:
            'All sources: permission PENDING — metadata only. No textbook paragraphs, exercises or outcome wording are ingested or displayed.',
        };
      }),

    getChapterExplorer: (grade, subject) =>
      delay(() => {
        requireViewer();
        const c = forCombo(grade, subject);
        return {
          editions: c.editions,
          chaptersBySource: buildChapters(c.crosswalk),
          completenessNote:
            'Only chapters and sections that were individually source-checked are listed. The full chapter list has not been imported, and no chapters or topics are inferred.',
        };
      }),

    listCandidateMappings: (grade, subject) =>
      delay(() => {
        requireViewer();
        return forCombo(grade, subject).candidates;
      }),

    submitReview: (mappingId: string, input: ReviewInput) =>
      delay(() => {
        const actor = requireViewer();
        if (!hasPermission(actor.role, 'REVIEW_CURRICULUM_MAPPINGS')) {
          throw new ApiError(403, 'Only administrators may record global catalogue review decisions.');
        }
        const problem = validateReviewInput(input);
        if (problem) throw new ApiError(422, problem);
        const row = snapshot.crosswalk.find((m) => m.mappingId === mappingId);
        if (!row) throw new ApiError(404, `Unknown candidate mapping ${mappingId}.`);
        // Same optimistic-concurrency and transition rules as the backend contract.
        const prior = store.get(mappingId) ?? [];
        if (input.expectedRevision !== prior.length) {
          throw new ApiError(409, 'Someone else changed this mapping since you loaded it. Reload and try again.');
        }
        const state = prior.length ? prior[prior.length - 1].decision : 'AWAITING_REVIEW';
        if (!allowedDecisions(state).includes(input.decision)) {
          throw new ApiError(409, 'That decision is not a valid change from the current review state.');
        }
        const history = [
          ...prior,
          {
            decision: input.decision,
            rationale: input.rationale.trim(),
            reviewer: actor.name,
            reviewedAt: new Date().toISOString(),
          },
        ];
        store.set(mappingId, history);
        return mapCandidate(row, history);
      }),
  };
}
