import React, { useEffect, useState } from 'react';
import { apiClient } from '../../lib/apiClient';
import { Button } from '../../components/common/Button';
import { Empty, Messages, ReleasedResult, Section, StatusBadge, formatDate, useRunner } from './ui';

const hw = apiClient.homework;

/** Parent view: linked children (ParentStudentLink), their homework, and released results only. */
export const ParentWorkspace: React.FC = () => {
  const { busy, error, run } = useRunner();
  const [children, setChildren] = useState<any[]>([]);
  const [child, setChild] = useState('');
  useEffect(() => { run(async () => {
    const rows = await hw.parentChildren(); setChildren(rows); if (rows.length) setChild(rows[0].id);
  }); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return <div className="space-y-5">
    <Messages error={error} />
    {children.length === 0 ? (!busy && !error && <Empty>No students are linked to this parent account. Contact the school.</Empty>) :
      <nav className="flex flex-wrap gap-2" aria-label="Linked students">{children.map(c =>
        <Button key={c.id} variant={c.id === child ? 'primary' : 'outline'} onClick={() => setChild(c.id)}>{c.name} - {c.class_name}</Button>)}</nav>}
    {child && <ChildHomework key={child} studentId={child} name={children.find(c => c.id === child)?.name} />}
  </div>;
};

function ChildHomework({ studentId, name }: { studentId: string; name?: string }) {
  const { busy, error, run } = useRunner();
  const [rows, setRows] = useState<any[]>([]);
  const [open, setOpen] = useState('');
  const [result, setResult] = useState<any>(null);
  const refresh = async () => setRows(await hw.parentAssignments(studentId));
  useEffect(() => { run(refresh); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
    <Section title={`${name ?? 'Student'}'s homework`} action={<Button size="sm" variant="outline" disabled={busy} onClick={() => run(refresh)}>Refresh</Button>}>
      <Messages error={error} />
      {rows.length === 0 ? <Empty>No homework has been assigned yet.</Empty> :
        <ul className="space-y-1.5">{rows.map(a => <li key={a.id} className={'rounded-xl border px-3 py-2.5 ' + (open === a.id ? 'border-teal-400 bg-teal-50' : 'border-surface-border bg-white')}>
          <div className="flex items-center justify-between gap-2"><span className="text-sm font-medium">{a.subject_name || a.subject_id}</span>
            <StatusBadge status={a.result_released ? 'released' : a.submission_status} /></div>
          <p className="text-xs text-content-secondary">{a.question_count} questions · {a.total_marks} marks · assigned {formatDate(a.assigned_at)} · due {formatDate(a.due_at)}</p>
          {a.result_released ? <Button className="mt-1" size="sm" variant="teal" disabled={busy} onClick={() => run(async () => {
            setOpen(a.id); setResult(await hw.parentResult(studentId, a.id));
          })}>View result</Button> : <p className="mt-1 text-xs text-content-secondary">Result not released yet.</p>}
        </li>)}</ul>}
    </Section>
    <Section title="Released result">
      {result && open ? <ReleasedResult result={result} /> : <Empty>Choose a homework with a released result.</Empty>}
    </Section>
  </div>;
}
