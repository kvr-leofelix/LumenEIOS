import React, { useEffect, useState } from 'react';
import { ApiError, apiClient } from '../../lib/apiClient';
import { Section } from './ui';

type ClassEvidence = Awaited<ReturnType<typeof apiClient.knowledgeGraph.classEvidence>>;
type StudentAnalysis = Awaited<ReturnType<typeof apiClient.knowledgeGraph.studentAnalysis>>;

const STATUS_LABEL: Record<string, string> = {
  proficient: 'Strong',
  developing: 'Partial',
  needs_improvement: 'Needs support',
  not_assessed: 'Not assessed',
};

const STATUS_CLASS: Record<string, string> = {
  proficient: 'text-emerald-700',
  developing: 'text-amber-700',
  needs_improvement: 'text-rose-700',
  not_assessed: 'text-content-secondary',
};

function scoreText(value: number | null) {
  return value == null ? 'Not assessed' : `${value}%`;
}

export function KcHomeworkAnalysis({
  classId,
  subjectId,
  studentId,
}: {
  classId: string;
  subjectId: string;
  studentId: string;
}) {
  const [classEvidence, setClassEvidence] = useState<ClassEvidence | null>(null);
  const [studentAnalysis, setStudentAnalysis] = useState<StudentAnalysis | null>(null);
  const [classError, setClassError] = useState('');
  const [studentError, setStudentError] = useState('');

  useEffect(() => {
    let active = true;
    setClassError('');
    apiClient.knowledgeGraph.classEvidence(classId, subjectId).then((data) => {
      if (active) setClassEvidence(data);
    }).catch((err) => {
      if (!active) return;
      setClassEvidence(null);
      setClassError(err instanceof ApiError ? err.message : 'Could not load the class concept analysis.');
    });
    return () => { active = false; };
  }, [classId, subjectId]);

  useEffect(() => {
    if (!studentId) {
      setStudentAnalysis(null);
      setStudentError('');
      return;
    }
    let active = true;
    setStudentError('');
    apiClient.knowledgeGraph.studentAnalysis(studentId, subjectId).then((data) => {
      if (active) setStudentAnalysis(data);
    }).catch((err) => {
      if (!active) return;
      setStudentAnalysis(null);
      setStudentError(err instanceof ApiError ? err.message : 'Could not load this student\'s concept analysis.');
    });
    return () => { active = false; };
  }, [studentId, subjectId]);

  const assessedStudent = studentAnalysis?.concepts.filter((concept) => concept.learning_status !== 'not_assessed') ?? [];

  return (
    <Section
      title="Knowledge-component analysis"
      subtitle="From marked answer sheets. A concept with no evidence is left out of averages and is not treated as zero."
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-navy-900">
            Class {classEvidence ? `· ${classEvidence.class_name}` : ''}
          </h3>
          {classError && <p role="alert" className="text-sm text-rose-700">{classError}</p>}
          {!classError && !classEvidence && <p className="text-sm text-content-secondary">Loading class concepts…</p>}
          {classEvidence && classEvidence.concepts.length === 0 && (
            <p className="text-sm text-content-secondary">No concept has been evaluated for this class and subject yet.</p>
          )}
          <ul className="space-y-2">
            {classEvidence?.concepts.map((concept) => (
              <li key={concept.id} className="rounded-lg border border-surface-border px-3 py-2 text-sm">
                <p className="font-semibold text-navy-900">{concept.name}</p>
                <p className="text-xs text-content-secondary">
                  {concept.student_count} assessed
                  {concept.average_mastery != null ? ` · average ${concept.average_mastery}%` : ''}
                  {' '}· {concept.needs_improvement_count} need support, {concept.developing_count} partial, {concept.proficient_count} strong
                </p>
              </li>
            ))}
          </ul>
        </div>
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-navy-900">
            {studentAnalysis ? studentAnalysis.student_name : 'Selected student'}
          </h3>
          {!studentId && <p className="text-sm text-content-secondary">Choose a student to see which concepts their homework should practise.</p>}
          {studentError && <p role="alert" className="text-sm text-rose-700">{studentError}</p>}
          {studentId && !studentError && !studentAnalysis && <p className="text-sm text-content-secondary">Loading this student…</p>}
          {studentAnalysis && assessedStudent.length === 0 && (
            <p className="text-sm text-content-secondary">
              {studentAnalysis.student_name} has no assessed concept in {studentAnalysis.subject_name}. Grey concepts are not scored as zero.
            </p>
          )}
          <ul className="space-y-2">
            {assessedStudent.map((concept) => (
              <li key={concept.id} className="rounded-lg border border-surface-border px-3 py-2 text-sm">
                <p className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-navy-900">{concept.name}</span>
                  <span className={`text-xs font-semibold ${STATUS_CLASS[concept.learning_status] || ''}`}>
                    {STATUS_LABEL[concept.learning_status] || concept.learning_status} · {scoreText(concept.overall_mastery)}
                  </span>
                </p>
                <p className="text-xs text-content-secondary">
                  {concept.attempt_count} question{concept.attempt_count === 1 ? '' : 's'} · {concept.correct_count} correct · {concept.incorrect_count} incorrect
                </p>
                {concept.recommendations.map((note) => (
                  <p key={note} className="mt-1 text-xs text-navy-800">{note}</p>
                ))}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Section>
  );
}
