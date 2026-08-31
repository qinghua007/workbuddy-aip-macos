# Mac 本地开发环境报告

任务编号：`TASK-20260831-172058`

## 状态

`PARTIAL`

项目本地环境已完成部署、测试、构建和启动冒烟；GitHub CLI 已登录，部署分支已发布并创建 PR，但测试服和正式服链路尚未执行，因此不能宣称端到端发布链已完成。

## 推荐结论

当前项目是 Python/Tkinter 单体桌面程序，不需要 Node、Java、PHP、Go、Rust、Docker、数据库、Redis 或消息队列。推荐保持：

```text
Mac 原生 Python/Tkinter
+ 项目独立 .venv
+ GitHub main
+ 每个任务独立 Branch/Worktree
+ GitHub Actions 负责 macOS 构建
```

本机为 Intel Mac，不使用 Rosetta。macOS 应用本地产物只用于 Intel 本地验证；不要将 macOS 二进制上传到 Linux 测试服或正式服。

## Mac

| 项目 | 实际值 |
| --- | --- |
| macOS | 26.6，Build 25G72 |
| CPU | MacBookPro16,1，Intel Core i9-9880H |
| 架构 | `x86_64` |
| Shell | `/bin/zsh` |
| 内存 | 16 GiB |
| 项目磁盘 | 932 GiB，总可用约 723 GiB |
| Xcode CLT | `/Library/Developer/CommandLineTools` |

## 已安装或可用

| 工具 | 版本/路径 | 状态 |
| --- | --- | --- |
| Git | Apple Git 2.50.1，`/usr/bin/git` | PASS |
| Python | 3.13.12，managed runtime | PASS |
| Node.js | 22.22.2，managed runtime | 可用但项目不需要 |
| npm | 10.9.7，managed runtime | 可用但项目不需要 |
| WorkBuddy | `/Applications/WorkBuddy.app` | PASS |
| Google Chrome | `/Applications/Google Chrome.app` | PASS |
| Xcode CLT | `/Library/Developer/CommandLineTools` | PASS |
| curl | `/usr/bin/curl` | PASS |
| SSH | OpenSSH 10.3p1 | PASS |
| Tkinter | 9.0 | PASS |
| certifi | `.venv` 内安装 | PASS |
| Pillow | `.venv` 内安装 | PASS |
| PyInstaller | `.venv` 内安装，6.22.2 | PASS |

## 未安装或当前不需要

- Homebrew：当前未安装。已尝试官方安装脚本；普通会话无 `sudo` 权限，提升权限重试又遭遇网络空响应，因此需要管理员终端和稳定网络人工完成。Intel Mac 官方前缀应为 `/usr/local`。
- GitHub CLI：已安装，`gh 2.98.0`，路径 `/Users/mac/.local/bin/gh`；当前未登录 GitHub。需要人工执行 `gh auth login` 完成第三方授权，不要在对话中提供密码、Token 或验证码。
- Git LFS：未安装；仓库当前无 LFS 文件。
- SVN：未安装；SVN 不是当前 GitHub 主开发链。
- Docker / Docker Compose：未安装；仓库没有 Dockerfile 或 Compose 配置，也无本地基础服务。
- pnpm / yarn / fnm / nvm / uv：未安装；仓库没有 Node 或 uv 项目配置。
- Java / Maven / Gradle / PHP / Composer / Go / Rust：未安装；仓库无对应技术栈。
- jq / ripgrep / fd / wget / mkcert：未安装；当前项目测试和构建不需要。
- VS Code：未发现；WorkBuddy 是主要执行工具。

## 项目

- GitHub 业务仓库：`https://github.com/qinghua007/workbuddy-aip-macos.git`
- 本地主仓库：`/Users/mac/Projects/workbuddy-aip-macos`
- 主分支：`main`
- 当前主分支 Commit：`3dc581fd8bbb2b165c9b05aeec8aeabc4d990e99`
- Worktree 根目录：`/Users/mac/Projects/susu-worktrees`
- 当前部署 Worktree：`/Users/mac/Projects/susu-worktrees/macos-dev-environment-TASK-20260831-172058`
- 当前部署分支：`chore/macos-dev-environment-TASK-20260831-172058`
- 部署分支最新本地提交：`0840f84`；远端 PR 分支最新提交：`faf672c`

## 本地环境

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 前端 | NOT APPLICABLE | Tkinter 桌面 GUI，不是 Web 前端 |
| 后端 | NOT APPLICABLE | 无独立后端服务 |
| 数据库 | NOT REQUIRED | 使用本机 JSON 配置 |
| Redis | NOT REQUIRED | 仓库无 Redis 依赖 |
| API | PASS | TLS 回归测试覆盖 `/models` 请求和重定向安全逻辑 |
| 页面/GUI | PARTIAL | GUI 进程已启动并存活；当前受限会话未做人工窗口操作 |
| 构建 | PASS | PyInstaller Intel `.app` 构建成功，架构 `x86_64` |
| 测试 | PASS | Python 语法检查和 TLS 回归测试通过 |

