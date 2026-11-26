// Live regression check for the recovered NCERT review-batch dataset.
// Uses the restored shared workspace and the real Catalogue/Time-Aware pages in Microsoft Edge.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const appDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourcePath = path.resolve(appDir, '../../scratchpad/acceptance/recovered_ncert_dataset.json');
const evidenceDir = path.resolve(appDir, 'e2e-shots/20261112-syllabus-restoration');
const api = process.env.API_URL ?? 'http://localhost:8000/api/v1';
const web = process.env.WEB_URL ?? 'http://localhost:3000';
fs.mkdirSync(evidenceDir, { recursive: true });
const logPath = path.join(evidenceDir, 'restoration.log');
const log = (line) => {
  const entry = `${new Date().toISOString()} ${line}`;
  console.log(entry);
  fs.appendFileSync(logPath, `${entry}\n`);
};
const assert = (condition, message) => { if (!condition) throw new Error(message); };
const original = JSON.parse(fs.readFileSync(sourcePath, 'utf8'));
const grades = [6, 7, 8];
const subjects = ['Mathematics', 'Science'];
const roman = { 6: 'VI', 7: 'VII', 8: 'VIII' };

async function readWorkspace() {
  const login = await fetch(`${api}/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'admin@lumeneios.demo', password: 'demo123' }),
  });
  assert(login.ok, `Admin API login failed: ${login.status}`);
  const { access_token: token } = await login.json();
  const response = await fetch(`${api}/planning/workspace`, { headers: { Authorization: `Bearer ${token}` } });
  assert(response.ok, `Workspace API failed: ${response.status}`);
  return response.json();
}

const ws = await readWorkspace();
const dataset = ws.state?.datasets?.find((row) => row.id === original.id);
assert(dataset, `Recovered dataset ${original.id} is missing from the persisted isolated workspace.`);
assert(dataset.nodes.length === 531 && dataset.textbooks.length === 8, 'Persisted dataset count differs from the recovered source.');
const nodeIds = dataset.nodes.map((node) => node.id);
assert(new Set(nodeIds).size === nodeIds.length, 'Persisted dataset has duplicate node IDs.');
assert(JSON.stringify(dataset) === JSON.stringify(original), 'Persisted data differs from the exact recovered dataset artifact.');
log(`API verified persisted ${dataset.id}: ${dataset.textbooks.length} textbooks, ${dataset.nodes.length} unique nodes, workspace revision ${ws.revision}.`);

const expected = new Map();
for (const grade of grades) for (const subject of subjects) {
  const books = dataset.textbooks.filter((book) => book.grade === grade && book.subject === subject);
  const nodes = dataset.nodes.filter((node) => books.some((book) => book.id === node.textbookId));
  const children = new Set(nodes.filter((node) => ['TOPIC', 'SUBTOPIC'].includes(node.kind) && node.parentId).map((node) => node.parentId));
  const units = nodes.filter((node) => ['TOPIC', 'SUBTOPIC'].includes(node.kind) && !children.has(node.id));
  const row = { books, nodes, units, chapters: nodes.filter((node) => node.kind === 'CHAPTER') };
  assert(row.chapters.length > 0 && row.units.length > 0, `Missing complete syllabus for Class ${grade} ${subject}.`);
  expected.set(`${grade}/${subject}`, row);
}

const browser = await chromium.launch({ channel: 'msedge', headless: false });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
page.on('pageerror', (error) => log(`BROWSER ERROR ${error.message}`));

try {
  await page.goto(`${web}/login`);
  await page.getByPlaceholder('e.g. teacher@lumeneios.demo').fill('teacher@lumeneios.demo');
  await page.getByPlaceholder('demo123').fill('demo123');
  await page.getByRole('button', { name: 'Sign In to Dashboard' }).click();
  await page.waitForURL(/\/teacher\//, { timeout: 20000 });
  await page.goto(`${web}/curriculum/catalogue`);
  await page.waitForSelector('[data-testid="curriculum-catalogue"]');
  await page.getByRole('button', { name: 'Class VI', exact: true }).click();
  await page.getByTestId('combo-6-mathematics').click();
  await page.waitForSelector('[data-testid="syllabus-view"]');

  for (const grade of grades) for (const subject of subjects) {
    if (grade !== 6 || subject !== 'Mathematics') {
      await page.getByRole('radio', { name: `Class ${roman[grade]}`, exact: true }).click();
      await page.getByRole('radio', { name: subject, exact: true }).click();
    }
    await page.waitForFunction(([g, s]) => {
      const heading = document.querySelector('[data-testid="syllabus-view"]')?.textContent ?? '';
      return heading.includes(`Class ${g}`) && heading.includes(s);
    }, [roman[grade], subject]);
    const row = expected.get(`${grade}/${subject}`);
    const visibleChapters = await page.locator('[data-testid^="chapter-"]').evaluateAll((els) => els.filter((el) => !/^chapter-(status|count)-/.test(el.getAttribute('data-testid'))).length);
    assert(visibleChapters === row.chapters.length, `Class ${grade} ${subject}: visible chapters ${visibleChapters}, expected ${row.chapters.length}.`);
    assert(await page.getByTestId('coverage-total').innerText() === String(row.units.length), `Class ${grade} ${subject}: coverage count differs from source eligible-unit count.`);
    for (const chapter of row.chapters) assert(await page.getByTestId(`chapter-${chapter.id}`).count() === 1, `Chapter missing from UI: ${chapter.title}`);
    await page.getByRole('button', { name: 'Expand all' }).click();
    for (const node of row.nodes.filter((entry) => ['TOPIC', 'SUBTOPIC'].includes(entry.kind))) {
      assert(await page.getByTestId(`topic-${node.id}`).count() === 1, `Structural topic hidden from Class ${grade} ${subject}: ${node.title}`);
    }
    const tag = `${String(grade).padStart(2, '0')}-${subject.toLowerCase().replaceAll(' ', '-')}`;
    await page.screenshot({ path: path.join(evidenceDir, `${tag}-expanded.png`), fullPage: true });
    const titleList = row.books.map((book) => book.title + (book.part ? ` ${book.part}` : '')).join(' + ');
    log(`BROWSER PASS Class ${roman[grade]} ${subject}: dataset=${dataset.id}; books=${titleList}; chapters=${row.chapters.length}; topics=${row.nodes.filter((node) => node.kind === 'TOPIC').length}; subtopics=${row.nodes.filter((node) => node.kind === 'SUBTOPIC').length}; eligible=${row.units.length}; visible structural entries=${row.nodes.filter((node) => ['TOPIC', 'SUBTOPIC'].includes(node.kind)).length}.`);
  }

  await page.getByRole('link', { name: /Time-Aware Engine/ }).first().click();
  await page.getByLabel('Class').selectOption('6');
  await page.getByLabel('Subject').selectOption('Science');
  await page.waitForFunction(() => document.querySelectorAll('[data-testid^="ta-coverage-"]').length > 0);
  const science = expected.get('6/Science');
  const expectedUnitIds = science.units.map((unit) => unit.id).sort();
  const timeAwareIds = (await page.locator('[data-testid^="ta-coverage-"]').evaluateAll((els) => els.map((el) => el.getAttribute('data-testid').slice('ta-coverage-'.length)).sort()));
  assert(JSON.stringify(timeAwareIds) === JSON.stringify(expectedUnitIds), 'Time-Aware uses different topic identities from the Catalogue.');
  await page.screenshot({ path: path.join(evidenceDir, 'time-aware-class-vi-science.png'), fullPage: true });
  log(`BROWSER PASS Time-Aware Class VI Science shares all ${timeAwareIds.length} schedulable topic IDs with the Catalogue.`);

  await page.goto(`${web}/curriculum/catalogue/6/science`);
  await page.waitForSelector('[data-testid="syllabus-view"]');
  await page.getByRole('button', { name: 'Expand all' }).click();
  await page.screenshot({ path: path.join(evidenceDir, 'final-class-vi-science-expanded.png'), fullPage: true });
  fs.writeFileSync(path.join(evidenceDir, 'browser.pid'), String(process.pid));
  log('PASS Complete syllabus restoration walkthrough; Edge left open on Class VI Science expanded.');
  await new Promise(() => {});
} catch (error) {
  log(`FAIL ${error.stack ?? error}`);
  await browser.close();
  process.exitCode = 1;
}
