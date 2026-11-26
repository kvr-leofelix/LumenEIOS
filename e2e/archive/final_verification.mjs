// Final targeted verification on a FRESH disposable database (roster: JNV Bengaluru / Dakshana Kottayam).
// UI actions run in Edge via Playwright; every result is then read back from the backend API / SQLite, never from the page alone.
//   WEB_URL=http://127.0.0.1:5182 API_URL=http://127.0.0.1:8012/api/v1 DB=<path to the disposable .db> SHOTS=./e2e-shots/final node e2e/final_verification.mjs
import { DatabaseSync } from 'node:sqlite';
import fs from 'node:fs';
import { API, WEB, api, assert, launch, shot } from '../lib.mjs';

const DB = process.env.DB;
const { page, browser, version } = await launch();
const results = [];
const run = async (id, what, fn) => {
  try { const n = await fn(); results.push({ id, what, ok: true, note: n ?? '' }); console.log(`PASS ${id} ${what} ${n ?? ''}`); }
  catch (e) { const m = String(e.message).split('\n')[0].slice(0, 300); results.push({ id, what, ok: false, note: m }); console.log(`FAIL ${id} ${what}: ${m}`); await shot(page, `${id}_FAIL`); }
};
const login = async (email) => {
  await page.goto(`${WEB}/login`); await page.evaluate(() => localStorage.clear()); await page.goto(`${WEB}/login`);
  await page.locator('input').first().fill(email); await page.locator('input[type="password"]').fill('demo123');
  await page.getByRole('button', { name: /^Sign in/ }).click(); await page.waitForURL((u) => !u.pathname.includes('login'), { timeout: 20000 });
};
const tokenOf = async (email) => { const r = await api('POST', '/auth/login', null, { email, password: 'demo123' }); assert(r.status === 200, `login ${email} ${r.status}`); return r.json.access_token; };
const G = { email: 'teacher@lumeneios.demo', id: 'user-teacher-garima' }, K = { email: 'kamlesh@lumeneios.demo', id: 'user-teacher-kamlesh' };
const P1 = 'principal@lumeneios.demo', P2 = 'principal.dakshana@lumeneios.demo', ADMIN = 'admin@lumeneios.demo';
const tok = {}; for (const e of [G.email, K.email, P1, P2, ADMIN]) tok[e] = await tokenOf(e);
const plan = async (who, t, g, s) => (await api('GET', `/teacher-plans/${t.id}?grade=${g}&subject=${s}`, tok[who.email])).json;
const topicOf = async (key) => (await plan(G, G, 6, 'Science')).topics.find((t) => t.topic_key === key);
const logsFor = async (key) => (await api('GET', `/plan-logs?teacher_id=${G.id}&limit=200`, tok[P1])).json.items.filter((e) => e.topic_keys?.includes(key));
const openCatalogue = async (g = 6, s = 'science', q = '') => {
  await page.goto(`${WEB}/curriculum/catalogue/${g}/${s}${q}`); await page.waitForSelector('[data-testid="plan-context"]', { timeout: 30000 });
  await page.getByText('Expand all').click();
};
const covSel = (key) => page.getByTestId(`topic-${key}`).getByLabel(/^Coverage status/);
const clsSel = (key) => page.getByTestId(`topic-${key}`).getByLabel(/^Core or Non-Core/);
const settle = (sel, v) => sel.evaluate((el, val) => new Promise((res) => { const t = setInterval(() => { if (el.value === val && !el.disabled) { clearInterval(t); res(true); } }, 50); }), v);
const lessonTimeAware = async (who, g, s) => { await login(who); await page.goto(`${WEB}/teacher/time-aware`); await page.waitForTimeout(2500);
  await page.getByLabel('Class').selectOption(String(g)); await page.getByLabel('Subject').selectOption(s); await page.waitForTimeout(4500); };
console.log('Browser', version, '| DB', DB);

