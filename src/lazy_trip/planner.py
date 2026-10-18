"""Bounded itinerary search with explicit unknowns and a real return leg."""

import math
import re
from datetime import UTC, datetime
from itertools import permutations
from urllib.parse import urlencode

from .errors import TripError
from .io import now, timestamp
from .maps import ROUTE_SUFFIXES, normalized_route, number, resolve_nodes, result_index
from .request import china_date, hhmm, minutes, validate_candidates, validate_request


def fresh(value: str) -> bool:
    age = (datetime.now(UTC) - timestamp(value)).total_seconds()
    return -300 <= age <= 86400


def weather_for_date(snapshot: dict, selected_date: str, city: str | None = None) -> dict:
    record = result_index(snapshot).get("weather")
    if not record:
        return {"known": False, "note": "缺少天气查询，方案需要补查天气。"}
    if not record["tool"].endswith("maps_weather"):
        raise TripError("weather_tool_mismatch", "天气记录对应的工具不正确。")
    data = record["data"]
    forecasts = data.get("forecasts", data.get("casts", []))
    first = forecasts[0] if isinstance(forecasts, list) and forecasts else {}
    actual_city = data.get("city") or first.get("city") or record["arguments"].get("city")
    if city and str(actual_city).removesuffix("市") != str(city).removesuffix("市"):
        raise TripError("weather_city_mismatch", "天气城市与本次需求不符。")
    if isinstance(first.get("casts"), list):
        forecasts = first["casts"]
    day = next((item for item in forecasts if item.get("date") == selected_date), None)
    if not day:
        return {"known": False, "receivedAt": record["receivedAt"],
                "note": "出行日期不在本次预报范围，不能套用今天的天气。"}
    description = f"{day.get('dayweather', '')} {day.get('nightweather', '')}".strip()
    high = number(day.get("daytemp"))
    low = number(day.get("nighttemp"))
    # A date alone is not a usable weather forecast.
    known = bool(description) and high is not None and low is not None
    return {"known": known, "date": selected_date, "description": description,
            "highC": high, "lowC": low, "rain": bool(re.search("雨|雪", description)),
            "severe": bool(re.search("暴雨|大雨|暴雪|台风|雷暴", description)),
            "receivedAt": record["receivedAt"], "fresh": fresh(record["receivedAt"]),
            "reportTime": data.get("reporttime") or first.get("reporttime"),
            "resolution": "day-night", "note": "日间/夜间预报，不代表逐小时降雨概率或官方预警。"
            if known else "本次天气字段不完整，需要补查，不能把缺失温度当作零度。"}


def opening_window(text: str | None) -> tuple[int, int] | None:
    if not isinstance(text, str) or not text.strip():
        return None
    if re.search("24小时|全天", text):
        return 0, 1440
    ranges = re.findall(r"(\d{1,2}):(\d{2})\s*[-–—~至]\s*(\d{1,2}):(\d{2})", text)
    # Split/overnight hours remain unknown instead of silently taking the first interval.
    if len(ranges) != 1:
        return None
    sh, sm, eh, em = map(int, ranges[0])
    if not (0 <= sh <= 23 and 0 <= sm <= 59 and 0 <= eh <= 24 and 0 <= em <= 59) \
            or (eh == 24 and em != 0):
        return None
    start, end = sh * 60 + sm, eh * 60 + em
    return (start, end) if end > start else None


def candidate_closed(candidate: dict) -> bool:
    return candidate.get("availability") == "closed" or bool(re.search(
        "暂停营业|已关闭|歇业|永久关闭", f"{candidate['poi'].get('name', '')} "
        f"{candidate.get('businessStatus', '')}"))


