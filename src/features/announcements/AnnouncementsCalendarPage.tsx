import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { CalendarDays, Megaphone, Plus, Trash2 } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { cn } from '../../lib/utils';
import { CalendarPage } from '../calendar/CalendarPage';
import { rangeLabel } from '../calendar/calendarModel';
import { AnnouncementComposer } from './AnnouncementComposer';
import {
  ANNOUNCEMENT_COLOR, SENDER_ROLES, announcementsApi, audienceLabel, postedLabel, useAnnouncements, type Announcement,
} from './announcementsModel';

const eventRange = (a: Announcement) => rangeLabel({ start: a.event_start as string, end: a.event_end || (a.event_start as string) } as any);

/** "Announcements & Calendar": announcements first, then the calendar underneath. */
export const AnnouncementsCalendarPage: React.FC = () => {
  const { currentUser } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const focusId = params.get('id');
  const { items, error, reload } = useAnnouncements();
  const [composing, setComposing] = useState(false);
  const [toast, setToast] = useState('');
  const [confirming, setConfirming] = useState<string | null>(null);
  const [actionError, setActionError] = useState('');
  // Bumped when an announcement is sent or removed, so the calendar below reloads its events too.
  const [calendarVersion, setCalendarVersion] = useState(0);
  const canSend = !!currentUser && SENDER_ROLES.includes(currentUser.role);

  // Arriving from a notification: bring that announcement into view.
  useEffect(() => {
    if (!focusId || !items) return;
    document.getElementById(`announcement-${focusId}`)?.scrollIntoView?.({ block: 'center', behavior: 'smooth' });
  }, [focusId, items]);

  async function remove(a: Announcement) {
    setActionError('');
    try {
      await announcementsApi.remove(a.id);
      setConfirming(null);
      reload();
      setCalendarVersion((v) => v + 1);
    } catch (err: any) {
      setActionError(err?.message || 'Could not remove this announcement.');
    }
  }

  return (
    <div className="space-y-8">
      <section aria-label="Announcements" className="space-y-4">
        <div className="flex flex-col gap-4 rounded-2xl border border-surface-border bg-gradient-to-r from-fuchsia-50 to-white p-5 shadow-subtle md:flex-row md:items-center md:justify-between">
          <div className="flex items-start gap-3">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-white" style={{ background: ANNOUNCEMENT_COLOR }}><Megaphone className="h-6 w-6" /></span>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-navy-900">Announcements &amp; Calendar</h1>
              <p className="mt-0.5 text-xs text-content-secondary">Messages from your school first, then the calendar of holidays, exams, deadlines and events.</p>
            </div>
          </div>
          {canSend && (
            <button type="button" onClick={() => setComposing(true)}
              className="inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white shadow-subtle hover:opacity-90" style={{ background: ANNOUNCEMENT_COLOR }}>
              <Plus className="h-4 w-4" />New announcement
            </button>
          )}
        </div>

        {toast && <p role="status" className="rounded-lg bg-fuchsia-50 px-3 py-2 text-sm font-semibold text-fuchsia-900">{toast}</p>}
        {actionError && <p role="alert" className="text-sm text-rose-700">{actionError}</p>}

        {error ? (
          <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error} <button type="button" onClick={reload} className="font-semibold underline">Retry</button></p>
        ) : items === null ? (
          <p role="status" className="text-sm text-content-secondary">Loading announcements…</p>
        ) : items.length === 0 ? (
          <p className="rounded-2xl border border-surface-border bg-white p-6 text-sm text-content-secondary shadow-subtle">No announcements yet.{canSend ? ' Use “New announcement” to send the first one.' : ''}</p>
        ) : (
          <ul className="space-y-3">
            {items.map((a) => (
              <li key={a.id} id={`announcement-${a.id}`}
                className={cn('overflow-hidden rounded-2xl border bg-white shadow-subtle', a.id === focusId ? 'border-fuchsia-500 ring-2 ring-fuchsia-300' : 'border-surface-border')}>
                <div className="flex">
                  <span aria-hidden="true" className="w-1.5 shrink-0" style={{ background: ANNOUNCEMENT_COLOR }} />
                  <div className="min-w-0 flex-1 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <h2 className="break-words text-sm font-semibold text-navy-900">{a.title}</h2>
                      <span className="shrink-0 text-xs text-content-muted">{postedLabel(a.created_at)}</span>
                    </div>
                    <p className="mt-0.5 text-xs text-content-secondary">From {a.sender_name}{a.sender_role ? ` (${a.sender_role})` : ''} · To {audienceLabel(a)}</p>
                    <p className="mt-2 whitespace-pre-wrap break-words text-sm text-navy-900">{a.content}</p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {a.event_start && (
                        <button type="button" onClick={() => navigate(`/calendar?date=${a.event_start}`)}
                          className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-semibold text-white hover:opacity-90" style={{ background: ANNOUNCEMENT_COLOR }}>
                          <CalendarDays className="h-3.5 w-3.5" />Event · {eventRange(a)}
                        </button>
                      )}
                      {a.can_delete && (confirming === a.id ? (
                        <span className="inline-flex items-center gap-1 text-xs">
                          <button type="button" onClick={() => remove(a)} className="rounded-md bg-rose-600 px-2 py-1 font-semibold text-white">Remove</button>
                          <button type="button" onClick={() => setConfirming(null)} className="rounded-md border border-surface-border px-2 py-1 font-semibold">Keep</button>
                        </span>
                      ) : (
                        <button type="button" onClick={() => setConfirming(a.id)} aria-label={`Remove ${a.title}`}
                          className="inline-flex items-center gap-1 rounded-md border border-surface-border px-2 py-1 text-xs font-semibold text-rose-700 hover:border-rose-400">
                          <Trash2 className="h-3 w-3" />Remove
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <CalendarPage key={calendarVersion} />

      <AnnouncementComposer
        isOpen={composing}
        onClose={() => setComposing(false)}
        onSent={(message) => { setComposing(false); setToast(message); reload(); setCalendarVersion((v) => v + 1); setTimeout(() => setToast(''), 6000); }}
      />
    </div>
  );
};

export default AnnouncementsCalendarPage;
