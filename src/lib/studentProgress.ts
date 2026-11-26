/** Types and helpers for Unified Student Progress (backend contracts only). */

export type ProgressAudience = 'educator' | 'student_or_parent';
export type CompetencyDim = 'LU' | 'CU' | 'AU' | 'CT';
export type EvidenceStatus = 'demonstrated' | 'developing' | 'insufficient';
export type SubjectCompetencyStatus = 'available' | 'partial' | 'unavailable';

export const COMPETENCY_DIMS: CompetencyDim[] = ['LU', 'CU', 'AU', 'CT'];

export const COMPETENCY_LABELS: Record<CompetencyDim, string> = {
  LU: 'Language Understanding',
  CU: 'Concept Understanding',
  AU: 'Application',
  CT: 'Critical Thinking',
};

export type CompetencyScores = {
  LU: number;
  CU: number;
  AU: number;
  CT: number;
  overall: number;
};

export type OptionalCompetencyScores = {
  LU: number | null;
  CU: number | null;
  AU: number | null;
  CT: number | null;
  overall: number | null;
};

export type CompetencyEvidence = {
  source_type: string;
  source_id: string;
  assessment_id?: string | null;
  assignment_id?: string | null;
  title?: string | null;
  occurred_at?: string | null;
  awarded_marks?: number | null;
  max_marks?: number | null;
  scores?: OptionalCompetencyScores | null;
  dimension?: CompetencyDim | null;
  dimension_value?: number | null;
};

export type SubjectCompetencyProfile = {
  student_id: string;
  subject_id: string;
  subject_name?: string | null;
  status: SubjectCompetencyStatus;
  scores?: OptionalCompetencyScores | null;
  evidence_count: number;
  dimension_evidence_counts: Record<string, number>;
  evidence: CompetencyEvidence[];
  methodology: string;
};

export type ProgressEvent = {
  id: string;
  source_type: string;
  source_id: string;
  subject_id?: string | null;
  subject_name?: string | null;
  title?: string | null;
  occurred_at?: string | null;
  awarded_marks?: number | null;
  max_marks?: number | null;
  percentage?: number | null;
  evaluation_status?: string | null;
  is_scanned?: boolean | null;
  competency_scores?: CompetencyScores | null;
  feedback?: string | null;
  assignment_id?: string | null;
  assessment_id?: string | null;
};

export type SubjectPerformance = {
  subject_id: string;
  subject_name?: string | null;
  event_count: number;
  comparable_event_count: number;
  average_percentage?: number | null;
  latest_percentage?: number | null;
  latest_occurred_at?: string | null;
  competencies?: SubjectCompetencyProfile | null;
};

export type Recommendation = {
  kind: string;
  summary: string;
  evidence: string[];
  subject_id?: string | null;
  competency?: string | null;
};

export type StudentProgressOverview = {
  student: {
    id: string;
    name: string;
    roll_no: number;
    school_id: string;
    class_id: string;
    class_name: string;
    subject_ids: string[];
    subject_names: string[];
  };
  audience: ProgressAudience;
  overall: {
    verified_event_count: number;
    average_percentage?: number | null;
    latest_activity_at?: string | null;
  };
  subjects: SubjectPerformance[];
  competencies: {
    current: CompetencyScores;
    baseline: CompetencyScores;
    source: string;
    history: ProgressEvent[];
  };
  subject_competencies: SubjectCompetencyProfile[];
  recent_activity: ProgressEvent[];
  trends: Array<{
    occurred_at: string;
    percentage: number;
    subject_id?: string | null;
    subject_name?: string | null;
    source_type: string;
    source_id: string;
    title?: string | null;
  }>;
  subject_trends: Array<{
    subject_id: string;
    subject_name?: string | null;
    points: Array<{
      occurred_at: string;
      percentage: number;
      source_type: string;
      source_id: string;
      title?: string | null;
    }>;
  }>;
  recommendations: Recommendation[];
  generated_at: string;
};

