#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON="$VENV_DIR/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "Local environment missing. Run scripts/setup-macos.sh first." >&2
  exit 1
fi
cd "$ROOT_DIR"
"$PYTHON" -m py_compile workbuddy_aip.pyw test_ssl_regression.py generate_icon_macos.py
"$PYTHON" test_ssl_regression.py
printf '%s\n' "LOCAL_TESTS_OK"
