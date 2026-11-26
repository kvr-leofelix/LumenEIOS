import type {AssessmentStages} from './panchapadi';
export type Competency = 'LU' | 'CU' | 'AU' | 'CT';
export type Stage = 'Adheeti' | 'Bodh' | 'Abhyas' | 'Prayog' | 'Prasar';
export type Kind = 'support' | 'teach_back' | 'mission';
export interface Scope {
  schools?: { id: string; name: string }[];
  students: { id: string; name: string; class_id: string; school_id: string }[];
  classes: { id: string; name: string; school_id: string; subjects: {id: string; name: string}[] }[];
}
export interface Topic { id: string; class_id: string; subject_id: string; title: string }
export interface Activity { id: string; topic_id: string; kind: Kind; title: string; instructions: string; rubric: string; competency: Competency; stage: Stage; version: number }
export interface Feedback { correctly_understood: string[]; missing_concepts: string[]; misconceptions: string[]; strengths: string[]; next_step: string }
export interface Evaluation { kind: 'ai' | 'ai_failure' | 'teacher'; date: string; feedback?: Feedback | string; outcome?: string; error?: string; completed?: boolean }
export interface Attempt { id: string; assignment_id: string; response: string; hints: number | null; submitted_at: string; evaluations: Evaluation[]; completed: boolean; version: number }
export interface Assignment { id: string; student_id: string; snapshot: Omit<Activity,'topic_id'> & {topic_id:string|null;topic_title: string; subject_id: string; class_id: string;assessment_result_id?:string;assessment_id?:string;evidence_positions?:number[];generation?:string}; assigned_at: string; due_at: string | null; intervention_for: string | null; attempts: Attempt[] }
export interface Finding { subject_id: string; topic_id: string; topic: string; competency: Competency; observations: number; activities: number; score_pct: number | null; status: string; reason: string; rule: string; suggestion: string; sources: {id: string; assignment_id: string; attempt_id: string; score: number; maximum: number; correct: boolean | null; hints: number | null; recorded_at: string; source: string}[] }
export interface AssessmentObservation { id: string; result_id: string; submission_id: string; assessment_id: string; assessment_title: string; subject_id: string; topic_id: string | null; topic: string | null; competency: Competency; score: number; maximum: number; correct: boolean | null; source: string; recorded_at: string; provenance: string; scoring_basis: string }
export interface AssessmentFinding { subject_id: string; topic_id: string | null; topic: string | null; competency: Competency; observations: number; assessments: number; score_pct: number; reason: string; status: string; suggestion: string; sources: AssessmentObservation[] }
export interface Support { panchapadi_assessments?:AssessmentStages[]; student_id: string; findings: Finding[]; empty_message: string | null; assessment_findings?: AssessmentFinding[] }
export interface Journey { panchapadi_assessments?:AssessmentStages[]; assessment_observations?: AssessmentObservation[]; student_id: string; participation: number; completed_assignments: number; verified_observations: number; stages: Record<Stage, number>; timeline: {kind: string; date: string; title: string; stage: Stage | null; topic: string | null; subject_id: string | null; competency: Competency | null; detail: string}[]; trends: {subject_id: string; topic_id: string; topic: string; competency: Competency; scoring_basis: string; points: {date: string; score_pct: number}[]; change: number | null}[] }
