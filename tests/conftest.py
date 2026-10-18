import json
from datetime import UTC, datetime, timedelta

import pytest

from lazy_trip.io import now
from lazy_trip.request import validate_candidates, validate_request


@pytest.fixture
def sample():
    selected_date = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
    request = validate_request({"city": "广州", "area": "测试区域",
        "origin": {"name": "起点", "amapId": "o"}, "date": selected_date,
        "startTime": "14:00", "endTime": "19:00", "budgetYuan": 100,
        "maxWalkingMeters": 3000})
    candidates = validate_candidates({"candidates": [
        {"id": "p", "name": "室外公园", "amapId": "p", "kind": "play", "environment": "outdoor",
         "stayMinutes": 60, "insideWalkingMeters": 300, "costYuan": {"min": 0, "max": 0},
         "openingHours": "全天", "evidenceIds": ["e"]},
        {"id": "f", "name": "餐馆", "amapId": "f", "kind": "food", "environment": "indoor",
         "stayMinutes": 45, "insideWalkingMeters": 20, "costYuan": {"min": 20, "max": 30},
         "openingHours": "10:00-20:00", "evidenceIds": ["e"]},
        {"id": "i", "name": "室内展馆", "amapId": "i", "kind": "play", "environment": "indoor",
         "stayMinutes": 45, "insideWalkingMeters": 100, "costYuan": {"min": 0, "max": 0},
         "openingHours": "10:00-20:00", "evidenceIds": ["e"]},
    ]})
    results = []
    coords = {"origin": "113,23", "p": "113.001,23", "f": "113.002,23", "i": "113.003,23"}

    def add(identifier, tool, arguments, data):
        results.append({"id": identifier, "tool": tool, "arguments": arguments, "receivedAt": now(),
                        "result": {"content": [{"type": "text", "text": json.dumps(data)}]}})

    add("weather", "maps_weather", {"city": "广州"}, {"forecasts": [{"date": selected_date,
        "dayweather": "晴", "nightweather": "晴", "daytemp": "25", "nighttemp": "20"}]})
    for node in [{"id": "origin", "amapId": "o", "name": "起点"}, *candidates]:
        add(f"poi:{node['id']}", "maps_search_detail", {"id": node["amapId"]},
            {"id": node["amapId"], "name": node["name"], "location": coords[node["id"]]})
    for source in coords:
        for target in coords:
            if source != target:
                add(f"route:{source}:{target}", "maps_direction_walking",
                    {"origin": coords[source], "destination": coords[target]},
                    {"route": {"paths": [{"distance": "300", "duration": "240"}]}})
    return {"request": request, "candidates": candidates, "snapshot": {"results": results},
            "evidence": [{"id": "e", "source": "synthetic", "sourceUrl": "https://example.com",
                          "title": "<script>alert(1)</script>"}]}
