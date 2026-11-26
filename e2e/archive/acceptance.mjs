// Real-browser acceptance: Playwright + installed Microsoft Edge against the running app (frontend :3000, backend :8000,
// isolated database). Run `bash e2e/reset_env.sh` first for a clean environment. Writes e2e-results.json.
import fs from 'node:fs';
import { API, WEB, api, assert, consoleIssues, launch, loginUi, report, shot, step, storeReady, token, workspace } from '../lib.mjs';

const { browser, context, page, version } = await launch();
const S = (id, role, wf, exp, fn) => step(id, role, wf, exp, fn, page);
const body = async () => (await page.innerText('body')).replace(/\s+/g, ' ');
const state = {};

// ------------------------------------------------------------------ A. Authentication, sessions, role access
await S('A01', 'anonymous', 'Planning API without a token', '401 even though DEMO_MODE is on', async () => {
  const r = await api('GET', '/planning/workspace', null);
  assert(r.status === 401, `got ${r.status}`);
  return '401';
});

await S('A02', 'anonymous', 'Open a protected route without a session', 'Redirected to login', async () => {
  await page.goto(`${WEB}/login`);
  await page.evaluate(() => localStorage.clear());
  await page.goto(`${WEB}/teacher/time-aware`);
  await page.waitForTimeout(800);
  assert(/\/login/.test(page.url()), `url ${page.url()}`);
  return page.url();
});

const landing = { admin: '/admin/dashboard', principal: '/principal/dashboard', teacher: '/teacher/dashboard', student: '/student/dashboard', parent: '/parent/dashboard' };
for (const role of ['admin', 'principal', 'teacher', 'student']) {
  await S(`A03-${role}`, role, '1-click demo login and role landing page', `Lands on ${landing[role]}`, async () => {
    await loginUi(page, role);
    assert(page.url().endsWith(landing[role]), page.url());
    await shot(page, `A03_${role}_dashboard`);
    state[`nav_${role}`] = await page.$$eval('aside a, nav a', (els) => els.map((e) => e.innerText.trim()).filter(Boolean));
    return `${page.url()} · nav: ${state[`nav_${role}`].join(', ')}`.slice(0, 300);
  });
}

await S('A04', 'teacher', 'Session persists across reload', 'Still signed in as teacher after reload', async () => {
  await loginUi(page, 'teacher');
  await page.reload();
  await page.waitForTimeout(800);
  assert(page.url().endsWith(landing.teacher), page.url());
  assert(/Vikram Sengupta/.test(await body()), 'teacher name not shown');
});

