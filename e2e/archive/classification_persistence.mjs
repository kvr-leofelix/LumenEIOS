// Classification persistence: a teacher's Core/Non-Core decision AND required periods survive calendar changes (holidays added, removed, repeated).
// Steps follow the acceptance brief: set a topic to mixed 3 Core + 1 Non-Core (and Core-only 4+0, Non-Core-only 0+4) in Course Curriculum, add holidays,
// verify, remove holidays, verify again. Auto-derived defaults are the control: THEY recalculate. Runs on a DISPOSABLE copy of the demo database.
//   GRADE=7 SUBJECT=Mathematics WEB_URL=http://127.0.0.1:5183 API_URL=http://127.0.0.1:8013/api/v1 SHOTS=./e2e-shots/persist node e2e/classification_persistence.mjs
import fs from 'node:fs';
import { WEB, api, assert, launch, shot } from '../lib.mjs';
const GR = Number(process.env.GRADE || 7), SUB = process.env.SUBJECT || 'Mathematics', SUBL = SUB.toLowerCase();
const { page, browser, version } = await launch();
const results = [];
const run = async (id, what, fn) => {
  try { const n = await fn(); results.push({ id, what, ok: true, note: n ?? '' }); console.log(`PASS ${id} ${what} ${n ?? ''}`); }
  catch (e) { const m = String(e.message).split('\n')[0].slice(0, 320); results.push({ id, what, ok: false, note: m }); console.log(`FAIL ${id} ${what}: ${m}`); await shot(page, `${id}_FAIL`); }
};
const login = async (email) => {
  await page.goto(`${WEB}/login`); await page.evaluate(() => localStorage.clear()); await page.goto(`${WEB}/login`);
  await page.locator('input').first().fill(email); await page.locator('input[type="password"]').fill('demo123');
  await page.getByRole('button', { name: /^Sign in/ }).click(); await page.waitForURL((u) => !u.pathname.includes('login'), { timeout: 20000 });
};
const tokenOf = async (email) => (await api('POST', '/auth/login', null, { email, password: 'demo123' })).json.access_token;
const TA = { email: 'teacher2a@lumeneios.demo', id: 'demo-plan-teacher-2a' }, PR = 'principal2@lumeneios.demo';
const tok = { [TA.email]: await tokenOf(TA.email), [PR]: await tokenOf(PR) };
const plan = async () => (await api('GET', `/teacher-plans/${TA.id}?grade=${GR}&subject=${SUB}`, tok[TA.email])).json;
const calendar = async () => (await api('GET', '/plan-calendar', tok[PR])).json;
const openCatalogue = async () => { await login(TA.email); await page.goto(`${WEB}/curriculum/catalogue/${GR}/${SUBL}`); await page.waitForSelector('[data-testid="plan-context"]', { timeout: 30000 }); await page.waitForSelector('[data-testid="teacher-plan-panel"]', { timeout: 30000 }); await page.getByText('Expand all').click(); };
const openAcademicConfig = async () => { await login(PR); await page.goto(`${WEB}/principal/academic-config`); await page.waitForSelector('[data-testid="available-time"]', { timeout: 30000 }); await page.getByLabel(/^Entry \d+ description$/).first().waitFor({ timeout: 30000 }); await page.waitForTimeout(800); };
const idxOf = async (label) => { const n = await page.getByLabel(/^Entry \d+ description$/).count(); for (let i = 1; i <= n; i++) if ((await page.getByLabel(`Entry ${i} description`).inputValue()) === label) return i; return 0; };
const addHoliday = async (label, from, to) => {
  await page.getByRole('button', { name: /Add holiday/ }).click(); const n = await page.getByLabel(/^Entry \d+ description$/).count(); let k = 0;
  for (let i = 1; i <= n; i++) if ((await page.getByLabel(`Entry ${i} description`).inputValue()) === '') k = i;
  await page.getByLabel(`Entry ${k} description`).fill(label); await page.getByLabel(`Entry ${await idxOf(label)} from`).fill(from); await page.getByLabel(`Entry ${await idxOf(label)} to`).fill(to);
};
const saveCalendar = async (reason) => { await page.getByLabel('Reason for the calendar change').fill(reason); await page.getByRole('button', { name: 'Save Academic Configuration' }).click(); await page.getByText(/Calendar version \d+ saved/).first().waitFor({ timeout: 30000 }); };
console.log('Browser', version, `| ${SUB} Class ${GR}`);
const want = { mixed: [3, 1], core: [4, 0], non_core: [0, 4] };
const picks = {};   // kind -> topic row (auto-derived, open) that the teacher sets through the UI
let control, samples;

