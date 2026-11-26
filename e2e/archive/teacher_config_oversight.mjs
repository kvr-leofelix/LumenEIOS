// Companion run: Time-Aware Engine, Planning Oversight, Coverage Oversight and Central Logs read the same persisted plan.
import { WEB, assert, launch, shot } from '../lib.mjs';
const { page, browser } = await launch(); const out = [];
const run = async (id, fn) => { try { const n = await fn(); out.push(1); console.log('PASS', id, n ?? ''); } catch (e) { out.push(0); console.log('FAIL', id, String(e.message).split('\n')[0]); await shot(page, id + '_FAIL'); } };
const login = async (email) => { await page.goto(`${WEB}/login`); await page.evaluate(() => localStorage.clear()); await page.goto(`${WEB}/login`);
  await page.locator('input').first().fill(email); await page.locator('input[type="password"]').fill('demo123'); await page.getByRole('button', { name: /^Sign in/ }).click(); await page.waitForURL((u) => !u.pathname.includes('login'), { timeout: 20000 }); };
const text = async () => (await page.innerText('body')).replace(/\s+/g, ' ');
await run('O1 Time-Aware (teacher, Class VI Science) shows saved requirements, no "Not configured"', async () => {
  await login('teacher@lumeneios.demo'); await page.goto(`${WEB}/teacher/time-aware`); await page.getByLabel('Class').selectOption('6'); await page.getByLabel('Subject').selectOption('Science'); await page.waitForTimeout(6000);
  const t = await text(); assert(!/Not configured/.test(t), 'Not configured present'); assert(/Core \/ \d+ Non-Core/.test(t) || /\d+\s*Core/.test(t), 'no requirements rendered'); await shot(page, 'o1_time_aware'); return t.includes('Core') ? 'Core/Non-Core present' : 'no table yet';
});
await run('O2 Planning Oversight (principal) lists the teacher plan', async () => {
  await login('principal@lumeneios.demo'); await page.goto(`${WEB}/principal/curriculum`); await page.waitForTimeout(5000);
  const t = await text(); assert(/Garima/.test(t), 'teacher missing'); await shot(page, 'o2_planning_oversight'); return 'Garima listed';
});
await run('O3 Coverage Oversight shows the persisted Done count (1 of 65 = 1.5%)', async () => {
  await page.goto(`${WEB}/principal/coverage`); await page.waitForTimeout(5000); const t = await text(); await shot(page, 'o3_coverage_oversight');
  assert(/Garima/.test(t) && /1\.5\s?%/.test(t), t.slice(0, 300)); return '1.5% present';
});
await run('O4 Central Logs record the classification/coverage changes', async () => {
  await page.goto(`${WEB}/logs`); await page.waitForTimeout(4000); const t = await text(); await shot(page, 'o4_logs');
  assert(/topic_classification|classification|coverage/i.test(t), t.slice(0, 200));
});
await browser.close(); process.exit(out.every(Boolean) ? 0 : 1);
