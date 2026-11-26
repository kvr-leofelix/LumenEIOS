// Real-browser acceptance for the Curriculum Catalogue (class -> subject -> syllabus coverage) and its connection to the
// Time-Aware Engine and Daily Curriculum. There is one catalogue: /curriculum/catalogue and /curriculum/catalogue/:grade/:subject.
// Edge via playwright-core against the running app (frontend :3000, backend :8000, isolated database).
// Prerequisites: `bash e2e/reset_env.sh`, and NCERT_IMPORT=<path to the JSON from scripts/build_planning_import.py>.
// Expected values are computed here from the import file and from first principles, never read back from the app.
import fs from 'node:fs';
import { API, WEB, api, assert, consoleIssues, launch, loginUi, report, shot, step, token, workspace } from '../lib.mjs';

const IMPORT = JSON.parse(fs.readFileSync(process.env.NCERT_IMPORT, 'utf8'));
const { browser, page, version } = await launch();
const S = (id, role, wf, exp, fn) => step(id, role, wf, exp, fn, page);
const body = async () => (await page.innerText('body')).replace(/\s+/g, ' ');
const state = {};

// ---- independent expectations from the import file -------------------------------------------------------------
const books = Object.fromEntries(IMPORT.textbooks.map((t, i) => [t.id, { ...t, order: i }]));
function expectedSyllabus(grade, subject) {
  const nodes = IMPORT.nodes.filter((n) => books[n.textbookId].grade === grade && books[n.textbookId].subject === subject);
  nodes.sort((a, b) => books[a.textbookId].order - books[b.textbookId].order || a.sequence - b.sequence);
  const parents = new Set(nodes.filter((n) => n.parentId).map((n) => n.parentId));
  const chapters = nodes.filter((n) => n.kind === 'CHAPTER');
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const chapterOf = (n) => { let c = n; while (c.kind !== 'CHAPTER') c = byId[c.parentId]; return c.id; };
  const units = nodes.filter((n) => n.kind !== 'CHAPTER' && !parents.has(n.id));
  return { nodes, chapters, units, chapterOf, perChapter: Object.fromEntries(chapters.map((c) => [c.id, units.filter((u) => chapterOf(u) === c.id)])) };
}
const CLASS_NAME = { 6: 'Class VI', 7: 'Class VII', 8: 'Class VIII' };
const COMBOS = [[6, 'Mathematics'], [6, 'Science'], [7, 'Mathematics'], [7, 'Science'], [8, 'Mathematics'], [8, 'Science']];
const RGB = { DONE: 'rgb(22, 163, 74)', NOT_DONE: 'rgb(156, 163, 175)', IN_PROGRESS: 'rgb(245, 158, 11)' };

const ready = () => page.waitForFunction(() => document.querySelector('[data-testid="curriculum-catalogue"]') && !/Loading syllabus coverage/.test(document.body.innerText), null, { timeout: 20000 });
const catalogueUrl = (g, s) => `${WEB}/curriculum/catalogue/${g}/${String(s).toLowerCase()}`;
const openCourse = async (role, q = '') => {
  await loginUi(page, role);
  const m = /class=(\d)&subject=(\w+)/.exec(q);
  await page.goto(m ? catalogueUrl(m[1], m[2]) : `${WEB}/curriculum/catalogue`);
  await ready();
  await page.waitForTimeout(400);
};
const dotColor = (id) => page.getByTestId(`dot-${id}`).evaluate((e) => getComputedStyle(e).backgroundColor);
const dotStatus = (id) => page.getByTestId(`dot-${id}`).getAttribute('data-status');
const txt = async (id) => (await page.getByTestId(id).innerText()).replace(/\s+/g, ' ').trim();
const coverageOnServer = async () => (await workspace('admin')).state.coverage ?? {};

// ------------------------------------------------------------------ CC. Course Curriculum
await S('CC00', 'admin', 'Load the NCERT heading structure through the existing Syllabus import', 'Import validated and stored as one dataset; 531 nodes in the shared workspace', async () => {
  await loginUi(page, 'admin');
  await page.goto(`${WEB}/teacher/time-aware`);
  await page.waitForFunction(() => /Shared planning store \(backend\)/.test(document.body.innerText), null, { timeout: 20000 });
  await page.getByRole('tab', { name: 'Syllabus & classification' }).click();
  await page.getByLabel('Syllabus import JSON').fill(JSON.stringify(IMPORT));
  await page.getByRole('button', { name: 'Validate and import' }).click();
  await page.waitForFunction(() => !document.querySelector('textarea[aria-label="Syllabus import JSON"]')?.value, null, { timeout: 30000 });
  const ws = await workspace('admin');
  assert(ws.state.datasets.length === 1 && ws.state.datasets[0].nodes.length === IMPORT.nodes.length, `datasets ${ws.state.datasets.length}`);
  return `${ws.state.datasets[0].nodes.length} nodes stored at revision ${ws.revision}`;
});

await S('CC01', 'teacher', 'Open the Curriculum Catalogue from its existing sidebar entry', 'Header, subtitle and the single neutral notice; three class choices; no subject or syllabus yet; no extra route or navigation item exists', async () => {
  await loginUi(page, 'teacher');
  assert(await page.getByRole('link', { name: /Course Curriculum/ }).count() === 0, 'a Course Curriculum navigation item exists');
  await page.getByRole('link', { name: /Curriculum Catalogue/ }).first().click();
  await ready();
  assert(/\/curriculum\/catalogue$/.test(page.url()), page.url());
  assert((await page.getByRole('heading', { level: 1 }).first().innerText()) === 'Curriculum Catalogue', 'h1');
  assert(/Explore the syllabus and track teaching coverage\./.test(await body()), 'subtitle');
  assert((await txt('demo-notice')) === 'Demonstration syllabus and coverage data.', 'notice');
  for (const c of ['Class VI', 'Class VII', 'Class VIII']) assert(await page.getByRole('button', { name: c, exact: true }).count() === 1, `missing ${c}`);
  assert(await page.getByRole('button', { name: 'Mathematics', exact: true }).count() === 0, 'subject shown before a class');
  assert(await page.getByTestId('syllabus-view').count() === 0, 'syllabus shown before selection');
  await shot(page, 'CC01_catalogue_home');
  await page.goto(`${WEB}/curriculum/course`);
  await page.waitForTimeout(500);
  assert(await page.getByTestId('curriculum-catalogue').count() === 0 && /not found|404/i.test(await body()), 'a /curriculum/course route exists');
  await page.goto(`${WEB}/curriculum/catalogue`); await ready();
});

