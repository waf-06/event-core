# EVENT CORE · 多模型调度台

把本机的几个模型（本地 Ollama、DeepSeek API、Qoder CN 官方 CLI）组织成**可互相评审的子 agent**，
由一个调度引擎统一分发、汇总、计量，并配一个实时可视化的调度台。

![调度台](https://img.shields.io/badge/UI-Event%20Core-cfe9ff) ![python](https://img.shields.io/badge/python-3.11%2B-blue) ![deps](https://img.shields.io/badge/deps-stdlib%20only-green)

---

## 它做什么

```
                    ┌──────────────┐
   一个任务  ─────▶ │  dispatch    │ ──▶ ⚡ 速记 (本地 4B)      ┐
                    │  engine      │ ──▶ ✍️ 助手 (本地 9B)      │ 第1轮：各自独立回答
                    │   :8765      │ ──▶ 🛠️ 工程 (DeepSeek)     │
                    └──────┬───────┘ ──▶ 🔍 评审 (DeepSeek Pro) │
                           │         └─▶ 🧩 Qoder (官方 CLI)    ┘
                           │
                           ▼  第2轮：互相挑错 / 补充
                    ┌──────────────┐
                    │  synthesis   │ ──▶ 一份带分歧标注的最终答案
                    └──────────────┘
```

- **并行发言**：所有被选中的 agent 同时回答，互不阻塞
- **交叉评审**：第二轮每个 agent 看到别人说了什么，只补充或纠正
- **汇总**：由一个便宜的模型合并成最终答案，保留分歧并标注是谁的意见
- **计量**：每次调用记 token / 延迟 / 花费；Qoder 记 Credits（与人民币分开）
- **可续跑**：每轮落盘，引擎中途崩了标 `interrupted`，`/resume` 只补缺口
- **预算闸门**：每局一个上限（默认 ¥0.06），派活前按估价预留，超限时汇总降级而不是不给结论
- **人工拍板**：汇总认为「必须你决定」时，房间停在 `awaiting`，控制台出按钮；答完只重跑汇总
- **自适应轮次**：第一轮已收敛就跳过第二轮
- **可视化**：黑洞式核心 + 模块卡片 + 消息时间线，全部由真实调用驱动

## 界面

| 调度台 `/dispatch` | 用量 `/usage` |
|---|---|
| 事件视界核心、5 个模块节点、喷流粒子、模块卡片、时间线、事件流 | KPI、14 天柱状图、按后端统计、Qoder Credits |

两页都是纯静态 HTML + Canvas，由 `ui.py` 直接托管，可以嵌进任何 Electron/浏览器。

## 快速开始

```bash
git clone <this repo> && cd event-core
python ui.py            # 引擎 http://127.0.0.1:8765
# 浏览器打开 http://127.0.0.1:8765/dispatch
```

零第三方依赖，只要 Python 3.11+。首次运行前改 `models.json` 里的路径和 `agents.json` 里的成员。

```bash
python mbus.py doctor                      # 体检：各后端是否可达
python mbus.py run "用一句话说明幂等" --backend deepseek-flash
python mbus.py usage --days 7              # 命令行看账本
```

## 组件

| 文件 | 作用 |
|---|---|
| `ui.py` | 调度引擎：群聊轮次、账本、预算、技能注入、HTTP API（8765） |
| `dispatch.html` | 调度台（Canvas 核心 + 卡片 + 时间线 + 底部通栏） |
| `usage.html` | 用量页（30 天 / 周月聚合 / hover / 点柱子看当天） |
| `mbus.py` | 模型路由、账本、预算硬上限、命令行 |
| `qoder_mcp.py` | 把 Qoder CLI 包成 MCP 工具（`ask_qoder` / `qoder_models` / `qoder_status`） |
| `watchdog.py` | 60s 探活，引擎/worker 挂了自动拉起 |
| `DESIGN-TRADEOFFS.md` | 参考 agent-autoloop 的取舍记录：借了什么、拒了什么、二阶影响 |
| `plugin/model-select.js` | Hermes 桌面插件：把两个页面挂进侧边栏 |

## 接入 Qoder（官方路径）

不走反代、不碰内部网关，用官方 CLI：

```powershell
irm https://static.qoder.com.cn/qoder-cli-cn/install.ps1 | iex
qoderclicn login          # 浏览器授权
qoderclicn --list-models  # 13 个内置 + BYOK
```

然后注册成 MCP 工具：

```bash
hermes mcp add qoder --command <python> --args <绝对路径>/qoder_mcp.py
```

`ask_qoder` 优先走常驻 worker（3.4s/轮），worker 不在时回落到冷启动 CLI（25s）。

## 配置

`agents.json` — 成员表：

```json
{
  "id": "engineer", "name": "工程", "emoji": "🛠️",
  "backend": "deepseek-flash", "transport": "api",
  "role": "给可执行的方案、代码、命令，注意边界条件。",
  "enabled": true, "skills": ["test-driven-development"]
}
```

`transport` 三种：`api`（OpenAI 兼容端点）、`qoder-cli`（官方 CLI）、`gui`（驱动桌面 App，慢，兜底）。

`models.json` — 后端定义、价格、预算上限：

```json
"budget": { "cny": 10, "period": "day", "hard": true }
```

超预算的云调用会被拒绝，本地模型不受影响；`--force` 可越过。

## 技能库

`ui.py` 会把 `$MBUS_SKILL_LIB/catalog.json` 里对应技能的 `SKILL.md` 摘录注进 agent 的提示词。
调度台里选中一个 agent，搜技能、点一下即挂载（最多 2 个）。库本身不入库，路径由环境变量 `MBUS_SKILL_LIB` 指定（默认 `~/HermesWork/技能库`）。

## HTTP 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/room` | 开一局：`{task, agents?, rounds?, cap?}` |
| GET | `/api/room/<id>` | 读一局（含 `status` / `cost` / `questions` / `answers`） |
| POST | `/api/room/<id>/answer` | 拍板：`{id:"q1", choice:"…"}`，全部答完才继续汇总 |
| POST | `/api/room/<id>/resume` | 续跑中断的局，只补缺口 |
| GET | `/api/skills?q=&limit=` | 搜技能库 |
| POST | `/api/agent` | 改成员的模型或技能：`{id, model?, skills?}` |

`status` 取值：`running` → `synthesizing` → `done`，或停在 `awaiting`（等你拍板），
崩溃重启用 `interrupted` 标出来。

## 已知限制

- **GUI 类 App 无法隐身**：Chromium 不接受后台输入，只能缩到 460×340 露 2–3 秒；且 ghost（alpha=0）会让 UIA 树永久失效，必须冷启动。
- **Qoder 单轮 ~3.4s** 是常驻 worker 的极限，模型本身 1.9–3.5s；冷启动仍是 20s+。
- **Credits 与人民币不换算**，分开显示。
- **Dashboard 的动画是装饰**：只有粒子密度和节点亮度由真实调用驱动，其余是恒定背景。
- **`awaiting` 没有超时提醒**：一局可以无限期挂着，不会主动叫你。
- **Qoder 的 credits 不进预算闸门**（无法与人民币换算），所以 Qoder 调用不受单局上限约束。
- 第二轮评审只拿摘要时可能产生幻觉（举例：误判别人的代码有 bug），代码类任务建议传全文。

## License

MIT
