import { apiRequest as request } from './apiClient';
import type {PanchapadiHistory} from '../types/panchapadi';
import type { Scope, Topic, Activity, Assignment, Attempt, Support, Journey } from '../types/learnsphere';
const base = '/learnsphere';
const post = <T>(path: string, body: unknown) => request<T>(base + path, {method: 'POST', body: JSON.stringify(body)});
export const learnsphere = {
  panchapadi: (id:string) => request<PanchapadiHistory>(`${base}/students/${encodeURIComponent(id)}/panchapadi?include_provisional=true`),
  assessmentOptions: (id:string) => request<import('../types/assessmentGuidance').AssessmentOption[]>(`${base}/students/${encodeURIComponent(id)}/assessments`),
  assessmentGuidance: (id:string,assessment:string) => request<import('../types/assessmentGuidance').AssessmentGuidance>(`${base}/students/${encodeURIComponent(id)}/assessments/${encodeURIComponent(assessment)}/guidance`),
  assessmentResult: (id:string) => request<import('../types/assessmentResults').AssessmentResult>('/assessments/results/'+encodeURIComponent(id)),
  reviewCompetencies: (studentId:string,assessmentId:string,body:unknown) =>
    post<import('../types/assessmentGuidance').AssessmentGuidance>('/students/'+encodeURIComponent(studentId)+'/assessments/'+encodeURIComponent(assessmentId)+'/competencies',body),
  scope: () => request<Scope>(base + '/scope'),
  summary: () => request<{students: number; assignments: number; completed_assignments: number}>(base + '/summary'),
  support: (id: string) => request<Support>(`${base}/students/${encodeURIComponent(id)}/support`),
  journey: (id: string) => request<Journey>(`${base}/students/${encodeURIComponent(id)}/journey`),
  topics: (id: string) => request<Topic[]>(`${base}/topics?class_id=${encodeURIComponent(id)}`),
  createTopic: (body: unknown) => post<Topic>('/topics', body),
  activities: (id: string) => request<Activity[]>(`${base}/activities?class_id=${encodeURIComponent(id)}`),
  createActivity: (body: unknown) => post<Activity>('/activities', body),
  updateActivity: (id: string, body: unknown) => request<Activity>(`${base}/activities/${id}`, {method:'PUT', body:JSON.stringify(body)}),
  assign: (id: string, body: unknown) => post<{assignment_ids: string[]}>(`/activities/${id}/assignments`, body),
  assignments: (id: string) => request<Assignment[]>(`${base}/assignments?student_id=${encodeURIComponent(id)}`),
  submit: (id: string, body: unknown) => post<Attempt>(`/assignments/${id}/attempts`, body),
  evaluate: (id: string) => post<Attempt>(`/attempts/${id}/evaluate`, {}),
  review: (id: string, body: unknown) => post<Attempt>(`/attempts/${id}/review`, body),
};
