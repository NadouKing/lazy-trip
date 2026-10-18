import math
import re
from datetime import UTC, date, datetime, timedelta, timezone

from .errors import TripError

CHINA = timezone(timedelta(hours=8))


def finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def minutes(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
        raise TripError("invalid_time", "时间必须是 HH:mm。")
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def hhmm(value: int | float) -> str:
    rounded = math.ceil(value)
    return f"{rounded // 60:02d}:{rounded % 60:02d}"


def china_date(value: datetime | None = None) -> str:
    return (value or datetime.now(UTC)).astimezone(CHINA).date().isoformat()


def validate_request(value: dict) -> dict:
    if not isinstance(value, dict):
        raise TripError("missing_request", "需求必须是 JSON 对象。")
    request = {"timezone": "Asia/Shanghai", "people": 1, "mode": "walking",
               "bufferMinutes": 10, "maxStops": 3, "avoidMiddayHeat": True, **value}
    if request.get("overnight") is True:
        raise TripError("out_of_scope", "第一版仅支持当天往返。")
    if not all(isinstance(request.get(key), str) and request[key].strip()
               for key in ("city", "area")) or not isinstance(request.get("origin"), dict) \
            or not isinstance(request["origin"].get("name"), str) \
            or not request["origin"]["name"].strip():
        raise TripError("missing_request", "请填写 city、area 和 origin.name。")
    try:
        selected_date = date.fromisoformat(request.get("date", ""))
        if selected_date.isoformat() != request["date"]:
            raise ValueError
    except (ValueError, TypeError) as error:
        raise TripError("invalid_date", "请填写有效出行日期 YYYY-MM-DD。") from error
    if minutes(request.get("endTime")) <= minutes(request.get("startTime")):
        raise TripError("invalid_window", "返程时间必须晚于出发时间，第一版不跨日。")
    for key in ("budgetYuan", "maxWalkingMeters", "bufferMinutes"):
        if not finite(request.get(key)) or request[key] < 0:
            raise TripError("invalid_constraint", f"{key} 必须是非负数字。")
    for key, low, high, code in (("people", 1, 20, "invalid_people"),
                                  ("maxStops", 1, 4, "invalid_stops")):
        if type(request.get(key)) is not int or not low <= request[key] <= high:
            raise TripError(code, f"{key} 必须是 {low}–{high} 的整数。")
    if request["mode"] not in {"walking", "transit", "driving", "bicycling"}:
        raise TripError("invalid_mode", "mode 支持 walking、transit、driving、bicycling。")
    if request["timezone"] != "Asia/Shanghai":
        raise TripError("unsupported_timezone", "第一版按中国标准时间排程。")
    return request


def validate_candidates(value: dict) -> list[dict]:
    candidates = value.get("candidates") if isinstance(value, dict) else None
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 6:
        raise TripError("invalid_candidates", "第一版需要 1–6 个候选地点。")
    seen = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise TripError("invalid_candidate", "候选必须是对象。")
        identifier = candidate.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(r"[\w-]+", identifier) \
                or identifier == "origin" or identifier in seen \
                or not isinstance(candidate.get("name"), str) or not candidate["name"].strip() \
                or candidate.get("kind") not in {"food", "play"} \
                or candidate.get("environment") not in {"indoor", "outdoor", "mixed"}:
            raise TripError("invalid_candidate", "候选需要唯一 id、name、kind 和 environment。")
        seen.add(identifier)
        if not finite(candidate.get("stayMinutes")) or candidate["stayMinutes"] <= 0 \
                or not finite(candidate.get("insideWalkingMeters")) \
                or candidate["insideWalkingMeters"] < 0:
            raise TripError("invalid_candidate", f"{identifier} 需要停留时间与场内步行估计。")
        if not isinstance(candidate.get("evidenceIds"), list) or not candidate["evidenceIds"] \
                or any(not isinstance(item, str) or not item for item in candidate["evidenceIds"]):
            raise TripError("missing_evidence", f"{identifier} 缺少 evidenceIds。")
        cost = candidate.get("costYuan")
        if cost is not None and (not isinstance(cost, dict) or not finite(cost.get("min"))
                                 or not finite(cost.get("max")) or cost["min"] < 0
                                 or cost["max"] < cost["min"]):
            raise TripError("invalid_price", f"{identifier} 预算区间无效。")
        if "priority" in candidate and not finite(candidate["priority"]):
            raise TripError("invalid_candidate", f"{identifier} 的 priority 必须是数字。")
        if candidate.get("availability") not in {None, "open", "closed", "uncertain"}:
            raise TripError("invalid_candidate", f"{identifier} 的营业状态无效。")
    return candidates
