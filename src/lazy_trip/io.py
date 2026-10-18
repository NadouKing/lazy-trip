import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .errors import TripError

SECRET_KEYS = re.compile(
    r"cookie|authorization|access.?token|refresh.?token|xsec.?token|^token$|^signature$|^headers$",
    re.I,
)


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp needs a timezone")
    return parsed.astimezone(UTC)


def public_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return "#"
        query = [(k, v) for k, v in parse_qsl(parts.query) if not SECRET_KEYS.search(k)]
        return urlunsplit((parts.scheme, parts.netloc.split("@")[-1], parts.path,
                           urlencode(query), ""))
    except (ValueError, TypeError):
        return "#"


def public_data(value):
    """Strip platform access fields before writing shareable evidence or stdout."""
    if isinstance(value, dict):
        return {k: public_data(v) for k, v in value.items() if not SECRET_KEYS.search(k)}
    if isinstance(value, list):
        return [public_data(v) for v in value]
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        return public_url(value)
    return value


def read_json(path: str | Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise TripError("invalid_json_file", "无法读取 JSON 文件，请检查路径和 JSON 格式。") from error


def write_text(path: str | Path, value: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent,
                                         delete=False, suffix=".tmp") as handle:
            temporary = Path(handle.name)
            handle.write(value)
        os.replace(temporary, target)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def write_json(path: str | Path, value) -> None:
    write_text(path, json.dumps(public_data(value), ensure_ascii=False, indent=2, allow_nan=False)
               + "\n")
