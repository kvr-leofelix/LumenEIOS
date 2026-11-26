import { LANGUAGE_LABEL, type LanguageTag } from './types';

export const ERA_LABEL: Record<string, string> = {
  CURRENT: 'Current',
  CURRENT_NEW_TEXTBOOKS: 'For current textbooks',
  HISTORICAL_2006: 'Historical (2006)',
  LEGACY_OUTCOMES: '2017 outcomes document',
  CURRENT_CLASS_OUTCOMES: 'Current class-specific',
  '2024_IMPLEMENTATION': '2024 implementation advisory',
};

export const RESOURCE_TYPE_LABEL: Record<string, string> = {
  CURRICULUM_FRAMEWORK: 'Curriculum framework',
  SYLLABUS: 'Syllabus',
  LEARNING_OUTCOMES_DOCUMENT: 'Learning outcomes',
  PRESCRIBED_TEXTBOOK_WORK: 'Textbook work',
  TEXTBOOK_PART: 'Textbook part',
  LANGUAGE_EDITION: 'Language edition',
  COURSE_IMPLEMENTATION_GUIDANCE: 'Implementation guidance',
};

export const languageLabel = (lang: string) => LANGUAGE_LABEL[lang as LanguageTag] ?? lang;
export const eraLabel = (era: string) => ERA_LABEL[era] ?? era.replace(/_/g, ' ').toLowerCase();
export const humanize = (code: string) => code.split(';')[0].replace(/_/g, ' ').toLowerCase();
