import { Student, CompetencyScores, CurriculumDay, LostTeachingDay } from '../types';

export function calculateAverageCompetencies(students: Student[]): CompetencyScores {
  if (!students || students.length === 0) {
    return { LU: 0, CU: 0, AU: 0, CT: 0, overall: 0 };
  }

  const totals = students.reduce(
    (acc, s) => {
      acc.LU += s.competencies.LU;
      acc.CU += s.competencies.CU;
      acc.AU += s.competencies.AU;
      acc.CT += s.competencies.CT;
      acc.overall += s.competencies.overall;
      return acc;
    },
    { LU: 0, CU: 0, AU: 0, CT: 0, overall: 0 }
  );

  const count = students.length;
  return {
    LU: Math.round(totals.LU / count),
    CU: Math.round(totals.CU / count),
    AU: Math.round(totals.AU / count),
    CT: Math.round(totals.CT / count),
    overall: Math.round(totals.overall / count),
  };
}

export interface PacingMetrics {
  totalOfficialDays: number;
  currentDay: number;
  totalLostDays: number;
  remainingInstructionalDays: number;
  coreConceptsRemaining: number;
  supplementaryTopicsRemaining: number;
  totalPeriodsNeededOriginal: number;
  pacingBuffer: number; // positive = ahead, negative = behind
  riskStatus: 'low' | 'medium' | 'high';
  riskLabel: string;
}

/**
 * Legacy seed-data pacing (CurriculumDay / lostTeachingDays).
 * Authoritative instructional progress for Classes VI–VIII Mathematics & Science
 * lives in `lib/planning/progress.ts` (planProgress / workspaceProgress).
 */
export function calculateTimeAwarePacing(
  curriculum: CurriculumDay[],
  lostDaysList: LostTeachingDay[],
  totalOfficialDays = 180,
  currentDay = 104
): PacingMetrics {
  const totalLostDays = lostDaysList.reduce((sum, item) => sum + item.daysLost, 0);
  
  // Actual available teaching days left in the academic calendar
  const grossRemainingDays = Math.max(0, totalOfficialDays - currentDay);
  const remainingInstructionalDays = Math.max(0, grossRemainingDays - totalLostDays);

  const pendingDays = curriculum.filter(
    (d) => d.status === 'pending' || d.status === 'in-progress'
  );
  const coreConceptsRemaining = pendingDays.filter((d) => d.classification === 'core').length;
  const supplementaryTopicsRemaining = pendingDays.filter((d) => d.classification === 'supplementary').length;

  const totalPeriodsNeededOriginal = coreConceptsRemaining + supplementaryTopicsRemaining;
  const pacingBuffer = remainingInstructionalDays - totalPeriodsNeededOriginal;

  let riskStatus: 'low' | 'medium' | 'high' = 'low';
  let riskLabel = 'On Track (Healthy Buffer)';

  if (pacingBuffer < -3) {
    riskStatus = 'high';
    riskLabel = 'High Pacing Risk (Deficit: ' + Math.abs(pacingBuffer) + ' days)';
  } else if (pacingBuffer <= 3) {
    riskStatus = 'medium';
    riskLabel = 'Tight Pacing (Buffer: ' + pacingBuffer + ' days)';
  }

  return {
    totalOfficialDays,
    currentDay,
    totalLostDays,
    remainingInstructionalDays,
    coreConceptsRemaining,
    supplementaryTopicsRemaining,
    totalPeriodsNeededOriginal,
    pacingBuffer,
    riskStatus,
    riskLabel,
  };
}

export interface CompressionPlanProposal {
  originalDurationDays: number;
  revisedDurationDays: number;
  daysSaved: number;
  topicsPreservedCount: number;
  topicsReassignedCount: number;
  topicsIntegratedCount: number;
  reassignedTopics: CurriculumDay[];
  integratedTopics: CurriculumDay[];
  preservedCoreCount: number;
  tradeOffAnalysis: string[];
  remediationRequirements: string[];
}

/** Legacy callers must use the approved planning workspace allocator. */
export function generateSyllabusCompressionPlan(_curriculum: CurriculumDay[], _lostDaysCount: number): CompressionPlanProposal {
  throw new Error('Legacy compression is retired. Use approved topic requirements in the Time-Aware Engine.');
}

export function recommendDifferentiatedHomework(student: Student) {
  const { LU, CU, AU, CT } = student.competencies;
  const minVal = Math.min(LU, CU, AU, CT);

  if (minVal === LU) {
    return {
      competency: 'LU' as const,
      title: 'Word Problem Linguistic Scaffolding: Visual Keyword Annotations',
      description: 'Break down complex multi-clause mathematics and science statements with bilingual vocabulary glossaries and color-coded clue identification.',
      rationale: `Student has an LU score of ${LU}%. Strengthening reading comprehension directly unlocks performance in applied word problems.`,
    };
  } else if (minVal === CU) {
    return {
      competency: 'CU' as const,
      title: 'Visual Concept Mapping & Number Line Decomposition',
      description: 'Hands-on diagrammatic representation of rational operations and algebraic variables using interactive balance scales.',
      rationale: `Student has a CU score of ${CU}%. Visual structural mapping cements fundamental mental models before algebraic abstraction.`,
    };
  } else if (minVal === AU) {
    return {
      competency: 'AU' as const,
      title: 'Real-World Household Mensuration & Data Collection Lab',
      description: 'Calculate volume and surface area using actual kitchen containers, converting between cubic centimeters and liters.',
      rationale: `Student has an AU score of ${AU}%. Concrete practical applications bridge the gap between classroom formulae and physical reality.`,
    };
  } else {
    return {
      competency: 'CT' as const,
      title: 'Counterexample Investigation & Fallacy Detection',
      description: 'Evaluate mathematical conjectures and advertising graph representations to identify truncated axes and flawed generalizations.',
      rationale: `Student has a CT score of ${CT}%. Targeted critical thinking exercises foster analytical rigor and hypothesis testing.`,
    };
  }
}

