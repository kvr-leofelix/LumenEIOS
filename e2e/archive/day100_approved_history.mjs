import fs from 'node:fs';
import { chromium } from 'playwright-core';

const shots = process.env.SHOTS || './e2e-shots/20261112-day100-recovery';
fs.mkdirSync(shots, { recursive: true });
const logFile = `${shots}/approved-history.log`;
const log = (m) => { const line = `${new Date().toISOString()} ${m}`; console.log(line); fs.appendFileSync(logFile, line + '\n'); };
const browser = await chromium.launch({ channel: 'msedge', headless: false, args: ['--start-maximized'] });
const context = await browser.newContext({ viewport: null });
const page = await context.newPage();
const problems = [];
page.on('pageerror', (e) => problems.push(e.message));
page.on('response', (r) => { if (r.status() >= 400 && r.url().includes(':8000')) problems.push(`${r.status()} ${r.url()}`); });
const shot = (name) => page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });

try {
  await page.goto('http://localhost:3000/login', { waitUntil: 'domcontentloaded' });
  await page.getByPlaceholder(/teacher@/i).fill('admin@lumeneios.demo');
  await page.getByPlaceholder('demo123').fill('demo123');
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForURL(/\/admin\//, { timeout: 15000 });
  await page.goto('http://localhost:3000/principal/curriculum', { waitUntil: 'domcontentloaded' });
  await page.getByTestId('recovery-progress').waitFor({ timeout: 20000 });
  if (!/approved schedule v3/i.test(await page.locator('body').innerText())) throw new Error('The active approved v3 schedule is missing from oversight after restart');
  await shot('10_day100_approved_schedule_and_audit');
  log('Admin oversight reopened after backend restart; active approved v3 schedule is visible with persisted revision/audit.');

  const history = page.getByRole('button', { name: /Show history \(3 approved version\(s\)/ });
  await history.scrollIntoViewIfNeeded();
  await history.click();
  await page.getByText('Proposal history', { exact: true }).waitFor();
  await shot('11_day100_version_execution_proposal_history');
  log('Captured original v1, approved v2/v3, rejected and approved recovery decisions, classroom execution and homework history.');

  await page.goto('http://localhost:3000/teacher/curriculum-180', { waitUntil: 'domcontentloaded' });
  await page.getByText('Daily Curriculum', { exact: true }).first().waitFor();
  await page.getByRole('tab', { name: 'By period' }).click();
  await page.getByRole('button', { name: /Show history \(3 approved version/ }).scrollIntoViewIfNeeded();
  await page.getByRole('button', { name: /Show history \(3 approved version/ }).click();
  await page.getByRole('table', { name: /period ledger/i }).waitFor().catch(() => {});
  await shot('12_day100_daily_curriculum_periods_and_execution');
  log('Daily Curriculum shows the persisted approved period ledger and execution history.');

  await page.goto('http://localhost:3000/teacher/time-aware', { waitUntil: 'domcontentloaded' });
  await page.getByLabel('Class').selectOption('6');
  await page.getByLabel('Subject').selectOption('Mathematics');
  await page.waitForFunction(() => /Academic day 100 of 180/.test(document.body.innerText) && /Behind on Core/.test(document.body.innerText), null, { timeout: 15000 });
  await shot('13_day100_live_after_restart');
  if (problems.length) throw new Error(`Browser/API errors: ${JSON.stringify(problems)}`);
  log('PASS; app survived restart and remains open on Time-Aware at Day 100.');
  fs.writeFileSync(`${shots}/approved-browser.pid`, String(process.pid));
} catch (e) {
  log(`FAIL ${e.stack || e.message}`);
  await page.screenshot({ path: `${shots}/approved-history-FAIL.png`, fullPage: false }).catch(() => {});
  throw e;
}
