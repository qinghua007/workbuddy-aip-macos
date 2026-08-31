#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-$ROOT_DIR/.local}"
PID_FILE="$RUNTIME_DIR/workbuddy-aip.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "Not running"
  exit 0
fi
pid="$(tr -cd '0-9' < "$PID_FILE")"
if [ -z "$pid" ]; then
  rm -f "$PID_FILE"
  echo "Not running"
  exit 0
fi
if kill -0 "$pid" 2>/dev/null; then
  kill "$pid"
  for _ in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "Process did not stop cleanly: pid=$pid" >&2
    exit 1
  fi
fi
rm -f "$PID_FILE"
printf 'stopped pid=%s\n' "$pid"
