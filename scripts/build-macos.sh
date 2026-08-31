#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON="$VENV_DIR/bin/python"
APP_NAME="${APP_NAME:-WorkBuddy第三方AIP对接工具-Intel芯片}"
BUNDLE_ID="${BUNDLE_ID:-com.susu.workbuddy-aip}"
DIST_DIR="$ROOT_DIR/dist-intel-local"
BUILD_DIR="$ROOT_DIR/build-intel-local"
ICONSET_DIR="$ROOT_DIR/icon.iconset"
ICON_FILE="$ROOT_DIR/susu_icon.icns"
APP_PATH="$DIST_DIR/$APP_NAME.app"
BIN_PATH="$APP_PATH/Contents/MacOS/$APP_NAME"

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "x86_64" ]; then
  echo "This build script targets an Intel macOS host." >&2
  exit 1
fi
if [ ! -x "$PYTHON" ]; then
  echo "Local environment missing. Run scripts/setup-macos.sh first." >&2
  exit 1
fi

cd "$ROOT_DIR"
"$PYTHON" generate_icon_macos.py
iconutil -c icns "$ICONSET_DIR" -o "$ICON_FILE"
"$PYTHON" -m PyInstaller --noconfirm --clean --onefile --windowed \
  --name "$APP_NAME" --osx-bundle-identifier "$BUNDLE_ID" --icon "$ICON_FILE" \
  --collect-data certifi --distpath "$DIST_DIR" --workpath "$BUILD_DIR" workbuddy_aip.pyw

test -d "$APP_PATH"
test -f "$APP_PATH/Contents/Info.plist"
test -x "$BIN_PATH"
/usr/libexec/PlistBuddy -c "Delete :CFBundleIdentifier" "$APP_PATH/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Delete :CFBundleShortVersionString" "$APP_PATH/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Delete :CFBundleVersion" "$APP_PATH/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string $BUNDLE_ID" "$APP_PATH/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string 1.4" "$APP_PATH/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string 1.4.0" "$APP_PATH/Contents/Info.plist"
chmod 755 "$BIN_PATH"
codesign --force --deep --sign - "$APP_PATH"
"$BIN_PATH" --self-test-tls
plutil -lint "$APP_PATH/Contents/Info.plist"
test "$(lipo -archs "$BIN_PATH")" = "x86_64"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"
printf 'MACOS_BUILD_OK\napp=%s\narch=%s\n' "$APP_PATH" "$(lipo -archs "$BIN_PATH")"
