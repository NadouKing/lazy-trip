"""Standalone static report; all source text and URLs are treated as untrusted."""

from html import escape

from .io import public_url, timestamp
from .request import CHINA


def esc(value) -> str:
    return escape("" if value is None else str(value), quote=True)


def local_time(value) -> str:
    try:
        return timestamp(value).astimezone(CHINA).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return "未记录"


def route_html(route: dict | None, heading: str, sources: dict) -> str:
    if not route:
        return f"<section><h2>{esc(heading)}</h2><p>现有候选和约束下未找到可行方案，需要补候选或路线数据。</p></section>"
    price = route["costYuanGroup"]
    unknown = "，另有未知费用" if not price["complete"] else ""
    rows = []
    modes = {"walking": "步行", "transit": "公交/地铁", "driving": "驾车", "bicycling": "骑行"}
    environments = {"indoor": "室内", "outdoor": "室外", "mixed": "室内外"}
    for item in route["timeline"]:
        clock = f"<time>{esc(item['start'])}–{esc(item['end'])}</time>"
        if item["type"] == "travel":
            text = f"{esc(item['from'])} → {esc(item['to'])}<small>{esc(modes.get(item['mode']))} · " \
                   f"{esc(round(item['distanceMeters']))} 米 · 高德估计 " \
                   f"{esc(item['durationSeconds'] / 60):s} 分钟，另留缓冲</small>"
        elif item["type"] == "wait":
            text = esc(item["reason"])
        else:
            links = "、".join(f'<a href="#source-{sources[identifier]}">来源 {sources[identifier]}</a>'
                             for identifier in item["evidenceIds"] if identifier in sources)
            text = f"<strong>{esc(item['name'])}</strong><p>{esc(item.get('reason'))}</p>" \
                   f"<small>{esc(item.get('address'))} · {esc(environments.get(item['environment']))} · " \
                   f"{links}</small><a href=\"{esc(public_url(item['navigationUrl']))}\">在高德查看位置</a>"
        rows.append(f"<article>{clock}<div>{text}</div></article>")
    issues = "<aside>" + "<br>".join(map(esc, route["issues"])) + "</aside>" if route["issues"] else ""
    return f"<section><h2>{esc(heading)}</h2><p class=\"metrics\">{esc(route['walkingMeters'])} 米步行" \
        f"（含场内估计） · 全组约 ¥{esc(price['min'])}–{esc(price['max'])}{unknown} · " \
        f"{esc(route['returnBy'])} 前返回起点</p>{''.join(rows)}{issues}<small>" \
        f"{'；'.join(map(esc, route['assumptions']))}</small></section>"


def render_html(report: dict) -> str:
    sources = {item["id"]: index + 1 for index, item in enumerate(report["evidence"])}
    request = report["request"]
    weather = report["weather"]
    label = {"ready_with_estimates": "已检查约束，含规划估计", "provisional": "方案待补充核实",
             "needs_route_data": "需要补查路线", "no_feasible_plan": "当前条件下没有可行方案"}
    description = f"{esc(weather['description'])} · {esc(weather['lowC'])}–{esc(weather['highC'])}℃" \
        if weather["known"] else esc(weather["note"])
    advisories = "<aside>" + "<br>".join(map(esc, report["advisory"])) + "</aside>" \
        if report["advisory"] else ""
    excluded = "".join(f"<li>{esc(item['name'])}：{esc(item.get('details') or item['reason'])}</li>"
                       for item in report["excluded"]) or "<li>暂无主动排除项。</li>"
    excluded += "".join(f"<li>缺少路线：{esc(identifier)}</li>" for identifier in report["missingRoutes"])
    evidence = []
    for index, item in enumerate(report["evidence"], 1):
        count = f" · 本次读取文字评论 {esc(item['commentSampleCount'])} 条" \
            if item.get("commentSampleCount") is not None else ""
        evidence.append(f'<li id="source-{index}"><a href="{esc(public_url(item.get("sourceUrl")))}">'
                        f'来源 {index} · {esc(item.get("title") or item["id"])}</a>'
                        f'<small>{esc(item.get("source"))} · 查询 '
                        f'{esc(local_time(item.get("fetchedAt")))}{count}</small>'
                        f'<p>{esc(item.get("summary"))}</p></li>')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>当天往返 · {esc(request['area'])}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f5f1;color:#24362d;font:16px/1.7 system-ui,sans-serif}}
main{{max-width:960px;margin:auto;padding:32px 20px}}header{{padding:30px;background:#173f35;color:white;border-radius:20px}}
h1{{font-size:30px;margin:8px 0}}h2{{font-size:22px;margin:0 0 16px}}section{{background:white;padding:26px;margin-top:20px;border-radius:16px}}
article{{display:grid;grid-template-columns:110px 1fr;gap:16px;border-top:1px solid #e2e8df;padding:18px 0}}
article p{{margin:5px 0}}time{{color:#47735d}}small{{display:block;color:#617468;font-size:13px}}header small{{color:#cee3d5}}
a{{color:#246b55;overflow-wrap:anywhere}}.metrics{{background:#edf4ec;border-radius:10px;padding:12px}}
aside{{background:#fff1d8;border-left:4px solid #d1a247;padding:14px;margin:16px 0}}li{{margin:8px 0}}
@media(max-width:520px){{article{{grid-template-columns:1fr;gap:4px}}main{{padding:15px}}section{{padding:20px}}}}
@media print{{body{{background:white}}section,header{{break-inside:avoid}}}}
</style><main><header><small>LAZY TRIP · 当天往返</small><h1>{esc(request['area'])}</h1>
<div>{esc(request['date'])} · {esc(request['origin']['name'])} 出发 · {esc(request['startTime'])}–{esc(request['endTime'])}</div>
<div>全组预算 ¥{esc(request['budgetYuan'])} · {esc(request['people'])} 人 · {esc(label.get(report['state'], report['state']))}</div></header>
<section><h2>天气与规划条件</h2><p>{description}</p><small>{esc(weather['note'])}；查询时间 {esc(local_time(weather.get('receivedAt')))}</small>{advisories}</section>
{route_html(report['main'], '主方案', sources)}{route_html(report['indoorAlternative'], '室内备选', sources)}
<section><h2>已排除与待核实</h2><ul>{excluded}</ul></section><section><h2>依据与限制</h2><ul>{''.join(evidence)}</ul>
<aside>{'<br>'.join(map(esc, report['limits']))}</aside><small>生成于 {esc(local_time(report['generatedAt']))}（中国标准时间）。</small></section></main></html>'''
