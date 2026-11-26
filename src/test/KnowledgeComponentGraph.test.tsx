import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { KnowledgeGraphView, type KnowledgeGraph } from '../pages/student/KnowledgeComponentGraph';

const graph: KnowledgeGraph = {
  insights: ['Practice reasoning-based exercises on Chain Rule.'],
  edges: [{ source_id: 'limits', target_id: 'chain', relationship: 'PREREQUISITE_OF' }],
  nodes: [
    {
      id: 'limits',
      name: 'Limits',
      description: 'The value a function approaches.',
      subject: 'Mathematics',
      topic: 'Calculus',
      overall_mastery: null,
      lu: null,
      cu: null,
      ct: null,
      au: null,
      attempt_count: 0,
      correct_count: 0,
      incorrect_count: 0,
      learning_status: 'not_assessed',
      last_assessed_at: null,
      latest: { LU: null, CU: null, CT: null, AU: null },
      previous: { LU: null, CU: null, CT: null, AU: null },
      history: [],
      prerequisites: [],
      related: [],
      recommendations: [],
    },
    {
      id: 'chain',
      name: 'Chain Rule',
      description: 'Differentiate a composition.',
      subject: 'Mathematics',
      topic: 'Calculus',
      overall_mastery: 60,
      lu: 85,
      cu: 75,
      ct: 45,
      au: 30,
      attempt_count: 3,
      correct_count: 2,
      incorrect_count: 1,
      learning_status: 'developing',
      last_assessed_at: '2026-11-14T00:00:00Z',
      latest: { LU: 85, CU: 75, CT: 45, AU: 30 },
      previous: { LU: 70, CU: null, CT: null, AU: null },
      history: [{
        assessed_at: '2026-11-14T00:00:00Z',
        question_id: '1',
        competency: 'CT',
        score: 45,
        awarded_marks: 1,
        max_marks: 2,
        correct: false,
      }],
      prerequisites: [{
        id: 'limits', name: 'Limits', relationship: 'PREREQUISITE_OF',
        overall_mastery: null, learning_status: 'not_assessed',
      }],
      related: [],
      recommendations: ['Practice reasoning-based exercises on Chain Rule.'],
    },
  ],
};

describe('knowledge component graph', () => {
  it('shows mastery, prerequisites, and recommendations from the supplied graph', async () => {
    render(<KnowledgeGraphView graph={graph} />);
    expect(screen.getByRole('button', { name: /Limits/ }).dataset.status).toBe('not_assessed');
    expect(screen.getByRole('button', { name: /Chain Rule/ }).dataset.status).toBe('developing');
    expect(screen.getAllByText('Practice reasoning-based exercises on Chain Rule.').length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole('button', { name: /Chain Rule/ }));
    expect(screen.getByText('85%')).toBeInTheDocument();
    expect(screen.getByText('75%')).toBeInTheDocument();
    expect(screen.getByText('45%')).toBeInTheDocument();
    expect(screen.getByText('30%')).toBeInTheDocument();
    expect(screen.getByText('3 (2 correct, 1 incorrect)')).toBeInTheDocument();
    expect(screen.getByText(/CT 45%/)).toBeInTheDocument();
    expect(screen.getByText(/Limits · Not assessed/)).toBeInTheDocument();
  });
});
