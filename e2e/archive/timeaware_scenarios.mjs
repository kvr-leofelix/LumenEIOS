// Scenarios A-F: Core/Non-Core consistency between Course Curriculum and Time-Aware, 2+2 defaults, holiday add/remove recalculation,
// insufficient capacity. Runs against a DISPOSABLE COPY of the seeded demo database (school-2: Principal + two teachers).
//   WEB_URL=http://127.0.0.1:5183 API_URL=http://127.0.0.1:8013/api/v1 SHOTS=./e2e-shots/scenarios node e2e/timeaware_scenarios.mjs
// UI actions in Edge (Playwright); every outcome is read back from the API; capacity arithmetic is recomputed here independently.
import fs from 'node:fs';
import { API, WEB, api, assert, launch, shot } from '../lib.mjs';

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
const tokenOf = async (email) => { const r = await api('POST', '/auth/login', null, { email, password: 'demo123' }); assert(r.status === 200, `login ${email} ${r.status}`); return r.json.access_token; };
const TA = { email: 'teacher2a@lumeneios.demo', id: 'demo-plan-teacher-2a' }, TB = { email: 'teacher2b@lumeneios.demo', id: 'demo-plan-teacher-2b' }, PR = 'principal2@lumeneios.demo';
const tok = {}; for (const e of [TA.email, TB.email, PR]) tok[e] = await tokenOf(e);
const plan = async (t, g = GR, s = SUB) => (await api('GET', `/teacher-plans/${t.id}?grade=${g}&subject=${s}`, tok[t.email])).json;
const calendar = async () => (await api('GET', '/plan-calendar', tok[PR])).json;
const expectedP = (cfg, subject) => {  // independent re-implementation: weekdays minus every calendar entry, times periods per day
  const blocked = new Set(); for (const e of cfg.entries) for (let d = new Date(e.start + 'T00:00:00Z'); d <= new Date(e.end + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + 1)) blocked.add(d.toISOString().slice(0, 10));
  let days = 0; for (let d = new Date(cfg.start + 'T00:00:00Z'); d <= new Date(cfg.end + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + 1)) { if (cfg.weekdays.includes(d.getUTCDay()) && !blocked.has(d.toISOString().slice(0, 10))) days += 1; }
  const per = cfg.subjectPeriodsPerDay[subject]; const P = days * per, R = Math.ceil(P / 10); return { days, per, P, R, T: P - R };
};
const TODAY = new Date().toLocaleDateString('sv-SE');  // the planning date: the server's current date (same machine)
const windowOf = (cfg, subject) => {  // periods on instructional days STRICTLY AFTER today, own 10% reserve
  const blocked = new Set(); for (const e of cfg.entries) for (let d = new Date(e.start + 'T00:00:00Z'); d <= new Date(e.end + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + 1)) blocked.add(d.toISOString().slice(0, 10));
  let days = 0; for (let d = new Date(cfg.start + 'T00:00:00Z'); d <= new Date(cfg.end + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + 1)) { const iso = d.toISOString().slice(0, 10); if (iso > TODAY && cfg.weekdays.includes(d.getUTCDay()) && !blocked.has(iso)) days += 1; }
  const P = days * cfg.subjectPeriodsPerDay[subject], R = Math.ceil(P / 10); return { days, P, R, T: P - R };
};
const text = async () => (await page.innerText('body')).replace(/\s+/g, ' ');
const openTimeAware = async (email, g = GR, s = SUB, q = '') => {
  await login(email); await page.goto(`${WEB}/teacher/time-aware${q}`); await page.waitForTimeout(2500);
  await page.getByLabel('Class').selectOption(String(g)); await page.getByLabel('Subject').selectOption(s);
  await page.waitForSelector('[data-testid="plan-capacity-summary"]', { timeout: 30000 }); await page.waitForTimeout(1500);
};
const openAcademicConfig = async () => {
  await login(PR); await page.goto(`${WEB}/principal/academic-config`); await page.waitForSelector('[data-testid="available-time"]', { timeout: 30000 });
  await page.getByLabel(/^Entry \d+ description$/).first().waitFor({ timeout: 30000 }); await page.waitForTimeout(800); // the saved calendar has loaded
};
const idxOf = async (label) => { const n = await page.getByLabel(/^Entry \d+ description$/).count(); for (let i = 1; i <= n; i++) if ((await page.getByLabel(`Entry ${i} description`).inputValue()) === label) return i; return 0; };
const addEntry = async (button, label, from, to) => {  // rows may re-sort when dates change, so each row is found again by its unique description
  await page.getByRole('button', { name: button }).click();
  const n = await page.getByLabel(/^Entry \d+ description$/).count(); let k = 0;
  for (let i = 1; i <= n; i++) if ((await page.getByLabel(`Entry ${i} description`).inputValue()) === '') k = i;
  assert(k, 'new entry row not found'); await page.getByLabel(`Entry ${k} description`).fill(label);
  await page.getByLabel(`Entry ${await idxOf(label)} from`).fill(from); await page.getByLabel(`Entry ${await idxOf(label)} to`).fill(to);
};
const cap = async (name) => Number((await page.getByTestId(`cap-${name}`).first().innerText()).trim());
const rowFor = (section) => page.locator('tr', { hasText: section }).first();
const CLASS_WORD = { core: 'Core', mixed: 'Mixed', non_core: 'Non-Core' };
const reqText = (c, n) => (c && n ? `${c} Core + ${n} Non-Core` : c ? `${c} Core` : n ? `${n} Non-Core` : '—');
// the Time-Aware requirements row: classification pill (2nd cell) and Required (3rd cell) exactly as the teacher reads them
const checkRow = async (x, core, non, kind) => { const cells = rowFor(x.section).locator('td'); const cls = (await cells.nth(1).innerText()).trim(); const req = (await cells.nth(2).innerText()).trim(); assert(cls === CLASS_WORD[kind] && req === reqText(core, non), `${x.section}: classification "${cls}" required "${req}" (wanted ${CLASS_WORD[kind]} / ${reqText(core, non)})`); return `${cls} · ${req}`; };
console.log('Browser', version);
const snap = {};

