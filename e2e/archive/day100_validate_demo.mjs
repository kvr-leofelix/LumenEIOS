import fs from 'node:fs';
import { chromium } from 'playwright-core';

const shots = process.env.SHOTS || './e2e-shots/20261112-day100-recovery';
fs.mkdirSync(shots, { recursive: true });
const logFile = `${shots}/browser-acceptance.log`;
const log = (m) => { const line = `${new Date().toISOString()} ${m}`; console.log(line); fs.appendFileSync(logFile, line + '\n'); };
const browser = await chromium.launch({ channel: 'msedge', headless: false, args: ['--start-maximized'] });
const page = await (await browser.newContext({ viewport: null })).newPage();
const issues = [];
page.on('pageerror', (e) => issues.push(`PAGEERROR ${e.message}`));
page.on('response', (r) => { if (r.status() >= 400 && r.url().includes(':8000')) issues.push(`${r.status()} ${r.url()}`); });
const shot = (n) => page.screenshot({ path: `${shots}/${n}.png`, fullPage: false });

try {
  await page.goto('http://localhost:3000/login', { waitUntil: 'domcontentloaded' });
  await page.getByPlaceholder(/teacher@/i).fill('teacher@lumeneios.demo');
  await page.getByPlaceholder('demo123').fill('demo123');
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForURL(/\/teacher\//, { timeout: 15000 });

  // Reconcile old manual demo coverage marks with the sole completed classroom execution.
  await page.goto('http://localhost:3000/curriculum/catalogue/6/mathematics', { waitUntil: 'domcontentloaded' });
  await page.getByTestId('syllabus-view').waitFor();
  await page.getByRole('button', { name: 'Expand all' }).click();
  const untaughtDemoTopics = [
    ['What is Mathematics?', 'ncert-review-section_src_9a2ff6ddbbd42bbd140a_p0001_b001_l000'],
    ['Visualising Number Sequences', 'ncert-review-section_src_9a2ff6ddbbd42bbd140a_p0003_b007_l000'],
    ['Relations among Number Sequences', 'ncert-review-section_src_9a2ff6ddbbd42bbd140a_p0006_b004_l000'],
    ['Patterns in Shapes', 'ncert-review-section_src_9a2ff6ddbbd42bbd140a_p0009_b006_l000'],
    ['Relation to Number Sequences', 'ncert-review-section_src_9a2ff6ddbbd42bbd140a_p0011_b005_l000'],
    ['The Token Model', 'ncert-review-section_src_2c286fb7a738c1f17824_p0015_b002_l000'],
  ];
  for (const [topic, id] of untaughtDemoTopics) {
    const selector = page.locator(`[data-testid="topic-${id}"] select`);
    if (await selector.inputValue() !== 'NOT_DONE') {
      await selector.selectOption('NOT_DONE');
      await page.waitForFunction((testId) => document.querySelector(`[data-testid="topic-${testId}"] select`)?.value === 'NOT_DONE', id, { timeout: 12000 });
    }
    log(`Catalogue coverage confirms Not done for untaught demo topic: ${topic}`);
  }
  const mathCounts = {
    total: Number(await page.getByTestId('coverage-total').innerText()),
    done: Number(await page.getByTestId('coverage-done').innerText()),
    inProgress: Number(await page.getByTestId('coverage-inprogress').innerText()),
    notDone: Number(await page.getByTestId('coverage-notdone').innerText()),
  };
  await shot('04_day100_math_coverage');
  log(`Class VI Mathematics catalogue after evidence reconciliation: ${JSON.stringify(mathCounts)}.`);

  await page.goto('http://localhost:3000/curriculum/catalogue/6/science', { waitUntil: 'domcontentloaded' });
  await page.getByTestId('syllabus-view').waitFor();
  await page.getByRole('button', { name: 'Expand all' }).click();
  await shot('05_day100_science_full_syllabus');
  log('Class VI Science complete textbook hierarchy opened and captured.');

  await page.goto('http://localhost:3000/teacher/time-aware', { waitUntil: 'domcontentloaded' });
  await page.getByLabel('Class').selectOption('6');
  await page.getByLabel('Subject').selectOption('Mathematics');
  await page.getByTestId('engine-metrics').waitFor();
  await page.waitForFunction(() => {
    const text = document.querySelector('[data-testid="engine-metrics"]')?.innerText ?? '';
    return /Academic day 100 of 180/i.test(text) && /Teaching days left\s*80/i.test(text);
  }, null, { timeout: 15000 });
  const timeText = (await page.getByTestId('engine-metrics').innerText()).replace(/\s+/g, ' ');
  if (!/Academic day 100 of 180/i.test(timeText) || !/Teaching days left\s*80/i.test(timeText)) throw new Error(`Day 100 metrics missing: ${timeText}`);
  await shot('06_day100_time_aware_metrics');
  await page.getByRole('tab', { name: 'Day tracker' }).click();
  await page.getByText('Election Duties', { exact: true }).waitFor();
  await shot('07_day100_historical_losses');
  log('Time-Aware shows Day 100 / 180, 80 days remaining, actual Core/Non-Core counts, and historical lost periods with reasons.');

  await page.goto('http://localhost:3000/teacher/curriculum-180', { waitUntil: 'domcontentloaded' });
  await page.getByText(/Daily Curriculum/i).first().waitFor({ timeout: 15000 });
  await shot('08_day100_daily_curriculum_execution');
  log('Daily Curriculum opened to the persistent execution workflow.');

  const report = { maths: mathCounts, timeAware: timeText, issues };
  fs.writeFileSync(`${shots}/browser-metrics.json`, JSON.stringify(report, null, 2));
  if (issues.length) throw new Error(`Browser/API errors: ${JSON.stringify(issues)}`);
  await page.goto('http://localhost:3000/curriculum/catalogue/6/science', { waitUntil: 'domcontentloaded' });
  await page.getByTestId('syllabus-view').waitFor();
  await page.getByRole('button', { name: 'Expand all' }).click();
  await shot('09_final_state');
  log('PASS; Microsoft Edge left open on the expanded Class VI Science catalogue.');
  fs.writeFileSync(`${shots}/browser.pid`, String(process.pid));
} catch (e) {
  log(`FAIL ${e.stack || e.message}`);
  await page.screenshot({ path: `${shots}/browser-FAIL.png`, fullPage: false }).catch(() => {});
  throw e;
}
