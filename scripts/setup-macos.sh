#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This setup script requires macOS." >&2
  exit 1
fi
if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
  echo "python3 was not found. Install Python 3.12+ and retry." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
  echo "Python 3.12 or newer is required." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import tkinter' >/dev/null 2>&1; then
  echo "Tkinter is unavailable in the selected Python." >&2
  exit 1
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip certifi pillow pyinstaller
"$VENV_DIR/bin/python" -c 'import certifi, PIL, tkinter; print("MACOS_ENVIRONMENT_OK")'
printf 'environment=%s\npython=%s\n' "$VENV_DIR" "$($VENV_DIR/bin/python --version)"
