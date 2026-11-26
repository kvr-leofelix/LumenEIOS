import { REVIEW_RATIONALE_MAX, REVIEW_RATIONALE_MIN } from './contract';
import type {
  CandidateMapping,
  CatalogueDashboardData,
  ChapterExplorerData,
  CombinationDetail,
  DataSourceKind,
  GradeNumber,
  ReviewDecision,
  SubjectKey,
} from '../types';
import type { Role } from '../../../types';

/** Who is acting. The HTTP implementation relies on the bearer token instead; the backend is the authority. */
export interface CatalogueActor {
  name: string;
  role: Role;
}

export interface ReviewInput {
  decision: ReviewDecision;
  rationale: string;
  /** Must equal the mapping's current revision (optimistic concurrency, as in the backend contract). */
  expectedRevision: number;
}

/**
 * MOCK-mode seam between the research-snapshot screens and their data. API mode uses
 * NcertApi (api/ncertApi.ts) against the real backend contract instead.
 */
export interface CurriculumCatalogueService {
  readonly kind: DataSourceKind;
  getDashboard(): Promise<CatalogueDashboardData>;
  getCombination(grade: GradeNumber, subject: SubjectKey): Promise<CombinationDetail>;
  getChapterExplorer(grade: GradeNumber, subject: SubjectKey): Promise<ChapterExplorerData>;
  listCandidateMappings(grade: GradeNumber, subject: SubjectKey): Promise<CandidateMapping[]>;
  submitReview(mappingId: string, input: ReviewInput): Promise<CandidateMapping>;
}

export { REVIEW_RATIONALE_MIN as MIN_RATIONALE_LENGTH } from './contract';

export function validateReviewInput(input: ReviewInput): string | null {
  if (!['APPROVED', 'REJECTED', 'REVISION_REQUESTED'].includes(input.decision)) {
    return 'Choose a review decision.';
  }
  const n = input.rationale.trim().length;
  if (n < REVIEW_RATIONALE_MIN) {
    return `A decision rationale of at least ${REVIEW_RATIONALE_MIN} characters is required.`;
  }
  if (n > REVIEW_RATIONALE_MAX) {
    return `The rationale must be at most ${REVIEW_RATIONALE_MAX} characters.`;
  }
  return null;
}
