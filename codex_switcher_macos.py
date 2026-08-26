#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codex Provider Switcher V1.22 — macOS Edition
Codex 供应商切换器 macOS 版本
支持读取模型、使用中转站后直达 Codex，以及切换 GPT 账号登录。
"""

import copy
import glob
import json
import os
import pathlib
import platform
import re
import shlex
import shutil
import ssl
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request

import certifi
import keyring
from tkinter import messagebox, ttk

APP_NAME = "苏苏全能中转站一键切换"
APP_VERSION = "1.22-macOS"
KEYCHAIN_SERVICE = "com.susu.codex-switcher.api-key"

# ---------------- Codex 双配置目录 ----------------
def resolve_codex_dir():
    """CLI 使用 CODEX_HOME；官方桌面端固定读取 ~/.codex。"""
    home = os.environ.get("CODEX_HOME") or ""
    if home:
        return os.path.abspath(os.path.expanduser(os.path.expandvars(home)))
    return os.path.join(os.path.expanduser("~"), ".codex")


CODEX_DIR = resolve_codex_dir()
DESKTOP_CODEX_DIR = os.path.join(os.path.expanduser("~"), ".codex")
CONFIG_PATH = os.path.join(CODEX_DIR, "config.toml")
AUTH_PATH = os.path.join(CODEX_DIR, "auth.json")
DESKTOP_CONFIG_PATH = os.path.join(DESKTOP_CODEX_DIR, "config.toml")
DESKTOP_AUTH_PATH = os.path.join(DESKTOP_CODEX_DIR, "auth.json")
SW_DIR = os.path.join(CODEX_DIR, "provider-switcher")
PROVIDERS_FILE = os.path.join(SW_DIR, "providers.json")
BACKUP_DIR = os.path.join(SW_DIR, "backups")
OFFICIAL_AUTH_BACKUP_PATH = os.path.join(SW_DIR, "official-auth-backup.json")
OFFICIAL_AUTH_BACKUP_META_PATH = os.path.join(SW_DIR, "official-auth-backup.meta.json")
RECOVERY_AUTH_BACKUP_PATH = os.path.join(SW_DIR, "pre-switch-auth-recovery.json")
RECOVERY_AUTH_BACKUP_META_PATH = os.path.join(SW_DIR, "pre-switch-auth-recovery.meta.json")

WIRE_RESPONSES = "responses"
WIRE_CHAT = "chat_completions"
SWITCH_LOCK = threading.Lock()
INSTANCE_LOCK_HANDLE = None
PROVIDER_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

# ---------------- macOS shell profile for env vars ----------------
def get_shell_profile():
    """Return the shell profile path for setting environment variables."""
    home = os.path.expanduser("~")
    zshrc = os.path.join(home, ".zshrc")
    if os.path.exists(zshrc) or os.environ.get("SHELL", "").endswith("zsh"):
        return zshrc
    return os.path.join(home, ".bash_profile")


# ---------------- 默认预置供应商（首次运行写入 providers.json） ----------------
DEFAULT_PROVIDERS = [
    {
        "key": "vakv",
        "name": "VAKV",
        "base_url": "https://api.vakv.cn/v1",
        "wire_api": WIRE_RESPONSES,
        "api_key": "",
        "models": ["gpt-5.6-terra", "gpt-5.6", "gpt-5.6-luna", "gpt-5.6-sol", "gpt-5.5", "gpt-4.1"],
        "model": "gpt-5.6-terra",
    },
    {
        "key": "aivr",
        "name": "AIVR",
        "base_url": "https://api.aivr.cc/v1",
        "wire_api": WIRE_RESPONSES,
        "api_key": "",
        "models": ["gpt-5.6", "gpt-5.5", "claude-opus-4.8"],
        "model": "gpt-5.6",
    },
    {
        "key": "openai",
        "name": "OpenAI 官方",
        "base_url": "https://api.openai.com/v1",
        "wire_api": WIRE_RESPONSES,
        "api_key": "",
        "models": ["gpt-5.6", "gpt-5.5", "gpt-5", "o3", "gpt-4.1"],
        "model": "gpt-5.6",
    },
]


# ============================ 核心逻辑（无 GUI 依赖，可单测） ============================

def validate_provider_key(provider_key):
    provider_key = str(provider_key or "").strip()
    if not PROVIDER_KEY_PATTERN.fullmatch(provider_key):
        raise ValueError("供应商 key 仅允许小写字母、数字、下划线和短横线，且长度不超过 64")
    return provider_key


def providers_without_secrets(providers):
    """providers.json 只保存结构，不保存 API Key。"""
    clean = copy.deepcopy(providers)
    for provider in clean:
        provider["api_key"] = ""
    return clean


def atomic_write_text(path, text, mode=None):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    temp_path = "%s.%s.%s.tmp" % (path, os.getpid(), threading.get_ident())
    try:
        with open(temp_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(temp_path, mode)
        os.replace(temp_path, path)
        if mode is not None:
            os.chmod(path, mode)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def migrate_provider_secrets(providers):
    """迁移旧明文密钥；任一持久化失败时不返回脱敏数据。"""
    clean = copy.deepcopy(providers)
    migrated = 0
    for provider in clean:
        provider_key = validate_provider_key(provider.get("key"))
        api_key = str(provider.get("api_key") or "").strip()
        if api_key:
            env_name = "%s_API_KEY" % provider_key.upper()
            set_user_env_macos(env_name, api_key)
            os.environ[env_name] = api_key
            migrated += 1
        provider["api_key"] = ""
    return clean, migrated


def load_providers():
    """加载供应商；旧明文密钥成功持久化后立即原子脱敏。"""
    candidates = [PROVIDERS_FILE]
    legacy = os.path.join(DESKTOP_CODEX_DIR, "provider-switcher", "providers.json")
    if os.path.normcase(os.path.abspath(legacy)) != os.path.normcase(os.path.abspath(PROVIDERS_FILE)):
        candidates.append(legacy)

    found_existing = False
    last_error = None
    for candidate in candidates:
        if not os.path.exists(candidate):
            continue
        found_existing = True
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list) or not data:
                raise ValueError("供应商文件不是有效的非空列表")
            clean, migrated = migrate_provider_secrets(data)
            if candidate != PROVIDERS_FILE or migrated or clean != data:
                save_providers(clean)
            return clean
        except Exception as exc:
            last_error = exc
            continue

    if found_existing:
        raise RuntimeError("读取或迁移现有供应商配置失败，原文件已保留：%s" % last_error)

    clean = providers_without_secrets(DEFAULT_PROVIDERS)
    save_providers(clean)
    return copy.deepcopy(clean)


def save_providers(providers):
    payload = json.dumps(providers_without_secrets(providers), ensure_ascii=False, indent=2)
    atomic_write_text(PROVIDERS_FILE, payload)


def parse_toml(path):
    """极简 TOML 解析，仅需顶层键与 [section] 键。"""
    result = {}
    section = None
    if not os.path.exists(path):
        return result
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1].strip()
                    result[section] = {}
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if section:
                        result[section][k] = v
                    else:
                        result[k] = v
    except Exception:
        pass
    return result


def toml_string(value):
    """用 JSON 双引号转义生成兼容 TOML basic string 的安全字符串。"""
    return json.dumps(str(value), ensure_ascii=False)


def build_config_text(provider, existing_config=""):
    """安全更新 config.toml：顶层模型键置顶，目标 Provider 段置于末尾。"""
    provider_key = validate_provider_key(provider["key"])
    target_section = "model_providers.%s" % provider_key
    preserved = []
    lifted_top_level = []
    current_section = None
    skip_target_section = False
    known_top_level_keys = {
        "approval_policy", "sandbox_mode", "web_search", "personality",
        "disable_response_storage", "model_context_window",
        "model_auto_compact_token_limit", "model_reasoning_effort",
        "model_reasoning_summary", "model_verbosity", "hide_agent_reasoning",
        "show_raw_agent_reasoning", "file_opener", "notify",
    }

    old_provider_key = ""
    for line in existing_config.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            break
        if "=" in stripped and not stripped.startswith("#"):
            key_name, value = stripped.split("=", 1)
            if key_name.strip() == "model_provider":
                old_provider_key = value.strip().strip('"').strip("'")
                break
    damaged_section = "model_providers.%s" % old_provider_key if old_provider_key else ""

    for line in existing_config.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped.strip("[]").strip()
            skip_target_section = current_section == target_section
            if skip_target_section:
                continue
        key_name = ""
        if "=" in stripped and not stripped.startswith("#"):
            key_name = stripped.split("=", 1)[0].strip()
        if skip_target_section:
            if key_name in known_top_level_keys:
                lifted_top_level.append(line)
            continue
        if current_section == damaged_section and key_name in known_top_level_keys:
            lifted_top_level.append(line)
            continue
        if current_section is None and key_name in {"model_provider", "model"}:
            continue
        preserved.append(line)

    while preserved and not preserved[0].strip():
        preserved.pop(0)
    while preserved and not preserved[-1].strip():
        preserved.pop()

    lines = [
        "model_provider = %s" % toml_string(provider_key),
        "model = %s" % toml_string(provider["model"]),
    ]
    lines.extend(lifted_top_level)
    if preserved:
        lines.extend([""] + preserved)
    else:
        lines.extend(["", "[features]", "goals = true"])
    if provider_key != "openai":
        lines.extend([
            "",
            "[model_providers.%s]" % provider_key,
            "name = %s" % toml_string(provider["name"]),
            "base_url = %s" % toml_string(provider["base_url"].rstrip("/")),
            "wire_api = %s" % toml_string(provider["wire_api"]),
            "env_key = %s" % toml_string("%s_API_KEY" % provider_key.upper()),
        ])
    return "\n".join(lines).rstrip() + "\n"


def backup_config(path=CONFIG_PATH, label="cli"):
    """切换前备份指定 config.toml，返回备份路径或 None。"""
    if not os.path.exists(path):
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S") + ("-%03d" % (time.time_ns() % 1000))
    dst = os.path.join(BACKUP_DIR, "config-%s-%s.toml" % (label, ts))
    shutil.copy2(path, dst)
    return dst


def validate_env_name(name):
    if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", str(name or "")):
        raise ValueError("环境变量名不安全")
    return str(name)


def set_keychain_secret(name, value):
    """通过 Python macOS Keychain 后端写入登录钥匙串，避免密钥进入进程参数。"""
    name = validate_env_name(name)
    if not value:
        return
    try:
        keyring.set_password(KEYCHAIN_SERVICE, name, value)
    except Exception as exc:
        detail = str(exc).replace(value, "***")
        raise RuntimeError("写入 macOS 钥匙串失败：%s" % detail)


def get_keychain_secret(name):
    name = validate_env_name(name)
    try:
        value = keyring.get_password(KEYCHAIN_SERVICE, name)
    except Exception:
        return None
    return value or None


def delete_keychain_secret(name):
    name = validate_env_name(name)
    try:
        keyring.delete_password(KEYCHAIN_SERVICE, name)
    except keyring.errors.PasswordDeleteError:
        pass


def restore_keychain_secret(name, value):
    if value:
        set_keychain_secret(name, value)
    else:
        delete_keychain_secret(name)
    if value:
        os.environ[name] = value
    else:
        os.environ.pop(name, None)


def _get_shell_profile_secret(name):
    name = validate_env_name(name)
    profile = get_shell_profile()
    if not os.path.exists(profile):
        return None
    marker_begin = "# >>> Codex Provider Switcher: %s >>>" % name
    marker_end = "# <<< Codex Provider Switcher: %s <<<" % name
    in_block = False
    try:
        with open(profile, "r", encoding="utf-8", errors="strict") as f:
            for raw in f:
                line = raw.strip()
                if line == marker_begin:
                    in_block = True
                    continue
                if line == marker_end:
                    in_block = False
                    continue
                if in_block and line.startswith("export %s=" % name):
                    tokens = shlex.split(line[len("export "):], posix=True)
                    if len(tokens) == 1 and tokens[0].startswith(name + "="):
                        value = tokens[0].split("=", 1)[1]
                        return value or None
    except (OSError, ValueError):
        return None
    return None


def set_user_env_macos(name, value):
    """API Key 仅写入 macOS 钥匙串；旧版 shell profile 只读迁移，不再新增明文。"""
    name = validate_env_name(name)
    if not value:
        return
    set_keychain_secret(name, value)
    os.environ[name] = value


def get_user_env_macos(name):
    """读取本进程、macOS 钥匙串或旧版 shell profile，并自动迁移旧密钥。"""
    name = validate_env_name(name)
    if os.environ.get(name):
        return os.environ[name]
    keychain_value = get_keychain_secret(name)
    if keychain_value:
        os.environ[name] = keychain_value
        return keychain_value
    legacy_value = _get_shell_profile_secret(name)
    if legacy_value:
        try:
            set_keychain_secret(name, legacy_value)
        except Exception:
            pass
        os.environ[name] = legacy_value
        return legacy_value
    return None


def bundled_codex_cli_path():
    """返回随本应用打包的官方原生 Codex CLI 路径。"""
    bundle_root = getattr(sys, "_MEIPASS", "")
    if not bundle_root:
        return ""
    return os.path.join(bundle_root, "codex-cli", "codex")


def _codex_app_bundles():
    """动态发现系统、用户和 Spotlight 可见的 Codex.app，不依赖固定安装名称。"""
    home = os.path.expanduser("~")
    bundles = [
        "/Applications/Codex.app",
        os.path.join(home, "Applications", "Codex.app"),
    ]
    for root in ("/Applications", os.path.join(home, "Applications")):
        bundles.extend(sorted(glob.glob(os.path.join(root, "*Codex*.app"))))
    if sys.platform == "darwin":
        try:
            lookup = subprocess.run(
                ["/usr/bin/mdfind", "kMDItemCFBundleIdentifier == 'com.openai.codex'"],
                capture_output=True, text=True, timeout=8,
            )
            if lookup.returncode == 0:
                bundles.extend(line.strip() for line in lookup.stdout.splitlines() if line.strip().endswith(".app"))
        except Exception:
            pass
    return list(dict.fromkeys(os.path.realpath(path) for path in bundles if path))


def codex_gui_pids():
    """返回 Codex.app 主进程及辅助进程 PID，用于确认认证切换前后确实重启。"""
    if sys.platform != "darwin":
        return set()
    markers = [
        os.path.realpath(bundle) + os.sep + "Contents" + os.sep
        for bundle in _codex_app_bundles()
    ]
    pids = set()
    try:
        result = subprocess.run(
            ["/bin/ps", "-axo", "pid=,command="],
            capture_output=True, text=True, timeout=8,
        )
    except Exception as exc:
        raise RuntimeError("无法读取 Codex GUI 进程：%s" % exc)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "返回码 %d" % result.returncode).strip()
        raise RuntimeError("无法读取 Codex GUI 进程：%s" % detail)
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        command = parts[1]
        is_discovered_bundle = any(marker in command for marker in markers)
        is_codex_bundle = bool(re.search(r"/[^/]*\bCodex\b[^/]*\.app/Contents/", command))
        if is_discovered_bundle or is_codex_bundle:
            pids.add(int(parts[0]))
    return pids


def wait_for_codex_app_exit(timeout=18):
    """等待 Codex.app 的全部进程退出，避免新认证被旧 renderer/session 缓存覆盖。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not codex_gui_pids():
            return True
        time.sleep(0.25)
    return not codex_gui_pids()


