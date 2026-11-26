/** Announcements: composer rules, dashboard card, and the "announcements first, then calendar" page. */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const request = vi.fn();
let role = 'principal';
vi.mock('../../../lib/apiClient', async (orig) => ({ ...(await orig<typeof import('../../../lib/apiClient')>()), apiRequest: (...a: unknown[]) => request(...a) }));
vi.mock('../../../context/AuthContext', () => ({ useAuth: () => ({ currentUser: { id: 'u1', role, name: 'Sender' } }) }));

import { AnnouncementComposer } from '../AnnouncementComposer';
import { AnnouncementsOverview } from '../AnnouncementsOverview';
import { AnnouncementsCalendarPage } from '../AnnouncementsCalendarPage';
import { CATEGORY_META } from '../../calendar/calendarModel';
import { ANNOUNCEMENT_COLOR, type Announcement } from '../announcementsModel';

const ann = (over: Partial<Announcement> = {}): Announcement => ({
  id: 'a1', school_id: 's1', sender_id: 'p1', sender_name: 'Dr. Rao', sender_role: 'principal', title: 'Annual Day',
  content: 'Please attend the rehearsal.', audience: ['student', 'parent'], class_ids: null, class_names: [],
  event_start: '2099-01-10', event_end: null, can_delete: true, created_at: '2026-11-20T10:00:00', ...over,
});
const feed = { start: '2099-01-01', end: '2099-02-01', events: [], meta: { schools: [], session_start: null, session_end: null, working_weekdays: [1, 2, 3, 4, 5] } };

beforeEach(() => {
  role = 'principal';
  request.mockReset();
  request.mockImplementation(async (url: string, opts?: RequestInit) => {
    if (url === '/announcements/options') return { audiences: ['teacher', 'student', 'parent'], classes: [{ id: 'c1', name: 'Class 7-A' }], scope: 'whole school' };
    if (url === '/announcements' && opts?.method === 'POST') return { ...ann(), recipients: 7 };
    if (url === '/announcements') return [ann()];
    if (url.startsWith('/calendar/events')) return feed;
    return {};
  });
});
afterEach(cleanup);

describe('announcement colour', () => {
  it('is one fixed colour shared by the calendar and announcements', () => {
    expect(CATEGORY_META.announcement.color).toBe(ANNOUNCEMENT_COLOR);
    const others = Object.entries(CATEGORY_META).filter(([k]) => k !== 'announcement').map(([, v]) => v.color);
    expect(others).not.toContain(ANNOUNCEMENT_COLOR);
  });
});

describe('composer', () => {
  const open = async (onSent = vi.fn()) => {
    render(<AnnouncementComposer isOpen onClose={() => undefined} onSent={onSent} />);
    await screen.findByLabelText('Teachers');
    return onSent;
  };

  it('needs a group before it will send', async () => {
    await open();
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Hello' } });
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'World' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send announcement' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Choose at least one group');
    expect(request).not.toHaveBeenCalledWith('/announcements', expect.objectContaining({ method: 'POST' }));
  });

  it('sends the chosen groups and the calendar event', async () => {
    const onSent = await open();
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Annual Day' } });
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'Please attend' } });
    fireEvent.click(screen.getByLabelText('Parents'));
    fireEvent.click(screen.getByLabelText('Teachers'));
    fireEvent.click(screen.getByLabelText(/Mark on the calendar/));
    fireEvent.change(screen.getByLabelText('Event date'), { target: { value: '2099-01-10' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send announcement' }));
    await waitFor(() => expect(onSent).toHaveBeenCalled());
    const post = request.mock.calls.find(([u, o]) => u === '/announcements' && o?.method === 'POST')!;
    expect(JSON.parse(post[1].body)).toEqual({ title: 'Annual Day', content: 'Please attend', audience: ['parent', 'teacher'], event_start: '2099-01-10' });
    expect(onSent.mock.calls[0][0]).toContain('7 people');
  });

  it('asks for a date when the calendar option is on', async () => {
    await open();
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'T' } });
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'M' } });
    fireEvent.click(screen.getByLabelText('Students'));
    fireEvent.click(screen.getByLabelText(/Mark on the calendar/));
    fireEvent.click(screen.getByRole('button', { name: 'Send announcement' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Pick the date of the event');
  });
});

describe('dashboard card and page', () => {
  it('lists the latest announcement with its event date; staff get a New button, learners do not', async () => {
    render(<MemoryRouter><AnnouncementsOverview /></MemoryRouter>);
    expect(await screen.findByText('Annual Day')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /New/ })).toBeInTheDocument();
    cleanup();
    role = 'student';
    render(<MemoryRouter><AnnouncementsOverview /></MemoryRouter>);
    await screen.findByText('Annual Day');
    expect(screen.queryByRole('button', { name: /New/ })).toBeNull();
  });

  it('shows announcements before the calendar', async () => {
    render(<MemoryRouter><AnnouncementsCalendarPage /></MemoryRouter>);
    const heading = await screen.findByRole('heading', { name: 'Announcements & Calendar' });
    const calendar = await screen.findByRole('region', { name: 'Calendar' });
    expect(await screen.findByText('Please attend the rehearsal.')).toBeInTheDocument();
    expect(heading.compareDocumentPosition(calendar) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText('Please attend the rehearsal.').compareDocumentPosition(calendar) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
