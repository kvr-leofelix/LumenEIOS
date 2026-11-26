import React from 'react';
import {useLearning} from './LearnSphereLayout';
import {PanchapadiProgress} from '../../components/learnsphere/PanchapadiProgress';
export function LearningJourney(){
  const {studentId}=useLearning();
  return <div className="space-y-4"><h2 className="text-xl font-semibold">Learning Journey</h2><p>Assessment performance over time. View question-wise guidance and the selected assessment distribution in Learning Support.</p>{studentId?<PanchapadiProgress key={studentId} studentId={studentId}/>:<p>Select a student.</p>}</div>;
}