def quit_running_codex_app(grace_timeout=12, terminate_timeout=8):
    """先请求 Codex 正常退出；无响应时仅终止 Codex.app 进程，不执行 codex logout。"""
    old_pids = codex_gui_pids()
    if not old_pids:
        return old_pids, ["未检测到正在运行的 Codex GUI"]

    script = 'tell application id "com.openai.codex" to quit'
    try:
        subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            capture_output=True, text=True, timeout=8,
        )
    except Exception:
        pass
    if wait_for_codex_app_exit(grace_timeout):
        return old_pids, ["已正常退出旧 Codex GUI，准备重新加载认证状态"]

    remaining = codex_gui_pids()
    for pid in remaining:
        try:
            os.kill(pid, 15)
        except (ProcessLookupError, PermissionError):
            pass
    if not wait_for_codex_app_exit(terminate_timeout):
        raise RuntimeError("Codex GUI 未能完全退出，请手动退出 Codex 后重试")
    return old_pids | remaining, ["旧 Codex GUI 未响应，已安全终止其进程并清除旧会话状态"]


def wait_for_fresh_codex_app(old_pids, timeout=20):
    """等待不属于旧实例的新 Codex GUI PID 出现。"""
    deadline = time.monotonic() + timeout
    old_pids = set(old_pids or ())
    while time.monotonic() < deadline:
        current = codex_gui_pids()
        fresh = current - old_pids
        if fresh:
            return fresh
        time.sleep(0.25)
    return set()


