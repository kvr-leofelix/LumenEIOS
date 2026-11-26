import React, { useState } from 'react';
import { apiClient } from '../../lib/apiClient';
import type { BloomLevel, CompetencyKey, Question } from '../../types';
import { Button } from './Button';
import { COMPETENCIES } from '../../lib/questionStudio';

const BLOOMS: BloomLevel[] = ['Remember', 'Understand', 'Apply', 'Analyze', 'Evaluate', 'Create'];
const NAMES = { LU: 'Language Understanding', CU: 'Concept Understanding', AU: 'Application', CT: 'Critical Thinking' };

export function ManualQuestionForm({ subjectId, onSaved, onBusy }: {
  subjectId: string; onSaved: (question: Question) => void; onBusy: (busy: boolean) => void;
}) {
  const [text, setText] = useState('');
  const [type, setType] = useState<Question['type']>('mcq');
  const [competency, setCompetency] = useState<CompetencyKey>('CU');
  const [bloomLevel, setBloomLevel] = useState<BloomLevel>('Understand');
  const [marks, setMarks] = useState(2);
  const [options, setOptions] = useState(['', '', '', '']);
  const [correctIndex, setCorrectIndex] = useState('');
  const [answer, setAnswer] = useState('');
  const [rubric, setRubric] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const inputClass = 'block w-full rounded-lg border border-surface-border p-2 text-sm mt-1';

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (saving) return;
    setError('');
    const cleanOptions = options.map((option) => option.trim());
    const correctAnswer = type === 'mcq' ? cleanOptions[Number(correctIndex)] : answer.trim();
    if (!text.trim() || !rubric.trim() || !correctAnswer || (type === 'mcq' && correctIndex === '')) {
      setError('Enter question text, an answer and a marking rubric or explanation.'); return;
    }
    if (!Number.isInteger(marks) || marks < 1) { setError('Marks must be a positive whole number.'); return; }
    if (type === 'mcq' && (cleanOptions.some((option) => !option) || new Set(cleanOptions.map((option) => option.toLowerCase())).size !== 4)) {
      setError('Enter four distinct, non-empty MCQ options.'); return;
    }
    setSaving(true); onBusy(true);
    try {
      const saved = await apiClient.assessments.createQuestion({
        subjectId, text: text.trim(), type, competency, bloomLevel, marks,
        options: type === 'mcq' ? cleanOptions : [], correctAnswer, markingRubric: rubric.trim(),
      });
      onSaved(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the question.');
    } finally { setSaving(false); onBusy(false); }
  };

  return <form onSubmit={save} className="space-y-4 text-sm">
    <fieldset disabled={saving} className="space-y-4">
      <label className="block">Question text<textarea required className={inputClass} value={text} onChange={(e) => setText(e.target.value)} /></label>
      <label className="block">Question type<select className={inputClass} value={type} onChange={(e) => setType(e.target.value as Question['type'])}>
        <option value="mcq">MCQ</option><option value="short">Short answer</option><option value="descriptive">Descriptive</option><option value="practical">Practical</option>
      </select></label>
      <label className="block">Primary competency<select className={inputClass} value={competency} onChange={(e) => setCompetency(e.target.value as CompetencyKey)}>
        {COMPETENCIES.map((code) => <option key={code} value={code}>{code} — {NAMES[code]}</option>)}
      </select></label>
      <label className="block">Bloom level<select className={inputClass} value={bloomLevel} onChange={(e) => setBloomLevel(e.target.value as BloomLevel)}>
        {BLOOMS.map((level) => <option key={level}>{level}</option>)}
      </select></label>
      <label className="block">Marks<input required type="number" min="1" step="1" className={inputClass} value={Number.isNaN(marks) ? '' : marks} onChange={(e) => setMarks(e.target.valueAsNumber)} /></label>
      {type === 'mcq' ? <div className="space-y-2">
        {options.map((option, index) => <label className="block" key={index}>Option {index + 1}<input required className={inputClass} value={option} onChange={(e) => setOptions((current) => current.map((value, i) => i === index ? e.target.value : value))} /></label>)}
        <label className="block">Correct answer<select required className={inputClass} value={correctIndex} onChange={(e) => setCorrectIndex(e.target.value)}>
          <option value="">Choose the correct option</option>{options.map((option, index) => <option key={index} value={index}>Option {index + 1}: {option}</option>)}
        </select></label>
      </div> : <label className="block">Expected answer<textarea required className={inputClass} value={answer} onChange={(e) => setAnswer(e.target.value)} /></label>}
      <label className="block">{type === 'mcq' ? 'Answer explanation / marking rubric' : 'Marking rubric'}<textarea required className={inputClass} value={rubric} onChange={(e) => setRubric(e.target.value)} /></label>
    </fieldset>
    {error && <p role="alert" className="text-rose-700">{error}</p>}
    <Button type="submit" variant="teal" loading={saving} disabled={saving || !subjectId}>Save Question</Button>
  </form>;
}
