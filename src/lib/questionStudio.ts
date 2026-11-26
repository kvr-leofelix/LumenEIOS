import type { CompetencyKey } from '../types';

export const COMPETENCIES: CompetencyKey[] = ['LU', 'CU', 'AU', 'CT'];
export type CompetencyDistribution = Record<CompetencyKey, number>;

export function distributeQuestions(total: number, selected: CompetencyKey[]): CompetencyDistribution {
  if (!Number.isInteger(total) || total < 1 || total > 25 || !selected.length || new Set(selected).size !== selected.length || selected.some(c => !COMPETENCIES.includes(c))) {
    throw new Error('Choose a whole total from 1 to 25 and at least one competency.');
  }
  const codes = COMPETENCIES.filter(c => selected.includes(c));
  return Object.fromEntries(COMPETENCIES.map(c => [c, codes.includes(c) ? Math.floor(total / codes.length) + (codes.indexOf(c) < total % codes.length ? 1 : 0) : 0])) as CompetencyDistribution;
}

export function distributionError(counts: CompetencyDistribution, total: number): string {
  if (COMPETENCIES.some((code) => !Number.isInteger(counts[code]) || counts[code] < 0)) {
    return 'Competency counts must be non-negative whole numbers.';
  }
  const allocated = COMPETENCIES.reduce((sum, code) => sum + counts[code], 0);
  if (allocated === 0) return 'Allocate at least one question to a competency.';
  if (allocated !== total) return `Allocated ${allocated} questions; the requested total is ${total}. Counts must match.`;
  return '';
}
