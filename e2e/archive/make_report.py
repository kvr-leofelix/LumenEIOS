"""Builds docs/FINAL_ACCEPTANCE_REPORT.md from a real acceptance run (e2e-results.json) plus recorded facts.

Nothing in the browser table is typed by hand: every row is copied from the run's results file.
Usage: python e2e/make_report.py <results.json> <facts.json> <out.md>
"""
import json
import sys

results = json.load(open(sys.argv[1], encoding='utf-8'))
facts = json.load(open(sys.argv[2], encoding='utf-8'))
out = sys.argv[3]

rows = results['results']
passed = sum(1 for r in rows if r['result'] == 'PASS')


def cell(s):
    return str(s).replace('|', '\\|').replace('\n', ' ')[:260]


L = []
w = L.append
w('# LumenEIOS — Final acceptance report')
w('')
w(f"Generated from a real browser run: **{results['browser']}**, started {results['when']} (UTC). Verification date: {facts['date']}.")
w(f"Repository `{facts['repo']}` · branch `{facts['branch']}` · no commits were made by this work.")
w('')
w('## 1. Result summary')
w('')
w('| Check | Result | Detail |')
w('|---|---|---|')
for name, res, det in facts['summary']:
    w(f'| {name} | {res} | {cell(det)} |')
w('')
NON_BROWSER = {'A01', 'A07', 'F06', 'G05', 'K03'}
def is_api_only(r):
    return '(API)' in r['role'] or r['id'] in NON_BROWSER
api_rows = [r for r in rows if is_api_only(r)]
br_rows = [r for r in rows if not is_api_only(r)]
br_pass = sum(1 for r in br_rows if r['result'] == 'PASS')
w(f'Overall: **{passed}/{len(rows)} steps passed**. Of these, **{br_pass}/{len(br_rows)} steps interacted with the live UI in a real browser** (frontend :3000, backend :8000, isolated database); the other {len(api_rows)} are API/state checks against the running backend ({", ".join(r["id"] for r in api_rows)}) and are not browser interaction. Several browser steps also verify server state over the API.')
w('')
w('## 2. Real-browser acceptance steps')
w('')
w('| Test ID | Role | Workflow | Expected behaviour | Actual behaviour | Result |')
w('|---|---|---|---|---|---|')
for r in rows:
    w(f"| {r['id']} | {cell(r['role'])} | {cell(r['workflow'])} | {cell(r['expected'])} | {cell(r['actual'])} | {r['result']} |")
w('')
w('Run history (each from a freshly created isolated database): a first partial run (24 steps) found 4 failures; full runs then scored 30/65, 62/65, 64/65, 65/65, 65/65 and 65/65; after the later Course Curriculum work the suite was re-run on the final code: one run scored 64/65 (a 30-second page.goto timeout in I01, not an assertion failure) and the immediately following full run scored 65/65. Most early failures were errors in the acceptance script itself (wrong selectors, a `<select>` filled as text, CSS-uppercased headings, an unimported variable), not product defects. The product defects the browser found are D6, D7, D8 and D9 in section 5. This table is the final run.')
w('')
w('### Console / network issues recorded by the final run')
w('')
for line in facts['console']:
    w(f'- {line}')
w('')
for title, key in (('3. Not verified in a real browser', 'not_browser'), ('4. Known limitations and remaining external dependencies', 'limits')):
    w(f'## {title}')
    w('')
    for line in facts[key]:
        w(f'- {line}')
    w('')
w('## 5. Defects found and fixed in this work')
w('')
w('| Ref | Defect | Found by | Fix | Regression test |')
w('|---|---|---|---|---|')
for d in facts['defects']:
    w('| ' + ' | '.join(cell(x) for x in d) + ' |')
w('')
w('## 6. Database integrity')
w('')
for line in facts['database']:
    w(f'- {line}')
w('')
w('## 7. NCERT review batch')
w('')
for line in facts['ncert']:
    w(f'- {line}')
w('')
w('## 8. Files')
w('')
w('**Modified this session:** ' + ', '.join(f'`{f}`' for f in facts['modified']))
w('')
w('**Added this session:** ' + ', '.join(f'`{f}`' for f in facts['added']))
w('')
w('Pre-existing uncommitted work (Time-Aware Engine, planning workspace, catalogue, migrations 001–003, earlier tests) was preserved untouched. Secondary worktrees were not modified.')
w('')
w('## 9. Launch instructions')
w('')
w('```powershell')
w('cd C:\\Users\\Tanav\\Downloads\\DP\\CODE\\arena\\apps\\lumeneios')
w('# Isolated database (never the original lumeneios.db): copy, stage NCERT draft structure, start backend on :8000')
w('$env:ACCEPT_DIR="C:/path/outside/repo/acceptance"; bash e2e/reset_env.sh')
w('# Frontend')
w('npx vite --port 3000        # http://localhost:3000')
w('# Real-browser acceptance (uses installed Microsoft Edge via playwright-core)')
w('$env:ACCEPT_DIR="C:/path/outside/repo/acceptance"; $env:SHOTS="$env:ACCEPT_DIR/screenshots"; $env:OUT_DIR=$env:ACCEPT_DIR; npm run e2e')
w('```')
w('')
w('Backend started manually must set `DATABASE_URL` explicitly, e.g. `$env:DATABASE_URL="sqlite+aiosqlite:///C:/path/acceptance/lumeneios_e2e.db"; venv\\Scripts\\python.exe -m uvicorn backend.app.main:app --port 8000`. Without it the backend reads `.env`/the default and uses the ORIGINAL `lumeneios.db`.')
w('Demo logins: `admin@`, `principal@`, `teacher@`, `student@`, `parent@lumeneios.demo`, password `demo123`. Sign-in is now required (no implicit admin session); set `VITE_DEMO_AUTO_LOGIN=true` only for an explicit stakeholder demo.')
open(out, 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')
print('wrote', out, f'{passed}/{len(rows)}')
