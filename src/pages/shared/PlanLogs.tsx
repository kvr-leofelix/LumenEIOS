import React, { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useRemote } from '../../features/teacherPlan/useRemote';
import { CATEGORY_LABEL, teacherPlanApi } from '../../lib/teacherPlanApi';
import { inputCls, labelCls, PageHeader, selectCls, tdCls, thCls } from '../time-aware/planningUi';

const FILTERS = ['teacher_id', 'grade', 'subject', 'category', 'status', 'topic_key', 'date_from', 'date_to'] as const;

/** Central Logs. The same records back every module's contextual history link (/logs?topic_key=... etc.). */
export const PlanLogs: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const [open, setOpen] = useState<string | null>(null);
  const filters: Record<string, string> = Object.fromEntries(FILTERS.map((k) => [k, params.get(k) ?? '']));
  const { data, error, loading } = useRemote(() => teacherPlanApi.logs({ ...filters, limit: 200 }), [params.toString()]);
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
  };
  return (
    <div className="space-y-4" data-testid="plan-logs">
      <PageHeader title="Central Logs" subtitle="Append-only record of planning events for the selected school." />
      <div className="bg-white p-3 rounded-xl border border-surface-border grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
        <label>
          <span className={labelCls}>Category</span>
          <select aria-label="Category" className={`${selectCls} w-full`} value={filters.category} onChange={(e) => set('category', e.target.value)}>
            <option value="">All</option>
            {Object.entries(CATEGORY_LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className={labelCls}>Subject</span>
          <select aria-label="Subject" className={`${selectCls} w-full`} value={filters.subject} onChange={(e) => set('subject', e.target.value)}>
            <option value="">All</option>
            <option>Mathematics</option>
            <option>Science</option>
          </select>
        </label>
        <label>
          <span className={labelCls}>Class</span>
          <select aria-label="Class" className={`${selectCls} w-full`} value={filters.grade} onChange={(e) => set('grade', e.target.value)}>
            <option value="">All</option>
            <option value="6">VI</option>
            <option value="7">VII</option>
            <option value="8">VIII</option>
          </select>
        </label>
        <label>
          <span className={labelCls}>Teacher</span>
          <input aria-label="Teacher" className={inputCls} value={filters.teacher_id} placeholder="Teacher ID" onChange={(e) => set('teacher_id', e.target.value)} />
        </label>
        <label>
          <span className={labelCls}>From</span>
          <input aria-label="From date" type="date" className={inputCls} value={filters.date_from} onChange={(e) => set('date_from', e.target.value)} />
        </label>
        <label>
          <span className={labelCls}>To</span>
          <input aria-label="To date" type="date" className={inputCls} value={filters.date_to} onChange={(e) => set('date_to', e.target.value)} />
        </label>
        <label>
          <span className={labelCls}>Status</span>
          <input aria-label="Status" className={inputCls} value={filters.status} placeholder="recorded" onChange={(e) => set('status', e.target.value)} />
        </label>
        <label>
          <span className={labelCls}>Topic</span>
          <input aria-label="Topic" className={inputCls} value={filters.topic_key} placeholder="Topic key" onChange={(e) => set('topic_key', e.target.value)} />
        </label>
      </div>
      {error && (
        <p role="alert" className="text-xs text-rose-700">
          {error}
        </p>
      )}
      {loading && <p className="text-xs text-content-muted">Loading…</p>}
      {data && (
        <div className="bg-white rounded-xl border border-surface-border overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr>
                <th className={thCls}>When</th>
                <th className={thCls}>Category</th>
                <th className={thCls}>Event</th>
                <th className={thCls}>Actor</th>
              </tr>
            </thead>
            <tbody>
              {data.items.length === 0 && (
                <tr>
                  <td className={tdCls} colSpan={4}>
                    No events match these filters.
                  </td>
                </tr>
              )}
              {data.items.map((e) => (
                <React.Fragment key={e.id}>
                  <tr className="cursor-pointer hover:bg-surface-bg" onClick={() => setOpen(open === e.id ? null : e.id)} data-testid="log-row">
                    <td className={tdCls}>{e.occurred_at.slice(0, 16).replace('T', ' ')} UTC</td>
                    <td className={tdCls}>{CATEGORY_LABEL[e.category] ?? e.category}</td>
                    <td className={tdCls}>{e.summary}</td>
                    <td className={tdCls}>{e.actor_name}</td>
                  </tr>
                  {open === e.id && (
                    <tr data-testid="log-detail">
                      <td className={`${tdCls} bg-surface-bg`} colSpan={4}>
                        <dl className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-1">
                          {(
                            [
                              ['Teacher', e.teacher_id],
                              ['Class', e.grade],
                              ['Subject', e.subject],
                              ['Topics', e.topic_keys.join(', ')],
                              ['Reason', e.reason],
                              ['Schedule version', e.schedule_version],
                              ['Related event', e.related_event_id],
                              ['Proposal', e.related_proposal_id],
                            ] as [string, unknown][]
                          )
                            .filter(([, v]) => v !== null && v !== undefined && v !== '')
                            .map(([k, v]) => (
                              <div key={k}>
                                <dt className="text-content-muted">{k}</dt>
                                <dd>{String(v)}</dd>
                              </div>
                            ))}
                        </dl>
                        <pre className="mt-2 whitespace-pre-wrap text-[11px]">{JSON.stringify({ previous: e.previous_value, new: e.new_value }, null, 1)}</pre>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
          <p className="px-3 py-2 text-[11px] text-content-muted">{data.total} event(s)</p>
        </div>
      )}
    </div>
  );
};