def reopen_codex_app_best_effort(env):
    """失败回滚后尽力恢复用户原先正在使用的 Codex GUI，不覆盖原始错误。"""
    try:
        bundles = [path for path in _codex_app_bundles() if os.path.isdir(path)]
        command = ["/usr/bin/open", bundles[0]] if bundles else ["/usr/bin/open", "-a", "Codex"]
        subprocess.run(command, capture_output=True, text=True, timeout=20, env=env)
    except Exception:
        pass


def launch_fresh_codex_app(cli, cwd, env, old_pids=None):
    """启动全新 Codex GUI，并以新 PID 为准验证；命令返回 0 不再等同于成功。"""
    errors = []
    launch = None
    try:
        launch = subprocess.run(
            [cli, "app", cwd], capture_output=True, text=True, timeout=20, env=env,
        )
        if launch.returncode != 0:
            errors.append(
                "codex app: %s" % (
                    launch.stderr or launch.stdout or "返回码 %d" % launch.returncode
                ).strip()
            )
        else:
            fresh = wait_for_fresh_codex_app(old_pids, timeout=20)
            if fresh:
                return ["已启动全新 Codex GUI 进程（PID：%s），认证状态已重新加载" % ", ".join(map(str, sorted(fresh)))]
            current = codex_gui_pids()
            if current:
                raise RuntimeError("codex app 返回成功，但仅检测到旧或无法确认的新 Codex GUI 进程")
            raise RuntimeError("codex app 返回成功，但 20 秒内未检测到 Codex GUI 进程；为避免双实例未执行第二次启动")
    except Exception as exc:
        errors.append("codex app: %s" % exc)
        if (launch is not None and launch.returncode == 0) or codex_gui_pids():
            raise RuntimeError("；".join(errors))

    app_bundles = [path for path in _codex_app_bundles() if os.path.isdir(path)]
    fallback_command = (
        ["/usr/bin/open", "-n", app_bundles[0]]
        if app_bundles else ["/usr/bin/open", "-na", "Codex"]
    )
    try:
        fallback = subprocess.run(
            fallback_command, capture_output=True, text=True, timeout=20, env=env,
        )
        if fallback.returncode != 0:
            raise RuntimeError(
                (fallback.stderr or fallback.stdout or "返回码 %d" % fallback.returncode).strip()
            )
        fresh = wait_for_fresh_codex_app(old_pids, timeout=20)
        if fresh:
            return [
                "codex app 未创建新进程，已通过系统入口启动全新 Codex GUI（PID：%s）"
                % ", ".join(map(str, sorted(fresh)))
            ]
        raise RuntimeError("系统入口返回成功，但未检测到新的 Codex GUI 进程")
    except Exception as exc:
        errors.append("系统入口: %s" % exc)
        raise RuntimeError("；".join(errors))


def _codex_cli_candidates():
    """返回 GUI 环境下可用的 Codex CLI 候选；包内官方 CLI 优先，系统安装作为后备。"""
    home = os.path.expanduser("~")
    candidates = [
        bundled_codex_cli_path(),
        os.environ.get("CODEX_CLI_PATH") or "",
    ]
    for app_bundle in _codex_app_bundles():
        resource_root = os.path.join(app_bundle, "Contents", "Resources")
        candidates.extend([
            os.path.join(resource_root, "codex"),
            os.path.join(resource_root, "bin", "codex"),
            os.path.join(resource_root, "app.asar.unpacked", "codex"),
            os.path.join(resource_root, "app.asar.unpacked", "bin", "codex"),
        ])
        # 官方 App 内部目录会随版本变化；限定在 Resources 内动态寻找同名可执行文件。
        candidates.extend(sorted(glob.glob(os.path.join(resource_root, "**", "codex"), recursive=True)))
    candidates.extend([
        "/opt/homebrew/bin/codex",
        "/usr/local/bin/codex",
        "/usr/bin/codex",
        os.path.join(home, ".local", "bin", "codex"),
        os.path.join(home, ".npm-global", "bin", "codex"),
        os.path.join(home, ".volta", "bin", "codex"),
    ])
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if directory:
            candidates.append(os.path.join(directory, "codex"))
    candidates.extend(sorted(
        glob.glob(os.path.join(home, ".nvm", "versions", "node", "*", "bin", "codex")),
        reverse=True,
    ))
    for extension_root in (
        os.path.join(home, ".vscode", "extensions"),
        os.path.join(home, ".vscode-insiders", "extensions"),
        os.path.join(home, ".cursor", "extensions"),
        os.path.join(home, ".windsurf", "extensions"),
    ):
        candidates.extend(sorted(
            glob.glob(os.path.join(extension_root, "openai.chatgpt-*", "bin", "*", "codex")),
            reverse=True,
        ))
    for shell in ("/bin/zsh", "/bin/bash"):
        if not os.path.isfile(shell):
            continue
        try:
            shell_lookup = subprocess.run(
                [shell, "-lic", "command -v codex"], capture_output=True, text=True, timeout=8,
            )
            if shell_lookup.returncode == 0 and shell_lookup.stdout.strip():
                candidates.append(shell_lookup.stdout.strip().splitlines()[0])
        except Exception:
            pass
    return list(dict.fromkeys(os.path.realpath(path) for path in candidates if path))