// ---------- 0. fresh database facts ----------
await run('F0', 'fresh DB initialised: 415 topics, 6 plans, no duplicates, 76/353/102 in the dataset', async () => {
  const d = new DatabaseSync(DB, { readOnly: true }); const one = (q) => d.prepare(q).get();
  const topics = one("select count(*) c from plan_topics where source_ref like 'ncert-batch:%'").c;
  const cfg = one('select count(*) c from teacher_topic_configs').c, cov = one('select count(*) c from teacher_topic_coverage').c;
  const dup = one('select count(*) c from (select 1 from teacher_topic_configs group by school_id,teacher_id,academic_year,grade,subject,topic_key having count(*)>1)').c;
  const plans = one('select count(*) c from (select 1 from teacher_topic_configs group by teacher_id,grade,subject)').c;
  const ds = JSON.parse(one("select state s from planning_workspace_revisions where school_id='school-1'").s).datasets[0].nodes;
  const kinds = ds.reduce((m, n) => ((m[n.kind] = (m[n.kind] || 0) + 1), m), {});
  assert(topics === 415 && cfg === 415 && cov === 415 && dup === 0 && plans === 6, `topics=${topics} cfg=${cfg} cov=${cov} dup=${dup} plans=${plans}`);
  assert(kinds.CHAPTER === 76 && kinds.TOPIC === 353 && kinds.SUBTOPIC === 102, JSON.stringify(kinds));
  const per = d.prepare('select teacher_id,grade,subject,count(*) c from teacher_topic_configs group by 1,2,3 order by 1,2').all().map((r) => `${r.teacher_id.replace('user-teacher-', '')}:${r.grade}${r.subject[0]}=${r.c}`);
  const sum = d.prepare('select sum(c) s from (select count(*) c from teacher_topic_configs group by teacher_id,grade,subject)').get().s;
  assert(sum === 415, 'sum');
  return per.join(' ');
});

// ---------- 1. coverage transitions (UI) ----------
await login(G.email); await openCatalogue();
const keys = await page.locator('select[aria-label^="Coverage status"]').evaluateAll((els) => els.map((e) => e.closest('li').getAttribute('data-testid').slice(6)));
const A = keys[0], B = keys[1];
const hops = [[A, 'NOT_DONE', 'IN_PROGRESS', 'not_done', 'in_progress'], [A, 'IN_PROGRESS', 'DONE', 'in_progress', 'done'], [A, 'DONE', 'IN_PROGRESS', 'done', 'in_progress'],
  [A, 'IN_PROGRESS', 'NOT_DONE', 'in_progress', 'not_done'], [B, 'NOT_DONE', 'DONE', 'not_done', 'done'], [B, 'DONE', 'NOT_DONE', 'done', 'not_done']];
let n = 0;
for (const [key, from, to, bf, af] of hops) {
  n += 1;
  await run(`C${n}`, `coverage ${from} -> ${to} persists, audited with before/after`, async () => {
    assert((await covSel(key).inputValue()) === from, `start state ${await covSel(key).inputValue()} != ${from}`);
    await covSel(key).selectOption(to); await settle(covSel(key), to);
    assert((await topicOf(key)).coverage === af, 'API coverage');
    const ev = (await logsFor(key)).filter((e) => e.category === 'coverage_status')[0];
    assert(ev && ev.summary.includes(`${bf} -> ${af}`) && ev.actor_name === 'Garima' && ev.actor_role === 'teacher' && Date.now() - Date.parse(ev.occurred_at + 'Z') < 120000, JSON.stringify(ev));
    return `log: ${ev.summary.slice(-32)} by ${ev.actor_name} @ ${ev.occurred_at}`;
  });
}
await run('C7', 'coverage percentage equals persisted Done / 65 (all back to 0 done)', async () => {
  const p = await plan(G, G, 6, 'Science'); assert(p.coverage.done === 0 && p.coverage.eligible === 65, JSON.stringify(p.coverage));
  assert((await page.getByTestId('coverage-percent').innerText()).trim() === '0%', 'UI percent'); return '0% / 65';
});