// ---------------- Scenario A ----------------
await run('A1', 'Course Curriculum shows mixed / Core-only / Non-Core-only values for Teacher 2A', async () => {
  const p = await plan(TA); snap.p0 = p;
  const [t0, t1, t2] = [p.topics[3], p.topics[4], p.topics[5]]; snap.samples = { mixed: t0, core: t1, non_core: t2 };
  assert([t0.classification, t0.core_periods, t0.non_core_periods].join() === 'mixed,3,1', JSON.stringify(t0));
  assert([t1.classification, t1.core_periods, t1.non_core_periods].join() === 'core,4,0', JSON.stringify(t1));
  assert([t2.classification, t2.core_periods, t2.non_core_periods].join() === 'non_core,0,4', JSON.stringify(t2));
  await login(TA.email); await page.goto(`${WEB}/curriculum/catalogue/${GR}/${SUBL}`); await page.waitForSelector('[data-testid="plan-context"]', { timeout: 30000 }); await page.getByText('Expand all').click();
  for (const [kind, t] of Object.entries(snap.samples)) {
    assert((await page.getByTestId(`topic-${t.topic_key}`).getByLabel(/^Core or Non-Core/).inputValue()) === kind, `${kind} select`);
    assert((await page.getByLabel(`Core periods ${t.section}`, { exact: true }).inputValue()) === String(t.core_periods) && (await page.getByLabel(`Non-Core periods ${t.section}`, { exact: true }).inputValue()) === String(t.non_core_periods), `${kind} periods`);
  }
  await shot(page, 'A1_course_curriculum'); return 'mixed 3+1, core 4+0, non-core 0+4';
});
await run('A2', 'Time-Aware shows the SAME classification and periods; nothing pending / Not configured', async () => {
  await openTimeAware(TA.email); const t = await text();
  assert(!/Not configured|Classification pending/.test(t), 'pending/not configured present');
  for (const [kind, x] of Object.entries(snap.samples)) {
    await checkRow(x, x.core_periods, x.non_core_periods, kind);
  }
  await shot(page, 'A2_time_aware'); return 'classification + required Core/Non-Core identical for all three kinds';
});
await run('A3', 'a Principal opening Time-Aware gets a teacher context (selector) and sees the same values (was: all Not configured)', async () => {
  await login(PR); await page.goto(`${WEB}/teacher/time-aware`); await page.waitForTimeout(2500);
  await page.getByLabel('Class').selectOption(String(GR)); await page.getByLabel('Subject').selectOption(SUB);
  await page.waitForSelector('[data-testid="plan-capacity-summary"]', { timeout: 30000 }); await page.waitForTimeout(1500);
  const t = await text(); assert(!/Not configured|Classification pending/.test(t), 'reviewer still sees pending');
  assert((await page.getByLabel('Teacher').inputValue()) !== '', 'teacher selector empty');
  await page.getByLabel('Teacher').selectOption(TB.id); await page.waitForTimeout(3000);
  const b = await plan(TB); const x = b.topics[3]; await checkRow(x, x.core_periods, x.non_core_periods, x.classification); await shot(page, 'A3_principal_time_aware'); return 'selector present; switching to Teacher 2B loads 2B\'s own rows';
});

