import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { CalendarDays, Clock, Plus, Save, Trash2 } from 'lucide-react';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import {
  AcademicConfig as Config,
  CalendarEntryType,
  ENTRY_TYPE_LABEL,
  PLANNING_SUBJECTS,
  REMOVES_WORKING_DAY,
  configDifferences,
  sameConfig,
  summarizeCalendar,
  validateConfig,
} from '../../lib/planning/calendar';
import { configChangedSinceApproval, newId, planLabel } from '../../lib/planning/execution';
import { usePlanning } from '../../lib/planning/usePlanning';
import { describeError, teacherPlanApi } from '../../lib/teacherPlanApi';
import { reloadCalendar } from '../../features/teacherPlan/calendarStore';
import { invalidateRequirements } from '../../features/teacherPlan/requirementsStore';
import { CalendarPreviewPanel } from '../../features/teacherPlan/CalendarImpact';
import { useAuth } from '../../context/AuthContext';
import { inputCls, labelCls, PageHeader, SectionCard, selectCls, Stat, StoreBanner, tdCls, thCls } from '../time-aware/planningUi';

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export const AcademicConfig: React.FC = () => {
  const p = usePlanning();
  const { workspace, isReviewer } = p;
  const { currentSchoolId } = useAuth();
  const [draft, setDraft] = useState<Config>(workspace.config);
  // The stored configuration this draft was started from. A save is refused if the stored value has moved on,
  // so a stale draft can never silently replace another user's newer configuration.
  const [base, setBase] = useState<Config>(workspace.config);
  const [touched, setTouched] = useState(false);
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [reason, setReason] = useState('');
  const [saveError, setSaveError] = useState('');
  // The calendar version this draft started from: a save is refused (409) if the school's calendar moved on since.
  const [baseVersion, setBaseVersion] = useState(p.calendarVersion);

  // Adopt the authoritative configuration once it loads, unless the user is mid-edit.
  useEffect(() => {
    if (!touched) {
      setDraft(workspace.config);
      setBase(workspace.config);
      setBaseVersion(p.calendarVersion);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace.config, touched]);

  const errors = useMemo(() => validateConfig(draft), [draft]);
  const summary = useMemo(() => (errors.length ? null : summarizeCalendar(draft)), [draft, errors]);
  const dirty = !sameConfig(draft, workspace.config);
  // Someone else saved a different configuration while this user has unsaved edits.
  const staleBase = touched && (!sameConfig(base, workspace.config) || baseVersion !== p.calendarVersion);

  if (!isReviewer) {
    return (
      <div className="space-y-6">
        <PageHeader title="Academic Configuration" subtitle="Requires Admin or Principal access." />
      </div>
    );
  }

  const set = (patch: Partial<Config>) => {
    setTouched(true);
    setMessage('');
    setDraft((d) => ({ ...d, ...patch }));
  };
  const setEntry = (id: string, patch: Partial<Config['entries'][number]>) => set({ entries: draft.entries.map((e) => (e.id === id ? { ...e, ...patch } : e)) });
  const addEntry = (type: CalendarEntryType) => set({ entries: [...draft.entries, { id: newId('cal'), type, label: '', start: draft.start, end: draft.start }] });

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (errors.length) {
      setMessage('Fix the validation problems before saving.');
      return;
    }
    const why = reason.trim() || (p.calendarVersion === 0 ? 'Initial academic calendar' : '');
    if (why.length < 3) {
      setSaveError('Give a reason for the calendar change (at least 3 characters).');
      return;
    }
    setSaving(true);
    setSaveError('');
    try {
      // The calendar is saved as a new version by the backend (validated, audited). The backend recalculates the remaining untaught allocations; taught periods, Done topics and classifications are kept.
      const res = await teacherPlanApi.saveCalendar({ config: draft, reason: why, expected_version: baseVersion });
      await reloadCalendar(currentSchoolId);
      invalidateRequirements();
      setTouched(false);
      setReason('');
      setMessage(
        `Calendar version ${res.version} saved. The remaining (untaught) syllabus was recalculated for ${res.plans_recalculated ?? 0} teacher plan(s) (${res.topics_changed ?? 0} topic allocation(s) changed); completed teaching and classifications were kept.${res.teachers_needing_review ? ` ${res.teachers_needing_review} plan(s) cannot fit the remaining syllabus: the shortfall is shown in their Time-Aware Engine.` : ''} Approved schedules keep their calendar snapshot until a recalculation is approved.`,
      );
    } catch (err) {
      const status = (err as { status?: number })?.status;
      if (status === 409) await reloadCalendar(currentSchoolId);
      setSaveError(status === 409 ? 'Not saved: a different Academic Configuration was saved while you were editing. Your edits are kept. Review the differences below, then keep your edits or discard them.' : describeError(err).message);
      setMessage('');
    }
    setSaving(false);
  };

  const keepMine = () => {
    setBase(workspace.config);
    setBaseVersion(p.calendarVersion);
    setSaveError('');
    p.clearError();
    setMessage('Your edits are now based on the latest saved configuration. Save to apply them.');
  };
  const discardMine = () => {
    setDraft(workspace.config);
    setBase(workspace.config);
    setTouched(false);
    setSaveError('');
    p.clearError();
    setMessage('Your unsaved edits were discarded; the latest saved configuration is shown.');
  };

  const affectedPlans = workspace.plans.filter((pl) => configChangedSinceApproval(pl, workspace.config));
  const num = (v: string) => (v === '' ? NaN : Number(v));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Academic Configuration"
        subtitle="One authoritative school calendar shared by Admin and Principal. Working and instructional days are calculated from it — nothing is assumed."
        badge={<Badge variant="teal" size="sm">{workspace.config.year}</Badge>}
        actions={
          <Link to="/teacher/time-aware" className="text-xs font-semibold text-teal-700 underline">
            Continue to Time-Aware Engine →
          </Link>
        }
      />
      <StoreBanner mode={p.mode} notice={p.notice} error={p.error} revision={p.revision} legacyPlans={p.legacyPlans} onDismiss={p.clearError} onRetry={p.reload} />

      {p.calendarError && (
        <div role="alert" data-testid="calendar-load-error" className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-900 flex items-center gap-3">
          <span>The school calendar could not be loaded ({p.calendarError}). Saving is disabled until it loads.</span>
          <Button type="button" size="sm" variant="outline" onClick={() => void reloadCalendar(currentSchoolId)}>Retry</Button>
        </div>
      )}

      {staleBase && (
        <div role="alert" data-testid="config-conflict" className="p-4 rounded-xl bg-amber-50 border border-amber-300 text-xs text-amber-950 space-y-2">
          <p className="font-bold">The saved configuration changed while you were editing.</p>
          <p>
            Revision {p.lastSaved.revision}
            {p.lastSaved.by ? ` saved by ${p.lastSaved.by}` : ''}
            {p.lastSaved.at ? ` at ${p.lastSaved.at.slice(0, 16).replace('T', ' ')}` : ''} changed: {configDifferences(base, workspace.config).join(', ') || 'no configuration fields'}.
          </p>
          <p>Your unsaved edits differ from it in: {configDifferences(draft, workspace.config).join(', ') || 'nothing (your draft matches the latest)'}.</p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="primary" onClick={keepMine}>
              Keep my edits and review before saving
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={discardMine}>
              Discard my edits and use the latest
            </Button>
          </div>
        </div>
      )}

      <form onSubmit={save} className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <SectionCard title="Academic year and school week" subtitle="Calendar boundaries and school working weekdays" action={<CalendarDays className="w-4 h-4 text-teal-600" />}>
            <div className="grid sm:grid-cols-3 gap-4">
              <label>
                <span className={labelCls}>Academic year</span>
                <input aria-label="Academic year" className={inputCls} value={draft.year} onChange={(e) => set({ year: e.target.value })} />
              </label>
              <label>
                <span className={labelCls}>Calendar start</span>
                <input aria-label="Calendar start" type="date" className={inputCls} value={draft.start} onChange={(e) => set({ start: e.target.value })} />
              </label>
              <label>
                <span className={labelCls}>Calendar end</span>
                <input aria-label="Calendar end" type="date" className={inputCls} value={draft.end} onChange={(e) => set({ end: e.target.value })} />
              </label>
            </div>
            <fieldset>
              <legend className={labelCls}>School working weekdays</legend>
              <div className="flex flex-wrap gap-2">
                {WEEKDAYS.map((name, i) => (
                  <label key={name} className={`px-3 py-1.5 rounded-lg border cursor-pointer ${draft.weekdays.includes(i) ? 'bg-teal-50 border-teal-300 text-teal-800' : 'bg-white border-surface-border'}`}>
                    <input
                      type="checkbox"
                      className="mr-1.5"
                      checked={draft.weekdays.includes(i)}
                      onChange={(e) => set({ weekdays: e.target.checked ? [...draft.weekdays, i].sort() : draft.weekdays.filter((d) => d !== i) })}
                    />
                    {name}
                  </label>
                ))}
              </div>
            </fieldset>
          </SectionCard>

          <SectionCard title="Holidays, vacations, examinations and events" subtitle="Holidays and vacations remove working days. Examinations and events keep school open but remove teaching time.">
            <div className="flex flex-wrap gap-2">
              {(Object.keys(ENTRY_TYPE_LABEL) as CalendarEntryType[]).map((t) => (
                <Button key={t} type="button" size="sm" variant="outline" icon={<Plus className="w-3.5 h-3.5" />} onClick={() => addEntry(t)}>
                  Add {ENTRY_TYPE_LABEL[t].toLowerCase()}
                </Button>
              ))}
            </div>
            {draft.entries.length ? (
              <div className="overflow-x-auto border border-surface-border rounded-xl">
                <table className="w-full table-fixed min-w-[640px]">
                  <colgroup>
                    <col className="w-40" />
                    <col />
                    <col className="w-36" />
                    <col className="w-36" />
                    <col className="w-10" />
                  </colgroup>
                  <thead>
                    <tr>
                      {['Type / effect', 'Description', 'From', 'To', ''].map((h) => (
                        <th key={h} className={thCls}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {draft.entries.map((en, i) => (
                      <tr key={en.id}>
                        <td className={tdCls}>
                          <select aria-label={`Entry ${i + 1} type`} className={`${selectCls} w-full`} value={en.type} onChange={(e) => setEntry(en.id, { type: e.target.value as CalendarEntryType })}>
                            {(Object.keys(ENTRY_TYPE_LABEL) as CalendarEntryType[]).map((t) => (
                              <option key={t} value={t}>
                                {ENTRY_TYPE_LABEL[t]}
                              </option>
                            ))}
                          </select>
                          <span className="block mt-1 text-[10px] text-content-muted">{REMOVES_WORKING_DAY[en.type] ? 'Not a working day' : 'Working, non-instructional'}</span>
                        </td>
                        <td className={tdCls}>
                          <input aria-label={`Entry ${i + 1} description`} className={inputCls} value={en.label} placeholder="e.g. Diwali break" onChange={(e) => setEntry(en.id, { label: e.target.value })} />
                        </td>
                        <td className={tdCls}>
                          <input aria-label={`Entry ${i + 1} from`} type="date" className={inputCls} value={en.start} onChange={(e) => setEntry(en.id, { start: e.target.value, end: en.end < e.target.value ? e.target.value : en.end })} />
                        </td>
                        <td className={tdCls}>
                          <input aria-label={`Entry ${i + 1} to`} type="date" className={inputCls} value={en.end} onChange={(e) => setEntry(en.id, { end: e.target.value })} />
                        </td>
                        <td className={tdCls}>
                          <button type="button" aria-label={`Remove entry ${i + 1}`} className="text-rose-600" onClick={() => set({ entries: draft.entries.filter((x) => x.id !== en.id) })}>
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-content-secondary">No holidays, vacations, examinations or events entered yet.</p>
            )}
          </SectionCard>

          <SectionCard title="Periods and planning horizon" subtitle="Timetable structure used to calculate available instructional time" action={<Clock className="w-4 h-4 text-teal-600" />}>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <label>
                <span className={labelCls}>Periods per school day</span>
                <input aria-label="Periods per school day" type="number" className={inputCls} value={Number.isNaN(draft.periodsPerDay) ? '' : draft.periodsPerDay} onChange={(e) => set({ periodsPerDay: num(e.target.value) })} />
              </label>
              <label>
                <span className={labelCls}>Period duration (minutes)</span>
                <input aria-label="Period duration (minutes)" type="number" className={inputCls} value={Number.isNaN(draft.periodMinutes) ? '' : draft.periodMinutes} onChange={(e) => set({ periodMinutes: num(e.target.value) })} />
              </label>
              {PLANNING_SUBJECTS.map((s) => (
                <label key={s}>
                  <span className={labelCls}>{s} periods per instructional day</span>
                  <input
                    aria-label={`${s} periods per instructional day`}
                    type="number"
                    className={inputCls}
                    value={Number.isNaN(draft.subjectPeriodsPerDay[s]) ? '' : draft.subjectPeriodsPerDay[s]}
                    onChange={(e) => set({ subjectPeriodsPerDay: { ...draft.subjectPeriodsPerDay, [s]: num(e.target.value) } })}
                  />
                </label>
              ))}
              <label>
                <span className={labelCls}>Curriculum planning horizon (instructional days)</span>
                <input
                  aria-label="Curriculum planning horizon"
                  type="number"
                  className={inputCls}
                  placeholder="All instructional days"
                  value={draft.horizonDays ?? ''}
                  onChange={(e) => set({ horizonDays: e.target.value === '' ? null : num(e.target.value) })}
                />
                <span className="text-[11px] text-content-muted">Leave blank to plan across every instructional day.</span>
              </label>
            </div>
          </SectionCard>
        </div>

        <div className="space-y-6">
          <SectionCard title="Calculated calendar" subtitle="Updates as you edit">
            {summary ? (
              <div className="grid grid-cols-2 gap-3">
                <Stat label="Calendar days" value={summary.calendarDays} />
                <Stat label="School working days" value={summary.workingDates.length} tone="indigo" hint="Weekdays minus holidays/vacations" />
                <Stat label="Instructional days" value={summary.instructionalDates.length} tone="teal" hint="Working days minus exams/events" />
                <Stat label="Planning horizon" value={summary.planningDates.length} hint="Instructional days planned" />
                <Stat label="Holiday days" value={summary.countsByType.HOLIDAY + summary.countsByType.VACATION} tone="amber" hint={`${summary.countsByType.VACATION} vacation`} />
                <Stat label="Exam / event days" value={summary.countsByType.EXAM + summary.countsByType.EVENT} tone="amber" />
                <div className="col-span-2 p-3 rounded-xl border border-surface-border bg-surface-bg space-y-1" data-testid="available-time">
                  <p className="font-semibold text-navy-900">Available instructional time</p>
                  <p>School: {Math.round(summary.schoolInstructionalMinutes / 60)} h ({summary.instructionalDates.length} days × {draft.periodsPerDay} × {draft.periodMinutes} min)</p>
                  {PLANNING_SUBJECTS.map((s) => (
                    <p key={s}>
                      {s}: {summary.subjectAvailablePeriods[s]} periods = {Math.round(summary.subjectAvailableMinutes[s] / 60)} h in the horizon
                    </p>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-content-secondary">Calendar figures appear once the configuration is valid.</p>
            )}
          </SectionCard>

          <SectionCard title="Effect on annual allocations" subtitle="Preview computed by the backend; nothing is saved by looking">
            <CalendarPreviewPanel config={draft} valid={!errors.length} dirty={dirty} />
          </SectionCard>

          <SectionCard title="Validation">
            {errors.length ? (
              <ul className="space-y-1 text-rose-800" aria-label="Configuration problems">
                {errors.map((er) => (
                  <li key={er} className="bg-rose-50 border border-rose-200 rounded-lg px-3 py-1.5">
                    {er}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-emerald-700">Configuration is valid.</p>
            )}
            {p.calendarVersion > 0 && (
              <label className="block">
                <span className={labelCls}>Reason for the change</span>
                <input aria-label="Reason for the calendar change" className={inputCls} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Timetable revised" />
              </label>
            )}
            <Button type="submit" variant="teal" className="w-full" disabled={!!errors.length || saving || !!p.calendarError || staleBase || (!dirty && workspace.configHistory.length > 0)} loading={saving} icon={<Save className="w-4 h-4" />}>
              Save Academic Configuration
            </Button>
            {saveError && <p role="alert" data-testid="calendar-save-error" className="text-rose-700">{saveError}</p>}
            {!dirty && !message && <p className="text-content-muted text-[11px]">No unsaved changes.</p>}
            <p role="status" className="text-teal-800">
              {message}
            </p>
          </SectionCard>

          {affectedPlans.length > 0 && (
            <SectionCard title="Plans using an earlier calendar">
              <ul className="space-y-1">
                {affectedPlans.map((pl) => (
                  <li key={pl.id}>{planLabel(pl)} — recalculate from the Time-Aware Engine; the change applies only after approval.</li>
                ))}
              </ul>
            </SectionCard>
          )}

          <SectionCard title="Save history" subtitle="Every saved configuration is retained">
            {workspace.configHistory.length ? (
              <ul className="space-y-1">
                {[...workspace.configHistory].reverse().slice(0, 8).map((h) => (
                  <li key={h.savedAt} className="text-[11px]">
                    {h.savedAt.slice(0, 16).replace('T', ' ')} · {h.savedBy.name} ({h.savedBy.role}) · {h.config.year}, {h.config.entries.length} calendar entr{h.config.entries.length === 1 ? 'y' : 'ies'}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-content-secondary">Not saved yet — the values shown are the default timetable (2 Mathematics + 2 Science periods per instructional day).</p>
            )}
          </SectionCard>
        </div>
      </form>
    </div>
  );
};
