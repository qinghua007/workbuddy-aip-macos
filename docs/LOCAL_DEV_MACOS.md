# macOS 本地开发说明

## 适用范围

本说明面向从 GitHub `main` 检出的 macOS 本地开发环境。当前项目是 Python/Tkinter 桌面程序，Intel Mac 使用 `x86_64` 构建目标。脚本只操作当前仓库和用户目录下的 `.workbuddy/workbuddy-aip` 数据，不连接测试服或正式服。

## 前置条件

- macOS 13 或更高版本
- Intel Mac（`x86_64`）用于本地 Intel 打包
- Python 3，且该 Python 可导入 `tkinter`
- Xcode Command Line Tools
- 可访问 PyPI 的网络，用于首次安装依赖

当前源码不包含 `.env` 配置，也不要求把 API Key 写入仓库。API Key 由应用运行时在本机配置文件中管理，禁止提交到 Git。

## 初始化环境

在仓库根目录执行：

```bash
./scripts/setup-macos.sh
```

默认创建 `.venv`，安装并验证：

- `certifi`：严格 HTTPS 请求的 Mozilla CA bundle
- `Pillow`：生成 macOS 图标
- `PyInstaller`：构建 `.app`

可用 `PYTHON_BIN` 或 `VENV_DIR` 覆盖默认路径，例如：

```bash
PYTHON_BIN=/path/to/python3 VENV_DIR=/tmp/workbuddy-venv ./scripts/setup-macos.sh
```

## 测试

```bash
./scripts/test-local.sh
```

该命令执行 Python 语法检查和 TLS 回归测试，预期输出包含：

```text
SSL_REGRESSION_OK
LOCAL_TESTS_OK
```

## 启动与停止

```bash
./scripts/dev-local.sh
./scripts/stop-local.sh
```

启动脚本把 PID 和日志放在未跟踪目录 `.local/`：

```text
.local/workbuddy-aip.pid
.local/workbuddy-aip.log
```

应用启动后会显示 Tkinter GUI。若当前会话没有可用的窗口显示环境，启动检查只能确认进程是否存活；应在有桌面会话的 Mac 上进行界面验收。

## 构建 Intel macOS 应用

```bash
./scripts/build-macos.sh
```

构建过程会生成图标、PyInstaller `.app`、临时构建目录，并验证：

- 应用包和 `Info.plist` 存在
- Mach-O 架构为 `x86_64`
- TLS 自检通过
- `Info.plist` 格式正确
- 临时签名验证通过

本地产物位于 `dist-intel-local/`，构建中间文件位于 `build-intel-local/`，均不会提交到 Git。

## 清理与凭据边界

本地构建产物可以直接删除；不要删除用户的 `~/.workbuddy` 数据。不要把真实 API Key、Cookie、Token、私钥或认证文件复制到仓库、日志、Issue、Commit 或 Release。提交前检查：

```bash
git status --short
git diff --check
git grep -n -I -E 'sk-[A-Za-z0-9]|Bearer[[:space:]]+[A-Za-z0-9._-]+' -- ':!docs/LOCAL_DEV_MACOS.md' || true
```
