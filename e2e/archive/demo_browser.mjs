// Visible (headed) Microsoft Edge demonstration of the running application. Signs in as the demo teacher through the real
// login form, walks Curriculum Catalogue -> Time-Aware Engine -> Daily Curriculum, then leaves the window open.
// Usage: node e2e/demo_browser.mjs   (env: SHOTS=<dir>, WEB_URL, API_URL)
import fs from 'node:fs';
import { chromium } from 'playwright-core';

const WEB = process.env.WEB_URL || 'http://localhost:3000';
const API = process.env.API_URL || 'http://localhost:8000/api/v1';
const SHOTS = process.env.SHOTS || './e2e-shots/live-demo';
const SYLLABUS_DATASET_PATH = process.env.SYLLABUS_DATASET || new URL('../../../scratchpad/acceptance/recovered_ncert_dataset.json', import.meta.url);
const restoredDataset = JSON.parse(fs.readFileSync(SYLLABUS_DATASET_PATH, 'utf8'));
if (restoredDataset.id !== 'import-mwcgxn30' || restoredDataset.textbooks?.length !== 8 || restoredDataset.nodes?.length !== 531) {
  throw new Error('The recovered complete syllabus dataset is missing or incomplete; refusing to start a sample-only demo.');
}
fs.mkdirSync(SHOTS, { recursive: true });
const LOG = `${SHOTS}/demo.log`;
const log = (m) => { const line = `${new Date().toISOString()} ${m}`; console.log(line); fs.appendFileSync(LOG, line + '\n'); };

const browser = await chromium.launch({ channel: 'msedge', headless: false, args: ['--start-maximized'] });
const context = await browser.newContext({ viewport: null });
const page = await context.newPage();
const problems = [];
page.on('pageerror', (e) => problems.push('PAGEERROR ' + e.message));
page.on('response', (r) => { if (r.status() >= 400 && r.url().includes(':8000')) problems.push(`${r.status()} ${r.url().replace('http://localhost:8000/api/v1', '')}`); });
const shot = (n) => page.screenshot({ path: `${SHOTS}/${n}.png`, fullPage: false });
const ok = (c, m) => { if (!c) throw new Error(m); log('OK   ' + m); };
const txt = async (id) => (await page.getByTestId(id).innerText()).replace(/\s+/g, ' ').trim();
const ready = () => page.waitForFunction(() => document.querySelector('[data-testid="curriculum-catalogue"]') && !/Loading syllabus coverage/.test(document.body.innerText), null, { timeout: 20000 });
const storeReady = () => page.waitForFunction(() => /Shared planning store \(backend\)/.test(document.body.innerText), null, { timeout: 20000 });

