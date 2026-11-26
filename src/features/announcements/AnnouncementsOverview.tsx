import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, CalendarDays, Megaphone, Plus } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { cn } from '../../lib/utils';
import { friendlyDate } from '../calendar/calendarModel';
import { AnnouncementComposer } from './AnnouncementComposer';
import { ANNOUNCEMENT_COLOR, SENDER_ROLES, audienceLabel, postedLabel, useAnnouncements } from './announcementsModel';

/**
 * Dashboard card that sits next to the calendar: the latest announcements for this user, and (for principals and
 * teachers) a button to send a new one. The whole card opens the full Announcements & Calendar page.
 */
export const AnnouncementsOverview: React.FC<{ className?: string; limit?: number }> = ({ className, limit = 3 }) => {
  const navigate = useNavigate();
  const { currentUser } = useAuth();
  const { items, error, reload } = useAnnouncements();
  const [composing, setComposing] = useState(false);
  const [toast, setToast] = useState('');
  const canSend = !!currentUser && SENDER_ROLES.includes(currentUser.role);
  const latest = (items ?? []).slice(0, limit);
  const open = (id?: string) => navigate(id ? `/announcements?id=${id}` : '/announcements');

  return (
    <div className={cn('rounded-2xl border border-surface-border bg-white p-4 shadow-subtle', className)} data-testid="announcements-overview">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-navy-900">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg text-white" style={{ background: ANNOUNCEMENT_COLOR }}><Megaphone className="h-4 w-4" /></span>
          Announcements
        </h2>
        <div className="flex items-center gap-2">
          {canSend && (
            <button type="button" onClick={() => setComposing(true)}
              className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold text-white hover:opacity-90" style={{ background: ANNOUNCEMENT_COLOR }}>
              <Plus className="h-3.5 w-3.5" />New
            </button>
          )}
          <button type="button" onClick={() => open()} className="inline-flex items-center gap-1 text-xs font-semibold text-fuchsia-800 hover:underline">
            View all<ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {toast && <p role="status" className="mb-2 rounded-lg bg-fuchsia-50 px-3 py-1.5 text-xs font-semibold text-fuchsia-900">{toast}</p>}

      {error ? (
        <p className="text-xs text-content-secondary">Announcements are unavailable right now.</p>
      ) : items === null ? (
        <p role="status" className="text-xs text-content-secondary">Loading…</p>
      ) : latest.length === 0 ? (
        <p className="text-xs text-content-secondary">No announcements yet.</p>
      ) : (
        <ul className="space-y-2">
          {latest.map((a) => (
            <li key={a.id}>
              <button type="button" onClick={() => open(a.id)} className="block w-full rounded-lg border border-surface-border px-3 py-2 text-left hover:border-fuchsia-400">
                <span className="flex items-start justify-between gap-2">
                  <span className="min-w-0 truncate text-xs font-semibold text-navy-900">{a.title}</span>
                  <span className="shrink-0 text-[11px] text-content-muted">{postedLabel(a.created_at)}</span>
                </span>
                <span className="mt-0.5 line-clamp-2 block text-[11px] text-content-secondary">{a.content}</span>
                <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-content-muted">
                  <span>{a.sender_name} · {audienceLabel(a)}</span>
                  {a.event_start && (
                    <span className="inline-flex items-center gap-1 font-semibold" style={{ color: ANNOUNCEMENT_COLOR }}>
                      <CalendarDays className="h-3 w-3" />{friendlyDate(a.event_start)}
                    </span>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <AnnouncementComposer
        isOpen={composing}
        onClose={() => setComposing(false)}
        onSent={(message) => { setComposing(false); setToast(message); reload(); setTimeout(() => setToast(''), 5000); }}
      />
    </div>
  );
};

export default AnnouncementsOverview;
