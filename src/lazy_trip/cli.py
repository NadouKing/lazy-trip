import argparse
import asyncio
import importlib.metadata
import json
import os
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import __version__
from .errors import TripError, public_error
from .io import public_data, read_json, write_json, write_text
from .maps import map_tasks, route_tasks
from .planner import plan
from .render import render_html
from .request import china_date, validate_candidates, validate_request
from .research import collect


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="lazy-trip", description=
        "小红书找灵感，官方高德核实商家、路线与天气，规划当天往返。")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--config", help="显式路径设置；默认读取用户配置目录/lazy-trip/config.json")
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="生成待填写的需求文件，不覆盖已有文件")
    init.add_argument("--out", required=True)
    init.add_argument("--city", default="")
    init.add_argument("--area", default="")
    init.add_argument("--origin", default="")
    doctor = commands.add_parser("doctor", help="检查运行环境；--live 才访问平台")
    doctor.add_argument("--live", action="store_true")
    _browser_options(doctor)
    doctor.add_argument("--out")
    research = commands.add_parser("research", help="读取小红书正文和评论样本")
    research.add_argument("--request", required=True)
    research.add_argument("--out", required=True)
    research.add_argument("--notes", type=int, default=4)
    research.add_argument("--comments", type=int, default=20)
    _browser_options(research)
    maps = commands.add_parser("map-tasks", help="生成官方高德地点与天气任务")
    maps.add_argument("--stage", choices=["search", "details"], default="details")
    routes = commands.add_parser("route-tasks", help="从选定 POI 的真实回执生成有向路线任务")
    routes.add_argument("--maps", required=True)
    planning = commands.add_parser("plan", help="检查约束，输出 JSON 与可选 HTML")
    planning.add_argument("--maps", required=True)
    planning.add_argument("--evidence", required=True)
    planning.add_argument("--html")
    for command in (maps, routes, planning):
        command.add_argument("--request", required=True)
        command.add_argument("--candidates", required=True)
        command.add_argument("--out")
    return root


def _browser_options(command):
    command.add_argument("--config", default=argparse.SUPPRESS,
                         help="显式路径设置文件，不存Cookie或令牌")
    command.add_argument("--xhs-profile", help="小红书专用用户目录")
    command.add_argument("--xhs-cookies", help="明确导入已有本地 Cookie 文件；不修改原文件")
    command.add_argument("--chrome", help="Chrome 可执行文件路径")
    command.add_argument("--headed", action="store_const", dest="headless", const=False,
                         default=None, help="显示浏览器窗口")
    command.add_argument("--timeout", type=float)


def browser_options(args) -> dict:
    explicit = args.config or os.environ.get("LAZY_TRIP_CONFIG")
    if os.name == "nt":
        config_root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    config_path = Path(explicit) if explicit else config_root / "lazy-trip/config.json"
    config = read_json(config_path) if explicit or config_path.is_file() else {}
    if not isinstance(config, dict) or any(key not in {"xiaohongshu", "dianping"} for key in config):
        raise TripError("invalid_config", "配置仅允许小红书路径与浏览器设置；旧点评段会被忽略。")
    allowed = {"profile_dir", "chrome_path", "headless", "timeout"}
    xhs = config.get("xiaohongshu", {})
    if not isinstance(xhs, dict) or set(xhs) - allowed:
        raise TripError("invalid_config", "平台配置仅允许 profile_dir/chrome_path/headless/timeout。")
    xhs = {"profile_dir": None, "chrome_path": None, "headless": True, "timeout": 30.0, **xhs}
    for name, value in (("profile_dir", args.xhs_profile), ("chrome_path", args.chrome),
                         ("headless", args.headless), ("timeout", args.timeout)):
        if value is not None:
            xhs[name] = value
    if not isinstance(xhs["timeout"], (int, float)) or isinstance(xhs["timeout"], bool) \
            or not 1 <= xhs["timeout"] <= 300:
        raise TripError("invalid_timeout", "timeout 必须在 1–300 秒之间。")
    if type(xhs["headless"]) is not bool or any(xhs[name] is not None and
            not isinstance(xhs[name], str) for name in ("profile_dir", "chrome_path")):
        raise TripError("invalid_config", "浏览器路径须为字符串，headless 须为布尔值。")
    if args.xhs_cookies:
        xhs["cookies_file"] = args.xhs_cookies
    return xhs