## 命令

```bash
./scripts/setup-macos.sh
./scripts/test-local.sh
./scripts/dev-local.sh
./scripts/stop-local.sh
./scripts/build-macos.sh
```

脚本位于当前部署 Worktree 的 `scripts/`。初始化会创建仓库内 `.venv` 并安装 `certifi`、`Pillow`、`PyInstaller`。本地运行日志和 PID 位于 `.local/`，不提交到 Git。

Intel 构建产物：

```text
dist-intel-local/WorkBuddy第三方AIP对接工具-Intel芯片.app
```

## Git 工作流

```text
Mac Worktree
→ 独立 Branch
→ 本地测试/构建
→ Push Branch
→ PR
→ main
→ CI
→ 测试服
→ 测试服验收
→ 正式服
```

当前部署分支已通过 GitHub 官方 Git 数据 API 发布并创建 PR。不得直接修改 `main`、测试服或正式服。

## 测试服与正式服

- 测试服链路：`PARTIAL`。GitHub 分支与 PR 已就绪；尚未合并 PR 或执行测试服部署。
- 正式服链路：`PARTIAL`。本轮未连接或修改正式服；必须在测试服验收同一 Git Commit/Release 后再发布。
- GitHub CLI `gh 2.98.0` 已登录 `qinghua007`，认证由系统钥匙串管理，GitHub Token scope 包含 `repo`。已通过 GitHub API 发布部署分支并创建 PR：<https://github.com/qinghua007/workbuddy-aip-macos/pull/2>。PR 当前为 `OPEN`，base 为 `main`，merge state 为 `CLEAN`，暂无失败检查项。Git 的 HTTPS Push 仍受本机代理隧道 `502` 影响，因此本次分支发布使用已登录 CLI 的官方 Git 数据 API 完成；未修改 `main`。

## ECS 只读盘点（2026-08-31）

已通过一次性 SSH 密码提示完成两台 ECS 的只读检查；密码未写入文件、命令参数、日志或提交。服务器未执行安装、重启、发布、删除、源码修改或数据库写操作。

| 环境 | 公网 IP | 系统 | 关键运行状态 | 公开监听端口 |
| --- | --- | --- | --- | --- |
| 开发版服 | `47.104.68.59` | CentOS 8 | `mysqld.service` 运行；`php-fpm-72.service`、`redis.service` 失败 | `21`、`22`、`80`、`443`、`888`、`8888`、`1818`、`3306` |
| 正式服 | `118.190.106.133` | CentOS 7 | Docker、Nginx、Hermes API/CRUD、new-token-api、`susu-codex-task-staging` 均运行 | `22`、`80`、`443`、`888`、`8888`、`1818`、`1238`、`7272` |

正式服发现 3 个已不存在的 Hermes staging systemd 单元残留，以及 cloud-init 失败单元；这些仅记录，未清理。正式服 `/opt/hermes/current` 当前指向 `/opt/hermes-prod/releases/SUSU-COMMON-20260806-025-r123`。开发服存在 `/opt/hermes`，本次未发现可确认的发布指针。检查未读取 `.env`、密钥、业务配置内容或数据库数据。

本机已配置不含凭据的 SSH 别名：

```text
ssh susu-dev-ecs
ssh susu-prod-ecs
```

配置文件：`~/.ssh/config`。后续使用别名连接时仍需在终端输入密码，或改用已授权的 SSH 公钥。

## Mac 兼容问题

已经修复：

- managed Python 虚拟环境缺少 Tcl/Tk 资源搜索路径，导致 `tkinter.Tk()` 找不到 `init.tcl`。`dev-local.sh` 现会动态设置 `TCL_LIBRARY` 和 `TK_LIBRARY`。
- 构建产物验证已加入架构、TLS、Info.plist 和临时签名检查。

仍存在：

- 当前会话无法进行人工 GUI 交互验收。
- PyInstaller 6.22.2 对 `onefile + windowed .app` 发出弃用提示，未来升级到 v7 前建议迁移 `onedir`。
- 主仓库 README 仍保留 `%USERPROFILE%` Windows 文案；源码运行时通过 `os.path.expanduser("~")` 已跨平台，文档可后续单独补充 macOS 路径说明。

## 凭据要求

API Key 由应用在本机配置中管理，不写入仓库。禁止把真实 Token、Cookie、私钥、密码或生产配置复制到 Mac、日志、Commit、Issue 或 Release。测试和生产凭据必须分离。

## 验收记录

- `bash -n scripts/*.sh`：通过
- `./scripts/test-local.sh`：通过，输出 `SSL_REGRESSION_OK`、`LOCAL_TESTS_OK`
- `./scripts/build-macos.sh`：通过，输出 `MACOS_BUILD_OK`，架构 `x86_64`
- `./scripts/dev-local.sh`：启动成功，进程存活检查通过
- `./scripts/stop-local.sh`：停止成功，重复执行返回 `Not running`
- 部署 Worktree：提交后干净
- 主业务仓库：`main` 保持干净
