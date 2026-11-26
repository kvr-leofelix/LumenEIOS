// Real HTTP/database acceptance. No mocked API responses or browser demo store.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from '@playwright/test';

const run = path.resolve(process.env.LUMENEIOS_SEEDED_RUN_DIR || '.local-demo/seeded-acceptance-verified-20261119');
const root = path.resolve('.local-demo');
assert.ok(run.startsWith(root + path.sep), 'Only an isolated .local-demo run is permitted');
const accounts = JSON.parse(await readFile(path.join(run, 'seed-accounts.json'), 'utf8'));
const workflow = JSON.parse(await readFile(path.join(run, 'workflow.json'), 'utf8'));
const origin = 'http://127.0.0.1:18881';
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const results = [];
let activePage;
try {
  for (const role of ['teacher', 'student', 'parent', 'principal']) {
    const user = accounts.find(u => role === 'student' ? u.id === workflow.student_id
      : role === 'teacher' ? u.id === 'user-teacher-garima'
      : role === 'principal' ? u.id === 'user-principal-1'
      : u.id === workflow.parent_id);
    assert.ok(user, 'Existing seed account required for ' + role);
    const context = await browser.newContext();
    const page = await context.newPage();
    activePage = page;
    page.setDefaultTimeout(15000);
    const failed = [];
    page.on('pageerror', error => { failed.push(error.message); console.error('Browser exception:', error.message); });
    await page.route('**/*', route => ['http://127.0.0.1:18881', 'http://127.0.0.1:18880'].includes(new URL(route.request().url()).origin)
      ? route.continue() : route.abort('blockedbyclient'));
    await page.goto(origin + '/login');
    await page.getByLabel('Email', { exact: true }).fill(user.email);
    await page.getByLabel('Password', { exact: true }).fill(user.password);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await page.waitForURL('**/' + role + '/dashboard');
    await page.getByRole('main').waitFor();
    await page.goto(origin + '/learnsphere/support');
    await page.getByRole('heading', { name: 'Learning Support', exact: true }).waitFor();
    await page.getByLabel('Learning Support assessment').waitFor();
    const selector = page.getByLabel('Learning Support assessment');
    // Educator selectors start at the first pupil; explicitly select the exercised seed record.
    const studentSelect = page.getByLabel('Student', { exact: true });
    await page.getByLabel('Authorized class', { exact: true }).selectOption('class-sps-7a');
    if (await studentSelect.count()) await studentSelect.selectOption(workflow.student_id);
    await selector.selectOption(workflow.assessment_id);
    await page.getByText('Question marks are teacher-reviewed.', { exact: false }).waitFor();
    assert.ok((await page.locator('body').innerText()).includes('Acceptance fixture guidance for Q1'));
    if (role === 'student' || role === 'parent') {
      assert.equal(await page.getByRole('button', { name: 'Review and confirm assessment', exact: true }).count(), 0);
      assert.equal(await page.getByText('Review primary competency', { exact: true }).count(), 0);
    }
    await page.goto(origin + '/learnsphere/journey');
    await page.getByRole('heading', { name: 'Panchapadi Progress', exact: true }).waitFor();
    await page.getByLabel('Authorized class', { exact: true }).selectOption('class-sps-7a');
    await page.getByLabel('Student', { exact: true }).selectOption(workflow.student_id);
    for (const stage of ['Adheeti', 'Bodh', 'Abhyas', 'Prayog', 'Prasar']) {
      await page.getByRole('heading', { name: stage + ' Progress', exact: true }).waitFor();
    }
    await page.waitForFunction(() => document.querySelectorAll('circle.assessment-progress-dot[data-status="confirmed"]').length === 5);
    await page.reload();
    await page.getByRole('heading', { name: 'Panchapadi Progress', exact: true }).waitFor();
    await page.getByLabel('Authorized class', { exact: true }).selectOption('class-sps-7a');
    await page.getByLabel('Student', { exact: true }).selectOption(workflow.student_id);
    await page.waitForFunction(() => document.querySelectorAll('circle.assessment-progress-dot[data-status="confirmed"]').length === 5);
    await page.screenshot({ path: path.join(run, role + '-journey.png'), fullPage: true });
    assert.deepEqual(failed, [], role + ' browser exceptions');
    results.push({ role, dashboard: true, persistedSupport: true, fiveStageJourney: true, reload: true });
    await context.close();
  }
  await writeFile(path.join(run, 'browser.json'), JSON.stringify(results, null, 2));
  console.log('PASS live seeded database browser checks for teacher, student, parent and principal');
} catch (error) {
  console.error('Browser URL:', activePage?.url());
  console.error('Browser body:', (await activePage?.locator('body').innerText())?.slice(0, 3000));
  await activePage?.screenshot({ path: path.join(run, 'browser-failure.png'), fullPage: true });
  throw error;
} finally {
  await browser.close();
}
