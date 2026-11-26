#!/usr/bin/env bash
# Stops all LumenEIOS servers (backend + Qwen model, frontend). Add --list to only show them.
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/stop-all.sh" "$@"
