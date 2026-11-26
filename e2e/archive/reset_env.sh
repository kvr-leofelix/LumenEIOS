#!/usr/bin/env bash
# Rebuilds the isolated acceptance environment. NEVER touches the original database:
#   original lumeneios.db  --copy-->  $ACCEPT_DIR/lumeneios_e2e.db  --stage NCERT draft structure-->  backend on :8000
# Usage: ACCEPT_DIR=/abs/path/to/acceptance bash e2e/reset_env.sh
set -euo pipefail
cd "$(dirname "$0")/.."
: "${ACCEPT_DIR:?set ACCEPT_DIR to an absolute directory outside the repository}"
mkdir -p "$ACCEPT_DIR"
ORIG="lumeneios.db"
before=$(sha256sum "$ORIG" | cut -c1-64)
powershell -NoProfile -Command "\$p=(Get-NetTCPConnection -LocalPort 8000 -State Listen -EA SilentlyContinue).OwningProcess|Select -Unique; if(\$p){Stop-Process -Id \$p -Force}" || true
sleep 2
rm -f "$ACCEPT_DIR/lumeneios_e2e.db"
cp "$ORIG" "$ACCEPT_DIR/lumeneios_e2e.db"
venv/Scripts/python.exe -I scripts/import_ncert_review.py --zip ../../LumenEIOS_NCERT_Review_Batch_01.zip --apply --database "$ACCEPT_DIR/lumeneios_e2e.db" > "$ACCEPT_DIR/stage_report.json"
export DATABASE_URL="sqlite+aiosqlite:///$ACCEPT_DIR/lumeneios_e2e.db"
nohup venv/Scripts/python.exe -m uvicorn backend.app.main:app --port 8000 > "$ACCEPT_DIR/backend_e2e.log" 2>&1 &
for i in $(seq 1 30); do curl -s -o /dev/null http://localhost:8000/api/v1/planning/workspace && break; sleep 1; done
[ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/v1/planning/workspace)" = "401" ] || { echo "backend not healthy"; exit 1; }
after=$(sha256sum "$ORIG" | cut -c1-64)
[ "$before" = "$after" ] && echo "backend on isolated DB: $ACCEPT_DIR/lumeneios_e2e.db ; original unchanged ($after)" || { echo "ORIGINAL DB CHANGED"; exit 2; }
