import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, apiClient, DemoWalkthrough } from '../../lib/apiClient';
import { KnowledgeGraphView, type KnowledgeGraph } from '../student/KnowledgeComponentGraph';

export function SampleWalkthrough() {
  const [subjects, setSubjects] = useState<Array<{ id: string; name: string }>>([]);
  const [subjectId, setSubjectId] = useState('');
  const [demo, setDemo] = useState<DemoWalkthrough | null>(null);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let active = true;
    apiClient.assessments.targets().then((classes) => {
      if (!active) return;
      const byId = new Map<string, string>();
      classes.forEach((section) => section.subjects.forEach((subject) => byId.set(subject.id, subject.name)));
      const rows = [...byId.entries()].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
      setSubjects(rows);
      setSubjectId((current) => current || rows[0]?.id || '');
    }).catch((err) => {
      if (active) setError(err instanceof ApiError ? err.message : 'Could not load subjects.');
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!subjectId) return;
    let active = true;
    setError('');
    apiClient.knowledgeGraph.demoPreview(subjectId).then((data) => {
      if (active) setDemo(data);
    }).catch((err) => {
      if (active) setError(err instanceof ApiError ? err.message : 'Could not prepare the sample paper.');
    });
    return () => { active = false; };
  }, [subjectId]);

  async function evaluate() {
    if (!subjectId) return;
    setPending(true);
    setError('');
    try {
      setDemo(await apiClient.knowledgeGraph.demoEvaluate(subjectId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not evaluate the sample.');
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="space-y-4 rounded-2xl border border-teal-200 bg-teal-50/40 p-5">
      <div>
        <h2 className="text-base font-semibold text-navy-900">Sample walkthrough</h2>
        <p className="mt-1 text-sm text-content-secondary">
          Step 2 of 3. This is a stored answer from {demo ? demo.student_name : 'the student'}. Evaluating it does not call Gemini or Qwen. Step 3 is the Student persona, on My Learning Mission.
        </p>
      </div>
      {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
      {subjects.length > 0 && (
        <label className="block text-sm font-medium text-navy-900">
          Subject
          <select
            className="mt-1 block w-full max-w-xs rounded-lg border border-surface-border bg-white px-3 py-2 text-sm"
            value={subjectId}
            onChange={(event) => setSubjectId(event.target.value)}
          >
            {subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}
          </select>
        </label>
      )}
      {demo && (
        <>
          <p className="text-sm text-navy-900">
            <span className="font-semibold">{demo.title}</span>
            <span className="text-content-secondary"> · {demo.class_name} · saved as {demo.student_name}&apos;s upload</span>
          </p>
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-lg border border-surface-border bg-white p-3 text-xs">{demo.extracted_text}</pre>
          <button
            type="button"
            onClick={evaluate}
            disabled={pending}
            className="rounded-lg bg-navy-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {pending ? 'Evaluating sample…' : 'Evaluate sample answer'}
          </button>
          {demo.evaluated && demo.percentage != null && (
            <p role="status" className="text-sm text-teal-900">
              Sample marks {demo.total_marks_obtained}/{demo.max_possible_marks} ({demo.percentage}%). Switch to the Student persona. The same colours are on My Learning Mission.
            </p>
          )}
          <KnowledgeGraphView graph={demo.graph as KnowledgeGraph} />
          <p className="text-xs text-content-secondary">
            The concept list is on <Link className="font-semibold text-teal-700 underline" to="/teacher/knowledge-components">Knowledge Components</Link>.
          </p>
        </>
      )}
    </section>
  );
}
