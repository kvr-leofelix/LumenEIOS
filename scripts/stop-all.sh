#!/usr/bin/env bash
# Stops every LumenEIOS server on this machine: FastAPI backends (which also unloads the Qwen model
# and frees GPU memory) and Vite frontends, including ones left behind by earlier runs.
# Launched by stop-lumeneios.bat (double-click from Windows), stop-lumeneios.sh, or directly.
#   bash scripts/stop-all.sh --list   only shows what is running
set -u

say() { printf '\033[1;36m[lumeneios]\033[0m %s\n' "$*"; }

list() { # pattern -> "pid port cwd" lines for matching processes
  local pid
  for pid in $(pgrep -f "$1" 2>/dev/null); do
    # Never match this script, the shell that launched it, or any command line that merely mentions it.
    [ "$pid" = "$$" ] || [ "$pid" = "$PPID" ] && continue
    local cmd
    cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)"
    case "$cmd" in *stop-all.sh*|*stop-lumeneios*|*pgrep*) continue ;; esac
    local cwd port
    cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null || echo '?')"
    port="$(ss -ltnp 2>/dev/null | awk -v p="pid=$pid," '$0 ~ p {split($4, a, ":"); print a[length(a)]; exit}')"
    echo "$pid ${port:--} $cwd"
  done
}

backends="$(list 'uvicorn backend.app.main:app')"
# Vite can be started directly, through npm/npx, or from a wrapper script, so match any process with
# "vite" in its command line whose working directory is a LumenEIOS checkout.
frontends="$(for line in $(list 'vite' | awk '$3 ~ /apps\/lumeneios/ {print $1}'); do
  # Only real Node/npm processes are frontends (not shells whose text happens to contain "vite").
  case "$(basename "$(tr '\0' '\n' < "/proc/$line/cmdline" 2>/dev/null | head -1)")" in
    node|npm|npx) list 'vite' | awk -v p="$line" '$1 == p' ;;
  esac
done)"

if [ -z "$backends$frontends" ]; then
  say "Nothing to stop: no LumenEIOS servers are running."
  exit 0
fi

if [ "${1:-}" = "--list" ]; then
  say "Running LumenEIOS servers (pid, port, folder):"
  [ -n "$backends" ] && sed 's/^/  backend   /' <<<"$backends"
  [ -n "$frontends" ] && sed 's/^/  frontend  /' <<<"$frontends"
  exit 0
fi

stop() { # label, lines
  [ -z "$2" ] && return
  while read -r pid port cwd; do
    say "Stopping $1 (pid $pid, port $port) from $cwd"
    pkill -TERM -P "$pid" 2>/dev/null
    kill -TERM "$pid" 2>/dev/null
  done <<<"$2"
}
stop "frontend" "$frontends"
stop "backend" "$backends"

# Give them a moment to exit cleanly, then force anything still running.
sleep 4
for pid in $(printf '%s\n%s\n' "$backends" "$frontends" | awk 'NF {print $1}'); do
  kill -0 "$pid" 2>/dev/null && { kill -KILL "$pid" 2>/dev/null; say "Forced pid $pid to stop."; }
done

if command -v nvidia-smi >/dev/null 2>&1; then
  say "GPU memory now in use: $(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader 2>/dev/null | head -1)"
fi
say "LumenEIOS is stopped."
