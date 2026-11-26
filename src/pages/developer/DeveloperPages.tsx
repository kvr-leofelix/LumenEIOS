import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { apiClient, ApiError } from '../../lib/apiClient';
import { UnauthorizedPage } from '../shared/UnauthorizedPage';

function Shell({ title, lede, children }: { title: string; lede: string; children: React.ReactNode }) {
  const { currentUser } = useAuth();
  if (currentUser?.role !== 'developer') return <UnauthorizedPage />;
  return (
    <div className="space-y-6">
      <div className="bg-white p-5 rounded-2xl border border-surface-border shadow-subtle">
        <h1 className="text-xl font-bold text-navy-900 tracking-tight">{title}</h1>
        <p className="text-xs text-content-secondary mt-0.5">{lede}</p>
      </div>
      {children}
    </div>
  );
}

function useLoad<T>(load: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const reload = () => {
    setError('');
    load().then(setData).catch((err) => {
      setError(err instanceof ApiError ? err.message : 'Could not load this page.');
    });
  };
  useEffect(() => { reload(); }, []);
  return { data, error, reload, setData };
}

const links = [
  ['/developer/health', 'Platform health', 'API, database, OCR model, and question model.'],
  ['/developer/gemini', 'Gemini model', 'Choose which Gemini model OCR and scan evaluation use.'],
  ['/developer/roster', 'Sample roster', 'Accounts that exist, and a confirmed reseed.'],
  ['/developer/flags', 'Feature flags', 'Hide a beta for one school.'],
  ['/developer/access', 'Access log', 'Every role switch from a developer session.'],
  ['/developer/framework', 'Competency framework', 'Publish the outcomes schools inherit.'],
  ['/developer/workshop', 'Model workshop', 'Preview OCR blocks and a competency question.'],
  ['/developer/quality', 'Data quality', 'Missing principals, teachers, parents, and outcomes.'],
  ['/developer/releases', 'Release notes', 'What to say in a live demonstration.'],
] as const;

export const DeveloperHome: React.FC = () => (
  <Shell title="Developer portal" lede="Operate the platform. School administration stays in the Management role.">
    <div className="grid sm:grid-cols-2 gap-3">
      {links.map(([path, title, lede]) => (
        <Link key={path} to={path} className="bg-white p-4 rounded-2xl border border-surface-border hover:border-teal-500">
          <p className="text-sm font-semibold text-navy-900">{title}</p>
          <p className="text-xs text-content-secondary mt-1">{lede}</p>
        </Link>
      ))}
    </div>
  </Shell>
);

export const PlatformHealth: React.FC = () => {
  const { data, error } = useLoad(() => apiClient.developer.health());
  return (
    <Shell title="Platform health" lede="These checks read configuration and the database. They do not call the vision model.">
      {error && <p role="alert" className="text-xs text-rose-600">{error}</p>}
      {data && (
        <div className="grid sm:grid-cols-2 gap-3">
          <Status title="API" value={data.api} detail={data.environment} />
          <Status title="Database" value={data.database} detail="Query succeeded" />
          <Status title="OCR" value={data.ocr.model} detail={`${data.ocr.stored_scans} stored scans`} />
          <Status title="Question model" value={data.question_model.provider} detail={data.question_model.model} />
        </div>
      )}
    </Shell>
  );
};

export const GeminiModel: React.FC = () => {
  const { data, error, setData } = useLoad(() => apiClient.developer.geminiModels());
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const choose = async (model: string) => {
    if (!data || model === data.current) return;
    setBusy(true);
    setMessage('');
    try {
      const saved = await apiClient.developer.setGeminiModel(model);
      setData({ ...data, current: saved.current });
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'The model was not changed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell title="Gemini model" lede="OCR and scan evaluation use the model selected here. The choice lasts until the API restarts.">
      {error && <p role="alert" className="text-xs text-rose-600">{error}</p>}
      {data && (
        <div className="bg-white p-4 rounded-2xl border border-surface-border space-y-2">
          <label className="block text-sm font-semibold text-navy-900" htmlFor="gemini-model">
            Available Gemini models
            <select
              id="gemini-model"
              value={data.current}
              disabled={busy}
              onChange={(event) => { void choose(event.target.value); }}
              className="mt-2 block w-full rounded-lg border border-surface-border bg-white px-3 py-2 text-sm font-normal"
            >
              {data.models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.label === model.id ? model.id : `${model.label} (${model.id})`}
                </option>
              ))}
            </select>
          </label>
          <p className="text-xs text-content-secondary">Current model: <span className="font-mono">{data.current}</span></p>
          {message && <p role="alert" className="text-xs text-rose-600">{message}</p>}
        </div>
      )}
    </Shell>
  );
};

