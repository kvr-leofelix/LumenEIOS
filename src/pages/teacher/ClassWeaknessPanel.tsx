import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, apiClient } from '../../lib/apiClient';

export type ClassEvidence = Awaited<ReturnType<typeof apiClient.knowledgeGraph.classEvidence>>;
type ConceptEvidence = ClassEvidence['concepts'][number];

const STATUS_LABEL: Record<string, string> = {
  proficient: 'Proficient',
  developing: 'Developing',
  needs_improvement: 'Needs improvement',
};

export function ClassWeaknessPanel({
  classId,
  subjectId,
  selectedId,
  onSelect,
}: {
  classId: string;
  subjectId: string;
  selectedId: string;
  onSelect: (concept: ConceptEvidence) => void;
}) {
  const [evidence, setEvidence] = useState<ClassEvidence | null>(null);
  const [openId, setOpenId] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!classId || !subjectId) return;
    let active = true;
    setError('');
    apiClient.knowledgeGraph.classEvidence(classId, subjectId).then((data) => {
      if (active) setEvidence(data);
    }).catch((err) => {
      if (!active) return;
      setEvidence(null);
      setError(err instanceof ApiError ? err.message : 'Could not load evaluated concepts.');
    });
    return () => { active = false; };
  }, [classId, subjectId]);

  return (
    <section className="space-y-2 rounded-xl border border-teal-200 bg-teal-50/50 p-3">
      <div>
        <h3 className="text-xs font-semibold text-navy-900">Weak concepts from evaluated work</h3>
        <p className="mt-1 text-[11px] text-content-secondary">
          These come from marked answer sheets for this class. Choose one to fill the topic, then use sample questions to decide what to assign. Grey, unassessed concepts are left out.
        </p>
      </div>
      {error && <p role="alert" className="text-xs text-rose-700">{error}</p>}
      {evidence && evidence.concepts.length === 0 && (
        <p className="text-xs text-content-secondary">
          No concept has been evaluated for this class yet. Mark the sample answer on <Link className="font-semibold text-teal-700 underline" to="/upload">Upload</Link>, then return here.
        </p>
      )}
      <ul className="space-y-2">
        {evidence?.concepts.map((concept) => {
          const open = openId === concept.id;
          return (
            <li key={concept.id} className="rounded-lg border border-surface-border bg-white p-2">
              <button
                type="button"
                aria-pressed={selectedId === concept.id}
                onClick={() => {
                  setOpenId(concept.id);
                  onSelect(concept);
                }}
                className="flex w-full items-start justify-between gap-2 text-left"
              >
                <span>
                  <span className="block text-xs font-semibold text-navy-900">{concept.name}</span>
                  <span className="mt-0.5 block text-[11px] text-content-secondary">
                    {concept.needs_improvement_count} need improvement · {concept.developing_count} developing · {concept.proficient_count} proficient
                    {concept.average_mastery != null ? ` · average ${concept.average_mastery}%` : ''}
                    {concept.weakest_competency ? ` · weakest ${concept.weakest_competency}` : ''}
                  </span>
                </span>
                <span className="shrink-0 text-[11px] font-semibold text-teal-700">{selectedId === concept.id ? 'Selected' : 'Use topic'}</span>
              </button>
              {open && (
                <ul className="mt-2 space-y-1 border-t border-surface-border pt-2">
                  {concept.students.map((student) => (
                    <li key={student.student_id} className="flex items-center justify-between text-[11px] text-navy-900">
                      <span>{student.student_name}</span>
                      <span className="text-content-secondary">
                        {STATUS_LABEL[student.learning_status] || student.learning_status}
                        {student.overall_mastery != null ? ` · ${student.overall_mastery}%` : ''}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
