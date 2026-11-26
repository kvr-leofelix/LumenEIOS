import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { LearnSphereResultReview } from '../components/learnsphere/LearnSphereResultReview';
import { assessmentResults } from '../lib/assessmentResults';
import { CompetencyReview } from '../components/learnsphere/CompetencyReview';
import { ManualQuestionForm } from '../components/common/ManualQuestionForm';
import { learnsphere } from '../lib/learnsphere';
import { apiClient } from '../lib/apiClient';
import { distributeQuestions, distributionError } from '../lib/questionStudio';

afterEach(() => vi.restoreAllMocks());

describe('LearnSphere integrated review', () => {
  it('keeps a failed competency review visible and submits a separate decision', async () => {
    const saved = vi.fn();
    const review = vi.spyOn(learnsphere,'reviewCompetencies').mockRejectedValueOnce(new Error('Stale competency version')).mockResolvedValueOnce({} as any);
    render(<CompetencyReview studentId="student" assessmentId="assessment" position={0} version={2} mapping={{position:0,label:null,confidence:0.4,reason:'Ambiguous task',status:'requires_review'}} onSaved={saved}/>);
    fireEvent.click(screen.getByText('Review primary competency'));
    fireEvent.change(screen.getByLabelText('Q1 primary competency'),{target:{value:'CT'}});
    fireEvent.click(screen.getByRole('button',{name:'Save competency review'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Stale competency version');
    expect(saved).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Save competency review'}));
    await waitFor(() => expect(saved).toHaveBeenCalledOnce());
    const body = review.mock.calls[1][2] as any;
    expect(body).toMatchObject({expected_version:2,questions:[{position:0,label:'CT',reason:'Ambiguous task'}]});
    expect(body.request_key).toBe((review.mock.calls[0][2] as any).request_key);
    expect(body).not.toHaveProperty('confirm_panchapadi');
  });
  it('leaves unknown marks blank and confirms marks independently of competency decisions', async () => {
    vi.spyOn(learnsphere,'assessmentResult').mockResolvedValue({id:'result',version:7,questions:[{position:0,text:'Explain the relationship.',type:'short',options:[],marks:2,competency:'CU',correct_answer:'A relationship.',marking_rubric:'Explain the cause.'}],answers:[{position:0,answer_text:'Saved learner response.'}],outcomes:[{position:0,score:null,feedback:''}]} as any);
    const review=vi.spyOn(assessmentResults,'review').mockResolvedValue({} as any);
    const saved=vi.fn();
    render(<LearnSphereResultReview resultId="result" onSaved={saved}/>);
    const score=await screen.findByLabelText('Q1 reviewed marks');
    expect(score).toHaveValue(null);
    expect(screen.getByText('Saved learner response.')).toBeInTheDocument();
    fireEvent.change(score,{target:{value:'1'}});
    fireEvent.change(screen.getByLabelText('Q1 feedback'),{target:{value:'Explain the missing cause.'}});
    fireEvent.change(screen.getByLabelText('Overall teacher feedback'),{target:{value:'Add a justification.'}});
    fireEvent.click(screen.getByRole('button',{name:'Confirm reviewed marks'}));
    await waitFor(() => expect(saved).toHaveBeenCalledOnce());
    expect(review.mock.calls[0][1]).toMatchObject({expected_version:7,confirm_panchapadi:false,panchapadi_mappings:null,questions:[{position:0,score:1,correct:false}]});
    expect(review.mock.calls[0][1]).not.toHaveProperty('competency_reviews');
  });
  it('allocates counts stably and rejects a mismatched total', () => {
    expect(distributeQuestions(10,['CT','AU','CU','LU'])).toEqual({LU:3,CU:3,AU:2,CT:2});
    expect(distributionError({LU:1,CU:0,AU:0,CT:0},5)).toContain('Counts must match');
  });
  it('keeps manual creation open on persistence failure', async () => {
    const saved=vi.fn();
    vi.spyOn(apiClient.assessments,'createQuestion').mockRejectedValue(new Error('Save unavailable'));
    render(<ManualQuestionForm subjectId="science" onSaved={saved} onBusy={vi.fn()}/>);
    fireEvent.change(screen.getByLabelText('Question type'),{target:{value:'short'}});
    fireEvent.change(screen.getByLabelText('Question text'),{target:{value:'Explain the relationship.'}});
    fireEvent.change(screen.getByLabelText('Expected answer'),{target:{value:'A reasoned answer.'}});
    fireEvent.change(screen.getByLabelText('Marking rubric'),{target:{value:'Credit a justified explanation.'}});
    fireEvent.click(screen.getByRole('button',{name:'Save Question'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Save unavailable');
    expect(saved).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Question text')).toHaveValue('Explain the relationship.');
  });
});
