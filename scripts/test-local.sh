#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${WORKBUDDY_AIP_VENV:-$HOME/.workbuddy/binaries/python/envs/workbuddy-aip-macos}"
PYTHON_BIN="${PYTHON_BIN:-$VENV_DIR/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  printf '%s\n' "Python environment is missing. Run scripts/setup-macos.sh first." >&2
  exit 1
fi

cd "$ROOT_DIR"
"$PYTHON_BIN" -m py_compile workbuddy_aip.pyw test_ssl_regression.py generate_icon_macos.py
"$PYTHON_BIN" test_ssl_regression.py
"$PYTHON_BIN" -c 'import certifi, tkinter; assert tkinter.TkVersion >= 8.6; print("RUNTIME_IMPORTS_OK"); print("python=%s" % __import__("sys").version.split()[0]); print("certifi=%s" % certifi.where())'

if [[ "${RUN_GUI_HEALTHCHECK:-0}" == "1" ]]; then
  "$ROOT_DIR/scripts/dev-local.sh"
  trap '"$ROOT_DIR/scripts/stop-local.sh" >/dev/null 2>&1 || true' EXIT
  "$ROOT_DIR/scripts/stop-local.sh" --check
fi

printf '%s\n' "LOCAL_TESTS_OK"