def find_codex_cli():
    """定位可执行 Codex CLI；发行包内置官方原生 CLI，因此不依赖用户额外安装。"""
    checked = []
    for path in _codex_cli_candidates():
        checked.append(path)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    preview = "；".join(checked[:6]) if checked else "没有生成候选路径"
    raise FileNotFoundError(
        "未找到可执行的 Codex CLI。当前修复包应自带官方 CLI；请重新下载并完整解压 ZIP，"
        "不要只复制单个可执行文件。已检查：%s。也可设置 CODEX_CLI_PATH 指向实际 codex。" % preview
    )


def acquire_single_instance_lock():
    """使用 POSIX flock 阻止重复实例，避免 Dock 出现同一工具的重复图标。"""
    global INSTANCE_LOCK_HANDLE
    if sys.platform != "darwin":
        return True
    import fcntl
    lock_dir = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "SuSuCodexSwitcher")
    os.makedirs(lock_dir, exist_ok=True)
    handle = open(os.path.join(lock_dir, "instance.lock"), "a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    INSTANCE_LOCK_HANDLE = handle
    return True


def activate_existing_instance():
    """重复启动时激活已运行实例，不创建第二个 GUI 进程。"""
    if sys.platform != "darwin":
        return
    script = 'tell application id "com.susu.codex-switcher" to activate'
    try:
        subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, timeout=5)
    except Exception:
        pass


def current_api_key(provider):
    """优先使用本次表单输入，否则沿用用户环境持久层。"""
    return provider.get("api_key") or get_user_env_macos(
        "%s_API_KEY" % provider["key"].upper()
    ) or ""


def config_targets():
    targets = [(CONFIG_PATH, "cli")]
    if os.path.normcase(os.path.abspath(DESKTOP_CONFIG_PATH)) != os.path.normcase(os.path.abspath(CONFIG_PATH)):
        targets.append((DESKTOP_CONFIG_PATH, "desktop"))
    return targets


def write_provider_to_target(provider, config_path):
    existing = ""
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            existing = f.read()
    atomic_write_text(config_path, build_config_text(provider, existing))


def ensure_api_key_login(cli, api_key, codex_home=DESKTOP_CODEX_DIR):
    """使用官方登录命令；API Key 仅经 stdin 传递，桌面 CODEX_HOME 固定为 ~/.codex。"""
    env = os.environ.copy()
    env["CODEX_HOME"] = codex_home
    result = subprocess.run(
        [cli, "login", "--with-api-key"], input=api_key + "\n", text=True,
        capture_output=True, timeout=45, env=env,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "未知错误").strip().replace(api_key, "***")
        raise RuntimeError(detail)


def snapshot_file(path):
    return pathlib.Path(path).read_bytes() if os.path.exists(path) else None