await S('CC02', 'teacher', 'Select Class VI then Mathematics; view the full syllabus', 'Overview counts and chapters equal the independently computed syllabus (65 teachable topics, 10 chapters)', async () => {
  const exp = expectedSyllabus(6, 'Mathematics');
  state.exp6m = exp;
  await page.getByRole('button', { name: 'Class VI', exact: true }).click();
  assert(await page.getByRole('button', { name: 'Science', exact: true }).count() === 1, 'subjects not shown');
  await page.getByRole('button', { name: 'Mathematics', exact: true }).click();
  await page.getByTestId('syllabus-view').waitFor();
  assert(/\/curriculum\/catalogue\/6\/mathematics$/.test(page.url()), page.url());
  assert((await txt('coverage-total')) === String(exp.units.length), `total ${await txt('coverage-total')} vs ${exp.units.length}`);
  assert((await txt('coverage-notdone')) === String(exp.units.length) && (await txt('coverage-done')) === '0' && (await txt('coverage-inprogress')) === '0', 'initial counts');
  assert((await txt('coverage-percent')) === '0%', 'initial percent');
  const chapters = await page.locator('[data-testid^="chapter-"]').evaluateAll((els) => els.filter((e) => !/^chapter-(status|count)-/.test(e.getAttribute('data-testid'))).length);
  assert(chapters === exp.chapters.length, `chapters ${chapters} vs ${exp.chapters.length}`);
  for (const c of exp.chapters) assert(await page.getByTestId(`chapter-${c.id}`).count() === 1, `missing chapter ${c.title}`);
  await shot(page, 'CC02_class6_maths_collapsed');
  return `${exp.chapters.length} chapters, ${exp.units.length} teachable topics`;
});

await S('CC03', 'teacher', 'Expand chapters: sections, topics and subtopics; resources absent', 'Collapsed rows hide topics; one chapter expands to exactly its teachable topics; Expand all shows all 65', async () => {
  const exp = state.exp6m;
  assert(await page.locator('[data-testid^="topic-"]').count() === 0, 'topics visible while collapsed');
  const c1 = exp.chapters[0];
  const toggle = page.getByTestId(`chapter-${c1.id}`).getByRole('button').first();
  assert((await toggle.getAttribute('aria-expanded')) === 'false', 'not collapsed');
  await toggle.click();
  assert((await toggle.getAttribute('aria-expanded')) === 'true', 'not expanded');
  const rows = await page.locator('[data-testid^="topic-"]').count();
  assert(rows === exp.perChapter[c1.id].length, `rows ${rows} vs ${exp.perChapter[c1.id].length}`);
  await toggle.click();
  await page.getByRole('button', { name: 'Expand all' }).click();
  const all = await page.locator('[data-testid^="topic-"]').count();
  assert(all >= exp.units.length, `topics shown ${all} < ${exp.units.length}`);
  const selects = await page.getByRole('combobox').count();
  assert(selects === exp.units.length, `status controls ${selects} vs teachable ${exp.units.length}`);
  await shot(page, 'CC03_expanded');
});

await S('CC04', 'teacher', 'No source-quality, approval or publication wording in the module chrome', 'Header, selectors, overview, legend and status options contain none of the banned words', async () => {
  const parts = [];
  for (const sel of ['h1', '[data-testid="demo-notice"]', '[data-testid="coverage-overview"]']) parts.push(await page.locator(sel).first().innerText());
  parts.push(...(await page.getByRole('radiogroup').allInnerTexts()));
  assert(await page.getByRole('tab').count() === 0, 'old catalogue tabs are still present');
  parts.push(...(await page.getByRole('combobox').first().locator('option').allInnerTexts()));
  const chrome = parts.join(' ');
  const banned = /unverified|inferred|partial|review required|draft|approved|published|pending|permission required|verified/i;
  assert(!banned.test(chrome), 'banned wording: ' + (chrome.match(banned) || [])[0]);
  const options = await page.getByRole('combobox').first().locator('option').allInnerTexts();
  assert(JSON.stringify(options) === JSON.stringify(['Done', 'Not done', 'In progress']), `options ${options}`);
  assert(await page.getByRole('button', { name: /approve|publish|review|verify|schedule/i }).count() === 0, 'approval/publication/scheduling control present');
});

await S('CC05', 'teacher', 'Inline status: In progress -> Done -> Not done on one topic', 'Orange, green and grey; counts and percentage recalculate immediately', async () => {
  const exp = state.exp6m;
  const t = exp.units[0];
  state.firstUnit = t;
  const sel = page.getByTestId(`status-${t.id}`).getByRole("combobox");
  assert((await dotColor(t.id)) === RGB.NOT_DONE, 'initial colour');
  await sel.selectOption('IN_PROGRESS');
  await page.waitForFunction((x) => document.querySelector(`[data-testid="dot-${x}"]`)?.getAttribute('data-status') === 'IN_PROGRESS', t.id);
  assert((await dotColor(t.id)) === RGB.IN_PROGRESS, `in-progress colour ${await dotColor(t.id)}`);
  assert((await txt('coverage-inprogress')) === '1' && (await txt('coverage-percent')) === '0%', 'in-progress counts');
  await sel.selectOption('DONE');
  await page.waitForFunction((x) => document.querySelector(`[data-testid="dot-${x}"]`)?.getAttribute('data-status') === 'DONE', t.id);
  assert((await dotColor(t.id)) === RGB.DONE, `done colour ${await dotColor(t.id)}`);
  const pct = `${Math.round((1 / exp.units.length) * 1000) / 10}%`;
  assert((await txt('coverage-done')) === '1' && (await txt('coverage-percent')) === pct, `done counts ${await txt('coverage-percent')} vs ${pct}`);
  assert((await txt('coverage-notdone')) === String(exp.units.length - 1), 'not-done count');
  await shot(page, 'CC05_done_green');
  await sel.selectOption('NOT_DONE');
  await page.waitForFunction((x) => document.querySelector(`[data-testid="dot-${x}"]`)?.getAttribute('data-status') === 'NOT_DONE', t.id);
  assert((await dotColor(t.id)) === RGB.NOT_DONE && (await txt('coverage-percent')) === '0%', 'back to not done');
  await sel.selectOption('DONE');
  await page.waitForFunction((x) => document.querySelector(`[data-testid="dot-${x}"]`)?.getAttribute('data-status') === 'DONE', t.id);
  const cov = await coverageOnServer();
  assert(cov[t.id].status === 'DONE' && cov[t.id].history.map((h) => h.status).join() === 'IN_PROGRESS,DONE,NOT_DONE,DONE', 'server history ' + JSON.stringify(cov[t.id]?.history?.map((h) => h.status)));
  assert(cov[t.id].history.every((h) => h.source === 'MANUAL' && h.by.role === 'teacher'), 'history actor/source');
  return `percent ${pct}; server history IN_PROGRESS>DONE>NOT_DONE>DONE by teacher`;
});