// ---------------- Scenario B ----------------
await run('B1', 'mixed -> Core-only in Course Curriculum persists, and Time-Aware requirements change after reload', async () => {
  const x = snap.samples.mixed; const total = x.core_periods + x.non_core_periods;
  await login(TA.email); await page.goto(`${WEB}/curriculum/catalogue/${GR}/${SUBL}`); await page.waitForSelector('[data-testid="plan-context"]', { timeout: 30000 }); await page.getByText('Expand all').click();
  const sel = page.getByTestId(`topic-${x.topic_key}`).getByLabel(/^Core or Non-Core/); await sel.selectOption('core');
  await page.waitForFunction(([k]) => { const e = document.querySelector(`[data-testid="topic-${k}"] select[aria-label^="Core or Non-Core"]`); return e && e.value === 'core' && !e.disabled; }, [x.topic_key]);
  const t = (await plan(TA)).topics.find((q) => q.topic_key === x.topic_key); assert(t.classification === 'core' && t.core_periods === total && t.non_core_periods === 0 && t.origin === 'teacher', JSON.stringify(t));
  await page.reload(); await page.waitForSelector('[data-testid="plan-context"]'); await page.getByText('Expand all').click();
  assert((await page.getByTestId(`topic-${x.topic_key}`).getByLabel(/^Core or Non-Core/).inputValue()) === 'core', 'lost after reload');
  await openTimeAware(TA.email); const r = await checkRow(x, total, 0, 'core'); await shot(page, 'B1_time_aware_after_change'); return `3+1 -> ${total}+0, Time-Aware: ${r}`;
});

// ---------------- Scenario C ----------------
await run('C1', 'defaults are 2 Maths + 2 Science periods per day (Academic Configuration UI + API) and capacities match the formula', async () => {
  await login(PR); await page.goto(`${WEB}/principal/academic-config`); await page.waitForSelector('[data-testid="available-time"]', { timeout: 30000 });
  assert((await page.getByLabel('Mathematics periods per instructional day').inputValue()) === '2' && (await page.getByLabel('Science periods per instructional day').inputValue()) === '2', 'UI values');
  const c = await calendar(); assert(c.config.subjectPeriodsPerDay.Mathematics === 2 && c.config.subjectPeriodsPerDay.Science === 2, JSON.stringify(c.config.subjectPeriodsPerDay));
  snap.cal0 = c; const m = expectedP(c.config, SUB), s = expectedP(c.config, 'Science');
  assert(c.capacity.Mathematics.available_periods === m.P && c.capacity.Mathematics.reserved_periods === m.R && c.capacity.Mathematics.topic_capacity === m.T, JSON.stringify([c.capacity.Mathematics, m]));
  assert(c.capacity.Science.available_periods === s.P && c.capacity.Science.topic_capacity === s.T, 'science capacity');
  const t = await text(); assert(t.includes(`Mathematics: ${m.P} periods`) || new RegExp(`Mathematics: \\d+ periods`).test(t), 'available-time text');
  await shot(page, 'C1_academic_config'); snap.m0 = m; return `Maths ${m.days} days x 2 = P ${m.P}, R ${m.R}, T ${m.T}; Science P ${s.P}, T ${s.T}; v${c.version}`;
});
await run('C2', 'a normal instructional day provides exactly 2 Maths + 2 Science periods in the schedule (Time-Aware capacity card = API)', async () => {
  await openTimeAware(TA.email); const p = await plan(TA);
  assert((await cap('periods-per-day')) === 2 && (await cap('available')) === snap.m0.P && (await cap('reserve')) === snap.m0.R && (await cap('topic')) === snap.m0.T, 'card');
  assert(p.summary.periods_per_day === 2 && p.capacity.topic_capacity === snap.m0.T, 'api'); await shot(page, 'C2_capacity_card'); return `card P=${snap.m0.P} R=${snap.m0.R} T=${snap.m0.T}`;
});

