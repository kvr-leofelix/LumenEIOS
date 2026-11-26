import type { Assessment, AssessmentResult, CompetencyScores, Student } from '../types';

export const DIMS = ['LU', 'CU', 'AU', 'CT'] as const;
export const DIM_LABEL: Record<string, string> = {
  LU: 'Language Understanding', CU: 'Conceptual Understanding', AU: 'Application', CT: 'Critical Thinking',
};

const mean = (xs: number[]) => (xs.length ? Math.round(xs.reduce((a, b) => a + b, 0) / xs.length) : 0);

export function averageScores(students: Student[], key: 'competencies' | 'baselineCompetencies' = 'competencies'): CompetencyScores {
  return {
    LU: mean(students.map(s => s[key].LU)), CU: mean(students.map(s => s[key].CU)),
    AU: mean(students.map(s => s[key].AU)), CT: mean(students.map(s => s[key].CT)),
    overall: mean(students.map(s => s[key].overall)),
  };
}

/** "Half-Yearly Examination - Science" -> "Half-Yearly Examination". */
export function examName(title: string): string {
  return title.replace(/\s+-\s+[^-]+$/, '');
}

export function formatDay(day?: string | null): string {
  if (!day) return '';
  const d = new Date(day);
  return Number.isNaN(d.getTime()) ? day : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

export interface ExamSummary { assessment: Assessment; average: number; highest: number; lowest: number; count: number }

export function summariseExams(assessments: Assessment[], results: AssessmentResult[]): ExamSummary[] {
  const byExam = new Map<string, AssessmentResult[]>();
  for (const r of results) {
    const list = byExam.get(r.assessmentId);
    if (list) list.push(r); else byExam.set(r.assessmentId, [r]);
  }
  return assessments
    .filter(a => byExam.has(a.id))
    .map(a => {
      const rows = byExam.get(a.id)!;
      const pcts = rows.map(r => r.percentage);
      return { assessment: a, average: mean(pcts), highest: Math.max(...pcts), lowest: Math.min(...pcts), count: rows.length };
    })
    .sort((x, y) => x.assessment.date.localeCompare(y.assessment.date));
}

export function grade(pct: number): string {
  // CBSE-style grade bands for Classes 6-8.
  if (pct >= 91) return 'A1';
  if (pct >= 81) return 'A2';
  if (pct >= 71) return 'B1';
  if (pct >= 61) return 'B2';
  if (pct >= 51) return 'C1';
  if (pct >= 41) return 'C2';
  if (pct >= 33) return 'D';
  return 'E';
}
