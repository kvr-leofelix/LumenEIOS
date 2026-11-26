/**
 * LumenEIOS Production API Client
 * Facilitates typed asynchronous communication with the FastAPI backend.
 * Provides resilient fallback handling for local offline demonstration environments.
 */

import type { Role, Student, User, CompetencyKey } from '../types';
import { DEMO_MODE, clearTeachingCache, apiErrorMessage } from './runtime';

// Prefer VITE_API_URL. Local default is same-origin /api/v1 (Vite proxies to FastAPI).
const API_BASE_URL = ((import.meta as any).env?.VITE_API_URL || '/api/v1').replace(/\/+$/, '');

type AccountDetails = {
  name: string;
  email: string;
  password: string;
  phone?: string;
  address?: string;
  date_of_birth?: string;
};

type ApiUser = Pick<User, 'id' | 'name' | 'email'> & {
  role: Role;
  school_id: string | null;
  avatar?: string;
  designation?: string;
  demo_root?: boolean;
};

export class ApiError extends Error {
  constructor(public status: number, message: string, public data?: any) {
    super(message);
    this.name = 'ApiError';
  }
}

export type ProcessStep = {
  step: string;
  label: string;
  done: number;
  total: number;
};

export type AssignmentTarget = { id: string; name: string; school_id?: string; school_name?: string; subjects: { id: string; name: string }[] };

export type DemoWalkthrough = {
  student_name: string;
  student_email: string;
  subject_name: string;
  assessment_id: string;
  title: string;
  class_name: string;
  extracted_text: string;
  evaluated: boolean;
  total_marks_obtained: number | null;
  max_possible_marks: number | null;
  percentage: number | null;
  graph: {
    nodes: Array<{ id: string; name: string; subject: string; learning_status: string; overall_mastery: number | null }>;
    edges: Array<{ source_id: string; target_id: string; relationship: string }>;
    insights: string[];
  };
};

export interface AssignmentUploads {
  assessment: {
    id: string; title: string; date: string; status: string; total_marks: number; class_id: string;
    class_name: string | null; subject_id: string; subject_name: string | null;
    questions: { index: number; text: string; marks: number; competency: string; type: string; options: string[];
      correct_answer?: string | null; marking_rubric?: string | null; topic?: string | null }[];
  };
  students: {
    student_id: string; name: string; roll_no: number;
    uploads: { history_id: string; file_name: string; extracted_text: string; pages_processed: number; uploaded_at: string | null }[];
    grade: { submission_id: string; marks_obtained: number; total_marks: number; percentage: number; feedback: string | null; graded_on: string } | null;
  }[];
  summary: { students: number; uploaded: number; graded: number };
}

export interface PublishedGrade {
  submission_id: string; student_id: string; student_name: string; marks_obtained: number; total_marks: number;
  percentage: number; competency_scores: Record<string, number>; regraded: boolean;
  parameters_before: Record<string, number>; parameters_after: Record<string, number>;
}

export type UploadAssignment = {
  id: string;
  title: string;
  date: string;
  class_name: string;
  subject_name: string;
  total_marks: number;
  uploaded: boolean;
  questions: Array<{
    id?: string;
    text: string;
    type: string;
    options?: string[];
    marks: number;
    competency?: string;
  }>;
};

function authHeaders(options: RequestInit = {}): Record<string, string> {
  const token = localStorage.getItem('lumeneios_token');
  const currentSchoolId = localStorage.getItem('lumeneios_current_school') || 'school-1';
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  const headers: Record<string, string> = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    'X-School-Id': currentSchoolId,
    ...(options.headers as Record<string, string>),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

function errorMessage(errorBody: any, fallback: string) {
  const detail = errorBody?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => (typeof item === 'string' ? item : item?.msg || 'Request failed')).join(' ');
  }
  return fallback;
}

function progressBase(scope: { role: string; studentId?: string }) {
  if (scope.role === 'student') return '/students/me/progress';
  if (scope.role === 'parent') {
    if (!scope.studentId) throw new ApiError(400, 'Select a linked student to view progress.');
    return `/parents/me/students/${encodeURIComponent(scope.studentId)}/progress`;
  }
  if (!scope.studentId) throw new ApiError(400, 'Select a student to view progress.');
  return `/students/${encodeURIComponent(scope.studentId)}/progress`;
}

function progressOverviewPath(scope: { role: string; studentId?: string }) {
  return progressBase(scope);
}

/** Browsers report every dropped/refused connection as "Failed to fetch"; say what it means. */
const NETWORK_FAILURE = 'Could not reach the LumenEIOS server, or it stopped while working on this request. '
  + 'Check that the backend window is still open (start-lumeneios). If an OCR or AI step was running, the '
  + 'local Qwen model may have run out of GPU memory: stop every LumenEIOS server (stop-lumeneios), start '
  + 'again, or choose Gemini (fallback).';

function networkError(err: any): ApiError {
  const message = String(err?.message || '');
  if (err?.name === 'AbortError') return new ApiError(0, 'The request was cancelled.');
  return new ApiError(0, !message || /failed to fetch|networkerror|network error|load failed|err_/i.test(message)
    ? NETWORK_FAILURE : message);
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  if (DEMO_MODE) throw new ApiError(0, 'Offline demonstration: live API access is disabled.');
  const token = localStorage.getItem('lumeneios_token');
  const url = `${API_BASE_URL}${endpoint}`;
  try {
    const response = await fetch(url, { ...options, headers: authHeaders(options) });

    if (endpoint !== '/auth/login' && token !== localStorage.getItem('lumeneios_token')) {
      throw new ApiError(409, 'The session changed while this request was pending. Reload the current account.');
    }
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({ detail: response.statusText }));
      if (response.status === 401) {
        localStorage.removeItem('lumeneios_token');
        clearTeachingCache();
        window.dispatchEvent(new Event('lumeneios-session-expired'));
      }
      throw new ApiError(
        response.status,
        apiErrorMessage(response.status, errorBody.detail) || errorMessage(errorBody, 'API request failed'),
        errorBody,
      );
    }

    // 204 No Content (e.g. a DELETE) has no JSON body to parse.
    if (response.status === 204 || response.headers.get('content-length') === '0') return undefined as T;
    return await response.json();
  } catch (err: any) {
    if (err instanceof ApiError) throw err;
    if (err instanceof SyntaxError) throw new ApiError(0, 'The server sent an unreadable response.');
    throw networkError(err);
  }
}

