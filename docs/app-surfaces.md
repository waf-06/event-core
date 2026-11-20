# 桌面 App 的真实接口勘察（2026-11-16，本机实测）

本机装了什么、每个 App 的模型配置在哪、能不能无头调用——按这个表决定适配方式，不要凭印象猜。

## 总表

| App | 版本 / 路径 | 无头接口 | 模型切换点 | 用量来源 |
|---|---|---|---|---|
| WorkBuddy（腾讯 CodeBuddy） | 5.11.3 `<Apps>/WorkBuddy` | 自带 CodeBuddy CLI（`resources/app.asar.unpacked/cli`，dist 在 asar 内，直接跑 bin 会 `Cannot find module '../dist/codebuddy'`） | `~/.codebuddy/models.json`（官方文档支持自定义 OpenAI 兼容模型），选择器里切换 | 无 token 账本；`~/.workbuddy/usage-log.json` 只记 skill 使用 |
| Qoder CN IDE | 1.106.3 `<Apps>/Qoder CN IDE`（VS Code fork） | `bin/qodercn.cmd` 只支持 IDE 命令；官方 CLI 是独立产品 `npm i -g @qoder-ai/qodercli` / `irm https://qoder.com/install.ps1 \| iex` | IDE：Settings → Qoder IDE Settings → Models → + Add；CLI：`/model` → Custom | IDE 无账本；Qoder Credits 在账号页 |
| Qoder CN（Work 版） | 0.5.12 `<Apps>/Qoder CN` | 无 | `~/.qoder-cn/.models/default` = `{"key":"auto","uid":...,"scene":"app"}`；catalog-v7 是加密二进制，只能写 key | 无 |
| DeepSeek Harness | 0.2.1-rc.3 `<Apps>/Deepseek Harness` | 有：`pip install deepseek-harness-sdk` 提供 `dsh` 命令 + Python SDK（Windows x64 支持，原生 runtime wheel） | App：Settings → Models（DeepSeek key / 第三方 provider / 自定义 OpenAI 兼容端点）；SDK：profile | **`~/.dsh/dsh-usage/usage-ledger.json`：按天/按 provider/按模型的 input/output/cache/cost，真实数据** |
| 豆包 | `<Apps>/Doubao`（Chromium 壳，User Data 在 `%LOCALAPPDATA%\Doubao\User Data`） | 无。UI 里没有自定义 provider | 只能在 App 内选模型 | 无；只能按字符估算 |

## Qoder CN（Work 版）真正的控制面（2026-11-16 实测）

用户日常用的是 **Work 版**（`<Apps>/Qoder CN`，不是 IDE），所以按它的面做适配：

- `~/.qoder-cn/settings.json → providers` 存 **BYOK 自定义 provider**（`type: openai-compatible`、`protocol: openai`、`baseUrl`、`apiKey`、`model`、`models[]`）。
  本机已有两个：`qwen3.5:9b-64k` 和 `qwen3.5:4b-64k`，都指向 `http://127.0.0.1:11434/v1`。→ 所以“把 DeepSeek 接进 Qoder CN”是写这个 map，不需要 UI。
- `~/.qoder-cn/.models/default` 存当前选择：`{"key":"auto","uid":...,"scene":"app","updatedAt":...}`。
  日志里出现过的 key：`qfmodel`、`dfmodel`、`qmodel_38max`、`qmodel_latest`。写未知 key 可能回退 auto。
- 它内部有 `qodercli` daemon（`logs/runs/<ts>-<rand>-p<pid>/qodercli.log`，日志里有 `[sdk-protocol]`、`daemon.get_models`、`daemon.list_byok_configs`），
  但 PATH 上没有 `qoderclicn.exe`；`~/.qoder-cn/entry/qodercn.cmd` 的 dispatcher 提示可装
  `irm https://static.qoder.com.cn/qoder-cli-cn/install.ps1 | iex`（CN 版 CLI，**不是** npm 的 `@qoder-ai/qodercli`）。
- **用量不可得**：日志里有 `input_tokens= / output_tokens=` 字段，但 BYOK provider 的每次运行都记 **0**。不要拿它当计量来源。

## DSH 的额外汇总点

- `~/.dsh/.credentials.yaml`：provider 凭据（`refs:` 里有 `OLLAMA_API_KEY` / `DEEPSEEK_API_KEY`），**永不读取/打印明文**。
- `~/.dsh/dsh-usage/provider-snapshots.json`：provider 列表 + 余额（DeepSeek 余额就在这里同步）。
- `~/.dsh/skills/`、`~/.dsh/plugins/`、`~/.dsh/profiles/`、`~/.dsh/sessions/`、`~/.dsh/task-board/`：DSH 本身是个 agent harness，和 Hermes 的目录结构同构；它可以被 `dsh` CLI 以独立 `--dsh-home` 驱动。
- DSH 的 cost 单位是 **人民币**（实测 44M cache read + 52 万 input ≈ ¥1.99，与 DeepSeek 人民币计价一致）。

## CodeBuddy / WorkBuddy models.json 的三个坑

1. **UTF-8 无 BOM**。带 BOM 会静默读不到（官方 troubleshooting 明确写了）。
2. `apiKey` 支持 `${ENV_VAR}`，所以 key 放环境变量，不写进文件。
3. 改完必须**完全退出并重启** App，选择器才刷新；只重开窗口不行。

## Qoder 模型 key

`.models/default` 的 `key` 是服务端下发的模型 key（当前 `auto`）。写入未知 key 后 App 可能回退到 auto，所以：
- 改之前先备份该文件；
- 改完重启，用 UI 确认选择器显示的是目标模型；
- 宁可走 Qoder CLI 的 `/model`——那是官方支持的切换面。

## 已确认的环境事实

- Ollama 0.40.16，已装 `qwen3.5:4b-64k` (3.3 GB)、`qwen3.5:9b-64k` (5.7 GB)，context_length 262144，tools 能力在。
- Hermes 当前默认模型就是 `qwen3.5:4b-64k`（provider ollama）。
- `DEEPSEEK_API_KEY` 已配置且余额可用；`MINIMAX_CN_API_KEY` 也在 `.env`。
- DeepSeek 现役模型名：`deepseek-flash`（V4.1-Flash）、`deepseek-v4-pro`；旧的 `deepseek-v4-flash` 会被路由到 Flash 并按 Flash 计费。
