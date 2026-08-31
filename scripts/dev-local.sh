#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON="$VENV_DIR/bin/python"
RUNTIME_DIR="${RUNTIME_DIR:-$ROOT_DIR/.local}"
PID_FILE="$RUNTIME_DIR/workbuddy-aip.pid"
LOG_FILE="$RUNTIME_DIR/workbuddy-aip.log"

if [ ! -x "$PYTHON" ]; then
  echo "Local environment missing. Run scripts/setup-macos.sh first." >&2
  exit 1
fi

# The managed Python build may not export its Tcl/Tk resource paths into a venv.
TCL_LIBRARY="${TCL_LIBRARY:-$($PYTHON -c 'import os, sys, _tkinter; print(os.path.join(sys.base_prefix, "lib", "tcl%s" % _tkinter.TCL_VERSION))')}"
TK_LIBRARY="${TK_LIBRARY:-$($PYTHON -c 'import os, sys, _tkinter; print(os.path.join(sys.base_prefix, "lib", "tk%s" % _tkinter.TK_VERSION))')}"
export TCL_LIBRARY TK_LIBRARY
if [ ! -f "$TCL_LIBRARY/init.tcl" ] || [ ! -f "$TK_LIBRARY/tk.tcl" ]; then
  echo "Tcl/Tk resources were not found. TCL_LIBRARY=$TCL_LIBRARY TK_LIBRARY=$TK_LIBRARY" >&2
  exit 1
fi
mkdir -p "$RUNTIME_DIR"

if [ -f "$PID_FILE" ]; then
  pid="$(tr -cd '0-9' < "$PID_FILE")"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "Already running: pid=$pid"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

cd "$ROOT_DIR"
nohup "$PYTHON" workbuddy_aip.pyw >>"$LOG_FILE" 2>&1 &
pid=$!
printf '%s\n' "$pid" > "$PID_FILE"

for _ in $(seq 1 20); do
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "Application exited during startup. See $LOG_FILE" >&2
    rm -f "$PID_FILE"
    exit 1
  fi
  sleep 0.25
done
printf 'started pid=%s\nlog=%s\n' "$pid" "$LOG_FILE"
