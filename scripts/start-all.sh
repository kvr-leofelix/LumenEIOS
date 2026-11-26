#!/usr/bin/env bash
# Starts the whole LumenEIOS stack inside WSL/Linux: FastAPI backend, Vite frontend and the local Qwen
# model (loaded on the GPU inside the backend), then opens the app in the browser.
#
# Launched by start-lumeneios.bat (double-click from Windows), start-lumeneios.sh (Linux), or directly:
#   bash scripts/start-all.sh
#
# Optional environment overrides:
#   WARM_MODEL=0     skip loading the Qwen model at startup (it then loads on the first OCR/AI request)
#   NO_BROWSER=1     do not open the browser
#   SKIP_INSTALL=1   never install/update Python or npm packages
#   BACKEND_PORT / FRONTEND_PORT   defaults 8000 / 3000 (the dev frontend proxies /api to 8000)
set -u

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR" || exit 1

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
LOG_DIR="${TMPDIR:-/tmp}/lumeneios-logs"
mkdir -p "$LOG_DIR"
PIDS=()

say()  { printf '\033[1;36m[lumeneios]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[lumeneios]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[lumeneios]\033[0m %s\n' "$*"; cleanup; exit 1; }

cleanup() {
  trap - EXIT INT TERM HUP
  if ((${#PIDS[@]})); then
    say "Stopping the servers this window started..."
    for pid in "${PIDS[@]}"; do pkill -TERM -P "$pid" 2>/dev/null; kill -TERM "$pid" 2>/dev/null; done
    wait 2>/dev/null
  fi
}
trap 'cleanup; exit 0' INT TERM HUP
trap cleanup EXIT

up() { curl -s -o /dev/null -m 3 "$1"; }

wait_for() { # url, pid, seconds
  local i
  for ((i = 0; i < $3; i++)); do
    up "$1" && return 0
    kill -0 "$2" 2>/dev/null || return 1
    sleep 1
  done
  return 1
}

port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

say "LumenEIOS - starting from $APP_DIR"
command -v curl >/dev/null 2>&1 || fail "curl is required (sudo apt install curl)."

# --- configuration ---------------------------------------------------------------------------
if [ ! -f .env ]; then
  [ -f .env.example ] || fail "No .env or .env.example in $APP_DIR."
  cp .env.example .env
  warn "Created .env from .env.example. Add GEMINI_API_KEY there to enable the Gemini fallback and AI marking."
fi
if ! grep -Eq '^GEMINI_API_KEY=.+' .env; then
  warn "GEMINI_API_KEY is empty in .env: Qwen still works; Gemini fallback, AI marking and AI question generation will be unavailable."
fi

# --- Python backend environment ----------------------------------------------------------------
PY=.venv/bin/python
if [ ! -x "$PY" ]; then
  [ "${SKIP_INSTALL:-0}" = "1" ] && fail "No Python environment at $APP_DIR/.venv."
  command -v python3 >/dev/null 2>&1 || fail "python3 was not found. Install Python 3.11+."
  say "Creating the Python environment (first run only)..."
  python3 -m venv .venv || fail "Could not create .venv (try: sudo apt install python3-venv)."
fi
req_stamp=".venv/.lumeneios-requirements.sha"
req_hash="$(cat backend/requirements.txt backend/requirements-ocr.txt 2>/dev/null | sha1sum | cut -d' ' -f1)"
if [ "${SKIP_INSTALL:-0}" != "1" ] && [ "$(cat "$req_stamp" 2>/dev/null)" != "$req_hash" ]; then
  say "Installing/updating Python packages (only when requirements change; can take several minutes)..."
  "$PY" -m pip install -q --upgrade pip >/dev/null 2>&1
  "$PY" -m pip install -q -r backend/requirements.txt || fail "pip install -r backend/requirements.txt failed."
  if [ -f backend/requirements-ocr.txt ]; then
    "$PY" -m pip install -q -r backend/requirements-ocr.txt || warn "OCR/Qwen packages failed to install; Qwen OCR will be unavailable."
  fi
  echo "$req_hash" >"$req_stamp"
fi

# --- Node frontend environment -----------------------------------------------------------------
# Node is often installed through nvm, which non-interactive shells do not load on their own.
if ! command -v npm >/dev/null 2>&1 && [ -s "$HOME/.nvm/nvm.sh" ]; then . "$HOME/.nvm/nvm.sh" >/dev/null 2>&1; fi
command -v npm >/dev/null 2>&1 || fail "npm was not found. Install Node.js 18+ (for example with nvm)."
if [ "${SKIP_INSTALL:-0}" != "1" ] && { [ ! -d node_modules/vite ] || [ package-lock.json -nt node_modules/.package-lock.json ]; }; then
  say "Installing/updating frontend packages (only when package-lock.json changes)..."
  npm install --no-audit --no-fund || fail "npm install failed."
fi

# --- GPU for Qwen ------------------------------------------------------------------------------
if command -v nvidia-smi >/dev/null 2>&1 && gpu="$(nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader 2>/dev/null | head -1)" && [ -n "$gpu" ]; then
  say "GPU: $gpu"
else
  warn "No NVIDIA GPU visible: Qwen will be unavailable. Choose 'Gemini (fallback)' in Scan Review."
fi

# --- leftover servers ------------------------------------------------------------------------
# Every backend process loads its own copy of Qwen. Two or three left running from earlier sessions
# fill an 8 GB GPU and make OCR stall or fail ("Failed to fetch" / CUDA errors), so call them out.
others="$(bash scripts/stop-all.sh --list 2>/dev/null | grep '^  backend' | awk -v p="$BACKEND_PORT" '$3 != p && $3 != "-"')"
if [ -n "$others" ]; then
  warn "Other LumenEIOS backends are already running and may be holding GPU memory:"
  printf '%s\n' "$others"
  warn "If OCR or the Question Studio stalls, double-click stop-lumeneios.bat, then start again."
fi

# --- backend ---------------------------------------------------------------------------------
if up "http://127.0.0.1:$BACKEND_PORT/health"; then
  say "Backend is already running on port $BACKEND_PORT - reusing it."
else
  port_busy "$BACKEND_PORT" && fail "Port $BACKEND_PORT is used by another program. Stop it or run with BACKEND_PORT=8001."
  say "Starting backend on port $BACKEND_PORT  (log: $LOG_DIR/backend.log)"
  "$PY" -m uvicorn backend.app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" >"$LOG_DIR/backend.log" 2>&1 &
  PIDS+=($!)
  wait_for "http://127.0.0.1:$BACKEND_PORT/health" "$!" 120 || { tail -n 30 "$LOG_DIR/backend.log"; fail "Backend did not start. See the log above."; }
fi

# --- frontend --------------------------------------------------------------------------------
if up "http://127.0.0.1:$FRONTEND_PORT/"; then
  say "Frontend is already running on port $FRONTEND_PORT - reusing it."
else
  port_busy "$FRONTEND_PORT" && fail "Port $FRONTEND_PORT is used by another program. Stop it or run with FRONTEND_PORT=3001."
  say "Starting frontend on port $FRONTEND_PORT  (log: $LOG_DIR/frontend.log)"
  LUMENEIOS_BACKEND_URL="http://127.0.0.1:$BACKEND_PORT" npx vite --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort >"$LOG_DIR/frontend.log" 2>&1 &
  PIDS+=($!)
  wait_for "http://127.0.0.1:$FRONTEND_PORT/" "$!" 120 || { tail -n 30 "$LOG_DIR/frontend.log"; fail "Frontend did not start. See the log above."; }
fi

say "Ready:"
say "  App        http://localhost:$FRONTEND_PORT"
say "  API docs   http://localhost:$BACKEND_PORT/api/v1/docs"
say "  Logs       $LOG_DIR"
say "  Sign in with the one-click demo personas on the login page."

# --- open the browser --------------------------------------------------------------------------
if [ "${NO_BROWSER:-0}" != "1" ]; then
  if command -v cmd.exe >/dev/null 2>&1; then (cd /mnt/c 2>/dev/null && cmd.exe /c start "" "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1)
  elif command -v wslview >/dev/null 2>&1; then wslview "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1; fi
fi

# --- load the local Qwen model so the first OCR / Question Studio / assistant request is fast --
if [ "${WARM_MODEL:-1}" = "1" ]; then
  (
    img="$LOG_DIR/warmup.png"
    "$PY" -c "from PIL import Image, ImageDraw; im = Image.new('RGB', (360, 90), 'white'); ImageDraw.Draw(im).text((12, 34), 'LumenEIOS model warm-up', fill='black'); im.save('$img')" 2>/dev/null
    say "Loading the Qwen model on the GPU in the background (about 30-90 seconds on first use)..."
    code=$(curl -s -o "$LOG_DIR/warmup.json" -w '%{http_code}' -m 900 -X POST "http://127.0.0.1:$BACKEND_PORT/api/v1/ocr/extract-preview" \
      --form-string wait_before_each_image=false --form-string provider=qwen -F "files=@$img")
    case "$code" in
      200) say "Qwen model is loaded and ready." ;;
      401|403) say "Qwen will load on the first OCR request (warm-up needs a login when DEMO_MODE is off)." ;;
      *) warn "Qwen model was not preloaded (HTTP $code): $(head -c 300 "$LOG_DIR/warmup.json" 2>/dev/null)"
         warn "The app still works; choose 'Gemini (fallback)' in Scan Review if Qwen stays unavailable." ;;
    esac
  ) &
fi

if ((${#PIDS[@]})); then
  say "Keep this window open. To shut everything down (frees the GPU): press Ctrl+C here or close this"
  say "window. If anything is left running, double-click stop-lumeneios.bat."
  wait "${PIDS[@]}"
else
  say "Everything was already running. You can close this window."
fi
