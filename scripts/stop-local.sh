#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_DIR="${WORKBUDDY_AIP_RUNTIME_DIR:-${TMPDIR:-/tmp}/workbuddy-aip-macos-${USER}}"
PID_FILE="$RUNTIME_DIR/app.pid"
COMMAND_FILE="$RUNTIME_DIR/app.command"

if [[ ! -f "$PID_FILE" ]]; then
  printf '%s\n' "WorkBuddy AIP is not running."
  exit 0
fi
pid="$(<"$PID_FILE")"
if ! [[ "$pid" =~ ^[0-9]+$ ]]; then
  rm -f "$PID_FILE" "$COMMAND_FILE"
  printf '%s\n' "Removed invalid PID file."
  exit 0
fi

if kill -0 "$pid" 2>/dev/null && [[ -f "$COMMAND_FILE" ]] && [[ "$(<"$COMMAND_FILE")" == "$ROOT_DIR/workbuddy_aip.pyw" ]]; then
  kill "$pid"
  for _ in 1 2 3 4 5; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL "$pid"
  fi
  printf 'Stopped WorkBuddy AIP: PID %s\n' "$pid"
else
  printf 'PID %s is not this worktree application; no process was stopped.\n' "$pid"
fi
rm -f "$PID_FILE" "$COMMAND_FILE"