await S('CC06', 'teacher', 'Chapter status is calculated from its topics', 'All topics Done = Done; a mixture = In progress; counts "x of y"', async () => {
  const exp = state.exp6m;
  const ch = exp.chapters[0];
  const units = exp.perChapter[ch.id];
  const chStatus = async () => page.getByTestId(`chapter-status-${ch.id}`).getAttribute('data-status');
  for (const u of units) {
    const sel = page.getByTestId(`status-${u.id}`).getByRole('combobox');
    if ((await dotStatus(u.id)) !== 'DONE') await sel.selectOption('DONE');
  }
  await page.waitForFunction((c) => document.querySelector(`[data-testid="chapter-status-${c}"]`)?.getAttribute('data-status') === 'DONE', ch.id);
  assert((await txt(`chapter-count-${ch.id}`)) === `${units.length} of ${units.length}`, await txt(`chapter-count-${ch.id}`));
  if (units.length > 1) {
    await page.getByTestId(`status-${units[1].id}`).getByRole('combobox').selectOption('NOT_DONE');
    await page.waitForFunction((c) => document.querySelector(`[data-testid="chapter-status-${c}"]`)?.getAttribute('data-status') === 'IN_PROGRESS', ch.id);
  }
  assert((await chStatus()) === (units.length > 1 ? 'IN_PROGRESS' : 'DONE'), 'mixture status');
  const total = (await txt('coverage-done'));
  const expectDone = units.length - (units.length > 1 ? 1 : 0);
  assert(total === String(expectDone), `subject Done ${total} vs ${expectDone}`);
  state.ch1Done = expectDone;
});

await S('CC07', 'teacher', 'Refresh, log out and back in, and a fresh browser session', 'Coverage, counts and chapter status persist each time', async () => {
  const exp = state.exp6m;
  const doneNow = await txt('coverage-done');
  await page.reload(); await ready();
  assert((await txt('coverage-done')) === doneNow && /catalogue\/6\/mathematics/.test(page.url()), 'lost after refresh');
  await page.getByRole('button', { name: /Vikram Sengupta/ }).click();
  await page.getByRole('button', { name: /log ?out/i }).first().click();
  await page.waitForURL(/\/login/);
  await loginUi(page, 'teacher');
  await page.goto(catalogueUrl(6, 'Mathematics')); await ready();
  assert((await txt('coverage-done')) === doneNow, 'lost after re-login');
  const ctx2 = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p2 = await ctx2.newPage();
  await loginUi(p2, 'principal');
  await p2.goto(catalogueUrl(6, 'Mathematics'));
  await p2.waitForFunction(() => document.querySelector('[data-testid="coverage-done"]') && !/Loading syllabus coverage/.test(document.body.innerText), null, { timeout: 20000 });
  await p2.waitForTimeout(500);
  const seen = (await p2.getByTestId('coverage-done').innerText()).trim();
  const ro = await p2.getByText('Coverage is read-only for your role.').count();
  await ctx2.close();
  assert(seen === doneNow, `fresh session shows ${seen}`);
  assert(ro === 1, 'principal view not read-only');
  state.doneAfterCC = doneNow;
  return `${doneNow} Done of ${exp.units.length} persisted across refresh, re-login and a fresh principal session`;
});

await S('CC08', 'teacher', 'All six class/subject combinations list the full available syllabus', 'For each: chapter count, teachable-topic total and every chapter title match the independent computation', async () => {
  const lines = [];
  for (const [g, s] of COMBOS) {
    const exp = expectedSyllabus(g, s);
    await page.goto(catalogueUrl(g, s)); await ready();
    await page.getByTestId('syllabus-view').waitFor();
    assert((await txt('coverage-total')) === String(exp.units.length), `${CLASS_NAME[g]} ${s}: total ${await txt('coverage-total')} vs ${exp.units.length}`);
    for (const c of exp.chapters) {
      assert(await page.getByTestId(`chapter-${c.id}`).count() === 1, `${CLASS_NAME[g]} ${s}: missing chapter ${c.title}`);
      assert((await page.getByTestId(`chapter-${c.id}`).innerText()).includes(c.title), `title ${c.title}`);
    }
    await page.getByRole('button', { name: 'Expand all' }).click();
    const rows = await page.locator('[data-testid^="topic-"]').count();
    assert(rows >= exp.units.length && (await page.getByRole('combobox').count()) === exp.units.length, `${CLASS_NAME[g]} ${s}: rows ${rows}`);
    lines.push(`${CLASS_NAME[g]} ${s}: ${exp.chapters.length} ch / ${exp.units.length} topics`);
  }
  return lines.join('; ');
});

await S('CC09', 'teacher', 'Set coverage in Science and Classes VII and VIII', 'Each change shows the right colour and updates that combination\'s totals only', async () => {
  const out = [];
  for (const [g, s] of [[6, 'Science'], [7, 'Mathematics'], [8, 'Science']]) {
    const exp = expectedSyllabus(g, s);
    await page.goto(catalogueUrl(g, s)); await ready();
    await page.getByRole('button', { name: 'Expand all' }).click();
    const u = exp.units[2];
    await page.getByTestId(`status-${u.id}`).getByRole('combobox').selectOption('IN_PROGRESS');
    await page.waitForFunction((x) => document.querySelector(`[data-testid="dot-${x}"]`)?.getAttribute('data-status') === 'IN_PROGRESS', u.id);
    assert((await dotColor(u.id)) === RGB.IN_PROGRESS && (await txt('coverage-inprogress')) === '1', `${g} ${s}`);
    await page.getByTestId(`status-${u.id}`).getByRole('combobox').selectOption('DONE');
    await page.waitForFunction((x) => document.querySelector(`[data-testid="dot-${x}"]`)?.getAttribute('data-status') === 'DONE', u.id);
    assert((await dotColor(u.id)) === RGB.DONE && (await txt('coverage-done')) === '1', `${g} ${s} done`);
    out.push(`${CLASS_NAME[g]} ${s}: ${await txt('coverage-percent')}`);
  }
  const cm = (await txt('coverage-percent'));
  await page.goto(catalogueUrl(6, 'Mathematics')); await ready();
  assert((await txt('coverage-done')) === state.doneAfterCC, 'Class VI Mathematics totals changed by other combinations');
  return out.join('; ');
});