async function setupDay100() {
  const login = await fetch(`${API}/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'admin@lumeneios.demo', password: 'demo123' }) });
  if (!login.ok) throw new Error(`isolated demo admin login failed: ${login.status}`);
  const { access_token: token } = await login.json();
  const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
  const currentResponse = await fetch(`${API}/planning/workspace`, { headers });
  if (!currentResponse.ok) throw new Error(`isolated planning workspace unavailable: ${currentResponse.status}`);
  const current = await currentResponse.json();

  const ensureRestoredSyllabus = async (workspace, revision) => {
    const existing = workspace.datasets?.find((dataset) => dataset.id === restoredDataset.id);
    if (existing) {
      if (JSON.stringify(existing) !== JSON.stringify(restoredDataset)) throw new Error('The recovered syllabus ID exists with different contents; refusing to continue.');
      log(`Verified restored syllabus ${existing.id}: ${existing.textbooks.length} textbooks, ${existing.nodes.length} structural nodes.`);
      return;
    }
    if (workspace.datasets?.length) throw new Error('A different syllabus dataset is already stored; refusing to replace or mix datasets.');
    const at = new Date().toISOString();
    const state = {
      ...workspace,
      datasets: [restoredDataset],
      audit: [...(workspace.audit || []), {
        id: `restore-syllabus-${Date.now()}`, at, action: 'SYLLABUS_IMPORT',
        summary: 'Initialize isolated demo with the recovered full reviewed structural syllabus',
        actor: { id: 'demo-admin', name: 'Demo Administrator', role: 'admin' },
      }],
    };
    const saved = await fetch(`${API}/planning/workspace`, {
      method: 'PUT', headers,
      body: JSON.stringify({ expected_revision: revision, action: 'SYLLABUS_IMPORT', summary: 'Initialize isolated demo with recovered complete syllabus structure', state }),
    });
    if (!saved.ok) throw new Error(`Recovered syllabus import failed: ${saved.status} ${await saved.text()}`);
    log(`Imported recovered syllabus ${restoredDataset.id}: ${restoredDataset.textbooks.length} textbooks, ${restoredDataset.nodes.length} structural nodes.`);
  };

  const planningDates = [];
  for (let d = new Date('2026-04-01T00:00:00Z'); planningDates.length < 180; d.setUTCDate(d.getUTCDate() + 1)) {
    if ([1, 2, 3, 4, 5].includes(d.getUTCDay())) planningDates.push(d.toISOString().slice(0, 10));
  }
  const asOf = planningDates[99];
  if (current.state) {
    const s = current.state;
    if (s.asOf !== asOf || s.config?.horizonDays !== 180 || (s.plans || []).length || Object.keys(s.classifications || {}).length) {
      throw new Error('The isolated demo database already has a different planning workspace; refusing to overwrite it.');
    }
    await ensureRestoredSyllabus(s, current.revision);
    log(`Verified existing isolated Day 100 workspace at revision ${current.revision}: ${asOf}, 180 instructional days, 80 remaining.`);
    return;
  }
  if (current.revision !== 0) throw new Error('The isolated demo database has unexpected revisions; refusing to overwrite it.');
  const state = {
    schemaVersion: 2,
    config: { year: '2026-2027', start: '2026-04-01', end: '2027-03-31', weekdays: [1, 2, 3, 4, 5], entries: [], periodsPerDay: 8, periodMinutes: 40, subjectPeriodsPerDay: { Mathematics: 1, Science: 1 }, horizonDays: 180 },
    configHistory: [], datasets: [], classifications: {}, relationships: [], plans: [], coverage: {}, asOf,
    audit: [{ id: `day100-${Date.now()}`, at: new Date().toISOString(), action: 'CONFIG_SAVE', summary: 'Configured the isolated 180 instructional-day demonstration horizon and Day 100 reference date.', actor: { id: 'demo-admin', name: 'Demo Admin', role: 'admin' } }],
  };
  const saved = await fetch(`${API}/planning/workspace`, { method: 'PUT', headers, body: JSON.stringify({ expected_revision: 0, action: 'CONFIG_SAVE', summary: 'Isolated Day 100 demonstration calendar', state }) });
  if (!saved.ok) throw new Error(`could not configure isolated Day 100 calendar: ${saved.status} ${await saved.text()}`);
  const created = await saved.json();
  await ensureRestoredSyllabus(created.state, created.revision);
  log(`Day 100 demo calendar saved: academic day 100 is ${asOf}; 80 instructional days remain within the 180-day horizon. No syllabus records or teaching requirements were fabricated.`);
}

try {
  await setupDay100();
  // 5-6. Open the catalogue route and sign in with the real form
  await page.goto(`${WEB}/curriculum/catalogue`);
  await page.evaluate(() => localStorage.clear());
  await page.goto(`${WEB}/login`);
  await page.getByPlaceholder('e.g. teacher@lumeneios.demo').fill('teacher@lumeneios.demo');
  await page.getByPlaceholder('demo123').fill('demo123');
  await page.getByRole('button', { name: 'Sign In to Dashboard' }).click();
  await page.waitForURL(/\/teacher\//, { timeout: 15000 });
  ok(true, 'signed in as teacher@lumeneios.demo with the login form (password verified by the backend)');

  // Curriculum Catalogue
  await page.getByRole('link', { name: /Curriculum Catalogue/ }).first().click();
  await ready();
  ok(page.url().endsWith('/curriculum/catalogue'), 'Curriculum Catalogue opened from the sidebar: ' + page.url());
  await shot('01_catalogue_home');
  await page.getByRole('button', { name: 'Class VI', exact: true }).click();
  await page.getByTestId('combo-6-science').click();
  await page.getByTestId('syllabus-view').waitFor();
  await ready();
  ok(/\/curriculum\/catalogue\/6\/science$/.test(page.url()), 'Class VI -> Science: ' + page.url());
  const total = await txt('coverage-total');
  const chapters = await page.locator('[data-testid^="chapter-"]').evaluateAll((els) => els.filter((e) => !/^chapter-(status|count)-/.test(e.getAttribute('data-testid'))).length);
  ok(Number(total) > 0 && chapters > 0, `full syllabus: ${chapters} chapters, ${total} teachable topics`);
  await page.getByRole('button', { name: 'Expand all' }).click();
  await shot('02_class6_science_expanded');

  // coverage change + persistence
  const pick = page.getByRole('combobox').last();
  const label = await pick.getAttribute('aria-label');
  const before = { done: await txt('coverage-done'), prog: await txt('coverage-inprogress'), pct: await txt('coverage-percent') };
  await pick.selectOption('IN_PROGRESS');
  await page.waitForFunction((v) => document.querySelector('[data-testid="coverage-inprogress"]')?.textContent.trim() === String(v + 1), Number(before.prog));
  const dotId = await pick.evaluate((el) => el.closest('[data-testid^="status-"]').getAttribute('data-testid').replace('status-', ''));
  const orange = await page.getByTestId(`dot-${dotId}`).evaluate((e) => getComputedStyle(e).backgroundColor);
  ok(orange === 'rgb(245, 158, 11)', `${label} -> In progress (orange ${orange}); In progress count ${before.prog} -> ${await txt('coverage-inprogress')}`);
  await shot('03_in_progress_orange');
  await pick.selectOption('DONE');
  await page.waitForFunction((v) => document.querySelector('[data-testid="coverage-done"]')?.textContent.trim() === String(v + 1), Number(before.done));
  const green = await page.getByTestId(`dot-${dotId}`).evaluate((e) => getComputedStyle(e).backgroundColor);
  ok(green === 'rgb(22, 163, 74)', `${label} -> Done (green ${green}); Done ${before.done} -> ${await txt('coverage-done')}, coverage ${before.pct} -> ${await txt('coverage-percent')}`);
  await shot('04_done_green');
  const doneNow = await txt('coverage-done'); const pctNow = await txt('coverage-percent');
  await page.reload(); await ready();
  ok((await txt('coverage-done')) === doneNow && (await txt('coverage-percent')) === pctNow, `after refresh the change persisted (Done ${doneNow}, ${pctNow})`);

  // other classes / subjects
  for (const [cls, sub] of [['Class VII', 'Mathematics'], ['Class VIII', 'Mathematics'], ['Class VI', 'Science'], ['Class VII', 'Science'], ['Class VIII', 'Science']]) {
    await page.getByRole('radio', { name: cls, exact: true }).click();
    await page.getByRole('radio', { name: sub, exact: true }).click();
    await page.waitForFunction((t) => document.querySelector('[data-testid="syllabus-view"] h2')?.textContent.includes(t), `${cls.replace('Class ', 'Class ')} · ${sub}`);
    ok(true, `${cls} ${sub}: ${await txt('coverage-total')} topics, ${await txt('coverage-percent')} covered`);
  }
  await shot('05_class8_science');
  const text = (await page.getByTestId('curriculum-catalogue').innerText());
  ok(!/unverified|inferred|review required|draft|approved|published|permission required|verified/i.test(text.replace(/\s+/g, ' ')) || false, 'no source-quality or publication labels in the catalogue');

  // Time-Aware Engine
  await page.getByRole('link', { name: /Time-Aware Engine/ }).first().click();
  await storeReady();
  await page.getByLabel('Class').selectOption('6');
  await page.getByLabel('Subject').selectOption('Science');
  await page.waitForTimeout(700);
  const timeAwareText = (await page.innerText('body')).replace(/\s+/g, ' ');
  ok(/Academic day 100 of 180/.test(timeAwareText) && /Teaching days left\s*80/i.test(timeAwareText), 'isolated calendar and remaining-day calculation agree at Day 100');
  ok(await page.getByRole('tab', { name: 'Syllabus & classification' }).count() === 0 && await page.getByRole('tab', { name: 'Requirements' }).count() === 1, 'Time-Aware has a requirements summary instead of a duplicate syllabus browser');
  ok(/not approved|without an approved requirement|missing counts/i.test(timeAwareText), 'missing approved period counts are visible and left unscheduled');
  const rows = (await page.getByRole('table', { name: 'Generated schedule' }).getByRole('row').count()) - 1;
  const tags = await page.locator('[data-testid^="ta-coverage-"]').count();
  ok(rows === Number(total) && tags === rows, `Time-Aware Engine (Class VI Science): ${rows} topics = catalogue topics, each with a read-only coverage tag`);
  const t = (await page.innerText('body')).replace(/\s+/g, ' ');
  ok(/CORE \/ NON-CORE REQUIRED\s*130 \/ 65 p/i.test(t) || /without an approved requirement|missing counts|not approved/i.test(t), 'Core/Non-Core requirements (or missing-requirement flags) shown');
  await shot('06_time_aware');
  await page.getByTestId('lost-period-recorder').scrollIntoViewIfNeeded();
  await shot('07_time_aware_lost_periods');

  // Daily Curriculum
  await page.getByRole('link', { name: /Daily Curriculum/ }).first().click();
  await storeReady();
  await page.waitForTimeout(800);
  ok(/Daily Curriculum/.test(await page.innerText('body')), 'Daily Curriculum opened: ' + page.url());
  await shot('08_daily_curriculum');
  const cp = await page.getByTestId('classroom-progress').innerText().catch(() => '');
  log('INFO classroom progress: ' + cp.replace(/\s+/g, ' '));

  // leave the window on the working catalogue
  await page.goto(`${WEB}/curriculum/catalogue/6/science`);
  await ready();
  await page.getByRole('button', { name: 'Expand all' }).click();
  await shot('09_final_state');
  log(`DONE demonstration complete; browser left open on ${page.url()}; unexpected problems: ${JSON.stringify(problems)}`);
} catch (e) {
  log('FAIL ' + e.message);
  await shot('FAIL').catch(() => {});
}
fs.writeFileSync(`${SHOTS}/browser.pid`, String(process.pid));
log('holding the browser open (close the window or stop this process to end)');
setInterval(() => {}, 1 << 30);
await new Promise(() => {});
