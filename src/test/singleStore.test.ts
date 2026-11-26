/**
 * Step 7: the relational teacher-plan records are the only store for planning data. This test reads the application source and
 * fails if a screen starts reading or writing the legacy workspace document (or the browser) for a migrated responsibility.
 */
import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

const SRC = join(__dirname, '..');
const files: { rel: string; text: string }[] = [];
(function walk(dir: string) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      if (['test', '__tests__', 'node_modules'].includes(name)) continue;
      walk(full);
    } else if (/\.(ts|tsx)$/.test(name) && !/\.test\./.test(name)) {
      files.push({ rel: relative(SRC, full).split(sep).join('/'), text: readFileSync(full, 'utf-8') });
    }
  }
})(SRC);

const using = (pattern: RegExp) => files.filter((f) => pattern.test(f.text)).map((f) => f.rel).sort();

describe('single store: planning data is read and written only through the relational API', () => {
  it('only the planning hook and the workspace store itself touch the workspace store (useData().planning)', () => {
    // DataContext exposes the store; usePlanning is the one consumer that turns it into the relational view.
    expect(using(/\bplanning\b\s*[,}]?[^\n]*=\s*useData\(\)|=\s*useData\(\)[^\n]*\bplanning\b|\{[^}]*\bplanning\b[^}]*\}\s*=\s*useData\(\)/)).toEqual(['lib/planning/usePlanning.ts']);
  });

  it('the browser-stored workspace key is referenced only by the workspace store', () => {
    expect(using(/lumeneios_planning_workspace_v2|\bLOCAL_KEY\b/)).toEqual(['lib/planning/store.ts']);
    expect(using(/lumeneios_academicWorkflow/).filter((f) => f !== 'pages/time-aware/planningUi.tsx')).toEqual(['lib/planning/store.ts']);
  });

  it('only the workspace store calls the workspace endpoint', () => {
    expect(using(/planning\/workspace/)).toEqual(['lib/planning/store.ts']);
  });

  it('every planning HTTP call goes through teacherPlanApi (one client, one contract)', () => {
    const callers = using(/['"`]\/(teacher-plans|plans|plan-calendar|plan-oversight|plan-logs)\b/);
    expect(callers).toEqual(['lib/teacherPlanApi.ts']);
  });

  it('no screen writes a migrated workspace field: the only workspace-level commits left are datasets and the planning date', () => {
    // A commit label that names a migrated responsibility may only appear where it is a plan/calendar command label, never as a
    // workspace write: usePlanning refuses such labels at the workspace branch (see its tests), and the server answers 410.
    const workspaceWrites = using(/planning\.commit\(/);
    expect(workspaceWrites).toEqual(['lib/planning/usePlanning.ts']);
    const retired = /\.commit\(\s*'(CONFIG_SAVE|COVERAGE_UPDATE|CLASSIFICATION_PROPOSE|CLASSIFICATION_REVIEW|RELATIONSHIP_PROPOSE|RELATIONSHIP_REVIEW)'/;
    expect(using(retired)).toEqual([]);
  });

  it('migrated workspace fields are never read from the stored document outside the workspace store and the legacy-view pass-through', () => {
    const stored = /\bplanning\.workspace\.(coverage|classifications|relationships|plans|config|configHistory|audit)\b|\bws\.(coverage|classifications|relationships|plans)\b/;
    expect(using(stored)).toEqual([]);
  });

  it('requirements, relationships, coverage and lost periods reach the engine only through the shared relational stores', () => {
    expect(using(/ctx:\s*EngineContext\s*=/)).toEqual(['lib/planning/usePlanning.ts']);
    expect(using(/useTeacherClassifications\(|useTeacherRelationships\(|useTeacherLostRows\(/)).toEqual(['features/teacherPlan/requirementsStore.ts', 'lib/planning/usePlanning.ts']);
    expect(using(/useTeacherCoverage\(/).sort()).toEqual([
      'features/curriculum/components/CoverageSyllabus.tsx',
      'features/teacherPlan/useTeacherCoverage.ts',
      'pages/time-aware/planningUi.tsx',
    ]);
  });

  it('there is exactly one audit surface for planning events: the plan log API (no screen renders the workspace audit list)', () => {
    expect(using(/workspace\.audit|\.audit\.map\(|\baudit\.length\b/)).toEqual([]);
  });
});