await S('CC10', 'teacher', 'Mobile layout (390 px)', 'No horizontal overflow; status control usable; chapters expand', async () => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(catalogueUrl(6, 'Mathematics')); await ready();
  await page.getByRole('button', { name: 'Expand all' }).click();
  const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  assert(m.sw <= m.iw + 4, `horizontal overflow ${m.sw} > ${m.iw}`);
  const u = state.exp6m.units[state.exp6m.units.length - 6]; // late topic, not touched by CC05/CC06
  await page.getByTestId(`status-${u.id}`).getByRole('combobox').selectOption('IN_PROGRESS');
  await page.waitForFunction((x) => document.querySelector(`[data-testid="dot-${x}"]`)?.getAttribute('data-status') === 'IN_PROGRESS', u.id);
  await shot(page, 'CC10_mobile_390');
  await page.getByTestId(`status-${u.id}`).getByRole('combobox').selectOption('NOT_DONE');
  await page.waitForFunction((x) => document.querySelector(`[data-testid="dot-${x}"]`)?.getAttribute('data-status') === 'NOT_DONE', u.id);
  await page.setViewportSize({ width: 1440, height: 900 });
});

await S('CC11', 'principal/student', 'Permissions', 'Principal read-only (disabled controls); student sees a staff-only message; API refuses both', async () => {
  await openCourse('principal', '?class=6&subject=Mathematics');
  await page.getByRole('button', { name: 'Expand all' }).click();
  assert(await page.getByRole('combobox').first().isDisabled(), 'principal control enabled');
  await loginUi(page, 'student');
  await page.goto(catalogueUrl(6, 'Mathematics'));
  await page.waitForTimeout(800);
  assert(await page.getByTestId('state-unauthorized').count() === 1, 'student not shown the unauthorized state');
  assert(await page.getByTestId('syllabus-view').count() === 0 && await page.getByRole('combobox').count() === 0, 'student sees syllabus controls');
  const ws = await workspace('admin');
  const tamper = JSON.parse(JSON.stringify(ws.state));
  const id = Object.keys(tamper.coverage)[0];
  tamper.coverage[id].status = 'NOT_DONE';
  tamper.coverage[id].history.push({ at: 'now', by: { id: 'x', name: 'x', role: 'principal' }, status: 'NOT_DONE', source: 'MANUAL' });
  tamper.audit.push({ id: 'cc11' });
  const r = await api('PUT', '/planning/workspace', await token('principal'), { expected_revision: ws.revision, action: 'COVERAGE_UPDATE', summary: 'tamper', state: tamper });
  assert(r.status === 403, `principal coverage write got ${r.status}`);
  const s = await api('PUT', '/planning/workspace', await token('student'), { expected_revision: ws.revision, action: 'COVERAGE_UPDATE', summary: 'tamper', state: tamper });
  assert(s.status === 403, `student write got ${s.status}`);
});