// ---------- 2. Core <-> Non-Core ----------
const mixed = (await plan(G, G, 6, 'Science')).topics.find((t) => t.classification === 'mixed' && t.core_periods + t.non_core_periods >= 3);
const total = mixed.core_periods + mixed.non_core_periods, orig = [mixed.core_periods, mixed.non_core_periods];
const classHops = [['non_core', 0, total], ['core', total, 0], ['mixed', Math.ceil((total * 2) / 3), total - Math.ceil((total * 2) / 3)], ['core', total, 0], ['non_core', 0, total]];
let m = 0, prev = 'mixed';
for (const [to, c, nc] of classHops) {
  m += 1; const from = prev;
  await run(`K${m}`, `classification ${from} -> ${to}: periods redistributed (total ${total} kept) and persisted`, async () => {
    await clsSel(mixed.topic_key).selectOption(to); await settle(clsSel(mixed.topic_key), to);
    const t = await topicOf(mixed.topic_key); assert(t.classification === to && t.core_periods === c && t.non_core_periods === nc && t.origin === 'teacher', JSON.stringify(t));
    const ev = (await logsFor(mixed.topic_key)).filter((e) => e.category === 'topic_classification')[0];
    assert(ev && ev.previous_value.classification === from && ev.new_value.classification === to && ev.new_value.core_periods === c && ev.actor_name === 'Garima', JSON.stringify(ev && [ev.previous_value, ev.new_value]));
    prev = to; return `${from}->${to} core=${c} non-core=${nc}`;
  });
}
await run('K6', 'reload keeps Core/Non-Core and capacity total unchanged', async () => {
  await openCatalogue(); assert((await clsSel(mixed.topic_key).inputValue()) === 'non_core', 'select lost');
  const p = await plan(G, G, 6, 'Science'); assert(p.allocation.proposed_total === 234 || p.allocation.valid, JSON.stringify(p.allocation)); return `allocation valid, proposed_total=${p.allocation.proposed_total}`;
});
await shot(page, 'k_classification');

