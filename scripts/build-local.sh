#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${WORKBUDDY_AIP_VENV:-$HOME/.workbuddy/binaries/python/envs/workbuddy-aip-macos}"
PYTHON_BIN="${PYTHON_BIN:-$VENV_DIR/bin/python}"
APP_NAME="WorkBuddy第三方AIP对接工具-Intel芯片"
DIST_DIR="$ROOT_DIR/dist-local"
BUILD_DIR="$ROOT_DIR/build-local"
ICONSET="$ROOT_DIR/icon.iconset"
ICON="$ROOT_DIR/susu_icon.icns"

if [[ "$(uname -m)" != "x86_64" ]]; then
  printf '%s\n' "This build script is for Intel x86_64 macOS." >&2
  exit 1
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  printf '%s\n' "Python environment is missing. Run scripts/setup-macos.sh first." >&2
  exit 1
fi

cd "$ROOT_DIR"
rm -rf "$DIST_DIR" "$BUILD_DIR" "$ICONSET" "$ICON"
"$PYTHON_BIN" generate_icon_macos.py
iconutil -c icns "$ICONSET" -o "$ICON"
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean --onefile --windowed \
  --name "$APP_NAME" --osx-bundle-identifier com.susu.workbuddy-aip \
  --icon "$ICON" --collect-data certifi --distpath "$DIST_DIR" \
  --workpath "$BUILD_DIR" workbuddy_aip.pyw

APP="$DIST_DIR/$APP_NAME.app"
BIN="$APP/Contents/MacOS/$APP_NAME"
test -x "$BIN"
test "$(lipo -archs "$BIN")" = "x86_64"
"$BIN" --self-test-tls
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
printf 'BUILD_OK\napp=%s\narch=%s\n' "$APP" "$(lipo -archs "$BIN")"
