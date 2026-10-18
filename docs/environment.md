# 环境和安装验收

目标是 Python3.14 标准 GIL 构建。无 native 扩展要求的依赖路径先测试；本次不承诺 free-threaded 构建、其他 Python 大版本或所有操作系统已实测。

主应用和小红书工具各有 pyproject、独立版本和 CLI；主仓直接 import 库，日常只用主仓 `.venv`。点评已退出依赖；不会安装或启动它。小红书 profile 独立于 Python 环境保存。

## 开发多个仓库

默认 release sources 为固定 Git SHA。并排克隆后可临时用 uv 的本地源覆盖调试（不要把本地绝对路径提交到 release）：

```toml
[tool.uv.sources]
xiaohongshu-tools = { path = "../xiaohongshu-tools", editable = true }
```

开发机共用测试环境也可以，但它不是用户安装流程。发布前恢复不可变 SHA 并重新锁定，在仅克隆主仓的新目录验证 `uv sync --locked`。

## wheel 目录外验收

```powershell
uv build
# 在仓库之外创建临时目录和新环境，不复用 PYTHONPATH。
uv venv <临时目录>/.venv --python 3.14
# 从主仓导出固定Git来源和依赖，先安装它们，再装主仓wheel。
uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file <临时目录>/requirements.txt
uv pip install --python <临时目录>/.venv/Scripts/python.exe -r <临时目录>/requirements.txt
uv pip install --no-deps --python <临时目录>/.venv/Scripts/python.exe <主仓>/dist/lazy_trip-0.1.0-py3-none-any.whl
```

然后在临时目录运行 `python -c "import lazy_trip, xiaohongshu_tools"`、`lazy-trip --help`、`lazy-trip doctor` 和离线合成例子。主要验收仍是只clone主仓的 `uv sync --locked`；裸wheel 的依赖默认来自索引，Git来源属于主仓的 uv配置，二者不能混淆。

绝不依赖 Codex 私有运行时路径。CI/新环境只用公开仓库、锁文件和浏览器前提。已有个人 Cookie/profile 不是测试夹具、分发内容或部署依赖。
