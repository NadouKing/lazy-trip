"""Build official MCP tasks and validate real receipts; never contact Amap directly."""

import math
import re

from .errors import TripError
from .io import now, timestamp

ROUTE_SUFFIXES = {"walking": "direction_walking", "transit": "direction_transit_integrated",
                  "driving": "direction_driving", "bicycling": "direction_bicycling"}


def unwrap(value):
    import json

    if not isinstance(value, dict):
        raise TripError("invalid_amap_result", "高德结果必须是 JSON 对象。")
    if value.get("isError"):
        raise TripError("amap_error", "高德工具返回错误。")
    if isinstance(value.get("structuredContent"), dict):
        return unwrap(value["structuredContent"])
    if isinstance(value.get("content"), list):
        for block in value["content"]:
            if block.get("type") == "text":
                try:
                    return unwrap(json.loads(block["text"]))
                except (ValueError, TypeError) as error:
                    raise TripError("invalid_amap_result", "高德文本结果不是 JSON 对象。") from error
        raise TripError("invalid_amap_result", "高德结果没有可读取的 JSON 内容。")
    return value


def result_index(snapshot: dict) -> dict:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("results"), list):
        raise TripError("invalid_map_snapshot", "高德交接文件需要 results 数组。")
    result = {}
    for item in snapshot["results"]:
        try:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) \
                    or not item["id"] or item["id"] in result \
                    or not isinstance(item.get("tool"), str) \
                    or not isinstance(item.get("arguments"), dict):
                raise ValueError
            timestamp(item.get("receivedAt"))
        except (ValueError, TypeError) as error:
            raise TripError("invalid_map_record", "高德记录需要唯一 id、tool、arguments、有效 receivedAt。") from error
        result[item["id"]] = {**item, "data": unwrap(item.get("result", item.get("data")))}
    return result


def map_tasks(request: dict, candidates: list[dict], stage: str = "details") -> dict:
    if stage not in {"search", "details"}:
        raise TripError("invalid_stage", "stage 为 search 或 details。")
    nodes = [{**request["origin"], "id": "origin"}, *candidates]
    tasks = [{"id": "weather", "tool": "maps_weather", "arguments": {"city": request["city"]}}]
    for node in nodes:
        detail = stage == "details" and node.get("amapId")
        tasks.append({"id": f"{'poi' if detail else 'search'}:{node['id']}",
                      "tool": "maps_search_detail" if detail else "maps_text_search",
                      "arguments": {"id": node["amapId"]} if detail else {
                          "keywords": node["name"], "city": request["city"], "citylimit": True}})
    return {"schemaVersion": 1, "provider": "existing-official-amap-mcp", "generatedAt": now(),
            "tasks": tasks, "instruction": "由当前 AI 调用已连接的官方高德工具；保存真实 "
            "results:[{id,tool,arguments,receivedAt,result}]。搜索结果需人工或 AI 核对分店、" 
            "地址后填写 amapId；工具命名空间可以保留宿主前缀。"}


def location_of(poi: dict) -> str | None:
    location = poi.get("location")
    if isinstance(location, str) and re.fullmatch(r"-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?", location):
        lon, lat = map(float, location.split(","))
    else:
        point = location if isinstance(location, dict) else {}
        try:
            lon = float(point.get("lng", poi.get("lon", poi.get("lng"))))
            lat = float(point.get("lat", poi.get("lat")))
        except (ValueError, TypeError):
            return None
        location = f"{lon:g},{lat:g}"
    return location if -180 <= lon <= 180 and -90 <= lat <= 90 else None


def resolve_nodes(request: dict, candidates: list[dict], snapshot: dict) -> list[dict]:
    index = result_index(snapshot)
    resolved = []
    for node in [{**request["origin"], "id": "origin"}, *candidates]:
        if not node.get("amapId"):
            raise TripError("poi_selection_required", f"{node['name']} 尚未选定高德 amapId。")
        record = index.get(f"poi:{node['id']}")
        if not record or record["arguments"].get("id") != node["amapId"] \
                or not record["tool"].endswith("maps_search_detail"):
            raise TripError("poi_detail_missing", f"缺少 {node['name']} 对应的高德详情记录。")
        data = record["data"]
        if isinstance(data.get("pois"), list):
            poi = next((item for item in data["pois"] if item.get("id") == node["amapId"]), None)
            if poi is None:
                raise TripError("poi_mismatch", f"{node['name']} 的高德结果 ID 不符。")
        else:
            poi = data.get("poi", data)
        if not isinstance(poi, dict) or poi.get("id") not in {None, node["amapId"]}:
            raise TripError("poi_mismatch", f"{node['name']} 的高德结果 ID 不符。")
        location = location_of(poi)
        if not location:
            raise TripError("poi_location_missing", f"{node['name']} 的高德详情没有有效坐标。")
        resolved.append({**node, "poi": poi, "location": location,
                         "mapReceivedAt": record["receivedAt"]})
    return resolved


def route_tasks(request: dict, candidates: list[dict], snapshot: dict) -> dict:
    nodes = resolve_nodes(request, candidates, snapshot)
    tasks = []
    for source in nodes:
        for target in nodes:
            if source["id"] == target["id"] or source.get("availability") in {"closed", "uncertain"} \
                    or target.get("availability") in {"closed", "uncertain"}:
                continue
            arguments = {"origin": source["location"], "destination": target["location"]}
            if request["mode"] == "transit":
                arguments.update(city=request["city"], cityd=request["city"])
            tasks.append({"id": f"route:{source['id']}:{target['id']}",
                          "tool": "maps_" + ROUTE_SUFFIXES[request["mode"]],
                          "arguments": arguments})
    return {"schemaVersion": 1, "provider": "existing-official-amap-mcp",
            "generatedAt": now(), "tasks": tasks}


def number(value) -> float | None:
    if value is None or isinstance(value, bool) or isinstance(value, (dict, list)) or value == "":
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def normalized_route(record: dict, mode: str) -> dict:
    data = record["data"]
    route = data.get("route", data.get("data", data))
    paths = route.get("transits" if mode == "transit" else "paths", [])
    chosen = paths[0] if paths else route
    distance = number(chosen.get("distance", route.get("distance")))
    cost = chosen.get("cost")
    duration = number(chosen.get("duration", cost.get("duration") if isinstance(cost, dict) else None))
    if distance is None or distance < 0 or duration is None or duration < 0:
        raise TripError("route_unavailable", f"路线 {record['id']} 没有有效距离和耗时。")
    walk = distance if mode == "walking" else number(chosen.get("walking_distance")) \
        if mode == "transit" else 0
    if mode == "transit":
        fare = number(cost.get("transit_fee") if isinstance(cost, dict) else cost)
    elif mode in {"walking", "bicycling"}:
        fare = 0
    else:
        fare = None
    return {"distanceMeters": distance, "durationSeconds": duration,
            "walkingMeters": walk if walk is not None and walk >= 0 else None,
            "fareYuan": fare if fare is not None and fare >= 0 else None,
            "mode": mode, "receivedAt": record["receivedAt"]}