def print_json(value):
    print(json.dumps(public_data(value), ensure_ascii=False, indent=2, allow_nan=False))


def save_or_print(value, path):
    if path:
        write_json(path, value)
        print_json({"saved": str(Path(path).resolve())})
    else:
        print_json(value)


async def doctor(args) -> dict:
    xhs_options = browser_options(args)
    candidates = [shutil.which(name) for name in ("google-chrome", "chrome", "chromium")]
    if os.name == "nt":
        candidates += [str(Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) /
                           "Google/Chrome/Application/chrome.exe")]
    if sys.platform == "darwin":
        candidates += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    chrome = xhs_options.get("chrome_path") or next(
        (item for item in candidates if item and Path(item).is_file()), None)
    packages = {}
    for name in ("lazy-trip", "xiaohongshu-tools"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not_installed"
    report = {"python": sys.version.split()[0], "packages": packages,
              "chromeFound": bool(chrome and Path(chrome).is_file()),
              "amap": "复用宿主 AI 已连接的官方 MCP；独立 CLI 不检查或提取其配置。"}
    if args.live:
        from xiaohongshu_tools import XiaohongshuClient
        sources = [("xiaohongshu", XiaohongshuClient, xhs_options)]
        for source, factory, options in sources:
            try:
                async with factory(**options) as client:
                    status = await client.check_session()
                    report[source] = public_data(status)
            except Exception as error:
                report[source] = {"error": public_error(error)}
    return report


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            if Path(args.out).exists():
                raise TripError("file_exists", "目标文件已存在，请选择新路径。")
            value = {"city": args.city, "area": args.area, "origin": {"name": args.origin},
                     "date": china_date(datetime.now(UTC) + timedelta(days=1)),
                     "startTime": "14:00", "endTime": "19:00", "people": 1,
                     "budgetYuan": 150, "maxWalkingMeters": 5000, "mode": "walking",
                     "bufferMinutes": 10, "maxStops": 3, "overnight": False,
                     "interests": ["轻松散步", "吃点东西"]}
            save_or_print(value, args.out)
        elif args.command == "doctor":
            save_or_print(asyncio.run(doctor(args)), args.out)
        elif args.command == "research":
            request = validate_request(read_json(args.request))
            xhs = browser_options(args)
            result = asyncio.run(collect(request, out=args.out, note_limit=args.notes,
                comment_limit=args.comments, xhs_options=xhs,
                progress=lambda value: print(value, file=sys.stderr)))
            print_json({"saved": str(Path(args.out).resolve()),
                        "evidenceCount": len(result["evidence"]),
                        "commentSampleCount": sum(item.get("commentSampleCount", 0)
                                                  for item in result["evidence"]),
                        "errors": result["errors"]})
            return 0 if result["evidence"] else 2
        else:
            request = validate_request(read_json(args.request))
            candidates = validate_candidates(read_json(args.candidates))
            if args.command == "map-tasks":
                value = map_tasks(request, candidates, args.stage)
            elif args.command == "route-tasks":
                value = route_tasks(request, candidates, read_json(args.maps))
            else:
                evidence = read_json(args.evidence)
                value = plan(request, candidates, read_json(args.maps),
                             evidence.get("evidence", []) if isinstance(evidence, dict) else evidence)
                if args.html:
                    write_text(args.html, render_html(value))
            save_or_print(value, args.out)
            if args.command == "plan" and not value["main"]:
                return 2
        return 0
    except (KeyboardInterrupt, BrokenPipeError):
        return 130
    except Exception as error:
        print_json({"error": public_error(error)})
        return 1
