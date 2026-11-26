import { useCallback, useEffect, useState } from 'react';
import { apiRequest } from '../../lib/apiClient';

export type AudienceRole = 'teacher' | 'student' | 'parent';

export interface Announcement {
  id: string;
  school_id: string;
  sender_id: string;
  sender_name: string;
  sender_role: string | null;
  title: string;
  content: string;
  audience: AudienceRole[];
  /** null = every class the sender could reach (the whole school for a principal). */
  class_ids: string[] | null;
  class_names: string[];
  /** ISO dates; present when the announcement is marked on the calendar. */
  event_start: string | null;
  event_end: string | null;
  can_delete: boolean;
  recipients?: number;
  created_at: string;
}

export interface SendOptions {
  audiences: AudienceRole[];
  classes: { id: string; name: string }[];
  scope: string;
}

export interface AnnouncementInput {
  title: string;
  content: string;
  audience: AudienceRole[];
  class_ids?: string[];
  event_start?: string;
  event_end?: string;
}

/** One fixed colour for everything announcement-related (calendar chips, bell, cards). Deliberately not configurable. */
export const ANNOUNCEMENT_COLOR = '#A21CAF';

export const AUDIENCE_LABEL: Record<AudienceRole, string> = { teacher: 'Teachers', student: 'Students', parent: 'Parents' };

export const SENDER_ROLES = ['admin', 'principal', 'teacher'];

export const announcementsApi = {
  list: () => apiRequest<Announcement[]>('/announcements'),
  options: () => apiRequest<SendOptions>('/announcements/options'),
  create: (body: AnnouncementInput) => apiRequest<Announcement>('/announcements', { method: 'POST', body: JSON.stringify(body) }),
  remove: async (id: string) => {
    // DELETE answers 204 with no body, which the shared JSON helper cannot parse, so it is called directly.
    const base = ((import.meta as any).env?.VITE_API_URL || '/api/v1').replace(/\/+$/, '');
    const response = await fetch(`${base}/announcements/${id}`, {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${localStorage.getItem('lumeneios_token') ?? ''}`,
        'X-School-Id': localStorage.getItem('lumeneios_current_school') || 'school-1',
      },
    });
    if (!response.ok) throw new Error('Could not remove this announcement.');
  },
};

export function audienceLabel(a: Announcement): string {
  const who = a.audience.map((r) => AUDIENCE_LABEL[r]).join(', ');
  return a.class_names.length && a.audience.some((r) => r !== 'teacher') ? `${who} · ${a.class_names.join(', ')}` : who;
}

export function useAnnouncements() {
  const [items, setItems] = useState<Announcement[] | null>(null);
  const [error, setError] = useState('');
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let active = true;
    announcementsApi.list()
      .then((rows) => { if (active) { setItems(rows); setError(''); } })
      .catch((err: any) => { if (active) setError(err?.message || 'Could not load announcements.'); });
    return () => { active = false; };
  }, [nonce]);
  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { items, error, reload };
}

export function postedLabel(iso: string): string {
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}
