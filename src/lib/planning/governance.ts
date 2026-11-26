/**
 * Pedagogical governance: Core/Non-Core classification and topic relationships.
 *
 * Classification is recorded per schedulable syllabus unit (conceptual topic/subtopic; activities and investigations are attached resources), the finest
 * level that receives classroom time. Outcome links in the current data are inferred, so classifying outcomes
 * directly would rest on unverified links.
 *
 * Lifecycle: PENDING (default, nothing recorded) → PROPOSED (with criteria, rationale, evidence) → APPROVED / REJECTED
 * by an Admin/Principal who is not the proposer. A suggestion is never applied automatically. Time shortage is not
 * an accepted criterion, and the engine never changes a classification.
 */
import type { SyllabusNode } from './syllabus';

/** MIXED = the topic has both Core and Non-Core required periods. */
export type ClassValue = 'CORE' | 'NON_CORE' | 'MIXED';
export type ReviewStatus = 'PENDING' | 'PROPOSED' | 'APPROVED' | 'REJECTED' | 'DEMO_DEFAULT' | 'TEACHER_CUSTOM';

export interface Actor {
  id: string;
  name: string;
  role: string;
}

export const CORE_CRITERIA: Record<string, string> = {
  PREREQUISITE_FOR_LATER: 'Required as a prerequisite by later units (approved prerequisite relationship)',
  FOUNDATIONAL_CONCEPT: 'Foundational concept for the stage-level curricular goals of this subject',
  ASSESSED_OUTCOME: 'Directly supports a learning outcome that is formally assessed',
  CROSS_SUBJECT_DEPENDENCY: 'Required by the other subject (approved cross-curricular relationship)',
};

export const NON_CORE_CRITERIA: Record<string, string> = {
  ENRICHMENT: 'Extension or enrichment beyond the essential outcome',
  INDEPENDENT_LEARNING_SUITABLE: 'Suitable for tracked independent learning with follow-up',
  COVERED_ELSEWHERE: 'Substantially covered by another approved unit',
};

export interface ClassificationEvent {
  at: string;
  actor: Actor;
  action: 'PROPOSED' | 'APPROVED' | 'REJECTED';
  value: ClassValue;
  note: string;
}

export interface Classification {
  nodeId: string;
  status: Exclude<ReviewStatus, 'PENDING'>;
  /** Set for records built from the relational teacher plan. 'demo_default' is hypothetical and never counts as approved. */
  origin?: 'demo_default' | 'teacher' | 'approved_import';
  value: ClassValue;
  /**
   * Approved instructional requirement for the topic: required Core and Non-Core classroom periods.
   * The engine schedules exactly these counts. Records approved before counts existed have neither field and
   * are flagged as needing an approved requirement — counts are never invented.
   */
  corePeriods?: number;
  nonCorePeriods?: number;
  independentPeriods?: number;
  teachingMode?: 'SHARED' | 'INDEPENDENT';
  criteria: string[];
  rationale: string;
  evidence: string;
  proposedBy: Actor;
  proposedAt: string;
  reviewedBy?: Actor;
  reviewedAt?: string;
  reviewNote?: string;
  history: ClassificationEvent[];
}

export type Classifications = Record<string, Classification>;

export function classificationOf(c: Classifications, nodeId: string): { status: ReviewStatus; value?: ClassValue; record?: Classification } {
  const r = c[nodeId];
  if (!r) return { status: 'PENDING' };
  return { status: r.status, value: r.value, record: r };
}

/** The value the engine may act on: only an APPROVED classification counts. */
export function approvedValue(c: Classifications, nodeId: string): ClassValue | null {
  const r = c[nodeId];
  return r && r.status === 'APPROVED' ? r.value : null;
}

export interface TopicRequirement {
  core: number;
  nonCore: number;
  independent: number;
  teachingMode: 'SHARED' | 'INDEPENDENT';
}

/** The approved per-topic requirement, or null when none is approved (legacy unit-level approvals included). */
export function approvedRequirement(c: Classifications, nodeId: string): TopicRequirement | null {
  const r = c[nodeId];
  // A hypothetical demo default feeds the engine (flagged by origin) but keeps a non-approved status everywhere else.
  if (!r || (r.status !== 'APPROVED' && r.status !== 'DEMO_DEFAULT' && r.status !== 'TEACHER_CUSTOM') || !Number.isInteger(r.corePeriods) || !Number.isInteger(r.nonCorePeriods) || r.corePeriods! < 0 || r.nonCorePeriods! < 0 || (r.origin !== 'demo_default' && r.corePeriods! + r.nonCorePeriods! < 1)) return null;
  const independent = Number.isInteger(r.independentPeriods) ? r.independentPeriods! : 0;
  if (independent < 0 || independent > r.nonCorePeriods!) return null;
  return { core: r.corePeriods!, nonCore: r.nonCorePeriods!, independent, teachingMode: r.teachingMode ?? 'INDEPENDENT' };
}