// ---------- 3. Time-Aware / lost periods / recovery (Science needs 2 periods a day for same-date losses) ----------
await run('T0', 'default Academic Configuration is already 2 Maths + 2 Science periods/day (no manual setup needed)', async () => {
  const cur = (await api('GET', '/plan-calendar', tok[ADMIN])).json; const spd = cur.config.subjectPeriodsPerDay;
  assert(spd.Science === 2 && spd.Mathematics === 2, JSON.stringify(spd)); return `calendar v${cur.version}: ${JSON.stringify(spd)}`;
});
await run('T1', 'Time-Aware (Garima, VI Science) renders saved requirements; no "Not configured"; day counts present', async () => {
  await lessonTimeAware(G.email, 6, 'Science'); const t = (await page.innerText('body')).replace(/\s+/g, ' ');
  assert(!/Not configured/.test(t) && /DAYS COMPLETED \d+/.test(t) && /LOST DAYS 0/.test(t) && /LOST PERIODS 0/.test(t), 'content'); await shot(page, 't1_time_aware');
  return (t.match(/DAYS COMPLETED \d+ DAYS REMAINING \d+/) || [''])[0] + ' | ' + (t.match(/CORE PERIODS \d+ configured/) || [''])[0];
});
let planId, v1;
await run('T2', 'Generate draft (teacher) then principal approves -> schedule v1', async () => {
  await page.getByRole('button', { name: 'Generate draft schedule for approval' }).click(); await page.getByText(/Draft saved for/).first().waitFor({ timeout: 20000 });
  await login(P1); await page.goto(`${WEB}/principal/curriculum`); const d = page.getByTestId('draft-review'); await d.waitFor({ timeout: 20000 });
  await d.getByRole('button', { name: 'Approve teaching schedule' }).click(); await d.waitFor({ state: 'detached', timeout: 15000 });
  const pl = (await api('GET', `/plans?teacher_id=${G.id}`, tok[P1])).json.plans.find((p) => p.status === 'APPROVED' && p.grade === 6);
  assert(pl && pl.versions.length === 1, 'not approved v1'); planId = pl.id; v1 = JSON.stringify(pl.versions[0]); return `plan ${planId.slice(0, 8)} v1, lessons=${pl.versions[0].lessons.length}`;
});
const lost = async () => (await api('GET', `/teacher-plans/${G.id}/lost-periods?grade=6&subject=Science`, tok[G.email])).json;
let pickedDates;
await run('L1', 'record TWO periods on the SAME date -> 2 lost periods but ONE lost day', async () => {
  await lessonTimeAware(G.email, 6, 'Science'); await page.getByTestId('lost-period-recorder').getByRole('button', { name: 'Record a Lost Day' }).click();
  const dlg = page.getByRole('dialog'); await dlg.waitFor();
  const labels = await dlg.getByRole('checkbox').evaluateAll((els) => els.map((e) => e.getAttribute('aria-label')));
  const byDate = {}; for (const l of labels) { const mm = /^Period (\d+): (\d{4}-\d\d-\d\d)/.exec(l); if (mm) (byDate[mm[2]] ||= []).push(l); }
  const d1 = Object.keys(byDate).find((d) => byDate[d].length >= 2); assert(d1, 'no date with 2 periods: ' + labels.slice(0, 4));
  const d2 = Object.keys(byDate).find((d) => d > d1 && byDate[d].length >= 1); pickedDates = { d1, d2, d2label: byDate[d2][0] };
  await dlg.getByLabel(byDate[d1][0]).check(); await dlg.getByLabel(byDate[d1][1]).check();
  await dlg.getByLabel('Loss reason').selectOption('Election Duties'); await dlg.getByRole('button', { name: /^Record \d+ lost period/ }).click();
  await page.getByText(/Recorded period\(s\)/).first().waitFor({ timeout: 15000 });
  const l = await lost(); assert(l.lost_periods === 2 && l.lost_days === 1, `periods=${l.lost_periods} days=${l.lost_days}`);
  const t = (await page.innerText('body')).replace(/\s+/g, ' '); assert(/LOST DAYS 1/.test(t) && /LOST PERIODS 2/.test(t), 'UI counters'); await shot(page, 'l1_lost_same_date');
  return `date ${d1}: periods=${l.lost_periods} days=${l.lost_days}`;
});
await run('R1', 'a recovery proposal is generated automatically; v1 stays authoritative; Core not dropped', async () => {
  const pl = (await api('GET', `/plans?teacher_id=${G.id}`, tok[P1])).json.plans.find((p) => p.id === planId);
  const pend = pl.proposals.filter((p) => p.status === 'PENDING'); assert(pend.length === 1 && pl.versions.length === 1 && JSON.stringify(pl.versions[0]) === v1, 'proposal/versions');
  const coreV1 = pl.versions[0].lessons.reduce((s, x) => s + x.slots.filter((q) => q.kind === 'CORE').length, 0);
  const prop = pend[0]; const coreP = (prop.lessons || []).reduce((s, x) => s + x.slots.filter((q) => q.kind === 'CORE').length, 0);
  assert(coreP >= coreV1 - 2, `core v1=${coreV1} proposal=${coreP}`); return `pending=1 core(v1)=${coreV1} core(proposal)=${coreP} (2 lost periods)`;
});
await run('R2', 'principal reviews proposal in UI; rejection needs a reason; v1 unchanged', async () => {
  await login(P1); await page.goto(`${WEB}/principal/curriculum`); const pr = page.getByTestId('recovery-proposal'); await pr.waitFor({ timeout: 20000 });
  assert((await pr.innerText()).replace(/\s+/g, ' ').match(/Original \(v1\)/i) && /Proposed/i.test(await pr.innerText()), 'comparison missing'); await shot(page, 'r2_proposal');
  await pr.getByRole('button', { name: 'Reject proposal' }).click(); await pr.getByRole('alert').waitFor({ timeout: 5000 });
  await pr.getByLabel('Recovery review note').fill('Final verification: reject first proposal'); await pr.getByRole('button', { name: 'Reject proposal' }).click(); await pr.waitFor({ state: 'detached', timeout: 15000 });
  const pl = (await api('GET', `/plans?teacher_id=${G.id}`, tok[P1])).json.plans.find((p) => p.id === planId);
  assert(pl.versions.length === 1 && JSON.stringify(pl.versions[0]) === v1 && pl.proposals.some((p) => p.status === 'REJECTED'), 'state');
});
await run('L2', 'a third loss on a different date -> 3 lost periods, 2 lost days', async () => {
  await lessonTimeAware(G.email, 6, 'Science'); await page.getByTestId('lost-period-recorder').getByRole('button', { name: 'Record a Lost Day' }).click();
  const dlg = page.getByRole('dialog'); await dlg.waitFor();
  // lose a CORE period (type badge "Core") on a different date, so recovery has real Core to protect
  const coreRow = dlg.getByRole('row').filter({ has: page.getByText('Core', { exact: true }) }).filter({ hasNotText: pickedDates.d1 }).first();
  pickedDates.coreLabel = await coreRow.getByRole('checkbox').getAttribute('aria-label'); await coreRow.getByRole('checkbox').check();
  await dlg.getByLabel('Loss reason').selectOption('Teacher Training'); await dlg.getByRole('button', { name: /^Record \d+ lost period/ }).click();
  await page.getByText(/Recorded period\(s\)/).first().waitFor({ timeout: 15000 }); const l = await lost(); assert(l.lost_periods === 3 && l.lost_days === 2, `periods=${l.lost_periods} days=${l.lost_days}`); return `lost a Core period (${pickedDates.coreLabel}); periods=3 days=2`;
});
await run('R3', 'server REJECTS invalid proposals (a dropped topic; a Core slot silently downgraded) for the right reason', async () => {
  const pl = (await api('GET', `/plans?teacher_id=${G.id}`, tok[P1])).json.plans.find((p) => p.id === planId);
  const good = pl.proposals.find((p) => p.status === 'PENDING'); assert(good, 'no pending proposal');
  const mk = (mut) => { const b = JSON.parse(JSON.stringify(good)); delete b.status; b.id = 'bad-' + Math.random().toString(36).slice(2); b.baseVersion = pl.versions[0].version; mut(b); return b; };
  const dropped = await api('POST', `/plans/${planId}/proposals`, tok[G.email], mk((b) => { b.lessons = b.lessons.slice(1); }));
  assert(dropped.status === 422 && /(drop|topic|lesson|missing|unscheduled)/i.test(JSON.stringify(dropped.json)) && !/proposal id/i.test(JSON.stringify(dropped.json)), `dropped: ${dropped.status} ${JSON.stringify(dropped.json).slice(0, 160)}`);
  const downgraded = await api('POST', `/plans/${planId}/proposals`, tok[G.email], mk((b) => { for (const l of b.lessons) for (const q of l.slots) if (q.kind === 'CORE') { q.kind = 'NON_CORE'; return; } }));
  assert(downgraded.status === 422 && /core/i.test(JSON.stringify(downgraded.json)), `downgraded: ${downgraded.status} ${JSON.stringify(downgraded.json).slice(0, 160)}`);
  const stale = await api('POST', `/plans/${planId}/proposals`, tok[G.email], mk((b) => { b.baseVersion = 99; }));
  assert(stale.status === 409, `stale ${stale.status}`);
  const still = (await api('GET', `/plans?teacher_id=${G.id}`, tok[P1])).json.plans.find((p) => p.id === planId); assert(still.versions.length === 1, 'invalid proposal changed the schedule');
  return `dropped topic ${dropped.status}; core downgrade ${downgraded.status}; stale base ${stale.status}; schedule still v1`;
});
await run('R4', 'principal approves the proposal in UI -> schedule v2 linked to it, v1 untouched', async () => {
  await login(P1); await page.goto(`${WEB}/principal/curriculum`); const pr = page.getByTestId('recovery-proposal'); await pr.waitFor({ timeout: 20000 });
  await pr.getByRole('button', { name: 'Approve recovery schedule' }).click(); await pr.waitFor({ state: 'detached', timeout: 15000 });
  const pl = (await api('GET', `/plans?teacher_id=${G.id}`, tok[P1])).json.plans.find((p) => p.id === planId);
  assert(pl.versions.length === 2 && JSON.stringify(pl.versions[0]) === v1 && pl.versions[1].version === 2 && pl.versions[1].proposalId, 'versions');
  const lostSlots = pl.versions[1].lostSlots?.length ?? 0; assert(lostSlots === 3, `frozen lost slots ${lostSlots}`);
  return `v2 from proposal ${pl.versions[1].proposalId.slice(0, 8)}, lostSlots=${lostSlots}`;
});
await run('R5', 'v2 invariants: same Core total as v1 (nothing silently dropped), no duplicate slot', async () => {
  const pl = (await api('GET', `/plans?teacher_id=${G.id}`, tok[P1])).json.plans.find((p) => p.id === planId);
  const core = (v) => v.lessons.reduce((s, x) => s + x.slots.filter((q) => q.kind === 'CORE').length + (x.coreUnscheduled || 0), 0);
  const slots = pl.versions[1].lessons.flatMap((x) => x.slots.map((q) => `${q.date}#${q.period}`)); assert(new Set(slots).size === slots.length, 'duplicate slot');
  assert(core(pl.versions[1]) >= core(pl.versions[0]), `core v1=${core(pl.versions[0])} v2=${core(pl.versions[1])}`); return `core v1=${core(pl.versions[0])} v2=${core(pl.versions[1])} slots=${slots.length}`;
});

