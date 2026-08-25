#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codex Provider Switcher v1.4 — macOS Edition
Codex 供应商切换器 macOS 版本
支持读取模型、使用中转站和切换 GPT 账号登录。
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from tkinter import messagebox, ttk

APP_NAME = "苏苏全能中转站一键切换"
APP_VERSION = "1.4-macOS"

# ---------------- 真实配置目录（CODEX_HOME 优先，回退 ~/.codex） ----------------
def resolve_codex_dir():
    home = os.environ.get("CODEX_HOME") or ""
    if home and os.path.isdir(home):
        return home
    return os.path.join(os.path.expanduser("~"), ".codex")


CODEX_DIR = resolve_codex_dir()
CONFIG_PATH = os.path.join(CODEX_DIR, "config.toml")
AUTH_PATH = os.path.join(CODEX_DIR, "auth.json")
SW_DIR = os.path.join(CODEX_DIR, "provider-switcher")
PROVIDERS_FILE = os.path.join(SW_DIR, "providers.json")
BACKUP_DIR = os.path.join(SW_DIR, "backups")

WIRE_RESPONSES = "responses"
WIRE_CHAT = "chat_completions"

# ---------------- macOS shell profile for env vars ----------------
def get_shell_profile():
    """Return the shell profile path for setting environment variables."""
    home = os.path.expanduser("~")
    # Prefer .zshrc (default on macOS since Catalina)
    zshrc = os.path.join(home, ".zshrc")
    bash_profile = os.path.join(home, ".bash_profile")
    if os.path.exists(zshrc) or os.environ.get("SHELL", "").endswith("zsh"):
        return zshrc
    return bash_profile


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

