import React, { useEffect, useState } from 'react';
import { marksLabel } from '../../lib/utils';
import { Link, useSearchParams } from 'react-router-dom';
import { ScanGrading } from './ScanGrading';
import { useData } from '../../context/DataContext';
import { AlertCircle, FileText, Loader2, Printer, ScanLine, Trash2, UploadCloud } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { ProcessProgress } from '../../components/common/ProcessProgress';
import { MathText } from '../../components/common/MathText';
import { ApiError, apiClient, ProcessStep, UploadAssignment } from '../../lib/apiClient';
import { DEMO_MODE, escapeHtml } from '../../lib/runtime';
import { UnauthorizedPage } from '../shared/UnauthorizedPage';
import { SampleWalkthrough } from './SampleWalkthrough';

const OFFLINE_DEMO_BANNER = 'OFFLINE DEMO - synthetic data, not official student results.';

function printOcrExtract(
  items: Array<{ fileName: string; extractedText: string; pagesProcessed: number }>,
  provider: string,
  modelVersion: string,
) {
  const printWin = window.open('', '_blank', 'width=900,height=700');
  if (!printWin) return;
  const demoBanner = DEMO_MODE
    ? `<p style="background:#FEF3C7;border:1px solid #F59E0B;padding:8px 12px;font-size:12px;">${escapeHtml(OFFLINE_DEMO_BANNER)}</p>`
    : '';
  const cards = items
    .map((item) => `
      <section style="margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid #E1E7ED;">
        <h2 style="font-size:14px;margin:0 0 6px 0;">${escapeHtml(item.fileName)}</h2>
        <p style="font-size:11px;color:#667085;margin:0 0 8px 0;">${escapeHtml(item.pagesProcessed)} page(s)</p>
        <pre style="white-space:pre-wrap;font-size:12px;background:#F3F6F8;padding:12px;">${escapeHtml(item.extractedText || '[No text extracted]')}</pre>
      </section>`)
    .join('');
  printWin.document.write(`
    <html>
      <head>
        <title>OCR extract — LumenEIOS</title>
        <style>body{font-family:Inter,Arial,sans-serif;color:#182230;padding:32px;line-height:1.5}</style>
      </head>
      <body>
        ${demoBanner}
        <h1>LumenEIOS OCR extract</h1>
        <p style="font-size:12px;color:#667085;">${escapeHtml(provider)} · ${escapeHtml(modelVersion)}</p>
        ${cards}
      </body>
    </html>
  `);
  printWin.document.close();
  printWin.focus();
  setTimeout(() => printWin.print(), 250);
}

const MAX_FILE_SIZE = 15 * 1024 * 1024;
const MAX_FILES = 50;

/** Upload: students upload handwritten answers to an assigned worksheet; teachers OCR and grade them. */
export function ScanReview() {
  const { currentUser } = useAuth();
  if (!currentUser || !['student', 'teacher'].includes(currentUser.role)) return <UnauthorizedPage />;
  const key = `${currentUser.id}:${currentUser.schoolId}`;
  return <UploadBeta key={key} />;
}