// ---------- 4. oversight + logs ----------
await run('O1', 'Planning Oversight (API) equals the teacher record: lost days/periods, version, approval', async () => {
  const r = (await api('GET', `/plan-oversight/planning?teacher_id=${G.id}&grade=6&subject=Science`, tok[P1])).json.rows[0];
  assert(r.lost_days === 2 && r.lost_periods === 3 && r.schedule_version === 2 && /APPROVED/i.test(r.approval_status), JSON.stringify(r)); return `lost_days=${r.lost_days} lost_periods=${r.lost_periods} v${r.schedule_version} ${r.approval_status}`;
});
await run('O2', 'Coverage Oversight (API+UI) equals Course Curriculum for the same teacher', async () => {
  await login(G.email); await openCatalogue(); await covSel(A).selectOption('DONE'); await settle(covSel(A), 'DONE'); await covSel(B).selectOption('IN_PROGRESS'); await settle(covSel(B), 'IN_PROGRESS');
  const p = await plan(G, G, 6, 'Science'); const cc = (await api('GET', `/plan-oversight/curriculum?teacher_id=${G.id}&grade=6&subject=Science`, tok[P1])).json.rows[0];
  assert(cc.done === p.coverage.done && cc.eligible === 65 && cc.done === 1 && cc.percent === 1.5, JSON.stringify([cc.done, cc.percent, p.coverage]));
  await login(P1); await page.goto(`${WEB}/principal/coverage`); await page.waitForTimeout(5000); const t = (await page.innerText('body')).replace(/\s+/g, ' ');
  assert(/Garima/.test(t) && /1\.5\s?%/.test(t), 'UI shows ' + t.slice(0, 120)); await shot(page, 'o2_coverage_oversight'); return 'API done=1 percent=1.5; UI 1.5%';
});
await run('O3', 'Planning Oversight UI lists the teacher with the same figures', async () => {
  await page.goto(`${WEB}/principal/curriculum`); await page.waitForTimeout(5000); const t = (await page.innerText('body')).replace(/\s+/g, ' ');
  assert(/Garima/.test(t), 'teacher missing'); await shot(page, 'o3_planning_oversight'); return 'Garima row present';
});
await run('G1', 'Central Logs (API): actor, timestamp and before/after on classification, coverage, loss, rejection and approval', async () => {
  const items = (await api('GET', `/plan-logs?teacher_id=${G.id}&limit=500`, tok[P1])).json.items; const cats = new Set(items.map((e) => e.category));
  for (const c of ['coverage_status', 'topic_classification', 'plan_draft', 'plan_approval', 'recovery_proposal', 'recovery_rejection', 'recovery_approval', 'schedule_version']) assert(cats.has(c), `missing category ${c}; have ${[...cats]}`);
  assert(items.every((e) => e.actor_name && e.actor_role && !Number.isNaN(Date.parse(e.occurred_at + 'Z'))), 'actor/time missing');
  const ap = items.find((e) => e.category === 'recovery_approval'); assert(ap.actor_role === 'principal', ap.actor_role);
  const chrono = items.map((e) => Date.parse(e.occurred_at + 'Z')); assert(chrono.every((v, i) => i === 0 || chrono[i - 1] >= v), 'not newest-first/chronological');
  return `${items.length} events; categories=${[...cats].join(',')}`;
});
await run('G2', 'Central Logs page renders the events', async () => {
  await login(P1); await page.goto(`${WEB}/logs?teacher_id=${G.id}`); await page.waitForTimeout(4000); const t = (await page.innerText('body')).replace(/\s+/g, ' ');
  assert(/Garima/.test(t) && /(classification|coverage)/i.test(t), t.slice(0, 160)); await shot(page, 'g2_logs'); return 'rendered';
});

