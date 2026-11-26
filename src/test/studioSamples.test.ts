import { describe, expect, it } from 'vitest';
import { questionConceptLabels, sampleQuestionsFor, topicHintFor } from '../pages/teacher/studioSamples';

describe('studio sample questions', () => {
  it('fills the topic from the weak competency and marks only matching questions', () => {
    expect(topicHintFor('Chemical Bonding', 'CU')).toBe('Chemical Bonding, with extra practice on conceptual understanding');
    const questions = sampleQuestionsFor('Chemical Bonding', 'CU');
    const matching = questions.filter((question) => questionConceptLabels(question.text, ['Chemical Bonding']).length > 0);
    expect(matching).toHaveLength(3);
    expect(questions.some((question) => questionConceptLabels(question.text, ['Chemical Bonding']).length === 0)).toBe(true);
  });
});
