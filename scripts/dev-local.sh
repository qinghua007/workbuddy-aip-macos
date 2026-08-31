#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${WORKBUDDY_AIP_VENV:-$HOME/.workbuddy/binaries/python/envs/workbuddy-aip-macos}"
PYTHON_BIN="${PYTHON_BIN:-$VENV_DIR/bin/python}"
RUNTIME_DIR="${WORKBUDDY_AIP_RUNTIME_DIR:-${TMPDIR:-/tmp}/workbuddy-aip-macos-${USER}}"
PID_FILE="$RUNTIME_DIR/app.pid"
COMMAND_FILE="$RUNTIME_DIR/app.command"
LOG_FILE="$RUNTIME_DIR/app.log"

if [[ ! -x "$PYTHON_BIN" ]]; then
  printf '%s\n' "Python environment is missing. Run scripts/setup-macos.sh first." >&2
  exit 1
fi

# The managed Python build keeps Tcl/Tk resources beside its base prefix.
read -r TCL_LIBRARY TK_LIBRARY < <("$PYTHON_BIN" -c 'import os, sys; base=sys.base_prefix; print(os.path.join(base, "lib", "tcl9.0"), os.path.join(base, "lib", "tk9.0"))')
export TCL_LIBRARY TK_LIBRARY

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(<"$PID_FILE")"
  if kill -0 "$old_pid" 2>/dev/null && [[ -f "$COMMAND_FILE" ]] && [[ "$(<"$COMMAND_FILE")" == "$ROOT_DIR/workbuddy_aip.pyw" ]]; then
    printf 'Already running: PID %s\nLog: %s\n' "$old_pid" "$LOG_FILE"
    exit 0
  fi
  rm -f "$PID_FILE" "$COMMAND_FILE"
fi

mkdir -p "$RUNTIME_DIR"
: > "$LOG_FILE"
nohup "$PYTHON_BIN" "$ROOT_DIR/workbuddy_aip.pyw" >> "$LOG_FILE" 2>&1 &
pid=$!
printf '%s\n' "$pid" > "$PID_FILE"
printf '%s\n' "$ROOT_DIR/workbuddy_aip.pyw" > "$COMMAND_FILE"

for _ in 1 2 3 4 5; do
  if ! kill -0 "$pid" 2>/dev/null; then
    printf 'Application exited during startup. Log: %s\n' "$LOG_FILE" >&2
    rm -f "$PID_FILE" "$COMMAND_FILE"
    exit 1
  fi
  sleep 1
done

if [[ ! -f "$COMMAND_FILE" ]] || [[ "$(<"$COMMAND_FILE")" != "$ROOT_DIR/workbuddy_aip.pyw" ]]; then
  printf 'Health check failed: missing command identity. Log: %s\n' "$LOG_FILE" >&2
  exit 1
fi
printf 'Started WorkBuddy AIP: PID %s\nLog: %s\n' "$pid" "$LOG_FILE"
