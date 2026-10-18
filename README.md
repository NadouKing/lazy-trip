# lazy-trip

想出去走走，却懒得翻几十篇攻略、核对店名，再来回切地图。

lazy-trip 把这些琐事串起来：小红书找灵感和真实评论样本，大众点评核实商家，现有官方高德 MCP 查地点、路线和天气，最后得到一份当天出门、当天回家的安排。

**你决定想怎么过这一天，工具负责搜集、核对和计算。** 信息不足会写明待核实，不会用猜测补齐攻略。

## 现在能做什么

- 从两套 Python 工具库直接读取帖子、文字评论样本和商家信息。
- 保留来源、查询时间、评论样本数和部分失败，供当前 AI 阅读、总结和提炼候选。
- 生成官方高德任务，读取真实工具回执；按预算、步行量、营业时间和返程时间筛方案。
- 看出行当天的日间/夜间天气，雨天选室内、高温偏好避开中午室外停留。
- 输出 JSON 和可直接打开的 HTML，含主方案、室内备选、来源和待核实项。

当前版本由 **AI + CLI + 现有官方高德 MCP** 协同工作。CLI 没有内置独立大模型，不能独自理解所有帖子或调用聊天里的高德连接。它也不预订、不付款。

## 三个仓库怎样配合

[`xiaohongshu-tools`](https://github.com/NadouKing/xiaohongshu-tools) 和 [`dazhongdianping-tools`](https://github.com/NadouKing/dazhongdianping-tools) 都可以单独安装，提供各自的 Python 库与 CLI，也能供其他应用使用。Trip 是调用方：`lazy-trip → 两个 tools`，工具不依赖 Trip 或彼此。

两个 tools 负责各平台的数据读取和合同；Trip 的 `research` 模块负责把它们适配成出行证据，再结合需求、候选、官方地图/天气和路线计算。相似的异步调用和 JSON 外壳方便接入，小红书的笔记/评论与点评的商家字段仍各自保留。共用一个安装环境只是为了省事，不要求工具绑定出行场景。

## 安装一次，共用一个环境

需要 [uv](https://docs.astral.sh/uv/getting-started/installation/)、Git 和 Chrome/Chromium。Python 使用 **3.14 标准构建**，由 uv 准备；两个工具包随主项目装入同一个 `.venv`，无需另外安装 Node 或 Go。

```powershell
git clone https://github.com/NadouKing/lazy-trip.git
cd lazy-trip
uv sync --locked
uv run lazy-trip doctor
```

仓库锁定两个工具包的 Git 提交。只克隆主仓即可安装，无需手动下载两个工具仓。三个仓库一起开发时的本地覆盖方式见[环境说明](docs/environment.md)。浏览器程序和平台登录态位于环境之外；共享 Python 环境不等于共享平台 Cookie。

第一次需要在各自专用浏览器里登录（不会替你操作账号）：

```powershell
uv run xhs login
uv run dp login
uv run lazy-trip doctor --live
```

已有专用 profile 时用 `--xhs-profile` / `--dp-profile` 明确指定，不同时启动多个使用相同目录的进程。已有小红书 Cookie 可通过 `--xhs-cookies` 显式导入，原文件不修改。不会从你的其他软件中自动寻找凭证。

也可以用 `--config settings.json` 或 `LAZY_TRIP_CONFIG` 指定只含路径与浏览器设置的配置；默认读取 Windows `%LOCALAPPDATA%/lazy-trip/config.json`，其他系统 `$XDG_CONFIG_HOME/lazy-trip/config.json`（缺省为 `~/.config`）。格式如下，CLI 参数优先，不在这里存 Cookie、令牌或密钥：

```json
{
  "xiaohongshu": {"profile_dir": "你的专用小红书目录", "headless": true},
  "dianping": {"profile_dir": "你的专用点评目录", "headless": true}
}
```

## 一次出门怎样准备

先写自己的需求，下面只是广州当天往返的输入示例，没有预设你的住址或喜好。

```powershell
uv run lazy-trip init --city 广州 --area 东山口 --origin "东山口地铁站" --out runtime/request.json
uv run lazy-trip research --request runtime/request.json --notes 4 --shops 2 --out runtime/evidence.json
```

修改日期、时间、人数、全组预算和步行上限。然后请当前 AI 阅读证据，整理 `candidates.json`；格式见 [examples/synthetic/candidates.json](examples/synthetic/candidates.json)。每个候选都应说明具体分店、证据 ID 和估计的依据。

搜索结果可能召回其他区域的同名分店；**搜到了不等于就是目标门店**。先核对地址、分店和证据相关性，再送入路线规划。

```powershell
uv run lazy-trip map-tasks --request runtime/request.json --candidates runtime/candidates.json --stage search --out runtime/map-tasks.json
```

请当前 AI 用已连接的**官方高德 MCP**执行任务，核对分店并填写 `amapId`。再生成详情任务并执行，保存真实 `amap-results.json`：

```powershell
uv run lazy-trip map-tasks --request runtime/request.json --candidates runtime/candidates.json --stage details --out runtime/detail-tasks.json
uv run lazy-trip route-tasks --request runtime/request.json --candidates runtime/candidates.json --maps runtime/amap-results.json --out runtime/route-tasks.json
```

执行路线任务，把真实回执追加到同一个 `results` 数组，再生成报告：

```powershell
uv run lazy-trip plan --request runtime/request.json --candidates runtime/candidates.json --maps runtime/amap-results.json --evidence runtime/evidence.json --out runtime/report.json --html runtime/itinerary.html
```

每条回执必须保留 `id / tool / arguments / receivedAt / result`；格式见[接口说明](docs/contracts.md)。也可把[规划 Skill](skills/daytrip-planner/SKILL.md)交给当前 AI 按步骤执行。

## 怎样读报告

| 状态 | 意思 |
|---|---|
| `ready_with_estimates` | 已检查记录中的约束，停留、消费和场内步行仍为估计 |
| `provisional` | 有可行路线，但有天气、费用、营业时间、来源冲突等待核实项 |
| `needs_route_data` | 缺少交通段，含返程也必须有真实数据 |
| `no_feasible_plan` | 当前候选无法满足已给出的条件 |

退出码：`0` 命令完成（仍需看报告状态）；`1` 参数/数据/运行错误；`2` 没取得证据或没有可行方案。stdout 为 JSON，研究进度写 stderr。

日预报不能说明某小时一定下雨。点评没有展示评论时不会虚构评论。复杂/跨夜营业时段暂标未核实。网页变化、登录或人工验证可能使某个来源暂时不可用，已取得的证据会保留。

## 接下来怎样变好

按四阶段推进：[先跑起来 → 部署简单 → 共用资源 → 效果更好](docs/roadmap.md)。第一版聚焦当天往返；抖音、微博、携程、去哪儿、美团列入后续规划，先用官方能力，有确认的缺口再补自己的工具。

## 开发与来源

每次功能开发和修复按[开发与PR交付](docs/development-delivery.md)提交可验证的草稿PR，并[处理审查](docs/review.md)、更新验收记录。本轮上游检查和工具版本接入顺序见[维护记录](docs/maintenance-2026-10-18.md)。

```powershell
uv sync --locked
uv run pytest
uv run ruff check .
uv build
```

[架构](docs/architecture.md) · [部署](docs/deployment.md) · [环境与安装验收](docs/environment.md) · [工程规则](AGENTS.md)

感谢 [travel-agent](https://github.com/huahuanao/travel-agent) 提供多来源出行思路，参考 [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) 的网页状态读取、[dp-mcp](https://github.com/qianwj/dp-mcp) 的商家字段整理；本仓为原 Node 验证版规划器的 Python 迁移。

MIT License。登录态、Cookie、个人研究数据均不属于源码和示例。