def plan(request: dict, candidates: list[dict], snapshot: dict,
         evidence: list[dict] | None = None) -> dict:
    request = validate_request(request)
    candidates = validate_candidates({"candidates": candidates})
    evidence = evidence or []
    if not isinstance(evidence, list) or any(not isinstance(item, dict) or
                                           not isinstance(item.get("id"), str) for item in evidence):
        raise TripError("invalid_evidence", "证据需要带有 id 的对象数组。")
    known_evidence = {item["id"] for item in evidence}
    if len(known_evidence) != len(evidence):
        raise TripError("duplicate_evidence", "证据 id 不能重复。")
    nodes = resolve_nodes(request, candidates, snapshot)
    origin = nodes[0]
    index = result_index(snapshot)
    weather = weather_for_date(snapshot, request["date"], request["city"])
    excluded, feasible, missing_routes = [], [], set()
    for node in nodes[1:]:
        for identifier in node["evidenceIds"]:
            if identifier not in known_evidence:
                raise TripError("unresolved_evidence", f"{node['name']} 引用了不存在的来源。")
        if candidate_closed(node) or node.get("availability") == "uncertain":
            excluded.append({"id": node["id"], "name": node["name"],
                             "reason": "存在停业信息" if candidate_closed(node) else
                             "营业状态有冲突，先排除", "details": node.get("reason"),
                             "evidenceIds": node["evidenceIds"]})
        else:
            feasible.append(node)

    high = weather.get("highC")
    hot = high is not None and high >= 32

    def evaluate(order: tuple[dict, ...], indoor_only: bool) -> dict | None:
        if indoor_only and any(item["environment"] != "indoor" for item in order):
            return None
        t, walking, cost_min, cost_max = minutes(request["startTime"]), 0, 0, 0
        unknown_cost = unknown_walk = verification_pending = False
        hours_complete = True
        heat_minutes = idle_minutes = 0
        timeline, issues = [], []
        previous = origin
        for target in (*order, origin):
            route_id = f"route:{previous['id']}:{target['id']}"
            record = index.get(route_id)
            if not record:
                missing_routes.add(route_id)
                return None
            if not record["tool"].endswith("maps_" + ROUTE_SUFFIXES[request["mode"]]):
                raise TripError("route_mode_mismatch", f"{route_id} 交通方式与需求不符。")
            if record["arguments"].get("origin") != previous["location"] \
                    or record["arguments"].get("destination") != target["location"]:
                raise TripError("route_coordinate_mismatch", f"{route_id} 坐标与选定分店不符。")
            try:
                route = normalized_route(record, request["mode"])
            except TripError as error:
                if error.code != "route_unavailable":
                    raise
                missing_routes.add(route_id)
                return None
            arrival = t + math.ceil(route["durationSeconds"] / 60)
            timeline.append({"type": "travel", "from": previous["name"], "to": target["name"],
                             "start": hhmm(t), "end": hhmm(arrival), **route,
                             "evidenceId": route_id})
            t = arrival + request["bufferMinutes"]
            if route["walkingMeters"] is None:
                unknown_walk = True
            else:
                walking += route["walkingMeters"]
            if route["fareYuan"] is None:
                unknown_cost = True
            else:
                cost_min += route["fareYuan"] * request["people"]
                cost_max += route["fareYuan"] * request["people"]
            if target["id"] != "origin":
                if request["avoidMiddayHeat"] and hot and target["environment"] != "indoor" \
                        and t < 960 and t + target["stayMinutes"] > 720:
                    idle_minutes += 960 - t
                    timeline.append({"type": "wait", "start": hhmm(t), "end": "16:00",
                                     "reason": "按高温日偏好延后室外活动；可延后出门或在上一室内地点休息，" 
                                     "不要求在室外等候"})
                    t = 960
                hours = opening_window(target.get("openingHours"))
                if hours and t < hours[0]:
                    timeline.append({"type": "wait", "start": hhmm(t), "end": hhmm(hours[0]),
                                     "reason": "等待营业"})
                    t = hours[0]
                if hours and t + target["stayMinutes"] > hours[1]:
                    return None
                if not hours:
                    hours_complete = False
                    issues.append(f"{target['name']} 营业时间未核实")
                verification_pending |= bool(target.get("verificationPending"))
                issues.extend(f"{target['name']}：{note}" for note in target.get("verificationNotes", []))
                if hot and target["environment"] != "indoor":
                    heat_minutes += max(0, min(t + target["stayMinutes"], 960) - max(t, 720))
                cost = target.get("costYuan")
                if cost is None:
                    unknown_cost = True
                else:
                    cost_min += cost["min"] * request["people"]
                    cost_max += cost["max"] * request["people"]
                walking += target["insideWalkingMeters"]
                timeline.append({"type": "visit", "id": target["id"], "name": target["name"],
                                 "start": hhmm(t), "end": hhmm(t + target["stayMinutes"]),
                                 "environment": target["environment"], "reason": target.get("reason"),
                                 "costYuanPerPerson": cost, "evidenceIds": target["evidenceIds"],
                                 "address": target["poi"].get("address"),
                                 "navigationUrl": "https://uri.amap.com/marker?" + urlencode({
                                     "position": target["location"],
                                     "name": target["poi"].get("name", target["name"])})})
                t += target["stayMinutes"]
            previous = target
        if t > minutes(request["endTime"]) or walking > request["maxWalkingMeters"] \
                or cost_max > request["budgetYuan"]:
            return None
        if unknown_walk:
            issues.append("部分交通步行量未知，无法确认步行上限")
        if unknown_cost:
            issues.append("部分费用未知，无法确认总预算")
        if heat_minutes:
            issues.append(f"12–16 点室外停留约 {heat_minutes:g} 分钟，日预报无法证明逐小时温度")
        has_food = any(item["kind"] == "food" for item in order)
        has_play = any(item["kind"] == "play" for item in order)
        score = sum(item.get("priority", 1) for item in order) * 100 + \
            (100 if has_food and has_play else 0) - walking / 100 - heat_minutes * 2 \
            - idle_minutes / 2 - len(issues) * 15
        assumptions = ["停留时间、场内步行量及消费区间属于规划估计；路段耗时来自本次高德查询",
                       f"每段交通后预留 {request['bufferMinutes']} 分钟缓冲"]
        if request["avoidMiddayHeat"] and hot:
            assumptions.append("按高温日偏好将室外停留放在 16:00 后；不是逐小时温度预测")
        return {"stopIds": [item["id"] for item in order], "timeline": timeline,
                "returnBy": hhmm(t), "walkingMeters": math.ceil(walking),
                "costYuanGroup": {"min": cost_min, "max": cost_max, "complete": not unknown_cost},
                "walkingComplete": not unknown_walk, "assumptions": assumptions,
                "issues": list(dict.fromkeys(issues)), "openingHoursComplete": hours_complete,
                "verificationPending": verification_pending,
                "constraintsVerified": not unknown_walk and not unknown_cost and hours_complete
                and not verification_pending, "score": score, "hasFood": has_food, "hasPlay": has_play}

    orders = [order for size in range(1, min(len(feasible), request["maxStops"]) + 1)
              for order in permutations(feasible, size)]
    indoor = sorted(filter(None, (evaluate(order, True) for order in orders)),
                    key=lambda item: item["score"], reverse=True)
    ranked = sorted(filter(None, (evaluate(order, weather.get("rain") or weather.get("severe"))
                                  for order in orders)), key=lambda item: item["score"], reverse=True)
    best = ranked[0] if ranked else None
    alternate = next((item for item in indoor if not best or item["stopIds"] != best["stopIds"]),
                     indoor[0] if indoor else None)
    stale = any(not fresh(item["receivedAt"]) for item in snapshot["results"])
    state = "ready_with_estimates" if best and weather["known"] and not stale \
        and best["constraintsVerified"] and best["hasFood"] and best["hasPlay"] else \
        "provisional" if best else "needs_route_data" if missing_routes else "no_feasible_plan"
    advisory = []
    if not weather["known"]:
        advisory.append(weather["note"])
    if weather.get("rain"):
        advisory.append("预报有雨，主方案仅选择室内停留；往返交通仍需考虑天气")
    if weather.get("severe"):
        advisory.append("预报出现恶劣天气描述，优先考虑延期，并在出发前核实官方预警")
    if best and not (best["hasFood"] and best["hasPlay"]):
        advisory.append("当前可行方案未同时覆盖吃饭和游玩，需要补候选或调整约束")
    if china_date() > request["date"]:
        advisory.append("该日期已经过去，此报告仅用于回放验证")
        if best:
            state = "provisional"
    if stale:
        advisory.append("部分高德数据超过 24 小时或时间戳异常，出发前需刷新")
    if snapshot.get("synthetic"):
        advisory.append("合成数据仅用于离线验证，不是平台或官方地图的真实查询")
        if best:
            state = "provisional"
    fields = ("id", "source", "summary", "fetchedAt", "publishedAt", "commentSampleCount",
              "commentScope", "method", "elapsedMs")
    sources = [{**{key: item[key] for key in fields if key in item},
                "sourceUrl": item.get("sourceUrl", item.get("url")),
                "title": item.get("title", item.get("name"))} for item in evidence]
    return {"schemaVersion": 1, "generatedAt": now(), "state": state, "request": request,
            "weather": weather, "advisory": advisory, "main": best, "indoorAlternative": alternate,
            "excluded": excluded, "missingRoutes": sorted(missing_routes), "evidence": sources,
            "limits": ["高德日间/夜间天气，不含逐小时降雨与预警", "不自动预约、下单或支付",
                       "商家评分不代表已读取完整评论", "高德耗时为查询时估计，不保证未来班次或路况",
                       "当前 AI 负责语义提炼与官方 MCP 调用；本 CLI 没有独立大模型宿主"]}