function Status({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <div className="bg-white p-4 rounded-2xl border border-surface-border">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-content-secondary">{title}</p>
      <p className="mt-1 text-sm font-semibold text-navy-900 break-words">{value}</p>
      <p className="text-xs text-content-secondary mt-1">{detail}</p>
    </div>
  );
}

export const SampleRoster: React.FC = () => {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const { data, error } = useLoad(() => apiClient.developer.roster());
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const reseed = async () => {
    setBusy(true);
    setMessage('');
    try {
      await apiClient.developer.reseed(confirm.trim());
      logout();
      navigate('/login', { replace: true });
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Reseed did not run.');
      setBusy(false);
    }
  };

  return (
    <Shell title="Sample roster" lede="Passwords are the sample password. This list does not show password hashes.">
      {error && <p role="alert" className="text-xs text-rose-600">{error}</p>}
      {data && (
        <>
          <p className="text-xs text-navy-900">
            Root login <span className="font-mono">{data.root_login}</span> uses the password on the sign-in page.
            Sample accounts use <span className="font-mono">{data.sample_password}</span>.
          </p>
          <div className="bg-white rounded-2xl border border-surface-border overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-surface-bg/80 text-content-secondary">
                <tr>
                  <th className="py-3 px-4">Name</th>
                  <th className="py-3 px-4">Email</th>
                  <th className="py-3 px-4">Role</th>
                  <th className="py-3 px-4">School</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                {data.accounts.map((account: { id: string; name: string; email: string; role: string; school: string }) => (
                  <tr key={account.id}>
                    <td className="py-2.5 px-4">{account.name}</td>
                    <td className="py-2.5 px-4 font-mono">{account.email}</td>
                    <td className="py-2.5 px-4">{account.role}</td>
                    <td className="py-2.5 px-4">{account.school}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="bg-white p-4 rounded-2xl border border-surface-border space-y-2">
            <p className="text-sm font-semibold text-navy-900">Reseed sample schools</p>
            <p className="text-xs text-content-secondary">
              Replaces every row with the IIT Mandi roster and signs you out. A SQLite backup is written beside the database file.
            </p>
            <input
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              placeholder="Type reset"
              className="w-full sm:w-48 px-3 py-2 border border-surface-border rounded-lg text-sm"
            />
            <button
              type="button"
              disabled={busy || confirm.trim() !== 'reset'}
              onClick={() => void reseed()}
              className="block px-3 py-2 rounded-lg bg-navy-800 text-white text-xs font-semibold disabled:opacity-50"
            >
              {busy ? 'Reseeding…' : 'Reseed and sign out'}
            </button>
            {message && <p role="alert" className="text-xs text-rose-600">{message}</p>}
          </div>
        </>
      )}
    </Shell>
  );
};

type FlagSchool = { id: string; name: string; flags: Record<string, boolean> };
type FlagKey = { key: string; label: string };

export const FeatureFlags: React.FC = () => {
  const { data, error, setData } = useLoad(() => apiClient.developer.flags());
  const [message, setMessage] = useState('');

  const toggle = async (schoolId: string, key: string, enabled: boolean) => {
    setMessage('');
    try {
      await apiClient.developer.setFlag(schoolId, key, enabled);
      setData((current: { keys: FlagKey[]; schools: FlagSchool[] } | null) => current && ({
        ...current,
        schools: current.schools.map((school) => school.id === schoolId
          ? { ...school, flags: { ...school.flags, [key]: enabled } }
          : school),
      }));
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Could not save that flag.');
    }
  };

  return (
    <Shell title="Feature flags" lede="A school with a flag turned off no longer shows that beta. The developer session always keeps them available.">
      {error && <p role="alert" className="text-xs text-rose-600">{error}</p>}
      {message && <p role="alert" className="text-xs text-rose-600">{message}</p>}
      {data && (
        <div className="space-y-3">
          {data.schools.map((school: FlagSchool) => (
            <div key={school.id} className="bg-white p-4 rounded-2xl border border-surface-border">
              <p className="text-sm font-semibold text-navy-900">{school.name}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {data.keys.map((item: FlagKey) => {
                  const on = school.flags[item.key] !== false;
                  return (
                    <button
                      key={item.key}
                      type="button"
                      aria-pressed={on}
                      onClick={() => void toggle(school.id, item.key, !on)}
                      className={`px-3 py-1.5 rounded-full text-xs font-semibold border ${on ? 'bg-teal-50 text-teal-800 border-teal-200' : 'bg-surface-bg text-content-secondary border-surface-border'}`}
                    >
                      {item.label}: {on ? 'On' : 'Off'}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </Shell>
  );
};

export const AccessLog: React.FC = () => {
  const { data, error } = useLoad(() => apiClient.developer.access());
  return (
    <Shell title="Access log" lede="Recorded when this root session opens another role. The banner says Viewing as while that role is open.">
      {error && <p role="alert" className="text-xs text-rose-600">{error}</p>}
      {data && data.length === 0 && <p className="text-xs text-content-secondary">No role switches yet.</p>}
      {data && data.length > 0 && (
        <div className="bg-white rounded-2xl border border-surface-border overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-surface-bg/80 text-content-secondary">
              <tr>
                <th className="py-3 px-4">When</th>
                <th className="py-3 px-4">Who</th>
                <th className="py-3 px-4">From</th>
                <th className="py-3 px-4">To</th>
                <th className="py-3 px-4">School</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border">
              {data.map((event: { id: string; created_at: string; actor_name: string; from_role: string; to_role: string; school: string }) => (
                <tr key={event.id}>
                  <td className="py-2.5 px-4">{event.created_at}</td>
                  <td className="py-2.5 px-4">{event.actor_name}</td>
                  <td className="py-2.5 px-4">{event.from_role}</td>
                  <td className="py-2.5 px-4">{event.to_role}</td>
                  <td className="py-2.5 px-4">{event.school}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Shell>
  );
};

type Outcome = { id: string; code: string; domain: string; grade: number; statement: string; version: number };

export const CompetencyFramework: React.FC = () => {
  const { data, error, reload } = useLoad(() => apiClient.developer.framework());
  const [draft, setDraft] = useState({ code: '', domain: 'LU', grade: 6, statement: '' });
  const [message, setMessage] = useState('');

  const save = async (outcome: Outcome, statement: string) => {
    setMessage('');
    try {
      await apiClient.developer.saveOutcome(outcome.id, {
        code: outcome.code,
        domain: outcome.domain,
        grade: outcome.grade,
        statement,
      });
      reload();
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Could not publish that outcome.');
    }
  };

  const create = async () => {
    setMessage('');
    try {
      await apiClient.developer.createOutcome(draft);
      setDraft({ code: '', domain: 'LU', grade: 6, statement: '' });
      reload();
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Could not add that outcome.');
    }
  };

  return (
    <Shell title="Competency framework" lede="Learning, conceptual, application, and critical-thinking outcomes. Saving a statement publishes the next version.">
      {error && <p role="alert" className="text-xs text-rose-600">{error}</p>}
      {message && <p role="alert" className="text-xs text-rose-600">{message}</p>}
      <div className="space-y-3">
        {(data || []).map((outcome: Outcome) => (
          <OutcomeRow key={`${outcome.id}-${outcome.version}`} outcome={outcome} onSave={save} />
        ))}
      </div>
      <form
        className="bg-white p-4 rounded-2xl border border-surface-border grid sm:grid-cols-4 gap-2"
        onSubmit={(event) => { event.preventDefault(); void create(); }}
      >
        <input required value={draft.code} onChange={(event) => setDraft({ ...draft, code: event.target.value })} placeholder="Code" className="px-3 py-2 border border-surface-border rounded-lg text-sm" />
        <select value={draft.domain} onChange={(event) => setDraft({ ...draft, domain: event.target.value })} className="px-3 py-2 border border-surface-border rounded-lg text-sm">
          {['LU', 'CU', 'AU', 'CT'].map((domain) => <option key={domain}>{domain}</option>)}
        </select>
        <input required type="number" min={1} max={12} value={draft.grade} onChange={(event) => setDraft({ ...draft, grade: Number(event.target.value) })} className="px-3 py-2 border border-surface-border rounded-lg text-sm" />
        <input required value={draft.statement} onChange={(event) => setDraft({ ...draft, statement: event.target.value })} placeholder="Statement" className="px-3 py-2 border border-surface-border rounded-lg text-sm sm:col-span-3" />
        <button type="submit" className="px-3 py-2 rounded-lg bg-navy-800 text-white text-xs font-semibold">Add outcome</button>
      </form>
    </Shell>
  );
};

function OutcomeRow({ outcome, onSave }: { outcome: Outcome; onSave: (outcome: Outcome, statement: string) => Promise<void> }) {
  const [statement, setStatement] = useState(outcome.statement);
  return (
    <div className="bg-white p-4 rounded-2xl border border-surface-border">
      <p className="text-xs font-semibold text-navy-900">{outcome.code} · Grade {outcome.grade} · version {outcome.version}</p>
      <textarea value={statement} onChange={(event) => setStatement(event.target.value)} className="mt-2 w-full px-3 py-2 border border-surface-border rounded-lg text-sm" rows={2} />
      <button type="button" onClick={() => void onSave(outcome, statement)} className="mt-2 px-3 py-1.5 rounded-lg bg-navy-800 text-white text-xs font-semibold">Publish</button>
    </div>
  );
}

export const ModelWorkshop: React.FC = () => {
  const [kind, setKind] = useState<'ocr' | 'question'>('ocr');
  const [text, setText] = useState('');
  const [code, setCode] = useState('CU-6');
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');

  const run = async () => {
    setError('');
    try {
      setResult(await apiClient.developer.workshop({ kind, text, competency_code: code }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'The preview did not run.');
    }
  };

  return (
    <Shell title="Model workshop" lede="A sandbox that is not tied to a class. The preview is deterministic and does not call a hosted model.">
      <div className="bg-white p-4 rounded-2xl border border-surface-border space-y-3">
        <div className="flex gap-2">
          <button type="button" onClick={() => setKind('ocr')} className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${kind === 'ocr' ? 'bg-navy-800 text-white' : 'border border-surface-border'}`}>OCR blocks</button>
          <button type="button" onClick={() => setKind('question')} className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${kind === 'question' ? 'bg-navy-800 text-white' : 'border border-surface-border'}`}>Question</button>
        </div>
        {kind === 'question' && (
          <input value={code} onChange={(event) => setCode(event.target.value)} className="w-full sm:w-40 px-3 py-2 border border-surface-border rounded-lg text-sm" aria-label="Competency code" />
        )}
        <textarea value={text} onChange={(event) => setText(event.target.value)} rows={5} placeholder="Paste a line from a sheet, or a concept to turn into a question." className="w-full px-3 py-2 border border-surface-border rounded-lg text-sm" />
        <button type="button" onClick={() => void run()} className="px-3 py-2 rounded-lg bg-navy-800 text-white text-xs font-semibold">Run preview</button>
        {error && <p role="alert" className="text-xs text-rose-600">{error}</p>}
        {result && <pre className="text-xs bg-surface-bg p-3 rounded-lg overflow-x-auto">{JSON.stringify(result.result, null, 2)}</pre>}
      </div>
    </Shell>
  );
};

export const DataQuality: React.FC = () => {
  const { data, error } = useLoad(() => apiClient.developer.quality());
  return (
    <Shell title="Data quality" lede="Gaps across the school network. Management still sees a single school.">
      {error && <p role="alert" className="text-xs text-rose-600">{error}</p>}
      {data && (
        <div className="grid sm:grid-cols-2 gap-3">
          <Gap title="Schools missing a principal" rows={data.schools_missing_principal.map((row: { id: string; name: string }) => row.name)} />
          <Gap title="Classes missing a teacher" rows={data.classes_missing_teacher.map((row: { id: string; name: string; school: string }) => `${row.name} · ${row.school}`)} />
          <Gap title="Students missing a parent" rows={data.students_missing_parent.map((row: { id: string; name: string; school: string }) => `${row.name} · ${row.school}`)} />
          <Gap title="Subjects without an outcome at that grade" rows={data.subjects_without_outcome.map((row: { id: string; name: string; grade: number }) => `${row.name} · grade ${row.grade}`)} />
        </div>
      )}
    </Shell>
  );
};

function Gap({ title, rows }: { title: string; rows: string[] }) {
  return (
    <div className="bg-white p-4 rounded-2xl border border-surface-border">
      <p className="text-sm font-semibold text-navy-900">{title}</p>
      {rows.length === 0 ? <p className="text-xs text-content-secondary mt-2">None.</p> : (
        <ul className="mt-2 space-y-1 text-xs text-content-primary">
          {rows.map((row) => <li key={row}>{row}</li>)}
        </ul>
      )}
    </div>
  );
}

export const ReleaseNotes: React.FC = () => {
  const { data, error } = useLoad(() => apiClient.developer.releases());
  return (
    <Shell title="Release notes" lede="A short brief for the people in the room. Pair it with the Presentation theme.">
      {error && <p role="alert" className="text-xs text-rose-600">{error}</p>}
      <div className="space-y-3">
        {(data || []).map((note: { version: string; title: string; points: string[] }) => (
          <article key={note.version} className="bg-white p-4 rounded-2xl border border-surface-border">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-content-secondary">{note.version}</p>
            <h2 className="text-sm font-semibold text-navy-900 mt-1">{note.title}</h2>
            <ul className="mt-2 space-y-1 text-xs text-content-primary list-disc pl-4">
              {note.points.map((point) => <li key={point}>{point}</li>)}
            </ul>
          </article>
        ))}
      </div>
    </Shell>
  );
};