async function postEventStream<T>(
  endpoint: string,
  options: RequestInit,
  onProgress: (step: ProcessStep) => void,
): Promise<T> {
  if (DEMO_MODE) throw new ApiError(0, 'Offline demonstration: live API access is disabled.');
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, { ...options, headers: authHeaders(options) });
  } catch (err: any) {
    throw networkError(err);
  }
  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, errorMessage(errorBody, 'API request failed') || 'API request failed', errorBody);
  }
  if (!response.body) throw new ApiError(0, 'The server did not report progress.');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result: T | undefined;
  let failed: ApiError | undefined;
  while (true) {
    let chunk: ReadableStreamReadResult<Uint8Array>;
    try {
      chunk = await reader.read();
    } catch (err: any) {
      throw networkError(err);  // the server went away mid-job (e.g. the model crashed)
    }
    const { value, done } = chunk;
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() ?? '';
    for (const chunk of chunks) {
      const line = chunk.split('\n').find((item) => item.startsWith('data: '));
      if (!line) continue;
      const event = JSON.parse(line.slice(6));
      if (event.kind === 'progress') onProgress(event);
      else if (event.kind === 'complete') result = event.result as T;
      else if (event.kind === 'error') failed = new ApiError(event.status || 500, event.message || 'The process failed.');
    }
  }
  if (failed) throw failed;
  if (result === undefined) throw new ApiError(0, 'The server stopped before finishing. ' + NETWORK_FAILURE.split('. ').slice(1).join('. '));
  return result;
}
/** Shared typed request helper (auth header + school context) for feature service modules. */
export const apiRequest = request;

function mapQuestionOut(q: any) {
  return {
    id: q.id,
    assessmentId: q.assessment_id || q.assessmentId,
    subjectId: q.subject_id || q.subjectId,
    text: q.text,
    type: q.type,
    options: q.options || undefined,
    correctAnswer: q.correct_answer ?? q.correctAnswer,
    markingRubric: q.marking_rubric ?? q.markingRubric,
    marks: q.marks,
    competency: q.competency,
    bloomLevel: q.bloom_level || q.bloomLevel,
    topic: q.topic ?? null,
    sourceDocumentIds: q.source_document_ids || q.sourceDocumentIds || [],
    sourceDocumentNames: q.source_document_names || q.sourceDocumentNames || [],
    isAiGenerated: q.is_ai_generated ?? q.isAiGenerated ?? false,
  };
}

function mapSourceDocOut(d: any) {
  return {
    id: d.id,
    schoolId: d.school_id || d.schoolId || 'school-1',
    subjectId: d.subject_id || d.subjectId,
    uploadedBy: d.uploaded_by || d.uploadedBy || 'user-teacher-1',
    fileName: d.file_name || d.fileName,
    mimeType: d.mime_type || d.mimeType,
    fileSize: d.file_size ?? d.fileSize ?? 0,
    pageCount: d.page_count ?? d.pageCount ?? 1,
    docType: d.doc_type || d.docType || 'source_material',
    status: d.status || 'ready',
    extractedTextPreview: d.extracted_text_preview || d.extractedTextPreview || '',
    createdAt: d.created_at || d.createdAt,
  };
}

function mapBatchItemOut(it: any) {
  return {
    id: it.id,
    batchId: it.batch_id || it.batchId,
    documentId: it.document_id ?? it.documentId ?? null,
    fileName: it.file_name || it.fileName,
    fileSize: it.file_size ?? it.fileSize ?? 0,
    mimeType: it.mime_type || it.mimeType || 'application/pdf',
    pageCount: it.page_count ?? it.pageCount ?? 1,
    pageRange: it.page_range ?? it.pageRange ?? null,
    status: it.status,
    stageProgress: it.stage_progress ?? it.stageProgress ?? 0,
    errorMessage: it.error_message ?? it.errorMessage ?? null,
    retryCount: it.retry_count ?? it.retryCount ?? 0,
    studentId: it.student_id ?? it.studentId ?? null,
    studentName: it.student_name ?? it.studentName ?? null,
    studentConfidence: it.student_confidence ?? it.studentConfidence ?? 0,
    ocrConfidence: it.ocr_confidence ?? it.ocrConfidence ?? 0,
    extractedText: it.extracted_text ?? it.extractedText ?? null,
    questionEvaluations: it.question_evaluations || it.questionEvaluations || [],
    marksObtained: it.marks_obtained ?? it.marksObtained ?? 0,
    maxMarks: it.max_marks ?? it.maxMarks ?? 25,
    percentage: it.percentage ?? 0,
    grade: it.grade || 'C',
    competencyScores: it.competency_scores || it.competencyScores || {},
    requiresReview: it.requires_review ?? it.requiresReview ?? false,
    reviewReasons: it.review_reasons || it.reviewReasons || [],
    teacherApproved: it.teacher_approved ?? it.teacherApproved ?? false,
    approvedById: it.approved_by_id ?? it.approvedById ?? null,
    approvedAt: it.approved_at ?? it.approvedAt ?? null,
  };
}

function mapBatchOut(b: any) {
  return {
    id: b.id,
    schoolId: b.school_id || b.schoolId || 'school-1',
    classId: b.class_id || b.classId,
    className: b.class_name ?? b.className ?? null,
    subjectId: b.subject_id || b.subjectId,
    subjectName: b.subject_name ?? b.subjectName ?? null,
    assessmentId: b.assessment_id || b.assessmentId,
    assessmentTitle: b.assessment_title ?? b.assessmentTitle ?? null,
    createdById: b.created_by_id || b.createdById || 'user-teacher-1',
    uploadMode: b.upload_mode || b.uploadMode || 'bulk',
    status: b.status,
    totalFiles: b.total_files ?? b.totalFiles ?? 0,
    validFiles: b.valid_files ?? b.validFiles ?? 0,
    invalidOrDuplicateFiles: b.invalid_or_duplicate_files ?? b.invalidOrDuplicateFiles ?? 0,
    completedFiles: b.completed_files ?? b.completedFiles ?? 0,
    reviewRequiredFiles: b.review_required_files ?? b.reviewRequiredFiles ?? 0,
    failedFiles: b.failed_files ?? b.failedFiles ?? 0,
    splitMultiPdf: b.split_multi_pdf ?? b.splitMultiPdf ?? false,
    concurrencyLimit: b.concurrency_limit ?? b.concurrencyLimit ?? 4,
    createdAt: b.created_at ?? b.createdAt ?? null,
    completedAt: b.completed_at ?? b.completedAt ?? null,
    items: Array.isArray(b.items) ? b.items.map(mapBatchItemOut) : [],
  };
}

