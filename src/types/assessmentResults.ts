import type {StageEvaluation} from './panchapadi';
import type {Stage} from './learnsphere';
export interface LearningDraft {kind:'support'|'teach_back'|'mission';positions:number[];stage:Stage;title:string;explanation:string;learning_tip:string;scenario:string;instructions:string;expected_submission:string;objective:string;rubric:string}
export interface LearningDecision extends LearningDraft {decision:'draft'|'approved'|'rejected';topic_id:string|null;activity_id?:string;assignment_id?:string}
export interface AssessmentAnswer { position: number; selected_option_index?: number | null; answer_text?: string | null }
export interface AssessmentOutcome { position: number; question_id?: string; competency: string; score?: number | null; maximum: number; correct?: boolean | null; provenance: string; feedback?: string; topic_id?: string | null; explanation?:string;key_verified?:boolean }
export interface AssessmentResult {
  id: string; assessment_id: string; assessment_title: string; student_id: string; school_id: string; class_id: string; subject_id: string;
  submission_id?: string | null; version: number; status: string;
  questions: {position: number; id?: string; text: string; type: string; options: string[]; marks: number; competency: string; correct_answer?: string; marking_rubric?: string}[];
  answers: AssessmentAnswer[]; automatic_outcomes: AssessmentOutcome[]; outcomes: AssessmentOutcome[];
  reviews: {revision_id: string; reviewer_id: string; date: string; feedback: string; outcomes: AssessmentOutcome[];panchapadi?:StageEvaluation;learning_plan?:LearningDecision[]}[];
  learning_drafts?:LearningDraft[];guidance_status?:string;evaluation_warnings?:string[];
  panchapadi?:StageEvaluation;
  marks_obtained?: number | null; total_marks: number;
}