function UploadBeta() {
  const { currentUser } = useAuth();
  const { workspace, refreshWorkspace } = useData();
  const isStudent = currentUser?.role === 'student';
  const [params, setParams] = useSearchParams();
  const [assignments, setAssignments] = useState<UploadAssignment[]>();
  const selectedId = params.get('assignment');
  const setSelectedId = (id: string | null) => setParams(p => { const n = new URLSearchParams(p); if (id) n.set('assignment', id); else n.delete('assignment'); return n; });
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    apiClient.assessments.uploadAssignments()
      .then((papers) => { if (active) setAssignments(papers); })
      .catch((err) => { if (active) setError(err instanceof Error ? err.message : 'Could not load assignments.'); });
    return () => { active = false; };
  }, []);

  const selected = assignments?.find((assignment) => assignment.id === selectedId);
  if (selected) {
    return (
      <div className="space-y-5">
      {!isStudent && <ScanGrading assessmentId={selected.id} onChanged={() => { void refreshWorkspace(); }} />}
      <UploadPage
        key={selected.id}
        assignment={selected}
        onBack={() => setSelectedId(null)}
        onProcessed={isStudent ? () => {
          setAssignments((papers) => papers?.map((paper) =>
            paper.id === selected.id ? { ...paper, uploaded: true } : paper
          ));
        } : undefined}
      />
      </div>
    );
  }

  return (
    <section className="space-y-4">
      <header className="rounded-2xl border border-surface-border bg-white p-5 shadow-subtle">
        <h1 className="text-xl font-bold text-navy-900">Upload</h1>
        <p className="mt-2 text-sm text-content-secondary">
          {isStudent ? 'Open an assignment for your class and subject.' : 'Open an assignment in your school to preview OCR.'}
        </p>
      </header>
      {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
      {!assignments && !error && <p role="status">Loading assignments…</p>}
      {assignments?.length === 0 && <p className="text-sm text-content-secondary">No open assignments.</p>}
      <div className="grid gap-4 sm:grid-cols-2">
        {assignments?.map((assignment) => (
          <button
            key={assignment.id}
            type="button"
            onClick={() => setSelectedId(assignment.id)}
            className="rounded-xl border border-surface-border bg-white p-4 text-left shadow-subtle hover:border-teal-500 focus-visible:outline-teal-500"
          >
            <span className="block font-semibold text-teal-700">{assignment.subject_name}</span>
            <span className="mt-1 block font-bold text-navy-900">{assignment.title}</span>
            <span className="mt-1 block text-xs text-content-secondary">
              {assignment.class_name} · {assignment.date} · {assignment.total_marks} marks
              {isStudent && (assignment.uploaded ? ' · Uploaded' : ' · Awaiting upload')}
            </span>
            {!isStudent && (workspace?.pendingUploads?.[assignment.id] ?? 0) > 0 && (
              <span className="mt-2 inline-block rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
                {workspace?.pendingUploads?.[assignment.id]} upload(s) to evaluate
              </span>
            )}
          </button>
        ))}
      </div>
    </section>
  );
}

