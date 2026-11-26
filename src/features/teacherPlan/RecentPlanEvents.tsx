import React from 'react';
import { Link } from 'react-router-dom';
import { CATEGORY_LABEL, teacherPlanApi } from '../../lib/teacherPlanApi';
import { useRemote } from './useRemote';
import { useStoreVersion } from './requirementsStore';

/** The newest planning events, read from the same append-only records as the Central Logs page (no second audit trail). */
export const RecentPlanEvents: React.FC<{ limit?: number; filters?: Record<string, string | number> }> = ({ limit = 8, filters = {} }) => {
  const version = useStoreVersion();
  const { data, error } = useRemote(() => teacherPlanApi.logs({ ...filters, limit }), [limit, JSON.stringify(filters), version]);
  const query = new URLSearchParams(Object.entries(filters).map(([k, v]) => [k, String(v)])).toString();
  return (
    <div className="space-y-1" data-testid="recent-plan-events">
      {error && <p role="status" className="text-xs text-rose-700">{error}</p>}
      {data && data.items.length === 0 && <p className="text-content-secondary">No changes recorded yet.</p>}
      {data && data.items.length > 0 && (
        <ul className="space-y-0.5" aria-label="Recent planning events">
          {data.items.map((e) => (
            <li key={e.id}>
              {e.occurred_at.slice(0, 16).replace('T', ' ')} UTC · <b>{e.actor_name}</b> ({e.actor_role}) · {CATEGORY_LABEL[e.category] ?? e.category} · {e.summary}
            </li>
          ))}
        </ul>
      )}
      <Link className="text-xs font-semibold text-teal-700 underline" to={`/logs${query ? `?${query}` : ''}`}>Open in Central Logs →</Link>
    </div>
  );
};