await run('P0', 'the six demonstration samples are persisted teacher-specific configurations (origin teacher, written by system-demo-samples)', async () => {
  const p = await plan(); samples = p.topics.slice(0, 6);
  const kinds = samples.map((t) => `${t.classification}:${t.core_periods}+${t.non_core_periods}`).join(' ');
  assert(kinds === 'mixed:3+1 core:4+0 non_core:0+4 mixed:3+1 core:4+0 non_core:0+4' && samples.every((t) => t.origin === 'teacher'), kinds + ' / ' + samples.map((t) => t.origin));
  const logs = (await api('GET', `/plan-logs?teacher_id=${TA.id}&limit=300`, tok[PR])).json.items.filter((e) => e.actor_id === 'system-demo-samples');
  assert(logs.length >= 1, 'no audit event for the samples'); return kinds;
});
await run('P1', 'Course Curriculum: set a MIXED topic to 3 Core + 1 Non-Core, a CORE topic to 4 + 0, a NON-CORE topic to 0 + 4 (UI, Save requirements)', async () => {
  const p = await plan(); const auto = p.topics.filter((t) => t.origin === 'demo_default' && t.coverage === 'not_done');
  for (const kind of ['mixed', 'core', 'non_core']) picks[kind] = auto.find((t) => t.classification === kind && !Object.values(picks).includes(t)); for (const k of Object.keys(picks)) assert(picks[k], `no auto ${k} topic`);
  control = auto.find((t) => !Object.values(picks).includes(t));
  await openCatalogue();
  for (const [kind, t] of Object.entries(picks)) {
    await page.getByLabel(`Core periods ${t.section}`, { exact: true }).fill(String(want[kind][0])); await page.getByLabel(`Non-Core periods ${t.section}`, { exact: true }).fill(String(want[kind][1]));
  }
  await page.getByRole('button', { name: 'Save requirements' }).click(); await page.getByText('Requirements saved.').waitFor({ timeout: 20000 });
  const after = await plan();
  for (const [kind, t] of Object.entries(picks)) { const r = after.topics.find((x) => x.topic_key === t.topic_key); assert(r.classification === kind && r.core_periods === want[kind][0] && r.non_core_periods === want[kind][1] && r.origin === 'teacher', `${kind}: ${JSON.stringify(r)}`); }
  await shot(page, `P1_${SUBL}_teacher_set`); return 'mixed 3+1, core 4+0, non-core 0+4 saved with origin teacher';
});
const watched = () => [...samples, ...Object.values(picks)];
const snapshotRows = async () => { const p = await plan(); return Object.fromEntries(watched().map((t) => { const r = p.topics.find((x) => x.topic_key === t.topic_key); return [t.topic_key, `${r.classification}|${r.core_periods}|${r.non_core_periods}|${r.origin}`]; })); };
const expectedRows = async (ref) => { const now = await snapshotRows(); for (const k of Object.keys(ref)) assert(now[k] === ref[k], `teacher decision changed: ${k} ${ref[k]} -> ${now[k]}`); return Object.keys(ref).length; };
let ref, controlBefore, calV0, autoBefore, autoAfterAdd, autoAfterRemove;
const autoSum = async () => (await plan()).topics.filter((t) => t.origin === 'demo_default' && t.coverage !== 'done').reduce((s, t) => s + t.core_periods + t.non_core_periods, 0);
await run('P2', 'record the teacher decisions and an auto-derived control topic BEFORE any calendar change', async () => {
  ref = await snapshotRows(); const p = await plan(); const c = p.topics.find((x) => x.topic_key === control.topic_key); controlBefore = c.core_periods + c.non_core_periods; calV0 = (await calendar()).version; autoBefore = await autoSum();
  return `${Object.keys(ref).length} teacher-set topics watched (6 samples + 3 UI-set); auto-derived untaught topics total ${autoBefore} periods (control ${control.section}: ${controlBefore}); calendar v${calV0}`;
});
await run('P3', 'ADD three holidays in Academic Configuration and save: all teacher decisions unchanged, control recalculates', async () => {
  await openAcademicConfig(); for (const [l, f, t] of [['Persist holiday A', '2026-11-23', '2026-11-27'], ['Persist holiday B', '2027-01-25', '2027-01-29'], ['Persist holiday C', '2027-02-15', '2027-02-17']]) await addHoliday(l, f, t);
  await saveCalendar('Persistence check: holidays added'); await shot(page, `P3_${SUBL}_after_add`);
  assert((await calendar()).version === calV0 + 1, 'calendar not versioned'); const n = await expectedRows(ref);
  const now = await autoSum(); autoAfterAdd = now; assert(now < autoBefore, `auto-derived total did not shrink: ${autoBefore} -> ${now}`);
  return `${n} teacher decisions unchanged; auto-derived untaught total ${autoBefore} -> ${now} periods (recalculated to the shorter calendar)`;
});
await run('P4', 'REMOVE the holidays and save again: teacher decisions still unchanged, control recalculates back', async () => {
  await openAcademicConfig(); for (const l of ['Persist holiday A', 'Persist holiday B', 'Persist holiday C']) { const i = await idxOf(l); assert(i, `${l} missing`); await page.getByRole('button', { name: `Remove entry ${i}` }).click(); }
  await saveCalendar('Persistence check: holidays removed'); await shot(page, `P4_${SUBL}_after_remove`);
  const n = await expectedRows(ref); const now = await autoSum();
  autoAfterRemove = now; assert(now > autoAfterAdd, `capacity did not return: ${autoAfterAdd} -> ${now}`); return `${n} teacher decisions unchanged; auto-derived untaught total ${autoAfterAdd} -> ${now} (capacity restored)`;
});
await run('P5', 'repeat: add a 2-week closure then remove it; decisions still identical', async () => {
  await openAcademicConfig(); await addHoliday('Persist closure', '2026-12-07', '2026-12-18'); await saveCalendar('Persistence check: closure added'); const a = await expectedRows(ref); const mid = await autoSum(); assert(mid < autoAfterRemove, 'closure did not reduce capacity');
  await openAcademicConfig(); const i = await idxOf('Persist closure'); await page.getByRole('button', { name: `Remove entry ${i}` }).click(); await saveCalendar('Persistence check: closure removed'); const b = await expectedRows(ref); assert((await autoSum()) === autoAfterRemove, `round trip not exact: ${autoAfterRemove} -> ${await autoSum()}`);
  return `${a}/${b} decisions unchanged; auto-derived total ${autoAfterRemove} -> ${mid} -> ${autoAfterRemove} (exact round trip)`;
});
await run('P6', 'Time-Aware shows the same persisted classification and required periods after all calendar changes', async () => {
  await login(TA.email); await page.goto(`${WEB}/teacher/time-aware`); await page.waitForTimeout(2500); await page.getByLabel('Class').selectOption(String(GR)); await page.getByLabel('Subject').selectOption(SUB);
  await page.waitForSelector('[data-testid="plan-capacity-summary"]', { timeout: 30000 }); await page.waitForTimeout(1500);
  const WORD = { core: 'Core', mixed: 'Mixed', non_core: 'Non-Core' }; const reqText = (c, n) => (c && n ? `${c} Core + ${n} Non-Core` : c ? `${c} Core` : `${n} Non-Core`);
  for (const [kind, t] of Object.entries(picks)) { const cells = page.locator('tr', { hasText: t.section }).first().locator('td'); const cls = (await cells.nth(1).innerText()).trim(); const req = (await cells.nth(2).innerText()).trim(); assert(cls === WORD[kind] && req === reqText(...want[kind]), `${kind}: "${cls}" / "${req}"`); }
  await shot(page, `P6_${SUBL}_time_aware`); return 'Mixed: 3 Core + 1 Non-Core; Core: 4 Core; Non-Core: 4 Non-Core';
});
await run('P7', 'principal sees the same persisted teacher decisions (read-only teacher selector view)', async () => {
  await login(PR); await page.goto(`${WEB}/teacher/time-aware?teacher=${TA.id}`); await page.waitForTimeout(2500); await page.getByLabel('Class').selectOption(String(GR)); await page.getByLabel('Subject').selectOption(SUB);
  await page.waitForSelector('[data-testid="plan-capacity-summary"]', { timeout: 30000 }); await page.waitForTimeout(1500); const t = picks.mixed; const cells = page.locator('tr', { hasText: t.section }).first().locator('td'); const cls = (await cells.nth(1).innerText()).trim(), req = (await cells.nth(2).innerText()).trim();
  assert(cls === 'Mixed' && req === '3 Core + 1 Non-Core', `"${cls}" / "${req}"`); return 'principal view: Mixed 3 Core + 1 Non-Core for the same topic';
});
await browser.close();
fs.writeFileSync(process.env.REPORT || 'e2e-results-persistence.json', JSON.stringify(results, null, 1));
const bad = results.filter((r) => !r.ok); console.log(`\n${results.length - bad.length}/${results.length} passed`); process.exit(bad.length ? 1 : 0);