// ---------------- prepare taught work for D/E/F ----------------
let planId, lessons;
await run('D00', 'ensure two completed (Done) topics exist in this plan, set by the teacher through the coverage API', async () => {
  const p = await plan(TA); let made = 0;
  for (const t of p.topics.slice(0, 2)) if (t.coverage !== 'done') { const r = await api('PUT', `/teacher-plans/${TA.id}/coverage`, tok[TA.email], { grade: GR, subject: SUB, topic_key: t.topic_key, status: 'done' }); assert(r.status === 200, `coverage ${r.status}`); made += 1; }
  const a = await plan(TA); assert(a.topics.slice(0, 2).every((t) => t.coverage === 'done'), 'not done'); return `${made} topic(s) newly marked Done; 2 Done topics present`;
});
await run('D0', 'teacher drafts + principal approves a schedule; classroom teaching is recorded for one open topic (taught periods exist)', async () => {
  await openTimeAware(TA.email); await page.getByRole('button', { name: 'Generate draft schedule for approval' }).click(); await page.getByText(/Draft saved for/).first().waitFor({ timeout: 25000 });
  await login(PR); await page.goto(`${WEB}/principal/curriculum`); const d = page.getByTestId('draft-review'); await d.waitFor({ timeout: 25000 });
  await d.getByRole('button', { name: 'Approve teaching schedule' }).click(); await d.waitFor({ state: 'detached', timeout: 20000 });
  const pl = (await api('GET', `/plans?teacher_id=${TA.id}`, tok[PR])).json.plans.find((x) => x.status === 'APPROVED' && x.grade === GR && x.subject === SUB); assert(pl, 'no approved plan');
  planId = pl.id; lessons = pl.versions[0].lessons; snap.versions0 = pl.versions.length;
  const open = lessons.find((l) => l.slots.length && (snap.p0.topics.find((t) => t.topic_key === l.nodeId)?.coverage === 'not_done'));
  snap.takenKey = open.nodeId; const date = open.slots[0].date;
  const r = await api('POST', `/plans/${planId}/execution`, tok[TA.email], { id: 'exec-final-1', nodeId: open.nodeId, date, status: 'PARTIAL', periodsTaught: 2, note: 'Scenario D classroom record' });
  assert(r.status === 201 || r.status === 200, `execution ${r.status} ${JSON.stringify(r.json).slice(0, 160)}`);
  const p = await plan(TA); const row = p.topics.find((t) => t.topic_key === open.nodeId); assert(row.taught_periods === 2 && p.summary.taught_periods === 2, `taught=${row.taught_periods}`);
  return `topic ${open.title} partially taught: 2 periods recorded on ${date}`;
});
const stateOf = async (t) => { const p = await plan(t); return { p, done: p.topics.filter((x) => x.coverage === 'done'), open: p.topics.filter((x) => x.coverage !== 'done') }; };
const checkRecalc = async (before, label, cfg) => {
  const exp = expectedP(cfg, SUB); const a = await stateOf(TA);
  assert(a.p.capacity.available_periods === exp.P && a.p.capacity.reserved_periods === exp.R && a.p.capacity.topic_capacity === exp.T, `capacity ${JSON.stringify(a.p.capacity)} vs ${JSON.stringify(exp)}`);
  for (const d of before.done) { const n = a.p.topics.find((t) => t.topic_key === d.topic_key); assert(n.coverage === 'done' && n.core_periods === d.core_periods && n.non_core_periods === d.non_core_periods, `done topic changed: ${d.section}`); }
  assert(a.p.summary.taught_periods === before.p.summary.taught_periods, 'taught periods changed');
  for (const o of before.open) {
    const n = a.p.topics.find((t) => t.topic_key === o.topic_key);
    assert(n.classification === o.classification && n.coverage === o.coverage && n.taught_periods === o.taught_periods, `classification/coverage/taught changed: ${o.section}`);
    if (o.origin !== 'demo_default') assert(n.core_periods === o.core_periods && n.non_core_periods === o.non_core_periods && n.origin === o.origin, `teacher-set requirement changed: ${o.section} ${o.core_periods}+${o.non_core_periods} -> ${n.core_periods}+${n.non_core_periods}`);
  }
  const doneTotal = a.done.reduce((s, t) => s + t.core_periods + t.non_core_periods, 0);
  const lockedRows = a.open.filter((t) => t.origin !== 'demo_default'), autoRows = a.open.filter((t) => t.origin === 'demo_default');
  const lockedTotal = lockedRows.reduce((s, t) => s + t.core_periods + t.non_core_periods, 0), lockedRem = lockedRows.reduce((s, t) => s + Math.max(0, t.core_periods + t.non_core_periods - t.taught_periods), 0);
  const floors = autoRows.reduce((s, t) => s + t.taught_periods, 0), win = windowOf(cfg, SUB);
  const pool = Math.min(win.T - lockedRem, exp.T - doneTotal - lockedTotal - floors), openAlloc = autoRows.reduce((s, t) => s + t.core_periods + t.non_core_periods, 0);
  return { exp, a, pool, openAlloc, floors, doneTotal, win, lockedRows, autoRows, lockedTotal, lockedRem };
};

