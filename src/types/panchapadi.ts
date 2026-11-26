import type {Stage} from './learnsphere';
import type {LearningDecision} from './assessmentResults';
export const PANCHAPADI_STAGES: Stage[]=['Adheeti','Bodh','Abhyas','Prayog','Prasar'];
export interface StageMapping {stage:Stage;reasoning:string;prerequisite_test:boolean;procedural_practice:boolean;independent_extension:boolean}
export interface QuestionStageMapping {position:number;mappings:StageMapping[]}
export interface StageScore {stage:Stage;score_pct?:number|null;earned_marks?:number|null;maximum_marks?:number|null;evidence_count:number;status:string;explanation:string;teacher_verified:boolean;contributions:{position:number;question_id?:string|null;reasoning:string;score?:number|null;maximum:number;eligible:boolean;exclusion_reason?:string|null}[]}
export interface StageEvaluation {status:string;attempt_id?:string;date?:string;error?:string;mapping:QuestionStageMapping[];stages:StageScore[];teacher_verified?:boolean;review_revision_id?:string}
export interface AssessmentStages {result_id:string;assessment_id:string;assessment_name:string;subject_id:string;assessed_at:string;evaluation:StageEvaluation;learning_plan?:LearningDecision[]}
export interface StageHistoryPoint {result_id:string;assessment_id:string;assessment_name:string;subject_id:string;assessed_at:string;score_pct:number|null;earned_marks:number|null;maximum_marks:number|null;evidence_count:number;status:string;explanation:string;review_revision_id:string|null;teacher_verified?:boolean}
export interface StageHistory {stage:Stage;points:StageHistoryPoint[]}
export interface PanchapadiHistory {student_id:string;graphs:StageHistory[]}