export const requirementValue = (core: number, nonCore: number): ClassValue => (core > 0 && nonCore > 0 ? 'MIXED' : core > 0 ? 'CORE' : 'NON_CORE');

export function validateRequirementProposal(core: number, nonCore: number, criteria: string[], rationale: string, evidence: string): string[] {
  const errors: string[] = [];
  const whole = (n: number) => Number.isInteger(n) && n >= 0 && n <= 60;
  if (!whole(core) || !whole(nonCore)) errors.push('Core and Non-Core periods must be whole numbers from 0 to 60.');
  else if (core + nonCore < 1) errors.push('A topic needs at least one required period.');
  if (core > 0 && !criteria.some((k) => CORE_CRITERIA[k])) errors.push('Select at least one Core criterion for the Core periods.');
  if (nonCore > 0 && !criteria.some((k) => NON_CORE_CRITERIA[k])) errors.push('Select at least one Non-Core criterion for the Non-Core periods.');
  if (criteria.some((k) => !CORE_CRITERIA[k] && !NON_CORE_CRITERIA[k])) errors.push('Unknown criterion selected.');
  if (core === 0 && criteria.some((k) => CORE_CRITERIA[k])) errors.push('Core criteria were selected but no Core periods are required.');
  if (nonCore === 0 && criteria.some((k) => NON_CORE_CRITERIA[k])) errors.push('Non-Core criteria were selected but no Non-Core periods are required.');
  if (rationale.trim().length < 20) errors.push('Reasoning must be at least 20 characters.');
  if (/(insufficient|not enough|lack of|short(age)? of|limited)\s+(instructional\s+|teaching\s+|class(room)?\s+)?time|time\s+(shortage|shortfall|constraint)|shortfall|behind schedule|calendar (is )?(short|full)/i.test(rationale)) {
    errors.push('Insufficient instructional time is not a valid reason to set Core or Non-Core requirements.');
  }
  if (!evidence.trim()) errors.push('Evidence (source reference, locator or review note) is required.');
  return errors;
}

/** Proposes a topic's instructional requirement (Core + Non-Core periods) for independent review. */
export function proposeRequirement(
  c: Classifications,
  nodeId: string,
  core: number,
  nonCore: number,
  criteria: string[],
  rationale: string,
  evidence: string,
  actor: Actor,
  at = new Date().toISOString(),
): Classifications {
  const errors = validateRequirementProposal(core, nonCore, criteria, rationale, evidence);
  if (errors.length) throw new Error(errors.join(' '));
  const next = propose(c, nodeId, requirementValue(core, nonCore), criteria, rationale, evidence, actor, at);
  return { ...next, [nodeId]: { ...next[nodeId], corePeriods: core, nonCorePeriods: nonCore } };
}

export function validateProposal(value: ClassValue, criteria: string[], rationale: string, evidence: string): string[] {
  const errors: string[] = [];
  const allowed = value === 'CORE' ? CORE_CRITERIA : NON_CORE_CRITERIA;
  if (!criteria.length) errors.push('Select at least one pedagogical criterion.');
  if (criteria.some((k) => !allowed[k])) errors.push('Selected criteria do not match the proposed classification.');
  if (rationale.trim().length < 20) errors.push('Reasoning must be at least 20 characters.');
  if (value === 'NON_CORE' && /(insufficient|not enough|lack of|short(age)? of|limited)\s+(instructional\s+|teaching\s+|class(room)?\s+)?time|time\s+(shortage|shortfall|constraint)|shortfall|behind schedule|calendar (is )?(short|full)/i.test(rationale)) {
    errors.push('Insufficient instructional time is not a valid reason to classify a unit as Non-Core.');
  }
  if (!evidence.trim()) errors.push('Evidence (source reference, locator or review note) is required.');
  return errors;
}

export function propose(
  c: Classifications,
  nodeId: string,
  value: ClassValue,
  criteria: string[],
  rationale: string,
  evidence: string,
  actor: Actor,
  at = new Date().toISOString(),
): Classifications {
  const prev = c[nodeId];
  return {
    ...c,
    [nodeId]: {
      nodeId,
      status: 'PROPOSED',
      value,
      criteria,
      rationale: rationale.trim(),
      evidence: evidence.trim(),
      proposedBy: actor,
      proposedAt: at,
      history: [...(prev?.history ?? []), { at, actor, action: 'PROPOSED', value, note: rationale.trim() }],
    },
  };
}

export function canReview(record: Classification | Relationship | undefined, actor: Actor): string | null {
  if (!record || record.status !== 'PROPOSED') return 'Only a pending proposal can be reviewed.';
  if (!['admin', 'principal'].includes(actor.role)) return 'Only an Admin or Principal can approve or reject.';
  if (record.proposedBy.id === actor.id) return 'The proposer cannot approve their own proposal; a second reviewer is required.';
  return null;
}

