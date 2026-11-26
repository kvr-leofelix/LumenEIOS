import fs from 'node:fs';
import { chromium } from 'playwright-core';

const shots = process.env.SHOTS || './e2e-shots/20261112-day100-recovery';
fs.mkdirSync(shots, { recursive: true });
const logPath = `${shots}/day100.log`;
const log = (m) => { const line = `${new Date().toISOString()} ${m}`; console.log(line); fs.appendFileSync(logPath, line + '\n'); };
const browser = await chromium.launch({ channel: 'msedge', headless: false, args: ['--start-maximized'] });
const teacherContext = await browser.newContext({ viewport: null });
const teacher = await teacherContext.newPage();
const errors = [];
teacher.on('pageerror', (e) => errors.push(e.message));
teacher.on('response', (r) => { if (r.status() >= 400 && r.url().includes(':8000')) errors.push(`${r.status()} ${r.url()}`); });
const shot = (name) => teacher.screenshot({ path: `${shots}/${name}.png`, fullPage: false });
const api = 'http://localhost:8000/api/v1';

try {
  await teacher.goto('http://localhost:3000/login', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await teacher.getByPlaceholder(/teacher@/i).fill('teacher@lumeneios.demo');
  await teacher.getByPlaceholder('demo123').fill('demo123');
  await teacher.getByRole('button', { name: /sign in/i }).click();
  await teacher.waitForURL(/\/teacher\//, { timeout: 15000 });
  await teacher.goto('http://localhost:3000/teacher/time-aware', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await teacher.getByText(/Shared planning store \(backend\)/).waitFor({ timeout: 20000 });
  await teacher.getByLabel('Class').selectOption('6');
  await teacher.getByLabel('Subject').selectOption('Mathematics');
  await teacher.getByText('Recalculate with current configuration', { exact: true }).click();
  await teacher.getByText(/Recalculation proposal created/i).waitFor({ timeout: 15000 });
  log('Teacher generated a configuration-change proposal against the approved v2 plan; awaiting Admin review.');

  const adminContext = await browser.newContext({ viewport: null });
  const admin = await adminContext.newPage();
  admin.on('pageerror', (e) => errors.push(e.message));
  admin.on('response', (r) => { if (r.status() >= 400 && r.url().includes(':8000')) errors.push(`${r.status()} ${r.url()}`); });
  await admin.goto('http://localhost:3000/login', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await admin.getByPlaceholder(/teacher@/i).fill('admin@lumeneios.demo');
  await admin.getByPlaceholder('demo123').fill('demo123');
  await admin.getByRole('button', { name: /sign in/i }).click();
  await admin.waitForURL(/\/admin\//, { timeout: 15000 });
  await admin.goto('http://localhost:3000/principal/curriculum', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await admin.getByTestId('recovery-proposal').waitFor({ timeout: 20000 });
  await admin.screenshot({ path: `${shots}/01_recovery_proposal.png`, fullPage: false });
  log('Admin review shows the original, current approved and proposed schedules.');

  const stateResponse = await fetch(`${api}/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'admin@lumeneios.demo', password: 'demo123' }) });
  if (!stateResponse.ok) throw new Error(`Admin API login failed ${stateResponse.status}`);
  const { access_token: token } = await stateResponse.json();
  const workspaceResponse = await fetch(`${api}/planning/workspace`, { headers: { Authorization: `Bearer ${token}` } });
  const beforeReview = await workspaceResponse.json();
  const activePlan = beforeReview.state.plans.find((p) => p.status === 'APPROVED' && p.grade === 6 && p.subject === 'Mathematics');
  const proposal = activePlan?.proposals.find((p) => p.status === 'PENDING');
  if (!proposal || proposal.trigger.kind !== 'CONFIG_CHANGE') throw new Error('Expected pending Day 100 config-change proposal missing');
  log(`Pending proposal ${proposal.id}: ${proposal.changes.length} changed topics; ${proposal.remainingAvailablePeriods} periods available for ${proposal.remainingRequiredPeriods} periods still required.`);

  await admin.getByRole('button', { name: 'Approve recovery schedule' }).click();
  await admin.getByText(/approved schedule v3/i).waitFor({ timeout: 15000 });
  await admin.screenshot({ path: `${shots}/02_recovery_approved.png`, fullPage: false });
  await admin.goto('http://localhost:3000/teacher/time-aware', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await admin.getByLabel('Class').selectOption('6');
  await admin.getByLabel('Subject').selectOption('Mathematics');
  await admin.getByTestId('engine-metrics').waitFor();
  await admin.screenshot({ path: `${shots}/03_day100_active_schedule.png`, fullPage: false });
  const text = (await admin.locator('body').innerText()).replace(/\s+/g, ' ');
  if (!/Academic day 100 of 180/.test(text) || !/Teaching days left 80/.test(text)) throw new Error('Time-Aware does not show the Day 100/80 remaining snapshot');
  log('Active Time-Aware page confirms academic Day 100 of 180 and 80 teaching days left.');

  const afterResponse = await fetch(`${api}/planning/workspace`, { headers: { Authorization: `Bearer ${token}` } });
  const after = await afterResponse.json();
  const p = after.state.plans.find((x) => x.grade === 6 && x.subject === 'Mathematics' && x.status === 'APPROVED');
  const v = p.versions.at(-1);
  const approvedProposal = p.proposals.find((x) => x.trigger.kind === 'CONFIG_CHANGE' && x.status === 'APPROVED');
  const flat = v.lessons.flatMap((l) => l.slots);
  const taught = p.execution.filter((e) => ['TAUGHT', 'PARTIAL'].includes(e.status)).reduce((n, e) => n + e.periodsTaught, 0);
  if (v.version !== 3 || !approvedProposal || flat.some((s) => s.date <= after.state.asOf)) throw new Error('Approved Day 100 schedule version is inconsistent');
  const data = {
    revision: after.revision, asOf: after.state.asOf, academicDays: v.config.horizonDays,
    remainingTeachingDays: 80, activeVersion: v.version, proposalStatus: approvedProposal.status,
    scheduleSlotsAfterDay100: flat.length, firstSlot: flat.map((s) => s.date).sort()[0], lastSlot: flat.map((s) => s.date).sort().at(-1),
    topics: v.lessons.length, coreRequired: v.lessons.reduce((n, l) => n + l.corePeriods, 0),
    nonCoreRequired: v.lessons.reduce((n, l) => n + l.nonCorePeriods, 0),
    independentLearning: v.lessons.reduce((n, l) => n + l.independentPeriods, 0),
    executionEvents: p.execution.length, periodsTaught: taught, losses: p.losses.length,
    lostPeriods: p.losses.reduce((n, x) => n + x.periodsLost, 0), versions: p.versions.length,
    approvedRecoveryMoves: approvedProposal.changes.length,
  };
  fs.writeFileSync(`${shots}/day100-summary.json`, JSON.stringify(data, null, 2));
  log(`Persisted restart-check summary: ${JSON.stringify(data)}`);
  if (errors.length) throw new Error(`Browser/API errors: ${JSON.stringify(errors)}`);
  log('DEMO PASSED; Edge left open on the active Day 100 Time-Aware schedule.');
  fs.writeFileSync(`${shots}/browser.pid`, String(process.pid));
} catch (e) {
  log(`FAIL ${e.stack || e.message}`);
  await teacher.screenshot({ path: `${shots}/FAIL.png`, fullPage: false }).catch(() => {});
  throw e;
}
