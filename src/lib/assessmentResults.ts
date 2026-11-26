import { apiRequest as request } from './apiClient';
import type { AssessmentAnswer, AssessmentResult } from '../types/assessmentResults';
export const assessmentResults = {
  retryStages: (id:string,refreshGuidance=false) => request<AssessmentResult>(`/assessments/results/${encodeURIComponent(id)}/panchapadi/evaluate${refreshGuidance?'?refresh_guidance=true':''}`,{method:'POST'}),
  mine: () => request<AssessmentResult[]>('/assessments/my-results'),
  forReview: () => request<AssessmentResult[]>('/assessments/results-for-review'),
  submit: (id: string, answers: AssessmentAnswer[], key: string) => request<AssessmentResult>(`/assessments/${encodeURIComponent(id)}/answers`, {method:'POST',body:JSON.stringify({answers,request_key:key})}),
  review: (id: string, body: unknown) => request<AssessmentResult>(`/assessments/results/${encodeURIComponent(id)}/review`, {method:'POST',body:JSON.stringify(body)}),
};