// ---------------- Scenario D ----------------
let before, afterD, calD;
await run('D1', 'record capacity and untaught allocations BEFORE adding holidays', async () => {
  before = await stateOf(TA); snap.beforeB = await stateOf(TB); snap.cal1 = await calendar();
  const first = (await plan(TB)).topics[0]; snap.tb1 = first; snap.ta = before;
  return `P=${before.p.capacity.available_periods} R=${before.p.capacity.reserved_periods} T=${before.p.capacity.topic_capacity}; 2B topic 1 = ${first.section} ${first.core_periods}+${first.non_core_periods}; done=${before.done.length}, open=${before.open.length}, taught=${before.p.summary.taught_periods}`;
});
await run('D2', 'add THREE holidays in Academic Configuration and save: days, periods, reserve and untaught allocations recalculate; completed work unchanged', async () => {
  await openAcademicConfig();
  const adds = [['Final test holiday A', '2026-11-23', '2026-11-27'], ['Final test holiday B', '2027-01-25', '2027-01-29'], ['Final test holiday C', '2027-02-15', '2027-02-17']];
  for (const [label, from, to] of adds) await addEntry(/Add holiday/, label, from, to);
  await page.getByLabel('Reason for the calendar change').fill('Scenario D: three holidays added'); await shot(page, 'D2_before_save');
  await page.getByRole('button', { name: 'Save Academic Configuration' }).click(); await page.getByText(/Calendar version \d+ saved/).first().waitFor({ timeout: 30000 });
  const msg = await text(); assert(/remaining \(untaught\) syllabus was recalculated/.test(msg), 'no recalculation message'); await shot(page, 'D2_saved');
  calD = await calendar(); assert(calD.version === snap.cal1.version + 1, 'not versioned');
  const r = await checkRecalc(before, 'D', calD.config); afterD = r;
  assert(r.exp.P < expectedP(snap.cal1.config, SUB).P && r.exp.R <= expectedP(snap.cal1.config, SUB).R && r.win.P < windowOf(snap.cal1.config, SUB).P, 'capacity did not drop');
  assert(r.pool >= r.autoRows.length, 'unexpected shortage'); assert(r.openAlloc - r.floors === r.pool, `auto allocation ${r.openAlloc} - floors ${r.floors} != pool ${r.pool}`);
  const shares = r.autoRows.map((t) => t.core_periods + t.non_core_periods - t.taught_periods); assert(Math.max(...shares) - Math.min(...shares) <= 1, 'not proportional (equal weights, largest remainder)');
  assert(r.a.p.summary.fits === true && r.a.p.summary.core_shortfall === 0, 'unexpected shortfall');
  const e = (await api('GET', `/plan-logs?teacher_id=${TA.id}&limit=50`, tok[PR])).json.items.find((x) => x.category === 'calendar_recalculation'); assert(e && e.actor_role === 'principal', 'no recalculation audit event');
  const was = expectedP(snap.cal1.config, SUB), wasW = windowOf(snap.cal1.config, SUB); return `annual P ${was.P}->${r.exp.P}, R ${was.R}->${r.exp.R}, T ${was.T}->${r.exp.T}; window P ${wasW.P}->${r.win.P}, T_rem ${wasW.T}->${r.win.T}; auto-derived untaught alloc ${before.open.filter((t) => t.origin === 'demo_default').reduce((s, t) => s + t.core_periods + t.non_core_periods, 0)}->${r.openAlloc} (${r.lockedRows.length} teacher-set topics kept, ${r.lockedTotal} periods); shares ${Math.min(...shares)}..${Math.max(...shares)}`;
});
await run('D3', 'Teacher 2B: the teacher-set Topic 1.1 keeps its classification and periods; an auto-derived topic adjusts; 2A\'s Done topic 1 unchanged', async () => {
  const b = await plan(TB); const t = b.topics[0]; const was = snap.tb1;
  assert(t.classification === was.classification && t.core_periods === was.core_periods && t.non_core_periods === was.non_core_periods && t.origin === 'teacher', `Topic 1.1 changed: ${JSON.stringify(t)}`);
  const isAuto = (x) => x.origin === 'demo_default' && x.coverage === 'not_done'; const sum = (rows) => rows.filter(isAuto).reduce((s, x) => s + x.core_periods + x.non_core_periods, 0);
  const autoWas = sum(snap.beforeB.p.topics), autoNow = sum(b.topics); assert(autoNow !== autoWas, `auto-derived untaught total did not recalculate (${autoWas})`);
  const a1 = (await plan(TA)).topics[0]; assert(a1.coverage === 'done' && a1.core_periods === snap.ta.p.topics[0].core_periods && a1.non_core_periods === snap.ta.p.topics[0].non_core_periods, 'done topic 1 changed');
  const eb = expectedP(calD.config, SUB), wb = windowOf(calD.config, SUB); assert(b.capacity.topic_capacity === eb.T, '2B capacity');
  const all = b.topics.reduce((s, x) => s + x.core_periods + x.non_core_periods, 0); assert(all === Math.min(wb.T, eb.T), `2B total ${all} != capacity left ${wb.T}`);
  return `2B ${t.section}: ${t.classification} ${t.core_periods}+${t.non_core_periods} kept (teacher-set); auto-derived untaught topics total ${autoWas} -> ${autoNow} (capacity left ${wb.T}); 2A topic 1 stays Done`;
});
await run('D4', 'Time-Aware after reload shows the revised capacity, the revised untaught allocations and the recalculation note', async () => {
  await openTimeAware(TA.email); const e = expectedP(calD.config, SUB);
  const wn = windowOf(calD.config, SUB);
  assert((await cap('available')) === e.P && (await cap('reserve')) === e.R && (await cap('topic')) === e.T, 'card'); assert((await cap('taught')) === 2, 'taught');
  assert((await cap('left-days')) === wn.days && (await cap('left-periods')) === wn.P && (await cap('left-reserve')) === wn.R && (await cap('left-capacity')) === wn.T, 'remaining-window card');
  assert(await page.getByTestId('last-recalculation').count() === 1, 'no recalculation note'); await shot(page, 'D4_time_aware_after_holidays');
  const open = afterD.autoRows.find((t) => t.topic_key !== snap.takenKey); await checkRow(open, open.core_periods, open.non_core_periods, open.classification); return `card annual P=${e.P} R=${e.R} T=${e.T}; window after ${TODAY}: ${wn.days} days, ${wn.P} periods, reserve ${wn.R}, capacity ${wn.T}; taught stays 2`;
});
await run('D5', 'approved schedule is not duplicated or rewritten; execution record unchanged', async () => {
  const pls = (await api('GET', `/plans?teacher_id=${TA.id}`, tok[PR])).json.plans.filter((x) => x.grade === GR && x.subject === SUB && x.status === 'APPROVED');
  assert(pls.length === 1 && pls[0].id === planId && pls[0].versions.length === snap.versions0, `plans=${pls.length} versions=${pls[0]?.versions.length}`);
  assert(pls[0].execution.filter((x) => x.nodeId === snap.takenKey).length === 1 && pls[0].execution[0].periodsTaught === 2, 'execution changed'); return 'single approved plan, versions unchanged, 1 execution record (2 periods)';
});

