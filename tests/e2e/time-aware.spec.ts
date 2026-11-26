import { test, expect } from './fixtures';
import type { Page } from '@playwright/test';

// Flagship workflow: the teacher generates a schedule, the principal approves it, the teacher records two lost
// Core periods, the engine proposes a recovery, and the principal's approval produces schedule version 2 in which
// no Core period is left unscheduled.
const PASSWORD = 'browser-test-password';
const API = 'http://127.0.0.1:18080/api/v1';

async function signIn(page: Page, email: string) {
  await page.goto('/login');
  await page.evaluate(() => localStorage.clear());
  await page.goto('/login');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveURL(/dashboard/, { timeout: 20000 });
}

async function openEngine(page: Page) {
  await page.goto('/teacher/time-aware');
  await page.getByLabel('Class', { exact: true }).selectOption({ label: 'Class VII' });
  await page.getByLabel('Subject', { exact: true }).selectOption({ label: 'Science' });
  await expect(page.getByRole('heading', { name: /capacity and remaining syllabus/ })).toBeVisible({ timeout: 20000 });
}

test('schedule, approval, lost periods and Core-protecting recovery', async ({ page, request }) => {
  page.on('dialog', (d) => d.accept());
  const teacher = 'garima.sharma@sps.lumeneios.demo', principal = 'lakshmi.narayanan@sps.lumeneios.demo';

  // 1. Teacher generates the draft schedule for the remaining teaching days.
  await signIn(page, teacher);
  await openEngine(page);
  await page.getByRole('button', { name: 'Generate draft schedule for approval' }).click();
  await expect(page.getByText(/Draft saved for Class VII Science/)).toBeVisible({ timeout: 20000 });

  // 2. Principal approves it in Planning Oversight.
  await signIn(page, principal);
  await page.goto('/principal/curriculum');
  await page.getByRole('button', { name: 'Approve teaching schedule' }).first().click();
  await expect(page.getByRole('button', { name: 'Approve teaching schedule' })).toHaveCount(0, { timeout: 20000 });

  // 3. Teacher records two lost Core periods followed by Non-Core work the engine can move.
  await signIn(page, teacher);
  await openEngine(page);
  await page.getByRole('button', { name: 'Record a Lost Day' }).click();
  const dialog = page.getByRole('dialog', { name: 'Record a Lost Day' });
  const rows = dialog.getByRole('row').filter({ hasText: 'Scheduled' });
  // The first day whose two periods are both Core and whose following periods include Non-Core work.
  const texts = await rows.allInnerTexts();
  const isCore = (t: string) => /\bCore\b/.test(t) && !/Non-Core/.test(t);
  let pick = -1;
  for (let i = 0; i + 3 < texts.length; i++) {
    if (isCore(texts[i]) && isCore(texts[i + 1]) && texts.slice(i + 2, i + 8).some((t) => /Non-Core/.test(t))) { pick = i; break; }
  }
  expect(pick, 'a Core day followed by Non-Core work').toBeGreaterThanOrEqual(0);
  await rows.nth(pick).getByRole('checkbox').check();
  await rows.nth(pick + 1).getByRole('checkbox').check();
  await dialog.getByLabel('Loss reason').selectOption({ label: 'Extreme Weather' });
  await dialog.getByLabel('Loss note').fill('Red alert - school closed.');
  await dialog.getByRole('button', { name: /^Record 2 lost period/ }).click();
  await expect(dialog).toHaveCount(0, { timeout: 20000 });

  // 4. A recovery proposal recovers both Core periods; the principal approves it.
  await signIn(page, principal);
  await page.goto('/principal/curriculum');
  await expect(page.getByText(/Proposed, not yet approved: 2 Core period\(s\) recovered/).first()).toBeVisible({ timeout: 20000 });
  await page.getByRole('button', { name: /Approve recovery/ }).first().click();
  await expect(page.getByRole('button', { name: /Approve recovery/ })).toHaveCount(0, { timeout: 20000 });

  // The approved plan is now version 2 with its recovery proposal approved.
  const login = await request.post(API + '/auth/login', { data: { email: principal, password: PASSWORD } });
  const token = (await login.json()).access_token;
  const plans = await (await request.get(API + '/plans', { headers: { Authorization: 'Bearer ' + token } })).json();
  const plan = plans.plans.find((p: { grade: number; subject: string; status: string }) => p.grade === 7 && p.subject === 'Science' && p.status === 'APPROVED');
  expect(plan.versions.map((v: { version: number }) => v.version)).toEqual([1, 2]);
  expect(plan.proposals.map((p: { status: string }) => p.status)).toEqual(['APPROVED']);
});
