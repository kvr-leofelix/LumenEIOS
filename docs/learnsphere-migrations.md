# Safe LearnSphere migrations and local startup

The five new tables are managed by Alembic revision `0001_learnsphere`.
`backend/migrations/v1_schema.py` freezes the v1 definitions; later model changes must use
new revisions, not edit that frozen schema. The migration touches no existing application
table. LearnSphere tables are deliberately excluded from the application's legacy startup
`create_all` path. No seed data is added.

## Windows local setup

Run from the `arena-learnsphere` root. Existing dependencies include Alembic and httpx;
no new runtime package is required.

```powershell
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
npm.cmd install
```

Stop application writes before an upgrade. First validate only:

```powershell
.venv/Scripts/python.exe -B -m backend.scripts.migrate_learnsphere --database lumeneios.db
```

This opens the original SQLite database read-only, creates uniquely named backup and rehearsal
files in `migration_backups`, verifies integrity and hashes every existing table's records,
applies the migration to the rehearsal copy and checks existing records again. It does not
alter the original database. Both database and backup directory must stay in this project.
Keep backups private; they contain student information and are excluded from version control.

Apply after successful rehearsal:

```powershell
.venv/Scripts/python.exe -B -m backend.scripts.migrate_learnsphere --database lumeneios.db --apply
```

The apply command makes a fresh verified backup and rehearsal, obtains an exclusive SQLite
write lock, checks that the original still matches its backup, and executes the additive
migration inside an explicit transaction. A failure rolls back schema changes. Record hashes
are rechecked before commit. Re-running an already applied upgrade is harmless.

Do not replace the original with a rehearsal file. Do not run reset/roster scripts or reseed.
Direct Alembic online execution is blocked: the runner must supply a reviewed connection.
The downgrade refuses to remove any table containing learning history. For a normal rollback,
roll back application code and retain the additive tables. An empty schema can be reversed
through a reviewed Alembic connection; no automatic downgrade command is exposed to users.

Start the application in two terminals:

```powershell
.venv/Scripts/python.exe -B -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

```powershell
npm.cmd run dev
```

Open `http://localhost:3000/learnsphere` after signing in. Use existing account provisioning
to establish student links and existing class assignments to establish teacher access.
Missing relationships intentionally produce empty or unavailable views.

LearnSphere trusts persisted class assignments, not browser-only roster changes. If the
legacy teacher-assignment screen only updates local state, an authorized principal/admin
can use the existing authenticated `POST /api/v1/classes/{class_id}/assignments` endpoint in
`http://127.0.0.1:8000/api/v1/docs` with `teacher_id` and `teacher_name`. The backend validates
both school scope and the teacher's school membership, and uses the teacher's actual stored
name. No assignment is inferred automatically. Existing browser-only roster UI is not a
source of LearnSphere permissions.

For local Qwen, run Ollama with the configured model installed. Existing defaults are:

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
QWEN_QUESTION_STUDIO_MODEL_ID=qwen2.5vl:7b
```

## PostgreSQL

The schema uses portable SQLAlchemy types and constraints. Tests compile all five tables
for PostgreSQL, but this task does not connect to a PostgreSQL service. Have the deployment
owner take and verify a managed database backup and rehearse against a restored instance.
Generate reviewable SQL with an Alembic Config whose `sqlalchemy.url` is `postgresql://`
and call `command.upgrade(config, 'head', sql=True)`. Run that SQL through the deployment's
transactional migration process only after backup/rehearsal. The SQLite runner deliberately
does not pretend to verify a PostgreSQL backup. Set the backend's existing DATABASE_URL to
the deployed PostgreSQL async URL after deployment.

## Verification

Revision `0003_panchapadi` adds two nullable assessment evaluation metadata columns, without historical backfill. See [Panchapadi migration, preservation checks and rollback limits](panchapadi-assessments.md).

```powershell
.venv/Scripts/python.exe -B -m pytest backend/tests -q -p no:cacheprovider
npm.cmd run build
```

Backend fixtures create isolated temporary databases and check original database/upload
files remain unchanged. UI tests require a dedicated Chrome debugging instance on 9331 and
Vite on 5178; they create disposable browser contexts and intercept API requests with test
fixtures. They never send mutations to the real backend.

```powershell
$env:STUDIO_UI_ORIGIN='http://127.0.0.1:5178'
node tests/studio-ui.mjs
node tests/learnsphere-ui.mjs
```
