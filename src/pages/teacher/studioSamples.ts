import type { CompetencyKey, Question } from '../../types';

const FOCUS: Record<string, string> = {
  LU: 'language understanding',
  CU: 'conceptual understanding',
  CT: 'critical thinking',
  AU: 'application',
};

export function topicHintFor(conceptName: string, weakest: string | null) {
  const focus = weakest ? FOCUS[weakest] : '';
  return focus ? `${conceptName}, with extra practice on ${focus}` : conceptName;
}

export function questionConceptLabels(text: string, conceptNames: string[]) {
  const folded = text.toLocaleLowerCase();
  const names = [...new Set(conceptNames.map((name) => name.trim()).filter(Boolean))].sort((a, b) => b.length - a.length);
  return names.filter((name) => name.length >= 3 && phraseIn(folded, name.toLocaleLowerCase()));
}

function phraseIn(text: string, phrase: string) {
  let start = 0;
  while (start <= text.length) {
    const index = text.indexOf(phrase, start);
    if (index < 0) return false;
    const before = index > 0 ? text[index - 1] : ' ';
    const after = index + phrase.length < text.length ? text[index + phrase.length] : ' ';
    if (!isAlnum(before) && !isAlnum(after)) return true;
    start = index + 1;
  }
  return false;
}

function isAlnum(value: string) {
  return /[0-9a-z]/i.test(value);
}

export function sampleQuestionsFor(conceptName: string, competency: CompetencyKey): Question[] {
  const other = competency === 'LU' ? 'CU' : 'LU';
  return [
    {
      id: `sample-${conceptName}-recall`,
      text: `State the meaning of ${conceptName}.`,
      type: 'short',
      marks: 2,
      competency,
      bloomLevel: 'Remember',
      isAiGenerated: true,
      markingRubric: `Award both marks for a clear statement of ${conceptName}.`,
    },
    {
      id: `sample-${conceptName}-apply`,
      text: `Use ${conceptName} to solve this new classroom problem. Show the step you check first.`,
      type: 'descriptive',
      marks: 4,
      competency: competency === 'AU' ? 'AU' : 'AU',
      bloomLevel: 'Apply',
      isAiGenerated: true,
      markingRubric: `Award marks for a correct use of ${conceptName} and a stated check.`,
    },
    {
      id: `sample-${conceptName}-reason`,
      text: `Two explanations of ${conceptName} disagree. Which one is stronger, and why?`,
      type: 'descriptive',
      marks: 4,
      competency: 'CT',
      bloomLevel: 'Evaluate',
      isAiGenerated: true,
      markingRubric: `Award marks for a justified choice about ${conceptName}.`,
    },
    {
      id: 'sample-unrelated-roster',
      text: 'Copy the class register heading onto your answer sheet.',
      type: 'short',
      marks: 1,
      competency: other,
      bloomLevel: 'Remember',
      isAiGenerated: true,
      markingRubric: 'This item does not assess the selected concept.',
    },
  ];
}
