import React from 'react';
import type { Scope } from '../../types/learnsphere';
export function StudentScopeSelector({scope, classId, studentId, onClass, onStudent}: {scope: Scope; classId: string; studentId: string; onClass: (id: string) => void; onStudent: (id: string) => void}) {
  const selectedSchool = scope.classes.find(c => c.id === classId)?.school_id || '';
  const schools = scope.schools || [...new Set(scope.classes.map(c => c.school_id))].map(id => ({id, name:id}));
  return <div className="grid sm:grid-cols-3 gap-4 bg-white border rounded-xl p-4">
    <label>Authorized school<select aria-label="Authorized school" className="block w-full border rounded-lg p-2" value={selectedSchool} onChange={e => onClass(scope.classes.find(c => c.school_id === e.target.value)?.id || '')}>
      <option value="">Choose a school</option>{schools.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
    </select></label>
    <label>Authorized class<select aria-label="Authorized class" className="block w-full border rounded-lg p-2" value={classId} onChange={e => onClass(e.target.value)}>
      <option value="">Choose a class</option>{scope.classes.filter(c => !selectedSchool || c.school_id === selectedSchool).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
    </select></label>
    <label>Student<select aria-label="Student" className="block w-full border rounded-lg p-2" value={studentId} onChange={e => onStudent(e.target.value)}>
      <option value="">Choose a student</option>{scope.students.filter(s => s.class_id === classId).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
    </select></label>
  </div>;
}
