# macOS 本地开发指南

本指南用于在 Intel Mac 上从 GitHub 的 `main` 创建可重复的本地开发环境。当前仓库是 Python/Tkinter 桌面应用，不需要 Docker、Node、PHP、Composer、Homebrew 或 Windows SVN 工作副本。

## 前置条件

- macOS 13 或更高版本
- Intel `x86_64` Mac
- Xcode Command Line Tools（提供 `git`、`make`、`codesign`、`iconutil`）
- Python 3.9 或更高版本，并包含 Tkinter
- 可访问 Python 包索引，用于安装 `certifi`、`Pillow` 和 `PyInstaller`

项目脚本会优先使用 WorkBuddy 管理的 Python：
`/Users/mac/.workbuddy/binaries/python/versions/3.13.12/bin/python3`。
没有该路径时会回退到 `python3`。依赖安装在用户目录的隔离虚拟环境中，不写入系统 Python。

## 首次部署

从一个全新的 Clone 创建任务分支和 Worktree：

```sh
git clone --origin github https://github.com/qinghua007/workbuddy-aip-macos.git ~/Projects/susu-github-TASK_ID
git -C ~/Projects/susu-github-TASK_ID branch chore/macos-dev-environment-TASK_ID main
git -C ~/Projects/susu-github-TASK_ID worktree add ~/Projects/susu-worktrees/macos-dev-environment-TASK_ID chore/macos-dev-environment-TASK_ID
cd ~/Projects/susu-worktrees/macos-dev-environment-TASK_ID
```

确认分支从确定的 `main` SHA 创建后，再执行：

```sh
./scripts/setup-macos.sh
```

脚本默认创建：
`~/.workbuddy/binaries/python/envs/workbuddy-aip-macos`。

也可以显式指定 Python 和虚拟环境路径：

```sh
PYTHON_BIN=/path/to/python3 WORKBUDDY_AIP_VENV=/path/to/venv ./scripts/setup-macos.sh
```

## 测试、构建与启动

运行无界面回归测试：

```sh
./scripts/test-local.sh
```

该命令执行 Python 编译检查、严格 TLS 回归测试、Tkinter 导入检查和 certifi CA 包检查。它不会访问任何供应商 API，也不会要求 API Key。

在当前 Mac 上启动真实 GUI 并验证进程保持运行至少 5 秒：

```sh
./scripts/dev-local.sh
```

运行目录和日志默认位于 `${TMPDIR}/workbuddy-aip-macos-${USER}`。检查日志：

```sh
tail -n 50 "${TMPDIR}/workbuddy-aip-macos-${USER}/app.log"
```

停止当前 Worktree 启动的应用：

```sh
./scripts/stop-local.sh
```

Intel 本机构建：

```sh
./scripts/build-local.sh
```

构建输出位于 `dist-local/WorkBuddy第三方AIP对接工具-Intel芯片.app`。脚本会生成图标、使用 PyInstaller 打包、校验 `x86_64`、运行内置 TLS self-test，并执行临时签名和签名验证。构建目录和图标均被 `.gitignore` 忽略。

## 运行时数据与凭据

应用运行时数据写入用户目录：

- `~/.workbuddy/workbuddy-aip/providers.json`
- `~/.workbuddy/workbuddy-aip/backups/`
- `~/.workbuddy/workbuddy-aip/exports/`
- `~/.workbuddy/models.json`

这些文件不属于源码，不得加入 Git、日志、Issue、PR 或构建产物。`.env.example` 只包含非敏感配置示例；不要创建包含 API Key 的 `.env` 并提交。

## 故障排查

- `Python environment is missing`：先运行 `./scripts/setup-macos.sh`，或设置 `PYTHON_BIN` / `WORKBUDDY_AIP_VENV`。
- `ModuleNotFoundError: certifi`：确认使用的是虚拟环境中的 Python，不要直接调用系统 Python。
- `This build script is for Intel x86_64 macOS`：M 芯片机器应使用 CI 的 Apple Silicon 构建，不要在本脚本中交叉替代。
- GUI 启动后立即退出：查看 `app.log`，并确认当前用户会话允许 Tk 窗口显示；无图形会话时只能运行无界面测试和构建检查。
- macOS 首次打开交付的未公证 App 被拦截：按照对应 Intel 交付说明使用 Finder 的“打开”或修复脚本。本地开发启动不需要复制或修改已验收交付包。

## 提交前检查

```sh
git status --short --branch
git diff --check
./scripts/test-local.sh
git diff --stat
```

开发分支必须通过审查和 PR 流程后才能合并。不要直接修改或推送 `main`，不要从 SVN、测试服或正式服覆盖源码。
