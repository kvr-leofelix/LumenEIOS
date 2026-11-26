"""Builds Part A of docs/FINAL_ACCEPTANCE_REPORT.md (Curriculum Catalogue + Time-Aware Engine) from a real run.

Usage: python e2e/make_cc_section.py <e2e-cc-results.json> <facts_cc.json>   (prints markdown to stdout)
Every table row is copied from the run's results file; nothing is typed by hand.
"""
import json
import sys

res = json.load(open(sys.argv[1], encoding='utf-8'))
facts = json.load(open(sys.argv[2], encoding='utf-8'))
rows = res['results']
API_ONLY = {'TA03', 'TA11'}


def cell(s):
    return str(s).replace('|', '\\|').replace('\n', ' ')[:300]


out = []
w = out.append
passed = sum(1 for r in rows if r['result'] == 'PASS')
ui = [r for r in rows if r['id'] not in API_ONLY]
w(f"Generated from a real browser run: **{res['browser']}**, started {res['when']} (UTC).")
w('')
w('### A1. Result summary')
w('')
w('| Check | Result | Detail |')
w('|---|---|---|')
for n, r, d in facts['summary']:
    w(f'| {cell(n)} | {r} | {cell(d)} |')
w('')
for title, key in (('A2. Implemented', 'implemented'), ('A3. Browser verified (this assignment)', 'browser'), ('A4. Not verified', 'not_browser'), ('A5. Blocked by missing data or external dependencies', 'blocked')):
    w(f'### {title}')
    w('')
    for line in facts[key]:
        w(f'- {line}')
    w('')
w('### A6. Browser steps')
w('')
w(f'{passed}/{len(rows)} passed; {sum(1 for r in ui if r["result"] == "PASS")}/{len(ui)} UI-interaction steps; API/state-check steps: {", ".join(sorted(API_ONLY))}.')
w('')
w('| Test ID | Role | Workflow | Expected behaviour | Actual behaviour | Result |')
w('|---|---|---|---|---|---|')
for r in rows:
    w(f"| {r['id']} | {cell(r['role'])} | {cell(r['workflow'])} | {cell(r['expected'])} | {cell(r['actual'])} | {r['result']} |")
w('')
w(f"Console errors recorded by this run: {len(res['consoleIssues'])}; failed API requests: {len(res['networkIssues'])}.")
w('')
w('### A7. Defects and changes in this assignment')
w('')
w('| Ref | Issue | Found by | Fix | Test |')
w('|---|---|---|---|---|')
for d in facts['defects']:
    w('| ' + ' | '.join(cell(x) for x in d) + ' |')
w('')
w('### A8. Database')
w('')
for line in facts['database']:
    w(f'- {line}')
w('')
w('### A9. Files')
w('')
w('**Modified:** ' + '; '.join(f'`{f}`' for f in facts['modified']))
w('')
w('**Added:** ' + ', '.join(f'`{f}`' for f in facts['added']))
w('')
w('### A10. Launch')
w('')
w('```powershell')
w('cd C:\\Users\\Tanav\\Downloads\\DP\\CODE\\arena\\apps\\lumeneios')
w('$env:ACCEPT_DIR="C:/path/outside/repo/acceptance"')
w('bash e2e/reset_env.sh                      # isolated copy of lumeneios.db, NCERT draft staged, backend on :8000')
w('npx vite --port 3000                       # frontend: http://localhost:3000  (Curriculum Catalogue: /curriculum/catalogue)')
w('venv\\Scripts\\python.exe -I scripts/build_planning_import.py --zip ..\\..\\LumenEIOS_NCERT_Review_Batch_01.zip --out "$env:ACCEPT_DIR/ncert_structure_import.json"')
w('# Admin: Time-Aware Engine > Syllabus & classification > paste that JSON > Validate and import')
w('$env:NCERT_IMPORT="$env:ACCEPT_DIR/ncert_structure_import.json"; $env:SHOTS="$env:ACCEPT_DIR/screenshots"; $env:OUT_DIR=$env:ACCEPT_DIR; npm run e2e:course')
w('```')
print('\n'.join(out))
