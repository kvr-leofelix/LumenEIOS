import { defineConfig } from '@playwright/test';
import { existsSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomBytes } from 'node:crypto';
const isolated = process.env.LUMENEIOS_E2E_DIR || mkdtempSync(join(tmpdir(), 'lumen-browser-'));
process.env.LUMENEIOS_E2E_DIR = isolated;
// The project's virtual environment when present (Linux/WSL .venv, Windows venv), otherwise python on PATH.
const venvPython = ['.venv/bin/python', 'venv/bin/python', 'venv/Scripts/python.exe', '.venv/Scripts/python.exe'].find((p) => existsSync(p));
const python = process.env.LUMENEIOS_TEST_PYTHON || venvPython || 'python';
const API_URL = 'http://127.0.0.1:18080/api/v1';
export default defineConfig({
  // Every spec except the optional demo walkthrough (LUMENEIOS_DEMO_E2E=true runs only that one).
  testDir:'./tests/e2e', testMatch:process.env.LUMENEIOS_DEMO_E2E==='true'?'demo.spec.ts':/(?<!demo)\.spec\.ts$/, workers:1, timeout:120000, reporter:'list',
  use:{baseURL:'http://127.0.0.1:14173',headless:true,channel:process.env.PLAYWRIGHT_CHANNEL || 'msedge'},
  webServer:[
    {command:`"${python}" -B -m backend.tests.browser_server`,
     url:'http://127.0.0.1:18080/health',reuseExistingServer:false,timeout:120000,
     env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',APP_ENV:'test',DEMO_MODE:'false',DEBUG:'false',
       SECRET_KEY:randomBytes(32).toString('hex'),DATABASE_URL:`sqlite+aiosqlite:///${join(isolated,'test.db').replaceAll('\\','/')}`,
       STORAGE_LOCAL_DIR:join(isolated,'uploads'),BACKEND_CORS_ORIGINS:'["http://127.0.0.1:14173"]'}},
    // Builds against the isolated test API first, so a stale build can never point the tests at a real backend.
    {command:'npx vite build --outDir dist-e2e && npx vite preview --outDir dist-e2e --host 127.0.0.1 --port 14173 --strictPort',
     url:'http://127.0.0.1:14173',reuseExistingServer:false,timeout:240000,env:{...process.env,VITE_API_URL:API_URL}}
  ]
});