await run('D6', 'two calendars are explained; a holiday changes working days so a NEW schedule is generated from the CURRENT calendar and approval stays explicit; notice disappears after approval', async () => {
  await openTimeAware(TA.email); const n = page.getByTestId('calendar-snapshot-notice'); await n.waitFor({ timeout: 20000 }); const t = (await n.innerText()).replace(/\s+/g, ' ');
  const curDays = expectedP(calD.config, SUB).days, snapDays = expectedP(snap.cal1.config, SUB).days;
  assert(t.includes(`${curDays} instructional days`) && t.includes(`${snapDays} instructional days`) && /cannot be edited in place/.test(t) && /Principal\/Admin must approve/.test(t), t.slice(0, 1200));
  assert(/approved schedule v1: days left/i.test(await text()) && /current academic calendar \(version \d+\)/i.test(await text()), 'figures are not labelled with their calendar'); await shot(page, 'D6_two_calendars_notice');
  await page.getByRole('button', { name: 'Recalculate with current configuration' }).first().click(); await page.getByText(/New schedule generated using the updated academic calendar/).first().waitFor({ timeout: 25000 });
  let all = (await api('GET', `/plans?teacher_id=${TA.id}`, tok[PR])).json.plans.filter((x) => x.grade === GR && x.subject === SUB);
  const approvedBefore = all.filter((x) => x.status === 'APPROVED'); assert(approvedBefore.length === 1 && approvedBefore[0].id === planId && all.some((x) => x.status === 'DRAFT'), 'the draft replaced the approved schedule before approval');
  await login(PR); await page.goto(`${WEB}/principal/curriculum`); const d = page.getByTestId('draft-review'); await d.waitFor({ timeout: 25000 }); await shot(page, 'D6_draft_awaiting_approval');
  await d.getByRole('button', { name: 'Approve teaching schedule' }).click(); await d.waitFor({ state: 'detached', timeout: 20000 });
  all = (await api('GET', `/plans?teacher_id=${TA.id}`, tok[PR])).json.plans.filter((x) => x.grade === GR && x.subject === SUB);
  const nowApproved = all.filter((x) => x.status === 'APPROVED'); assert(nowApproved.length === 1 && nowApproved[0].id !== planId && all.find((x) => x.id === planId).status === 'SUPERSEDED', 'old schedule not superseded exactly once');
  assert(expectedP(nowApproved[0].versions[0].config, SUB).days === curDays, 'new schedule is not on the current calendar');
  const executions = all.reduce((s, x) => s + x.execution.length, 0); assert(executions === 1, `execution history changed: ${executions}`);
  assert((await plan(TA)).summary.taught_periods === 2, 'taught periods lost'); planId = nowApproved[0].id; snap.versions0 = nowApproved[0].versions.length;
  await openTimeAware(TA.email); assert((await page.getByTestId('calendar-snapshot-notice').count()) === 0, 'notice still shown after approval');
  return `new draft waited for approval (old schedule stayed approved) -> approved -> old superseded, new on ${curDays} days; taught history kept (2 periods); notice gone`;
});

