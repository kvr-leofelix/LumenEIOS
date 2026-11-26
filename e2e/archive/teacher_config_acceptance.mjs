// Real-browser (Edge via Playwright) acceptance of the inline Core/Non-Core + coverage controls on the existing Curriculum
// Catalogue screen. Run against a FRESH isolated database: see docs/CURRICULUM_SETUP.md.
//   WEB_URL=http://127.0.0.1:5180 API_URL=http://127.0.0.1:8010/api/v1 SHOTS=./e2e-shots/config node e2e/teacher_config_acceptance.mjs
import { API, WEB, assert, launch, shot } from '../lib.mjs';
const { page, browser, version } = await launch();
const E = process.env;  // defaults = fresh-database roster; override for another roster
const T1 = { email: E.T1_EMAIL || 'teacher@lumeneios.demo', id: E.T1_ID || 'user-teacher-garima', name: E.T1_NAME || 'Garima' };
const T2 = { email: E.T2_EMAIL || 'kamlesh@lumeneios.demo', name: E.T2_NAME || 'Kamlesh', grade: E.T2_GRADE || '6', subject: E.T2_SUBJECT || 'mathematics', count: Number(E.T2_COUNT || 65) };
const PRINCIPAL = E.PRINCIPAL_EMAIL || 'principal@lumeneios.demo';
const out = [];
const log = (id, ok, note) => { out.push({ id, ok, note }); console.log(`${ok ? 'PASS' : 'FAIL'} ${id} ${note}`); };
const login = async (email) => {
  await page.goto(`${WEB}/login`); await page.evaluate(() => localStorage.clear()); await page.goto(`${WEB}/login`);
  await page.locator('input').first().fill(email); await page.locator('input[type="password"]').fill('demo123');
  await page.getByRole('button', { name: /^Sign in/ }).click();
  await page.waitForURL((u) => !u.pathname.includes('login'), { timeout: 20000 });
};
const open = async (g, s) => {
  await page.goto(`${WEB}/curriculum/catalogue/${g}/${s}`);
  await page.waitForSelector('[data-testid="plan-context"]', { timeout: 30000 });
  await page.getByText('Expand all').click();
};
const pct = async () => (await page.getByTestId('coverage-percent').innerText()).trim();
const run = async (id, fn) => { try { const n = await fn(); log(id, true, n ?? ''); } catch (e) { log(id, false, String(e.message).split('\n')[0]); await shot(page, `${id}_FAIL`); } };
console.log('Browser', version);
let t1 = {};
await run('V1 login+open Garima Class VI Science', async () => {
  await login(T1.email); await open(6, 'science');
  const ctx = await page.getByTestId('plan-context').innerText();
  assert(new RegExp(T1.name).test(ctx) && /Class VI/.test(ctx) && /Science/.test(ctx), ctx);
  await shot(page, 'v1_class6_science'); return ctx.slice(0, 120);
});
await run('V2 full syllabus (12 chapters, 65 topics) + controls on every topic', async () => {
  const chapters = await page.locator('[data-testid^="chapter-ncert"]').count();
  const classSel = await page.locator('select[aria-label^="Core or Non-Core"]').count();
  const covSel = await page.locator('select[aria-label^="Coverage status"]').count();
  const unconf = await page.locator('[data-testid^="unconfigured-"]').count();
  assert(chapters === 12 && classSel === 65 && covSel === 65 && unconf === 0, `chapters=${chapters} class=${classSel} cov=${covSel} unconfigured=${unconf}`);
  return `chapters=${chapters} classification selects=${classSel} coverage selects=${covSel} not-configured=${unconf}`;
});
const cls = (n) => page.locator('select[aria-label^="Core or Non-Core"]').nth(n);
const cov = (n) => page.locator('select[aria-label^="Coverage status"]').nth(n);
await run('V3 change topic 0 classification and topic 1 to In progress, topic 2 to Done', async () => {
  t1.c0 = await cls(0).inputValue(); t1.c1 = await cls(1).inputValue(); t1.c2 = await cls(2).inputValue();
  t1.new0 = t1.c0 === 'non_core' ? 'core' : 'non_core';
  await cls(0).selectOption(t1.new0); await page.waitForFunction((v) => document.querySelectorAll('select[aria-label^="Core or Non-Core"]')[0].value === v && !document.querySelectorAll('select[aria-label^="Core or Non-Core"]')[0].disabled, t1.new0);
  await cov(1).selectOption('IN_PROGRESS'); await page.waitForFunction(() => document.querySelectorAll('select[aria-label^="Coverage status"]')[1].value === 'IN_PROGRESS' && !document.querySelectorAll('select[aria-label^="Coverage status"]')[1].disabled);
  await cov(2).selectOption('DONE'); await page.waitForFunction(() => document.querySelectorAll('select[aria-label^="Coverage status"]')[2].value === 'DONE' && !document.querySelectorAll('select[aria-label^="Coverage status"]')[2].disabled);
  t1.pct = await pct(); assert(t1.pct === (Math.round(1000 / 65) / 10).toString() + '%', t1.pct);
  await shot(page, 'v3_after_changes'); return `topic0 ${t1.c0}->${t1.new0}; coverage ${t1.pct}`;
});
await run('V4 reload keeps changes', async () => {
  await open(6, 'science');
  assert(await cls(0).inputValue() === t1.new0 && await cov(1).inputValue() === 'IN_PROGRESS' && await cov(2).inputValue() === 'DONE' && await pct() === t1.pct, 'values lost');
  assert(await cls(1).inputValue() === t1.c1, 'untouched topic changed'); await shot(page, 'v4_after_reload');
});
await run('V5 another teacher (Kamlesh, Mathematics) has an independent, fully configured plan', async () => {
  await login(T2.email); await open(T2.grade, T2.subject);
  const ctx = await page.getByTestId('plan-context').innerText(); assert(new RegExp(T2.name).test(ctx), ctx);
  assert(await page.locator('select[aria-label^="Core or Non-Core"]').count() === T2.count, `expected ${T2.count} topics`);
  assert(await page.locator('[data-testid^="unconfigured-"]').count() === 0, 'unconfigured topics');
  assert(await pct() === '0%', await pct()); await shot(page, 'v5_second_teacher'); return ctx.slice(0, 100);
});
await run('V6 back to Garima: her changes persist', async () => {
  await login(T1.email); await open(6, 'science');
  assert(await cls(0).inputValue() === t1.new0 && await cov(2).inputValue() === 'DONE' && await pct() === t1.pct, 'lost');
});
await run('V7 principal sees the same saved plan read-only via ?teacher=', async () => {
  await login(PRINCIPAL);
  await page.goto(`${WEB}/curriculum/catalogue/6/science?teacher=${T1.id}`);
  await page.waitForSelector('[data-testid="plan-context"]', { timeout: 30000 }); await page.getByText('Expand all').click();
  assert(await pct() === t1.pct, await pct()); assert(await cls(0).isDisabled(), 'should be read-only'); assert(await cls(0).inputValue() === t1.new0, 'differs'); await shot(page, 'v7_principal_view');
});
await run('V8 all six class/subject combos load the full syllabus', async () => {
  await login(T1.email); const exp = { 'science-6': 65, 'science-7': 78, 'science-8': 84 };
  for (const [k, n] of Object.entries(exp)) { const [s, g] = k.split('-'); await open(g, s); const c = await page.locator('select[aria-label^="Core or Non-Core"]').count(); assert(c === n, `${k}: ${c} != ${n}`); }
});
await browser.close();
console.log(JSON.stringify(out.map((r) => [r.id, r.ok])));
process.exit(out.every((r) => r.ok) ? 0 : 1);
