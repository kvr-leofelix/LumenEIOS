import { test, expect } from './fixtures';

// Every role signs in through the real form and its main pages render without errors or failed API calls.
// The isolated browser server seeds the demonstration roster with one test password for every account.
const PASSWORD = 'browser-test-password';
const ROLES: { who: string; email: string; landing: RegExp; pages: { path: string; heading: RegExp }[] }[] = [
  { who: 'teacher', email: 'garima.sharma@sps.lumeneios.demo', landing: /\/teacher\/dashboard/, pages: [
    { path: '/teacher/classes', heading: /Classroom Roster/ },
    { path: '/teacher/time-aware', heading: /Time-Aware Engine/ },
    { path: '/teacher/homework', heading: /Differentiated Homework/ },
    { path: '/teacher/assessments', heading: /AI Question Studio/ },
    { path: '/upload', heading: /Upload/ },
    { path: '/learnsphere/journey', heading: /LearnSphere/ },
  ] },
  { who: 'student', email: 'gurleen.kaur@sps.lumeneios.demo', landing: /\/student\/dashboard/, pages: [
    { path: '/student/progress', heading: /Unified Student Progress/ },
    { path: '/student/homework', heading: /Differentiated Homework/ },
    { path: '/upload', heading: /Upload/ },
  ] },
  { who: 'parent', email: 'harpreet.kaur@sps.lumeneios.demo', landing: /\/parent\/dashboard/, pages: [
    { path: '/parent/homework', heading: /Differentiated Homework/ },
    { path: '/parent/progress', heading: /Unified Student Progress/ },
  ] },
  { who: 'principal', email: 'lakshmi.narayanan@sps.lumeneios.demo', landing: /\/principal\/dashboard/, pages: [
    { path: '/principal/curriculum', heading: /Planning Oversight/ },
    { path: '/principal/performance', heading: /School performance/ },
  ] },
  { who: 'management', email: 'ananya.rao@trust.lumeneios.demo', landing: /\/admin\/dashboard/, pages: [
    { path: '/admin/schools', heading: /Affiliated Schools Directory/ },
    { path: '/admin/users', heading: /User Directory/ },
  ] },
];

for (const role of ROLES) {
  test(`${role.who} signs in and every main page renders`, async ({ page }) => {
    const problems: string[] = [];
    page.on('pageerror', (e) => problems.push(`JS ${e.message}`));
    page.on('response', (r) => { if (r.url().includes('/api/') && r.status() >= 500) problems.push(`${r.status()} ${r.url()}`); });
    await page.goto('/login');
    await page.getByLabel('Email', { exact: true }).fill(role.email);
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page).toHaveURL(role.landing, { timeout: 20000 });
    await expect(page.getByRole('heading').first()).toBeVisible();
    for (const p of role.pages) {
      await page.goto(p.path);
      await expect(page.getByRole('heading', { name: p.heading }).first()).toBeVisible({ timeout: 20000 });
    }
    expect(problems).toEqual([]);
  });
}

test('a wrong password is refused and no session is created', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Email', { exact: true }).fill('garima.sharma@sps.lumeneios.demo');
  await page.getByLabel('Password', { exact: true }).fill('not-the-password');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('alert').first()).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});
