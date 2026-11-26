import React, { useState } from 'react';
import { ApiError, apiClient } from '../../lib/apiClient';

type Blueprint = Awaited<ReturnType<typeof apiClient.knowledgeGraph.classBlueprint>>;

export function ClassBlueprintPanel({
  classId,
  subjectId,
  onUseQuestions,
}: {
  classId: string;
  subjectId: string;
  onUseQuestions: (blueprint: Blueprint) => void;
}) {
  const [marks, setMarks] = useState(20);
  const [count, setCount] = useState(4);
  const [minutes, setMinutes] = useState(40);
  const [blueprint, setBlueprint] = useState<Blueprint | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [sampleNote, setSampleNote] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiClient.knowledgeGraph.classBlueprint({
        class_id: classId,
        subject_id: subjectId,
        total_marks: marks,
        question_count: count,
        duration_minutes: minutes,
      });
      setBlueprint(data);
    } catch (err) {
      setBlueprint(null);
      setError(err instanceof ApiError ? err.message : 'Could not build a class paper.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="space-y-2 rounded-xl border border-surface-border bg-white p-3">
      <div>
        <h3 className="text-xs font-semibold text-navy-900">Class test from assessed concepts</h3>
        <p className="mt-1 text-[11px] text-content-secondary">
          The mix uses students who have been assessed. Students with no evidence are counted separately and are not treated as zero.
        </p>
      </div>
      <div className="flex flex-wrap gap-2 text-[11px]">
        <label>Marks
          <input className="ml-1 w-16 rounded border border-surface-border px-1 py-0.5" type="number" min={1} value={marks} onChange={(event) => setMarks(Number(event.target.value))} />
        </label>
        <label>Questions
          <input className="ml-1 w-16 rounded border border-surface-border px-1 py-0.5" type="number" min={1} value={count} onChange={(event) => setCount(Number(event.target.value))} />
        </label>
        <label>Minutes
          <input className="ml-1 w-16 rounded border border-surface-border px-1 py-0.5" type="number" min={5} value={minutes} onChange={(event) => setMinutes(Number(event.target.value))} />
        </label>
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="rounded-lg bg-navy-900 px-2 py-1 text-[11px] font-semibold text-white" disabled={loading} onClick={() => load()}>
          {loading ? 'Building…' : 'Recommend a paper'}
        </button>
        <button
          type="button"
          className="rounded-lg border border-surface-border px-2 py-1 text-[11px] font-semibold text-navy-900"
          disabled={loading}
          onClick={async () => {
            setSampleNote('');
            setError('');
            try {
              const sample = await apiClient.knowledgeGraph.sampleFractions();
              const lines = sample.students.map((student) => `${student.student_name} (${student.profile}): ${student.recommendations.map((item) => item.kind).join(', ')}`);
              setSampleNote(`${sample.class_name}. ${sample.source_reference} ${lines.join(' ')}`);
            } catch (err) {
              setError(err instanceof ApiError ? err.message : 'The Class 6 sample is not available in this school.');
            }
          }}
        >
          Load Class 6 fractions sample
        </button>
      </div>
      {error && <p role="alert" className="text-xs text-rose-700">{error}</p>}
      {sampleNote && <p className="text-[11px] text-content-secondary">{sampleNote}</p>}
      {blueprint && (
        <div className="space-y-2">
          <p className="text-[11px] text-content-secondary">
            {blueprint.roster_count} students on the roll. {blueprint.students_without_evidence} have no assessed concept on this subject.
          </p>
          <ul className="space-y-1">
            {blueprint.concepts.filter((concept) => concept.band !== 'insufficient').map((concept) => (
              <li key={concept.id} className="text-[11px] text-navy-900">
                <span className="font-semibold">{concept.name}</span> · {concept.band}
                {concept.average_mastery != null ? ` · average ${concept.average_mastery}%` : ''}
                {' '}· {concept.proficient_count} proficient, {concept.developing_count} developing, {concept.needs_improvement_count} need support
              </li>
            ))}
          </ul>
          <ul className="space-y-2">
            {blueprint.slots.map((slot) => (
              <li key={`${slot.kc_id}-${slot.difficulty}-${slot.marks}`} className="rounded-lg border border-surface-border p-2">
                <p className="text-[11px] text-navy-900">{slot.reason}</p>
                <p className="mt-1 text-[11px] text-content-secondary">
                  {slot.difficulty} · {slot.marks} marks
                  {slot.question ? ` · ${slot.question.text}` : ' · no bank question for this concept yet'}
                </p>
                <button
                  type="button"
                  className="mt-1 text-[11px] font-semibold text-teal-700"
                  onClick={() => {
                    const next = blueprint.slots.filter((item) => item !== slot);
                    setBlueprint({ ...blueprint, slots: next });
                  }}
                >
                  Remove from paper
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="rounded-lg bg-teal-700 px-2 py-1 text-[11px] font-semibold text-white"
            onClick={() => onUseQuestions(blueprint)}
          >
            Use this paper in the preview
          </button>
        </div>
      )}
    </section>
  );
}