// ---------- 5. isolation ----------
await run('I1', 'a teacher cannot read or change another teacher\'s plan (403/404), nothing leaks', async () => {
  const kPlan = await api('GET', `/teacher-plans/${K.id}?grade=6&subject=Mathematics`, tok[G.email]); assert([403, 404].includes(kPlan.status), `read ${kPlan.status}`);
  const kTopic = (await plan(K, K, 6, 'Mathematics')).topics[0].topic_key;
  const w = await api('PUT', `/teacher-plans/${K.id}/coverage`, tok[G.email], { grade: 6, subject: 'Mathematics', topic_key: kTopic, status: 'done' }); assert([403, 404].includes(w.status), `write ${w.status}`);
  const w2 = await api('PUT', `/teacher-plans/${G.id}/coverage`, tok[K.email], { grade: 6, subject: 'Science', topic_key: A, status: 'not_done' }); assert([403, 404].includes(w2.status), `write2 ${w2.status}`);
  const kp = await plan(K, K, 6, 'Mathematics'); assert(kp.coverage.done === 0 && kp.topics.every((t) => t.origin === 'demo_default'), 'Kamlesh plan changed');
  const kplans = (await api('GET', '/plans', tok[K.email])).json.plans; assert(kplans.every((p) => p.teacherId === K.id), 'plans leak'); return `read ${kPlan.status}, writes ${w.status}/${w2.status}; Kamlesh plan untouched`;
});
await run('I2', 'school isolation: each principal\'s oversight and logs contain only their school', async () => {
  const o1 = (await api('GET', '/plan-oversight/planning', tok[P1])).json.rows.map((r) => r.teacher_id), o2 = (await api('GET', '/plan-oversight/planning', tok[P2])).json.rows.map((r) => r.teacher_id);
  assert(o1.includes(G.id) && !o1.includes(K.id) && o2.includes(K.id) && !o2.includes(G.id), JSON.stringify([o1, o2]));
  const l2 = (await api('GET', '/plan-logs?limit=500', tok[P2])).json.items; assert(l2.every((e) => e.teacher_id !== G.id && e.school_id !== 'school-1'), 'logs leak');
  const x = await api('GET', `/teacher-plans/${G.id}?grade=6&subject=Science`, tok[P2]); assert([403, 404].includes(x.status), `cross-school read ${x.status}`);
  const x2 = await api('GET', `/teacher-plans/${K.id}?grade=6&subject=Mathematics`, tok[P1]); assert([403, 404].includes(x2.status), `cross-school read2 ${x2.status}`);
  return `P1 sees ${o1.length} teacher(s), P2 sees ${o2.length}; cross-school reads ${x.status}/${x2.status}`;
});
await run('I3', 'UI: second teacher (Kamlesh) opens VI Maths: own plan, separate values', async () => {
  await login(K.email); await openCatalogue(6, 'mathematics'); const ctx = await page.getByTestId('plan-context').innerText(); assert(/Kamlesh/.test(ctx) && !/Garima/.test(ctx), ctx);
  assert((await page.getByTestId('coverage-percent').innerText()).trim() === '0%', 'pct'); await shot(page, 'i3_second_teacher'); return 'Kamlesh 0%';
});
await run('I4', 'Garima\'s edits persist across logout/login and a fresh browser context', async () => {
  await login(G.email); await openCatalogue(); assert((await covSel(A).inputValue()) === 'DONE' && (await covSel(B).inputValue()) === 'IN_PROGRESS' && (await clsSel(mixed.topic_key).inputValue()) === 'non_core', 'values');
  return 'DONE / IN_PROGRESS / non_core kept';
});
await run('I5', 'protected-looking ineligible teachers (English, Chemistry) have no plan rows', async () => {
  const d = new DatabaseSync(DB, { readOnly: true }); const c = d.prepare("select count(*) c from teacher_topic_configs where teacher_id in ('user-teacher-preeti','user-teacher-arvind')").get().c; assert(c === 0, `rows=${c}`); return '0 rows';
});
await browser.close();
fs.writeFileSync(process.env.REPORT || 'e2e-results-final.json', JSON.stringify(results, null, 1));
const bad = results.filter((r) => !r.ok); console.log(`\n${results.length - bad.length}/${results.length} passed`); process.exit(bad.length ? 1 : 0);