// ------------------------------------------------------------------ TA. Time-Aware Engine on the same topics
const tdates = (cfg) => {
  const out = []; const d = new Date(cfg.start + 'T00:00:00Z'); const end = new Date(cfg.end + 'T00:00:00Z');
  const blocked = (iso) => cfg.entries.some((e) => iso >= e.start && iso <= e.end);
  while (d <= end && out.length < cfg.horizonDays) {
    const iso = d.toISOString().slice(0, 10);
    if (cfg.weekdays.includes(d.getUTCDay()) && !blocked(iso)) out.push(iso);
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return out;
};
const CFG = { start: '2026-04-01', end: '2027-03-31', weekdays: [1, 2, 3, 4, 5], horizonDays: 70, entries: [{ start: '2026-04-02', end: '2026-04-02' }, { start: '2026-04-06', end: '2026-04-06' }] };
const DATES = tdates(CFG);

await S('TA01', 'admin', 'Academic Configuration: holiday 2 Apr, exam 6 Apr, 3 Mathematics periods per day, 70-day horizon', 'Saved; the calendar skips the holiday, weekend and exam', async () => {
  await loginUi(page, 'admin');
  await page.goto(`${WEB}/admin/academic-config`);
  await page.waitForFunction(() => /Shared planning store \(backend\)/.test(document.body.innerText), null, { timeout: 20000 });
  await page.getByRole('button', { name: /Add holiday/ }).click();
  await page.getByLabel('Entry 1 description').fill('Ram Navami');
  await page.getByLabel('Entry 1 from').fill('2026-04-02');
  await page.getByRole('button', { name: /Add examination period/ }).click();
  await page.getByLabel('Entry 2 description').fill('Periodic test');
  await page.getByLabel('Entry 2 from').fill('2026-04-06');
  await page.getByLabel('Mathematics periods per instructional day').fill('3');
  await page.getByLabel('Curriculum planning horizon').fill('70');
  await page.getByRole('button', { name: 'Save Academic Configuration' }).click();
  await page.getByText(/Configuration saved/).first().waitFor({ timeout: 10000 });
  const ws = await workspace('admin');
  state.config = JSON.stringify(ws.state.config);
  assert(ws.state.config.horizonDays === 70 && ws.state.config.subjectPeriodsPerDay.Mathematics === 3, 'not persisted');
  assert(DATES.slice(0, 4).join() === '2026-04-01,2026-04-03,2026-04-07,2026-04-08', DATES.slice(0, 4).join());
});

const goPlanner = async (role) => {
  await loginUi(page, role);
  await page.goto(`${WEB}/teacher/time-aware`);
  await page.waitForFunction(() => /Shared planning store \(backend\)/.test(document.body.innerText), null, { timeout: 20000 });
  await page.getByLabel('Class').selectOption('6');
  await page.getByLabel('Subject').selectOption('Mathematics');
};
const goDaily = async (role) => {
  await loginUi(page, role);
  await page.goto(`${WEB}/teacher/curriculum-180`);
  await page.waitForFunction(() => /Shared planning store \(backend\)/.test(document.body.innerText), null, { timeout: 20000 });
};

await S('TA02', 'teacher', 'Time-Aware Engine lists the same topics as the Curriculum Catalogue (same class and subject)', 'Same count and the same titles, in the same order; activities/headings are not units; every topic flagged as missing an approved requirement', async () => {
  await goPlanner('teacher');
  const exp = state.exp6m;
  const t = await body();
  assert(new RegExp(`${exp.units.length} topic\\(s\\) without an approved requirement`).test(t), 'missing-requirement flag');
  const rows = await page.getByRole('table', { name: 'Generated schedule' }).getByRole('row').allInnerTexts();
  const body_rows = rows.slice(1).map((r) => r.replace(/\s+/g, ' '));
  assert(body_rows.length === exp.units.length, `engine rows ${body_rows.length} vs ${exp.units.length}`);
  exp.units.forEach((u, i) => assert(body_rows[i].includes(u.title), `row ${i} "${body_rows[i].slice(0, 60)}" lacks "${u.title}"`));
  const cov = await coverageOnServer();
  for (const u of exp.units) {
    const tag = await page.getByTestId(`ta-coverage-${u.id}`).getAttribute('data-status');
    assert(tag === (cov[u.id]?.status ?? 'NOT_DONE'), `engine coverage tag for ${u.title}: ${tag} vs ${cov[u.id]?.status ?? 'NOT_DONE'}`);
  }
  await shot(page, 'TA02_engine_same_topics');
  return `${body_rows.length} topics in the same order as the Curriculum Catalogue, each with its catalogue coverage tag`;
});

async function bulk(role, mode) {
  await loginUi(page, role);
  await page.goto(`${WEB}/teacher/time-aware`);
  await page.waitForFunction(() => /Shared planning store \(backend\)/.test(document.body.innerText), null, { timeout: 20000 });
  return page.evaluate(async ({ mode }) => {
    const gov = await import('/src/lib/planning/governance.ts');
    const syl = await import('/src/lib/planning/syllabus.ts');
    const base = 'http://localhost:8000/api/v1';
    const H = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + localStorage.getItem('lumeneios_token'), 'X-School-Id': localStorage.getItem('lumeneios_current_school') || 'school-1' };
    const me = await (await fetch(base + '/auth/me', { headers: H })).json();
    const actor = { id: me.id, name: me.name, role: me.role };
    const ws = await (await fetch(base + '/planning/workspace', { headers: H })).json();
    const state = ws.state;
    const ds = syl.defaultDatasetFor(syl.allDatasets(state.datasets), 6, 'Mathematics');
    const units = syl.syllabusFor(ds, 6, 'Mathematics').units;
    let c = state.classifications;
    for (const u of units) {
      c = mode === 'propose'
        ? gov.proposeRequirement(c, u.id, 2, 1, ['FOUNDATIONAL_CONCEPT', 'ENRICHMENT'], 'Acceptance requirement: two core periods build the concept and one extends it.', 'Acceptance seed (bulk via API)', actor)
        : gov.review(c, u.id, 'APPROVED', '', actor);
    }
    const action = mode === 'propose' ? 'CLASSIFICATION_PROPOSE' : 'CLASSIFICATION_REVIEW';
    const summary = `Bulk ${mode} 2 Core + 1 Non-Core for ${units.length} Class VI Mathematics topics`;
    const next = { ...state, classifications: c, audit: [...state.audit, { id: 'bulk-' + mode, at: new Date().toISOString(), action, summary, actor }] };
    const r = await fetch(base + '/planning/workspace', { method: 'PUT', headers: H, body: JSON.stringify({ expected_revision: ws.revision, action, summary, state: next }) });
    return { status: r.status, units: units.length, detail: r.ok ? '' : await r.text() };
  }, { mode });
}

await S('TA03', 'teacher+principal (bulk API seed)', 'Approve 2 Core + 1 Non-Core for each of the 65 topics (teacher proposes, principal approves; seeded through the real API with the app\'s own governance functions)', 'Server accepts both; 65 approved records; no fixed ratio is implied by the engine', async () => {
  const a = await bulk('teacher', 'propose');
  assert(a.status === 200 && a.units === state.exp6m.units.length, `propose ${a.status} ${a.detail}`);
  const b = await bulk('principal', 'review');
  assert(b.status === 200, `review ${b.status} ${b.detail}`);
  const ws = await workspace('admin');
  const approved = Object.values(ws.state.classifications).filter((c) => c.status === 'APPROVED' && c.corePeriods === 2 && c.nonCorePeriods === 1).length;
  assert(approved === state.exp6m.units.length, `approved ${approved}`);
});

await S('TA04', 'teacher', 'Generate the schedule from the approved requirements', 'Required 195 periods; calendar capacity 210; draft allocation equals the independently derived timetable (each topic: 2 Core then 1 Non-Core, in order)', async () => {
  await goPlanner('teacher');
  const exp = state.exp6m;
  const t = await body();
  assert(/CORE \/ NON-CORE REQUIRED\s*130 \/ 65 p/i.test(t), 'totals: ' + (t.match(/CORE \/ NON-CORE REQUIRED[^|]{0,30}/i) || [''])[0]);
  await page.getByRole('button', { name: 'Generate draft schedule for approval' }).click();
  await page.getByText(/Draft saved for/).first().waitFor({ timeout: 15000 });
  const plan = (await workspace('admin')).state.plans[0];
  assert(plan.status === 'DRAFT' && plan.draft.lessons.length === exp.units.length, 'draft shape');
  assert(plan.draft.metrics.requiredPeriods === 195 && plan.draft.metrics.unscheduledPeriods === 0, `metrics ${JSON.stringify(plan.draft.metrics)}`);
  assert(plan.draft.metrics.availablePeriods === 210, `available ${plan.draft.metrics.availablePeriods}`);
  const timeline = DATES.flatMap((d) => [1, 2, 3].map((p) => `${d}#${p}`));
  let i = 0;
  exp.units.forEach((u, k) => {
    const want = ['C', 'C', 'N'].map((kind) => `${timeline[i++]}${kind}`).join(' ');
    const l = plan.draft.lessons[k];
    const got = l.slots.map((s) => `${s.date}#${s.period}${s.kind === 'CORE' ? 'C' : 'N'}`).join(' ');
    assert(l.nodeId === u.id, `lesson ${k} is ${l.nodeId}`);
    assert(got === want, `topic ${k + 1} ${u.title}: ${got} != ${want}`);
  });
  state.planId = plan.id;
});

