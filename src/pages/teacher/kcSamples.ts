export type SampleConcept = { name: string; topic: string; description: string };
export type SampleRelationship = 'PREREQUISITE_OF' | 'RELATED_TO' | 'PART_OF';

export type SampleLink = { source: string; target: string; relationship: SampleRelationship };

export type SubjectSamples = {
  concepts: SampleConcept[];
  links: SampleLink[];
};

const MATH: SubjectSamples = {
  concepts: [
    { name: 'Limits', topic: 'Calculus', description: 'The value a function approaches.' },
    { name: 'Chain Rule', topic: 'Calculus', description: 'Differentiate a composition of functions.' },
    { name: 'Differentiation', topic: 'Calculus', description: 'The rate of change of a function.' },
  ],
  links: [{ source: 'Limits', target: 'Chain Rule', relationship: 'PREREQUISITE_OF' }],
};

const CHEMISTRY: SubjectSamples = {
  concepts: [
    { name: 'Atomic Structure', topic: 'Atoms', description: 'Protons, neutrons, and electron arrangement.' },
    { name: 'Electron Configuration', topic: 'Atoms', description: 'How electrons are arranged in shells.' },
    { name: 'Periodic Trends', topic: 'Atoms', description: 'How properties change across the periodic table.' },
    { name: 'Chemical Bonding', topic: 'Bonds', description: 'How atoms join to form compounds.' },
    { name: 'Molecules', topic: 'Bonds', description: 'Groups of atoms held together by bonds.' },
    { name: 'Stoichiometry', topic: 'Reactions', description: 'Using a balanced equation to count particles.' },
    { name: 'Acids and Bases', topic: 'Reactions', description: 'Substances that donate or accept a proton.' },
  ],
  links: [
    { source: 'Atomic Structure', target: 'Electron Configuration', relationship: 'PREREQUISITE_OF' },
    { source: 'Atomic Structure', target: 'Periodic Trends', relationship: 'PREREQUISITE_OF' },
    { source: 'Atomic Structure', target: 'Chemical Bonding', relationship: 'PREREQUISITE_OF' },
    { source: 'Chemical Bonding', target: 'Stoichiometry', relationship: 'PREREQUISITE_OF' },
    { source: 'Stoichiometry', target: 'Acids and Bases', relationship: 'PREREQUISITE_OF' },
    { source: 'Chemical Bonding', target: 'Molecules', relationship: 'PART_OF' },
    { source: 'Periodic Trends', target: 'Chemical Bonding', relationship: 'RELATED_TO' },
  ],
};

const SCIENCE: SubjectSamples = {
  concepts: [
    { name: 'Cell Structure', topic: 'Life processes', description: 'Parts of a cell and what each part does.' },
    { name: 'Photosynthesis', topic: 'Life processes', description: 'How plants make food from light.' },
    { name: 'Nutrition', topic: 'Life processes', description: 'How organisms obtain food.' },
    { name: 'Respiration', topic: 'Life processes', description: 'Releasing energy from food.' },
    { name: 'Force and Motion', topic: 'Motion', description: 'How forces change the way objects move.' },
    { name: 'Energy', topic: 'Motion', description: 'The capacity to make something move or change.' },
    { name: 'Habitat', topic: 'Environment', description: 'The place an organism lives.' },
  ],
  links: [
    { source: 'Cell Structure', target: 'Photosynthesis', relationship: 'PREREQUISITE_OF' },
    { source: 'Cell Structure', target: 'Nutrition', relationship: 'PREREQUISITE_OF' },
    { source: 'Photosynthesis', target: 'Respiration', relationship: 'PREREQUISITE_OF' },
    { source: 'Force and Motion', target: 'Energy', relationship: 'PREREQUISITE_OF' },
    { source: 'Nutrition', target: 'Habitat', relationship: 'RELATED_TO' },
    { source: 'Photosynthesis', target: 'Energy', relationship: 'PART_OF' },
    { source: 'Cell Structure', target: 'Force and Motion', relationship: 'RELATED_TO' },
  ],
};

const ENGLISH: SubjectSamples = {
  concepts: [
    { name: 'Grammar', topic: 'Language', description: 'Rules for building a correct sentence.' },
    { name: 'Comprehension', topic: 'Language', description: 'Understanding the meaning of a passage.' },
    { name: 'Vocabulary', topic: 'Language', description: 'Words and how they are used.' },
  ],
  links: [{ source: 'Vocabulary', target: 'Comprehension', relationship: 'PREREQUISITE_OF' }],
};

const SOCIAL: SubjectSamples = {
  concepts: [
    { name: 'Maps', topic: 'Geography', description: 'Reading direction, scale, and symbols.' },
    { name: 'Constitution', topic: 'Civics', description: 'The basic rules of the country.' },
    { name: 'Resources', topic: 'Geography', description: 'Natural resources and how people use them.' },
  ],
  links: [{ source: 'Maps', target: 'Resources', relationship: 'RELATED_TO' }],
};

const GENERAL: SubjectSamples = {
  concepts: [
    { name: 'Core idea', topic: 'Foundations', description: 'The main idea of the topic.' },
    { name: 'Worked example', topic: 'Foundations', description: 'A solved example of the core idea.' },
    { name: 'Practice', topic: 'Foundations', description: 'Using the idea on a new question.' },
  ],
  links: [{ source: 'Core idea', target: 'Practice', relationship: 'PREREQUISITE_OF' }],
};

export function samplesFor(subjectName: string): SubjectSamples {
  const name = subjectName.toLowerCase();
  if (name.includes('chem')) return CHEMISTRY;
  if (name.includes('math')) return MATH;
  if (name.includes('eng')) return ENGLISH;
  if (name.includes('social') || name.includes('civics') || name.includes('histor') || name.includes('geograph')) return SOCIAL;
  if (name.includes('sci')) return SCIENCE;
  return GENERAL;
}
