import json

import pytest

from lazy_trip.errors import TripError
from lazy_trip.maps import location_of, map_tasks, route_tasks
from lazy_trip.planner import opening_window, plan, weather_for_date
from lazy_trip.render import render_html
from lazy_trip.request import hhmm, validate_candidates, validate_request


def run(sample):
    return plan(sample["request"], sample["candidates"], sample["snapshot"], sample["evidence"])


def record(sample, identifier):
    return next(item for item in sample["snapshot"]["results"] if item["id"] == identifier)


def weather(sample, description="晴", high="25"):
    record(sample, "weather")["result"] = {"forecasts": [{"date": sample["request"]["date"],
        "dayweather": description, "nightweather": description, "daytemp": high, "nighttemp": "20"}]}


def test_return_and_venue_walking(sample):
    route = run(sample)["main"]
    assert route["timeline"][-1]["to"] == "起点"
    assert route["walkingMeters"] == 300 * (len(route["stopIds"]) + 1) + sum(
        item["insideWalkingMeters"] for item in sample["candidates"] if item["id"] in route["stopIds"])
    assert route["walkingMeters"] <= sample["request"]["maxWalkingMeters"]


def test_missing_return_never_guessed(sample):
    sample["snapshot"]["results"] = [item for item in sample["snapshot"]["results"]
        if not (item["id"].startswith("route:") and item["id"].endswith(":origin"))]
    assert run(sample)["state"] == "needs_route_data"
    assert run(sample)["main"] is None


def test_whole_group_budget(sample):
    sample["request"].update(people=4, budgetYuan=100)
    report = run(sample)
    assert "f" not in report["main"]["stopIds"]
    assert report["state"] == "provisional"


def test_closing_hours(sample):
    sample["candidates"][1]["openingHours"] = "09:00-14:10"
    assert "f" not in run(sample)["main"]["stopIds"]


def test_rain_selects_indoor(sample):
    weather(sample, "小雨")
    result = run(sample)
    assert "p" not in result["main"]["stopIds"]
    assert result["main"]["hasFood"] and result["main"]["hasPlay"]


def test_forecast_range_unknown(sample):
    sample["request"]["date"] = "2099-12-31"
    assert weather_for_date(sample["snapshot"], "2099-12-31")["known"] is False
    assert run(sample)["state"] == "provisional"


def test_heat_avoids_midday(sample):
    weather(sample, high="33")
    outdoor = [item for item in run(sample)["main"]["timeline"]
               if item["type"] == "visit" and item["environment"] == "outdoor"]
    assert outdoor and all(item["start"] >= "16:00" for item in outdoor)


def test_wrong_transport_mode_rejected(sample):
    record(sample, "route:origin:p")["tool"] = "maps_direction_driving"
    with pytest.raises(TripError, match="交通方式") as error:
        run(sample)
    assert error.value.code == "route_mode_mismatch"


def test_very_small_walking_limit(sample):
    sample["request"]["maxWalkingMeters"] = 100
    assert run(sample)["state"] == "no_feasible_plan"


def test_closed_business_excluded(sample):
    record(sample, "poi:i")["result"] = {"id": "i", "name": "展馆(暂停营业)", "location": "113.003,23"}
    report = run(sample)
    assert "i" not in report["main"]["stopIds"]
    assert report["excluded"][0]["id"] == "i"


def test_wrong_branch_coordinate_rejected(sample):
    record(sample, "route:origin:p")["arguments"]["destination"] = "120,30"
    with pytest.raises(TripError) as error:
        run(sample)
    assert error.value.code == "route_coordinate_mismatch"


def test_unknown_source_rejected(sample):
    sample["candidates"][0]["evidenceIds"] = ["invented"]
    with pytest.raises(TripError) as error:
        run(sample)
    assert error.value.code == "unresolved_evidence"


def test_unknown_cost_explicit(sample):
    for item in sample["candidates"]:
        item.pop("costYuan")
    report = run(sample)
    assert report["state"] == "provisional"
    assert report["main"]["costYuanGroup"]["complete"] is False


def test_unknown_hours_explicit(sample):
    for item in sample["candidates"]:
        item.pop("openingHours")
    report = run(sample)
    assert report["state"] == "provisional"
    assert report["main"]["openingHoursComplete"] is False


