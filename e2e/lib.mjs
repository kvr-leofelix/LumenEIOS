// Shared helpers for the real-browser acceptance run (Playwright driving the installed Microsoft Edge).
import { chromium } from 'playwright-core';
import fs from 'node:fs';

export const WEB = process.env.WEB_URL || 'http://localhost:3000';
export const API = process.env.API_URL || 'http://localhost:8000/api/v1';
export const SHOTS = process.env.SHOTS || './e2e-shots';
fs.mkdirSync(SHOTS, { recursive: true });

export const results = [];
export const consoleIssues = [];
export const networkIssues = [];
let current = '';

export async function launch() {
  const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.on('console', (m) => {
    if (m.type() === 'error') consoleIssues.push({ step: current, text: m.text().slice(0, 240) });
  });
  page.on('pageerror', (e) => consoleIssues.push({ step: current, text: 'PAGEERROR ' + String(e.message).slice(0, 240) }));
  page.on('response', (r) => {
    if (r.status() >= 400 && r.url().startsWith(API)) networkIssues.push({ step: current, status: r.status(), url: r.url().replace(API, ''), method: r.request().method() });
  });
  return { browser, context, page, version: browser.version() };
}

export function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

export async function step(id, role, workflow, expected, fn, page) {
  current = id;
  try {
    const actual = await fn();
    results.push({ id, role, workflow, expected, actual: actual ?? 'As expected', result: 'PASS' });
    console.log(`PASS ${id} ${workflow}`);
  } catch (e) {
    const msg = String(e.message).split('\n')[0].slice(0, 400);
    results.push({ id, role, workflow, expected, actual: msg, result: 'FAIL' });
    console.log(`FAIL ${id} ${workflow}: ${msg}`);
    if (page) await page.screenshot({ path: `${SHOTS}/${id}_FAIL.png`, fullPage: true }).catch(() => {});
  }
}

export async function shot(page, name) {
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true }).catch(() => {});
}

/** Demonstration accounts (see docs/LOGIN_CREDENTIALS.md). The admin persona is labelled "management" on the sign-in page. */
export const ACCOUNTS = {
  admin: { email: 'ananya.rao@trust.lumeneios.demo', password: 'Admin@123', button: 'management' },
  principal: { email: 'lakshmi.narayanan@sps.lumeneios.demo', password: 'Principal@123', button: 'principal' },
  teacher: { email: 'garima.sharma@sps.lumeneios.demo', password: 'Teacher@123', button: 'teacher' },
  student: { email: 'gurleen.kaur@sps.lumeneios.demo', password: '14022013', button: 'student' },
  parent: { email: 'harpreet.kaur@sps.lumeneios.demo', password: 'Parent@123', button: 'parent' },
};

export async function loginUi(page, role) {
  await page.goto(`${WEB}/login`);
  await page.evaluate(() => localStorage.clear());
  await page.goto(`${WEB}/login`);
  await page.getByRole('button', { name: `Login as ${ACCOUNTS[role]?.button ?? role}` }).click();
  await page.waitForURL(new RegExp(`/${role}/`), { timeout: 15000 });
}

/** Waits until the shared planning store has loaded from the backend (not browser-only, not an error). */
export async function storeReady(page) {
  await page.waitForFunction(() => /Shared planning store \(backend\)/.test(document.body.innerText), null, { timeout: 20000 });
}

export async function token(role) {
  const r = await fetch(`${API}/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: ACCOUNTS[role].email, password: ACCOUNTS[role].password }) });
  assert(r.ok, `API login for ${role} failed: ${r.status}`);
  return (await r.json()).access_token;
}

export async function api(method, path, tok, body) {
  const r = await fetch(`${API}${path}`, { method, headers: { 'Content-Type': 'application/json', ...(tok ? { Authorization: `Bearer ${tok}` } : {}) }, body: body ? JSON.stringify(body) : undefined });
  let json = null;
  try { json = await r.json(); } catch { /* no body */ }
  return { status: r.status, json };
}

export async function workspace(role = 'admin') {
  const r = await api('GET', '/planning/workspace', await token(role));
  assert(r.status === 200, `workspace GET ${r.status}`);
  return r.json;
}

export function report() {
  return { results, consoleIssues, networkIssues };
}