export function review(
  c: Classifications,
  nodeId: string,
  decision: 'APPROVED' | 'REJECTED',
  note: string,
  actor: Actor,
  at = new Date().toISOString(),
): Classifications {
  const r = c[nodeId];
  const problem = canReview(r, actor);
  if (problem) throw new Error(problem);
  if (decision === 'REJECTED' && note.trim().length < 5) throw new Error('A rejection reason is required.');
  return {
    ...c,
    [nodeId]: {
      ...r,
      status: decision,
      reviewedBy: actor,
      reviewedAt: at,
      reviewNote: note.trim(),
      history: [...r.history, { at, actor, action: decision, value: r.value, note: note.trim() }],
    },
  };
}

/**
 * Transparent, rule-based suggestion (not AI, not applied automatically). Only suggests where an approved
 * relationship in the data gives a defensible reason; otherwise returns null rather than guessing.
 */
export function suggestClassification(node: SyllabusNode, relationships: Relationship[]): { value: ClassValue; criteria: string[]; reason: string } | null {
  const approved = relationships.filter((r) => r.status === 'APPROVED');
  const prereqFor = approved.filter((r) => r.type === 'PREREQUISITE' && r.fromNodeId === node.id);
  const crossLead = approved.filter((r) => r.type === 'CROSS_CURRICULAR' && r.leadNodeId === node.id);
  const criteria: string[] = [];
  const reasons: string[] = [];
  if (prereqFor.length) {
    criteria.push('PREREQUISITE_FOR_LATER');
    reasons.push(`approved prerequisite for ${prereqFor.length} later unit(s)`);
  }
  if (crossLead.length) {
    criteria.push('CROSS_SUBJECT_DEPENDENCY');
    reasons.push(`lead unit for ${crossLead.length} approved cross-curricular link(s)`);
  }
  if (!criteria.length) return null;
  return { value: 'CORE', criteria, reason: `Rule-based suggestion: ${reasons.join('; ')}. Requires human proposal and review.` };
}

/* ----------------------------------------------------------- relationships ---- */

export type RelationshipType = 'PREREQUISITE' | 'CROSS_CURRICULAR';

export interface Relationship {
  id: string;
  type: RelationshipType;
  /** PREREQUISITE: from must be taught before to. CROSS_CURRICULAR: a Mathematics unit and a Science unit. */
  fromNodeId: string;
  toNodeId: string;
  explanation: string;
  evidence: string;
  /** CROSS_CURRICULAR only: periods of shared instruction taught once, in the lead unit. */
  sharedPeriods: number;
  leadNodeId: string | null;
  status: Exclude<ReviewStatus, 'PENDING'>;
  proposedBy: Actor;
  proposedAt: string;
  reviewedBy?: Actor;
  reviewedAt?: string;
  reviewNote?: string;
}

export function validateRelationship(
  r: Pick<Relationship, 'type' | 'fromNodeId' | 'toNodeId' | 'explanation' | 'evidence' | 'sharedPeriods' | 'leadNodeId'>,
  from: SyllabusNode | undefined,
  to: SyllabusNode | undefined,
  existing: Relationship[],
): string[] {
  const errors: string[] = [];
  if (!from || !to) return ['Both units must exist in a syllabus dataset.'];
  if (from.id === to.id) errors.push('A unit cannot relate to itself.');
  if (r.explanation.trim().length < 20) errors.push('Explain the conceptual relationship (at least 20 characters).');
  if (!r.evidence.trim()) errors.push('Evidence grounded in the syllabus sources is required (e.g. both section locators).');
  if (r.type === 'CROSS_CURRICULAR') {
    if (from.subject === to.subject) errors.push('A cross-curricular link must connect Mathematics and Science.');
    if (!Number.isInteger(r.sharedPeriods) || r.sharedPeriods < 0) errors.push('Shared periods must be a whole number of 0 or more.');
    if (r.sharedPeriods > 0 && r.leadNodeId !== from.id && r.leadNodeId !== to.id) errors.push('Choose which unit teaches the shared portion.');
  } else if (from.grade > to.grade) {
    errors.push('A prerequisite cannot come from a later class.');
  }
  const dup = existing.find(
    (x) =>
      x.status !== 'REJECTED' &&
      x.type === r.type &&
      ((x.fromNodeId === r.fromNodeId && x.toNodeId === r.toNodeId) || (r.type === 'CROSS_CURRICULAR' && x.fromNodeId === r.toNodeId && x.toNodeId === r.fromNodeId)),
  );
  if (dup) errors.push('This relationship has already been proposed.');
  return errors;
}

export function reviewRelationship(rels: Relationship[], id: string, decision: 'APPROVED' | 'REJECTED', note: string, actor: Actor, at = new Date().toISOString()): Relationship[] {
  const r = rels.find((x) => x.id === id);
  const problem = canReview(r, actor);
  if (problem) throw new Error(problem);
  if (decision === 'REJECTED' && note.trim().length < 5) throw new Error('A rejection reason is required.');
  return rels.map((x) => (x.id === id ? { ...x, status: decision, reviewedBy: actor, reviewedAt: at, reviewNote: note.trim() } : x));
}