def load_providers():
    """加载供应商列表；优先真实目录，其次迁移旧位置。"""
    if os.path.exists(PROVIDERS_FILE):
        try:
            with open(PROVIDERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
    os.makedirs(SW_DIR, exist_ok=True)
    with open(PROVIDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_PROVIDERS, f, ensure_ascii=False, indent=2)
    return json.loads(json.dumps(DEFAULT_PROVIDERS, ensure_ascii=False))


def save_providers(providers):
    os.makedirs(SW_DIR, exist_ok=True)
    with open(PROVIDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(providers, f, ensure_ascii=False, indent=2)


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


def build_config_text(provider, existing_config=""):
    """生成 config.toml 内容（AIVR 风格）：
    model_provider = <key>；自定义供应商写 [model_providers.<key>]（env_key 方式）；
    保留现有所有原生配置（desktop/projects/plugins/mcp_servers/marketplaces 等）。"""
    preserved = []
    in_provider_section = False
    if existing_config:
        for line in existing_config.splitlines():
            stripped = line.strip()
            if (stripped.startswith("model_provider") or stripped.startswith("model =")
                    or stripped.startswith("disable_response_storage")
                    or stripped.startswith("model_context_window")
                    or stripped.startswith("model_auto_compact_token_limit")):
                continue
            if stripped.startswith("[model_providers"):
                in_provider_section = True
                continue
            if in_provider_section and stripped.startswith("[") and not stripped.startswith("[model_providers"):
                in_provider_section = False
            if in_provider_section:
                continue
            preserved.append(line)

    header = [
        'model_provider = "%s"' % provider["key"],
        'model = "%s"' % provider["model"],
    ]
    if provider["key"] != "openai":
        header += [
            "",
            "[model_providers.%s]" % provider["key"],
            'name = "%s"' % provider["name"],
            'base_url = "%s"' % provider["base_url"].rstrip("/"),
            'wire_api = "%s"' % provider["wire_api"],
            'env_key = "%s_API_KEY"' % provider["key"].upper(),
            "",
        ]

    if preserved:
        while preserved and preserved[0] == "":
            preserved.pop(0)
        while preserved and preserved[-1] == "":
            preserved.pop()
        return "\n".join(header + preserved) + "\n"
    else:
        return "\n".join(header + [
            "",
            "[features]",
            "goals = true",
            "",
        ])


def backup_config():
    """切换前备份现有 config.toml，返回备份路径或 None。"""
    if not os.path.exists(CONFIG_PATH):
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(BACKUP_DIR, "config-%s.toml" % ts)
    shutil.copy2(CONFIG_PATH, dst)
    return dst


def set_user_env_macos(name, value):
    """写入用户级环境变量到 shell profile（~/.zshrc 或 ~/.bash_profile）。
    macOS 没有 Windows 注册表那样的用户级环境变量机制，
    需要写入 shell profile 文件。"""
    if not value:
        return
    profile = get_shell_profile()
    marker_begin = "# >>> Codex Provider Switcher: %s >>>" % name
    marker_end = "# <<< Codex Provider Switcher: %s <<<" % name

    # Read existing content
    content = ""
    if os.path.exists(profile):
        try:
            with open(profile, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            content = ""

    # Remove old entry
    lines = content.splitlines()
    new_lines = []
    skipping = False
    for line in lines:
        if marker_begin in line:
            skipping = True
            continue
        if marker_end in line:
            skipping = False
            continue
        if not skipping:
            new_lines.append(line)

    # Add new entry
    export_line = 'export %s="%s"' % (name, value)
    new_lines.append("")
    new_lines.append(marker_begin)
    new_lines.append(export_line)
    new_lines.append(marker_end)

    try:
        with open(profile, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines) + "\n")
    except Exception as e:
        print("Failed to write shell profile: %s" % e)


def get_user_env_macos(name):
    """从 shell profile 读取环境变量值。"""
    profile = get_shell_profile()
    if not os.path.exists(profile):
        return None
    try:
        with open(profile, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.startswith("export %s=" % name):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    return val if val else None
    except Exception:
        pass
    # Also check current process env (may be set in current session)
    return os.environ.get(name)


def find_codex_cli():
    """定位 codex CLI：CODEX_CLI_PATH 环境变量 -> 常见安装路径 -> PATH。"""
    p = os.environ.get("CODEX_CLI_PATH") or ""
    if p and os.path.isfile(p):
        return p
    # macOS Homebrew path
    brew_paths = [
        "/usr/local/bin/codex",   # Intel Homebrew
        "/opt/homebrew/bin/codex", # Apple Silicon Homebrew
    ]
    for p in brew_paths:
        if os.path.isfile(p):
            return p
    # npm global
    npm_prefix = os.path.expanduser("~/.npm-global/bin/codex")
    if os.path.isfile(npm_prefix):
        return npm_prefix
    # PATH search
    for d in os.environ.get("PATH", "").split(os.pathsep):
        cand = os.path.join(d, "codex")
        if os.path.isfile(cand):
            return cand
    return "codex"


def write_auth(api_key):
    """合并写入 auth.json 的 OPENAI_API_KEY（保留已有登录 token 等字段）。"""
    if not api_key:
        return
    auth = {}
    if os.path.exists(AUTH_PATH):
        try:
            with open(AUTH_PATH, "r", encoding="utf-8") as f:
                auth = json.load(f)
        except Exception:
            auth = {}
    auth["OPENAI_API_KEY"] = api_key
    with open(AUTH_PATH, "w", encoding="utf-8") as f:
        json.dump(auth, f, indent=2, ensure_ascii=False)


def switch_provider(provider):
    """核心切换：备份 -> 写 config.toml -> 环境变量；保留第三方登录态。"""
    msgs = []
    if not provider.get("model"):
        return False, ["未选择模型，无法切换"]

    # 1. 备份
    bak = backup_config()
    if bak:
        msgs.append("已备份旧配置 -> %s" % os.path.basename(bak))
    else:
        msgs.append("无旧配置，跳过备份")

    # 2. 写 config.toml
    existing = ""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                existing = f.read()
        except Exception:
            pass
    os.makedirs(CODEX_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(build_config_text(provider, existing))
    msgs.append("config.toml 已写入 (provider=%s, model=%s) -> %s"
                % (provider["key"], provider["model"], CONFIG_PATH))

    # 3. API Key 写入 shell profile 环境变量
    env_name = "%s_API_KEY" % provider["key"].upper()
    if provider.get("api_key"):
        set_user_env_macos(env_name, provider["api_key"])
        msgs.append("环境变量 %s 已写入 %s" % (env_name, os.path.basename(get_shell_profile())))
    else:
        cur = get_user_env_macos(env_name)
        if cur:
            msgs.append("沿用已有环境变量 %s" % env_name)
        else:
            msgs.append("注意：%s 未设置，请在表单填写 API Key 后重新切换" % env_name)

    # 4. auth.json
    write_auth(provider.get("api_key") or "")
    msgs.append("auth.json 已处理")

    # 5. 记忆当前选择
    providers = load_providers()
    for p in providers:
        p["active"] = (p["key"] == provider["key"])
    save_providers(providers)

    # 使用中转站时禁止 logout，否则会删除刚建立的第三方登录态。
    msgs.append("已保留第三方登录态（未执行 codex logout）")
    return True, msgs


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
    auth_ok = False
    if os.path.exists(AUTH_PATH):
        try:
            with open(AUTH_PATH, "r", encoding="utf-8") as f:
                auth = json.load(f)
            auth_ok = bool(auth.get("OPENAI_API_KEY"))
        except Exception:
            pass
    if not (has_env or auth_ok):
        errors.append("缺少 API Key（环境变量 %s / auth.json 均未设置）" % env_key_name)
    else:
        valid = True
    return key, name, model, valid, errors


def fetch_models(base_url, api_key, timeout=20):
    """调用 GET {base}/models 拉取模型 ID 列表。"""
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer %s" % api_key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
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

        root.title("%s v%s" % (APP_NAME, APP_VERSION))
        root.geometry("860x620")
        root.minsize(780, 560)

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
        self.vars["api_key"].set(p.get("api_key", ""))
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
        p["api_key"] = self.vars["api_key"].get().strip()
        p["wire_api"] = self.wire_var.get()
        p["model"] = self.vars["model"].get().strip()
        models = list(self.model_combo["values"]) or []
        if p["model"] and p["model"] not in models:
            models.append(p["model"])
        p["models"] = models
        return p

    # ---------- 操作 ----------
    def do_switch(self):
        p = self.collect_current()
        if not p:
            messagebox.showwarning("提示", "请先选择供应商")
            return
        if not p["name"] or not p["base_url"] or not p["model"]:
            messagebox.showwarning("提示", "名称、API 地址、模型均为必填")
            return
        ok, msgs = switch_provider(p)
        save_providers(self.providers)
        for m in msgs:
            self.log(m)
        if ok:
            self.log("✔ 切换完成！请完全退出并重新打开 Codex 桌面端")
            self.log("⚠️ 新终端需 source ~/.zshrc 或重开终端才能生效环境变量")
            self.refresh_list()
            self.refresh_status()
        else:
            messagebox.showerror("切换失败", "\n".join(msgs))

    def save_current(self):
        p = self.collect_current()
        if not p:
            return
        if not p["name"] or not p["base_url"]:
            messagebox.showwarning("提示", "名称、API 地址必填")
            return
        save_providers(self.providers)
        self.log("已保存供应商「%s」配置" % p["name"])
        self.refresh_list()

    def add_provider(self):
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
        base = self.vars["base_url"].get().strip()
        key = self.vars["api_key"].get().strip()
        if not base:
            messagebox.showwarning("提示", "请先填写 API 地址")
            return
        self.log("正在拉取 %s/models ..." % base)
        threading.Thread(target=self._fetch_worker, args=(base, key), daemon=True).start()

    def _fetch_worker(self, base, key):
        try:
            ids = fetch_models(base, key)
        except urllib.error.HTTPError as e:
            self.log("✘ 拉取失败 HTTP %s: %s" % (e.code, e.reason))
            return
        except Exception as e:
            self.log("✘ 拉取失败: %s" % e)
            return
        self.root.after(0, lambda: self._apply_models(ids))

    def _apply_models(self, ids):
        self.model_combo["values"] = ids
        p = self.current_provider()
        if p:
            p["models"] = ids
            save_providers(self.providers)
        if ids and not self.vars["model"].get():
            self.vars["model"].set(ids[0])
        self.log("✔ 拉取到 %d 个模型" % len(ids))

    def switch_gpt_account(self):
        """退出当前 Codex 登录态并打开登录页面，让用户选择新的 GPT 账号。"""
        if not messagebox.askyesno(
            "切换 GPT 账号登录",
            "将停用当前中转站并退出当前 Codex 登录账号，然后打开登录页面。\n\n是否继续？",
        ):
            return
        self.log("正在切换 GPT 账号登录...")
        threading.Thread(target=self._switch_gpt_account_worker, daemon=True).start()

    def _switch_gpt_account_worker(self):
        cli = find_codex_cli()
        try:
            openai_provider = next(
                (dict(p) for p in self.providers if p.get("key") == "openai"),
                dict(DEFAULT_PROVIDERS[2]),
            )
            existing = ""
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    existing = f.read()
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write(build_config_text(openai_provider, existing))
            result = subprocess.run([cli, "logout"], capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "返回码 %d" % result.returncode).strip()
                raise RuntimeError("退出当前账号失败：%s" % detail)
            launched = False
            try:
                app_result = subprocess.run(
                    [cli, "app", os.getcwd()], capture_output=True, text=True, timeout=20
                )
                launched = app_result.returncode == 0
            except Exception:
                launched = False
            if not launched:
                subprocess.Popen(["open", "-a", "Codex"])
            self.root.after(0, lambda: self._account_switch_finished())
        except Exception as exc:
            error_text = str(exc)
            self.root.after(0, lambda msg=error_text: messagebox.showerror("切换账号失败", msg))

    def _account_switch_finished(self):
        self.log("✔ 已退出当前账号并打开 Codex，请选择新的 GPT 账号登录")
        self.refresh_status()

    def open_config(self):
        if not os.path.exists(CONFIG_PATH):
            messagebox.showwarning("提示", "config.toml 尚不存在，请先切换一次")
            return
        try:
            open_file_macos(CONFIG_PATH)
        except Exception as e:
            messagebox.showerror("打开失败", str(e))

    def manage_backups(self):
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
    """由名称生成 key（小写 ascii，失败则用 provider）。"""
    k = "".join(c for c in name.lower() if c.isalnum() or c in "-_")
    return k or "provider"


def main():
    if "--self-test-package" in sys.argv:
        expected_arch = os.environ.get("SUSU_EXPECT_ARCH", "")
        if expected_arch and platform.machine() != expected_arch:
            raise RuntimeError("构建架构不匹配：期望 %s，实际 %s" % (expected_arch, platform.machine()))
        if APP_VERSION != "1.4-macOS":
            raise RuntimeError("应用版本不是 v1.4 macOS")
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        out = sys.argv[2] if len(sys.argv) > 2 else "selftest.txt"
        selftest(out)
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
