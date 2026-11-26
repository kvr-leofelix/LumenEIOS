import React, { useEffect, useState } from 'react';
import { Modal } from '../../components/common/Modal';
import { Button } from '../../components/common/Button';
import { cn } from '../../lib/utils';
import { todayIso } from '../calendar/calendarModel';
import { ANNOUNCEMENT_COLOR, AUDIENCE_LABEL, announcementsApi, type AudienceRole, type SendOptions } from './announcementsModel';

const MAX_BODY = 2000;
const ALL_GROUPS: AudienceRole[] = ['teacher', 'student', 'parent'];

function flip<T>(set: Set<T>, value: T): Set<T> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value); else next.add(value);
  return next;
}

/** Compose a broadcast: pick the groups (and classes), optionally mark it on the calendar as an event to attend. */
export const AnnouncementComposer: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  onSent: (message: string) => void;
}> = ({ isOpen, onClose, onSent }) => {
  const [options, setOptions] = useState<SendOptions | null>(null);
  const [loadError, setLoadError] = useState('');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [audience, setAudience] = useState<Set<AudienceRole>>(new Set());
  const [allClasses, setAllClasses] = useState(true);
  const [classIds, setClassIds] = useState<Set<string>>(new Set());
  const [onCalendar, setOnCalendar] = useState(false);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    let active = true;
    setLoadError('');
    announcementsApi.options()
      .then((o) => { if (active) setOptions(o); })
      .catch((err: any) => { if (active) setLoadError(err?.message || 'Could not load your sending options.'); });
    return () => { active = false; };
  }, [isOpen]);

  const reachesLearners = audience.has('student') || audience.has('parent');
  const isTeacherScope = options?.scope === 'classes you teach';
  const groups = options?.audiences ?? ALL_GROUPS;

  function reset() {
    setTitle(''); setContent(''); setAudience(new Set()); setAllClasses(true); setClassIds(new Set());
    setOnCalendar(false); setStart(''); setEnd(''); setError('');
  }
  function close() { reset(); onClose(); }

  async function submit(e?: React.FormEvent) {
    e?.preventDefault();
    setError('');
    if (!title.trim()) return setError('Add a short title.');
    if (!content.trim()) return setError('Write the message.');
    if (audience.size === 0) return setError('Choose at least one group to send this to.');
    if (reachesLearners && !allClasses && classIds.size === 0) return setError('Choose at least one class, or switch back to all classes.');
    if (onCalendar && !start) return setError('Pick the date of the event, or untick "Mark on the calendar".');
    if (onCalendar && end && end < start) return setError('The event ends before it starts.');
    setSending(true);
    try {
      const sent = await announcementsApi.create({
        title: title.trim(),
        content: content.trim(),
        audience: [...audience],
        class_ids: reachesLearners && !allClasses ? [...classIds] : undefined,
        event_start: onCalendar ? start : undefined,
        event_end: onCalendar && end && end !== start ? end : undefined,
      });
      const n = sent.recipients ?? 0;
      const withEvent = onCalendar;
      reset();
      onSent(`Announcement sent to ${n} ${n === 1 ? 'person' : 'people'}${withEvent ? ' and added to their calendars' : ''}.`);
    } catch (err: any) {
      setError(err?.message || 'Could not send the announcement.');
    } finally {
      setSending(false);
    }
  }

  const field = 'w-full rounded-lg border border-surface-border bg-white px-3 py-2 text-sm text-navy-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-fuchsia-500';

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title="New announcement"
      subtitle={options ? (isTeacherScope ? 'Reach other teachers, and the students and parents of your classes' : 'Reach teachers, students and parents of your school') : undefined}
      maxWidth="lg"
      footer={
        <div className="flex w-full items-center justify-end gap-2.5">
          <Button variant="secondary" size="md" onClick={close}>Cancel</Button>
          <button
            type="button"
            onClick={() => submit()}
            disabled={sending || !options}
            style={{ background: ANNOUNCEMENT_COLOR }}
            className="rounded-lg px-4 py-2 text-sm font-semibold text-white shadow-subtle hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {sending ? 'Sending…' : 'Send announcement'}
          </button>
        </div>
      }
    >
      <form onSubmit={submit} className="space-y-4 text-sm" noValidate>
        {loadError && <p role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{loadError}</p>}

        <div>
          <label htmlFor="ann-title" className="mb-1 block text-xs font-semibold text-navy-900">Title</label>
          <input id="ann-title" value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} className={field} placeholder="e.g. Annual Day rehearsal" />
        </div>
        <div>
          <label htmlFor="ann-body" className="mb-1 block text-xs font-semibold text-navy-900">Message</label>
          <textarea id="ann-body" rows={4} value={content} maxLength={MAX_BODY} onChange={(e) => setContent(e.target.value)} className={field} placeholder="What do people need to know?" />
          <p className="mt-0.5 text-right text-[11px] text-content-muted">{content.length}/{MAX_BODY}</p>
        </div>

        <fieldset>
          <legend className="mb-1.5 text-xs font-semibold text-navy-900">Send to</legend>
          <div className="flex flex-wrap items-center gap-2">
            {groups.map((role) => (
              <label key={role} className={cn('inline-flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-semibold',
                audience.has(role) ? 'border-fuchsia-600 bg-fuchsia-50 text-fuchsia-900' : 'border-surface-border text-navy-900 hover:border-fuchsia-400')}>
                <input type="checkbox" checked={audience.has(role)} onChange={() => setAudience(flip(audience, role))} className="accent-fuchsia-700" />
                {AUDIENCE_LABEL[role]}
              </label>
            ))}
            <button type="button" onClick={() => setAudience(new Set(groups))} className="rounded-lg px-2 text-xs font-semibold text-fuchsia-800 underline">Everyone</button>
          </div>
        </fieldset>

        {reachesLearners && options && (
          <fieldset className="rounded-lg bg-surface-bg p-3">
            <legend className="px-1 text-xs font-semibold text-navy-900">Which classes? <span className="font-normal text-content-secondary">(students and parents)</span></legend>
            <div className="flex flex-wrap gap-4 text-xs">
              <label className="inline-flex items-center gap-1.5">
                <input type="radio" name="ann-scope" checked={allClasses} onChange={() => setAllClasses(true)} className="accent-fuchsia-700" />
                {isTeacherScope ? 'All my classes' : 'Whole school'}
              </label>
              <label className="inline-flex items-center gap-1.5">
                <input type="radio" name="ann-scope" checked={!allClasses} onChange={() => setAllClasses(false)} className="accent-fuchsia-700" />
                Choose classes
              </label>
            </div>
            {!allClasses && (
              <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Classes">
                {options.classes.length === 0 && <p className="text-xs text-content-secondary">No classes available.</p>}
                {options.classes.map((c) => (
                  <label key={c.id} className={cn('inline-flex cursor-pointer items-center gap-1.5 rounded-md border px-2 py-1 text-xs',
                    classIds.has(c.id) ? 'border-fuchsia-600 bg-fuchsia-50 font-semibold text-fuchsia-900' : 'border-surface-border bg-white')}>
                    <input type="checkbox" checked={classIds.has(c.id)} onChange={() => setClassIds(flip(classIds, c.id))} className="accent-fuchsia-700" />
                    {c.name}
                  </label>
                ))}
              </div>
            )}
            {isTeacherScope && options.classes.length === 0 && (
              <p className="mt-2 text-xs text-rose-700">You have no classes assigned, so there are no students or parents to reach.</p>
            )}
          </fieldset>
        )}

        <div className="rounded-lg border border-surface-border p-3">
          <label className="inline-flex cursor-pointer items-center gap-2 text-xs font-semibold text-navy-900">
            <input type="checkbox" checked={onCalendar} onChange={(e) => setOnCalendar(e.target.checked)} className="accent-fuchsia-700" />
            Mark on the calendar as an event to attend
          </label>
          {onCalendar && (
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor="ann-start" className="mb-1 block text-xs font-semibold text-navy-900">Event date</label>
                <input id="ann-start" type="date" min={todayIso()} value={start} onChange={(e) => setStart(e.target.value)} className={field} />
              </div>
              <div>
                <label htmlFor="ann-end" className="mb-1 block text-xs font-semibold text-navy-900">Ends <span className="font-normal text-content-secondary">(optional)</span></label>
                <input id="ann-end" type="date" min={start || todayIso()} value={end} onChange={(e) => setEnd(e.target.value)} className={field} />
              </div>
            </div>
          )}
          <p className="mt-2 text-[11px] text-content-secondary">
            This only adds an entry to the calendar of the people you send it to. Holidays, working days and the Academic Config are never changed.
          </p>
        </div>

        {error && <p role="alert" className="text-xs font-semibold text-rose-700">{error}</p>}
      </form>
    </Modal>
  );
};

export default AnnouncementComposer;