export type SubjectProgress = {
  student_id: string;
  subject_id: string;
  subject_name?: string | null;
  performance: SubjectPerformance;
  competencies: SubjectCompetencyProfile;
  events: ProgressEvent[];
  trend: Array<{
    occurred_at: string;
    percentage: number;
    source_type: string;
    source_id: string;
    title?: string | null;
  }>;
  recommendations: Recommendation[];
  generated_at: string;
};

export type SubjectTimeline = {
  student_id: string;
  subject_id: string;
  subject_name?: string | null;
  academic_year?: string;
  months?: TimelineCheckpoint[];
  terms?: TimelineCheckpoint[];
  methodology?: string;
  [key: string]: unknown;
};

export type TimelineCheckpoint = {
  student_id: string;
  subject_id: string;
  subject_name?: string | null;
  period_kind: 'month' | 'term';
  period_id: string;
  period_label: string;
  academic_year: string;
  status: SubjectCompetencyStatus;
  scores?: OptionalCompetencyScores | null;
  evidence_count: number;
  assessment_count?: number;
  coverage?: { dimensions_present: number; dimensions_total: number };
  methodology?: string;
  evidence_ids?: string[];
};

export type ProgressExplanations = {
  student_id: string;
  subject_id: string;
  findings: Array<{
    kind: string;
    summary: string;
    subject_id: string;
    competency?: string | null;
    evidence_ids: string[];
    period_ids?: string[];
    caveat?: string;
  }>;
  methodology: string;
};

/** Map backend availability to the product evidence labels (no score invention). */
export function evidenceStatusFromProfile(
  status: SubjectCompetencyStatus,
  dim?: CompetencyDim,
  profile?: SubjectCompetencyProfile | null,
): EvidenceStatus {
  if (status === 'unavailable') return 'insufficient';
  if (dim && profile) {
    const count = profile.dimension_evidence_counts?.[dim] ?? 0;
    const score = profile.scores?.[dim];
    if (count <= 0 || score == null) return 'insufficient';
    if (status === 'partial') return 'developing';
    return 'demonstrated';
  }
  if (status === 'partial') return 'developing';
  return 'demonstrated';
}

export function evidenceStatusLabel(status: EvidenceStatus): string {
  if (status === 'demonstrated') return 'Demonstrated';
  if (status === 'developing') return 'Developing';
  return 'Insufficient evidence';
}

export function evidenceStatusVariant(
  status: EvidenceStatus,
): 'success' | 'warning' | 'danger' {
  if (status === 'demonstrated') return 'success';
  if (status === 'developing') return 'warning';
  return 'danger';
}

export function formatPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return `${Math.round(value)}%`;
}

export function formatWhen(value: string | null | undefined): string {
  if (!value) return 'Date unavailable';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function sourceTypeLabel(source: string): string {
  switch (source) {
    case 'differentiated_homework':
      return 'Differentiated homework';
    case 'assessment_studio':
      return 'Assessment studio';
    case 'answer_sheet_ocr':
      return 'Answer sheet OCR';
    case 'competency_snapshot':
      return 'Competency snapshot';
    default:
      return source.replace(/_/g, ' ');
  }
}

export function progressPaths(role: string, studentId?: string) {
  if (role === 'student') {
    return {
      overview: '/student/progress',
      subject: (subjectId: string) => `/student/progress/subjects/${encodeURIComponent(subjectId)}`,
    };
  }
  if (role === 'parent') {
    const id = studentId || '';
    return {
      overview: `/parent/students/${encodeURIComponent(id)}/progress`,
      subject: (subjectId: string) =>
        `/parent/students/${encodeURIComponent(id)}/progress/subjects/${encodeURIComponent(subjectId)}`,
    };
  }
  const id = studentId || '';
  return {
    overview: `/teacher/students/${encodeURIComponent(id)}/progress`,
    subject: (subjectId: string) =>
      `/teacher/students/${encodeURIComponent(id)}/progress/subjects/${encodeURIComponent(subjectId)}`,
  };
}