// ---------------- Scenario E ----------------
await run('E1', 'remove one holiday: capacity increases, remaining allocation recalculates, no duplicates, history unchanged', async () => {
  const calDcfg = (await calendar()).config; const beforeE = await stateOf(TA); const pBefore = beforeE.p.capacity.available_periods;
  await openAcademicConfig();
  const idx = await idxOf('Final test holiday B'); assert(idx, 'holiday B not found');
  await page.getByRole('button', { name: `Remove entry ${idx}` }).click(); await page.getByLabel('Reason for the calendar change').fill('Scenario E: holiday B removed');
  await page.getByRole('button', { name: 'Save Academic Configuration' }).click(); await page.getByText(/Calendar version \d+ saved/).first().waitFor({ timeout: 30000 }); await shot(page, 'E1_saved');
  const calE = await calendar(); const r = await checkRecalc(beforeE, 'E', calE.config);
  assert(r.a.p.capacity.available_periods === pBefore + 5 * 2 && r.win.P === windowOf(calDcfg, SUB).P + 10, `P ${pBefore} -> ${r.a.p.capacity.available_periods} (+10 expected)`);
  assert(r.openAlloc - r.floors === r.pool && r.a.p.summary.fits, `allocation ${r.openAlloc - r.floors} != pool ${r.pool}`);
  const pls = (await api('GET', `/plans?teacher_id=${TA.id}`, tok[PR])).json.plans.filter((x) => x.grade === GR && x.subject === SUB && x.status === 'APPROVED'); assert(pls.length === 1 && pls[0].versions.length === snap.versions0 && (await api('GET', `/plans?teacher_id=${TA.id}`, tok[PR])).json.plans.filter((x) => x.grade === GR && x.subject === SUB).reduce((s2, x) => s2 + x.execution.length, 0) === 1, 'duplicates/history');
  const topicRows = r.a.p.topics.length; assert(topicRows === snap.ta.p.topics.length && new Set(r.a.p.topics.map((t) => t.topic_key)).size === topicRows, 'duplicate topic rows');
  return `P ${pBefore} -> ${r.a.p.capacity.available_periods} (+10), T -> ${r.a.p.capacity.topic_capacity}; auto-derived untaught alloc ${beforeE.open.filter((t) => t.origin === 'demo_default').reduce((s, t) => s + t.core_periods + t.non_core_periods, 0)} -> ${r.openAlloc}; ${topicRows} unique topic rows`;
});

