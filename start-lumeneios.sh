#!/usr/bin/env bash
# Linux / WSL launcher: double-click (if your file manager runs scripts) or run ./start-lumeneios.sh
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/start-all.sh" "$@"