await S('A05', 'teacher', 'Form login with the demo password; wrong password', 'Correct credentials sign in; a wrong password must not', async () => {
  await page.evaluate(() => localStorage.clear());
  await page.goto(`${WEB}/login`);
  await page.getByPlaceholder('e.g. teacher@lumeneios.demo').fill('teacher@lumeneios.demo');
  await page.getByPlaceholder('demo123').fill('WRONG-password');
  await page.getByRole('button', { name: 'Sign In to Dashboard' }).click();
  await page.waitForTimeout(1500);
  const wrongSignedIn = /\/teacher\//.test(page.url());
  state.wrongPasswordSignedIn = wrongSignedIn;
  await page.evaluate(() => localStorage.clear());
  await page.goto(`${WEB}/login`);
  await page.getByPlaceholder('e.g. teacher@lumeneios.demo').fill('teacher@lumeneios.demo');
  await page.getByPlaceholder('demo123').fill('demo123');
  await page.getByRole('button', { name: 'Sign In to Dashboard' }).click();
  await page.waitForURL(/\/teacher\//, { timeout: 10000 });
  assert(!wrongSignedIn, 'DEFECT: the sign-in form accepted a wrong password (client-side demo login does not verify it)');
});

await S('A06', 'student', 'Student opens a teacher route directly', 'Blocked (unauthorized page or redirect)', async () => {
  await loginUi(page, 'student');
  await page.goto(`${WEB}/teacher/time-aware`);
  await page.waitForTimeout(800);
  const t = await body();
  assert(!/Generate draft schedule for approval/.test(t), 'student can see the teacher planner');
  return page.url();
});

await S('A07', 'student/teacher', 'Server-side authorization over the API', 'Student 403 on planning; teacher 403 on config save; stale revision 409', async () => {
  const st = await token('student');
  assert((await api('GET', '/planning/workspace', st)).status === 403, 'student GET not 403');
  const ws = await workspace('admin');
  const probe = { schemaVersion: 2, config: { year: 'x' }, configHistory: [], datasets: [], classifications: {}, relationships: [], plans: [], audit: [{ id: 'z' }] };
  const t = await token('teacher');
  assert((await api('PUT', '/planning/workspace', t, { expected_revision: ws.revision, action: 'CONFIG_SAVE', summary: 'x', state: probe })).status === 403, 'teacher CONFIG_SAVE not 403');
  assert((await api('PUT', '/planning/workspace', await token('admin'), { expected_revision: ws.revision + 7, action: 'CONFIG_SAVE', summary: 'x', state: probe })).status === 409, 'stale revision not 409');
});

await S('A08', 'teacher', 'Logout', 'Session cleared and protected routes redirect to login', async () => {
  await loginUi(page, 'teacher');
  await page.getByRole('button', { name: /Vikram Sengupta/ }).click();
  await page.getByRole('button', { name: /log ?out|sign ?out/i }).first().click();
  await page.waitForTimeout(800);
  await page.goto(`${WEB}/teacher/time-aware`);
  await page.waitForTimeout(800);
  assert(/\/login/.test(page.url()), `after logout url ${page.url()}`);
});

// ------------------------------------------------------------------ B. Academic Configuration (admin)
await S('B01', 'admin', 'Open Academic Configuration; defaults visible', 'Calendar, weekdays, period settings and entries shown', async () => {
  await loginUi(page, 'admin');
  await page.goto(`${WEB}/admin/academic-config`);
  await storeReady(page);
  const t = await body();
  for (const s of ['Academic year and school week', 'Holidays, vacations, examinations and events', 'Periods and planning horizon', 'Mathematics periods per instructional day']) assert(t.includes(s), `missing: ${s}`);
  await shot(page, 'B01_academic_config');
});

await S('B02', 'admin', 'Validation: overlapping/invalid calendar entries are rejected', 'A validation message appears and saving is blocked', async () => {
  await page.getByRole('button', { name: /Add holiday/ }).click();
  await page.getByLabel('Entry 1 description').fill('Ram Navami');
  await page.getByLabel('Entry 1 from').fill('2026-04-02');
  await page.getByRole('button', { name: /Add examination period/ }).click();
  await page.getByLabel('Entry 2 description').fill('Periodic test');
  await page.getByLabel('Entry 2 from').fill('2026-04-06');
  // make entry 2 end before it starts to force a validation error
  const toField = page.getByLabel('Entry 2 to');
  if (await toField.count()) {
    await toField.fill('2026-04-01');
    await page.waitForTimeout(300);
    const t = await body();
    assert(!/Configuration is valid\./.test(t), 'invalid entry reported as valid');
    await toField.fill('2026-04-06');
  }
});

await S('B03', 'admin', 'Configure calendar: holiday 2 Apr, exam 6 Apr, 3 Mathematics periods/day, 3-day horizon', 'Configuration is valid and saves; first three teaching dates skip the holiday, weekend and exam', async () => {
  await page.getByLabel('Mathematics periods per instructional day').fill('3');
  await page.getByLabel('Curriculum planning horizon').fill('3');
  await page.waitForTimeout(300);
  assert(/Configuration is valid\./.test(await body()), 'not valid');
  await page.getByRole('button', { name: 'Save Academic Configuration' }).click();
  await page.getByText(/Configuration saved/).first().waitFor({ timeout: 10000 });
  const ws = await workspace('admin');
  assert(ws.state.config.subjectPeriodsPerDay.Mathematics === 3 && ws.state.config.horizonDays === 3, 'config not persisted on server');
  assert(ws.state.config.entries.map((e) => e.type).join() === 'HOLIDAY,EXAM', 'entries not persisted');
  state.configAfterSave = JSON.stringify(ws.state.config);
  await shot(page, 'B03_config_saved');
  return `server revision ${ws.revision}`;
});

await S('B04', 'principal', 'Principal can also edit/save the shared configuration; teacher cannot', 'Principal sees the same saved values; teacher has read-only/disabled save', async () => {
  await loginUi(page, 'principal');
  await page.goto(`${WEB}/principal/academic-config`);
  await storeReady(page);
  assert((await page.getByLabel('Mathematics periods per instructional day').inputValue()) === '3', 'principal does not see saved config');
  await loginUi(page, 'teacher');
  const t = await token('teacher');
  const ws = await workspace('admin');
  const next = JSON.parse(JSON.stringify(ws.state));
  next.config.subjectPeriodsPerDay.Mathematics = 5;
  next.audit.push({ id: 'tamper' });
  assert((await api('PUT', '/planning/workspace', t, { expected_revision: ws.revision, action: 'CONFIG_SAVE', summary: 'tamper', state: next })).status === 403, 'teacher tamper not rejected');
});

// ------------------------------------------------------------------ C. Curriculum, resources and Core/Non-Core governance
await S('C01', 'teacher', 'Time-Aware Engine: Class VII Mathematics lists only conceptual topics', 'Topics shown with source provenance; no activity/exercise units; both flagged as lacking approved requirements', async () => {
  await loginUi(page, 'teacher');
  await page.goto(`${WEB}/teacher/time-aware`);
  await storeReady(page);
  await page.getByLabel('Class').selectOption('7');
  await page.getByLabel('Subject').selectOption('Mathematics');
  const t = await body();
  assert(/8\.1 Multiplication of Fractions/.test(t) && /8\.2 Division of Fractions/.test(t), 'expected two VII Mathematics topics');
  assert(/2 topic\(s\) without an approved requirement/.test(t), 'missing-requirement flag not shown');
  assert(!/Activity|Investigation/.test(await page.getByRole('table', { name: 'Generated schedule' }).innerText().catch(() => '')), 'resource shown as schedulable');
  await shot(page, 'C01_engine_pending');
});

await S('C02', 'teacher', 'Schedule generation is blocked or empty while requirements are unapproved', 'Nothing is scheduled; 0 approved periods; shortfall not invented', async () => {
  const t = await body();
  assert(/APPROVED REQUIRED\s*0 p/i.test(t), 'approved required is not 0');
  assert(/SCHEDULED\s*0 p/i.test(t), 'periods scheduled without approval');
});

async function proposeRequirement(unitTestId, core, nonCore, criteria, reason) {
  await page.getByRole('tab', { name: 'Syllabus & classification' }).click();
  const row = page.getByTestId(unitTestId);
  await row.getByText(/Propose (classification|requirement)/i).first().click();
  await row.getByLabel('Required Core periods').fill(String(core));
  await row.getByLabel('Required Non-Core periods').fill(String(nonCore));
  for (const c of criteria) await row.getByLabel(c).check();
  await row.getByLabel('Classification reasoning').fill(reason);
  await row.getByRole('button', { name: 'Submit for expert review' }).click();
  await row.getByText(/awaiting review/).first().waitFor({ timeout: 10000 });
}

await S('C03', 'teacher', 'Propose per-topic requirements: 8.1 = 3 Core + 1 Non-Core; 8.2 = 2 Core + 3 Non-Core', 'Both proposals recorded as awaiting review (different splits, no fixed ratio)', async () => {
  await page.getByRole('tab', { name: 'Syllabus & classification' }).click();
  const ids = await page.$$eval('[data-testid^="unit-"]', (els) => els.map((e) => e.getAttribute('data-testid')));
  assert(ids.length === 2, `expected 2 unit rows, got ${ids.length}`);
  state.unitIds = ids;
  await proposeRequirement(ids[0], 3, 1, [/Foundational concept/, /Extension or enrichment/], 'Fraction multiplication is foundational; one enrichment period extends it.');
  await proposeRequirement(ids[1], 2, 3, [/Foundational concept/, /independent learning/], 'Division needs two core periods; practice suits tracked independent study.');
  await shot(page, 'C03_proposed');
  const ws = await workspace('admin');
  const c = Object.values(ws.state.classifications).map((x) => `${x.corePeriods}+${x.nonCorePeriods}:${x.status}`).sort();
  assert(c.join() === '2+3:PROPOSED,3+1:PROPOSED', `server classifications ${c}`);
});

await S('C04', 'teacher', 'A proposal cannot enter the scheduler while only proposed', 'Engine still shows 0 approved required periods', async () => {
  await page.getByRole('tab', { name: 'Schedule planner' }).click();
  const t = await body();
  assert(/APPROVED REQUIRED\s*0 p/i.test(t), 'proposed requirement counted as approved');
});

await S('C05', 'teacher', 'Teacher cannot approve a requirement (UI and API)', 'No approve button for teacher; API approval returns 403', async () => {
  await page.getByRole('tab', { name: 'Syllabus & classification' }).click();
  const approveBtns = page.getByRole('button', { name: 'Approve classification' });
  for (let i = 0; i < (await approveBtns.count()); i++) assert(await approveBtns.nth(i).isDisabled(), 'teacher can click Approve classification');
  assert(/proposer|independent|reviewer|Admin or Principal/i.test(await body()), 'no explanation shown for the disabled approval');
  const ws = await workspace('admin');
  const next = JSON.parse(JSON.stringify(ws.state));
  const id = Object.keys(next.classifications)[0];
  next.classifications[id].status = 'APPROVED';
  next.classifications[id].reviewedBy = { id: 'x', name: 'x', role: 'teacher' };
  next.audit.push({ id: 'forge' });
  const r = await api('PUT', '/planning/workspace', await token('teacher'), { expected_revision: ws.revision, action: 'CLASSIFICATION_REVIEW', summary: 'forge', state: next });
  assert(r.status === 403, `teacher approval got ${r.status}`);
});

await S('C06', 'principal', 'Principal reviews and approves both requirements', 'Both approved with reviewer identity; audit summary states the exact counts', async () => {
  await loginUi(page, 'principal');
  await page.goto(`${WEB}/teacher/time-aware`);
  await storeReady(page);
  await page.getByLabel('Class').selectOption('7');
  await page.getByLabel('Subject').selectOption('Mathematics');
  await page.getByRole('tab', { name: 'Syllabus & classification' }).click();
  for (const id of state.unitIds) {
    const row = page.getByTestId(id);
    await row.getByRole('button', { name: 'Approve classification' }).click();
    await row.getByText(/\(approved\)/).first().waitFor({ timeout: 10000 });
  }
  const ws = await workspace('admin');
  const sums = ws.state.audit.map((a) => a.summary).filter(Boolean).join(' | ');
  assert(/Approved 3 Core \+ 1 Non-Core/.test(sums) && /Approved 2 Core \+ 3 Non-Core/.test(sums), `audit: ${sums.slice(0, 300)}`);
  await shot(page, 'C06_approved');
});

// ------------------------------------------------------------------ D. Schedule generation and approval
await S('D01', 'teacher', 'Generate the schedule from approved requirements', 'Calendar-aware draft: 9 required = 9 available; allocation equals the independently derived timetable', async () => {
  await loginUi(page, 'teacher');
  await page.goto(`${WEB}/teacher/time-aware`);
  await storeReady(page);
  await page.getByLabel('Class').selectOption('7');
  await page.getByLabel('Subject').selectOption('Mathematics');
  const t = await body();
  assert(/CORE \/ NON-CORE REQUIRED\s*5 \/ 4 p/i.test(t), `core/non-core totals not 5 / 4: ${t.match(/CORE \/ NON-CORE REQUIRED[^|]{0,40}/i)}`);
  await page.getByRole('button', { name: 'Generate draft schedule for approval' }).click();
  await page.getByText(/Draft saved for/).first().waitFor({ timeout: 10000 });
  const ws = await workspace('admin');
  const plan = ws.state.plans[0];
  assert(plan.status === 'DRAFT', `plan status ${plan.status}`);
  // Independent derivation: teaching dates 2026-04-01, 03, 07 (02 holiday, 04-05 weekend, 06 exam); 3 periods/day;
  // topics in syllabus order, each topic's Core periods first, then its Non-Core periods.
  const dates = ['2026-04-01', '2026-04-03', '2026-04-07'];
  const timeline = dates.flatMap((d) => [1, 2, 3].map((p) => `${d}#${p}`));
  const need = [[3, 1], [2, 3]];
  const expected = [];
  let i = 0;
  for (const [c, n] of need) {
    const slots = [];
    for (let k = 0; k < c; k++) slots.push(`${timeline[i++]}C`);
    for (let k = 0; k < n; k++) slots.push(`${timeline[i++]}N`);
    expected.push(slots.join(' '));
  }
  const actual = plan.draft.lessons.map((l) => l.slots.map((s) => `${s.date}#${s.period}${s.kind === 'CORE' ? 'C' : 'N'}`).join(' '));
  assert(JSON.stringify(actual) === JSON.stringify(expected), `allocation\n actual   ${JSON.stringify(actual)}\n expected ${JSON.stringify(expected)}`);
  assert(plan.draft.metrics.unscheduledPeriods === 0, 'unscheduled periods present');
  await shot(page, 'D01_draft');
  return `draft allocation matches independent derivation: ${expected.join(' / ')}`;
});

await S('D02', 'teacher', 'Teacher cannot approve the schedule', 'No approve button for teacher; API approval returns 403', async () => {
  await page.goto(`${WEB}/principal/curriculum`);
  await page.waitForTimeout(1500);
  assert((await page.getByRole('button', { name: 'Approve teaching schedule' }).count()) === 0, 'teacher sees schedule approval');
  const ws = await workspace('admin');
  const next = JSON.parse(JSON.stringify(ws.state));
  next.plans[0].status = 'APPROVED';
  next.plans[0].versions = [{ version: 1, lessons: next.plans[0].draft.lessons, metrics: next.plans[0].draft.metrics, conflicts: [], config: next.config, approvedBy: { id: 'x', name: 'x', role: 'teacher' }, approvedAt: 'now', reason: 'forged', proposalId: null }];
  next.audit.push({ id: 'forge2' });
  const r = await api('PUT', '/planning/workspace', await token('teacher'), { expected_revision: ws.revision, action: 'PLAN_REVIEW', summary: 'forge', state: next });
  assert(r.status === 403, `teacher schedule approval got ${r.status}`);
});

await S('D03', 'principal', 'Principal approves the schedule', 'Plan APPROVED with exactly one version v1 approved by the principal; draft panel disappears', async () => {
  await loginUi(page, 'principal');
  await page.goto(`${WEB}/principal/curriculum`);
  const draft = page.getByTestId('draft-review');
  await draft.waitFor({ timeout: 15000 });
  await draft.getByRole('button', { name: 'Approve teaching schedule' }).click();
  await draft.waitFor({ state: 'detached', timeout: 10000 });
  const ws = await workspace('admin');
  const plan = ws.state.plans[0];
  assert(plan.status === 'APPROVED' && plan.versions.length === 1 && plan.versions[0].version === 1, 'version shape wrong');
  assert(plan.versions[0].approvedBy.role === 'principal', 'approver not principal');
  state.v1 = JSON.stringify(plan.versions[0]);
  await shot(page, 'D03_approved');
});

// ------------------------------------------------------------------ E. Daily Curriculum, lost periods, recovery
const goPlanner = async (role) => {
  await loginUi(page, role);
  await page.goto(`${WEB}/teacher/time-aware`);
  await storeReady(page);
  await page.getByLabel('Class').selectOption('7');
  await page.getByLabel('Subject').selectOption('Mathematics');
};
const goDaily = async (role) => {
  await loginUi(page, role);
  await page.goto(`${WEB}/teacher/curriculum-180`);
  await storeReady(page);
};
const planOf = async () => (await workspace('admin')).state.plans[0];
const flat = async (loc) => (await loc.innerText()).replace(/\s+/g, ' ');

await S('E01', 'teacher', 'Daily Curriculum shows the approved v1 schedule', 'Heading for Class 7 Mathematics; 9 scheduled periods by period; no pending change notice', async () => {
  await goDaily('teacher');
  assert(/Class 7 · Mathematics · Daily Curriculum/.test(await body()), 'heading missing');
  await page.getByRole('tab', { name: 'By period' }).click();
  const rows = await page.getByRole('table', { name: 'Daily curriculum by period' }).getByRole('row').count();
  assert(rows - 1 === 9, `ledger rows ${rows - 1}`);
  assert((await page.getByTestId('schedule-change-notice').count()) === 0, 'change notice before any approval');
  await shot(page, 'E01_daily_v1');
});

await S('E02', 'teacher', 'Record a Lost Day: select periods #1 and #2 together', 'Dialog lists all 9 periods with date/class/subject/topic/Core-Non-Core; submit disabled until a reason is given; re-toggling never duplicates', async () => {
  await goPlanner('teacher');
  await page.getByTestId('lost-period-recorder').getByRole('button', { name: 'Record a Lost Day' }).click();
  const dialog = page.getByRole('dialog');
  assert((await dialog.getByRole('checkbox').count()) === 9, 'expected 9 selectable periods');
  const p1 = dialog.getByLabel(/^Period 1: 2026-04-01, 8\.1 /);
  const p2 = dialog.getByLabel(/^Period 2: 2026-04-01, 8\.1 /);
  const row1 = await p1.locator('xpath=ancestor::tr').innerText();
  assert(/Core/.test(row1) && /VII/.test(row1) && /Mathematics/.test(row1), `row lacks class/subject/classification: ${row1}`);
  await p1.check(); await p2.check(); await p2.uncheck(); await p2.check();
  assert((await dialog.getByRole('list', { name: 'Selected periods' }).getByRole('listitem').count()) === 2, 'selected list not 2');
  const submit = dialog.getByRole('button', { name: 'Record 2 lost period(s)' });
  assert(await submit.isDisabled(), 'submit enabled without a reason');
  await dialog.getByLabel('Loss reason').selectOption('Election Duties');
  await dialog.getByLabel('Loss note').fill('Polling booth setup');
  await shot(page, 'E02_recorder_dialog');
  await submit.click();
  await page.getByText(/Recorded period\(s\) #1, #2 as lost \(Election Duties\)/).first().waitFor({ timeout: 10000 });
  return 'recorded #1,#2 in one submission';
});

await S('E03', 'teacher', 'Only the selected periods are lost; calendar and approved schedule untouched', 'One loss record [1,2]; exactly one pending proposal; v1 and calendar byte-identical; loss not written into the calendar', async () => {
  const plan = await planOf();
  const ws = await workspace('admin');
  assert(plan.losses.length === 1 && JSON.stringify(plan.losses[0].periods) === '[1,2]' && plan.losses[0].periodsLost === 2, `losses ${JSON.stringify(plan.losses)}`);
  assert(plan.losses[0].reason === 'Election Duties' && plan.losses[0].note === 'Polling booth setup', 'reason/note not stored');
  assert(plan.proposals.filter((x) => x.status === 'PENDING').length === 1, 'expected one pending proposal');
  assert(plan.versions.length === 1 && JSON.stringify(plan.versions[0]) === state.v1, 'approved v1 changed');
  assert(JSON.stringify(ws.state.config) === state.configAfterSave, 'Academic Configuration changed');
  assert(!JSON.stringify(ws.state.config.entries).includes('Election'), 'lost periods leaked into the calendar');
  state.proposal1 = plan.proposals.find((x) => x.status === 'PENDING');
});

await S('E04', 'teacher', 'Recorded periods cannot be selected again', '7 selectable periods; period 1 disabled under "all"', async () => {
  await page.reload(); await storeReady(page);
  await page.getByLabel('Class').selectOption('7'); await page.getByLabel('Subject').selectOption('Mathematics');
  await page.getByTestId('lost-period-recorder').getByRole('button', { name: 'Record a Lost Day' }).click();
  const dialog = page.getByRole('dialog');
  assert((await dialog.getByRole('checkbox').count()) === 7, 'expected 7 selectable');
  await dialog.getByLabel('Period filter').selectOption('all');
  assert(await dialog.getByLabel(/^Period 1: 2026-04-01/).isDisabled(), 'period 1 not disabled');
  await page.getByRole('button', { name: 'Cancel' }).click();
});

await S('E05', 'teacher', 'Teacher sees recovery as PROPOSED only', '2 lost periods; proposal 2 Core recovered / 2 Non-Core to independent learning / 0 unresolved; approved recovery counter 0', async () => {
  await page.getByRole('tab', { name: 'Day tracker' }).click();
  const prog = await flat(page.getByTestId('recovery-progress'));
  assert(/Lost periods recorded\s*2/.test(prog), prog);
  const prop = await flat(page.getByTestId('proposed-recovery'));
  assert(/2 Core period\(s\) recovered · 2 Non-Core period\(s\) to independent learning · 0 Core period\(s\) still unresolved/.test(prop), prop);
  assert(/Core recovered \(approved\)\s*0/.test(prog), 'approved recovery counter not 0: ' + prog);
});

await S('E06', 'teacher', 'Teacher cannot approve recovery (UI and API)', 'No approve button; API approval by a teacher returns 403', async () => {
  await page.goto(`${WEB}/principal/curriculum`);
  await page.waitForTimeout(1500);
  assert((await page.getByRole('button', { name: 'Approve recovery schedule' }).count()) === 0, 'teacher sees recovery approval');
  const ws = await workspace('admin');
  const next = JSON.parse(JSON.stringify(ws.state));
  const p = next.plans[0];
  const prop = p.proposals.find((x) => x.status === 'PENDING');
  prop.status = 'APPROVED';
  p.versions.push({ version: 2, lessons: prop.lessons, metrics: prop.metrics, conflicts: [], config: prop.config, approvedBy: { id: 'x', name: 'x', role: 'teacher' }, approvedAt: 'now', reason: 'forged', proposalId: prop.id });
  next.audit.push({ id: 'forge3' });
  const r = await api('PUT', '/planning/workspace', await token('teacher'), { expected_revision: ws.revision, action: 'RECOVERY_REVIEW', summary: 'forge', state: next });
  assert(r.status === 403, `teacher recovery approval got ${r.status}`);
});

await S('F01', 'principal', 'Review the recovery proposal: original vs proposed, every change explained', 'Loss summary, original (v1) and proposed columns, changed-period rows match the independently derived recovery', async () => {
  await loginUi(page, 'principal');
  await page.goto(`${WEB}/principal/curriculum`);
  const proposal = page.getByTestId('recovery-proposal');
  await proposal.waitFor({ timeout: 15000 });
  const t = await flat(proposal);
  assert(/Original \(v1\)/i.test(t) && /Current approved \(v1\)/i.test(t) && /Proposed/i.test(t), 'comparison columns missing');
  assert(/Lost periods on 2026-04-01 \(Election Duties\): 2 of 3 scheduled Mathematics period\(s\)/.test(t), 'loss summary: ' + t.slice(0, 300));
  assert(/not classroom teaching/i.test(t) && /not counted as taught/i.test(t), 'independent-learning-is-not-teaching disclaimer missing');
  const rows = (await proposal.getByRole('table', { name: 'Changed periods' }).getByRole('row').allInnerTexts()).slice(1).map((r) => r.replace(/\s+/g, ' ').trim());
  // Independent derivation: #1,#2 (Multiplication Core) lost on 04-01. Same-topic Non-Core is #4 (04-03): Core recovered there and that
  // Non-Core period moves to independent learning. The second Core is recovered in a later topic's Non-Core slot (#7, 04-07, Division).
  const want = [/^#1 2026-04-01 Lost/, /^#2 2026-04-01 Lost/, /^#4 2026-04-03 Core recovered/, /^#4 2026-04-03 Non-Core → independent learning/, /^#7 2026-04-07 Core recovered/, /^#7 2026-04-07 Non-Core → independent learning/];
  assert(rows.length === want.length, `expected ${want.length} changed rows, got ${rows.length}: ${JSON.stringify(rows)}`);
  want.forEach((re, i) => assert(re.test(rows[i]), `row ${i}: ${rows[i]}`));
  await shot(page, 'F01_proposal_review');
  return rows.join(' || ').slice(0, 280);
});

await S('F02', 'principal', 'Reject the proposal (reason required)', 'No reason -> alert; with reason the proposal is REJECTED, v1 stays authoritative, the loss record is retained', async () => {
  const proposal = page.getByTestId('recovery-proposal');
  await proposal.getByRole('button', { name: 'Reject proposal' }).click();
  await proposal.getByRole('alert').waitFor({ timeout: 5000 });
  assert(/rejection reason is required/i.test(await proposal.getByRole('alert').innerText()), 'wrong alert');
  await proposal.getByLabel('Recovery review note').fill('Cover through Saturday make-up class first');
  await proposal.getByRole('button', { name: 'Reject proposal' }).click();
  await proposal.waitFor({ state: 'detached', timeout: 10000 });
  const plan = await planOf();
  assert(plan.versions.length === 1 && JSON.stringify(plan.versions[0]) === state.v1, 'rejection altered the approved schedule');
  const p = plan.proposals.find((x) => x.id === state.proposal1.id);
  assert(p.status === 'REJECTED' && /Saturday/.test(p.review.note) && p.review.by.role === 'principal', 'rejection not traceable');
  assert(plan.losses.length === 1, 'loss record lost on rejection');
});

await S('F03', 'teacher', 'After rejection the teacher still sees the original approved schedule', 'No change notice; 2 lost awaiting recovery; 1 rejected kept; 0 approved revisions', async () => {
  await goPlanner('teacher');
  await page.getByRole('tab', { name: 'Day tracker' }).click();
  const prog = await flat(page.getByTestId('recovery-progress'));
  assert(/Lost, awaiting approval\s*2/.test(prog) && /Approved revisions\s*0/.test(prog) && /1 rejected \(kept\)/.test(prog), prog);
  await page.goto(`${WEB}/teacher/curriculum-180`); await storeReady(page);
  assert((await page.getByTestId('schedule-change-notice').count()) === 0, 'rejected proposal leaked into Daily Curriculum');
});

await S('F04', 'teacher', 'Generate another proposal: record period #5 (Division Core) as lost', 'A new pending proposal is created; v1 still authoritative; 3 lost periods in total', async () => {
  await goPlanner('teacher');
  await page.getByTestId('lost-period-recorder').getByRole('button', { name: 'Record a Lost Day' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel(/^Period 5: 2026-04-03, 8\.2 /).check();
  await dialog.getByLabel('Loss reason').selectOption('Teacher Training');
  await dialog.getByRole('button', { name: 'Record 1 lost period(s)' }).click();
  await page.getByText(/Recorded period\(s\) #5 as lost/).first().waitFor({ timeout: 10000 });
  const plan = await planOf();
  const pend = plan.proposals.filter((x) => x.status === 'PENDING');
  assert(pend.length === 1 && pend[0].id !== state.proposal1.id, 'expected a new pending proposal');
  assert(plan.versions.length === 1, 'approved schedule changed before approval');
  assert(plan.losses.length === 2, 'expected 2 loss records');
  state.proposal2 = pend[0];
  state.lostTotal = plan.losses.reduce((n, l) => n + l.periodsLost, 0);
  assert(state.lostTotal === 3, `lost total ${state.lostTotal}`);
});

await S('F05', 'principal', 'Approve the new proposal', 'v2 created from v1, approved by the principal, linked to the proposal; v1 unchanged', async () => {
  await loginUi(page, 'principal');
  await page.goto(`${WEB}/principal/curriculum`);
  const proposal = page.getByTestId('recovery-proposal');
  await proposal.waitFor({ timeout: 15000 });
  await shot(page, 'F05_proposal2');
  await proposal.getByRole('button', { name: 'Approve recovery schedule' }).click();
  await proposal.waitFor({ state: 'detached', timeout: 10000 });
  const plan = await planOf();
  assert(plan.versions.length === 2, `versions ${plan.versions.length}`);
  assert(JSON.stringify(plan.versions[0]) === state.v1, 'v1 mutated');
  const v2 = plan.versions[1];
  assert(v2.version === 2 && v2.approvedBy.role === 'principal' && v2.proposalId === state.proposal2.id, 'v2 linkage');
  assert(plan.proposals.find((x) => x.id === state.proposal2.id).status === 'APPROVED', 'proposal not approved');
});

await S('F06', 'server', 'Reconcile approved v2 against independent invariants', 'Core and Non-Core accounting closes exactly; no lost/duplicate/non-teaching slots; calendar unchanged', async () => {
  const ws = await workspace('admin');
  const v2 = ws.state.plans[0].versions[1];
  const REQ_CORE = 5, REQ_NON = 4; // 3+2 and 1+3, approved above
  const lessons = v2.lessons;
  const coreSlots = lessons.flatMap((l) => l.slots.filter((s) => s.kind === 'CORE')).length;
  const nonSlots = lessons.flatMap((l) => l.slots.filter((s) => s.kind !== 'CORE')).length;
  const coreUnsched = lessons.reduce((n, l) => n + (l.coreUnscheduled || 0), 0);
  const indep = lessons.reduce((n, l) => n + (l.independentPeriods || 0), 0);
  assert(lessons.reduce((n, l) => n + l.corePeriods, 0) === REQ_CORE && lessons.reduce((n, l) => n + l.nonCorePeriods, 0) === REQ_NON, 'approved requirement counts changed');
  assert(coreSlots + coreUnsched === REQ_CORE, `Core accounting: ${coreSlots} classroom + ${coreUnsched} unresolved != ${REQ_CORE}`);
  assert(nonSlots + indep === REQ_NON, `Non-Core accounting: ${nonSlots} classroom + ${indep} independent != ${REQ_NON}`);
  const all = lessons.flatMap((l) => l.slots.map((s) => `${s.date}#${s.period}`));
  assert(new Set(all).size === all.length, 'double-allocated period');
  const lost = new Set((v2.lostSlots || []).map((s) => `${s.date}#${s.period}`));
  assert(lost.size === 3, `lostSlots ${lost.size}`);
  all.forEach((k) => assert(!lost.has(k), `lost period ${k} still allocated`));
  const teaching = ['2026-04-01', '2026-04-03', '2026-04-07'];
  lessons.forEach((l) => l.slots.forEach((s) => assert(teaching.includes(s.date), `slot ${s.date} is not a teaching date`)));
  assert(JSON.stringify(ws.state.config) === state.configAfterSave && JSON.stringify(v2.config) === state.configAfterSave, 'Academic Configuration changed');
  return `Core ${coreSlots} classroom + ${coreUnsched} unresolved = ${REQ_CORE}; Non-Core ${nonSlots} classroom + ${indep} independent = ${REQ_NON}; lost ${lost.size}`;
});

await S('G01', 'teacher', 'Daily Curriculum reflects the approved v2 after reload', 'Change notice names v2; lost periods labelled with reason/note; Core recovery rows; independent learning shown as not taught', async () => {
  await goDaily('teacher');
  await page.reload(); await storeReady(page);
  assert(/v2 approved by/.test(await page.getByTestId('schedule-change-notice').innerText()), 'notice missing');
  await page.getByRole('tab', { name: 'By period' }).click();
  const ledger = page.getByRole('table', { name: 'Daily curriculum by period' });
  const row1 = (await ledger.getByText('#1', { exact: true }).locator('xpath=ancestor::tr').innerText()).replace(/\s+/g, ' ');
  assert(/Lost — recovery approved/.test(row1) && /Election Duties/.test(row1) && /Polling booth setup/.test(row1), row1);
  assert(/Core recovery \(approved\)/.test(await ledger.innerText()), 'no approved Core recovery rows');
  await page.getByRole('tab', { name: 'By topic' }).click();
  const topicTable = await flat(page.getByRole('table', { name: 'Daily curriculum schedule' }));
  assert(/tracked, not taught/.test(topicTable), 'independent learning not shown as not taught');
  assert(/Lost: #1 \(Election Duties\), #2 \(Election Duties\)/.test(topicTable), 'lost periods not itemised');
  await shot(page, 'G01_daily_v2');
});

await S('G02', 'teacher', 'Record execution: Multiplication completed as scheduled', 'Classroom progress rises by the topic\'s approved classroom periods only', async () => {
  const before = await flat(page.getByTestId('classroom-progress'));
  const row = page.getByRole('table', { name: 'Daily curriculum schedule' }).getByText(/^8\.1 /).locator('xpath=ancestor::tr');
  await row.getByRole('button', { name: 'Record execution' }).click();
  await row.getByRole('button', { name: 'Completed as scheduled' }).click();
  await page.waitForTimeout(1200);
  const after = await flat(page.getByTestId('classroom-progress'));
  const mClassroom = (await planOf()).versions[1].lessons[0].slots.length;
  assert(before !== after && new RegExp(`taught ${mClassroom} of [0-9]+ periods`).test(after), `expected ${mClassroom} classroom periods; before "${before}" after "${after}"`);
  state.classroomAfterM = after;
});

await S('G03', 'teacher', 'Homework is not classroom teaching', 'Division recorded as homework leaves classroom progress unchanged and shows "not counted as completed"', async () => {
  const row = page.getByRole('table', { name: 'Daily curriculum schedule' }).getByText(/^8\.2 /).locator('xpath=ancestor::tr');
  await row.getByRole('button', { name: 'Record execution' }).click();
  await page.getByRole('button', { name: 'Not completed — assigned as homework' }).click();
  await page.waitForTimeout(1500);
  const prog = await flat(page.getByTestId('classroom-progress'));
  assert(prog === state.classroomAfterM, `classroom progress moved: "${state.classroomAfterM}" -> "${prog}"`);
  assert(/Homework assigned — not counted as completed/.test(await body()), 'homework disclaimer missing');
});

await S('G04', 'teacher', 'Progress metrics: lost periods are not lost days', 'Teaching days "x of 3"; lost periods recorded = 3; academic calendar unchanged', async () => {
  const days = await flat(page.getByTestId('teaching-day-progress'));
  assert(/of 3 days/.test(days), days);
  const rec = await flat(page.getByTestId('recovery-progress'));
  assert(/Lost periods recorded\s*3/.test(rec), rec);
  assert(!/3 lost (teaching )?days?/i.test(await body()), 'lost periods presented as lost days');
  assert(JSON.stringify((await workspace('admin')).state.config) === state.configAfterSave, 'Academic Configuration changed');
  await shot(page, 'G04_progress');
  return `${days} | ${rec.slice(0, 200)}`;
});

await S('G05', 'server', 'Homework triggers a pending proposal; approved schedule stays v2 until approval', 'Pending proposal exists; 2 versions', async () => {
  const plan = await planOf();
  assert(plan.versions.length === 2, 'unexpected version change');
  const pend = plan.proposals.filter((x) => x.status === 'PENDING');
  assert(pend.length >= 1, 'expected a pending proposal from homework');
  state.proposal3 = pend[pend.length - 1];
});

// ------------------------------------------------------------------ H. Server-side enforcement against manipulated requests
const approveTamper = async (mutate, role = 'principal') => {
  const ws = await workspace('admin');
  const next = JSON.parse(JSON.stringify(ws.state));
  const p = next.plans[0];
  const prop = p.proposals.find((x) => x.id === state.proposal3.id);
  const v = JSON.parse(JSON.stringify(p.versions[1])); v.version = 3; v.proposalId = prop.id;
  prop.status = 'APPROVED'; p.versions.push(v); next.audit.push({ id: 'tamper' });
  mutate({ next, p, prop, v });
  const r = await api('PUT', '/planning/workspace', await token(role), { expected_revision: ws.revision, action: 'RECOVERY_REVIEW', summary: 'tamper', state: next });
  assert((await workspace('admin')).revision === ws.revision, 'a rejected write changed the workspace');
  return r;
};

await S('H01', 'principal (API)', 'Stale approval of a proposal built on an older version', 'Server answers 403 "Stale proposal" although the principal is authorised', async () => {
  const r = await approveTamper(({ prop }) => { prop.baseVersion = 1; });
  assert(r.status === 403 && /Stale proposal/.test(JSON.stringify(r.json)), `got ${r.status} ${JSON.stringify(r.json)}`);
});

await S('H02', 'principal (API)', 'Approve a proposal whose allocation uses the configured holiday', 'Server answers 403 "not a teaching date"', async () => {
  const r = await approveTamper(({ v }) => { const l = v.lessons.find((x) => x.slots.length); l.slots[0] = { ...l.slots[0], date: '2026-04-02' }; });
  assert(r.status === 403 && /not a teaching date/.test(JSON.stringify(r.json)), `got ${r.status} ${JSON.stringify(r.json)}`);
});

await S('H03', 'principal (API)', 'Approval that silently drops a topic', 'Server answers 403 "silently dropped"', async () => {
  const r = await approveTamper(({ v }) => { v.lessons = v.lessons.slice(0, 1); });
  assert(r.status === 403 && /silently dropped/.test(JSON.stringify(r.json)), `got ${r.status} ${JSON.stringify(r.json)}`);
});

await S('H04', 'principal (API)', 'Approval that double-books a period', 'Server answers 403 "allocated to both"', async () => {
  const r = await approveTamper(({ v }) => { const w = v.lessons.filter((l) => l.slots.length); w[1].slots[0] = { ...w[1].slots[0], date: w[0].slots[0].date, period: w[0].slots[0].period }; });
  assert(r.status === 403 && /allocated to both/.test(JSON.stringify(r.json)), `got ${r.status} ${JSON.stringify(r.json)}`);
});

await S('H05', 'principal/admin (API)', 'Re-open a decided proposal; rewrite an approved schedule version', 'Server answers 403 for both', async () => {
  const ws = await workspace('admin');
  const next = JSON.parse(JSON.stringify(ws.state));
  next.plans[0].proposals.find((x) => x.id === state.proposal2.id).status = 'PENDING';
  next.audit.push({ id: 'h05' });
  let r = await api('PUT', '/planning/workspace', await token('principal'), { expected_revision: ws.revision, action: 'RECOVERY_REVIEW', summary: 'reopen', state: next });
  assert(r.status === 403 && /decided recovery proposal/.test(JSON.stringify(r.json)), `reopen: ${r.status}`);
  const n2 = JSON.parse(JSON.stringify(ws.state));
  n2.plans[0].versions[0].lessons[0].slots[0].date = '2026-04-07';
  n2.audit.push({ id: 'h05b' });
  r = await api('PUT', '/planning/workspace', await token('admin'), { expected_revision: ws.revision, action: 'PLAN_REVIEW', summary: 'rewrite', state: n2 });
  assert(r.status === 403 && /append-only/.test(JSON.stringify(r.json)), `rewrite: ${r.status}`);
});

await S('H06', 'admin (API)', 'Workspace history and audit trail', 'Every change is a numbered revision with action and authenticated actor; audit entries carry the stamped actor', async () => {
  const h = await api('GET', '/planning/workspace/history?limit=200', await token('admin'));
  assert(h.status === 200 && h.json.length >= 10, `history length ${h.json?.length}`);
  const actions = h.json.map((x) => x.action);
  for (const a of ['CONFIG_SAVE', 'CLASSIFICATION_PROPOSE', 'CLASSIFICATION_REVIEW', 'PLAN_DRAFT', 'PLAN_REVIEW', 'LOSS_RECORD', 'RECOVERY_REVIEW', 'EXECUTION_RECORD']) assert(actions.includes(a), `missing ${a} in history`);
  const ws = await workspace('admin');
  assert(ws.state.audit.every((e) => e.actor && e.actor.role), 'audit entry without a stamped actor');
  const roles = new Set(h.json.map((x) => x.actor_role));
  assert(['admin', 'principal', 'teacher'].every((r) => roles.has(r)), `actor roles ${[...roles]}`);
  return `${h.json.length} revisions; roles ${[...roles].join(',')}`;
});

// ------------------------------------------------------------------ I. Persistence across a brand-new browser session
await S('I01', 'principal', 'Fresh browser context (no local storage): approved v2 persists on the server', 'New session sees v2 as authoritative', async () => {
  const ctx2 = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p2 = await ctx2.newPage();
  await loginUi(p2, 'principal');
  await p2.goto(`${WEB}/principal/curriculum`);
  await p2.waitForFunction(() => /Shared planning store \(backend\)/.test(document.body.innerText), null, { timeout: 20000 });
  await p2.waitForTimeout(1200);
  const t = (await p2.innerText('body')).replace(/\s+/g, ' ');
  await p2.screenshot({ path: `${process.env.SHOTS}/I01_fresh_session.png`, fullPage: true });
  await ctx2.close();
  assert(/v2/.test(t), 'v2 not visible after a fresh session: ' + t.slice(0, 200));
});

// ------------------------------------------------------------------ J. Save-conflict handling (two real browser sessions)
await S('J01', 'admin+principal', 'Two sessions edit the Academic Configuration; the second save is stale', 'Stale save refused with a conflict message, typed input kept, server keeps the first save', async () => {
  const ctxA = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const ctxB = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const A = await ctxA.newPage(); const B = await ctxB.newPage();
  await loginUi(A, 'principal'); await loginUi(B, 'admin');
  const ready = (pg) => pg.waitForFunction(() => /Shared planning store \(backend\)/.test(document.body.innerText), null, { timeout: 20000 });
  await A.goto(`${WEB}/principal/academic-config`); await ready(A);
  await B.goto(`${WEB}/admin/academic-config`); await ready(B);
  await B.getByLabel('Period duration (minutes)').fill('45');
  await B.getByRole('button', { name: 'Save Academic Configuration' }).click();
  await B.waitForTimeout(2500);
  const afterB = (await workspace('admin')).state.config.periodMinutes;
  assert(afterB === 45, `session B save not persisted (periodMinutes=${afterB})`);
  await A.getByLabel('Period duration (minutes)').fill('50');
  await A.getByRole('button', { name: 'Save Academic Configuration' }).click();
  await A.waitForTimeout(2500);
  const aText = (await A.innerText('body')).replace(/\s+/g, ' ');
  const serverNow = (await workspace('admin')).state.config.periodMinutes;
  await shot(A, 'J01_conflict_session_A');
  const kept = await A.getByLabel('Period duration (minutes)').inputValue().catch(() => '');
  await ctxA.close(); await ctxB.close();
  assert(serverNow === 45, `stale save overwrote the server (periodMinutes=${serverNow})`);
  assert(/changed|conflict|reload|another user|newer/i.test(aText), 'no conflict message shown: ' + aText.slice(0, 300));
  assert(kept === '50', `typed input was lost (value "${kept}")`);
});

await S('J02', 'teacher', 'A failed workspace load is not an empty revision-0 workspace', 'With an invalid backend token the app re-authenticates or shows an error; it never saves over real data', async () => {
  await goDaily('teacher');
  const before = (await workspace('admin')).revision;
  await page.evaluate(() => localStorage.setItem('lumeneios_token', 'expired.invalid.token'));
  await page.reload();
  await page.waitForTimeout(2500);
  const t = await body();
  const after = (await workspace('admin')).revision;
  assert(after === before, `workspace revision moved on a failed load (${before} -> ${after})`);
  assert(!/revision 0\b/.test(t), 'app shows an empty revision-0 workspace');
});

// ------------------------------------------------------------------ K. Curriculum catalogue, resources, draft NCERT staging
await S('K01', 'admin', 'Curriculum catalogue loads and does not present draft NCERT staging as verified or complete', 'Page loads; no completeness / production-ready claim', async () => {
  await loginUi(page, 'admin');
  await page.goto(`${WEB}/curriculum/catalogue`);
  await page.waitForTimeout(2500);
  const t = await body();
  await shot(page, 'K01_catalogue');
  assert(!/production[- ]ready|complete curriculum|fully verified/i.test(t) || /not (production|complete)/i.test(t), 'catalogue claims completeness');
  const i = t.indexOf('Curriculum Catalogue');
  return t.slice(i, i + 240);
});

await S('K02', 'admin', 'Only conceptual topics are schedulable units in the planner', 'Class VII Mathematics shows exactly 2 unit rows (topics); the scheduler has 2 lessons', async () => {
  await goPlanner('admin');
  await page.getByRole('tab', { name: 'Syllabus & classification' }).click();
  const n = await page.locator('[data-testid^="unit-"]').count();
  assert(n === 2, `unit rows ${n}`);
  assert(!/\bactivity\b|\binvestigation\b/i.test(await page.locator('[data-testid^="unit-"]').first().locator('p').first().innerText()), 'a resource shown as a unit');
  assert((await planOf()).versions[1].lessons.length === 2, 'scheduler lesson count');
});

await S('K03', 'admin', 'Staged NCERT review batch (isolated database)', 'Draft structure only: 540 nodes, complete_curriculum=false, production_ready=false', async () => {
  const rep = JSON.parse(fs.readFileSync(`${process.env.ACCEPT_DIR}/stage_report.json`, 'utf8'));
  assert(rep.status === 'STAGED_DRAFT' && rep.nodes_written === 540 && rep.complete_curriculum === false && rep.production_ready === false, JSON.stringify({ s: rep.status, n: rep.nodes_written }));
  return `status ${rep.status}, nodes ${rep.nodes_written}, complete_curriculum=${rep.complete_curriculum}`;
});

// ------------------------------------------------------------------ L. UI sweep: routes, console errors, overflow, keyboard, responsive
const sweep = {
  admin: ['/admin/dashboard', '/admin/schools', '/admin/users', '/admin/academic-config', '/admin/audit-logs', '/teacher/time-aware', '/curriculum/catalogue'],
  principal: ['/principal/dashboard', '/principal/teachers', '/principal/curriculum', '/principal/reports', '/principal/academic-config'],
  teacher: ['/teacher/dashboard', '/teacher/classes', '/teacher/assessments', '/teacher/curriculum-180', '/teacher/time-aware', '/teacher/scan-review', '/teacher/remediation'],
  student: ['/student/dashboard'],
  parent: ['/parent/dashboard'],
};
for (const [role, routes] of Object.entries(sweep)) {
  for (const width of [1440, 390]) {
    await S(`L-${role}-${width}`, role, `UI sweep at ${width}px`, 'Every route renders content, no uncaught errors, no horizontal page overflow, no redirect away', async () => {
      await page.setViewportSize({ width, height: 900 });
      await loginUi(page, role);
      const problems = [];
      for (const r of routes) {
        const errsBefore = consoleIssues.length;
        await page.goto(`${WEB}${r}`);
        await page.waitForTimeout(900);
        const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth, len: document.body.innerText.trim().length, h: !!document.querySelector('h1,h2') }));
        if (m.sw > m.iw + 4) problems.push(`${r}: horizontal overflow ${m.sw}>${m.iw}`);
        if (m.len < 80) problems.push(`${r}: nearly empty page`);
        if (!m.h) problems.push(`${r}: no heading`);
        if (/\/unauthorized|\/login/.test(page.url())) problems.push(`${r}: redirected to ${page.url().replace(WEB, '')}`);
        consoleIssues.slice(errsBefore).filter((c) => /PAGEERROR|TypeError|ReferenceError/.test(c.text)).forEach((c) => problems.push(`${r}: ${c.text.slice(0, 100)}`));
        if (width === 390) await shot(page, `L_${role}_${r.replace(/\//g, '_')}_390`);
      }
      assert(problems.length === 0, problems.join(' ; '));
      return `${routes.length} routes ok`;
    });
  }
}
await page.setViewportSize({ width: 1440, height: 900 });

await S('L-keyboard', 'teacher', 'Keyboard: Record a Lost Day dialog is operable and dismissible', 'Reachable by keyboard, role=dialog, focus moves into it, Escape closes it', async () => {
  await goPlanner('teacher');
  await page.getByTestId('lost-period-recorder').getByRole('button', { name: 'Record a Lost Day' }).focus();
  await page.keyboard.press('Enter');
  await page.getByRole('dialog').waitFor({ timeout: 3000 });
  const inside = await page.evaluate(() => !!document.activeElement?.closest('[role=dialog]'));
  await page.keyboard.press('Escape');
  await page.waitForTimeout(400);
  const closed = (await page.getByRole('dialog').count()) === 0;
  assert(inside, 'focus did not move into the dialog');
  assert(closed, 'Escape did not close the dialog');
});

await S('L-404', 'teacher', 'Unknown route', 'A not-found page, not a blank screen', async () => {
  await loginUi(page, 'teacher');
  await page.goto(`${WEB}/no/such/route`);
  await page.waitForTimeout(800);
  assert(/not found|404/i.test(await body()), 'no not-found page');
});

const OUT = process.env.OUT_DIR || '.';
fs.writeFileSync(`${OUT}/e2e-state.json`, JSON.stringify(state, null, 1));
const out = { ...report(), browser: `Microsoft Edge ${version} via playwright-core`, when: new Date().toISOString() };
fs.writeFileSync(`${OUT}/e2e-results.json`, JSON.stringify(out, null, 1));
const fails = out.results.filter((r) => r.result !== 'PASS');
console.log(`\n${out.results.length - fails.length}/${out.results.length} passed`);
await browser.close();