// ---------------- Scenario F ----------------
await run('F1', 'insufficient capacity: Core shortfall reported, Core never deleted/downgraded, Done work kept, Non-Core to independent/homework', async () => {
  const beforeF = await stateOf(TA);
  await openAcademicConfig();
  let n = await page.getByLabel(/^Entry \d+ description$/).count(); while (n > 0) { await page.getByRole('button', { name: `Remove entry ${n}` }).click(); n -= 1; }
  await addEntry(/Add vacation/, 'Scenario F: long closure', '2026-04-01', '2027-03-03');
  await page.getByLabel('Reason for the calendar change').fill('Scenario F: closure leaves only a few teaching days'); await shot(page, 'F1_before_save');
  await page.getByRole('button', { name: 'Save Academic Configuration' }).click(); await page.getByText(/Calendar version \d+ saved/).first().waitFor({ timeout: 30000 });
  const calF = await calendar(); const e = expectedP(calF.config, SUB); const a = await stateOf(TA);
  assert(a.p.capacity.topic_capacity === e.T && e.days === 20, `days=${e.days} T=${a.p.capacity.topic_capacity}`);
  assert(a.p.summary.fits === false && a.p.summary.core_shortfall > 0, `shortfall not reported: ${JSON.stringify(a.p.summary)}`);
  for (const d of beforeF.done) { const n2 = a.p.topics.find((t) => t.topic_key === d.topic_key); assert(n2.coverage === 'done' && n2.core_periods === d.core_periods && n2.non_core_periods === d.non_core_periods, 'done topic changed'); }
  assert(a.p.summary.taught_periods === 2, 'taught changed');
  const openRows = a.p.topics.filter((t) => t.coverage !== 'done' && t.origin === 'demo_default'); const doneAlloc = a.done.reduce((s, t) => s + t.core_periods + t.non_core_periods, 0);
  for (const o of beforeF.open.filter((t) => t.origin !== 'demo_default')) { const n2 = a.p.topics.find((t) => t.topic_key === o.topic_key); assert(n2.core_periods === o.core_periods && n2.non_core_periods === o.non_core_periods && n2.classification === o.classification, `teacher-set topic changed under shortage: ${o.section}`); }
  const coreTopics = openRows.filter((t) => t.classification !== 'non_core'); const served = coreTopics.filter((t) => t.core_periods > 0).length;
  const nonCoreServed = openRows.filter((t) => t.classification === 'non_core' && t.core_periods + t.non_core_periods > 0).length;
  assert(a.p.summary.core_shortfall === coreTopics.length - served, `core_shortfall ${a.p.summary.core_shortfall} != ${coreTopics.length - served}`);
  assert(!(nonCoreServed > 0 && served < coreTopics.length), `Non-Core served (${nonCoreServed}) before all Core (${served}/${coreTopics.length})`);
  assert(openRows.filter((t) => t.classification === 'core').every((t) => t.core_periods + t.non_core_periods === 0 || t.non_core_periods === 0), 'a Core topic was downgraded to Non-Core');
  assert(openRows.every((t) => t.classification === (beforeF.open.find((o) => o.topic_key === t.topic_key)?.classification)), 'a classification changed');
  await openTimeAware(TA.email); const alert = await page.getByTestId('capacity-shortfall').innerText(); assert(/Core topic\(s\) cannot be given a Core period/.test(alert), alert); await shot(page, 'F1_shortfall_banner');
  return `20 teaching days left, annual T=${e.T}, teacher-set topics kept; auto-derived Core topics served ${served}/${coreTopics.length}, Non-Core-only topics given periods ${nonCoreServed}; core_shortfall=${a.p.summary.core_shortfall}, total_shortfall=${a.p.summary.total_shortfall}; Done work (${a.done.length} topics, ${doneAlloc} periods) kept; overcommitted by teacher-set periods: ${a.p.summary.overcommitted_periods}`;
});
await run('F2', 'the second teacher (no taught work) gets the same independent shortage report; sufficient capacity was shown for both in D', async () => {
  const b = await plan(TB); assert(b.summary.fits === false && b.summary.core_shortfall > 0 && b.summary.taught_periods === 0, JSON.stringify(b.summary));
  return `2B: core_shortfall=${b.summary.core_shortfall}, total_shortfall=${b.summary.total_shortfall}, T=${b.capacity.topic_capacity}`;
});
await browser.close();
fs.writeFileSync(process.env.REPORT || 'e2e-results-scenarios.json', JSON.stringify(results, null, 1));
const bad = results.filter((r) => !r.ok); console.log(`\n${results.length - bad.length}/${results.length} passed`); process.exit(bad.length ? 1 : 0);
