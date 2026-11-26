// The "Recalculate with current configuration" action, driven in Edge (Playwright) with API/DB read-back. Disposable demo-DB copy only.
//   MODE=before|after GRADE=7 SUBJECT=Mathematics WEB_URL=... API_URL=... SHOTS=... node e2e/recalc_button.mjs
import fs from 'node:fs';
import { WEB, api, assert, launch, shot } from '../lib.mjs';
const MODE = process.env.MODE || 'after', GR = Number(process.env.GRADE || 7), SUB = process.env.SUBJECT || 'Mathematics';
const { page, browser, version } = await launch();
const results = [];
const run = async (id, what, fn) => {
  try { const n = await fn(); results.push({ id, what, ok: true, note: n ?? '' }); console.log(`PASS ${id} ${what} ${n ?? ''}`); }
  catch (e) { const m = String(e.message).split('\n')[0].slice(0, 360); results.push({ id, what, ok: false, note: m }); console.log(`FAIL ${id} ${what}: ${m}`); await shot(page, `${id}_FAIL`); }
};
const login = async (email) => {
  await page.goto(`${WEB}/login`); await page.evaluate(() => localStorage.clear()); await page.goto(`${WEB}/login`);
  await page.locator('input').first().fill(email); await page.locator('input[type="password"]').fill('demo123');
  await page.getByRole('button', { name: /^Sign in/ }).click(); await page.waitForURL((u) => !u.pathname.includes('login'), { timeout: 20000 });
};
const tokenOf = async (email) => (await api('POST', '/auth/login', null, { email, password: 'demo123' })).json.access_token;
const TA = { email: 'teacher2a@lumeneios.demo', id: 'demo-plan-teacher-2a' }, PR = 'principal2@lumeneios.demo';
const tok = { [TA.email]: await tokenOf(TA.email), [PR]: await tokenOf(PR) };
const plans = async () => (await api('GET', `/plans?teacher_id=${TA.id}`, tok[PR])).json.plans.filter((x) => x.grade === GR && x.subject === SUB);
const plan = async () => (await api('GET', `/teacher-plans/${TA.id}?grade=${GR}&subject=${SUB}`, tok[TA.email])).json;
const calendar = async () => (await api('GET', '/plan-calendar', tok[PR])).json;
const text = async () => (await page.innerText('body')).replace(/\s+/g, ' ');
const openTA = async () => {
  await login(TA.email); await page.goto(`${WEB}/teacher/time-aware`); await page.waitForTimeout(2500);
  await page.getByLabel('Class').selectOption(String(GR)); await page.getByLabel('Subject').selectOption(SUB);
  await page.waitForSelector('[data-testid="plan-capacity-summary"]', { timeout: 30000 }); await page.waitForTimeout(1500);
};
const openAC = async () => {
  await login(PR); await page.goto(`${WEB}/principal/academic-config`); await page.waitForSelector('[data-testid="available-time"]', { timeout: 30000 });
  await page.getByLabel(/^Entry \d+ description$/).first().waitFor({ timeout: 30000 }); await page.waitForTimeout(800);
};
const idxOf = async (label) => { const n = await page.getByLabel(/^Entry \d+ description$/).count(); for (let i = 1; i <= n; i++) if ((await page.getByLabel(`Entry ${i} description`).inputValue()) === label) return i; return 0; };
const addHoliday = async (label, from, to) => {
  await page.getByRole('button', { name: /Add holiday/ }).click(); const n = await page.getByLabel(/^Entry \d+ description$/).count(); let k = 0;
  for (let i = 1; i <= n; i++) if ((await page.getByLabel(`Entry ${i} description`).inputValue()) === '') k = i;
  await page.getByLabel(`Entry ${k} description`).fill(label); await page.getByLabel(`Entry ${await idxOf(label)} from`).fill(from); await page.getByLabel(`Entry ${await idxOf(label)} to`).fill(to);
};
const saveCal = async (why) => { await page.getByLabel('Reason for the calendar change').fill(why); await page.getByRole('button', { name: 'Save Academic Configuration' }).click(); await page.getByText(/Calendar version \d+ saved/).first().waitFor({ timeout: 30000 }); };
const snapTopics = async () => (await plan()).topics.map((t) => ({ k: t.topic_key, s: t.section, c: t.classification, core: t.core_periods, non: t.non_core_periods, cov: t.coverage, taught: t.taught_periods, o: t.origin }));
const sched = (lessons) => lessons.reduce((s, l) => s + l.slots.length, 0);
console.log('Browser', version, 'MODE', MODE);
const S = {};
await run('R0', 'approved schedule exists, 2 topics Done, 2 periods taught (set up through the UI + API)', async () => {
  const p0 = await plan();
  for (const t of p0.topics.slice(0, 2)) if (t.coverage !== 'done') await api('PUT', `/teacher-plans/${TA.id}/coverage`, tok[TA.email], { grade: GR, subject: SUB, topic_key: t.topic_key, status: 'done' });
  await openTA(); await page.getByRole('button', { name: 'Generate draft schedule for approval' }).click(); await page.getByText(/Draft saved for/).first().waitFor({ timeout: 25000 });
  await login(PR); await page.goto(`${WEB}/principal/curriculum`); const d = page.getByTestId('draft-review'); await d.waitFor({ timeout: 25000 });
  await d.getByRole('button', { name: 'Approve teaching schedule' }).click(); await d.waitFor({ state: 'detached', timeout: 20000 });
  const ap = (await plans()).find((x) => x.status === 'APPROVED'); S.planId = ap.id;
  const lesson = ap.versions[0].lessons.find((l) => l.slots.length && (p0.topics.find((t) => t.topic_key === l.nodeId)?.coverage === 'not_done'));
  const r = await api('POST', `/plans/${ap.id}/execution`, tok[TA.email], { id: 'exec-rb-1', nodeId: lesson.nodeId, date: lesson.slots[0].date, status: 'PARTIAL', periodsTaught: 2, note: 'recalc button test' });
  assert([200, 201].includes(r.status), `exec ${r.status}`); S.takenKey = lesson.nodeId; S.v1 = ap.versions[0].version; return `approved v${S.v1}; taught 2 periods on ${lesson.title}`;
});
await run('R1', 'record state BEFORE the calendar change (plans, versions, topic allocations)', async () => {
  S.before = await snapTopics(); S.plansBefore = (await plans()).map((x) => `${x.id}:${x.status}:${x.versions.length}`); S.cal0 = await calendar(); return `${S.plansBefore.length} plan(s); ${S.before.length} topics`;
});
await run('R2', 'principal adds holidays (UI) and saves the calendar', async () => {
  await openAC(); for (const [l, f, t] of [['Recalc holiday A', '2026-11-23', '2026-11-27'], ['Recalc holiday B', '2027-01-25', '2027-01-29']]) await addHoliday(l, f, t);
  await saveCal('Recalc test: holidays added'); S.cal1 = await calendar(); assert(S.cal1.version === S.cal0.version + 1, 'not versioned'); return `calendar v${S.cal0.version} -> v${S.cal1.version}`;
});
await run('R3', 'teacher opens Time-Aware and clicks "Recalculate with current configuration"', async () => {
  await openTA(); await shot(page, `R3_${MODE}_before_click`);
  const btn = page.getByRole('button', { name: /Recalculate with current configuration/ }).first(); await btn.waitFor({ timeout: 15000 });
  const calls = []; page.on('request', (rq) => { if (rq.method() !== 'GET' && rq.url().includes('/api/v1/')) calls.push(`${rq.method()} ${rq.url().split('/api/v1')[1].split('?')[0]}`); });
  await btn.click(); await page.waitForTimeout(MODE === 'before' ? 4000 : 7000); await shot(page, `R3_${MODE}_after_click`);
  const t = await text(); S.after = t; S.calls = calls; S.plansAfter = await plans();
  const visible = (t.match(/(Recalculation proposal created[^.]*\.|This plan was created with[^.]*\.|New schedule generated[^.]*\.|Nothing changed[^.]*\.)/) || [''])[0];
  return `API writes: [${calls.join(', ') || 'none'}]; visible message: "${visible || 'NONE'}"; plans now: ${S.plansAfter.map((x) => `${x.status}:v${x.versions.length}:proposals=${x.proposals.length}`).join(' | ')}`;
});
if (MODE === 'after') {
  await run('R4', 'a NEW DRAFT now exists in the database (approved schedule untouched) and the page says so', async () => {
    const all = S.plansAfter; const draft = all.find((x) => x.status === 'DRAFT'); const ap = all.find((x) => x.status === 'APPROVED');
    assert(draft && ap && ap.id === S.planId && ap.versions.length === 1, `plans: ${all.map((x) => x.status).join(',')}`); S.draftId = draft.id;
    assert(draft.draft.basis && draft.draft.basis.kind === 'RECALCULATION' && draft.draft.basis.fromPlanId === S.planId, 'draft has no recalculation basis');
    assert(/New schedule generated using the updated academic calendar\. Awaiting principal approval\./.test(S.after), 'success message missing');
    assert((await page.getByTestId('recalc-result').count()) > 0, 'result panel missing'); return `draft ${draft.id.slice(0, 8)} based on approved v1; calendar snapshot days ${draft.draft.basis.calendarDays}`;
  });
  await run('R5', 'the result panel shows previous vs revised allocations, capacity, remaining Core, shortfall and the approval requirement', async () => {
    const panel = (await page.getByTestId('recalc-result').innerText()).replace(/\s+/g, ' ');
    for (const re of [/Previous approved schedule v1/, /New draft/, /Awaiting principal approval/, /Remaining Core/i, /Shortfall/i, /instructional days/]) assert(re.test(panel), `panel lacks ${re}: ${panel.slice(0, 300)}`);
    const rows = await page.getByTestId('recalc-diff-row').count(); assert(rows > 0, 'no changed-allocation rows'); await shot(page, 'R5_result_panel'); return `${rows} changed topic row(s) shown`;
  });
  await run('R6', 'untaught allocations changed where capacity changed; Done topics and taught periods untouched; classifications unchanged', async () => {
    const draft = S.plansAfter.find((x) => x.status === 'DRAFT'); const d = Object.fromEntries(draft.draft.lessons.map((l) => [l.nodeId, l]));
    const done = S.before.filter((t) => t.cov === 'done'); assert(done.length >= 2 && done.every((t) => !d[t.k] || d[t.k].slots.length === 0), 'a Done topic was given new periods');
    const after = await snapTopics();
    for (const b of S.before) { const a = after.find((x) => x.k === b.k); assert(a.c === b.c && a.cov === b.cov && a.taught === b.taught, `topic changed: ${b.s}`); if (b.o !== 'demo_default') assert(a.core === b.core && a.non === b.non, `teacher-set periods changed: ${b.s}`); }
    assert(after.find((x) => x.k === S.takenKey).taught === 2, 'taught periods lost');
    const ds = sched(draft.draft.lessons); const ap = S.plansAfter.find((x) => x.status === 'APPROVED'); const as = sched(ap.versions[0].lessons);
    assert(ds !== as, `scheduled periods did not change (${ds} vs ${as})`); return `scheduled periods: approved v1 ${as} -> new draft ${ds}; ${done.length} Done topics got no periods; taught 2 kept`;
  });
  await run('R7', 'refresh: the draft, its message panel and allocations are still visible', async () => {
    await page.reload(); await page.waitForSelector('[data-testid="plan-capacity-summary"]', { timeout: 30000 }); await page.getByTestId('recalc-result').waitFor({ timeout: 20000 });
    const panel = (await page.getByTestId('recalc-result').innerText()).replace(/\s+/g, ' '); assert(/Awaiting principal approval/.test(panel) && (await page.getByTestId('recalc-diff-row').count()) > 0, panel.slice(0, 200));
    await shot(page, 'R7_after_refresh'); return 'panel persists after reload';
  });
  await run('R8', 'clicking again with the SAME calendar creates no duplicate draft and says so', async () => {
    const before = (await plans()).length; await page.getByRole('button', { name: /Recalculate with current configuration/ }).first().click(); await page.waitForTimeout(4000);
    const t = await text(); const now = (await plans()).length; assert(now === before, `duplicate draft created (${before} -> ${now})`); assert(/already generated|Nothing changed/.test(t), 'no explanation');
    await shot(page, 'R8_duplicate_guard'); return `plans stay ${now}; message explains it`;
  });
  await run('R9', 'principal sees and approves the draft (explicit approval): old schedule superseded, new one on the current calendar, taught history kept', async () => {
    await login(PR); await page.goto(`${WEB}/principal/curriculum`); const d = page.getByTestId('draft-review'); await d.waitFor({ timeout: 25000 }); await shot(page, 'R9_principal_draft_review');
    assert((await plans()).filter((x) => x.status === 'APPROVED').length === 1, 'approved changed before approval');
    await d.getByRole('button', { name: 'Approve teaching schedule' }).click(); await d.waitFor({ state: 'detached', timeout: 20000 });
    const all = await plans(); const ap = all.filter((x) => x.status === 'APPROVED'); assert(ap.length === 1 && ap[0].id === S.draftId && all.find((x) => x.id === S.planId).status === 'SUPERSEDED', 'supersede');
    assert(all.reduce((s, x) => s + x.execution.length, 0) === 1, 'execution history changed'); assert((await plan()).summary.taught_periods === 2, 'taught lost'); return 'new approved schedule; old SUPERSEDED with its execution record; taught 2';
  });
  await run('R10', 'second recalculation after REMOVING a holiday: a new draft reflects the larger capacity', async () => {
    await openAC(); const i = await idxOf('Recalc holiday B'); await page.getByRole('button', { name: `Remove entry ${i}` }).click(); await saveCal('Recalc test: holiday removed');
    await openTA(); const n0 = (await plans()).length; await page.getByRole('button', { name: /Recalculate with current configuration/ }).first().click();
    await page.getByText(/New schedule generated using the updated academic calendar/).first().waitFor({ timeout: 25000 });
    const all = await plans(); assert(all.length === n0 + 1 && all.filter((x) => x.status === 'DRAFT').length === 1 && all.filter((x) => x.status === 'APPROVED').length === 1, `plans ${all.map((x) => x.status)}`);
    const dr = all.find((x) => x.status === 'DRAFT'), ap = all.find((x) => x.status === 'APPROVED'); const ds = sched(dr.draft.lessons), as = sched(ap.versions[0].lessons);
    assert(ds > as, `capacity did not increase the scheduled periods (${as} -> ${ds})`); await shot(page, 'R10_second_recalc'); return `scheduled periods approved ${as} -> new draft ${ds} (holiday removed)`;
  });
}
await browser.close();
fs.writeFileSync(process.env.REPORT || `e2e-results-recalc-${MODE}.json`, JSON.stringify({ results, calls: S.calls }, null, 1));
const bad = results.filter((r) => !r.ok); console.log(`\n${results.length - bad.length}/${results.length} passed`); process.exit(bad.length ? 1 : 0);
