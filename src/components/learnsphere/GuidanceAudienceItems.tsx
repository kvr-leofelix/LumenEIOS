import React from 'react';
import {useAuth} from '../../context/AuthContext';
import type {AssessmentGuidance} from '../../types/assessmentGuidance';
type Advice=NonNullable<AssessmentGuidance['questions'][number]['guidance']>;
export function GuidanceAudienceItems({guidance}:{guidance:Advice}){
  const {currentUser}=useAuth();const role=currentUser?.role;
  const teacher=role==='teacher'||role==='principal';
  const teacherOnly=guidance.activity_for_student||guidance.activity?.startsWith('Create a simple experiment where students can observe the attraction of ');
  const practiceLabel=guidance.practice_for_student?(teacher?'Practice question for the student':role==='parent'?'Help your child practise with this question':role==='student'?'Your practice question':null):null;
  return <>
    {guidance.activity&&(!teacherOnly||teacher)&&<>{teacherOnly&&<p className="font-medium">Student activity — intended for the student to perform</p>}<p>Try this: {guidance.activity}</p></>}
    {guidance.practice_question&&<>{practiceLabel&&<p className="font-medium">{practiceLabel}</p>}<p>Practice question: {guidance.practice_question}</p></>}
  </>;
}
