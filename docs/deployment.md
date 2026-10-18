# 部署和运行

## 一次安装

1. 安装 uv、Git、Chrome/Chromium。
2. clone 主仓，`uv sync --locked`；uv 按 `.python-version` 准备标准 Python3.14，并把三包及依赖安装到主仓 `.venv`。
3. `uv run lazy-trip doctor` 检查版本和浏览器；需要时加 `--chrome` 指定浏览器。
4. 使用 `uv run xhs login`、`uv run dp login` 在各自独立窗口完成登录。`uv run lazy-trip doctor --live` 验证状态。
5. 在 AI 宿主保留已配置官方高德 MCP，然后按 README/Skill 研究、提炼、查询和排程。

不要求 Node、Go 或额外模型 API。浏览器是外部程序，登录是账号自己的交互操作，不因安装包就自动完成。此版本既不提取高德密钥，也不把浏览器状态塞进 wheel。

## 常见情况

- 登录失效：停止占用该 profile 的工具，重新运行对应 login；原有 Cookie 不上传。
- profile 冲突：同一平台同一目录同时只运行一个会话。不要删除用户目录“修复”锁。
- 平台要求验证：打开自己的专用浏览器完成；不自动破解或绕过。
- 研究部分失败：看 evidence.errors，先使用已取得的来源；若来源单薄则补充后再提炼候选。
- 缺地图：map-tasks/route-tasks 是交接任务，需要 AI 调用真实官方工具后回填，不会自动执行。
- 天气不在范围：报告暂定，临近出发刷新官方查询。
- `uv sync --locked` 失败：确认 Git 能访问已锁定仓库，不要随意删 lock 改装不明版本。

## 升级

平台网页易变，升级先在开发环境跑解析/错误与真实只读验收；确认再更新两个 Git SHA、uv.lock 和版本。保留主环境锁文件，浏览器 profile 与项目分开，不在升级时重建登录目录。
