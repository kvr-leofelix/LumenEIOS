import React, { useEffect, useMemo, useState } from 'react';
import { useData } from '../../context/DataContext';
import { Card, CardBody } from '../../components/common/Card';
import { Badge } from '../../components/common/Badge';
import { SearchInput } from '../../components/common/SearchInput';
import { CATEGORY_LABEL, describeError, teacherPlanApi } from '../../lib/teacherPlanApi';
import { useStoreVersion } from '../../features/teacherPlan/requirementsStore';

interface Row {
  id: string;
  timestamp: string;
  /** Full-precision sort key (newest first, stable within the same minute). */
  sortKey: string;
  action: string;
  category: string;
  operator: string;
  details: string;
  source: 'planning' | 'sample';
}

export const AuditLogs: React.FC = () => {
  const { auditLogs } = useData();
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');

  // Planning events come from the central, append-only plan log (the same records as Central Logs); the earlier workspace
  // audit entries are history and are no longer read here. Sample/system rows are the platform's separate demo log.
  const [live, setLive] = useState<Row[]>([]);
  const [liveError, setLiveError] = useState('');
  const version = useStoreVersion();
  useEffect(() => {
    let cancelled = false;
    teacherPlanApi
      .logs({ limit: 200 })
      .then((r) => {
        if (cancelled) return;
        setLiveError('');
        setLive(r.items.map((e) => ({ id: e.id, timestamp: `${e.occurred_at.slice(0, 16).replace('T', ' ')} UTC`, sortKey: e.occurred_at.replace('T', ' '), action: CATEGORY_LABEL[e.category] ?? e.category, category: 'planning', operator: `${e.actor_name} (${e.actor_role})`, details: e.summary, source: 'planning' as const })));
      })
      .catch((err) => !cancelled && setLiveError(describeError(err).message));
    return () => {
      cancelled = true;
    };
  }, [version]);
  const rows = useMemo<Row[]>(() => {
    const sample: Row[] = auditLogs.map((l) => ({ id: l.id, timestamp: l.timestamp, sortKey: l.timestamp, action: l.action, category: l.category, operator: l.userName, details: l.details, source: 'sample' }));
    return [...live, ...sample].sort((a, b) => b.sortKey.localeCompare(a.sortKey));
  }, [live, auditLogs]);

  const q = search.toLowerCase();
  const filtered = rows.filter(
    (r) => (categoryFilter === 'all' || r.category === categoryFilter) && (!q || r.action.toLowerCase().includes(q) || r.details.toLowerCase().includes(q) || r.operator.toLowerCase().includes(q)),
  );
  const liveCount = rows.filter((r) => r.source === 'planning').length;

  return (
    <div className="space-y-6">
      <div className="bg-white p-5 rounded-2xl border border-surface-border shadow-subtle flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-navy-900 tracking-tight">Security & Pedagogical Audit Trail</h1>
          <p className="text-xs text-content-secondary mt-0.5">
            Append-only planning records (configuration, requirement approvals, schedules, lost periods and recovery decisions) with the authenticated actor, alongside seeded demonstration events.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 shrink-0">
          <Badge variant="teal" size="sm">
            {liveCount} planning record(s)
          </Badge>
          <Badge variant="outline" size="sm">
            {rows.length - liveCount} sample event(s)
          </Badge>
        </div>
      </div>

      {liveError && <p role="status" data-testid="planning-log-error" className="text-xs text-rose-700">Planning records could not be loaded ({liveError}). The Central Logs page reads the same records.</p>}

      <Card>
        <CardBody className="p-4 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 text-xs">
          <SearchInput value={search} onChange={setSearch} placeholder="Search action, details or operator..." className="sm:w-72" />
          <label className="flex items-center gap-2">
            <span className="font-semibold text-content-secondary">Category:</span>
            <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} aria-label="Audit category" className="px-3 py-1.5 bg-surface-bg border border-surface-border rounded-lg text-xs">
              <option value="all">All categories</option>
              <option value="planning">Curriculum planning (live records)</option>
              <option value="curriculum">Curriculum (sample)</option>
              <option value="assessment">Assessments & scans (sample)</option>
              <option value="system">System & campuses (sample)</option>
            </select>
          </label>
        </CardBody>
      </Card>

      <Card>
        <CardBody className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs" aria-label="Audit trail">
              <thead className="bg-surface-bg/80 text-content-secondary border-b border-surface-border">
                <tr>
                  <th className="py-3 px-4">Timestamp</th>
                  <th className="py-3 px-4">Action</th>
                  <th className="py-3 px-3">Source</th>
                  <th className="py-3 px-4">Operator</th>
                  <th className="py-3 px-4">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border bg-white">
                {filtered.map((r) => (
                  <tr key={r.id} className="hover:bg-surface-bg/40 transition-colors align-top">
                    <td className="py-3 px-4 font-mono text-content-muted whitespace-nowrap">{r.timestamp}</td>
                    <td className="py-3 px-4 font-semibold text-navy-900 min-w-[160px]">{r.action}</td>
                    <td className="py-3 px-3 whitespace-nowrap">
                      {r.source === 'planning' ? (
                        <Badge size="sm" variant="teal">
                          Planning workspace
                        </Badge>
                      ) : (
                        <Badge size="sm" variant="outline">
                          Sample · {r.category}
                        </Badge>
                      )}
                    </td>
                    <td className="py-3 px-4 text-teal-700 font-semibold min-w-[140px]">{r.operator}</td>
                    <td className="py-3 px-4 text-content-secondary leading-relaxed min-w-[240px]">{r.details}</td>
                  </tr>
                ))}
                {!filtered.length && (
                  <tr>
                    <td colSpan={5} className="py-8 px-4 text-center text-content-secondary">
                      {rows.length ? 'No audit entries match the current search or category.' : 'No audit entries yet.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>
    </div>
  );
};