export type AssistantTurn = { role: 'user' | 'assistant'; content: string };
export type AssistantReply = {
  answer: string;
  links: { label: string; path: string }[];
  model_available: boolean;
};

export interface DevAccount {
  id: string; name: string; role: Role; email: string; username: string | null; school_id: string | null;
  school_name: string | null; designation: string | null; featured: boolean;
}

export const apiClient = {
  /** Role-scoped database workspace for the dashboards. */
  workspace() {
    return request<import('./workspace').Workspace>('/workspace');
  },
  homework: {
    call<T = any>(path: string, method = 'GET', body?: unknown) {
      return request<T>(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    },
    assignments() { return request<any[]>('/students/me/homework/assignments'); },
    assignment(id: string) { return request<any>(`/students/me/homework/assignments/${encodeURIComponent(id)}`); },
    submission(id: string) { return request<any>(`/students/me/homework/assignments/${encodeURIComponent(id)}/submission`); },
    save(id: string, answers: unknown[], version: number | null) {
      return request<any>(`/students/me/homework/assignments/${encodeURIComponent(id)}/submission`, {
        method: 'PUT', body: JSON.stringify({ answers, ...(version == null ? {} : { expected_version: version }) }),
      });
    },
    submit(id: string, version: number | null) {
      return request<any>(`/students/me/homework/assignments/${encodeURIComponent(id)}/submission/submit`, {
        method: 'POST', body: JSON.stringify(version == null ? {} : { expected_version: version }),
      });
    },
    result(id: string) { return request<any>(`/students/me/homework/assignments/${encodeURIComponent(id)}/evaluation`); },
    parentChildren() { return request<any[]>('/parents/me/students'); },
    parentAssignments(student: string) {
      return request<any[]>(`/parents/me/students/${encodeURIComponent(student)}/homework/assignments`);
    },
    parentResult(student: string, id: string) {
      return request<any>(`/parents/me/students/${encodeURIComponent(student)}/homework/assignments/${encodeURIComponent(id)}/evaluation`);
    },
    /** Teacher-only AI mark suggestions. Never finalizes, releases, or writes awarded_marks. */
    aiSuggestions(assignmentId: string) {
      return request<any>(`/homework/assignments/${encodeURIComponent(assignmentId)}/evaluation/ai-suggestions`);
    },
    generateAiSuggestions(assignmentId: string, body: { positions?: number[]; replace?: boolean; provider?: 'qwen' | 'gemini' } = {}) {
      return request<any>(`/homework/assignments/${encodeURIComponent(assignmentId)}/evaluation/ai-suggestions`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },
    rerunAiSuggestions(assignmentId: string, body: { positions?: number[]; provider?: 'qwen' | 'gemini' } = {}) {
      return request<any>(`/homework/assignments/${encodeURIComponent(assignmentId)}/evaluation/ai-suggestions/rerun`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },
  },

  assistant: {
    chat: (message: string, history: AssistantTurn[], signal: AbortSignal) =>
      request<AssistantReply>('/assistant/chat', {
        method: 'POST', body: JSON.stringify({ message, history }), signal,
      }),
  },

  /** Unified Student Progress — read-only projections over verified evidence. */
  progress: {
    overview(scope: { role: string; studentId?: string }) {
      return request<import('./studentProgress').StudentProgressOverview>(progressOverviewPath(scope));
    },
    history(scope: { role: string; studentId?: string }, subjectId?: string) {
      const query = subjectId ? `?subject_id=${encodeURIComponent(subjectId)}` : '';
      return request<{ student_id: string; audience: string; events: import('./studentProgress').ProgressEvent[]; generated_at: string }>(
        `${progressBase(scope)}/history${query}`,
      );
    },
    competencies(scope: { role: string; studentId?: string }) {
      return request<import('./studentProgress').StudentProgressOverview['competencies'] & {
        student_id: string;
        generated_at: string;
        subject_competencies: import('./studentProgress').SubjectCompetencyProfile[];
      }>(`${progressBase(scope)}/competencies`);
    },
    subject(scope: { role: string; studentId?: string }, subjectId: string) {
      return request<import('./studentProgress').SubjectProgress>(
        `${progressBase(scope)}/subjects/${encodeURIComponent(subjectId)}`,
      );
    },
    subjectCompetencies(scope: { role: string; studentId?: string }, subjectId: string) {
      return request<import('./studentProgress').SubjectCompetencyProfile>(
        `${progressBase(scope)}/subjects/${encodeURIComponent(subjectId)}/competencies`,
      );
    },
    subjectTimeline(scope: { role: string; studentId?: string }, subjectId: string) {
      return request<import('./studentProgress').SubjectTimeline>(
        `${progressBase(scope)}/subjects/${encodeURIComponent(subjectId)}/timeline`,
      );
    },
    periodEvidence(
      studentId: string,
      subjectId: string,
      periodKind: 'month' | 'term',
      periodId: string,
    ) {
      return request<Record<string, unknown>>(
        `/students/${encodeURIComponent(studentId)}/progress/subjects/${encodeURIComponent(subjectId)}/timeline/${periodKind}/${encodeURIComponent(periodId)}`,
      );
    },
    subjectExplanations(scope: { role: string; studentId?: string }, subjectId: string) {
      return request<import('./studentProgress').ProgressExplanations>(
        `${progressBase(scope)}/subjects/${encodeURIComponent(subjectId)}/explanations`,
      );
    },
  },

  // Authentication
  auth: {
    async login(email: string, password: string) {
      const res = await request<{ access_token: string; refresh_token?: string; user: ApiUser }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
        signal: AbortSignal.timeout(8000),
      });
      if (res.access_token) {
        clearTeachingCache();
        localStorage.setItem('lumeneios_token', res.access_token);
        localStorage.setItem('lumeneios_auth_user', JSON.stringify(res.user));
      }
      return res;
    },
    async me() {
      return request<ApiUser>('/auth/me', { signal: AbortSignal.timeout(8000) });
    },
    /** Development only: every account, featured personas first. 404 when the bypass is disabled. */
    devAccounts() {
      return request<{ enabled: boolean; accounts: DevAccount[] }>('/auth/dev/accounts', { signal: AbortSignal.timeout(8000) });
    },
    /** Development only: sign in as an account without its password. */
    async devLogin(userId: string) {
      const res = await request<{ access_token: string; user: ApiUser }>('/auth/dev/login', {
        method: 'POST',
        body: JSON.stringify({ user_id: userId }),
      });
      if (res.access_token) {
        clearTeachingCache();
        localStorage.setItem('lumeneios_token', res.access_token);
        localStorage.setItem('lumeneios_auth_user', JSON.stringify(res.user));
      }
      return res;
    },
    async switchDemoRole(role: Role | string) {
      const response = await request<{ access_token: string; user: ApiUser }>('/auth/demo-root/role', {
        method: 'POST',
        body: JSON.stringify({ role }),
      });
      if (response.access_token) {
        localStorage.setItem('lumeneios_token', response.access_token);
      }
      return response;
    },
    async switchSchool(schoolId: string) {
      const res = await request<{ access_token: string; user: ApiUser }>('/auth/switch-school', {
        method: 'POST',
        body: JSON.stringify({ school_id: schoolId }),
      });
      if (res.access_token) {
        localStorage.setItem('lumeneios_token', res.access_token);
      }
      return res;
    },
    async logout() {
      // Tokens are typically stateless; local logout must succeed even offline.
      localStorage.removeItem('lumeneios_token');
      clearTeachingCache();
    },
  },

  onboarding: {
    classes(schoolId: string) {
      return request<Array<{ id: string; name: string }>>(`/schools/${encodeURIComponent(schoolId)}/classes`);
    },
    addStudent(details: AccountDetails & { class_id: string; roll_no: number; gender: string }) {
      return request<ApiUser>('/onboarding/students', { method: 'POST', body: JSON.stringify(details) });
    },
    addTeacher(details: AccountDetails & { designation?: string }) {
      return request<ApiUser>('/onboarding/teachers', { method: 'POST', body: JSON.stringify(details) });
    },
    addSchool(details: {
      name: string; location: string; state: string; infrastructure_tier: string;
      academic_year: string; official_working_days: number; principal: AccountDetails;
    }) {
      return request<{ id: string; name: string }>('/onboarding/schools', {
        method: 'POST', body: JSON.stringify(details),
      });
    },
  },

  knowledgeGraph: {
    list(subjectId: string) {
      return request<Array<{
        id: string;
        name: string;
        description: string;
        subject_id: string;
        subject_name: string;
        topic: string;
      }>>(`/knowledge-components?subject_id=${encodeURIComponent(subjectId)}`);
    },
    create(body: { name: string; description: string; subject_id: string; topic: string }) {
      return request<{
        id: string;
        name: string;
        description: string;
        subject_id: string;
        subject_name: string;
        topic: string;
      }>('/knowledge-components', { method: 'POST', body: JSON.stringify(body) });
    },
    relationships(subjectId: string) {
      return request<Array<{
        id: string;
        source_id: string;
        target_id: string;
        relationship: 'PREREQUISITE_OF' | 'RELATED_TO' | 'PART_OF';
      }>>(`/knowledge-components/relationships?subject_id=${encodeURIComponent(subjectId)}`);
    },
    demoPreview(subjectId: string) {
      return request<DemoWalkthrough>(`/knowledge-components/demo-walkthrough?subject_id=${encodeURIComponent(subjectId)}`);
    },
    demoEvaluate(subjectId: string) {
      return request<DemoWalkthrough>(`/knowledge-components/demo-walkthrough?subject_id=${encodeURIComponent(subjectId)}`, { method: 'POST' });
    },
    classEvidence(classId: string, subjectId: string) {
      const query = new URLSearchParams({ class_id: classId, subject_id: subjectId });
      return request<{
        class_id: string;
        class_name: string;
        subject_id: string;
        subject_name: string;
        concepts: Array<{
          id: string;
          name: string;
          topic: string;
          student_count: number;
          proficient_count: number;
          developing_count: number;
          needs_improvement_count: number;
          average_mastery: number | null;
          weakest_competency: string | null;
          last_assessed_at: string | null;
          students: Array<{
            student_id: string;
            student_name: string;
            learning_status: string;
            overall_mastery: number | null;
            lu: number | null;
            cu: number | null;
            ct: number | null;
            au: number | null;
            last_assessed_at: string | null;
          }>;
        }>;
      }>(`/knowledge-components/class-evidence?${query.toString()}`);
    },
    studentAnalysis(studentId: string, subjectId: string) {
      const query = new URLSearchParams({ student_id: studentId, subject_id: subjectId });
      return request<{
        student_id: string;
        student_name: string;
        subject_id: string;
        subject_name: string;
        assessed_count: number;
        not_assessed_count: number;
        concepts: Array<{
          id: string;
          name: string;
          topic: string;
          learning_status: string;
          overall_mastery: number | null;
          attempt_count: number;
          correct_count: number;
          incorrect_count: number;
          recommendations: string[];
        }>;
      }>(`/knowledge-components/student-analysis?${query.toString()}`);
    },
    mapQuestions(subjectId: string, questions: Array<{
      id: string;
      text: string;
      competency: string;
      correct_answer?: string;
      marking_rubric?: string;
    }>) {
      return request<{
        questions: Array<{
          question_id: string;
          components: Array<{ id: string; name: string; relevance: number }>;
        }>;
      }>('/knowledge-components/map-questions', {
        method: 'POST',
        body: JSON.stringify({ subject_id: subjectId, questions }),
      });
    },
    classBlueprint(body: {
      class_id: string;
      subject_id: string;
      total_marks?: number;
      question_count?: number;
      duration_minutes?: number;
      topic?: string;
      slots?: Array<{ kc_id: string; include: boolean; question_count: number; difficulty: string }>;
    }) {
      return request<{
        class_name: string;
        subject_name: string;
        roster_count: number;
        students_without_evidence: number;
        concepts: Array<{
          id: string;
          name: string;
          band: string;
          student_count: number;
          average_mastery: number | null;
          proficient_count: number;
          developing_count: number;
          needs_improvement_count: number;
          reason: string;
        }>;
        slots: Array<{
          kc_id: string;
          kc_name: string;
          band: string;
          difficulty: string;
          marks: number;
          reason: string;
          question: null | {
            id: string;
            text: string;
            type: string;
            competency: string;
            marks: number;
            bloom_level: string;
            correct_answer?: string | null;
            marking_rubric?: string | null;
            kc_mappings: Array<{ kc_id: string; relevance: number }>;
          };
        }>;
      }>('/knowledge-components/class-blueprint', { method: 'POST', body: JSON.stringify(body) });
    },
    sampleFractions() {
      return request<{
        class_name: string;
        source_reference: string;
        students: Array<{
          student_name: string;
          profile: string;
          recommendations: Array<{ kc_name: string; kind: string; reason: string }>;
        }>;
      }>('/knowledge-components/sample-fractions', { method: 'POST' });
    },
    myRecommendations() {
      return request<Array<{
        kc_id: string;
        kc_name: string;
        kind: string;
        reason: string;
        previous_performance: string;
        attempt_count: number;
        expected_outcome: string;
        difficulty: string;
        question_type: string;
        needs_generation: boolean;
        question: null | { id: string; text: string; type: string; competency: string; marks: number };
      }>>('/students/me/question-recommendations');
    },
    link(body: { source_id: string; target_id: string; relationship: 'PREREQUISITE_OF' | 'RELATED_TO' | 'PART_OF' }) {
      return request<{
        id: string;
        source_id: string;
        target_id: string;
        relationship: 'PREREQUISITE_OF' | 'RELATED_TO' | 'PART_OF';
      }>('/knowledge-components/relationships', { method: 'POST', body: JSON.stringify(body) });
    },
    mine() {
      return request<{
        nodes: Array<{
          id: string;
          name: string;
          description: string;
          subject: string;
          topic: string;
          overall_mastery: number | null;
          lu: number | null;
          cu: number | null;
          ct: number | null;
          au: number | null;
          attempt_count: number;
          correct_count: number;
          incorrect_count: number;
          learning_status: 'proficient' | 'developing' | 'needs_improvement' | 'not_assessed';
          last_assessed_at: string | null;
          latest: { LU: number | null; CU: number | null; CT: number | null; AU: number | null };
          previous: { LU: number | null; CU: number | null; CT: number | null; AU: number | null };
          history: Array<{
            assessed_at: string;
            question_id: string;
            competency: 'LU' | 'CU' | 'CT' | 'AU';
            score: number;
            awarded_marks: number;
            max_marks: number;
            correct: boolean;
          }>;
          prerequisites: Array<{ id: string; name: string; relationship: string; overall_mastery: number | null; learning_status: string }>;
          related: Array<{ id: string; name: string; relationship: string; overall_mastery: number | null; learning_status: string }>;
          recommendations: string[];
        }>;
        edges: Array<{ source_id: string; target_id: string; relationship: string }>;
        insights: string[];
      }>('/students/me/knowledge-graph');
    },
  },

  student: {
    async profile(): Promise<Student> {
      const student = await request<any>('/classes/students/me');
      return {
        id: student.id,
        schoolId: student.school_id,
        classId: student.class_id,
        className: student.class_name,
        name: student.name,
        rollNo: student.roll_no,
        admissionNo: student.admission_no ?? undefined,
        gender: student.gender,
        attendancePct: student.attendance_pct,
        competencies: student.competencies,
        baselineCompetencies: student.baseline_competencies,
        learningModality: student.learning_modality,
        parentId: student.parent_id,
        homeworkCompletionRate: student.homework_completion_rate,
        needsSupport: student.needs_support,
        supportArea: student.support_area,
        subjectNames: student.subject_names || student.subjectNames || [],
        parentNames: student.parent_names || student.parentNames || [],
      };
    },
  },

  // Schools
  schools: {
    async getAll() {
      return request<any[]>('/schools');
    },
    async getById(id: string) {
      return request<any>(`/schools/${id}`);
    },
    async update(id: string, changes: { name?: string; location?: string; state?: string; infrastructure_tier?: string; description?: string }) {
      return request<any>(`/schools/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(changes) });
    },
  },

  teachers: {
    async create(teacher: { name: string; email: string; designation: string; schoolId: string }) {
      return request<any>('/teachers', {
        method: 'POST',
        body: JSON.stringify({
          name: teacher.name,
          email: teacher.email,
          designation: teacher.designation,
          school_id: teacher.schoolId,
        }),
        signal: AbortSignal.timeout(4000),
      });
    },
  },

  classes: {
    async assignTeacher(classId: string, teacherId: string) {
      return request<any>(`/classes/${encodeURIComponent(classId)}/assignments`, {
        method: 'POST',
        body: JSON.stringify({ teacher_id: teacherId }),
      });
    },
    async create(schoolId: string, name: string) {
      return request<any>('/classes', {
        method: 'POST',
        body: JSON.stringify({ school_id: schoolId, name }),
      });
    },
  },

  // Documents & Bulk Source Upload
  documents: {
    async list(subjectId?: string, docType: string = 'source_material') {
      const params = new URLSearchParams();
      if (subjectId) params.append('subject_id', subjectId);
      if (docType) params.append('doc_type', docType);
      const docs = await request<any[]>(`/documents?${params.toString()}`);
      return docs.map(mapSourceDocOut);
    },
    async bulkUpload(files: File[], subjectId?: string, docType: string = 'source_material') {
      const formData = new FormData();
      files.forEach((f) => formData.append('files', f));
      if (subjectId) formData.append('subject_id', subjectId);
      formData.append('doc_type', docType);
      const res = await request<any>('/documents/bulk-upload', {
        method: 'POST',
        body: formData,
      });
      return {
        totalSelected: res.total_selected,
        uploadedCount: res.uploaded_count,
        duplicateCount: res.duplicate_count,
        failedCount: res.failed_count,
        items: (res.items || []).map((it: any) => ({
          fileName: it.file_name,
          fileSize: it.file_size,
          mimeType: it.mime_type,
          status: it.status,
          documentId: it.document_id,
          pageCount: it.page_count,
          errorMessage: it.error_message,
          extractedTextPreview: it.extracted_text_preview,
        })),
      };
    },
    async uploadStudioPdf(file: File, subjectId: string) {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('subject_id', subjectId);
      const document = await request<any>('/documents/studio-pdf-upload', {
        method: 'POST',
        body: formData,
      });
      return mapSourceDocOut(document);
    },
    async delete(documentId: string) {
      return request<any>(`/documents/${documentId}`, {
        method: 'DELETE',
      });
    },
  },

  // Academic Calendar & Disruptions
  calendar: {
    async getSchoolCalendar(schoolId: string) {
      return request<any>(`/schools/${schoolId}/calendar`);
    },
    async recordDisruption(schoolId: string, data: { date: string; reason: string; days_lost: number; notes?: string }) {
      return request<any>(`/schools/${schoolId}/disruptions`, {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
    async deleteDisruption(disruptionId: string) {
      return request<any>(`/disruptions/${disruptionId}`, {
        method: 'DELETE',
      });
    },
  },

  // Time-Aware Pedagogical Engine
  timeAware: {
    async calculatePacing(classId: string, data: { total_official_days: number; current_day: number }) {
      return request<any>(`/classes/${classId}/time-aware/calculate`, {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
    async previewCompression(classId: string, data: { total_official_days: number; current_day: number }) {
      return request<any>(`/classes/${classId}/time-aware/compression-preview`, {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
    async approveProposal(proposalId: string, action: 'approve' | 'reject' = 'approve') {
      return request<any>(`/curriculum-proposals/${proposalId}/approve`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      });
    },
  },

  // Assessments & AI Question Generation
  assessments: {
    targets() {
      return request<AssignmentTarget[]>('/assessments/targets');
    },
    uploadAssignments() {
      return request<UploadAssignment[]>('/assessments/upload-assignments');
    },
    /** Teacher: the class roster for an assignment with each student's uploaded handwritten work. */
    uploads(assessmentId: string) {
      return request<AssignmentUploads>(`/assessments/${encodeURIComponent(assessmentId)}/uploads`);
    },
    /** Teacher: publish confirmed marks; updates the student's parameters and notifies student and parents. */
    publishGrade(assessmentId: string, body: {
      student_id: string; history_id?: string; overall_feedback?: string; evaluated_by?: string;
      items: { question_index: number; awarded_marks: number; feedback?: string }[];
    }) {
      return request<PublishedGrade>(`/assessments/${encodeURIComponent(assessmentId)}/grade`, {
        method: 'POST', body: JSON.stringify(body),
      });
    },
    async getAll() {
      return request<any[]>('/assessments');
    },
    async getClassAssessments(classId: string) {
      return request<any[]>(`/classes/${classId}/assessments`);
    },
    async create(classId: string, data: any) {
      return request<any>(`/classes/${classId}/assessments`, {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
    async getSubmissions(assessmentId: string) {
      return request<any[]>(`/assessments/${assessmentId}/submissions`);
    },
    async submitGrade(assessmentId: string, data: any) {
      return request<any>(`/assessments/${assessmentId}/submissions`, {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
    async getQuestionBank(subjectId?: string, bloomLevel?: string) {
      const params = new URLSearchParams();
      if (subjectId) params.append('subject_id', subjectId);
      if (bloomLevel) params.append('bloom_level', bloomLevel);
      const list = await request<any[]>(`/assessments/question-bank?${params.toString()}`);
      return list.map(mapQuestionOut);
    },
    async createTemplateQuestion(data: {
      subjectId: string;
      bloomLevel?: string;
      competency?: string;
    }) {
      const params = new URLSearchParams({ subject_id: data.subjectId });
      if (data.bloomLevel) params.append('bloom_level', data.bloomLevel);
      if (data.competency) params.append('competency', data.competency);
      const res = await request<any>(`/assessments/question-bank/template?${params.toString()}`, {
        method: 'POST',
      });
      return {
        subjectId: res.subject_id,
        generatedCount: res.generated_count,
        questions: (res.questions || []).map(mapQuestionOut),
      };
    },
    async generateQuestions(data: {
      subjectId: string;
      sourceDocumentIds: string[];
      mcqCount: number;
      theoryCount: number;
      bloomLevel: string;
      topicHint?: string;
      assessmentId?: string;
      saveToBank?: boolean;
    }, onProgress?: (step: ProcessStep) => void) {
      const body = JSON.stringify({
        subject_id: data.subjectId,
        source_document_ids: data.sourceDocumentIds,
        mcq_count: data.mcqCount,
        theory_count: data.theoryCount,
        bloom_level: data.bloomLevel,
        focus_topic: data.topicHint || undefined,
        assessment_id: data.assessmentId || undefined,
        save_to_bank: data.saveToBank ?? true,
      });
      const res = onProgress
        ? await postEventStream<any>('/assessments/generate-questions/stream', { method: 'POST', body }, onProgress)
        : await request<any>('/assessments/generate-questions', { method: 'POST', body });
      return {
        subjectId: res.subject_id,
        bloomLevel: res.bloom_level,
        sourceDocumentsUsed: res.source_documents_used || res.source_documents || [],
        generatedCount: res.generated_count,
        questions: (res.questions || []).map(mapQuestionOut),
      };
    },
    async generateQuestionsBeta(data: {
      subjectId: string;
      subjectName: string;
      sourceDocumentIds: string[];
      sourceUrls?: string[];
      mcqCount: number;
      theoryCount: number;
      competencyDistribution?: Record<CompetencyKey, number>;
      bloomLevel: string;
      topicHint?: string;
      bankTopic?: string;
      saveToBank?: boolean;
    }, onProgress?: (step: ProcessStep) => void) {
      const body = JSON.stringify({
        subject_id: data.subjectId,
        subject_name: data.subjectName,
        source_document_ids: data.sourceDocumentIds,
        source_urls: data.sourceUrls || [],
        mcq_count: data.mcqCount,
        theory_count: data.theoryCount,
        competency_distribution: data.competencyDistribution,
        bloom_level: data.bloomLevel,
        focus_topic: data.topicHint || undefined,
        bank_topic: data.bankTopic || undefined,
        save_to_bank: data.saveToBank ?? true,
      });
      const res = onProgress
        ? await postEventStream<any>('/assessments/generate-questions-beta/stream', { method: 'POST', body }, onProgress)
        : await request<any>('/assessments/generate-questions-beta', { method: 'POST', body });
      return {
        subjectId: res.subject_id,
        bloomLevel: res.bloom_level,
        sourceDocumentsUsed: res.source_documents_used || [],
        model: res.model,
        generatedCount: res.generated_count,
        questions: (res.questions || []).map(mapQuestionOut),
      };
    },
    async regenerateQuestion(
      questionId: string,
      context: {
        subjectId: string;
        type: string;
        competency: string;
        text: string;
        sourceDocumentIds?: string[];
        sourceDocumentNames?: string[];
      },
      bloomLevel?: string,
      customInstruction?: string,
    ) {
      const res = await request<any>(`/assessments/questions/${questionId}/regenerate`, {
        method: 'POST',
        body: JSON.stringify({
          subject_id: context.subjectId,
          question_type: context.type,
          competency: context.competency,
          current_text: context.text,
          source_document_ids: context.sourceDocumentIds || [],
          source_document_names: context.sourceDocumentNames || [],
          bloom_level: bloomLevel || undefined,
          custom_instruction: customInstruction || undefined,
        }),
      });
      return mapQuestionOut(res);
    },
    async updateQuestion(questionId: string, data: Partial<{
      text: string;
      type: string;
      options: string[];
      correctAnswer: string;
      markingRubric: string;
      marks: number;
      competency: string;
      bloomLevel: string;
      topic: string;
    }>) {
      const res = await request<any>(`/assessments/questions/${questionId}`, {
        method: 'PUT',
        body: JSON.stringify({
          text: data.text,
          type: data.type,
          options: data.options,
          correct_answer: data.correctAnswer,
          marking_rubric: data.markingRubric,
          marks: data.marks,
          competency: data.competency,
          bloom_level: data.bloomLevel,
          topic: data.topic,
        }),
      });
      return mapQuestionOut(res);
    },
    /** Topics used in the school's bank for one subject, with counts per competency. */
    bankTopics(subjectId: string) {
      return request<{ subject_id: string; untagged: number; topics: { topic: string; count: number; by_competency: Record<string, number> }[] }>(
        `/assessments/question-bank/topics?subject_id=${encodeURIComponent(subjectId)}`);
    },
    /** A teacher-written bank question (no AI). MCQs need a key equal to exactly one option. */
    async createQuestion(data: {
      subjectId: string;
      text: string;
      type: string;
      options: string[];
      correctAnswer: string;
      markingRubric: string;
      marks: number;
      competency: string;
      bloomLevel: string;
      topic?: string;
    }) {
      const res = await request<any>('/assessments/question-bank', {
        method: 'POST',
        body: JSON.stringify({
          subject_id: data.subjectId,
          text: data.text,
          type: data.type,
          options: data.type === 'mcq' ? data.options : [],
          correct_answer: data.correctAnswer,
          marking_rubric: data.markingRubric,
          marks: data.marks,
          competency: data.competency,
          bloom_level: data.bloomLevel,
          topic: data.topic || undefined,
        }),
      });
      return mapQuestionOut(res);
    },
    /** AI preview (local Qwen or Gemini, `provider`): returns questions for review; nothing is saved. */
    async aiGenerateQuestions(params: Record<string, unknown>) {
      return request<any>('/assessments/ai/generate-questions', { method: 'POST', body: JSON.stringify(params) });
    },
    /** Saves educator-approved (possibly edited) AI questions to the bank. */
    async aiSaveQuestions(subjectId: string, questions: unknown[], model?: string, topic?: string) {
      return request<any>('/assessments/ai/questions', {
        method: 'POST',
        body: JSON.stringify({ subject_id: subjectId, questions, model, topic: topic || undefined }),
      });
    },
    async deleteQuestion(questionId: string) {
      return request<any>(`/assessments/questions/${questionId}`, {
        method: 'DELETE',
      });
    },
  },

  // OCR, Optical Verification & Auto-Grade Batch Engine
  ocr: {
    async evaluateScan(assessmentId: string, extractedText: string, provider: 'gemini' | 'qwen' = 'qwen', historyId?: string) {
      return request<{
        scoring_summary: {
          total_marks_obtained: number;
          max_possible_marks: number;
          percentage: number;
          overall_feedback: string;
          needs_teacher_review: boolean;
          review_reasons: string[];
        };
        question_evaluations: Array<{
          question_id: string;
          question_index: number;
          question_text: string;
          status: string;
          awarded_marks: number;
          max_marks: number;
          feedback: string;
          flag_for_review: boolean;
          flag_reason: string | null;
          step_breakdown: Array<{ criterion: string; marks_awarded: number; max: number }>;
        }>;
      }>('/ocr/evaluate-scan', {
        method: 'POST',
        body: JSON.stringify({ assessment_id: assessmentId, extracted_text: extractedText, provider, ...(historyId ? { history_id: historyId } : {}) }),
      });
    },
    async history() {
      return request<Array<{ id: string; file_name: string; extracted_text: string; pages_processed: number; created_at: string; assignment_title?: string | null }>>('/ocr/history');
    },
    async extractPreview(
      files: File[],
      waitBeforeEachImage: boolean,
      onProgress?: (step: ProcessStep) => void,
      assessmentId?: string,
      provider: 'gemini' | 'qwen' = 'qwen',
    ) {
      const formData = new FormData();
      formData.append('wait_before_each_image', String(waitBeforeEachImage));
      formData.append('provider', provider);
      if (assessmentId) formData.append('assessment_id', assessmentId);
      files.forEach((file) => formData.append('files', file));

      const response = onProgress
        ? await postEventStream<{
            provider: string;
            model_version: string;
            results: { file_name: string; extracted_text: string; pages_processed: number }[];
          }>('/ocr/extract-preview/stream', { method: 'POST', body: formData }, onProgress)
        : await request<{
            provider: string;
            model_version: string;
            results: { file_name: string; extracted_text: string; pages_processed: number }[];
          }>('/ocr/extract-preview', { method: 'POST', body: formData });

      return {
        provider: response.provider,
        modelVersion: response.model_version,
        results: response.results.map((result) => ({
          fileName: result.file_name,
          extractedText: result.extracted_text,
          pagesProcessed: result.pages_processed,
        })),
      };
    },
    async processDocument(documentId: string, provider: string = 'simulated') {
      return request<any>('/ocr/process', {
        method: 'POST',
        body: JSON.stringify({ document_id: documentId, provider }),
      });
    },
    async verifyHumanReview(data: {
      document_id: string;
      student_id: string;
      assessment_id: string;
      verified_items: any[];
      teacher_notes?: string;
    }) {
      return request<any>('/ocr/review/verify', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },
    async createBatch(params: {
      classId: string;
      subjectId: string;
      assessmentId: string;
      uploadMode: 'single' | 'bulk';
      splitMultiPdf?: boolean;
      concurrencyLimit?: number;
      files: File[];
    }) {
      const formData = new FormData();
      formData.append('class_id', params.classId);
      formData.append('subject_id', params.subjectId);
      formData.append('assessment_id', params.assessmentId);
      formData.append('upload_mode', params.uploadMode);
      formData.append('split_multi_pdf', String(Boolean(params.splitMultiPdf)));
      formData.append('concurrency_limit', String(params.concurrencyLimit || 4));
      params.files.forEach((f) => formData.append('files', f));

      const res = await request<any>('/ocr/batches', {
        method: 'POST',
        body: formData,
      });
      return mapBatchOut(res);
    },
    async listBatches(assessmentId?: string, classId?: string) {
      const params = new URLSearchParams();
      if (assessmentId) params.append('assessment_id', assessmentId);
      if (classId) params.append('class_id', classId);
      const list = await request<any[]>(`/ocr/batches?${params.toString()}`);
      return list.map(mapBatchOut);
    },
    async getBatch(batchId: string) {
      const res = await request<any>(`/ocr/batches/${batchId}`);
      return mapBatchOut(res);
    },
    async startBatch(batchId: string, waitForCompletion: boolean = false) {
      const res = await request<any>(`/ocr/batches/${batchId}/start?wait_for_completion=${waitForCompletion}`, {
        method: 'POST',
      });
      return mapBatchOut(res);
    },
    async cancelBatch(batchId: string) {
      const res = await request<any>(`/ocr/batches/${batchId}/cancel`, {
        method: 'POST',
      });
      return mapBatchOut(res);
    },
    async removeBatchItem(batchId: string, itemId: string) {
      const res = await request<any>(`/ocr/batches/${batchId}/items/${itemId}`, {
        method: 'DELETE',
      });
      return mapBatchOut(res);
    },
    async retryBatchItem(batchId: string, itemId: string, waitForCompletion: boolean = false) {
      const res = await request<any>(`/ocr/batches/${batchId}/items/${itemId}/retry?wait_for_completion=${waitForCompletion}`, {
        method: 'POST',
      });
      return mapBatchOut(res);
    },
    async updateBatchItem(
      batchId: string,
      itemId: string,
      data: {
        studentId?: string;
        marksObtained?: number;
        questionEvaluations?: any[];
        clearReviewFlag?: boolean;
      }
    ) {
      const res = await request<any>(`/ocr/batches/${batchId}/items/${itemId}`, {
        method: 'PUT',
        body: JSON.stringify({
          student_id: data.studentId,
          marks_obtained: data.marksObtained,
          question_evaluations: data.questionEvaluations,
          clear_review_flag: data.clearReviewFlag ?? true,
        }),
      });
      return mapBatchItemOut(res);
    },
    async approveBatchItem(batchId: string, itemId: string) {
      const res = await request<any>(`/ocr/batches/${batchId}/items/${itemId}/approve`, {
        method: 'POST',
      });
      return mapBatchOut(res);
    },
    async approveAllBatchItems(batchId: string) {
      const res = await request<any>(`/ocr/batches/${batchId}/approve-all`, {
        method: 'POST',
      });
      return mapBatchOut(res);
    },
  },

  // Notifications & Audit
  notifications: {
    async getAll() {
      return request<any[]>('/notifications');
    },
    markRead(id: string) {
      return request<any>(`/notifications/${id}/read`, { method: 'POST' });
    },
  },
  users: {
    list(params: { role?: string; school_id?: string; search?: string } = {}) {
      const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString();
      return request<any[]>(`/users${q ? `?${q}` : ''}`);
    },
  },
  announcements: {
    list() {
      return request<any[]>('/announcements');
    },
    create(body: { title: string; content: string; target_role?: string }) {
      return request<any>('/announcements', { method: 'POST', body: JSON.stringify(body) });
    },
  },
  audit: {
    async getEvents(category?: string, search?: string) {
      const params = new URLSearchParams();
      if (category) params.append('category', category);
      if (search) params.append('search', search);
      return request<any[]>(`/audit/events?${params.toString()}`);
    },
  },

  // Developer portal
  developer: {
    health: () => request<any>('/developer/health'),
    roster: () => request<any>('/developer/roster'),
    reseed: (confirm: string) => request<any>('/developer/roster/reseed', {
      method: 'POST',
      body: JSON.stringify({ confirm }),
    }),
    flags: () => request<any>('/developer/flags'),
    setFlag: (schoolId: string, flagKey: string, enabled: boolean) => request<any>('/developer/flags', {
      method: 'PUT',
      body: JSON.stringify({ school_id: schoolId, flag_key: flagKey, enabled }),
    }),
    activeFlags: () => request<Record<string, boolean>>('/developer/flags/active'),
    access: () => request<any[]>('/developer/access'),
    framework: () => request<any[]>('/developer/framework'),
    saveOutcome: (id: string, body: { code: string; domain: string; grade: number; statement: string }) =>
      request<any>(`/developer/framework/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
    createOutcome: (body: { code: string; domain: string; grade: number; statement: string }) =>
      request<any>('/developer/framework', { method: 'POST', body: JSON.stringify(body) }),
    quality: () => request<any>('/developer/quality'),
    workshop: (body: { kind: 'ocr' | 'question'; text: string; competency_code?: string }) =>
      request<any>('/developer/workshop', { method: 'POST', body: JSON.stringify(body) }),
    releases: () => request<any[]>('/developer/releases'),
    geminiModels: () => request<{ current: string; models: { id: string; label: string }[] }>('/developer/gemini/models'),
    setGeminiModel: (model: string) => request<{ current: string }>('/developer/gemini/model', {
      method: 'PUT',
      body: JSON.stringify({ model }),
    }),
  },

  // Health
  health: {
    async check() {
      try {
        const res = await fetch(`${API_BASE_URL.replace(/\/api\/v1\/?$/, '')}/health`);
        return res.ok;
      } catch {
        return false;
      }
    },
  },
};