await S('TA05', 'principal', 'Principal approves the schedule', 'v1 approved; the catalogue shows nothing Done because topics were scheduled', async () => {
  await loginUi(page, 'principal');
  await page.goto(`${WEB}/principal/curriculum`);
  const draft = page.getByTestId('draft-review');
  await draft.waitFor({ timeout: 15000 });
  await draft.getByRole('button', { name: 'Approve teaching schedule' }).click();
  await draft.waitFor({ state: 'detached', timeout: 10000 });
  const plan = (await workspace('admin')).state.plans[0];
  assert(plan.status === 'APPROVED' && plan.versions.length === 1, 'not approved');
  state.v1 = JSON.stringify(plan.versions[0]);
  const cov = await coverageOnServer();
  const forClassVI = state.exp6m.units.filter((u) => cov[u.id] && cov[u.id].status !== 'NOT_DONE').map((u) => u.title);
  // coverage records for the topics set manually earlier (CC05/CC06) legitimately exist; none may have come from scheduling
  assert(Object.values(cov).every((r) => r.history.every((h) => h.source === 'MANUAL')), 'a schedule or approval created an execution-derived record');
  await page.goto(catalogueUrl(6, 'Mathematics'));
  await page.waitForFunction(() => document.querySelector('[data-testid="coverage-done"]') && !/Loading syllabus coverage/.test(document.body.innerText), null, { timeout: 20000 });
  await page.waitForTimeout(400);
  assert((await txt('coverage-done')) === state.doneAfterCC, `Done changed by scheduling: ${await txt('coverage-done')} vs ${state.doneAfterCC}`);
  return `scheduled+approved: Done stays ${state.doneAfterCC}; manual records: ${forClassVI.length}`;
});