def restore_file_snapshot(path, content, mode=None):
    if content is None:
        if os.path.exists(path):
            os.remove(path)
        return
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    temp_path = "%s.%s.%s.restore.tmp" % (path, os.getpid(), threading.get_ident())
    try:
        pathlib.Path(temp_path).write_bytes(content)
        if mode is not None:
            os.chmod(temp_path, mode)
        os.replace(temp_path, path)
        if mode is not None:
            os.chmod(path, mode)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def backup_official_auth():
    """保存切到第三方前的官方桌面认证。"""
    auth_content = snapshot_file(DESKTOP_AUTH_PATH)
    restore_file_snapshot(OFFICIAL_AUTH_BACKUP_PATH, auth_content, mode=0o600)
    atomic_write_text(
        OFFICIAL_AUTH_BACKUP_META_PATH,
        json.dumps({
            "version": 1, "had_auth": auth_content is not None,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False, indent=2),
        mode=0o600,
    )
    return auth_content is not None


def write_recovery_auth_snapshot(previous_provider):
    auth_content = snapshot_file(DESKTOP_AUTH_PATH)
    if auth_content is None:
        return False
    restore_file_snapshot(RECOVERY_AUTH_BACKUP_PATH, auth_content, mode=0o600)
    atomic_write_text(
        RECOVERY_AUTH_BACKUP_META_PATH,
        json.dumps({
            "version": 1, "previous_provider": previous_provider or "unknown",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False, indent=2),
        mode=0o600,
    )
    return True


def restore_official_auth():
    if not os.path.exists(OFFICIAL_AUTH_BACKUP_META_PATH):
        raise RuntimeError("未找到第三方登录前的官方认证备份，请先在 Codex 中完成 OpenAI 官方登录")
    try:
        metadata = json.loads(pathlib.Path(OFFICIAL_AUTH_BACKUP_META_PATH).read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError("官方认证备份元数据损坏：%s" % exc)
    if not metadata.get("had_auth") or not os.path.exists(OFFICIAL_AUTH_BACKUP_PATH):
        raise RuntimeError("没有可恢复的 OpenAI 官方认证，请重新登录官方账号")
    restore_file_snapshot(DESKTOP_AUTH_PATH, snapshot_file(OFFICIAL_AUTH_BACKUP_PATH), mode=0o600)


def transaction_paths(include_auth_backups=True):
    paths = [path for path, _ in config_targets()]
    paths.extend([DESKTOP_AUTH_PATH, PROVIDERS_FILE])
    if include_auth_backups:
        paths.extend([
            OFFICIAL_AUTH_BACKUP_PATH, OFFICIAL_AUTH_BACKUP_META_PATH,
            RECOVERY_AUTH_BACKUP_PATH, RECOVERY_AUTH_BACKUP_META_PATH,
        ])
    return list(dict.fromkeys(paths))


def sensitive_file_mode(path):
    sensitive_paths = {
        os.path.normcase(os.path.abspath(DESKTOP_AUTH_PATH)),
        os.path.normcase(os.path.abspath(OFFICIAL_AUTH_BACKUP_PATH)),
        os.path.normcase(os.path.abspath(OFFICIAL_AUTH_BACKUP_META_PATH)),
        os.path.normcase(os.path.abspath(RECOVERY_AUTH_BACKUP_PATH)),
        os.path.normcase(os.path.abspath(RECOVERY_AUTH_BACKUP_META_PATH)),
    }
    return 0o600 if os.path.normcase(os.path.abspath(path)) in sensitive_paths else None


def restore_snapshots(snapshots):
    errors = []
    for path, content in snapshots.items():
        try:
            restore_file_snapshot(path, content, mode=sensitive_file_mode(path))
            if content is not None and snapshot_file(path) != content:
                raise RuntimeError("恢复后内容校验不一致")
        except Exception as exc:
            errors.append("%s: %s" % (path, exc))
    return errors


def switch_provider(provider):
    """后台可调用的事务切换；正常流程绝不执行 logout。"""
    if not SWITCH_LOCK.acquire(blocking=False):
        return False, ["已有切换或账号操作正在进行，请稍候"]
    try:
        return _switch_provider_locked(copy.deepcopy(provider))
    finally:
        SWITCH_LOCK.release()


def _switch_provider_locked(provider):
    msgs = []
    if not provider.get("model"):
        return False, ["未选择模型，无法切换"]
    try:
        provider["key"] = validate_provider_key(provider.get("key"))
    except ValueError as exc:
        return False, [str(exc)]
    key = current_api_key(provider)
    if provider["key"] != "openai" and not key:
        return False, ["缺少 API Key，请填写后再切换"]

    targets = config_targets()
    snapshots = {path: snapshot_file(path) for path in transaction_paths()}
    env_name = "%s_API_KEY" % provider["key"].upper() if provider["key"] != "openai" else ""
    previous_key = get_user_env_macos(env_name) if env_name else None
    previous_provider = parse_toml(DESKTOP_CONFIG_PATH).get("model_provider", "")
    try:
        if provider["key"] != "openai" and write_recovery_auth_snapshot(previous_provider):
            msgs.append("已保存本次登录前的认证恢复快照")
        if (provider["key"] != "openai" and os.path.exists(DESKTOP_AUTH_PATH)
                and previous_provider in {"", "openai"}):
            backup_official_auth()
            msgs.append("已保存切换第三方前的 OpenAI 官方认证")

        for config_path, label in targets:
            bak = backup_config(config_path, label)
            if bak:
                msgs.append("已备份 %s 配置 -> %s" % (label, os.path.basename(bak)))
            write_provider_to_target(provider, config_path)
            msgs.append("%s 配置已同步 -> %s" % (label, config_path))

        if provider["key"] == "openai":
            if previous_provider not in {"", "openai"}:
                restore_official_auth()
                msgs.append("OpenAI 官方认证已恢复")
        else:
            ensure_api_key_login(find_codex_cli(), key, DESKTOP_CODEX_DIR)
            set_user_env_macos(env_name, key)
            os.environ[env_name] = key
            msgs.append("官方桌面端第三方 API Key 登录态已建立")

        providers = load_providers()
        for saved_provider in providers:
            saved_provider["active"] = saved_provider["key"] == provider["key"]
        save_providers(providers)
    except Exception as exc:
        rollback_errors = restore_snapshots(snapshots)
        if env_name:
            try:
                restore_keychain_secret(env_name, previous_key)
            except Exception as rollback_exc:
                rollback_errors.append("macOS 钥匙串: %s" % rollback_exc)
        error_text = str(exc).replace(key, "***") if key else str(exc)
        if rollback_errors:
            return False, msgs + ["切换失败，且部分回滚未完成：%s；%s" % (error_text, " | ".join(rollback_errors))]
        return False, msgs + ["切换失败，配置、认证、密钥与供应商状态已回滚：%s" % error_text]

    msgs.append("未执行 codex logout（保留第三方 API Key 登录态）")
    return True, msgs


def switch_provider_and_launch(provider, cli=None, cwd=None):
    """退出旧 GUI 后切换认证并启动新 GUI；正常第三方流程绝不执行 logout。"""
    if not SWITCH_LOCK.acquire(blocking=False):
        return False, ["已有切换或账号操作正在进行，请稍候"]
    provider = copy.deepcopy(provider)
    outer_snapshots = {}
    env_name = ""
    previous_key = None
    old_pids = set()
    quit_messages = []
    launch_env = os.environ.copy()
    try:
        outer_snapshots = {path: snapshot_file(path) for path in transaction_paths()}
        env_name = "%s_API_KEY" % provider.get("key", "").upper() if provider.get("key") != "openai" else ""
        previous_key = get_user_env_macos(env_name) if env_name else None
        cli = cli or find_codex_cli()
        cwd = cwd or os.getcwd()
        old_pids, quit_messages = quit_running_codex_app()

        ok, msgs = _switch_provider_locked(provider)
        if not ok:
            if old_pids:
                reopen_codex_app_best_effort(os.environ.copy())
            return False, quit_messages + msgs

        launch_env = os.environ.copy()
        launch_env["CODEX_HOME"] = DESKTOP_CODEX_DIR
        key = current_api_key(provider)
        if key and provider["key"] != "openai":
            launch_env[env_name] = key
            launch_env["OPENAI_API_KEY"] = key

        try:
            launch_messages = launch_fresh_codex_app(cli, cwd, launch_env, old_pids)
        except Exception as exc:
            rollback_errors = restore_snapshots(outer_snapshots)
            if env_name:
                try:
                    restore_keychain_secret(env_name, previous_key)
                except Exception as rollback_exc:
                    rollback_errors.append("macOS 钥匙串: %s" % rollback_exc)
            detail = "Codex 新 GUI 启动或验证失败，配置、认证、密钥与供应商状态已回滚：%s" % exc
            if old_pids:
                reopen_codex_app_best_effort(os.environ.copy())
            if rollback_errors:
                detail += "；部分回滚未完成：%s" % " | ".join(rollback_errors)
            return False, quit_messages + msgs + [detail]
        return True, quit_messages + msgs + launch_messages + ["✔ 新 Codex GUI 已加载当前中转站认证状态"]
    except Exception as exc:
        rollback_errors = restore_snapshots(outer_snapshots)
        if env_name:
            try:
                restore_keychain_secret(env_name, previous_key)
            except Exception as rollback_exc:
                rollback_errors.append("macOS 钥匙串: %s" % rollback_exc)
        if old_pids:
            reopen_codex_app_best_effort(os.environ.copy())
        detail = "切换失败，配置、认证、密钥与供应商状态已回滚：%s" % exc
        if rollback_errors:
            detail += "；部分回滚未完成：%s" % " | ".join(rollback_errors)
        return False, quit_messages + [detail]
    finally:
        SWITCH_LOCK.release()


def switch_gpt_account_flow(cli=None, cwd=None):
    """专用账号切换事务：双 config 切官方、logout、启动；失败完整回滚。"""
    if not SWITCH_LOCK.acquire(blocking=False):
        return False, ["已有切换或账号操作正在进行，请稍候"]
    try:
        return _switch_gpt_account_locked(cli or find_codex_cli(), cwd or os.getcwd())
    finally:
        SWITCH_LOCK.release()


def _switch_gpt_account_locked(cli, cwd):
    snapshots = {path: snapshot_file(path) for path in transaction_paths()}
    openai_provider = copy.deepcopy(next(
        (p for p in load_providers() if p.get("key") == "openai"), DEFAULT_PROVIDERS[2]
    ))
    env = os.environ.copy()
    env["CODEX_HOME"] = DESKTOP_CODEX_DIR
    messages = []
    old_pids = set()
    try:
        old_pids, quit_messages = quit_running_codex_app()
        messages.extend(quit_messages)

        for config_path, _label in config_targets():
            write_provider_to_target(openai_provider, config_path)
        providers = load_providers()
        for provider in providers:
            provider["active"] = provider.get("key") == "openai"
        save_providers(providers)

        result = subprocess.run(
            [cli, "logout"], capture_output=True, text=True, timeout=30, env=env,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "返回码 %d" % result.returncode).strip()
            raise RuntimeError("退出当前账号失败：%s" % detail)
        messages.append("已退出当前 Codex 登录账号")

        messages.extend(launch_fresh_codex_app(cli, cwd, env, old_pids))
        messages.append("✔ 全新 Codex GUI 已打开，请选择新的 GPT 账号登录")
        return True, messages
    except Exception as exc:
        rollback_errors = restore_snapshots(snapshots)
        if old_pids:
            reopen_codex_app_best_effort(env)
        if rollback_errors:
            return False, messages + ["切换账号失败，且部分回滚未完成：%s；%s" % (exc, " | ".join(rollback_errors))]
        return False, messages + ["切换账号失败，原 config/auth/providers 已恢复：%s" % exc]


def read_status():
    """返回 (provider_key, provider_name, model, valid, errors)。"""
    cfg = parse_toml(CONFIG_PATH)
    model = cfg.get("model", "")
    key = cfg.get("model_provider", "")
    name = ""
    valid = False
    errors = []

    if not key or not model:
        errors.append("config.toml 缺失 model 或 model_provider")
        return key, name, model, valid, errors

    if key == "openai":
        name = "OpenAI 官方"
        valid = True
        return key, name, model, valid, errors

    section = cfg.get("model_providers.%s" % key, {})
    if not section:
        errors.append("缺少 [model_providers.%s] 配置段" % key)
        return key, name, model, valid, errors

    name = section.get("name", key)
    base_url = section.get("base_url", "")
    for p in load_providers():
        if p["base_url"].rstrip("/") == base_url.rstrip("/"):
            name = p["name"]
            break

    env_key_name = section.get("env_key", "")
    has_env = bool(env_key_name and (os.environ.get(env_key_name) or get_user_env_macos(env_key_name)))
    if not has_env:
        errors.append("缺少 API Key（用户环境变量 %s 未设置）" % env_key_name)
    else:
        valid = True
    return key, name, model, valid, errors


def create_ssl_context():
    """使用随应用打包的 Mozilla CA，修复独立 macOS App 证书链缺失。"""
    ca_bundle = certifi.where()
    if not ca_bundle or not os.path.isfile(ca_bundle):
        raise RuntimeError("可信 CA 证书包不可用，请重新安装本工具")
    context = ssl.create_default_context(cafile=ca_bundle)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def fetch_models(base_url, api_key, timeout=20):
    """调用 GET {base}/models 拉取模型 ID 列表。"""
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer %s" % api_key})
    with urllib.request.urlopen(req, timeout=timeout, context=create_ssl_context()) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    ids = [m["id"] for m in data.get("data", []) if m.get("id")]
    return ids


def open_file_macos(path):
    """macOS 替代 os.startfile"""
    subprocess.Popen(["open", path])


# ============================ GUI ============================

class App:
    def __init__(self, root):
        self.root = root
        self.providers = load_providers()
        self.selected_key = None
        self.operation_active = False

        root.title("%s v%s" % (APP_NAME, APP_VERSION))
        root.geometry("860x620")
        root.minsize(780, 560)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        bg = "#f4f6f9"
        root.configure(bg=bg)
        style.configure("TFrame", background=bg)
        style.configure("Status.TLabel", background="#dbe7f5", foreground="#1f3a5f",
                        font=("Helvetica", 10))
        style.configure("Title.TLabel", font=("Helvetica", 13, "bold"),
                        foreground="#14304d", background=bg)
        style.configure("Sec.TLabel", font=("Helvetica", 10, "bold"),
                        foreground="#14304d", background=bg)
        style.configure("TLabel", background=bg, foreground="#222222",
                        font=("Helvetica", 9))
        style.configure("Accent.TButton", font=("Helvetica", 10, "bold"))

        self._build_ui()
        self.refresh_status()
        self.refresh_list()

    # ---------- UI ----------
    def _build_ui(self):
        # 顶部状态条
        top = tk.Frame(self.root, bg="#dbe7f5", pady=8)
        top.pack(fill="x", padx=10, pady=(10, 6))
        self.status_var = tk.StringVar(value="检测中...")
        tk.Label(top, textvariable=self.status_var, bg="#dbe7f5", fg="#1f3a5f",
                 font=("Helvetica", 10)).pack(side="left", padx=10)
        ttk.Button(top, text="刷新状态", command=self.refresh_status).pack(side="right", padx=10)
        self.path_var = tk.StringVar(value="配置目录: " + CODEX_DIR)
        tk.Label(top, textvariable=self.path_var, bg="#dbe7f5", fg="#3a5a80",
                 font=("Helvetica", 8)).pack(side="right", padx=10)

        main = tk.Frame(self.root, bg="#f4f6f9")
        main.pack(fill="both", expand=True, padx=10, pady=4)

        # ---- 左栏：供应商列表 ----
        left = tk.Frame(main, bg="#f4f6f9")
        left.pack(side="left", fill="y", padx=(0, 8))
        ttk.Label(left, text="供应商列表", style="Sec.TLabel").pack(anchor="w")
        self.listbox = tk.Listbox(left, width=22, height=16, font=("Helvetica", 10),
                                  activestyle="dotbox", selectbackground="#bcd6f0",
                                  selectforeground="#102a43", bg="white", bd=1, relief="solid")
        self.listbox.pack(fill="both", expand=True, pady=4)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        btnrow = tk.Frame(left, bg="#f4f6f9")
        btnrow.pack(fill="x")
        ttk.Button(btnrow, text="＋ 添加", command=self.add_provider).pack(side="left")
        ttk.Button(btnrow, text="－ 删除", command=self.delete_provider).pack(side="left", padx=6)

        # ---- 右栏：配置表单 ----
        right = tk.Frame(main, bg="#f4f6f9")
        right.pack(side="left", fill="both", expand=True)

        form = tk.LabelFrame(right, text=" 供应商配置 ", font=("Helvetica", 10, "bold"),
                             fg="#14304d", bg="#f4f6f9", bd=1, relief="solid", padx=12, pady=10)
        form.pack(fill="x")

        self.vars = {}
        rows = [
            ("name", "名称 *"),
            ("base_url", "API 地址 *"),
            ("api_key", "API Key"),
            ("model", "模型 *"),
        ]
        for i, (k, label) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=i, column=0, sticky="w", pady=4)
            var = tk.StringVar()
            self.vars[k] = var
            ent = ttk.Entry(form, textvariable=var, font=("Helvetica", 10))
            ent.grid(row=i, column=1, sticky="ew", pady=4, padx=6)
            if k == "api_key":
                ent.config(show="*")
                self.show_key = tk.BooleanVar(value=False)
                ttk.Checkbutton(form, text="显示", variable=self.show_key,
                                command=lambda: ent.config(show="" if self.show_key.get() else "*"),
                                style="Toolbutton").grid(row=i, column=2, padx=(0, 4))
            if k == "model":
                self.model_combo = ttk.Combobox(form, textvariable=var, font=("Helvetica", 10))
                self.model_combo.grid(row=i, column=1, sticky="ew", pady=4, padx=6)
                ttk.Button(form, text="读取模型", command=self.fetch_models_async).grid(row=i, column=2)

        ttk.Label(form, text="协议").grid(row=4, column=0, sticky="w", pady=4)
        self.wire_var = tk.StringVar(value=WIRE_RESPONSES)
        ttk.Radiobutton(form, text="Responses API", value=WIRE_RESPONSES,
                        variable=self.wire_var).grid(row=4, column=1, sticky="w")
        ttk.Radiobutton(form, text="Chat Completions (兼容)", value=WIRE_CHAT,
                        variable=self.wire_var).grid(row=4, column=2, sticky="w")
        form.columnconfigure(1, weight=1)

        # 主操作
        ops = tk.Frame(right, bg="#f4f6f9")
        ops.pack(fill="x", pady=8)
        ttk.Button(ops, text="⚡ 使用该中转站", style="Accent.TButton",
                   command=self.do_switch).pack(side="left")
        ttk.Button(ops, text="保存配置", command=self.save_current).pack(side="left", padx=8)
        ttk.Button(ops, text="切换 GPT 账号登录", command=self.switch_gpt_account).pack(side="left", padx=8)
        ttk.Button(ops, text="打开 config.toml", command=self.open_config).pack(side="left", padx=8)
        ttk.Button(ops, text="备份/恢复", command=self.manage_backups).pack(side="left", padx=8)

        # 日志区
        logframe = tk.LabelFrame(right, text=" 日志 ", font=("Helvetica", 10, "bold"),
                                 fg="#14304d", bg="#f4f6f9", bd=1, relief="solid")
        logframe.pack(fill="both", expand=True)
        self.log_text = tk.Text(logframe, height=8, font=("Menlo", 9), bg="#fbfcfe",
                                fg="#333333", bd=1, relief="solid", state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=6, pady=6)

    # ---------- 列表与表单 ----------
    def refresh_list(self):
        self.listbox.delete(0, "end")
        for p in self.providers:
            mark = "● " if p.get("active") else "   "
            self.listbox.insert("end", mark + p["name"])
        idx = next((i for i, p in enumerate(self.providers) if p.get("active")), 0)
        if self.providers:
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(idx)
            self.listbox.activate(idx)
            self.on_select()

    def current_provider(self):
        if self.selected_key is None and self.providers:
            self.selected_key = self.providers[0]["key"]
        return next((p for p in self.providers if p["key"] == self.selected_key), None)

    def on_select(self, event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        p = self.providers[sel[0]]
        self.selected_key = p["key"]
        self.vars["name"].set(p.get("name", ""))
        self.vars["base_url"].set(p.get("base_url", ""))
        saved_key = get_user_env_macos("%s_API_KEY" % p["key"].upper())
        self.vars["api_key"].set("********" if saved_key else "")
        self.wire_var.set(p.get("wire_api", WIRE_RESPONSES))
        models = p.get("models") or []
        self.model_combo["values"] = models
        self.vars["model"].set(p.get("model", models[0] if models else ""))

    def collect_current(self):
        p = self.current_provider()
        if not p:
            return None
        p["name"] = self.vars["name"].get().strip()
        p["base_url"] = self.vars["base_url"].get().strip()
        entered_key = self.vars["api_key"].get().strip()
        p["api_key"] = entered_key if entered_key and set(entered_key) != {"*"} else ""
        p["wire_api"] = self.wire_var.get()
        p["model"] = self.vars["model"].get().strip()
        models = list(self.model_combo["values"]) or []
        if p["model"] and p["model"] not in models:
            models.append(p["model"])
        p["models"] = models
        return p

    # ---------- 操作 ----------
    def on_close(self):
        if self.operation_active:
            messagebox.showwarning("操作进行中", "正在切换配置或认证，请等待完成后再关闭，避免事务被中断。")
            return
        self.root.destroy()

    def begin_operation(self):
        if self.operation_active:
            messagebox.showwarning("请稍候", "已有操作正在进行")
            return False
        self.operation_active = True
        return True

    def end_operation(self):
        self.operation_active = False

    def ensure_idle(self):
        if self.operation_active:
            messagebox.showwarning("请稍候", "已有操作正在进行")
            return False
        return True

    def do_switch(self):
        if not self.begin_operation():
            return
        p = self.collect_current()
        if not p:
            self.end_operation()
            messagebox.showwarning("提示", "请先选择供应商")
            return
        if not p["name"] or not p["base_url"] or not p["model"]:
            self.end_operation()
            messagebox.showwarning("提示", "名称、API 地址、模型均为必填")
            return
        operation_key = p["key"]
        self.log("正在同步中转站、建立第三方登录并打开 Codex...")
        threading.Thread(
            target=self._switch_worker, args=(copy.deepcopy(p), operation_key), daemon=True
        ).start()

    def _switch_worker(self, provider, operation_key):
        ok, msgs = switch_provider_and_launch(provider)
        self.root.after(0, lambda: self._switch_finished(ok, msgs, operation_key))

    def _switch_finished(self, ok, msgs, operation_key):
        self.end_operation()
        for msg in msgs:
            self.log(msg)
        if ok:
            for provider in self.providers:
                provider["active"] = provider["key"] == operation_key
                provider["api_key"] = ""
            self.log("✔ 中转站切换完成并已打开 Codex，第三方登录态已生效")
            self.log("API Key 已安全保存在 macOS 钥匙串")
            self.refresh_list()
            self.refresh_status()
        else:
            messagebox.showerror("切换失败", "\n".join(msgs))

    def save_current(self):
        if not self.ensure_idle():
            return
        p = self.collect_current()
        if not p:
            return
        if not p["name"] or not p["base_url"]:
            messagebox.showwarning("提示", "名称、API 地址必填")
            return
        api_key = str(p.get("api_key") or "").strip()
        env_name = "%s_API_KEY" % validate_provider_key(p["key"]).upper() if api_key else ""
        previous_key = get_user_env_macos(env_name) if env_name else None
        try:
            if api_key:
                set_user_env_macos(env_name, api_key)
            save_providers(self.providers)
            p["api_key"] = ""
            self.vars["api_key"].set("********" if current_api_key(p) else "")
        except Exception as exc:
            if env_name:
                try:
                    restore_keychain_secret(env_name, previous_key)
                except Exception as rollback_exc:
                    messagebox.showerror(
                        "保存失败",
                        "供应商配置未保存，且原 API Key 恢复失败：%s；%s" % (exc, rollback_exc),
                    )
                    return
            messagebox.showerror("保存失败", "供应商配置未保存，API Key 已恢复：%s" % exc)
            return
        self.log("已保存供应商「%s」配置%s" % (p["name"], "及 API Key" if api_key else ""))
        self.refresh_list()

    def add_provider(self):
        if not self.ensure_idle():
            return
        from tkinter import simpledialog
        name = simpledialog.askstring("添加供应商", "供应商名称（如 VAKV）：", parent=self.root)
        if not name:
            return
        name = name.strip()
        key = re_key(name)
        while any(p["key"] == key for p in self.providers):
            key += "_n"
        self.providers.append({
            "key": key, "name": name, "base_url": "https://api.openai.com/v1",
            "wire_api": WIRE_RESPONSES, "api_key": "",
            "models": [], "model": "", "active": False,
        })
        save_providers(self.providers)
        self.refresh_list()
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(len(self.providers) - 1)
        self.on_select()
        self.log("已添加供应商「%s」(key=%s)" % (name, key))

    def delete_provider(self):
        if not self.ensure_idle():
            return
        p = self.current_provider()
        if not p:
            return
        if not messagebox.askyesno("删除供应商", "确定删除「%s」吗？\n（不会影响已生成的配置文件）" % p["name"]):
            return
        self.providers = [x for x in self.providers if x["key"] != p["key"]]
        self.selected_key = self.providers[0]["key"] if self.providers else None
        save_providers(self.providers)
        self.refresh_list()
        self.log("已删除供应商「%s」" % p["name"])

    def fetch_models_async(self):
        if not self.begin_operation():
            return
        base = self.vars["base_url"].get().strip()
        entered = self.vars["api_key"].get().strip()
        provider = self.current_provider()
        provider_key = provider["key"] if provider else ""
        key = entered if entered and set(entered) != {"*"} else (
            current_api_key(provider) if provider else ""
        )
        if not base:
            self.end_operation()
            messagebox.showwarning("提示", "请先填写 API 地址")
            return
        self.log("正在拉取 %s/models ..." % base)
        threading.Thread(target=self._fetch_worker, args=(base, key, provider_key), daemon=True).start()

    def _fetch_worker(self, base, key, provider_key):
        try:
            ids = fetch_models(base, key)
        except urllib.error.HTTPError as e:
            message = "✘ 拉取失败 HTTP %s: %s" % (e.code, e.reason)
            self.root.after(0, lambda msg=message: self._fetch_failed(msg))
            return
        except Exception as e:
            message = "✘ 拉取失败: %s" % e
            self.root.after(0, lambda msg=message: self._fetch_failed(msg))
            return
        self.root.after(0, lambda: self._apply_models(ids, provider_key))

    def _fetch_failed(self, message):
        self.end_operation()
        self.log(message)

    def _apply_models(self, ids, provider_key):
        self.end_operation()
        p = next((item for item in self.providers if item["key"] == provider_key), None)
        if p:
            p["models"] = ids
            save_providers(self.providers)
        if self.selected_key != provider_key:
            self.log("✔ 已拉取 %d 个模型并保存到原供应商" % len(ids))
            return
        self.model_combo["values"] = ids
        if ids and not self.vars["model"].get():
            self.vars["model"].set(ids[0])
        self.log("✔ 拉取到 %d 个模型" % len(ids))

    def switch_gpt_account(self):
        """确认后后台执行专用账号切换事务；取消时不产生任何变化。"""
        if not messagebox.askyesno(
            "切换 GPT 账号登录",
            "将停用当前中转站并退出当前 Codex 登录账号，然后打开登录页面。\n\n是否继续？",
        ):
            return
        if not self.begin_operation():
            return
        self.log("正在切换 GPT 账号登录...")
        threading.Thread(target=self._switch_gpt_account_worker, daemon=True).start()

    def _switch_gpt_account_worker(self):
        ok, messages = switch_gpt_account_flow()
        self.root.after(0, lambda: self._account_switch_finished(ok, messages))

    def _account_switch_finished(self, ok, messages):
        self.end_operation()
        for message in messages:
            self.log(("✔ " if ok else "✘ ") + message)
        if ok:
            for provider in self.providers:
                provider["active"] = provider.get("key") == "openai"
            self.refresh_list()
            self.refresh_status()
        else:
            messagebox.showerror("切换账号失败", "\n".join(messages))

    def open_config(self):
        if not os.path.exists(CONFIG_PATH):
            messagebox.showwarning("提示", "config.toml 尚不存在，请先切换一次")
            return
        try:
            open_file_macos(CONFIG_PATH)
        except Exception as e:
            messagebox.showerror("打开失败", str(e))

    def manage_backups(self):
        if not self.ensure_idle():
            return
        if not os.path.isdir(BACKUP_DIR):
            messagebox.showinfo("备份", "暂无备份（切换供应商时会自动备份旧配置）")
            return
        files = sorted(os.listdir(BACKUP_DIR), reverse=True)
        if not files:
            messagebox.showinfo("备份", "暂无备份（切换供应商时会自动备份旧配置）")
            return
        win = tk.Toplevel(self.root)
        win.title("备份/恢复")
        win.geometry("460x320")
        lb = tk.Listbox(win, font=("Menlo", 9))
        lb.pack(fill="both", expand=True, padx=8, pady=8)
        for f in files:
            lb.insert("end", f)
        def restore():
            sel = lb.curselection()
            if not sel:
                return
            f = files[sel[0]]
            src = os.path.join(BACKUP_DIR, f)
            if messagebox.askyesno("恢复", "用 %s 覆盖当前 config.toml ？" % f):
                backup_config()
                shutil.copy2(src, CONFIG_PATH)
                self.log("已从备份恢复 %s" % f)
                self.refresh_status()
                win.destroy()
        def open_dir():
            open_file_macos(BACKUP_DIR)
        ttk.Button(win, text="恢复选中项", command=restore).pack(side="left", padx=8, pady=6)
        ttk.Button(win, text="打开备份文件夹", command=open_dir).pack(side="left", pady=6)

    # ---------- 状态 ----------
    def refresh_status(self):
        key, name, model, valid, errors = read_status()
        if valid:
            self.status_var.set("● 当前供应商: %s   |   模型: %s   |   配置: 有效" % (name, model))
        else:
            self.status_var.set("○ 当前配置: 未生效  (%s)" % ("; ".join(errors) if errors else "未配置"))
            self.log("状态: " + ("; ".join(errors) if errors else "当前未配置任何供应商"))

    def log(self, msg):
        self.log_text.config(state="normal")
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert("end", "[%s] %s\n" % (ts, msg))
        self.log_text.see("end")
        self.log_text.config(state="disabled")


def re_key(name):
    """由名称生成安全的 ASCII provider key。"""
    k = re.sub(r"[^a-z0-9_-]+", "-", str(name).lower()).strip("-_")
    if not k or not k[0].isalnum():
        k = "provider"
    return k[:64]


def main():
    if "--self-test-package" in sys.argv:
        expected_arch = os.environ.get("SUSU_EXPECT_ARCH", "")
        if expected_arch and platform.machine() != expected_arch:
            raise RuntimeError("构建架构不匹配：期望 %s，实际 %s" % (expected_arch, platform.machine()))
        if APP_VERSION != "1.22-macOS":
            raise RuntimeError("应用版本不是 V1.22 macOS")
        if sys.platform == "darwin":
            backend = keyring.get_keyring()
            backend_name = "%s.%s" % (backend.__class__.__module__, backend.__class__.__name__)
            if backend_name != "keyring.backends.macOS.Keyring":
                raise RuntimeError("macOS 钥匙串后端不可用：%s" % backend_name)
            bundled_cli = bundled_codex_cli_path()
            if not bundled_cli or not os.path.isfile(bundled_cli) or not os.access(bundled_cli, os.X_OK):
                raise RuntimeError("包内官方 Codex CLI 缺失或不可执行：%s" % bundled_cli)
        ssl_context = create_ssl_context()
        if ssl_context.verify_mode != ssl.CERT_REQUIRED or not ssl_context.check_hostname:
            raise RuntimeError("包内 TLS 证书验证未启用")
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        out = sys.argv[2] if len(sys.argv) > 2 else "selftest.txt"
        selftest(out)
        return
    if not acquire_single_instance_lock():
        activate_existing_instance()
        return
    root = tk.Tk()
    App(root)
    root.mainloop()


def selftest(out_path):
    lines = []
    def log(s):
        lines.append(str(s))
    log("配置目录: %s" % CODEX_DIR)
    log("配置文件: %s" % CONFIG_PATH)
    log("Shell Profile: %s" % get_shell_profile())
    providers = load_providers()
    log("[1] providers 加载: %d 个" % len(providers))
    for p in providers:
        log("    - %s (%s) model=%s" % (p["name"], p["base_url"], p.get("model")))
    vakv = next((p for p in providers if p["key"] == "vakv"), None)
    if not vakv:
        log("[2] FAIL: 未找到 vakv 供应商")
        return
    log("[2] 切换到 vakv ...")
    ok, msgs = switch_provider(vakv)
    for m in msgs:
        log("    " + m)
    log("[3] config.toml 内容:")
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            for ln in f.read().splitlines():
                log("    | " + ln)
    else:
        log("    FAIL: config.toml 不存在")
    log("[4] auth.json 内容:")
    if os.path.exists(AUTH_PATH):
        with open(AUTH_PATH, "r", encoding="utf-8") as f:
            log("    | " + f.read().strip())
    else:
        log("    (auth.json 不存在)")
    key, name, model, valid, errors = read_status()
    log("[5] 状态读取: provider=%s name=%s model=%s valid=%s errors=%s"
        % (key, name, model, valid, errors))
    log("[6] 模型在线拉取测试 (vakv):")
    try:
        ids = fetch_models("https://api.vakv.cn/v1", vakv["api_key"])
        log("    成功，共 %d 个模型，包含 gpt-5.6-terra: %s"
            % (len(ids), "gpt-5.6-terra" in ids))
    except Exception as e:
        log("    FAIL: %s" % e)
    log("=== SELFTEST DONE ===")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
