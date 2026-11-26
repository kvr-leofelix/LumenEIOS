import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useData } from '../../context/DataContext';
import { Card, CardHeader, CardBody } from '../../components/common/Card';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { planLabel } from '../../lib/planning/execution';
import { effectiveLosses } from '../../lib/planning/losses';
import { workspaceProgress } from '../../lib/planning/progress';
import { Download, Printer, CheckCircle2 } from 'lucide-react';

import { usePlanning } from '../../lib/planning/usePlanning';

export const PrincipalReports: React.FC = () => {
  const planned = usePlanning(); // plans are the relational teacher plans, one per teacher
  const [toast, setToast] = useState<string | null>(null);
  const approved = planned.workspace.plans.filter((p) => p.status === 'APPROVED');
  const progress = workspaceProgress(approved);
  const lossRows = approved.flatMap((plan) =>
    effectiveLosses(plan).map((r) => ({
      plan: planLabel(plan),
      date: r.date,
      periods: r.periodsLost,
      reason: r.reason,
      note: r.note,
    })),
  );
  const recoveryRows = approved.flatMap((plan) =>
    plan.proposals.map((x) => ({
      plan: planLabel(plan),
      status: x.status,
      createdAt: x.createdAt.slice(0, 10),
      changes: x.changes.length,
      review: x.review ? `${x.review.by.name}${x.review.note ? ` — ${x.review.note}` : ''}` : '—',
    })),
  );

  // Opens the browser print dialog for this page (navigation is hidden in print); "Save as PDF" is available there.
  const handleDownload = (reportName: string) => {
    setToast(`Opening the print dialog for "${reportName}" — choose “Save as PDF” to export.`);
    setTimeout(() => {
      window.print();
      setToast(null);
    }, 300);
  };

  return (
    <div className="space-y-6">
      {toast && (
        <div role="status" className="print:hidden fixed bottom-6 right-6 z-50 bg-navy-900 text-white px-4 py-3 rounded-xl shadow-modal border border-teal-500/40 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-teal-400" />
          <span>{toast}</span>
        </div>
      )}

      <div className="bg-white p-5 rounded-2xl border border-surface-border shadow-subtle flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-navy-900 tracking-tight">Institutional & NEP Governance Reports</h1>
          <p className="text-xs text-content-secondary mt-0.5">
            Lost-period audits and recovery approvals from the shared planning workspace · classroom progress {progress.classroomPct}%
          </p>
        </div>
        <Badge variant="teal" size="sm">
          NEP 2020 Compliant Format
        </Badge>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <Card className="flex flex-col">
          <CardHeader title="School Competency Card" subtitle="Campus evaluation export" action={<Badge size="sm" variant="outline">Sample data</Badge>} />
          <CardBody className="flex-1 flex flex-col gap-3 text-xs">
            <p className="text-content-secondary leading-relaxed">
              Consolidated 4-dimensional score sheets (LU, CU, AU, CT) across all classes with year-on-year baseline deltas. Scores in this prototype come from seeded demonstration records, not school assessments.
            </p>
            <div className="mt-auto pt-3 border-t border-surface-border print:hidden">
              <Button variant="outline" size="sm" className="w-full" onClick={() => handleDownload('Campus Competency Summary')} icon={<Download className="w-3.5 h-3.5" />}>
                Print / save as PDF
              </Button>
            </div>
          </CardBody>
        </Card>

        <Card className="flex flex-col">
          <CardHeader title="Teaching Period Disruption Audit" subtitle="From approved plans — periods, not fabricated day counts" />
          <CardBody className="flex-1 flex flex-col gap-3 text-xs">
            <p className="text-content-secondary leading-relaxed">
              {progress.lostPeriodsRecorded === 0
                ? 'No lost periods recorded against approved Mathematics/Science plans yet.'
                : `${progress.lostPeriodsRecorded} lost period(s) across ${progress.plans.length} approved plan(s); ${progress.unaccountedLostPeriods} still await approved recovery. Academic Configuration working days are unchanged.`}
            </p>
            {lossRows.length > 0 && (
              <ul className="max-h-28 overflow-auto space-y-1 text-[11px]" data-testid="reports-loss-audit">
                {lossRows.map((r, i) => (
                  <li key={`${r.plan}-${r.date}-${i}`}>
                    {r.plan} · {r.date} · {r.periods} period(s) · {r.reason}
                    {r.note ? ` — “${r.note}”` : ''}
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-auto pt-3 border-t border-surface-border print:hidden">
              <Button variant="outline" size="sm" className="w-full" onClick={() => handleDownload('Instructional Period Loss Audit')} icon={<Download className="w-3.5 h-3.5" />}>
                Print / save as PDF
              </Button>
            </div>
          </CardBody>
        </Card>

        <Card className="flex flex-col">
          <CardHeader title="Recovery Approval Record" subtitle="Approved and rejected recovery decisions" />
          <CardBody className="flex-1 flex flex-col gap-3 text-xs">
            <p className="text-content-secondary leading-relaxed">
              {recoveryRows.length === 0
                ? 'No recovery proposals yet. Record lost periods or incomplete execution, then review in Curriculum Oversight.'
                : `${recoveryRows.length} recovery proposal(s) · ${recoveryRows.filter((r) => r.status === 'APPROVED').length} approved · ${recoveryRows.filter((r) => r.status === 'REJECTED').length} rejected · ${recoveryRows.filter((r) => r.status === 'PENDING').length} pending.`}
            </p>
            {recoveryRows.length > 0 && (
              <ul className="max-h-28 overflow-auto space-y-1 text-[11px]" data-testid="reports-recovery-audit">
                {recoveryRows.map((r, i) => (
                  <li key={`${r.plan}-${r.createdAt}-${i}`}>
                    {r.plan} · {r.createdAt} · {r.changes} change(s) · <b>{r.status.toLowerCase()}</b> · {r.review}
                  </li>
                ))}
              </ul>
            )}
            <Link className="text-teal-700 underline text-[11px] font-semibold" to="/principal/curriculum">
              Open Curriculum Oversight →
            </Link>
            <div className="mt-auto pt-3 border-t border-surface-border print:hidden">
              <Button variant="outline" size="sm" className="w-full" onClick={() => handleDownload('Recovery Approval Record')} icon={<Printer className="w-3.5 h-3.5" />}>
                Print / save as PDF
              </Button>
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
};
