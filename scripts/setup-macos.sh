#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_PYTHON="/Users/mac/.workbuddy/binaries/python/versions/3.13.12/bin/python3"
VENV_DIR="${WORKBUDDY_AIP_VENV:-$HOME/.workbuddy/binaries/python/envs/workbuddy-aip-macos}"
PYTHON_BIN="${PYTHON_BIN:-$DEFAULT_PYTHON}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  printf '%s\n' "Python 3 is required. Set PYTHON_BIN to a Python 3 executable." >&2
  exit 1
fi

case "$($PYTHON_BIN -c 'import sys; print(sys.version_info.major)')" in
  3) ;;
  *) printf '%s\n' "PYTHON_BIN must point to Python 3." >&2; exit 1 ;;
esac

printf 'Creating virtual environment: %s\n' "$VENV_DIR"
"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install --requirement "$ROOT_DIR/requirements-macos.txt"

printf '\nSetup complete.\n'
printf 'Venv: %s\n' "$VENV_DIR"
printf 'Next: %s/scripts/test-local.sh\n' "$ROOT_DIR"
