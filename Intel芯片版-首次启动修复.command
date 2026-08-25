#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="CodexSwitcher-Intel.app"
APP=""

pause_and_exit() {
  printf '\n%s\n' "$1"
  read -r -p '按回车键关闭此窗口...'
  exit "${2:-1}"
}

open_privacy_settings() {
  open "x-apple.systempreferences:com.apple.preference.security?General" >/dev/null 2>&1 || \
    open "/System/Library/PreferencePanes/Security.prefPane" >/dev/null 2>&1 || true
}

printf '\n苏苏全能中转站一键切换 Intel 芯片版 v1.3 首次启动修复\n\n'

if [[ "$(uname -m)" != "x86_64" ]]; then
  pause_and_exit '当前不是 Intel 芯片 Mac，请使用 M 芯片版本。'
fi

for candidate in \
  "$SCRIPT_DIR/$APP_NAME" \
  "/Applications/$APP_NAME" \
  "$HOME/Applications/$APP_NAME"
do
  if [[ -d "$candidate" ]]; then
    APP="$candidate"
    break
  fi
done

if [[ -z "$APP" ]]; then
  osascript -e 'display dialog "未找到 CodexSwitcher-Intel.app。请将应用与修复脚本放在同一文件夹，或先把应用拖入“应用程序”，再重新运行本脚本。" buttons {"打开隐私与安全性", "好"} default button "好" with title "苏苏全能中转站一键切换"' >/dev/null 2>&1
  open_privacy_settings
  pause_and_exit '未找到应用，已打开“隐私与安全性”。'
fi

BIN="$APP/Contents/MacOS/CodexSwitcher-Intel"
if [[ ! -f "$BIN" ]]; then
  pause_and_exit "应用包不完整，缺少主程序：$BIN"
fi

printf '正在修复：%s\n' "$APP"
chmod 755 "$BIN" || pause_and_exit '无法设置主程序执行权限。'
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true
xattr -cr "$APP" 2>/dev/null || true
codesign --force --deep --sign - "$APP" || pause_and_exit '重新签名失败。'
codesign --verify --deep --strict "$APP" || pause_and_exit '签名校验失败。'

printf '\n修复完成，正在启动应用...\n'
if open "$APP"; then
  sleep 3
  open_privacy_settings
  osascript -e 'display dialog "修复已完成。“隐私与安全性”已自动打开；如果仍有拦截记录，请点击“仍要打开”，然后再次右键应用选择“打开”。" buttons {"知道了"} default button "知道了" with title "苏苏全能中转站一键切换"' >/dev/null 2>&1 || true
else
  open_privacy_settings
  pause_and_exit '系统仍阻止启动，已自动打开“隐私与安全性”。请点击“仍要打开”。'
fi

printf '\n如应用已经打开，可直接关闭此窗口。\n'
read -r -p '按回车键关闭此窗口...'
