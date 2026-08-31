# WorkBuddy 第三方 AIP 对接工具 v1.2

本项目提供一个本地桌面配置管理器，用于管理 WorkBuddy 可使用的 OpenAI-compatible 第三方 AI API 参数。

## 三个平台

- Windows
- macOS Apple Silicon（M 芯片）
- macOS Intel

## 批量导入到 WorkBuddy

通过当前 WorkBuddy 安装实际使用的 `%USERPROFILE%\.workbuddy\models.json` 格式，工具在拉取供应商 `/models` 后可以一键导入全部模型：按模型 ID 去重，同 ID 更新为当前供应商地址和 Key，其他已有模型保留；写入前自动备份到 `%USERPROFILE%\.workbuddy\model-backups\`。空文件会自动初始化，损坏或无效 JSON 会先备份为 `*-invalid.json` 再重建。导入完成后必须完全重启 WorkBuddy，才能在“设置 > 模型”看到更新后的列表。

## 本地开发

在 macOS Intel 上，从仓库根目录执行：

```sh
./scripts/setup-macos.sh
./scripts/test-local.sh
./scripts/dev-local.sh
```

停止本地 GUI：

```sh
./scripts/stop-local.sh
```

完整的 Intel 本机构建、签名和架构检查：

```sh
./scripts/build-local.sh
```

详细前置条件、目录约定、健康检查和故障排查见 [`docs/LOCAL_DEV_MACOS.md`](docs/LOCAL_DEV_MACOS.md)。

Windows 构建：

```text
python build_windows.py
```

macOS 构建由 `.github/workflows/build-macos.yml` 生成 M 芯片和 Intel 两个产物。