def test_stale_weather(sample):
    record(sample, "weather")["receivedAt"] = "2020-01-01T00:00:00Z"
    result = run(sample)
    assert result["state"] == "provisional"
    assert result["weather"]["fresh"] is False


def test_weather_city_rejected(sample):
    record(sample, "weather")["arguments"]["city"] = "北京"
    with pytest.raises(TripError) as error:
        run(sample)
    assert error.value.code == "weather_city_mismatch"


def test_html_source_escaping(sample):
    sample["evidence"][0]["sourceUrl"] = "javascript:alert(1)"
    sample["candidates"][0]["name"] = '<img src=x onerror="alert(1)">'
    html = render_html(run(sample))
    assert "<script>alert" not in html
    assert 'href="javascript:' not in html
    assert '<img src=x' not in html
    assert "&lt;script&gt;" in html
    assert "Content-Security-Policy" in html


def test_invalid_date_overnight_and_bool_budget(sample):
    for change, code in (({"date": "2026-02-30"}, "invalid_date"),
                          ({"overnight": True}, "out_of_scope"),
                          ({"budgetYuan": True}, "invalid_constraint")):
        with pytest.raises(TripError) as error:
            validate_request({**sample["request"], **change})
        assert error.value.code == code


def test_split_hours_and_overnight_remain_unknown():
    assert opening_window("09:00-12:00 14:00-18:00") is None
    assert opening_window("18:00-02:00") is None
    assert opening_window("25:00-27:00") is None
    assert opening_window("周一至周日 07:30-20:00") == (450, 1200)


def test_missing_temperature_not_zero(sample):
    weather(sample, high="")
    assert run(sample)["weather"]["highC"] is None
    assert run(sample)["weather"]["known"] is False
    assert run(sample)["state"] == "provisional"


def test_wrong_poi_id_and_invalid_coordinates(sample):
    record(sample, "poi:p")["result"] = {"pois": [{"id": "other", "location": "113,23"}]}
    with pytest.raises(TripError) as error:
        run(sample)
    assert error.value.code == "poi_mismatch"
    assert location_of({"location": "999,23"}) is None
    assert location_of({}) is None


def test_transit_unknown_walk_and_fare(sample):
    sample["request"]["mode"] = "transit"
    for row in sample["snapshot"]["results"]:
        if row["id"].startswith("route:"):
            row["tool"] = "maps_direction_transit_integrated"
            row["result"] = {"route": {"transits": [{"duration": 300, "distance": 400}]}}
    report = run(sample)
    assert report["state"] == "provisional"
    assert not report["main"]["walkingComplete"]
    assert not report["main"]["costYuanGroup"]["complete"]


def test_tool_tasks_official_handoff_and_all_directions(sample):
    tasks = map_tasks(sample["request"], sample["candidates"])
    assert tasks["provider"] == "existing-official-amap-mcp"
    assert tasks["tasks"][0]["tool"] == "maps_weather"
    directions = route_tasks(sample["request"], sample["candidates"], sample["snapshot"])
    assert len(directions["tasks"]) == 12
    assert any(task["id"].endswith(":origin") for task in directions["tasks"])


def test_reserved_origin_id_and_duplicate_sources_rejected(sample):
    sample["candidates"][0]["id"] = "origin"
    with pytest.raises(TripError):
        validate_candidates({"candidates": sample["candidates"]})
    sample["candidates"][0]["id"] = "p"
    sample["evidence"].append(sample["evidence"][0])
    with pytest.raises(TripError) as error:
        run(sample)
    assert error.value.code == "duplicate_evidence"


def test_clock_rounding():
    assert hhmm(899.9) == "15:00"


def test_current_resting_not_permanent_closure(sample):
    sample["candidates"][1]["businessStatus"] = "休息中 / 次日07:30开始营业"
    report = run(sample)
    assert not any(item["id"] == "f" for item in report["excluded"])


def test_receipt_future_date_provisional(sample):
    record(sample, "weather")["receivedAt"] = "2099-01-01T00:00:00Z"
    assert run(sample)["state"] == "provisional"


def test_namespace_and_structured_content_supported(sample):
    row = record(sample, "weather")
    row["tool"] = "mcp__amap__maps_weather"
    row["result"] = {"structuredContent": json.loads(row["result"]["content"][0]["text"])}
    assert run(sample)["weather"]["known"] is True
