import React, { useMemo, useState } from 'react';
import { GitBranch } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { GRADE_LABEL } from '../../lib/planning/calendar';
import { Relationship, RelationshipType, validateRelationship } from '../../lib/planning/governance';
import { crossCurricularSummary } from '../../lib/planning/engine';
import { currentVersion } from '../../lib/planning/execution';
import { findNode, SCHEDULABLE_KINDS, SyllabusNode } from '../../lib/planning/syllabus';
import { usePlanning } from '../../lib/planning/usePlanning';
import { describeError, teacherPlanApi } from '../../lib/teacherPlanApi';
import { invalidateRequirements } from '../../features/teacherPlan/requirementsStore';
import { topicKeyOf } from '../../features/teacherPlan/useTeacherCoverage';
import { inputCls, labelCls, SectionCard, selectCls, tdCls, thCls } from './planningUi';

const nodeLabel = (n: SyllabusNode | undefined) => (n ? `Class ${GRADE_LABEL[n.grade]} ${n.subject} · ${n.number} ${n.title}` : 'Unknown unit');

/** Relationships are the teacher's own relational records (also what the scheduling engine reads); nothing is stored in the workspace. */
export const RelationshipsPanel: React.FC<{ grade: number }> = ({ grade }) => {
  const p = usePlanning();
  const rels: Relationship[] = p.ctx.relationships;
  const units = useMemo(() => p.datasets.flatMap((d) => d.nodes.filter((n) => SCHEDULABLE_KINDS.includes(n.kind))), [p.datasets]);
  const [type, setType] = useState<RelationshipType>('CROSS_CURRICULAR');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [explanation, setExplanation] = useState('');
  const [evidence, setEvidence] = useState('');
  const [shared, setShared] = useState(0);
  const [lead, setLead] = useState('');
  const [errors, setErrors] = useState<string[]>([]);

  const submit = async () => {
    const fromNode = findNode(p.datasets, from);
    const toNode = findNode(p.datasets, to);
    const draft = { type, fromNodeId: from, toNodeId: to, explanation, evidence, sharedPeriods: type === 'CROSS_CURRICULAR' ? shared : 0, leadNodeId: type === 'CROSS_CURRICULAR' && shared > 0 ? lead : null };
    const errs = validateRelationship(draft, fromNode, toNode, rels);
    setErrors(errs);
    if (errs.length || !p.ownsPlan) return;
    try {
      await teacherPlanApi.addRelationship(p.teacherId, {
        kind: type,
        from_key: topicKeyOf(from),
        to_key: topicKeyOf(to),
        explanation: explanation.trim(),
        evidence: evidence.trim(),
        shared_periods: draft.sharedPeriods,
        lead_key: draft.leadNodeId ? topicKeyOf(draft.leadNodeId) : null,
      });
      invalidateRequirements(); // engine, Catalogue and this panel reload the same rows
      setExplanation('');
      setEvidence('');
      setShared(0);
    } catch (e) {
      const d = describeError(e);
      const server = (e as { data?: { detail?: { errors?: string[] } } })?.data?.detail?.errors;
      setErrors(server?.length ? server : [d.message]);
    }
  };

  const remove = async (r: Relationship) => {
    try {
      await teacherPlanApi.removeRelationship(p.teacherId, r.id, 'Removed by the teacher');
      invalidateRequirements();
    } catch (e) {
      setErrors([describeError(e).message]);
    }
  };

  const gradePlans = p.workspace.plans.filter((pl) => pl.status === 'APPROVED' && pl.grade === grade);
  const summary = crossCurricularSummary(
    gradePlans.map((pl) => currentVersion(pl)?.lessons ?? []),
    rels,
  );
  const fromNode = findNode(p.datasets, from);
  const toNode = findNode(p.datasets, to);

  return (
    <div className="space-y-6">
      <SectionCard title="Topic relationships" subtitle="Prerequisites and Mathematics–Science links saved by the teacher. They are used when the schedule is built and recovered." action={<GitBranch className="w-4 h-4 text-teal-600" />}>
        {!rels.length && (
          <p className="p-3 rounded-lg bg-surface-bg border border-surface-border text-content-secondary">
            No relationships recorded. The current syllabus data documents no Mathematics–Science overlap or prerequisite chain, so none is pre-populated or suggested automatically. Add one below with source evidence.
          </p>
        )}
        {rels.length > 0 && (
          <div className="overflow-x-auto border border-surface-border rounded-xl">
            <table className="w-full">
              <thead>
                <tr>
                  {['Type', 'From', 'To', 'Explanation & evidence', 'Status', ''].map((h) => (
                    <th key={h} className={thCls}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rels.map((r) => (
                  <tr key={r.id} data-testid="relationship-row">
                    <td className={tdCls}>{r.type === 'PREREQUISITE' ? 'Prerequisite' : 'Cross-curricular'}</td>
                    <td className={tdCls}>{nodeLabel(findNode(p.datasets, r.fromNodeId))}</td>
                    <td className={tdCls}>{nodeLabel(findNode(p.datasets, r.toNodeId))}</td>
                    <td className={tdCls}>
                      {r.explanation}
                      <span className="block text-[11px] text-content-muted">Evidence: {r.evidence}</span>
                      {r.type === 'CROSS_CURRICULAR' && r.sharedPeriods > 0 && (
                        <span className="block text-[11px] text-indigo-800">
                          {r.sharedPeriods} shared period(s) taught once in {findNode(p.datasets, r.leadNodeId ?? '')?.title}
                        </span>
                      )}
                    </td>
                    <td className={tdCls}>
                      <Badge size="sm" variant="success">
                        active
                      </Badge>
                    </td>
                    <td className={tdCls}>
                      {p.ownsPlan && (
                        <Button size="sm" variant="outline" onClick={() => remove(r)}>
                          Remove
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <SectionCard title={`Cross-curricular coverage — Class ${GRADE_LABEL[grade]}`} subtitle="Counts shared outcomes and shared time once across Mathematics and Science">
        <div className="grid sm:grid-cols-3 gap-3">
          <div className="p-3 rounded-lg border border-surface-border">
            <p className="text-content-secondary">Approved links in approved plans</p>
            <p className="text-lg font-bold text-navy-900">{summary.links.length}</p>
          </div>
          <div className="p-3 rounded-lg border border-surface-border">
            <p className="text-content-secondary">Distinct outcome references covered</p>
            <p className="text-lg font-bold text-navy-900">{summary.uniqueOutcomes}</p>
            <p className="text-[11px] text-content-muted">{summary.naiveOutcomeCount} unit–outcome links before de-duplication</p>
          </div>
          <div className="p-3 rounded-lg border border-surface-border">
            <p className="text-content-secondary">Shared periods counted once</p>
            <p className="text-lg font-bold text-navy-900">{summary.sharedPeriodsCountedOnce}</p>
          </div>
        </div>
        <p className="text-[11px] text-content-muted">Linked units remain visible in both subjects’ Daily Curriculum; only the shared portion of time is removed from the non-lead unit.</p>
      </SectionCard>

      <SectionCard title="Add a relationship" subtitle="Must be grounded in both units’ syllabus sources">
        <div className="grid md:grid-cols-2 gap-3">
          <label>
            <span className={labelCls}>Type</span>
            <select aria-label="Relationship type" className={selectCls} value={type} onChange={(e) => setType(e.target.value as RelationshipType)}>
              <option value="CROSS_CURRICULAR">Cross-curricular (Mathematics ↔ Science)</option>
              <option value="PREREQUISITE">Prerequisite (from must precede to)</option>
            </select>
          </label>
          <span />
          {[
            ['From unit', from, setFrom],
            ['To unit', to, setTo],
          ].map(([label, value, setter]) => (
            <label key={label as string}>
              <span className={labelCls}>{label as string}</span>
              <select aria-label={label as string} className={`${selectCls} w-full`} value={value as string} onChange={(e) => (setter as (v: string) => void)(e.target.value)}>
                <option value="">Select a unit…</option>
                {units.map((u) => (
                  <option key={u.id} value={u.id}>
                    {nodeLabel(u)}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <label className="md:col-span-2">
            <span className={labelCls}>Conceptual relationship</span>
            <textarea aria-label="Relationship explanation" className={inputCls} rows={2} value={explanation} onChange={(e) => setExplanation(e.target.value)} />
          </label>
          <label className="md:col-span-2">
            <span className={labelCls}>Evidence (section locators in both sources)</span>
            <input aria-label="Relationship evidence" className={inputCls} value={evidence} onChange={(e) => setEvidence(e.target.value)} />
          </label>
          {type === 'CROSS_CURRICULAR' && (
            <>
              <label>
                <span className={labelCls}>Shared periods taught once</span>
                <input aria-label="Shared periods" type="number" min={0} className={inputCls} value={shared} onChange={(e) => setShared(Number(e.target.value))} />
              </label>
              <label>
                <span className={labelCls}>Unit that teaches the shared portion</span>
                <select aria-label="Lead unit" className={`${selectCls} w-full`} value={lead} onChange={(e) => setLead(e.target.value)}>
                  <option value="">Select…</option>
                  {[fromNode, toNode].filter(Boolean).map((n) => (
                    <option key={n!.id} value={n!.id}>
                      {nodeLabel(n)}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}
        </div>
        {errors.length > 0 && (
          <ul className="text-rose-700 text-[11px]">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        )}
        <Button size="sm" variant="primary" onClick={submit} disabled={!p.ownsPlan} title={p.ownsPlan ? '' : 'Only the owning teacher can change relationships.'}>
          Save relationship
        </Button>
      </SectionCard>
    </div>
  );
};