function UploadPage({ assignment, onBack, onProcessed }: {
  assignment?: UploadAssignment;
  onBack?: () => void;
  onProcessed?: () => void;
}) {
  const { currentUser } = useAuth();
  const isStudent = currentUser?.role === 'student';
  const [files, setFiles] = useState<File[]>([]);
  const [results, setResults] = useState<Awaited<ReturnType<typeof apiClient.ocr.extractPreview>> | null>(
    null
  );
  const [waitBeforeEachImage, setWaitBeforeEachImage] = useState(false);
  const [modelProvider, setModelProvider] = useState<'gemini' | 'qwen'>('qwen');
  const [isDragging, setIsDragging] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [ocrSteps, setOcrSteps] = useState<ProcessStep[]>([]);
  const [error, setError] = useState('');
  const [gradingAssignments, setGradingAssignments] = useState<UploadAssignment[]>();
  const [gradingAssignmentId, setGradingAssignmentId] = useState('');
  const [assignmentError, setAssignmentError] = useState('');
  const showAssignmentPicker = !isStudent && !assignment && !!results;
  const evaluationAssignmentId = assignment?.id || gradingAssignmentId;

  useEffect(() => {
    if (!showAssignmentPicker) return;
    let active = true;
    setAssignmentError('');
    apiClient.assessments.uploadAssignments()
      .then((papers) => { if (active) setGradingAssignments(papers); })
      .catch((err) => { if (active) setAssignmentError(err instanceof Error ? err.message : 'Could not load assignments.'); });
    return () => { active = false; };
  }, [showAssignmentPicker]);

  const recordOcrStep = (step: ProcessStep) => {
    setOcrSteps((current) => {
      const index = current.findIndex((item) => item.step === step.step);
      if (index < 0) return [...current, step];
      const next = current.slice();
      next[index] = step;
      return next;
    });
  };

  const addFiles = (selected: FileList | File[]) => {
    const additions: File[] = [];
    const errors: string[] = [];
    const existing = new Set(files.map((file) => `${file.name}-${file.size}-${file.lastModified}`));

    for (const file of Array.from(selected)) {
      if (!/\.(pdf|jpe?g|png)$/i.test(file.name)) {
        errors.push(`${file.name}: use PDF, JPG, JPEG, or PNG.`);
      } else if (file.size === 0) {
        errors.push(`${file.name}: the file is empty.`);
      } else if (file.size > MAX_FILE_SIZE) {
        errors.push(`${file.name}: file must be no larger than 15 MB.`);
      } else if (existing.has(`${file.name}-${file.size}-${file.lastModified}`)) {
        errors.push(`${file.name}: already selected.`);
      } else if (files.length + additions.length >= MAX_FILES) {
        errors.push(`You can select up to ${MAX_FILES} files.`);
        break;
      } else {
        additions.push(file);
        existing.add(`${file.name}-${file.size}-${file.lastModified}`);
      }
    }

    if (additions.length) {
      setFiles((current) => [...current, ...additions]);
      setResults(null);
    }
    setError(errors.join(' '));
  };

  const processFiles = async (providerOverride?: 'gemini' | 'qwen') => {
    const providerToUse = providerOverride ?? modelProvider;
    if (providerOverride) setModelProvider(providerOverride);
    if (!files.length) {
      setError('Select at least one image or PDF first.');
      return;
    }

    setIsProcessing(true);
    setError('');
    setResults(null);
    setOcrSteps([]);
    try {
      setResults(await apiClient.ocr.extractPreview(
        files, waitBeforeEachImage, recordOcrStep, assignment?.id, providerToUse,
      ));
      onProcessed?.();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : 'OCR request failed. Check that the backend is running.'
      );
    } finally {
      setIsProcessing(false);
    }
  };

  const clearFiles = () => {
    setFiles([]);
    setResults(null);
    setOcrSteps([]);
    setError('');
  };

  return (
    <div className="space-y-6">
      <header className="rounded-2xl border border-surface-border bg-white p-5 shadow-subtle">
        <div className="flex items-center gap-2">
          <ScanLine className="h-5 w-5 text-teal-600" />
          <h1 className="text-xl font-bold tracking-tight text-navy-900">Upload</h1>
          <span className="rounded-full bg-teal-50 px-2.5 py-1 text-[11px] font-semibold text-teal-700">
            {modelProvider === 'qwen' ? 'Qwen' : 'Gemini'}
          </span>
        </div>
        <p className="mt-2 text-sm text-content-secondary">
          Upload a photo or PDF to extract text with {modelProvider === 'qwen' ? 'Qwen' : 'Gemini'}.
          {!isStudent && ' Review the extracted answers and evaluate them against an assignment.'}
        </p>
        {isStudent && (
          <p className="mt-2 text-sm text-content-secondary">
            Successful extracts are saved to your <Link to="/student/history" className="text-teal-700 underline">History</Link>.
          </p>
        )}
      </header>
      {!isStudent && !assignment && <SampleWalkthrough />}

      {assignment && (
        <article className="rounded-xl border border-surface-border bg-white p-4 shadow-subtle">
          <button type="button" onClick={onBack} disabled={isProcessing} className="mb-3 text-sm font-semibold text-teal-700 underline disabled:opacity-50">
            Back to assignments
          </button>
          <h2 className="font-semibold text-navy-900">{assignment.title}</h2>
          <p className="text-xs text-content-secondary">
            {assignment.class_name} · {assignment.subject_name} · {assignment.date} · {assignment.total_marks} marks
          </p>
          <ol className="mt-3 space-y-3">
            {assignment.questions.map((question, index) => (
              <li key={index} className="text-sm text-navy-900">
                <p><strong>Q{index + 1}.</strong> <MathText text={question.text} /> ({marksLabel(question.marks)})</p>
                {!!question.options?.length && (
                  <ul className="mt-1 space-y-1 pl-4 text-content-secondary">
                    {question.options.map((option, optionIndex) => <li key={optionIndex}><MathText text={option} /></li>)}
                  </ul>
                )}
              </li>
            ))}
          </ol>
        </article>
      )}

      <section className="rounded-2xl border border-surface-border bg-white p-5 shadow-subtle">
        <label
          htmlFor="ocr-file-input"
          onDragOver={(event) => {
            event.preventDefault();
            if (!isProcessing) setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setIsDragging(false);
            if (!isProcessing) addFiles(event.dataTransfer.files);
          }}
          className={`block w-full rounded-xl border-2 border-dashed p-8 text-center transition-colors focus-within:ring-2 focus-within:ring-teal-500 ${
            isDragging
              ? 'border-teal-500 bg-teal-50'
              : 'border-surface-border bg-surface-bg/40'
          } ${isProcessing ? 'cursor-not-allowed opacity-60' : 'cursor-pointer hover:border-teal-500/60'}`}
        >
          <input
            id="ocr-file-input"
            type="file"
            accept=".pdf,.jpg,.jpeg,.png"
            multiple
            disabled={isProcessing}
            className="sr-only"
            onChange={(event) => {
              if (event.target.files?.length) addFiles(event.target.files);
              event.target.value = '';
            }}
          />
          <UploadCloud className="mx-auto mb-2 h-9 w-9 text-teal-600" />
          <p className="font-semibold text-navy-900">
            Drop one or more answer sheets here, or click to browse
          </p>
          <p className="mt-1 text-xs text-content-secondary">
            PDF, JPG, JPEG, or PNG · up to 15 MB each · maximum {MAX_FILES} files
          </p>
        </label>

        <label className="mt-4 block text-sm font-semibold text-navy-900" htmlFor="ocr-model">
          Model
          <select
            id="ocr-model"
            value={modelProvider}
            disabled={isProcessing}
            onChange={(event) => setModelProvider(event.target.value as 'gemini' | 'qwen')}
            className="mt-1 block w-full max-w-xs rounded-lg border border-surface-border bg-white px-3 py-2 text-sm font-normal"
          >
            <option value="qwen">Qwen (default)</option>
            <option value="gemini">Gemini (fallback)</option>
          </select>
        </label>

        <label className="mt-4 flex w-fit cursor-pointer items-center gap-2 text-sm text-navy-900">
          <input
            type="checkbox"
            checked={waitBeforeEachImage}
            disabled={isProcessing}
            onChange={(event) => setWaitBeforeEachImage(event.target.checked)}
            className="rounded border-surface-border text-teal-600 focus:ring-teal-500"
          />
          Wait 5 seconds before processing each image/page
        </label>

        {files.length > 0 && (
          <div className="mt-5 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-navy-900">Selected files ({files.length})</h2>
              <button
                type="button"
                onClick={clearFiles}
                disabled={isProcessing}
                className="text-xs font-semibold text-content-secondary hover:text-rose-600 disabled:opacity-50"
              >
                Clear all
              </button>
            </div>
            <ul className="max-h-56 space-y-2 overflow-y-auto">
              {files.map((file) => (
                <li
                  key={`${file.name}-${file.size}-${file.lastModified}`}
                  className="flex items-center justify-between gap-3 rounded-lg border border-surface-border px-3 py-2"
                >
                  <span className="flex min-w-0 items-center gap-2 text-sm text-navy-900">
                    <FileText className="h-4 w-4 shrink-0 text-teal-600" />
                    <span className="truncate">{file.name}</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setFiles((current) => current.filter((item) => item !== file));
                      setResults(null);
                    }}
                    disabled={isProcessing}
                    className="rounded p-1 text-content-muted hover:text-rose-600 disabled:opacity-50"
                    aria-label={`Remove ${file.name}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="mt-4 flex items-start gap-2 rounded-lg bg-rose-50 p-3 text-sm text-rose-800"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="space-y-2">
              <span>{error}</span>
              {modelProvider === 'qwen' && files.length > 0 && !isProcessing && (
                <div>
                  <button
                    type="button"
                    onClick={() => processFiles('gemini')}
                    className="rounded-md border border-rose-300 bg-white px-2.5 py-1 text-xs font-semibold text-rose-800 hover:bg-rose-100"
                  >
                    Retry with Gemini (fallback)
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {ocrSteps.length > 0 && (
          <div className="mt-4">
            <ProcessProgress steps={ocrSteps} />
          </div>
        )}

        <button
          type="button"
          onClick={() => processFiles()}
          disabled={isProcessing || files.length === 0}
          className="mt-5 inline-flex items-center gap-2 rounded-lg bg-navy-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-navy-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isProcessing && <Loader2 className="h-4 w-4 animate-spin" />}
          {isProcessing ? 'Extracting text…' : 'Run OCR'}
        </button>
      </section>

      <section className="space-y-3" aria-live="polite">
        <div>
          <h2 className="text-lg font-bold text-navy-900">Extracted text</h2>
          <p className="text-xs text-content-secondary">
            {results
              ? `${results.provider} · ${results.modelVersion} · ${results.results.length} file(s) processed`
              : 'OCR results will appear here for verification.'}
          </p>
        </div>
        {results ? (
          <>
            {showAssignmentPicker && (
              <div className="rounded-xl border border-surface-border bg-white p-4">
                <label className="block text-sm font-semibold text-navy-900">
                  Assignment for evaluation
                  <select
                    value={gradingAssignmentId}
                    onChange={(event) => setGradingAssignmentId(event.target.value)}
                    className="mt-2 block w-full rounded-lg border border-surface-border p-2"
                  >
                    <option value="">Choose an assignment</option>
                    {gradingAssignments?.map((paper) => (
                      <option key={paper.id} value={paper.id}>
                        {paper.title} · {paper.class_name} · {paper.subject_name} · {paper.date}
                      </option>
                    ))}
                  </select>
                </label>
                {assignmentError && <p role="alert" className="mt-2 text-sm text-rose-700">{assignmentError}</p>}
                {!gradingAssignments && !assignmentError && <p role="status" className="mt-2 text-sm">Loading assignments…</p>}
                {gradingAssignments?.length === 0 && <p className="mt-2 text-sm">No open assignments are available.</p>}
              </div>
            )}
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => printOcrExtract(results.results, results.provider, results.modelVersion)}
                className="inline-flex items-center gap-2 rounded-lg border border-surface-border bg-white px-3 py-1.5 text-xs font-semibold text-navy-900 hover:bg-surface-bg"
              >
                <Printer className="h-3.5 w-3.5" />
                Print extract
              </button>
            </div>
            {results.results.map((result, index) => (
            <div
              key={index}
              className="rounded-xl border border-surface-border bg-white p-4 shadow-subtle"
            >
              <div className="mb-2 flex items-center justify-between gap-3">
                <h3 className="truncate text-sm font-semibold text-navy-900">{result.fileName}</h3>
                <span className="shrink-0 text-xs text-content-secondary">
                  {result.pagesProcessed} page(s)
                </span>
              </div>
              {!isStudent && result.extractedText.trim() ? (
                <ScanEvaluation
                  extractedText={result.extractedText}
                  assessmentId={evaluationAssignmentId}
                  provider={modelProvider}
                />
              ) : (
                <div className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-surface-bg p-3 text-sm text-navy-900">
                  <MathText text={result.extractedText || '[No text extracted]'} />
                </div>
              )}
            </div>
            ))}
          </>
        ) : (
          <div className="rounded-xl border border-surface-border bg-white p-4 text-sm text-content-secondary shadow-subtle">
            {isProcessing ? 'Waiting for OCR extraction…' : 'Extracted text will be shown in this panel.'}
          </div>
        )}
      </section>
    </div>
  );
}

function ScanEvaluation({
  extractedText, assessmentId, provider,
}: {
  extractedText: string;
  assessmentId: string;
  provider: 'gemini' | 'qwen';
}) {
  const [text, setText] = useState(extractedText);
  const [pending, setPending] = useState(false);
  const [outcome, setOutcome] = useState<{
    assessmentId: string;
    text: string;
    result?: Awaited<ReturnType<typeof apiClient.ocr.evaluateScan>>;
    error?: string;
  }>();
  const current = outcome?.assessmentId === assessmentId && outcome.text === text ? outcome : undefined;
  const summary = current?.result?.scoring_summary;

  const evaluate = async () => {
    setPending(true);
    setOutcome(undefined);
    try {
      const result = await apiClient.ocr.evaluateScan(assessmentId, text.trim(), provider);
      setOutcome({ assessmentId, text, result });
    } catch (err) {
      setOutcome({
        assessmentId,
        text,
        error: err instanceof Error ? err.message : 'Scan evaluation failed.',
      });
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="mt-4 space-y-3 text-sm text-navy-900">
      <label className="block font-semibold">
        Answers for evaluation
        <textarea
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setOutcome(undefined);
          }}
          disabled={pending}
          rows={5}
          className="mt-1 block w-full rounded-lg border border-surface-border p-2 font-normal"
        />
      </label>
      {/\\[([a-zA-Z]/.test(text) && (
        <div className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg border border-dashed border-teal-200 bg-teal-50/40 p-2 text-sm" aria-label="Formatted preview">
          <span className="mr-1 text-[11px] font-semibold uppercase tracking-wide text-teal-700">Preview</span>
          <MathText text={text} />
        </div>
      )}
      <p className="text-xs text-content-secondary">Correct OCR errors and remove student names and identifiers before sending the answers to {provider === 'qwen' ? 'Qwen' : 'Gemini'} for draft marking.</p>
      <button
        type="button"
        onClick={evaluate}
        disabled={pending || !assessmentId || !text.trim()}
        className="rounded-lg bg-navy-900 px-4 py-2 font-semibold text-white disabled:opacity-50"
      >
        {pending ? 'Evaluating scan…' : 'Evaluate this scan'}
      </button>
      {current?.error && <p role="alert" className="text-rose-700">{current.error}</p>}
      {summary && (
        <div className="space-y-2 rounded-lg border border-surface-border p-3">
          <h4 className="font-semibold">Draft marks · {summary.total_marks_obtained}/{summary.max_possible_marks} ({summary.percentage}%)</h4>
          {summary.overall_feedback && <p><MathText text={summary.overall_feedback} /></p>}
          {summary.needs_teacher_review && <p className="font-semibold text-amber-800">Teacher review required</p>}
          {summary.review_reasons.map((reason, index) => <p key={index} className="text-amber-800">{reason}</p>)}
          {current.result?.question_evaluations.map((question) => (
            <div key={question.question_id} className="border-t border-surface-border pt-2">
              <p className="font-semibold">Q{question.question_index}. <MathText text={question.question_text} /> · {question.awarded_marks}/{question.max_marks}</p>
              {question.status === 'unattempted' && <p>Unattempted</p>}
              {question.feedback && <p><MathText text={question.feedback} /></p>}
              {question.flag_for_review && <p className="text-amber-800">{question.flag_reason || 'Review required'}</p>}
              {!!question.step_breakdown.length && (
                <ul className="ml-5 list-disc">
                  {question.step_breakdown.map((step, index) => (
                    <li key={index}><MathText text={step.criterion} /> ({step.marks_awarded}/{step.max})</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