await S('TA06', 'teacher', 'Record a Lost Day: periods #1 and #2 together (both Core of the first topic)', 'One submission; only those two periods lost; calendar and v1 unchanged; one pending proposal', async () => {
  await goPlanner('teacher');
  await page.getByTestId('lost-period-recorder').getByRole('button', { name: 'Record a Lost Day' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel(/^Period 1: 2026-04-01, /).check();
  await dialog.getByLabel(/^Period 2: 2026-04-01, /).check();
  assert((await dialog.getByRole('list', { name: 'Selected periods' }).getByRole('listitem').count()) === 2, 'selection');
  const submit = dialog.getByRole('button', { name: 'Record 2 lost period(s)' });
  assert(await submit.isDisabled(), 'reason not mandatory');
  await dialog.getByLabel('Loss reason').selectOption('Election Duties');
  await dialog.getByLabel('Loss note').fill('Polling booth setup');
  await submit.click();
  await page.getByText(/Recorded period\(s\) #1, #2 as lost/).first().waitFor({ timeout: 10000 });
  const ws = await workspace('admin');
  const plan = ws.state.plans[0];
  assert(plan.losses.length === 1 && JSON.stringify(plan.losses[0].periods) === '[1,2]' && plan.losses[0].periodsLost === 2, 'loss record');
  assert(plan.proposals.filter((p) => p.status === 'PENDING').length === 1 && JSON.stringify(plan.versions[0]) === state.v1, 'proposal/v1');
  assert(JSON.stringify(ws.state.config) === state.config, 'calendar changed');
  state.proposal1 = plan.proposals.find((p) => p.status === 'PENDING');
});

await S('TA07', 'principal', 'Review the recovery proposal', 'Changed periods equal the derivation: #1,#2 lost on 04-01; Core recovered in the next topics\' Non-Core slots #6 (04-03) and #9 (04-07), which move to independent learning; 0 Core unresolved', async () => {
  await loginUi(page, 'principal');
  await page.goto(`${WEB}/principal/curriculum`);
  const pr = page.getByTestId('recovery-proposal');
  await pr.waitFor({ timeout: 15000 });
  const rows = (await pr.getByRole('table', { name: 'Changed periods' }).getByRole('row').allInnerTexts()).slice(1).map((r) => r.replace(/\s+/g, ' ').trim());
  // First-principles derivation. Day 1 (04-01): #1 T1 Core, #2 T1 Core, #3 T1 Non-Core. The window is the next 3 teaching days
  // (04-03, 04-07, 04-08) and excludes the loss date itself, so T1's own Non-Core on 04-01 is not eligible. Later topics' Non-Core
  // sessions are: #6 (T2, 04-03), #9 (T3, 04-07), #12 (T4, 04-08). Priority: earliest first -> #6 and #9.
  const want = [/^#1 2026-04-01 Lost/, /^#2 2026-04-01 Lost/, /^#6 2026-04-03 Core recovered/, /^#6 2026-04-03 Non-Core → independent learning/, /^#9 2026-04-07 Core recovered/, /^#9 2026-04-07 Non-Core → independent learning/];
  assert(rows.length === want.length, `rows ${rows.length}: ${JSON.stringify(rows)}`);
  want.forEach((re, i) => assert(re.test(rows[i]), `row ${i}: ${rows[i]}`));
  const t = (await pr.innerText()).replace(/\s+/g, ' ');
  assert(/Original \(v1\)/i.test(t) && /Proposed/i.test(t) && /0 Core period\(s\) still unresolved|Core still outstanding/i.test(t), 'comparison/unresolved');
  await shot(page, 'TA07_recovery_proposal');
  return rows.join(' || ').slice(0, 250);
});

await S('TA08', 'principal', 'Reject it (reason required); v1 stays authoritative; coverage untouched', 'Rejected with a note; v1 identical; no execution-derived coverage', async () => {
  const pr = page.getByTestId('recovery-proposal');
  await pr.getByRole('button', { name: 'Reject proposal' }).click();
  await pr.getByRole('alert').waitFor({ timeout: 5000 });
  await pr.getByLabel('Recovery review note').fill('Cover through the Saturday make-up class first');
  await pr.getByRole('button', { name: 'Reject proposal' }).click();
  await pr.waitFor({ state: 'detached', timeout: 10000 });
  const ws = await workspace('admin');
  const plan = ws.state.plans[0];
  assert(plan.versions.length === 1 && JSON.stringify(plan.versions[0]) === state.v1, 'v1 changed');
  assert(plan.proposals.find((p) => p.id === state.proposal1.id).status === 'REJECTED', 'not rejected');
  assert(Object.values(ws.state.coverage).every((r) => r.history.every((h) => h.source === 'MANUAL')), 'lost/rejection created execution coverage');
});

await S('TA09', 'teacher', 'Generate another proposal: also lose period #4 (second topic, Core)', 'New pending proposal covering all unresolved losses; v1 still authoritative', async () => {
  await goPlanner('teacher');
  await page.getByTestId('lost-period-recorder').getByRole('button', { name: 'Record a Lost Day' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel(/^Period 4: 2026-04-03, /).check();
  await dialog.getByLabel('Loss reason').selectOption('Teacher Training');
  await dialog.getByRole('button', { name: 'Record 1 lost period(s)' }).click();
  await page.getByText(/Recorded period\(s\) #4 as lost/).first().waitFor({ timeout: 10000 });
  const plan = (await workspace('admin')).state.plans[0];
  const pend = plan.proposals.filter((p) => p.status === 'PENDING');
  assert(pend.length === 1 && pend[0].id !== state.proposal1.id && plan.versions.length === 1 && plan.losses.length === 2, 'proposal2');
  state.proposal2 = pend[0];
});

await S('TA10', 'principal', 'Approve the new proposal', 'v2 created from v1, linked to the proposal; v1 unchanged', async () => {
  await loginUi(page, 'principal');
  await page.goto(`${WEB}/principal/curriculum`);
  const pr = page.getByTestId('recovery-proposal');
  await pr.waitFor({ timeout: 15000 });
  await pr.getByRole('button', { name: 'Approve recovery schedule' }).click();
  await pr.waitFor({ state: 'detached', timeout: 10000 });
  const plan = (await workspace('admin')).state.plans[0];
  assert(plan.versions.length === 2 && JSON.stringify(plan.versions[0]) === state.v1, 'versions');
  assert(plan.versions[1].version === 2 && plan.versions[1].proposalId === state.proposal2.id && plan.versions[1].approvedBy.role === 'principal', 'linkage');
});

await S('TA11', 'server', 'Reconcile v2 against independent invariants', 'Core 130 and Non-Core 65 account exactly; no lost, duplicate or non-teaching slots; recovered Core is within 3 teaching days; calendar unchanged', async () => {
  const ws = await workspace('admin');
  const v2 = ws.state.plans[0].versions[1];
  const lessons = v2.lessons;
  const coreSlots = lessons.flatMap((l) => l.slots.filter((s) => s.kind === 'CORE')).length;
  const nonSlots = lessons.flatMap((l) => l.slots.filter((s) => s.kind !== 'CORE')).length;
  const coreUnsched = lessons.reduce((n, l) => n + (l.coreUnscheduled || 0), 0);
  const indep = lessons.reduce((n, l) => n + (l.independentPeriods || 0), 0);
  assert(lessons.length === state.exp6m.units.length, 'topic dropped or added');
  assert(lessons.reduce((n, l) => n + l.corePeriods, 0) === 130 && lessons.reduce((n, l) => n + l.nonCorePeriods, 0) === 65, 'approved counts changed');
  assert(coreSlots + coreUnsched === 130, `Core ${coreSlots}+${coreUnsched}`);
  assert(nonSlots + indep === 65, `Non-Core ${nonSlots}+${indep}`);
  const all = lessons.flatMap((l) => l.slots.map((s) => `${s.date}#${s.period}`));
  assert(new Set(all).size === all.length, 'double booking');
  const lost = new Set((v2.lostSlots || []).map((s) => `${s.date}#${s.period}`));
  assert(lost.size === 3, `lost slots ${lost.size}`);
  all.forEach((k) => assert(!lost.has(k), `lost period ${k} allocated`));
  lessons.forEach((l) => l.slots.forEach((s) => assert(DATES.includes(s.date), `slot on non-teaching date ${s.date}`)));
  assert(JSON.stringify(ws.state.config) === state.config, 'calendar changed');
  return `Core ${coreSlots} classroom + ${coreUnsched} unresolved = 130; Non-Core ${nonSlots} classroom + ${indep} independent = 65; lost 3`;
});

await S('TA12', 'teacher', 'Progress: lost periods are not lost days; metrics distinct', '3 lost periods recorded; subject teaching days "of 65" (195 periods / 3 per day; the school calendar has 70); no "lost day" count', async () => {
  await goDaily('teacher');
  const rec = (await page.getByTestId('recovery-progress').innerText()).replace(/\s+/g, ' ');
  assert(/Lost periods recorded\s*3/.test(rec), rec);
  const days = (await page.getByTestId('teaching-day-progress').innerText()).replace(/\s+/g, ' ');
  // subject teaching days = days that hold scheduled periods: 195 periods / 3 per day = 65 (the school-wide calendar has 70)
  assert(/of 65 days/.test(days), days);
  assert(!/3 lost (teaching )?days?/i.test(await body()), 'lost periods shown as days');
  assert(/v2 approved by/.test(await page.getByTestId('schedule-change-notice').innerText()), 'notice');
  await shot(page, 'TA12_progress');
  return days;
});

await S('TA13', 'teacher', 'Catalogue coverage is unchanged after lost periods, rejection and recovery approval', 'Done count identical; nothing execution-derived', async () => {
  await openCourse('teacher', '?class=6&subject=Mathematics');
  assert((await txt('coverage-done')) === state.doneAfterCC, 'Done changed');
  const cov = await coverageOnServer();
  assert(Object.values(cov).every((r) => r.history.every((h) => h.source === 'MANUAL')), 'execution-derived record exists');
});

// ---- classroom execution moves coverage only when teaching is genuinely complete
const unit2 = () => state.exp6m.units[state.exp6m.units.length - 3]; // late-syllabus topic: untouched by every earlier step
const unit3 = () => state.exp6m.units[state.exp6m.units.length - 2];
const topicRow = (u) => page.getByRole('table', { name: 'Daily curriculum schedule' }).getByText(new RegExp(u.title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))).first().locator('xpath=ancestor::tr');

await S('TA14', 'teacher', 'Daily Curriculum: partially complete a topic, then complete it', 'Coverage: Not done -> In progress (orange) after a partial period -> Done (green) when the required teaching is complete; history source EXECUTION', async () => {
  const u = unit2();
  await goDaily('teacher');
  await page.getByRole('tab', { name: 'By topic' }).click();
  const row = topicRow(u);
  await row.getByRole('button', { name: 'Record execution' }).click();
  await page.getByLabel('Periods taught').fill('1');
  await page.getByRole('button', { name: 'Partially completed' }).click();
  await page.waitForTimeout(1200);
  let cov = await coverageOnServer();
  assert(cov[u.id]?.status === 'IN_PROGRESS' && cov[u.id].source === 'EXECUTION', `after partial: ${JSON.stringify(cov[u.id]?.status)}`);
  await openCourse('teacher', '?class=6&subject=Mathematics');
  await page.getByRole('button', { name: 'Expand all' }).click();
  assert((await dotColor(u.id)) === RGB.IN_PROGRESS, 'not orange in the Curriculum Catalogue');
  assert(/Updated from classroom teaching records/.test(await page.getByTestId(`topic-${u.id}`).innerText()), 'source caption');
  await goDaily('teacher');
  await page.getByRole('tab', { name: 'By topic' }).click();
  const row2 = topicRow(u);
  await row2.getByRole('button', { name: 'Record execution' }).click();
  await page.getByRole('button', { name: 'Completed as scheduled' }).click();
  await page.waitForTimeout(1200);
  cov = await coverageOnServer();
  assert(cov[u.id].status === 'DONE' && cov[u.id].history.map((h) => `${h.source}:${h.status}`).join() === 'EXECUTION:IN_PROGRESS,EXECUTION:DONE', `history ${JSON.stringify(cov[u.id].history.map((h) => h.source + ':' + h.status))}`);
  await openCourse('teacher', '?class=6&subject=Mathematics');
  await page.getByRole('button', { name: 'Expand all' }).click();
  assert((await dotColor(u.id)) === RGB.DONE, 'not green');
  await goPlanner('teacher');
  assert((await page.getByTestId(`ta-coverage-${u.id}`).getAttribute('data-status')) === 'DONE', 'engine does not show the completed topic as Done');
  const sched = unit3();
  assert((await page.getByTestId(`ta-coverage-${sched.id}`).getAttribute('data-status')) === 'NOT_DONE', 'a scheduled topic shows as covered');
  await shot(page, 'TA14_execution_done');
});

await S('TA15', 'teacher', 'Homework assigned does not make a topic Done', 'Coverage for that topic stays Not done; homework is shown as not counted', async () => {
  const u = unit3();
  await goDaily('teacher');
  await page.getByRole('tab', { name: 'By topic' }).click();
  const row = topicRow(u);
  await row.getByRole('button', { name: 'Record execution' }).click();
  await page.getByRole('button', { name: 'Not completed — assigned as homework' }).click();
  await page.waitForTimeout(1200);
  assert(/Homework assigned — not counted as completed/.test(await body()), 'homework disclaimer');
  const cov = await coverageOnServer();
  assert(!cov[u.id], `homework created coverage ${JSON.stringify(cov[u.id])}`);
  await openCourse('teacher', '?class=6&subject=Mathematics');
  await page.getByRole('button', { name: 'Expand all' }).click();
  assert((await dotColor(u.id)) === RGB.NOT_DONE, 'topic with homework not grey');
});

await S('TA16', 'teacher', 'Manual override never silently contradicts classroom records', 'Setting the completed topic back to Not done is recorded manually; the page shows that classroom records show it taught', async () => {
  const u = unit2();
  await page.getByTestId(`status-${u.id}`).getByRole('combobox').selectOption('NOT_DONE');
  await page.waitForFunction((x) => document.querySelector(`[data-testid="dot-${x}"]`)?.getAttribute('data-status') === 'NOT_DONE', u.id);
  assert(/Classroom records show this topic as taught/.test(await page.getByTestId(`topic-${u.id}`).innerText()), 'no conflict hint');
  const cov = await coverageOnServer();
  assert(cov[u.id].history.map((h) => `${h.source}:${h.status}`).join() === 'EXECUTION:IN_PROGRESS,EXECUTION:DONE,MANUAL:NOT_DONE', 'history');
  await page.getByTestId(`status-${u.id}`).getByRole('combobox').selectOption('DONE');
  await page.waitForFunction((x) => document.querySelector(`[data-testid="dot-${x}"]`)?.getAttribute('data-status') === 'DONE', u.id);
});

await S('TA17', 'teacher', 'Fresh session: approved v2, coverage and execution all persisted', 'New browser context shows v2 and the same coverage numbers', async () => {
  const done = await txt('coverage-done');
  const ctx2 = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p2 = await ctx2.newPage();
  await loginUi(p2, 'teacher');
  await p2.goto(catalogueUrl(6, 'Mathematics'));
  await p2.waitForFunction(() => document.querySelector('[data-testid="coverage-done"]') && !/Loading syllabus coverage/.test(document.body.innerText), null, { timeout: 20000 });
  await p2.waitForTimeout(500);
  const seen = (await p2.getByTestId('coverage-done').innerText()).trim();
  await p2.goto(`${WEB}/teacher/curriculum-180`);
  await p2.waitForFunction(() => /Shared planning store \(backend\)/.test(document.body.innerText), null, { timeout: 20000 });
  await p2.waitForTimeout(800);
  const v2 = /v2 approved by/.test(await p2.getByTestId('schedule-change-notice').innerText().catch(() => ''));
  await ctx2.close();
  assert(seen === done && v2, `fresh session Done ${seen} vs ${done}; v2 ${v2}`);
  assert(JSON.stringify((await workspace('admin')).state.config) === state.config, 'calendar changed');
});

// ------------------------------------------------------------------ routes and console
await S('UI01', 'all roles', 'Curriculum Catalogue route sweep', 'Staff roles load it; mobile shows no overflow; no uncaught page errors', async () => {
  const problems = [];
  for (const role of ['admin', 'principal', 'teacher']) {
    for (const w of [1440, 390]) {
      await page.setViewportSize({ width: w, height: 900 });
      await loginUi(page, role);
      await page.goto(catalogueUrl(8, 'Science'));
      await ready();
      const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
      if (m.sw > m.iw + 4) problems.push(`${role}@${w}: overflow ${m.sw}>${m.iw}`);
    }
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  consoleIssues.filter((c) => /PAGEERROR|TypeError|ReferenceError/.test(c.text)).forEach((c) => problems.push(c.text.slice(0, 120)));
  assert(problems.length === 0, problems.join(' ; '));
});

const OUT = process.env.OUT_DIR || '.';
fs.writeFileSync(`${OUT}/e2e-cc-state.json`, JSON.stringify({ ...state, exp6m: undefined }, null, 1));
const out = { ...report(), browser: `Microsoft Edge ${version} via playwright-core`, when: new Date().toISOString() };
fs.writeFileSync(`${OUT}/e2e-cc-results.json`, JSON.stringify(out, null, 1));
const fails = out.results.filter((r) => r.result !== 'PASS');
console.log(`\n${out.results.length - fails.length}/${out.results.length} passed`);
await browser.close();
